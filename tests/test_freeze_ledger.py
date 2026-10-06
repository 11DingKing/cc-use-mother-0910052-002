"""冻结 / 释放机制测试：守恒、幂等、并发承诺、部分成交、撤单、拒单、重试、恢复。"""

import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest

from app.trading.base import Order, OrderSide, OrderStatus, OrderType
from app.trading.simulation_adapter import SimulationAdapter
from app.trading.ledger import LedgerError


@pytest.fixture
def adapter():
    adapter = SimulationAdapter({
        "initial_cash": 100000,
        "commission_rate": 0.0003,
        "min_commission": 5,
        "stamp_tax_rate": 0.001,
    })
    adapter.connect()
    adapter.set_quote("000001", 10.0)
    return adapter


def _buy_order(adapter, code="000001", qty=100, price=9.0, otype=OrderType.LIMIT,
               client_order_id=None):
    order = Order(
        order_id=adapter._generate_order_id(),
        stock_code=code,
        side=OrderSide.BUY,
        order_type=otype,
        quantity=qty,
        price=price,
        client_order_id=client_order_id,
    )
    return adapter.place_order(order)


def _sell_order(adapter, code="000001", qty=100, price=11.0):
    order = Order(
        order_id=adapter._generate_order_id(),
        stock_code=code,
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        quantity=qty,
        price=price,
    )
    return adapter.place_order(order)


def _buy_in(adapter, code="000001", qty=1000, price=10.0):
    """先建仓（市价立即成交）。"""
    order = Order(
        order_id=adapter._generate_order_id(),
        stock_code=code,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=qty,
        price=Decimal(str(price)),
    )
    return adapter.place_order(order)


class TestFreezeOnSubmit:
    """订单确认时固定冻结规则。"""

    def test_buy_freezes_cash_while_resting(self, adapter):
        order = _buy_order(adapter, qty=1000, price=9.0)  # 现价10，买9不成交

        assert order.status == OrderStatus.SUBMITTED
        assert order.freeze_rule == "limit"
        assert order.frozen_amount == Decimal("9000") + Decimal("5")  # 含预估费用

        account = adapter.get_account()
        assert account.frozen_cash >= Decimal("9005")
        assert account.available_cash <= Decimal("100000") - Decimal("9005")
        # 可用 + 冻结 = 初始（尚未结算）
        assert account.available_cash + account.frozen_cash == Decimal("100000")

    def test_market_buy_freezes_with_protection_ratio(self, adapter):
        order = Order(
            order_id=adapter._generate_order_id(),
            stock_code="000001",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1000,
        )
        # 直接看冻结方案：保护价 = 10 * 1.03
        rule, cash, plan_price = adapter.ledger.freeze_plan(
            order, Decimal("10"), Decimal("0.0003"), Decimal("5")
        )
        assert rule == "market_protection"
        assert plan_price == Decimal("10.30")
        assert cash == Decimal("10300") + Decimal("5")

    def test_sell_freezes_position_while_resting(self, adapter):
        _buy_in(adapter, qty=1000)

        order = _sell_order(adapter, qty=400, price=11.0)  # 现价10，卖11不成交

        assert order.status == OrderStatus.SUBMITTED
        pos = adapter.get_position("000001")
        assert pos.quantity == 1000
        assert pos.available_quantity == 600
        assert pos.frozen_quantity == 400
        assert order.frozen_quantity == 400

    def test_insufficient_cash_rejected_without_any_freeze(self, adapter):
        order = _buy_order(adapter, qty=20000, price=9.0)  # 需18万+
        assert order.status == OrderStatus.REJECTED
        assert "资金不足" in order.error_message

        account = adapter.get_account()
        assert account.available_cash == Decimal("100000")
        assert account.frozen_cash == 0
        assert adapter.freeze_entries(active_only=True) == []

    def test_insufficient_position_rejected_without_freeze(self, adapter):
        _buy_in(adapter, qty=100)
        order = _sell_order(adapter, qty=200, price=11.0)
        assert order.status == OrderStatus.REJECTED
        assert "持仓不足" in order.error_message

        pos = adapter.get_position("000001")
        assert pos.available_quantity == 100
        assert pos.frozen_quantity == 0


class TestSettlement:
    """成交（全部 / 部分）把冻结转结算。"""

    def test_full_fill_buy_conserves_cash(self, adapter):
        # 限价 10，现价 10，立即成交
        result = _buy_order(adapter, qty=1000, price=10.0)
        assert result.status == OrderStatus.FILLED

        account = adapter.get_account()
        gross = Decimal("10000")
        commission = max(gross * Decimal("0.0003"), Decimal("5"))
        # 冻结时按 5 预留费用，实际佣金 5，无多余；可用恰好扣减货款+费用
        assert account.available_cash == Decimal("100000") - gross - commission
        assert account.frozen_cash == 0

        report = adapter.freeze_report()["conservation"]
        assert report["cash_conservation_ok"] is True
        assert report["frozen_cash_matches_ledger"] is True

    def test_partial_fill_then_cancel_releases_remainder(self, adapter):
        order = _buy_order(adapter, qty=1000, price=9.0)  # 挂单
        account = adapter.get_account()
        frozen_before = account.frozen_cash

        # 部分成交 400 股
        adapter.simulate_fill(order.order_id, quantity=400, price=9.0)
        order = adapter.get_order(order.order_id)
        assert order.status == OrderStatus.PARTIAL_FILLED
        assert order.filled_quantity == 400

        entry = adapter.ledger.get_entry(order.order_id)
        assert entry.filled_qty == 400
        assert entry.remaining_cash < frozen_before

        # 撤掉剩余 600
        assert adapter.cancel_order(order.order_id) is True
        order = adapter.get_order(order.order_id)
        assert order.status == OrderStatus.CANCELLED

        account = adapter.get_account()
        assert account.frozen_cash == 0
        # 只结算了 400 股的货款 + 费用
        settled_cost = Decimal("9.0") * 400 + Decimal("5")
        assert account.available_cash == Decimal("100000") - settled_cost

        report = adapter.freeze_report()["conservation"]
        assert report["cash_conservation_ok"] is True

    def test_partial_sell_then_cancel_restores_remaining_position(self, adapter):
        _buy_in(adapter, qty=1000)
        order = _sell_order(adapter, qty=1000, price=11.0)

        adapter.simulate_fill(order.order_id, quantity=400, price=11.0)
        pos = adapter.get_position("000001")
        assert pos.quantity == 600
        assert pos.available_quantity == 0
        assert pos.frozen_quantity == 600

        assert adapter.cancel_order(order.order_id) is True
        pos = adapter.get_position("000001")
        assert pos.quantity == 600
        assert pos.available_quantity == 600
        assert pos.frozen_quantity == 0

    def test_overfill_quantity_rejected(self, adapter):
        order = _buy_order(adapter, qty=1000, price=9.0)
        adapter.simulate_fill(order.order_id, quantity=600, price=9.0)
        # 再来 600 股，超过剩余 400，必须报错而不是重复/超额结算
        with pytest.raises(LedgerError):
            adapter.ledger.settle_fill(
                adapter.get_order(order.order_id),
                fill_quantity=600,
                fill_price=Decimal("9.0"),
                commission=Decimal("5"),
            )

    def test_sell_proceeds_return_to_available(self, adapter):
        _buy_in(adapter, qty=1000, price=10.0)
        cash_before = adapter.get_account().available_cash

        result = _sell_order(adapter, qty=1000, price=10.0)  # 立即成交
        assert result.status == OrderStatus.FILLED

        account = adapter.get_account()
        gross = Decimal("10000")
        fee = Decimal("5") + gross * Decimal("0.001")
        assert account.available_cash == cash_before + gross - fee
        assert adapter.get_position("000001") is None


class TestCancelIdempotency:
    """重复撤单不会重复释放。"""

    def test_double_cancel_no_double_release(self, adapter):
        order = _buy_order(adapter, qty=1000, price=9.0)
        account = adapter.get_account()
        available_after_freeze = account.available_cash

        assert adapter.cancel_order(order.order_id) is True
        assert adapter.cancel_order(order.order_id) is False  # 已撤销

        account = adapter.get_account()
        # 只释放一次
        assert account.available_cash == Decimal("100000")
        assert account.frozen_cash == 0
        assert available_after_freeze < Decimal("100000")

    def test_cancel_filled_order_fails_and_keeps_state(self, adapter):
        order = _buy_order(adapter, qty=100, price=10.0)
        assert order.status == OrderStatus.FILLED
        assert adapter.cancel_order(order.order_id) is False
        account = adapter.get_account()
        assert account.frozen_cash == 0
        assert account.available_cash < Decimal("100000")


class TestRetry:
    """重试先释放旧冻结，再按新规则冻结。"""

    def test_retry_resting_order_with_new_price(self, adapter):
        order = _buy_order(adapter, qty=1000, price=9.0)
        assert adapter.get_account().frozen_cash >= Decimal("9005")

        # 以 8 元重提
        retried = adapter.retry_order(order.order_id, price=8.0)
        assert retried.status == OrderStatus.SUBMITTED
        assert retried.freeze_rule == "limit"
        assert retried.frozen_amount == Decimal("8000") + Decimal("5")

        account = adapter.get_account()
        assert account.frozen_cash == Decimal("8005")
        # 旧冻结记录仍可审计，活动冻结只有新规则一笔
        active = adapter.freeze_entries(active_only=True)
        assert len(active) == 1
        assert active[0]["limit_price"] == 8.0

        moves = [(m.reason, float(m.cash_delta)) for m in adapter.ledger.moves(order.order_id)]
        reasons = [m[0] for m in moves]
        assert "retry" in reasons


class TestRecovery:
    """重连后按未终结订单重建冻结。"""

    def test_recover_resting_orders(self, adapter):
        # 新建一个干净的适配器，模拟从外部恢复两笔挂单
        resting_buy = Order(
            order_id="EXT_BUY_1",
            stock_code="000001",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1000,
            price=Decimal("9.0"),
            status=OrderStatus.SUBMITTED,
        )
        _buy_in(adapter, code="000002", qty=1000, price=10.0)
        adapter.set_quote("000002", 10.0)
        resting_sell = Order(
            order_id="EXT_SELL_1",
            stock_code="000002",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=1000,
            price=Decimal("11.0"),
            status=OrderStatus.PARTIAL_FILLED,
            filled_quantity=100,
        )

        result = adapter.recover_orders([resting_buy, resting_sell])
        assert len(result["recovered"]) == 2

        account = adapter.get_account()
        assert account.frozen_cash == Decimal("9005")

        pos = adapter.get_position("000002")
        assert pos.frozen_quantity == 900   # 剩余未成交 900 股
        assert pos.available_quantity == 100

        # 再次恢复是幂等的
        result2 = adapter.recover_orders([resting_buy, resting_sell])
        assert set(result2["skipped"]) >= {"EXT_BUY_1", "EXT_SELL_1"}
        assert adapter.get_account().frozen_cash == Decimal("9005")


class TestConcurrency:
    """并发请求不得重复承诺同一笔资金 / 持仓。"""

    def test_concurrent_buys_never_overcommit_cash(self, adapter):
        # 20 个线程各买 1000 股 @9（挂单冻结 9005），10 万现金最多容纳 11 笔
        results = []
        lock = threading.Lock()

        def place():
            order = _buy_order(adapter, qty=1000, price=9.0)
            with lock:
                results.append(order.status)

        with ThreadPoolExecutor(max_workers=20) as pool:
            list(pool.map(lambda _: place(), range(20)))

        submitted = results.count(OrderStatus.SUBMITTED)
        rejected = results.count(OrderStatus.REJECTED)
        assert submitted + rejected == 20
        assert submitted == 11  # floor(100000 / 9005)

        account = adapter.get_account()
        assert account.available_cash >= 0
        assert account.available_cash + account.frozen_cash == Decimal("100000")

        report = adapter.freeze_report()["conservation"]
        assert report["cash_conservation_ok"] is True
        assert report["frozen_cash_matches_ledger"] is True
        assert report["no_negative_balance"] is True

    def test_concurrent_sells_never_overcommit_position(self, adapter):
        _buy_in(adapter, qty=1000)

        results = []
        lock = threading.Lock()

        def place():
            order = _sell_order(adapter, qty=300, price=11.0)
            with lock:
                results.append(order.status)

        with ThreadPoolExecutor(max_workers=20) as pool:
            list(pool.map(lambda _: place(), range(20)))

        submitted = results.count(OrderStatus.SUBMITTED)
        assert submitted == 3  # 300+300+300，第 4 笔起拒绝
        pos = adapter.get_position("000001")
        assert pos.available_quantity == 100
        assert pos.frozen_quantity == 900

    def test_concurrent_fills_and_cancels_conserve(self, adapter):
        orders = [_buy_order(adapter, qty=1000, price=9.0) for _ in range(5)]

        def worker(i):
            oid = orders[i].order_id
            if i % 2 == 0:
                adapter.simulate_fill(oid, quantity=500, price=9.0)
                adapter.cancel_order(oid)
            else:
                adapter.cancel_order(oid)

        with ThreadPoolExecutor(max_workers=5) as pool:
            list(pool.map(worker, range(5)))

        account = adapter.get_account()
        assert account.frozen_cash == 0
        report = adapter.freeze_report()["conservation"]
        assert report["cash_conservation_ok"] is True
        # 偶数索引的三笔（0/2/4）各成交 500：3 * 500 * 9 + 费用
        assert account.available_cash == Decimal("100000") - Decimal("13500") - Decimal("15")

    def test_idempotent_client_order_id_under_duplicate_requests(self, adapter):
        def place():
            return _buy_order(
                adapter, qty=1000, price=9.0, client_order_id="IDEMP-1"
            )

        with ThreadPoolExecutor(max_workers=10) as pool:
            orders = list(pool.map(lambda _: place(), range(10)))

        order_ids = {o.order_id for o in orders}
        assert len(order_ids) == 1  # 只产生一笔委托
        account = adapter.get_account()
        assert account.frozen_cash == Decimal("9005")


class TestRejectedRetry:
    """被拒订单不占冻结，可直接重试。"""

    def test_rejected_order_holds_nothing_and_can_retry(self, adapter):
        # 下一笔超出资金的买单被拒
        order = _buy_order(adapter, qty=20000, price=9.0)
        assert order.status == OrderStatus.REJECTED
        assert adapter.get_account().frozen_cash == 0

        # 同号重试为小额可成交委托
        retried = adapter.retry_order(order.order_id, price=9.0)
        # 20000 股仍然超过资金 -> 拒绝；再改数量走新单验证释放逻辑无残留
        small = _buy_order(adapter, qty=1000, price=9.0)
        assert small.status == OrderStatus.SUBMITTED
        assert adapter.get_account().frozen_cash == Decimal("9005")
        assert retried.status == OrderStatus.REJECTED

    def test_partial_filled_order_cannot_retry(self, adapter):
        order = _buy_order(adapter, qty=1000, price=9.0)
        adapter.simulate_fill(order.order_id, quantity=400, price=9.0)
        result = adapter.retry_order(order.order_id, price=8.0)
        # 部分成交订单保留原状态，不重新冻结
        assert result.status == OrderStatus.PARTIAL_FILLED
        assert "不能重试" in result.error_message


class TestTPlus1:
    """T+1 模式下买入当日不可卖，持仓口径仍守恒。"""

    def test_buy_not_sellable_same_day(self):
        adapter = SimulationAdapter({"initial_cash": 100000, "t_plus_1": True})
        adapter.connect()
        adapter.set_quote("000001", 10.0)

        _buy_in(adapter, qty=1000)
        pos = adapter.get_position("000001")
        assert pos.quantity == 1000
        assert pos.available_quantity == 0

        order = _sell_order(adapter, qty=100, price=11.0)
        assert order.status == OrderStatus.REJECTED
        assert "持仓不足" in order.error_message

        report = adapter.freeze_report()["conservation"]
        assert report["positions_conservation_ok"] is True


class TestFreezeReport:
    """查询能解释可用 / 占用 / 已结算差异。"""

    def test_report_explains_cash_and_positions(self, adapter):
        _buy_in(adapter, qty=1000, price=10.0)
        resting = _sell_order(adapter, qty=400, price=11.0)
        adapter.simulate_fill(resting.order_id, quantity=100, price=11.0)

        report = adapter.freeze_report()
        cash = report["cash"]
        assert cash["frozen_cash_explained_by_orders"] == cash["frozen_cash"]
        assert len(cash["cash_holding_orders"]) == 0  # 卖出不冻结现金

        positions = {p["stock_code"]: p for p in report["positions"]}
        p = positions["000001"]
        assert p["quantity"] == 900
        assert p["frozen_quantity"] == 300
        assert p["available_quantity"] == 600
        assert p["conservation_ok"] is True
        assert len(p["freeze_orders"]) == 1

        conservation = report["conservation"]
        assert conservation["cash_conservation_ok"] is True
        assert conservation["positions_conservation_ok"] is True

    def test_moves_audit_trail_ordered(self, adapter):
        order = _buy_order(adapter, qty=1000, price=9.0)
        adapter.simulate_fill(order.order_id, quantity=400, price=9.0)
        adapter.cancel_order(order.order_id)

        moves = adapter.freeze_moves(order.order_id)
        assert [m["reason"] for m in moves] == ["freeze", "fill", "cancel"]
        seqs = [m["seq"] for m in moves]
        assert seqs == sorted(seqs)
