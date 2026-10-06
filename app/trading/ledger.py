"""资金与持仓的冻结 / 释放台账。

设计目标（并发下单场景）：

* 每一次占用（预留）、结算（成交）、释放（撤单 / 拒单 / 故障 / 重试）都是
  显式且可追踪的，落成只追加的 ``FreezeEvent`` 流水；
* 现金守恒：``capital_cash = available_cash + frozen_cash + settled_cash``，
  其中 ``settled_cash`` 为已成交净流出（买入为正、卖出为负、费用为正）；
* 持仓守恒：``quantity = available_quantity + frozen_quantity``；
* 释放按订单幂等：同一订单重复释放（撤单重试、恢复重放）不会第二次把
  额度放回可用，杜绝重复释放；
* 所有方法都必须在适配器的同一把锁内调用，保证“检查—扣减—记账”原子完成，
  并发请求不会产生负余额。
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional

from app.trading.base import Order, OrderSide, OrderStatus, Position, Account

logger = logging.getLogger(__name__)

CENT = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    """统一按分取整，避免部分成交多次拆分产生尾差。"""
    return Decimal(value).quantize(CENT)


class FreezeEventType(Enum):
    """台账事件类型。"""

    RESERVE_CASH = "reserve_cash"          # 买单确认，预留现金
    RESERVE_POSITION = "reserve_position"  # 卖单确认，预留持仓
    SETTLE_BUY = "settle_buy"              # 买入成交，冻结转已结算（含找零）
    SETTLE_SELL = "settle_sell"            # 卖出成交，交付持仓并回收现金
    RELEASE_CASH = "release_cash"          # 买单剩余冻结释放（撤单/拒单/失败）
    RELEASE_POSITION = "release_position"  # 卖单剩余冻结释放
    RECONCILE = "reconcile"                # 恢复时按订单快照修漂移


@dataclass
class FreezeEvent:
    """一条只追加的冻结流水。"""

    event_id: str
    timestamp: str
    order_id: str
    event_type: str
    cash_delta: Decimal = Decimal("0")      # 对可用现金的影响
    frozen_cash_delta: Decimal = Decimal("0")
    settled_cash_delta: Decimal = Decimal("0")
    quantity_delta: int = 0                 # 对可用持仓的影响
    frozen_quantity_delta: int = 0
    reason: str = ""
    client_order_id: Optional[str] = None
    balances_after: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "order_id": self.order_id,
            "client_order_id": self.client_order_id,
            "event_type": self.event_type,
            "cash_delta": float(self.cash_delta),
            "frozen_cash_delta": float(self.frozen_cash_delta),
            "settled_cash_delta": float(self.settled_cash_delta),
            "quantity_delta": self.quantity_delta,
            "frozen_quantity_delta": self.frozen_quantity_delta,
            "reason": self.reason,
            "balances_after": self.balances_after,
        }


class FreezeError(RuntimeError):
    """冻结/释放违反守恒或额度不足。整个事务应回滚，订单按拒单处理。"""


class FreezeLedger:
    """对账户与持仓做原子冻结操作并记录流水。

    本类不加自身锁：所有公共方法都要求在持有适配器交易锁的前提下调用，
    以保证撚账、订单状态、账户余额三者在同一临界区内一致提交。
    """

    def __init__(self) -> None:
        self._events: List[FreezeEvent] = []

    # ------------------------------------------------------------------ #
    # 流水
    # ------------------------------------------------------------------ #
    def _record(
        self,
        order: Order,
        event_type: FreezeEventType,
        account: Optional[Account],
        positions: Dict[str, Position],
        *,
        cash_delta: Decimal = Decimal("0"),
        frozen_cash_delta: Decimal = Decimal("0"),
        settled_cash_delta: Decimal = Decimal("0"),
        quantity_delta: int = 0,
        frozen_quantity_delta: int = 0,
        reason: str = "",
    ) -> FreezeEvent:
        event = FreezeEvent(
            event_id=f"FRZ_{uuid.uuid4().hex[:12]}",
            timestamp=datetime.now().isoformat(),
            order_id=order.order_id,
            client_order_id=order.client_order_id,
            event_type=event_type.value,
            cash_delta=_money(cash_delta),
            frozen_cash_delta=_money(frozen_cash_delta),
            settled_cash_delta=_money(settled_cash_delta),
            quantity_delta=quantity_delta,
            frozen_quantity_delta=frozen_quantity_delta,
            reason=reason,
            balances_after=(
                {
                    "available_cash": str(account.available_cash),
                    "frozen_cash": str(account.frozen_cash),
                    "settled_cash": str(account.settled_cash),
                    "capital_cash": str(account.capital_cash),
                }
                if account is not None
                else {}
            ),
        )
        self._events.append(event)
        return event

    def events(self, order_id: Optional[str] = None) -> List[FreezeEvent]:
        """返回冻结流水（可按订单过滤），供查询解释额度去向。"""
        if order_id is None:
            return list(self._events)
        return [e for e in self._events if e.order_id == order_id]

    # ------------------------------------------------------------------ #
    # 守恒校验
    # ------------------------------------------------------------------ #
    def _assert_invariants(
        self, account: Account, positions: Dict[str, Position]
    ) -> None:
        if account.available_cash < 0:
            raise FreezeError(f"可用现金为负: {account.available_cash}")
        if account.frozen_cash < 0:
            raise FreezeError(f"冻结现金为负: {account.frozen_cash}")

        cash_sum = _money(
            account.available_cash + account.frozen_cash + account.settled_cash
        )
        if cash_sum != account.capital_cash:
            raise FreezeError(
                "现金不守恒: "
                f"available={account.available_cash} + frozen={account.frozen_cash} "
                f"+ settled={account.settled_cash} = {cash_sum} "
                f"!= capital={account.capital_cash}"
            )

        for code, pos in positions.items():
            if pos.quantity < 0 or pos.available_quantity < 0 or pos.frozen_quantity < 0:
                raise FreezeError(f"持仓 {code} 出现负数: {pos}")
            if pos.available_quantity + pos.frozen_quantity != pos.quantity:
                raise FreezeError(
                    f"持仓 {code} 不守恒: available={pos.available_quantity} "
                    f"+ frozen={pos.frozen_quantity} != quantity={pos.quantity}"
                )

    # ------------------------------------------------------------------ #
    # 订单确认：冻结规则在此固定
    # ------------------------------------------------------------------ #
    def reserve_buy(
        self,
        order: Order,
        account: Account,
        freeze_price: Decimal,
        estimated_fee: Decimal,
    ) -> None:
        """买单确认时按固定单价预留现金（含预估费用缓冲）。"""
        if order.freeze_state != "none":
            raise FreezeError(f"订单 {order.order_id} 已冻结，禁止重复预留")

        reserve = _money(freeze_price * order.quantity) + _money(estimated_fee)
        if reserve > account.available_cash:
            raise FreezeError(
                f"可用资金不足，需要冻结 {reserve}，可用 {account.available_cash}"
            )

        # 冻结规则固定到订单快照，成交/撤单/恢复都以此为准
        order.frozen_price = Decimal(freeze_price)
        order.estimated_commission = _money(estimated_fee)
        order.frozen_cash = reserve
        order.freeze_state = "active"

        account.available_cash = _money(account.available_cash - reserve)
        account.frozen_cash = _money(account.frozen_cash + reserve)

        self._assert_invariants(account, {})
        self._record(
            order,
            FreezeEventType.RESERVE_CASH,
            account,
            {},
            cash_delta=-reserve,
            frozen_cash_delta=reserve,
            reason=f"买单确认，冻结价 {freeze_price} × {order.quantity} + 预估费用 {estimated_fee}",
        )

    def reserve_sell(
        self, order: Order, positions: Dict[str, Position]
    ) -> None:
        """卖单确认时预留持仓股数。"""
        if order.freeze_state != "none":
            raise FreezeError(f"订单 {order.order_id} 已冻结，禁止重复预留")

        pos = positions.get(order.stock_code)
        if pos is None or pos.available_quantity < order.quantity:
            available = pos.available_quantity if pos else 0
            raise FreezeError(
                f"可用持仓不足，需要冻结 {order.quantity}，可用 {available}"
            )

        order.frozen_quantity = order.quantity
        order.freeze_state = "active"

        pos.available_quantity -= order.quantity
        pos.frozen_quantity += order.quantity

        if pos.available_quantity < 0:
            raise FreezeError(f"持仓 {order.stock_code} 可用为负")
        self._record(
            order,
            FreezeEventType.RESERVE_POSITION,
            None,
            positions,
            quantity_delta=-order.quantity,
            frozen_quantity_delta=order.quantity,
            reason=f"卖单确认，冻结持仓 {order.quantity} 股",
        )

    # ------------------------------------------------------------------ #
    # 成交：冻结 → 已结算（支持多次部分成交）
    # ------------------------------------------------------------------ #
    def settle(
        self,
        order: Order,
        fill_quantity: int,
        fill_price: Decimal,
        fee: Decimal,
        account: Account,
        positions: Dict[str, Position],
    ) -> None:
        """把一笔成交对应的冻结额度结算为真实资产变动。

        可对同一订单多次调用（部分成交）；最后一笔必须吃完剩余冻结，
        实际成交价优于冻结价时，多出的预留当场找零回可用现金。
        """
        if fill_quantity <= 0:
            raise FreezeError("成交数量必须为正")
        if order.filled_quantity + fill_quantity > order.quantity:
            raise FreezeError(
                f"成交累计超过委托数量: {order.filled_quantity}+{fill_quantity}"
                f">{order.quantity}"
            )

        is_final = order.filled_quantity + fill_quantity == order.quantity
        fee = _money(fee)

        if order.side == OrderSide.BUY:
            self._settle_buy(
                order, fill_quantity, fill_price, fee, account, positions, is_final
            )
        else:
            self._settle_sell(
                order, fill_quantity, fill_price, fee, account, positions, is_final
            )

        order.settled_quantity += fill_quantity
        order.filled_quantity += fill_quantity
        order.freeze_state = "partial" if not is_final else "settled"
        self._assert_invariants(account, positions)

    def _settle_buy(
        self, order, fill_quantity, fill_price, fee, account, positions, is_final
    ) -> None:
        actual_cost = _money(fill_price * fill_quantity) + fee

        # 这笔成交对应的预留额度。费用按累计口径消耗：早期部分成交优先
        # 吃完整笔最低佣金缓冲（最低佣金按笔而非按股数收），避免中途预留
        # 不足；价格部分按冻结价 × 本笔数量拆分，尾差由最后一笔吸收。
        if is_final:
            reserved_consumed = order.frozen_cash
        else:
            price_part = _money(order.frozen_price * fill_quantity)
            cum_actual_fee = _money(
                getattr(order, "_cum_actual_fee", Decimal("0")) + fee
            )
            cum_fee_used = min(order.estimated_commission, cum_actual_fee)
            prev_fee_used = getattr(order, "_fee_reserve_used", Decimal("0"))
            fee_part = _money(cum_fee_used - prev_fee_used)
            order._cum_actual_fee = cum_actual_fee
            order._fee_reserve_used = cum_fee_used
            reserved_consumed = _money(price_part + fee_part)
            reserved_consumed = min(reserved_consumed, order.frozen_cash)

        if reserved_consumed < actual_cost:
            # 保守冻结下不应发生（市价单已按滑点上浮冻结），兜底防负
            raise FreezeError(
                f"买单 {order.order_id} 冻结不足以结算: "
                f"预留 {reserved_consumed} < 实际 {actual_cost}"
            )

        change_back = reserved_consumed - actual_cost  # 价格/费用优于预估的找零

        order.frozen_cash = _money(order.frozen_cash - reserved_consumed)
        account.frozen_cash = _money(account.frozen_cash - reserved_consumed)
        account.available_cash = _money(account.available_cash + change_back)
        account.settled_cash = _money(account.settled_cash + actual_cost)

        # 买入股份进入已结算持仓，立即可用
        pos = positions.get(order.stock_code)
        if pos is None:
            pos = Position(
                stock_code=order.stock_code,
                stock_name=order.stock_code,
                quantity=0,
                available_quantity=0,
                avg_cost=fill_price,
                current_price=fill_price,
                market_value=Decimal("0"),
                profit_loss=Decimal("0"),
                profit_loss_ratio=0.0,
            )
            positions[order.stock_code] = pos

        total_cost = pos.avg_cost * pos.quantity + fill_price * fill_quantity
        new_qty = pos.quantity + fill_quantity
        pos.quantity = new_qty
        pos.available_quantity += fill_quantity
        pos.avg_cost = total_cost / new_qty if new_qty else Decimal("0")

        self._record(
            order,
            FreezeEventType.SETTLE_BUY,
            account,
            positions,
            cash_delta=change_back,
            frozen_cash_delta=-reserved_consumed,
            settled_cash_delta=actual_cost,
            quantity_delta=fill_quantity,
            reason=(
                f"买入成交 {fill_quantity}@{fill_price}，费用 {fee}，"
                f"冻结找零 {change_back}"
            ),
        )

    def _settle_sell(
        self, order, fill_quantity, fill_price, fee, account, positions, is_final
    ) -> None:
        pos = positions.get(order.stock_code)
        if pos is None:
            raise FreezeError(f"卖出成交但无持仓: {order.stock_code}")

        # 最后一笔吃完剩余冻结股数，防止部分成交拆分出现股数尾差
        reserved_qty = order.frozen_quantity if is_final else fill_quantity
        reserved_qty = min(reserved_qty, pos.frozen_quantity)
        if reserved_qty < fill_quantity:
            raise FreezeError(
                f"卖单 {order.order_id} 冻结持仓不足以成交: "
                f"预留 {reserved_qty} < 成交 {fill_quantity}"
            )

        proceeds = _money(fill_price * fill_quantity - fee)

        order.frozen_quantity -= reserved_qty
        pos.frozen_quantity -= reserved_qty
        pos.quantity -= fill_quantity

        account.available_cash = _money(account.available_cash + proceeds)
        # 卖出回收现金，已结算净流出相应减少（可为负）
        account.settled_cash = _money(account.settled_cash - proceeds)

        if pos.quantity <= 0:
            # 清仓：台账键由适配器删除；先把字段归零维持删除前守恒
            pos.quantity = 0
            pos.available_quantity = 0
            pos.frozen_quantity = 0

        self._record(
            order,
            FreezeEventType.SETTLE_SELL,
            account,
            positions,
            cash_delta=proceeds,
            settled_cash_delta=-proceeds,
            frozen_quantity_delta=-reserved_qty,
            reason=f"卖出成交 {fill_quantity}@{fill_price}，费用 {fee}，回款 {proceeds}",
        )

    # ------------------------------------------------------------------ #
    # 释放：撤单 / 拒单 / 故障 / 重试，幂等
    # ------------------------------------------------------------------ #
    def release(
        self,
        order: Order,
        account: Account,
        positions: Dict[str, Position],
        reason: str,
    ) -> Dict[str, Decimal]:
        """释放订单上仍然占用的全部额度。返回实际释放量。

        幂等：若订单已无占用（全部成交、或已释放过），直接返回零，绝不二次
        退还，因此撤单重试 / 恢复重放不会产生重复释放。
        """
        released_cash = Decimal("0")
        released_qty = 0

        if order.freeze_state in ("none", "settled", "released"):
            logger.info(
                "订单 %s 状态 %s，无冻结可释放（幂等跳过）",
                order.order_id,
                order.freeze_state,
            )
            self._mark_released(order)
            return {"cash": released_cash, "quantity": released_qty}

        # 买单剩余现金
        if order.side == OrderSide.BUY and order.frozen_cash > 0:
            amount = order.frozen_cash
            account.available_cash = _money(account.available_cash + amount)
            account.frozen_cash = _money(account.frozen_cash - amount)
            order.released_cash = _money(order.released_cash + amount)
            order.frozen_cash = Decimal("0")
            released_cash = amount
            self._record(
                order,
                FreezeEventType.RELEASE_CASH,
                account,
                positions,
                cash_delta=amount,
                frozen_cash_delta=-amount,
                reason=reason,
            )

        # 卖单剩余持仓
        if order.side == OrderSide.SELL and order.frozen_quantity > 0:
            pos = positions.get(order.stock_code)
            qty = order.frozen_quantity
            if pos is not None:
                qty = min(qty, pos.frozen_quantity)
                pos.frozen_quantity -= qty
                pos.available_quantity += qty
            order.released_quantity += qty
            order.frozen_quantity = 0
            released_qty = qty
            self._record(
                order,
                FreezeEventType.RELEASE_POSITION,
                account,
                positions if pos is not None else {},
                quantity_delta=qty,
                frozen_quantity_delta=-qty,
                reason=reason,
            )

        self._mark_released(order)
        self._assert_invariants(account, positions)
        return {"cash": released_cash, "quantity": released_qty}

    @staticmethod
    def _mark_released(order: Order) -> None:
        if order.freeze_state != "settled":
            order.freeze_state = "released"

    # ------------------------------------------------------------------ #
    # 恢复：按订单确认时固定的快照重建台账并修正漂移
    # ------------------------------------------------------------------ #
    def reconcile(
        self,
        orders: List[Order],
        account: Account,
        positions: Dict[str, Position],
    ) -> Dict[str, object]:
        """重启 / 重连后，用活跃订单的冻结快照重建占用，修平任何漂移。

        活跃订单 = 已确认但未终结（PENDING/SUBMITTED/PARTIAL_FILLED）。
        已撤单 / 拒单 / 失败的订单若仍挂着冻结，一律释放；现金可用由
        恒等式 ``available = capital - settled - frozen`` 反推。
        """
        report: Dict[str, object] = {"repaired": [], "orphans": []}

        expected_frozen_cash = Decimal("0")
        expected_frozen_qty: Dict[str, int] = {}

        for order in orders:
            active = order.status in (
                OrderStatus.PENDING,
                OrderStatus.SUBMITTED,
                OrderStatus.PARTIAL_FILLED,
            )
            if not active:
                # 终结订单不应残留占用，残留即孤儿冻结
                if order.frozen_cash > 0 or order.frozen_quantity > 0:
                    released = self.release(
                        order, account, positions,
                        reason=f"恢复时发现终结订单 {order.status.value} 残留冻结，回收",
                    )
                    report["orphans"].append(
                        {"order_id": order.order_id, **{k: str(v) for k, v in released.items()}}
                    )
                continue

            # 依据确认时固定的快照重算剩余占用
            remaining = order.quantity - order.filled_quantity
            if order.side == OrderSide.BUY:
                if order.frozen_price is None:
                    # 无快照无法重建，保守起见不动现金但上报
                    report["repaired"].append(
                        {"order_id": order.order_id, "issue": "买单缺少冻结价快照"}
                    )
                    continue
                fee_left = (
                    order.estimated_commission * remaining / order.quantity
                    if order.quantity else Decimal("0")
                )
                should = _money(order.frozen_price * remaining) + _money(fee_left)
                drift = should - order.frozen_cash
                if drift != 0:
                    report["repaired"].append(
                        {"order_id": order.order_id, "cash_freeze_drift": str(drift)}
                    )
                order.frozen_cash = should
                expected_frozen_cash += should
            else:
                should = remaining
                if should != order.frozen_quantity:
                    report["repaired"].append(
                        {"order_id": order.order_id, "position_freeze_drift": should - order.frozen_quantity}
                    )
                order.frozen_quantity = should
                expected_frozen_qty[order.stock_code] = (
                    expected_frozen_qty.get(order.stock_code, 0) + should
                )
                order.freeze_state = "partial" if order.filled_quantity else "active"

        # 用聚合结果校正账户与持仓
        expected_frozen_cash = _money(expected_frozen_cash)
        cash_drift = expected_frozen_cash - account.frozen_cash
        if cash_drift != 0:
            report["repaired"].append(
                {
                    "scope": "account",
                    "frozen_cash_drift": str(cash_drift),
                    "detail": "按订单快照聚合的现金冻结与账户不一致，已修平",
                }
            )
        account.frozen_cash = expected_frozen_cash
        account.available_cash = _money(
            account.capital_cash - account.settled_cash - expected_frozen_cash
        )

        for code, pos in positions.items():
            expect_qty = expected_frozen_qty.get(code, 0)
            pos.frozen_quantity = expect_qty
            pos.available_quantity = pos.quantity - expect_qty

        self._assert_invariants(account, positions)

        snapshot = FreezeEvent(
            event_id=f"FRZ_{uuid.uuid4().hex[:12]}",
            timestamp=datetime.now().isoformat(),
            order_id="*",
            event_type=FreezeEventType.RECONCILE.value,
            reason="恢复对账",
            balances_after={
                "available_cash": str(account.available_cash),
                "frozen_cash": str(account.frozen_cash),
                "settled_cash": str(account.settled_cash),
                "cash_drift": str(cash_drift),
            },
        )
        self._events.append(snapshot)
        logger.warning("冻结台账恢复对账完成: %s", report)
        return report
