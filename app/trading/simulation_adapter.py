"""模拟交易适配器：所有资金 / 持仓变动经由冻结台账原子提交。"""

import logging
import threading
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from app.trading.base import (
    TradingAdapter,
    Order,
    OrderStatus,
    OrderType,
    OrderSide,
    Position,
    Account,
)
from app.trading.ledger import FreezeLedger, FreezeError, _money

logger = logging.getLogger(__name__)


class SimulationAdapter(TradingAdapter):
    """带冻结 / 释放台账的模拟适配器。

    并发安全：``place_order`` / ``cancel_order`` / ``apply_fill`` /
    ``recover`` 全部在同一把 ``_lock`` 内完成“检查—冻结—记账—撮合”，
    并发请求串行提交临界区，不会出现负余额或同一额度被两次承诺。
    """

    def __init__(self, config: Optional[Dict] = None):
        super().__init__(config or {})

        # 初始资金
        initial_cash = (
            Decimal(str(config.get("initial_cash", 1000000)))
            if config
            else Decimal("1000000")
        )

        self._account = Account(
            account_id="SIM_" + datetime.now().strftime("%Y%m%d%H%M%S"),
            broker="模拟交易",
            total_assets=initial_cash,
            available_cash=initial_cash,
            frozen_cash=Decimal("0"),
            market_value=Decimal("0"),
            profit_loss=Decimal("0"),
            profit_loss_ratio=0.0,
            capital_cash=initial_cash,
            settled_cash=Decimal("0"),
        )

        self._positions: Dict[str, Position] = {}
        self._orders: Dict[str, Order] = {}
        self._client_order_ids: Dict[str, str] = {}
        self._ledger = FreezeLedger()
        self._lock = threading.RLock()

        # 交易成本配置
        self.commission_rate = (
            Decimal(str(config.get("commission_rate", 0.0003)))
            if config
            else Decimal("0.0003")
        )
        self.min_commission = (
            Decimal(str(config.get("min_commission", 5))) if config else Decimal("5")
        )
        self.stamp_tax_rate = (
            Decimal(str(config.get("stamp_tax_rate", 0.001)))
            if config
            else Decimal("0.001")
        )
        self.slippage_rate = config.get("slippage_rate", 0.001) if config else 0.001
        self.default_quote_price = Decimal(
            str(config.get("default_quote_price", 10)) if config else "10"
        )

        # 模拟行情
        self._quotes: Dict[str, Dict] = {}

    # ------------------------------------------------------------------ #
    # 连接
    # ------------------------------------------------------------------ #
    def connect(self) -> bool:
        """业务模块说明。"""
        with self._lock:
            self._connected = True
            logger.info("Simulation adapter connected")
            return True

    def disconnect(self) -> None:
        """业务模块说明。"""
        with self._lock:
            self._connected = False
            logger.info("Simulation adapter disconnected")

    # ------------------------------------------------------------------ #
    # 查询
    # ------------------------------------------------------------------ #
    def get_account(self) -> Optional[Account]:
        """业务模块说明。"""
        return self._account

    def get_positions(self) -> List[Position]:
        """业务模块说明。"""
        with self._lock:
            return list(self._positions.values())

    def get_position(self, stock_code: str) -> Optional[Position]:
        """业务模块说明。"""
        with self._lock:
            return self._positions.get(stock_code)

    def get_freeze_events(self, order_id: Optional[str] = None) -> List[Dict]:
        """冻结流水，解释每笔订单额度的预留 / 结算 / 释放。"""
        with self._lock:
            return [e.to_dict() for e in self._ledger.events(order_id)]

    def get_reservations(self) -> List[Dict]:
        """当前仍在途（占用额度）的订单及占用量。"""
        with self._lock:
            result = []
            for order in self._orders.values():
                if order.frozen_cash > 0 or order.frozen_quantity > 0:
                    result.append(
                        {
                            "order_id": order.order_id,
                            "stock_code": order.stock_code,
                            "side": order.side.value,
                            "frozen_cash": float(order.frozen_cash),
                            "frozen_quantity": order.frozen_quantity,
                            "remaining_quantity": order.quantity
                            - order.filled_quantity,
                        }
                    )
            return result

    # ------------------------------------------------------------------ #
    # 下单：确认时固定冻结规则
    # ------------------------------------------------------------------ #
    def place_order(self, order: Order) -> Order:
        """业务模块说明。"""
        with self._lock:
            if not self._connected:
                order.status = OrderStatus.FAILED
                order.error_message = "交易连接已断开"
                return order

            # 幂等：同一 client_order_id 的重试直接返回首单，不二次冻结
            if order.client_order_id:
                existing_id = self._client_order_ids.get(order.client_order_id)
                if existing_id is not None:
                    logger.info(
                        "幂等命中 client_order_id=%s -> %s，跳过重放",
                        order.client_order_id,
                        existing_id,
                    )
                    return self._orders[existing_id]

            # 获取行情（市价单需要参考价，限价单也用于可成交判断）
            quote = self.get_quote(order.stock_code)
            if not quote:
                order.status = OrderStatus.REJECTED
                order.error_message = "无法获取行情数据"
                return order

            current_price = Decimal(str(quote["last_price"]))
            freeze_price, marketable_fill_price = self._freeze_and_fill_price(
                order, current_price
            )
            estimated_fee = self._estimate_fee(order, freeze_price)

            # 确认即冻结：冻结规则（单价、数量、预估费）固定进订单快照
            try:
                if order.side == OrderSide.BUY:
                    self._ledger.reserve_buy(
                        order, self._account, freeze_price, estimated_fee
                    )
                else:
                    self._ledger.reserve_sell(order, self._positions)
            except FreezeError as exc:
                # 预留失败：什么都没扣，直接拒单，账户 / 持仓零变动
                order.status = OrderStatus.REJECTED
                order.error_message = str(exc)
                order.freeze_state = "none"
                logger.warning("订单 %s 冻结失败被拒: %s", order.order_id, exc)
                return order

            order.status = OrderStatus.SUBMITTED
            order.updated_at = datetime.now()
            self._orders[order.order_id] = order
            if order.client_order_id:
                self._client_order_ids[order.client_order_id] = order.order_id

            # 立即撮合（限价单达到条件 / 市价单）；未成交则挂起，额度继续冻结
            if marketable_fill_price is not None:
                try:
                    self._settle_order(order, order.quantity, marketable_fill_price)
                except FreezeError:
                    # 结算异常：释放本单全部预留，按失败处理，绝不留悬挂冻结
                    logger.exception(
                        "订单 %s 确认后即时结算失败，释放冻结", order.order_id
                    )
                    self._ledger.release(
                        order,
                        self._account,
                        self._positions,
                        reason="即时结算失败，释放预留",
                    )
                    order.status = OrderStatus.FAILED
                    order.error_message = "即时结算失败，已释放冻结额度"
                    self._client_order_ids.pop(order.client_order_id, None)
                    self._refresh_valuations(order.stock_code)

            self._emit("on_order", order)
            return order

    def _freeze_and_fill_price(
        self, order: Order, current_price: Decimal
    ) -> tuple[Decimal, Optional[Decimal]]:
        """返回 (冻结单价, 可立即成交价)。冻结价对买入始终保守（>=成交价）。"""
        slippage = current_price * Decimal(str(self.slippage_rate))

        if order.order_type == OrderType.MARKET:
            if order.side == OrderSide.BUY:
                fill_price = current_price + slippage
            else:
                fill_price = current_price - slippage
            # 市价买单按含滑点的上限冻结，保证结算时冻结足够
            return fill_price, fill_price

        # 限价单：按委托价冻结
        if order.price is None:
            # 理论上服务层已拦截，兜底
            raise FreezeError("限价单必须指定价格")
        fill_price: Optional[Decimal] = None
        if order.side == OrderSide.BUY and current_price <= order.price:
            fill_price = order.price
        elif order.side == OrderSide.SELL and current_price >= order.price:
            fill_price = order.price
        return order.price, fill_price

    def _estimate_fee(self, order: Order, price: Decimal) -> Decimal:
        """订单确认时的费用预估，与成交时的实际计费口径保持一致。"""
        amount = price * order.quantity
        commission = max(amount * self.commission_rate, self.min_commission)
        if order.side == OrderSide.SELL:
            commission += amount * self.stamp_tax_rate
        return _money(commission)

    def _actual_fee(self, order: Order, price: Decimal, quantity: int) -> Decimal:
        """增量费用：按累计成交口径计算，返回本笔新增费用。

        部分成交时最低佣金不应按笔重复收取，否则预留的单笔预估费用不够；
        因此以累计成交额重算总费用，减去已累计费用，得到本笔增量。
        """
        prev_amount = Decimal(getattr(order, "_cum_trade_amount", "0"))
        new_amount = prev_amount + price * quantity
        order._cum_trade_amount = new_amount

        prev_fee = self._cumulative_fee(order, prev_amount)
        new_fee = self._cumulative_fee(order, new_amount)
        return _money(new_fee - prev_fee)

    def _cumulative_fee(self, order: Order, amount: Decimal) -> Decimal:
        if amount <= 0:
            return Decimal("0")
        commission = max(amount * self.commission_rate, self.min_commission)
        if order.side == OrderSide.SELL:
            commission += amount * self.stamp_tax_rate
        return _money(commission)

    # ------------------------------------------------------------------ #
    # 成交结算（支持部分成交，可外部驱动挂起的限价单）
    # ------------------------------------------------------------------ #
    def apply_fill(
        self,
        order_id: str,
        fill_quantity: Optional[int] = None,
        fill_price: Optional[float] = None,
    ) -> Order:
        """对挂起 / 部分成交的订单模拟一笔（部分）成交。"""
        with self._lock:
            order = self._orders.get(order_id)
            if order is None:
                raise FreezeError(f"订单不存在: {order_id}")
            if order.status not in (OrderStatus.SUBMITTED, OrderStatus.PARTIAL_FILLED):
                raise FreezeError(
                    f"订单状态 {order.status.value}，不可再成交: {order_id}"
                )

            remaining = order.quantity - order.filled_quantity
            qty = fill_quantity if fill_quantity is not None else remaining
            if qty <= 0 or qty > remaining:
                raise FreezeError(
                    f"成交数量非法: {qty}，剩余 {remaining}"
                )
            price = Decimal(str(fill_price)) if fill_price is not None else (
                order.filled_price or order.price or self.default_quote_price
            )
            self._settle_order(order, qty, price)
            return order

    def _settle_order(
        self, order: Order, fill_quantity: int, fill_price: Decimal
    ) -> None:
        """在台账上结算一笔成交，并刷新订单状态与账户估值。"""
        fee = self._actual_fee(order, fill_price, fill_quantity)
        try:
            self._ledger.settle(
                order,
                fill_quantity,
                fill_price,
                fee,
                self._account,
                self._positions,
            )
        except FreezeError:
            # 结算异常不应吃掉冻结：订单保持在途，等待撤单 / 恢复
            logger.exception("订单 %s 结算失败，冻结保留", order.order_id)
            raise

        # 累计实际费用与成交均价
        order.commission = _money(order.commission + fee)
        if order.filled_price is None:
            order.filled_price = fill_price
        else:
            total = order.filled_price * (order.filled_quantity - fill_quantity)
            order.filled_price = (total + fill_price * fill_quantity) / order.filled_quantity

        if order.filled_quantity >= order.quantity:
            order.status = OrderStatus.FILLED
        else:
            order.status = OrderStatus.PARTIAL_FILLED
        order.updated_at = datetime.now()

        # 卖出清仓则移除持仓键
        pos = self._positions.get(order.stock_code)
        if pos is not None and pos.quantity == 0:
            del self._positions[order.stock_code]

        self._refresh_valuations(order.stock_code)
        self._emit("on_trade", order)
        if order.status == OrderStatus.FILLED:
            logger.info(
                "Order filled: %s %s %s %s@%s fee=%s",
                order.order_id,
                order.side.value,
                order.stock_code,
                order.quantity,
                fill_price,
                fee,
            )

    def _refresh_valuations(self, moved_code: Optional[str] = None) -> None:
        """按最新价重算市值 / 盈亏与总资产；现金恒等式由台账保证。"""
        for code, pos in self._positions.items():
            pos.market_value = _money(pos.current_price * pos.quantity)
            if pos.avg_cost > 0:
                pos.profit_loss = _money(
                    (pos.current_price - pos.avg_cost) * pos.quantity
                )
                pos.profit_loss_ratio = float(
                    (pos.current_price - pos.avg_cost) / pos.avg_cost
                )
            pos.updated_at = datetime.now()

        self._account.market_value = _money(
            sum((p.market_value for p in self._positions.values()), Decimal("0"))
        )
        # 现金钱包 = 可用 + 冻结；总资产 = 现金钱包 + 市值
        self._account.total_assets = _money(
            self._account.available_cash
            + self._account.frozen_cash
            + self._account.market_value
        )
        self._account.profit_loss = _money(
            sum((p.profit_loss for p in self._positions.values()), Decimal("0"))
        )
        cost_basis = self._account.capital_cash - self._account.settled_cash
        if cost_basis > 0:
            self._account.profit_loss_ratio = float(
                self._account.profit_loss / cost_basis
            )
        self._account.updated_at = datetime.now()

    # ------------------------------------------------------------------ #
    # 撤单：幂等释放剩余冻结
    # ------------------------------------------------------------------ #
    def cancel_order(self, order_id: str) -> bool:
        """业务模块说明。"""
        with self._lock:
            order = self._orders.get(order_id)
            if not order:
                return False

            if order.status not in (
                OrderStatus.PENDING,
                OrderStatus.SUBMITTED,
                OrderStatus.PARTIAL_FILLED,
            ):
                # 已成交 / 已撤 / 拒单：不允许再撤（release 本身仍是幂等的）
                return False

            released = self._ledger.release(
                order,
                self._account,
                self._positions,
                reason=f"撤单 {order_id}，释放剩余冻结",
            )
            order.status = OrderStatus.CANCELLED
            order.updated_at = datetime.now()
            self._refresh_valuations(order.stock_code)
            self._emit("on_order", order)
            logger.info("订单 %s 已撤销，释放: %s", order_id, released)
            return True

    # ------------------------------------------------------------------ #
    # 恢复：按订单确认快照重建占用
    # ------------------------------------------------------------------ #
    def recover(self) -> Dict:
        """重连 / 故障恢复后对账，修平冻结漂移，回收孤儿冻结。"""
        with self._lock:
            report = self._ledger.reconcile(
                list(self._orders.values()), self._account, self._positions
            )
            self._refresh_valuations()
            return report

    # ------------------------------------------------------------------ #
    # 订单 / 行情查询
    # ------------------------------------------------------------------ #
    def get_order(self, order_id: str) -> Optional[Order]:
        """业务模块说明。"""
        with self._lock:
            return self._orders.get(order_id)

    def get_orders(
        self,
        stock_code: Optional[str] = None,
        status: Optional[OrderStatus] = None,
    ) -> List[Order]:
        """业务模块说明。"""
        with self._lock:
            orders = list(self._orders.values())

        if stock_code:
            orders = [o for o in orders if o.stock_code == stock_code]
        if status:
            orders = [o for o in orders if o.status == status]
        return sorted(orders, key=lambda o: o.created_at, reverse=True)

    def get_quote(self, stock_code: str) -> Optional[Dict]:
        """业务模块说明。"""
        with self._lock:
            if stock_code not in self._quotes:
                self.set_quote(stock_code, float(self.default_quote_price))

            quote = self._quotes[stock_code]
            quote["bid_price_1"] = quote["last_price"] * 0.999
            quote["ask_price_1"] = quote["last_price"] * 1.001
            quote["datetime"] = datetime.now().isoformat()

            if stock_code in self._positions:
                self._positions[stock_code].current_price = Decimal(
                    str(quote["last_price"])
                )
                self._refresh_valuations(stock_code)

            return dict(quote)

    def set_quote(self, stock_code: str, price: float) -> None:
        """业务模块说明。"""
        with self._lock:
            self._quotes[stock_code] = {
                "stock_code": stock_code,
                "last_price": price,
                "open": price,
                "high": price * 1.02,
                "low": price * 0.98,
                "close": price,
                "volume": 1000000,
                "bid_price_1": price * 0.999,
                "ask_price_1": price * 1.001,
                "bid_volume_1": 1000,
                "ask_volume_1": 1000,
                "datetime": datetime.now().isoformat(),
            }
