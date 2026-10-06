"""模拟交易适配器：所有资金 / 持仓变动都通过 ``FreezeLedger`` 原子完成。

生命周期与额度对应关系：

- 下单确认：买入冻结现金（限价按限价、市价按保护价），卖出冻结持仓，
  冻结规则写入订单快照；
- 成交（支持部分成交、多次回报）：冻结转已结算；
- 撤单 / 拒单 / 失败：剩余冻结幂等释放；
- 重试：释放旧冻结后按新价格重新固定规则；
- 恢复：按未成交委托重建冻结。

``place_order`` / ``cancel_order`` / ``simulate_fill`` 均在台账锁内执行
「校验 + 变动」，并发请求不会出现同一笔资金 / 持仓被两次承诺。
"""

import logging
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
from app.trading.ledger import (
    FreezeLedger,
    LedgerError,
    REASON_CANCEL,
    REASON_REJECT,
    REASON_RETRY,
    REASON_FILL,
)

logger = logging.getLogger(__name__)


class SimulationAdapter(TradingAdapter):
    """业务模块说明。"""

    def __init__(self, config: Optional[Dict] = None):
        super().__init__(config or {})

        # 初始资金
        initial_cash = Decimal(str(config.get("initial_cash", 1000000))) if config else Decimal("1000000")

        self._account = Account(
            account_id="SIM_" + datetime.now().strftime("%Y%m%d%H%M%S"),
            broker="模拟交易",
            total_assets=initial_cash,
            available_cash=initial_cash,
            frozen_cash=Decimal("0"),
            market_value=Decimal("0"),
            profit_loss=Decimal("0"),
            profit_loss_ratio=0.0,
        )

        self._positions: Dict[str, Position] = {}
        self._orders: Dict[str, Order] = {}
        # 客户端幂等单号 -> 内部订单号，并发重试只落一笔委托
        self._client_index: Dict[str, str] = {}

        # 交易成本配置
        self.commission_rate = Decimal(str(config.get("commission_rate", 0.0003))) if config else Decimal("0.0003")
        self.min_commission = Decimal(str(config.get("min_commission", 5))) if config else Decimal("5")
        self.stamp_tax_rate = Decimal(str(config.get("stamp_tax_rate", 0.001))) if config else Decimal("0.001")
        self.slippage_rate = config.get("slippage_rate", 0.001) if config else 0.001
        self.default_quote_price = Decimal(
            str(config.get("default_quote_price", 10)) if config else "10"
        )

        # 冻结台账
        self.ledger = FreezeLedger(
            self._account,
            self._positions,
            market_protect_ratio=config.get("market_protect_ratio", 0.03) if config else Decimal("0.03"),
            t_plus_1=bool(config.get("t_plus_1", False)) if config else False,
        )

        # 模拟行情
        self._quotes: Dict[str, Dict] = {}

    def connect(self) -> bool:
        """业务模块说明。"""
        self._connected = True
        logger.info("Simulation adapter connected")
        return True

    def disconnect(self) -> None:
        """业务模块说明。"""
        self._connected = False
        logger.info("Simulation adapter disconnected")

    def get_account(self) -> Optional[Account]:
        """业务模块说明。"""
        return self._account

    def get_positions(self) -> List[Position]:
        """业务模块说明。"""
        with self.ledger.lock:
            return list(self._positions.values())

    def get_position(self, stock_code: str) -> Optional[Position]:
        """业务模块说明。"""
        with self.ledger.lock:
            return self._positions.get(stock_code)

    # ------------------------------------------------------------------
    # 下单：校验与冻结在同一把锁内原子完成
    # ------------------------------------------------------------------

    def place_order(self, order: Order) -> Order:
        """业务模块说明。"""
        with self.ledger.lock:
            if not self._connected:
                order.status = OrderStatus.FAILED
                order.error_message = "交易连接已断开"
                self._orders[order.order_id] = order
                return order

            # 幂等：同一 client_order_id 的并发/重试请求返回同一笔委托
            if order.client_order_id:
                existing_id = self._client_index.get(order.client_order_id)
                if existing_id is not None:
                    logger.info(
                        f"Duplicate client_order_id={order.client_order_id}, "
                        f"return existing order {existing_id}"
                    )
                    return self._orders[existing_id]

            # 价格口径统一为 Decimal（外部可能直接传入 float）
            if order.price is not None and not isinstance(order.price, Decimal):
                order.price = Decimal(str(order.price))

            quote = self.get_quote(order.stock_code)
            if not quote:
                order.status = OrderStatus.REJECTED
                order.error_message = "无法获取行情数据"
                self._orders[order.order_id] = order
                return order

            current_price = Decimal(str(quote["last_price"]))

            # 冻结：现金/持仓不足在此被权威拒绝（台账状态不变）
            try:
                entry = self.ledger.freeze(
                    order,
                    reference_price=current_price,
                    commission_rate=self.commission_rate,
                    min_commission=self.min_commission,
                )
            except LedgerError as e:
                order.status = OrderStatus.REJECTED
                order.error_message = str(e)
                self._orders[order.order_id] = order
                return order

            order.freeze_rule = entry.rule
            order.frozen_amount = entry.frozen_cash
            order.frozen_quantity = entry.frozen_qty
            order.status = OrderStatus.SUBMITTED
            order.updated_at = datetime.now()
            self._orders[order.order_id] = order
            if order.client_order_id:
                self._client_index[order.client_order_id] = order.order_id

            self._emit("on_order", order)

            # 尝试即时撮合（市价单 / 已越过限价的限价单）
            fill_price = self._match_price(order, current_price)
            if fill_price is not None:
                self._apply_fill(order, order.quantity - order.filled_quantity, fill_price)

            return order

    def _match_price(self, order: Order, current_price: Decimal) -> Optional[Decimal]:
        """判断当前行情下订单的成交价，不可成交返回 None。"""
        if order.order_type == OrderType.MARKET:
            slippage = current_price * Decimal(str(self.slippage_rate))
            if order.side == OrderSide.BUY:
                return current_price + slippage
            return current_price - slippage

        if order.order_type == OrderType.LIMIT and order.price is not None:
            if order.side == OrderSide.BUY and current_price <= order.price:
                return order.price
            if order.side == OrderSide.SELL and current_price >= order.price:
                return order.price
        return None

    def _commission_for(self, order: Order, amount: Decimal) -> Decimal:
        """计算单笔成交费用（卖出含印花税）。"""
        commission = max(amount * self.commission_rate, self.min_commission)
        if order.side == OrderSide.SELL:
            commission += amount * self.stamp_tax_rate
        return commission

    def _apply_fill(self, order: Order, fill_quantity: int, fill_price: Decimal) -> Order:
        """在台账锁内结算一笔成交（可多次部分成交），幂等防重复。"""
        with self.ledger.lock:
            if order.status in (OrderStatus.FILLED, OrderStatus.CANCELLED,
                                OrderStatus.REJECTED, OrderStatus.FAILED):
                logger.warning(
                    f"Ignore fill for terminal order {order.order_id} "
                    f"status={order.status.value}"
                )
                return order

            remaining = order.quantity - order.filled_quantity
            fill_quantity = min(fill_quantity, remaining)
            if fill_quantity <= 0:
                return order

            gross = fill_price * fill_quantity
            commission = self._commission_for(order, gross)

            try:
                self.ledger.settle_fill(
                    order,
                    fill_quantity=fill_quantity,
                    fill_price=fill_price,
                    commission=commission,
                    reason=REASON_FILL,
                )
            except LedgerError as e:
                # 冻结额度不足以结算（如市价穿透保护价）：拒单并释放剩余冻结
                logger.error(f"Settle failed for {order.order_id}: {e}")
                order.status = OrderStatus.REJECTED
                order.error_message = f"成交结算失败: {e}"
                self.ledger.release(order, reason=REASON_REJECT, note=str(e))
                self._emit("on_order", order)
                return order

            # 累计成交，成交均价
            total_qty = order.filled_quantity + fill_quantity
            if order.filled_price is not None:
                order.filled_price = (
                    order.filled_price * order.filled_quantity + fill_price * fill_quantity
                ) / total_qty
            else:
                order.filled_price = fill_price
            order.filled_quantity = total_qty
            order.commission += commission
            order.updated_at = datetime.now()

            if order.filled_quantity >= order.quantity:
                order.status = OrderStatus.FILLED
                # 全部成交：释放买入预留的费用差额 / 任何残余冻结（幂等）
                self.ledger.release(order, reason=REASON_FILL, note="remainder after full fill")
            else:
                order.status = OrderStatus.PARTIAL_FILLED

            self._refresh_account()
            self._emit("on_trade", order)
            self._emit("on_order", order)
            logger.info(
                f"Order fill: {order.order_id} {order.side.value} "
                f"{order.stock_code} {fill_quantity}@{fill_price} "
                f"({order.filled_quantity}/{order.quantity})"
            )
            return order

    def simulate_fill(
        self,
        order_id: str,
        quantity: Optional[int] = None,
        price: Optional[float] = None,
    ) -> Optional[Order]:
        """供运营 / 测试驱动一笔部分或全部成交（模拟网关成交回报）。"""
        with self.ledger.lock:
            order = self._orders.get(order_id)
            if not order:
                return None
            fill_price = Decimal(str(price)) if price is not None else (
                order.price or Decimal(str(self.get_quote(order.stock_code)["last_price"]))
            )
            qty = quantity if quantity is not None else order.quantity - order.filled_quantity
            return self._apply_fill(order, qty, fill_price)

    def _match_resting_orders(self, stock_code: str, current_price: Decimal) -> None:
        """行情更新后尝试撮合该标的的未成交委托。"""
        for order in list(self._orders.values()):
            if order.stock_code != stock_code:
                continue
            if order.status not in (OrderStatus.SUBMITTED, OrderStatus.PARTIAL_FILLED):
                continue
            fill_price = self._match_price(order, current_price)
            if fill_price is not None:
                self._apply_fill(order, order.quantity - order.filled_quantity, fill_price)

    # ------------------------------------------------------------------
    # 撤单 / 重试 / 恢复
    # ------------------------------------------------------------------

    def cancel_order(self, order_id: str) -> bool:
        """业务模块说明。"""
        with self.ledger.lock:
            order = self._orders.get(order_id)
            if not order:
                return False

            if order.status not in (OrderStatus.SUBMITTED, OrderStatus.PENDING,
                                    OrderStatus.PARTIAL_FILLED):
                # 终结状态或已撤销：台账释放本身幂等，但撤单动作报失败
                return False

            released = self.ledger.release(order, reason=REASON_CANCEL)
            order.status = OrderStatus.CANCELLED
            order.updated_at = datetime.now()
            self._refresh_account()
            self._emit("on_order", order)
            logger.info(
                f"Order cancelled: {order_id}, "
                f"released cash={released['cash']}, qty={released['quantity']}"
            )
            return True

    def retry_order(self, order_id: str, price: Optional[float] = None) -> Optional[Order]:
        """重试被拒 / 失败 / 已撤销的委托：幂等释放旧冻结后重新确认。"""
        with self.ledger.lock:
            order = self._orders.get(order_id)
            if not order:
                return None
            if order.status in (OrderStatus.FILLED, OrderStatus.PARTIAL_FILLED):
                order.error_message = "已成交（含部分成交）的订单不能重试，请对剩余数量另下新单"
                return order

            quote = self.get_quote(order.stock_code)
            current_price = Decimal(str(quote["last_price"])) if quote else self.default_quote_price
            if price is not None:
                order.price = Decimal(str(price))

            order.error_message = None
            order.status = OrderStatus.PENDING
            order.filled_quantity = 0
            order.filled_price = None
            order.commission = Decimal("0")

            try:
                entry = self.ledger.retry(
                    order,
                    reference_price=current_price,
                    commission_rate=self.commission_rate,
                    min_commission=self.min_commission,
                )
            except LedgerError as e:
                order.status = OrderStatus.REJECTED
                order.error_message = str(e)
                return order

            order.freeze_rule = entry.rule
            order.frozen_amount = entry.frozen_cash
            order.frozen_quantity = entry.frozen_qty
            order.status = OrderStatus.SUBMITTED
            order.updated_at = datetime.now()
            if order.client_order_id:
                self._client_index[order.client_order_id] = order.order_id
            self._emit("on_order", order)

            fill_price = self._match_price(order, current_price)
            if fill_price is not None:
                self._apply_fill(order, order.quantity, fill_price)
            return order

    def recover_orders(self, orders: List[Order]) -> Dict[str, list]:
        """重连 / 恢复后按未终结委托重建冻结。"""
        with self.ledger.lock:
            reference_prices = {}
            for order in orders:
                if order.order_id not in self._orders:
                    self._orders[order.order_id] = order
                quote = self._quotes.get(order.stock_code)
                reference_prices[order.stock_code] = (
                    Decimal(str(quote["last_price"])) if quote
                    else (order.price or self.default_quote_price)
                )
            result = self.ledger.recover(
                orders,
                reference_prices=reference_prices,
                commission_rate=self.commission_rate,
                min_commission=self.min_commission,
            )
            self._refresh_account()
            return result

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get_order(self, order_id: str) -> Optional[Order]:
        """业务模块说明。"""
        return self._orders.get(order_id)

    def get_orders(
        self,
        stock_code: Optional[str] = None,
        status: Optional[OrderStatus] = None,
    ) -> List[Order]:
        """业务模块说明。"""
        orders = list(self._orders.values())

        if stock_code:
            orders = [o for o in orders if o.stock_code == stock_code]

        if status:
            orders = [o for o in orders if o.status == status]

        return sorted(orders, key=lambda o: o.created_at, reverse=True)

    def get_quote(self, stock_code: str) -> Optional[Dict]:
        """业务模块说明。"""
        if stock_code not in self._quotes:
            self.set_quote(stock_code, float(self.default_quote_price))

        quote = self._quotes[stock_code]
        quote["bid_price_1"] = quote["last_price"] * 0.999
        quote["ask_price_1"] = quote["last_price"] * 1.001
        quote["datetime"] = datetime.now().isoformat()

        # 更新持仓当前价格
        if stock_code in self._positions:
            with self.ledger.lock:
                self._positions[stock_code].current_price = Decimal(str(quote["last_price"]))
                self._refresh_account_locked()

        # 行情变化后撮合未成交委托
        if self._connected:
            with self.ledger.lock:
                self._match_resting_orders(stock_code, Decimal(str(quote["last_price"])))

        return quote

    def set_quote(self, stock_code: str, price: float) -> None:
        """业务模块说明。"""
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
        if self._connected:
            with self.ledger.lock:
                self._match_resting_orders(stock_code, Decimal(str(price)))

    # ------------------------------------------------------------------
    # 账户汇总 / 冻结解释
    # ------------------------------------------------------------------

    def _refresh_account(self) -> None:
        with self.ledger.lock:
            self._refresh_account_locked()

    def _refresh_account_locked(self) -> None:
        # 全部卖出后移除零持仓（台账中不再持有该标的）
        empty = [code for code, pos in self._positions.items() if pos.quantity <= 0]
        for code in empty:
            del self._positions[code]

        for pos in self._positions.values():
            pos.market_value = pos.current_price * pos.quantity
            if pos.avg_cost > 0:
                pos.profit_loss = (pos.current_price - pos.avg_cost) * pos.quantity
                pos.profit_loss_ratio = float(
                    (pos.current_price - pos.avg_cost) / pos.avg_cost
                )
            pos.updated_at = datetime.now()

        # 冻结现金仍是客户资产的一部分，总资产 = 可用 + 冻结 + 市值
        self._account.market_value = sum(p.market_value for p in self._positions.values())
        self._account.total_assets = (
            self._account.available_cash
            + self._account.frozen_cash
            + self._account.market_value
        )
        self._account.profit_loss = sum(p.profit_loss for p in self._positions.values())
        cost_basis = self._account.total_assets - self._account.profit_loss
        if cost_basis > 0:
            self._account.profit_loss_ratio = float(
                self._account.profit_loss / cost_basis
            )
        self._account.updated_at = datetime.now()

    def freeze_report(self) -> Dict:
        """可用 / 冻结 / 已结算的差异解释与守恒校验。"""
        with self.ledger.lock:
            return {
                "cash": self.ledger.account_breakdown(),
                "positions": self.ledger.position_breakdown(),
                "conservation": self.ledger.conservation_report(),
            }

    def freeze_entries(self, active_only: bool = True) -> List[Dict]:
        """逐笔订单的冻结记录。"""
        return [e.to_dict() for e in self.ledger.list_entries(active_only=active_only)]

    def freeze_moves(self, order_id: Optional[str] = None) -> List[Dict]:
        """冻结 / 释放 / 结算的审计流水。"""
        return [m.to_dict() for m in self.ledger.moves(order_id)]
