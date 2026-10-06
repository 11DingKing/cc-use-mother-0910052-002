"""订单冻结台账（cash / position freeze ledger）。

同一份可用资金或持仓可能被并发请求重复承诺，本模块用「不可变冻结记录 +
剩余额度」的方式跟踪每一笔下单占用的资源：

- 买入确认时冻结现金（限价单按限价预留，市价单按保护价预留）；
- 卖出确认时冻结持仓（T+1 下仅可用数量可被冻结）；
- 成交时把冻结额转为已结算（现金扣款 / 持仓扣减），部分成交按比例推进；
- 撤单 / 拒单 / 失败时把剩余冻结原路释放；
- 所有释放都以订单上的剩余冻结为上限，重复撤单、重复成交回报、重试
  都不会产生负余额或重复释放。

``FreezeLedger`` 自带锁，``apply()`` 以原子事务方式修改账户与持仓；
``conservation_report`` 给出可用 / 冻结 / 已结算的差异解释与守恒校验。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from app.trading.base import (
    Account,
    Order,
    OrderSide,
    OrderStatus,
    Position,
)

# 资金台账中现金对应的「标的代码」
CASH = ""

# 冻结来源，便于审计时区分冻结 / 释放是哪个环节触发的
REASON_FREEZE = "freeze"
REASON_FILL = "fill"
REASON_CANCEL = "cancel"
REASON_REJECT = "reject"
REASON_RETRY = "retry"
REASON_RECOVER = "recover"
REASON_ADJUST = "adjust"


@dataclass
class FreezeEntry:
    """一笔订单对应的不可变冻结记录。

    ``frozen_*`` 为确认时固定的总额度，``remaining_*`` 为仍处于冻结状态、
    尚未结算或释放的额度，二者之差即已结算（成交）部分。
    """

    order_id: str
    stock_code: str
    side: OrderSide
    # 冻结规则在订单确认时固定，之后不再改变
    rule: str                         # limit / market_protection
    limit_price: Optional[Decimal]   # 限价（冻结基准价）
    protect_ratio: Decimal           # 市价单保护价比例
    quantity: int                     # 委托数量
    frozen_cash: Decimal = Decimal("0")
    remaining_cash: Decimal = Decimal("0")
    frozen_qty: int = 0
    remaining_qty: int = 0
    filled_qty: int = 0               # 累计成交（买/卖均追踪）
    archived: bool = False            # 重试后被新规则取代，仅留审计
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    @property
    def settled_cash(self) -> Decimal:
        """已结算（成交）的现金额度。"""
        return self.frozen_cash - self.remaining_cash

    @property
    def settled_qty(self) -> int:
        """已结算（成交）的持仓数量。"""
        return self.filled_qty

    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "stock_code": self.stock_code,
            "side": self.side.value,
            "rule": self.rule,
            "limit_price": float(self.limit_price) if self.limit_price else None,
            "protect_ratio": float(self.protect_ratio),
            "quantity": self.quantity,
            "frozen_cash": float(self.frozen_cash),
            "remaining_cash": float(self.remaining_cash),
            "settled_cash": float(self.settled_cash),
            "frozen_quantity": self.frozen_qty,
            "remaining_quantity": self.remaining_qty,
            "settled_quantity": self.settled_qty,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class LedgerMove:
    """一次台账变动（冻结 / 结算 / 释放）的审计记录。"""

    seq: int
    timestamp: datetime
    order_id: str
    stock_code: str
    reason: str
    cash_delta: Decimal          # 对冻结现金的影响（正=增加冻结，负=释放/结算）
    qty_delta: int               # 对冻结持仓的影响
    cash_settled: Decimal        # 本次转结算的现金（成交扣款）
    qty_settled: int             # 本次转结算的数量
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "seq": self.seq,
            "timestamp": self.timestamp.isoformat(),
            "order_id": self.order_id,
            "stock_code": self.stock_code,
            "reason": self.reason,
            "cash_delta": float(self.cash_delta),
            "qty_delta": self.qty_delta,
            "cash_settled": float(self.cash_settled),
            "qty_settled": self.qty_settled,
            "note": self.note,
        }


class LedgerError(Exception):
    """台账操作违反守恒或订单状态约束。"""


class FreezeLedger:
    """线程安全的现金 / 持仓冻结台账。

    台账直接在锁内修改 ``Account`` / ``Position``，并始终维护：

    - 现金：``settled_cash + available_cash + frozen_cash = initial_cash``
    - 持仓：对任一标的 ``quantity = available + frozen_qty``（T+1 在途买入
      不计入任何一侧，故数量恒等式按可用口径单独追踪）。
    """

    def __init__(
        self,
        account: Account,
        positions: Dict[str, Position],
        market_protect_ratio: Decimal = Decimal("0.03"),
        t_plus_1: bool = False,
    ):
        self._account = account
        self._positions = positions
        self.market_protect_ratio = Decimal(str(market_protect_ratio))
        self.t_plus_1 = t_plus_1

        # 现金口径：初始可支配现金（available + frozen + 已结算支出恒定）
        self._initial_cash = account.available_cash + account.frozen_cash
        self._settled_cash = Decimal("0")       # 累计净结算现金支出（费用净额）
        self._settled_sales = Decimal("0")      # 累计卖出到账（含费用前口径见审计）

        self._entries: Dict[str, FreezeEntry] = {}
        # 重试后被取代的历史冻结记录（仍可审计，不再占额度）
        self._history: Dict[str, List[FreezeEntry]] = {}
        self._moves: List[LedgerMove] = []
        self._seq = 0
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # 只读视图
    # ------------------------------------------------------------------

    @property
    def lock(self) -> threading.RLock:
        """供服务层在「校验+冻结」复合操作中持有的锁。"""
        return self._lock

    def get_entry(self, order_id: str) -> Optional[FreezeEntry]:
        with self._lock:
            return self._entries.get(order_id)

    def list_entries(self, active_only: bool = False) -> List[FreezeEntry]:
        with self._lock:
            entries = list(self._entries.values())
            if not active_only:
                for archived in self._history.values():
                    entries.extend(archived)
        if active_only:
            entries = [
                e for e in entries
                if e.remaining_cash > 0 or e.remaining_qty > 0
            ]
        return sorted(entries, key=lambda e: e.created_at)

    def moves(self, order_id: Optional[str] = None) -> List[LedgerMove]:
        with self._lock:
            moves = list(self._moves)
        if order_id:
            moves = [m for m in moves if m.order_id == order_id]
        return moves

    # ------------------------------------------------------------------
    # 冻结：订单确认时固定规则与额度
    # ------------------------------------------------------------------

    def freeze_plan(
        self,
        order: Order,
        reference_price: Decimal,
        commission_rate: Decimal = Decimal("0"),
        min_commission: Decimal = Decimal("0"),
    ) -> Tuple[str, Decimal, Decimal]:
        """计算冻结方案，不修改任何状态。

        返回 ``(rule, frozen_cash, frozen_price)``。卖出冻结现金为 0。
        买入在委托额基础上预留预估费用，保证成交扣费不会出现负现金。
        """
        if order.side == OrderSide.SELL:
            return "position", Decimal("0"), Decimal("0")

        if order.price is not None:
            rule = "limit"
            frozen_price = order.price
        else:
            rule = "market_protection"
            frozen_price = (reference_price * (Decimal("1") + self.market_protect_ratio))

        gross = frozen_price * order.quantity
        est_fee = max(gross * commission_rate, min_commission)
        return rule, gross + est_fee, frozen_price

    def freeze(
        self,
        order: Order,
        reference_price: Decimal,
        commission_rate: Decimal = Decimal("0"),
        min_commission: Decimal = Decimal("0"),
        reason: str = REASON_FREEZE,
    ) -> FreezeEntry:
        """订单确认：原子地固定冻结规则并占用现金 / 持仓。

        必须在确认订单可提交后调用。余额不足抛 ``LedgerError``，此时台账
        与账户 / 持仓不发生任何变化（原子性）。
        """
        with self._lock:
            if order.order_id in self._entries:
                raise LedgerError(f"订单 {order.order_id} 已存在冻结记录，禁止重复冻结")

            rule, frozen_cash, frozen_price = self.freeze_plan(
                order, reference_price, commission_rate, min_commission
            )

            # 买入：检查并冻结现金
            if order.side == OrderSide.BUY:
                if frozen_cash > self._account.available_cash:
                    raise LedgerError(
                        f"可用资金不足，需要冻结 {frozen_cash:.2f}，"
                        f"可用 {self._account.available_cash:.2f}"
                    )
                self._account.available_cash -= frozen_cash
                self._account.frozen_cash += frozen_cash
                entry_cash, entry_qty = frozen_cash, 0
            else:
                # 卖出：检查并冻结持仓（仅可用数量）
                pos = self._positions.get(order.stock_code)
                available = pos.available_quantity if pos else 0
                if order.quantity > available:
                    raise LedgerError(
                        f"可用持仓不足，需要冻结 {order.quantity}，可用 {available}"
                    )
                pos.available_quantity -= order.quantity
                entry_cash, entry_qty = Decimal("0"), order.quantity

            entry = FreezeEntry(
                order_id=order.order_id,
                stock_code=order.stock_code,
                side=order.side,
                rule=rule,
                limit_price=order.price,
                protect_ratio=self.market_protect_ratio,
                quantity=order.quantity,
                frozen_cash=entry_cash,
                remaining_cash=entry_cash,
                frozen_qty=entry_qty,
                remaining_qty=entry_qty,
            )
            self._entries[order.order_id] = entry
            self._record_move(
                order, reason,
                cash_delta=entry_cash, qty_delta=entry_qty,
                cash_settled=Decimal("0"), qty_settled=0,
                note=f"rule={rule}, price={frozen_price}",
            )
            self._touch_account()
            return entry

    # ------------------------------------------------------------------
    # 结算：成交（支持部分成交、多次回报）
    # ------------------------------------------------------------------

    def settle_fill(
        self,
        order: Order,
        fill_quantity: int,
        fill_price: Decimal,
        commission: Decimal = Decimal("0"),
        reason: str = REASON_FILL,
    ) -> Dict[str, Any]:
        """把一笔成交对应数量的冻结转为已结算。

        - 买入：按成交价从冻结现金中转出（货款 + 费用），多余冻结留待
          后续成交或释放；持仓增加。
        - 卖出：对应数量的冻结持仓转为已交割（直接扣减总持仓），卖出
          净收入（货款 - 费用）回到可用现金。

        ``fill_quantity`` 不能超过订单剩余冻结数量；超出部分抛错，
        因此重复或乱序的成交回报不会重复结算。
        """
        with self._lock:
            entry = self._entries.get(order.order_id)
            if entry is None:
                raise LedgerError(f"订单 {order.order_id} 无冻结记录，无法结算")
            if fill_quantity <= 0:
                raise LedgerError("成交数量必须为正数")

            remaining = entry.quantity - entry.filled_qty
            if fill_quantity > remaining:
                raise LedgerError(
                    f"成交数量 {fill_quantity} 超过订单剩余未成交数量 {remaining}"
                )

            gross = fill_price * fill_quantity

            if entry.side == OrderSide.BUY:
                cost = gross + commission
                if cost > entry.remaining_cash:
                    # 保护价不足（极端行情穿透）：不允许透支，拒绝该笔结算
                    raise LedgerError(
                        f"买入结算金额 {cost:.2f} 超过剩余冻结 "
                        f"{entry.remaining_cash:.2f}，冻结额度不足"
                    )
                # 冻结 -> 已结算
                self._account.frozen_cash -= cost
                self._settled_cash += cost
                entry.remaining_cash -= cost
                self._add_position(order.stock_code, fill_quantity, fill_price)
                entry.filled_qty += fill_quantity
                cash_settled = cost
                qty_settled = 0
                cash_delta = -cost
                qty_delta = 0
            else:
                # 卖出：冻结持仓交割扣减，净收入回可用
                entry.remaining_qty -= fill_quantity
                entry.filled_qty += fill_quantity
                pos = self._positions.get(order.stock_code)
                if pos is not None:
                    pos.quantity -= fill_quantity
                    if pos.quantity <= 0:
                        pos.quantity = 0
                        pos.available_quantity = 0
                net = gross - commission
                self._account.available_cash += net
                self._settled_sales += gross
                self._settled_cash -= net
                cash_settled = Decimal("0")
                qty_settled = fill_quantity
                cash_delta = Decimal("0")
                qty_delta = -fill_quantity

            entry.updated_at = datetime.now()
            self._record_move(
                order, reason,
                cash_delta=cash_delta, qty_delta=qty_delta,
                cash_settled=cash_settled, qty_settled=qty_settled,
                note=f"fill {fill_quantity}@{fill_price}, fee={commission}",
            )
            self._touch_account()
            return {
                "fill_quantity": fill_quantity,
                "fill_price": fill_price,
                "commission": commission,
                "gross": gross,
            }

    # ------------------------------------------------------------------
    # 释放：撤单 / 拒单 / 失败，以及重试
    # ------------------------------------------------------------------

    def release(
        self,
        order: Order,
        reason: str = REASON_CANCEL,
        note: str = "",
    ) -> Dict[str, Decimal]:
        """释放订单全部剩余冻结（部分成交后撤单只释放未成交部分）。

        幂等：若订单已无剩余冻结（重复撤单、先拒单后撤单等），返回零
        变动而不会重复释放。
        """
        with self._lock:
            return self._release_locked(order, reason, note)

    def _release_locked(
        self,
        order: Order,
        reason: str,
        note: str = "",
    ) -> Dict[str, Decimal]:
        entry = self._entries.get(order.order_id)
        if entry is None:
            return {"cash": Decimal("0"), "quantity": 0}

        cash_back = entry.remaining_cash
        qty_back = entry.remaining_qty

        if cash_back > 0:
            self._account.frozen_cash -= cash_back
            self._account.available_cash += cash_back
            entry.remaining_cash = Decimal("0")

        if qty_back > 0:
            pos = self._positions.get(order.stock_code)
            if pos is not None:
                # 部分成交已减少总持仓，可释放的只有剩余冻结对应的数量
                pos.available_quantity += qty_back
                if pos.available_quantity > pos.quantity:
                    pos.available_quantity = pos.quantity
            entry.remaining_qty = 0

        entry.updated_at = datetime.now()
        self._record_move(
            order, reason,
            cash_delta=-cash_back, qty_delta=-qty_back,
            cash_settled=Decimal("0"), qty_settled=0,
            note=note or "release remaining freeze",
        )
        self._touch_account()
        return {"cash": cash_back, "quantity": qty_back}

    def retry(
        self,
        order: Order,
        reference_price: Decimal,
        commission_rate: Decimal = Decimal("0"),
        min_commission: Decimal = Decimal("0"),
    ) -> FreezeEntry:
        """重试：先幂等释放旧冻结，再按当前订单重新固定冻结规则。

        用于委托被网关临时拒单后以新价格重提。返回新的冻结记录。
        """
        with self._lock:
            if order.order_id in self._entries:
                self._release_locked(order, REASON_RETRY, "release before retry")
                # 旧记录归档留痕，不再占额度
                old = self._entries.pop(order.order_id)
                old.archived = True
                old.updated_at = datetime.now()
                self._history.setdefault(order.order_id, []).append(old)
            return self.freeze(
                order,
                reference_price,
                commission_rate,
                min_commission,
                reason=REASON_RETRY,
            )

    # ------------------------------------------------------------------
    # 恢复：重放订单状态，校正台账
    # ------------------------------------------------------------------

    def recover(
        self,
        orders: List[Order],
        reference_prices: Dict[str, Decimal],
        commission_rate: Decimal = Decimal("0"),
        min_commission: Decimal = Decimal("0"),
    ) -> Dict[str, Any]:
        """启动 / 重连后根据持久化订单重建冻结状态。

        - SUBMITTED / PARTIAL_FILLED：按订单剩余未成交数量重新冻结
          （现金按固定规则重算）；
        - FILLED / CANCELLED / REJECTED / FAILED：不占冻结；
        - 已有冻结记录的订单跳过，避免重复恢复。
        """
        with self._lock:
            recovered, skipped = [], []
            active = {
                OrderStatus.SUBMITTED,
                OrderStatus.PARTIAL_FILLED,
                OrderStatus.PENDING,
            }
            for order in orders:
                if order.order_id in self._entries:
                    skipped.append(order.order_id)
                    continue
                if order.status not in active:
                    continue

                remaining_qty = order.quantity - order.filled_quantity
                if remaining_qty <= 0:
                    continue

                recovery_order = Order(
                    order_id=order.order_id,
                    stock_code=order.stock_code,
                    side=order.side,
                    order_type=order.order_type,
                    quantity=remaining_qty,
                    price=order.price,
                )
                ref = reference_prices.get(
                    order.stock_code, order.price or Decimal("0")
                )
                try:
                    entry = self.freeze(
                        recovery_order,
                        ref,
                        commission_rate,
                        min_commission,
                        reason=REASON_RECOVER,
                    )
                    recovered.append(entry.to_dict())
                except LedgerError as e:
                    skipped.append(f"{order.order_id}: {e}")

            return {"recovered": recovered, "skipped": skipped}

    # ------------------------------------------------------------------
    # 查询解释：可用 / 占用 / 已结算
    # ------------------------------------------------------------------

    def account_breakdown(self) -> Dict[str, Any]:
        """解释现金的可用 / 冻结 / 已结算差异。"""
        with self._lock:
            active_cash = sum(
                e.remaining_cash for e in self._entries.values()
            )
            orders_holding_cash = [
                {
                    "order_id": e.order_id,
                    "stock_code": e.stock_code,
                    "remaining_cash": float(e.remaining_cash),
                    "rule": e.rule,
                }
                for e in self._entries.values()
                if e.remaining_cash > 0
            ]
            return {
                "initial_cash": float(self._initial_cash),
                "available_cash": float(self._account.available_cash),
                "frozen_cash": float(self._account.frozen_cash),
                "frozen_cash_explained_by_orders": float(active_cash),
                "settled_cash_net": float(self._settled_cash),
                "cash_holding_orders": orders_holding_cash,
                "cash_conservation": float(
                    self._account.available_cash
                    + self._account.frozen_cash
                    + self._settled_cash
                ),
            }

    def position_breakdown(self, stock_code: Optional[str] = None) -> List[Dict[str, Any]]:
        """解释每个标的的持仓可用 / 冻结 / 已结算差异。"""
        with self._lock:
            frozen_by_stock: Dict[str, int] = {}
            detail_by_stock: Dict[str, List[Dict[str, Any]]] = {}
            for e in self._entries.values():
                if e.remaining_qty <= 0:
                    continue
                frozen_by_stock[e.stock_code] = (
                    frozen_by_stock.get(e.stock_code, 0) + e.remaining_qty
                )
                detail_by_stock.setdefault(e.stock_code, []).append({
                    "order_id": e.order_id,
                    "remaining_quantity": e.remaining_qty,
                })

            codes = {stock_code} if stock_code else set(self._positions) | set(frozen_by_stock)
            result = []
            for code in sorted(codes):
                pos = self._positions.get(code)
                total = pos.quantity if pos else 0
                available = pos.available_quantity if pos else 0
                frozen = frozen_by_stock.get(code, 0)
                result.append({
                    "stock_code": code,
                    "quantity": total,
                    "available_quantity": available,
                    "frozen_quantity": frozen,
                    "settled_or_in_transit": total - available - frozen,
                    "conservation_ok": available + frozen <= total,
                    "freeze_orders": detail_by_stock.get(code, []),
                })
            return result

    def conservation_report(self) -> Dict[str, Any]:
        """守恒校验报告：现金恒等式、持仓恒等式、台账与账户一致性。"""
        with self._lock:
            cash_ok = (
                self._account.available_cash
                + self._account.frozen_cash
                + self._settled_cash
                == self._initial_cash
            )
            frozen_cash_ok = (
                self._account.frozen_cash
                == sum(e.remaining_cash for e in self._entries.values())
            )

            positions_ok = True
            position_checks = []
            frozen_by_stock: Dict[str, int] = {}
            for e in self._entries.values():
                frozen_by_stock[e.stock_code] = (
                    frozen_by_stock.get(e.stock_code, 0) + e.remaining_qty
                )
            for code, pos in self._positions.items():
                frozen_qty = frozen_by_stock.get(code, 0)
                ok = (
                    pos.available_quantity + frozen_qty <= pos.quantity
                    and pos.available_quantity >= 0
                )
                positions_ok = positions_ok and ok
                position_checks.append({
                    "stock_code": code,
                    "quantity": pos.quantity,
                    "available_quantity": pos.available_quantity,
                    "frozen_quantity": frozen_qty,
                    "ok": ok,
                })

            no_negative = (
                self._account.available_cash >= 0
                and self._account.frozen_cash >= 0
                and all(
                    p.available_quantity >= 0 and p.quantity >= 0
                    for p in self._positions.values()
                )
            )

            return {
                "cash_conservation_ok": cash_ok,
                "cash_identity": (
                    f"{self._account.available_cash} + {self._account.frozen_cash} "
                    f"+ {self._settled_cash} = {self._initial_cash}"
                ),
                "frozen_cash_matches_ledger": frozen_cash_ok,
                "positions_conservation_ok": positions_ok,
                "no_negative_balance": no_negative,
                "positions": position_checks,
                "active_freeze_count": sum(
                    1 for e in self._entries.values()
                    if e.remaining_cash > 0 or e.remaining_qty > 0
                ),
                "move_count": len(self._moves),
            }

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _add_position(self, code: str, qty: int, price: Decimal) -> None:
        pos = self._positions.get(code)
        if pos is None:
            pos = Position(
                stock_code=code,
                stock_name=code,
                quantity=0,
                available_quantity=0,  # A股 T+1，买入当日不可卖
                avg_cost=price,
                current_price=price,
                market_value=Decimal("0"),
                profit_loss=Decimal("0"),
                profit_loss_ratio=0.0,
            )
            self._positions[code] = pos

        if pos.quantity > 0:
            total_cost = pos.avg_cost * pos.quantity + price * qty
            pos.quantity += qty
            pos.avg_cost = total_cost / pos.quantity
        else:
            pos.quantity = qty
            pos.avg_cost = price
        pos.current_price = price
        if not self.t_plus_1:
            # 模拟盘默认买入当日可卖；实盘 T+1 下买入数量留在在途口径
            pos.available_quantity += qty

    def _record_move(
        self,
        order: Order,
        reason: str,
        cash_delta: Decimal,
        qty_delta: int,
        cash_settled: Decimal,
        qty_settled: int,
        note: str,
    ) -> None:
        self._seq += 1
        self._moves.append(LedgerMove(
            seq=self._seq,
            timestamp=datetime.now(),
            order_id=order.order_id,
            stock_code=order.stock_code,
            reason=reason,
            cash_delta=cash_delta,
            qty_delta=qty_delta,
            cash_settled=cash_settled,
            qty_settled=qty_settled,
            note=note,
        ))

    def _touch_account(self) -> None:
        self._account.updated_at = datetime.now()
        frozen_by_stock: Dict[str, int] = {}
        for e in self._entries.values():
            if e.remaining_qty > 0:
                frozen_by_stock[e.stock_code] = (
                    frozen_by_stock.get(e.stock_code, 0) + e.remaining_qty
                )
        for code, pos in self._positions.items():
            pos.frozen_quantity = frozen_by_stock.get(code, 0)
            pos.updated_at = datetime.now()
