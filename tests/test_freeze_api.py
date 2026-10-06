"""冻结机制 API 端到端测试：幂等下单、撤单释放、重试、冻结报告、并发。"""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import init_database
from app.controllers.trading_controller import trading_service


@pytest.fixture()
def client():
    """每个用例重置为全新的模拟账户，避免模块级单例串扰。"""
    init_database()
    trading_service.connect("simulation", {"initial_cash": 100000})
    trading_service.adapter.set_quote("000001", 10.0)
    with TestClient(app) as c:
        yield c


def _resting_buy(client, cid=None):
    payload = {
        "stock_code": "000001",
        "quantity": 1000,
        "price": 9.0,
        "order_type": "limit",
    }
    if cid:
        payload["client_order_id"] = cid
    return client.post("/api/trading/buy", json=payload)


class TestFreezeAPI:
    def test_buy_freeze_visible_in_account(self, client):
        resp = _resting_buy(client)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "submitted"
        assert body["freeze_rule"] == "limit"
        assert body["frozen_amount"] == 9005.0

        account = client.get("/api/trading/account").json()
        assert account["frozen_cash"] == 9005.0
        assert account["available_cash"] == 100000 - 9005

    def test_freeze_report_explains_and_conserves(self, client):
        resp = _resting_buy(client)
        order_id = resp.json()["order_id"]

        report = client.get("/api/trading/freeze/report").json()
        cash = report["cash"]
        assert cash["frozen_cash"] == 9005.0
        assert cash["frozen_cash_explained_by_orders"] == 9005.0
        assert cash["cash_conservation"] == 100000.0
        assert report["conservation"]["cash_conservation_ok"] is True
        assert report["conservation"]["no_negative_balance"] is True
        assert any(
            e["order_id"] == order_id for e in report["freeze_entries"]
        )

        moves = client.get(f"/api/trading/freeze/report", params={"order_id": order_id}).json()
        assert [m["reason"] for m in moves["moves"]] == ["freeze"]

    def test_cancel_releases_freeze(self, client):
        order_id = _resting_buy(client).json()["order_id"]

        resp = client.delete(f"/api/trading/orders/{order_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

        account = client.get("/api/trading/account").json()
        assert account["frozen_cash"] == 0.0
        assert account["available_cash"] == 100000.0

    def test_double_cancel_is_safe(self, client):
        order_id = _resting_buy(client).json()["order_id"]
        assert client.delete(f"/api/trading/orders/{order_id}").status_code == 200
        second = client.delete(f"/api/trading/orders/{order_id}")
        assert second.status_code == 400

        account = client.get("/api/trading/account").json()
        assert account["frozen_cash"] == 0.0

    def test_retry_re_freezes_with_new_price(self, client):
        order_id = _resting_buy(client).json()["order_id"]

        resp = client.post(
            f"/api/trading/orders/{order_id}/retry", json={"price": 8.0}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "submitted"
        assert body["frozen_amount"] == 8005.0

        account = client.get("/api/trading/account").json()
        assert account["frozen_cash"] == 8005.0

        moves = client.get("/api/trading/freeze/moves").json()["moves"]
        reasons = {m["reason"] for m in moves if m["order_id"] == order_id}
        assert {"retry"} <= reasons

    def test_idempotent_client_order_id(self, client):
        results = []

        def fire():
            results.append(_resting_buy(client, cid="IDEMP-API-1").json())

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: fire(), range(8)))

        assert len({r["order_id"] for r in results}) == 1
        account = client.get("/api/trading/account").json()
        assert account["frozen_cash"] == 9005.0

    def test_concurrent_buys_never_overcommit(self, client):
        codes = []
        lock = threading.Lock()

        def fire(i):
            r = _resting_buy(client, cid=f"C{i}")
            with lock:
                codes.append(r.status_code)

        with ThreadPoolExecutor(max_workers=16) as pool:
            list(pool.map(fire, range(16)))

        assert codes.count(200) == 11   # 成功冻结的挂单
        assert codes.count(400) == 5    # 资金不足被拒，未产生任何冻结

        report = client.get("/api/trading/freeze/report").json()
        assert report["conservation"]["no_negative_balance"] is True
        assert report["conservation"]["cash_conservation_ok"] is True

    def test_partial_fill_then_cancel_via_service(self, client):
        # 通过适配器驱动部分成交回报，验证 API 查询到的差异解释
        order_id = _resting_buy(client).json()["order_id"]
        adapter = trading_service.adapter
        adapter.simulate_fill(order_id, quantity=400, price=9.0)

        order = client.get(f"/api/trading/orders/{order_id}").json()
        assert order["status"] == "partial"
        assert order["filled_quantity"] == 400

        # 部分成交状态允许撤单，剩余冻结释放
        assert client.delete(f"/api/trading/orders/{order_id}").status_code == 200
        account = client.get("/api/trading/account").json()
        assert account["frozen_cash"] == 0.0
        # 已结算 400 股：3600 货款 + 5 费用
        assert account["available_cash"] == 100000 - 3605
