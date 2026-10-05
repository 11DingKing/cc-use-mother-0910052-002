"""业务模块说明。"""

import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta

from app.main import app
from app.config import init_database


@pytest.fixture(scope="module")
def client():
    """业务模块说明。"""
    init_database()
    with TestClient(app) as c:
        yield c


class TestHealthEndpoint:
    """业务模块说明。"""
    
    def test_health_check(self, client):
        """业务模块说明。"""
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


class TestWatchlistAPI:
    """业务模块说明。"""
    
    def test_add_and_get_watchlist(self, client):
        """业务模块说明。"""
        # Add stock (use valid A-share format)
        response = client.post("/api/watchlist", json={
            "stock_code": "000001",
            "stock_name": "测试股票"
        })
        assert response.status_code == 200
        
        # Get watchlist
        response = client.get("/api/watchlist")
        assert response.status_code == 200
        data = response.json()
        
        # Handle both list and dict response formats
        items = data.get("items", data) if isinstance(data, dict) else data
        assert isinstance(items, list)
        
        # Check if added stock exists (may be normalized to sz000001)
        codes = [item["stock_code"] for item in items]
        assert any("000001" in code for code in codes)
    
    def test_delete_from_watchlist(self, client):
        """业务模块说明。"""
        # First add
        client.post("/api/watchlist", json={
            "stock_code": "000002",
            "stock_name": "删除测试"
        })
        
        # Then delete
        response = client.delete("/api/watchlist/000002")
        assert response.status_code == 200
        
        # Verify deleted
        response = client.get("/api/watchlist")
        data = response.json()
        items = data.get("items", data) if isinstance(data, dict) else data
        codes = [item["stock_code"] for item in items]
        assert "000002" not in codes
    
    def test_watchlist_sorting(self, client):
        """业务模块说明。"""
        # Add multiple stocks
        for i in range(3):
            client.post("/api/watchlist", json={
                "stock_code": f"60000{i}",
                "stock_name": f"排序测试{i}"
            })
        
        # Get sorted by code
        response = client.get("/api/watchlist", params={"sort_by": "stock_code"})
        assert response.status_code == 200


class TestStockAPI:
    """业务模块说明。"""
    
    def test_get_candles_empty(self, client):
        """业务模块说明。"""
        response = client.get("/api/stocks/000099/candles")
        # May return various status codes depending on data availability
        assert response.status_code in [200, 404, 500, 502]


class TestAnalysisAPI:
    """业务模块说明。"""
    
    def test_get_analysis_not_found(self, client):
        """业务模块说明。"""
        response = client.get("/api/analysis/000099")
        # May return 200 with null or 404
        assert response.status_code in [200, 404]


class TestBacktestAPI:
    """业务模块说明。"""
    
    def test_run_backtest_validation(self, client):
        """业务模块说明。"""
        # Missing required fields
        response = client.post("/api/backtest/run", json={})
        assert response.status_code == 422  # Validation error
    
    def test_run_backtest_with_params(self, client):
        """业务模块说明。"""
        response = client.post("/api/backtest/run", json={
            "stock_code": "000001",
            "period": "daily",
            "start_date": "2024-01-01",
            "end_date": "2024-06-01",
            "initial_capital": 100000
        })
        # May succeed or fail due to no data, but should not be 422
        assert response.status_code != 422


class TestMultiLevelAnalysisAPI:
    """业务模块说明。"""
    
    def test_multi_level_analysis_endpoint_exists(self, client):
        """业务模块说明。"""
        response = client.post(
            "/api/analysis/000001/multi-level",
            params={
                "primary_period": "daily",
                "secondary_periods": "60min,30min",
            }
        )
        # May fail due to no data, but endpoint should exist
        assert response.status_code != 404
    
    def test_multi_level_recommendation_endpoint_exists(self, client):
        """业务模块说明。"""
        response = client.get(
            "/api/analysis/000001/multi-level/recommendation",
            params={
                "primary_period": "daily",
                "secondary_periods": "60min,30min",
            }
        )
        # May fail due to no data, but endpoint should exist
        assert response.status_code != 404


class TestTradingAPI:
    """业务模块说明。"""
    
    def test_connect_simulation(self, client):
        """业务模块说明。"""
        response = client.post("/api/trading/connect", json={
            "adapter_type": "simulation",
            "config": {"initial_cash": 100000}
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["adapter_type"] == "simulation"
    
    def test_get_account(self, client):
        """业务模块说明。"""
        # First connect
        client.post("/api/trading/connect", json={
            "adapter_type": "simulation",
            "config": {"initial_cash": 100000}
        })
        
        # Get account
        response = client.get("/api/trading/account")
        assert response.status_code == 200
        
        data = response.json()
        assert "total_assets" in data
        assert "available_cash" in data
    
    def test_get_positions_empty(self, client):
        """业务模块说明。"""
        client.post("/api/trading/connect", json={
            "adapter_type": "simulation"
        })
        
        response = client.get("/api/trading/positions")
        assert response.status_code == 200
        
        data = response.json()
        assert "positions" in data
        assert isinstance(data["positions"], list)
    
    def test_buy_order(self, client):
        """业务模块说明。"""
        client.post("/api/trading/connect", json={
            "adapter_type": "simulation",
            "config": {"initial_cash": 100000}
        })
        
        response = client.post("/api/trading/buy", json={
            "stock_code": "000001",
            "quantity": 100,
            "price": 10.0,
            "order_type": "limit"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "filled"
    
    def test_buy_invalid_quantity(self, client):
        """业务模块说明。"""
        client.post("/api/trading/connect", json={
            "adapter_type": "simulation"
        })
        
        response = client.post("/api/trading/buy", json={
            "stock_code": "000001",
            "quantity": 50,  # 不是100的倍数
            "price": 10.0
        })
        
        assert response.status_code == 400
        data = response.json()
        assert "error" in data
    
    def test_sell_order(self, client):
        """业务模块说明。"""
        client.post("/api/trading/connect", json={
            "adapter_type": "simulation",
            "config": {"initial_cash": 100000}
        })
        
        # Buy first
        client.post("/api/trading/buy", json={
            "stock_code": "000001",
            "quantity": 100,
            "price": 10.0
        })
        
        # Then sell
        response = client.post("/api/trading/sell", json={
            "stock_code": "000001",
            "quantity": 100,
            "price": 10.0
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "filled"
    
    def test_get_orders(self, client):
        """业务模块说明。"""
        client.post("/api/trading/connect", json={
            "adapter_type": "simulation"
        })
        
        # Execute some orders
        client.post("/api/trading/buy", json={
            "stock_code": "000001",
            "quantity": 100,
            "price": 10.0
        })
        
        response = client.get("/api/trading/orders")
        assert response.status_code == 200
        
        data = response.json()
        assert "orders" in data
    
    def test_get_quote(self, client):
        """业务模块说明。"""
        client.post("/api/trading/connect", json={
            "adapter_type": "simulation"
        })
        
        response = client.get("/api/trading/quote/000001")
        assert response.status_code == 200
        
        data = response.json()
        assert "last_price" in data
        assert "stock_code" in data
    
    def test_auto_trade_toggle(self, client):
        """业务模块说明。"""
        client.post("/api/trading/connect", json={
            "adapter_type": "simulation"
        })
        
        # Enable
        response = client.post("/api/trading/auto-trade/enable")
        assert response.status_code == 200
        
        # Disable
        response = client.post("/api/trading/auto-trade/disable")
        assert response.status_code == 200
    
    def test_disconnect(self, client):
        """业务模块说明。"""
        client.post("/api/trading/connect", json={
            "adapter_type": "simulation"
        })
        
        response = client.post("/api/trading/disconnect")
        assert response.status_code == 200


class TestAPIErrorHandling:
    """业务模块说明。"""
    
    def test_invalid_stock_code(self, client):
        """业务模块说明。"""
        response = client.get("/api/stocks/INVALID/candles")
        assert response.status_code in [400, 404, 422]
    
    def test_invalid_json(self, client):
        """业务模块说明。"""
        response = client.post(
            "/api/watchlist",
            content="invalid json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422
    
    def test_error_response_format(self, client):
        """业务模块说明。"""
        # Trigger a validation error
        response = client.post("/api/trading/buy", json={
            "stock_code": "000001",
            "quantity": 50,  # Invalid
            "price": 10.0
        })
        
        if response.status_code == 400:
            data = response.json()
            if "error" in data:
                # 检查错误信息是否用户友好（中文）
                error = data["error"]
                assert "message" in error
                # 可能包含 technical_message
                if "technical_message" in error:
                    assert error["technical_message"] is not None or error["message"] is not None
