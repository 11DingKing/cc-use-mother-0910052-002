"""冻结 / 释放机制测试：守恒、并发、幂等、部分成交与恢复。"""

import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest

from app.trading.base import Order, OrderSide, OrderType, OrderStatus
from app.trading.simulation_adapter import SimulationAdapter
from app.trading.ledger import FreezeLedger, FreezeError
from app.services.trading_service import TradingService, TradingException


@pytest.fixture
def adapter():
    a = SimulationAdapter({"initial_cash": 100000})
    a.connect()
    a.set_quote("000001", 10.0)
    return a


def _buy_order(adapter, code, qty, price, client_id=None):
    return adapter.place_order(
        Order(
            order_id=adapter._generate_order_id(),
            stock_code=code,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=qty,
            price=Decimal(str(price)),
            client_order_id=client_id,
        )
    )


def _sell_order(adapter, code, qty, price, client_id=None):
    return adapter.place_order(
        Order(
            order_id=adapter._generate_order_id(),
            stock_code=code,
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=qty,
            price=Decimal(str(price)),
            client_order_id=client_id,
        )
    )


def _assert_cash_conserved(adapter, capital=Decimal("100000.00")):
    acc = adapter.get_account()
    assert acc.available_cash >= 0
    assert acc.frozen_cash >= 0
    assert (acc.available_cash + acc.frozen_cash + acc.settled_cash) == capital
    for p in adapter.get_positions():
        assert p.quantity == p.available_quantity + p.frozen_quantity
        assert p.available_quantity >= 0 and p.frozen_quantity >= 0


class TestFreezeOnConfirmation:
    def test_pending_buy_freezes_cash(self, adapter):
        # 限价 9.5，当前价 10，不成交，应挂起并冻结
        order = _buy_order(adapter, "000001", 1000, 9.5)
        assert order.status == OrderStatus.SUBMITTED
        assert order.freeze_state == "active"
        # 9.5*1000=9500 + 预估佣金 5
        assert order.frozen_cash == Decimal("9505.00")
        assert order.frozen_price == Decimal("9.5")

        acc = adapter.get_account()
        assert acc.available_cash == Decimal("90495.00")
        assert acc.frozen_cash == Decimal("9505.00")
        _assert_cash_conserved(adapter)

    def test_pending_sell_freezes_position(self, adapter):
        _buy_order(adapter, "000001", 1000, 10.0)  # 立即成交
        order = _sell_order(adapter, "000001", 400, 10.5)  # 挂起
        assert order.status == OrderStatus.SUBMITTED

        pos = adapter.get_position("000001")
        assert pos.quantity == 1000
        assert pos.frozen_quantity == 400
        assert pos.available_quantity == 600
        assert order.frozen_quantity == 400
        _assert_cash_conserved(adapter)

    def test_rejected_buy_freezes_nothing(self, adapter):
        order = _buy_order(adapter, "000001", 100000, 9.5)  # 需 95 万
        assert order.status == OrderStatus.REJECTED
        assert order.freeze_state == "none"
        acc = adapter.get_account()
        assert acc.available_cash == Decimal("100000.00")
        assert acc.frozen_cash == 0
        # 没有任何预留流水
        assert adapter.get_freeze_events() == []

    def test_rejected_sell_freezes_nothing(self, adapter):
        order = _sell_order(adapter, "000001", 100, 10.5)
        assert order.status == OrderStatus.REJECTED
        assert adapter.get_position("000001") is None


class TestRelease:
    def test_cancel_buy_releases_cash(self, adapter):
        order = _buy_order(adapter, "000001", 1000, 9.5)
        assert adapter.cancel_order(order.order_id) is True
        order = adapter.get_order(order.order_id)
        assert order.status == OrderStatus.CANCELLED
        assert order.freeze_state == "released"
        assert order.frozen_cash == 0
        assert order.released_cash == Decimal("9505.00")
        acc = adapter.get_account()
        assert acc.available_cash == Decimal("100000.00")
        assert acc.frozen_cash == 0
        _assert_cash_conserved(adapter)

    def test_cancel_sell_releases_position(self, adapter):
        _buy_order(adapter, "000001", 1000, 10.0)
        order = _sell_order(adapter, "000001", 400, 10.5)
        assert adapter.cancel_order(order.order_id) is True
        pos = adapter.get_position("000001")
        assert pos.frozen_quantity == 0
        assert pos.available_quantity == 1000
        assert order.released_quantity == 400

    def test_double_cancel_is_idempotent_no_double_release(self, adapter):
        order = _buy_order(adapter, "000001", 1000, 9.5)
        assert adapter.cancel_order(order.order_id) is True
        # 再次撤单被拒绝，但即使直接调 release 也不会重复退还
        assert adapter.cancel_order(order.order_id) is False
        second = adapter._ledger.release(
            adapter.get_order(order.order_id),
            adapter.get_account(),
            adapter._positions,
            reason="重复撤单重试",
        )
        assert second["cash"] == 0
        assert adapter.get_account().available_cash == Decimal("100000.00")

    def test_cancel_filled_order_releases_nothing(self, adapter):
        order = _buy_order(adapter, "000001", 1000, 10.0)
        assert order.status == OrderStatus.FILLED
        assert adapter.cancel_order(order.order_id) is False
        # 成交后冻结为 0，可用不因任何释放而增加
        _assert_cash_conserved(adapter)


class TestPartialFill:
    def test_buy_partial_then_cancel(self, adapter):
        order = _buy_order(adapter, "000001", 1000, 9.5)  # 冻结 9505
        adapter.apply_fill(order.order_id, 300, 9.5)

        order = adapter.get_order(order.order_id)
        assert order.status == OrderStatus.PARTIAL_FILLED
        assert order.filled_quantity == 300
        pos = adapter.get_position("000001")
        assert pos.quantity == 300 and pos.available_quantity == 300
        # 剩余 700 股仍冻结（费用缓冲首笔已吃完最低佣金 5）
        assert order.frozen_cash == Decimal("6650.00")  # 9.5*700
        _assert_cash_conserved(adapter)

        adapter.cancel_order(order.order_id)
        order = adapter.get_order(order.order_id)
        assert order.status == OrderStatus.CANCELLED
        assert order.frozen_cash == 0
        # 释放量 = 剩余冻结
        assert order.released_cash == Decimal("6650.00")
        _assert_cash_conserved(adapter)

    def test_buy_multiple_partials_complete(self, adapter):
        order = _buy_order(adapter, "000001", 1000, 9.5)
        adapter.apply_fill(order.order_id, 300, 9.5)
        adapter.apply_fill(order.order_id, 300, 9.5)
        adapter.apply_fill(order.order_id, 400, 9.5)
        order = adapter.get_order(order.order_id)
        assert order.status == OrderStatus.FILLED
        assert order.filled_quantity == 1000
        assert order.frozen_cash == 0
        assert order.freeze_state == "settled"
        pos = adapter.get_position("000001")
        assert pos.quantity == 1000 and pos.available_quantity == 1000
        _assert_cash_conserved(adapter)

    def test_sell_partial_then_cancel(self, adapter):
        _buy_order(adapter, "000001", 1000, 10.0)
        order = _sell_order(adapter, "000001", 500, 10.5)

        adapter.apply_fill(order.order_id, 200, 10.5)
        order = adapter.get_order(order.order_id)
        assert order.status == OrderStatus.PARTIAL_FILLED
        pos = adapter.get_position("000001")
        assert pos.quantity == 800
        assert pos.frozen_quantity == 300
        assert pos.available_quantity == 500
        # 回款 = 10.5*200 - 佣金5(最低) - 印花税 2.1
        cash_after_fill = Decimal("100000") - Decimal("10005") + Decimal("2092.90")
        assert adapter.get_account().available_cash == cash_after_fill

        adapter.cancel_order(order.order_id)
        pos = adapter.get_position("000001")
        assert pos.quantity == 800 and pos.available_quantity == 800
        assert pos.frozen_quantity == 0
        assert order.released_quantity == 300
        _assert_cash_conserved(adapter)

    def test_better_fill_price_returns_change(self, adapter):
        # 直接驱动低于冻结价的成交，多预留部分应找零回可用
        order = _buy_order(adapter, "000001", 1000, 10.0)  # 冻结 10005
        # 先撤掉不行——改为挂起单：用 9.5 挂单再 9.4 成交
        adapter.cancel_order(order.order_id)
        pending = _buy_order(adapter, "000001", 1000, 9.5)  # 冻结 9505
        avail_before = adapter.get_account().available_cash
        adapter.apply_fill(pending.order_id, 1000, 9.4)
        # 实际成本 9400+5=9405，预留 9505，找零 100
        assert adapter.get_account().available_cash == avail_before + Decimal("100.00")
        _assert_cash_conserved(adapter)


class TestIdempotentRetry:
    def test_same_client_order_id_does_not_double_freeze(self, adapter):
        first = _buy_order(adapter, "000001", 1000, 9.5, client_id="REQ-1")
        second = _buy_order(adapter, "000001", 1000, 9.5, client_id="REQ-1")
        assert first.order_id == second.order_id
        assert adapter.get_account().frozen_cash == Decimal("9505.00")
        orders = adapter.get_orders()
        assert len(orders) == 1


class TestConcurrency:
    def test_concurrent_buys_never_overcommit_cash(self, adapter):
        # 每单冻结 9.5*100+5=955；10 万最多接受 104 单
        results = []
        lock = threading.Lock()

        def submit(i):
            o = _buy_order(adapter, "000001", 100, 9.5, client_id=f"C-{i}")
            with lock:
                results.append(o.status)

        with ThreadPoolExecutor(max_workers=16) as pool:
            list(pool.map(submit, range(200)))

        accepted = sum(1 for s in results if s == OrderStatus.SUBMITTED)
        rejected = sum(1 for s in results if s == OrderStatus.REJECTED)
        assert accepted == 104
        assert rejected == 96
        acc = adapter.get_account()
        assert acc.frozen_cash == Decimal("99320.00")  # 104*955
        assert acc.available_cash == Decimal("680.00")
        _assert_cash_conserved(adapter)

    def test_concurrent_sells_never_overcommit_position(self, adapter):
        _buy_order(adapter, "000001", 1000, 10.0)
        results = []
        lock = threading.Lock()

        def submit(i):
            o = _sell_order(adapter, "000001", 100, 10.5, client_id=f"S-{i}")
            with lock:
                results.append(o.status)

        with ThreadPoolExecutor(max_workers=16) as pool:
            list(pool.map(submit, range(20)))

        accepted = sum(1 for s in results if s == OrderStatus.SUBMITTED)
        assert accepted == 10
        pos = adapter.get_position("000001")
        assert pos.frozen_quantity == 1000
        assert pos.available_quantity == 0


class TestRecovery:
    def test_recover_repairs_cash_drift(self, adapter):
        o1 = _buy_order(adapter, "000001", 1000, 9.5)  # 冻结 9505
        o2 = _buy_order(adapter, "000002", 1000, 9.0)  # 冻结 9005
        adapter.set_quote("000002", 10.0)

        # 模拟故障后内存漂移：冻结被错误清零、可用虚高
        acc = adapter.get_account()
        acc.frozen_cash = Decimal("0")
        acc.available_cash = Decimal("100000.00")

        report = adapter.recover()
        assert acc.frozen_cash == Decimal("18510.00")
        assert acc.available_cash == Decimal("81490.00")
        _assert_cash_conserved(adapter)
        assert any("frozen_cash_drift" in str(r) for r in report["repaired"])

    def test_recover_releases_orphan_freeze(self, adapter):
        order = _buy_order(adapter, "000001", 1000, 9.5)
        # 撤单流程中只改状态、台账因故障没释放（模拟孤儿冻结）
        order.status = OrderStatus.CANCELLED
        assert adapter.get_account().frozen_cash == Decimal("9505.00")

        report = adapter.recover()
        assert adapter.get_account().frozen_cash == 0
        assert adapter.get_account().available_cash == Decimal("100000.00")
        assert len(report["orphans"]) == 1
        _assert_cash_conserved(adapter)

    def test_recover_rebuilds_sell_freeze(self, adapter):
        _buy_order(adapter, "000001", 1000, 10.0)
        order = _sell_order(adapter, "000001", 400, 10.5)
        # 部分成交 100 后故障，持仓冻结字段错乱
        adapter.apply_fill(order.order_id, 100, 10.5)
        pos = adapter.get_position("000001")
        pos.frozen_quantity = 0
        pos.available_quantity = pos.quantity  # 虚高

        adapter.recover()
        pos = adapter.get_position("000001")
        assert pos.quantity == 900
        assert pos.frozen_quantity == 300
        assert pos.available_quantity == 600
        _assert_cash_conserved(adapter)


class TestQueryExplainability:
    def test_account_breakdown(self, adapter):
        _buy_order(adapter, "000001", 1000, 9.5)
        data = adapter.get_account().to_dict()
        breakdown = data["breakdown"]
        assert breakdown["available"] + breakdown["reserved"] + breakdown["settled"] == 100000.0
        assert "cash_formula" in breakdown

    def test_freeze_events_trace(self, adapter):
        order = _buy_order(adapter, "000001", 1000, 9.5)
        adapter.cancel_order(order.order_id)
        events = adapter.get_freeze_events(order.order_id)
        types = [e["event_type"] for e in events]
        assert types == ["reserve_cash", "release_cash"]
        assert events[0]["frozen_cash_delta"] == 9505.0

    def test_reservations_list(self, adapter):
        _buy_order(adapter, "000001", 1000, 9.5)
        reservations = adapter.get_reservations()
        assert len(reservations) == 1
        assert reservations[0]["frozen_cash"] == 9505.0


class TestServiceLayer:
    @pytest.fixture
    def service(self):
        s = TradingService()
        s.connect("simulation", {"initial_cash": 100000})
        s.adapter.set_quote("000001", 10.0)
        return s

    def test_concurrent_buy_api_level(self, service):
        outcomes = []

        def submit(i):
            try:
                service.buy("000001", 100, 9.5, client_order_id=f"API-{i}")
                outcomes.append("ok")
            except TradingException:
                outcomes.append("rejected")

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(submit, range(150)))

        assert outcomes.count("ok") == 104
        acc = service.get_account()
        assert acc["available_cash"] + acc["frozen_cash"] + acc["settled_cash"] == 100000.0

    def test_retry_same_request_returns_same_order(self, service):
        r1 = service.buy("000001", 100, 9.5, client_order_id="DUP-1")
        r2 = service.buy("000001", 100, 9.5, client_order_id="DUP-1")
        assert r1["order_id"] == r2["order_id"]
        assert service.get_account()["frozen_cash"] == 955.0
