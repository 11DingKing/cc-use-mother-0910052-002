"""业务模块说明。"""

import pytest
from decimal import Decimal
from datetime import datetime

from app.trading.base import (
    Order,
    OrderStatus,
    OrderType,
    OrderSide,
    Position,
    Account,
    RiskManager,
)
from app.trading.simulation_adapter import SimulationAdapter
from app.services.trading_service import TradingService, TradingException


class TestOrder:
    """业务模块说明。"""
    
    def test_order_creation(self):
        """业务模块说明。"""
        order = Order(
            order_id="TEST001",
            stock_code="000001",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=100,
            price=Decimal("10.50"),
        )
        
        assert order.order_id == "TEST001"
        assert order.stock_code == "000001"
        assert order.side == OrderSide.BUY
        assert order.quantity == 100
        assert order.status == OrderStatus.PENDING
    
    def test_order_to_dict(self):
        """业务模块说明。"""
        order = Order(
            order_id="TEST001",
            stock_code="000001",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=100,
            price=Decimal("10.50"),
        )
        
        data = order.to_dict()
        
        assert data["order_id"] == "TEST001"
        assert data["side"] == "buy"
        assert data["price"] == 10.50


class TestSimulationAdapter:
    """业务模块说明。"""
    
    @pytest.fixture
    def adapter(self):
        adapter = SimulationAdapter({"initial_cash": 100000})
        adapter.connect()
        return adapter
    
    def test_connect(self):
        """业务模块说明。"""
        adapter = SimulationAdapter()
        result = adapter.connect()
        
        assert result is True
        assert adapter.is_connected is True
    
    def test_get_account(self, adapter):
        """业务模块说明。"""
        account = adapter.get_account()
        
        assert account is not None
        assert account.total_assets == Decimal("100000")
        assert account.available_cash == Decimal("100000")
    
    def test_buy_order(self, adapter):
        """业务模块说明。"""
        # 设置行情
        adapter.set_quote("000001", 10.0)
        
        order = adapter.buy(
            stock_code="000001",
            quantity=100,
            price=10.0,
            order_type=OrderType.LIMIT,
        )
        
        assert order.status == OrderStatus.FILLED
        assert order.filled_quantity == 100
        assert order.filled_price == Decimal("10.0")
        
        # 检查持仓
        position = adapter.get_position("000001")
        assert position is not None
        assert position.quantity == 100
    
    def test_sell_order(self, adapter):
        """业务模块说明。"""
        # 先买入
        adapter.set_quote("000001", 10.0)
        adapter.buy("000001", 100, 10.0)
        
        # 再卖出
        order = adapter.sell(
            stock_code="000001",
            quantity=100,
            price=10.0,
            order_type=OrderType.LIMIT,
        )
        
        assert order.status == OrderStatus.FILLED
        
        # 检查持仓已清空
        position = adapter.get_position("000001")
        assert position is None
    
    def test_insufficient_funds(self, adapter):
        """业务模块说明。"""
        adapter.set_quote("000001", 10.0)
        
        # 尝试买入超过可用资金的股票
        order = adapter.buy(
            stock_code="000001",
            quantity=20000,  # 需要 200000，超过可用的 100000
            price=10.0,
        )
        
        assert order.status == OrderStatus.REJECTED
        assert "资金不足" in order.error_message
    
    def test_insufficient_position(self, adapter):
        """业务模块说明。"""
        adapter.set_quote("000001", 10.0)
        
        # 尝试卖出没有持仓的股票
        order = adapter.sell(
            stock_code="000001",
            quantity=100,
            price=10.0,
        )
        
        assert order.status == OrderStatus.REJECTED
        assert "持仓不足" in order.error_message
    
    def test_cancel_order(self, adapter):
        """业务模块说明。"""
        adapter.set_quote("000001", 10.0)
        order = adapter.buy("000001", 100, 10.0)
        
        # 已成交订单无法撤销
        result = adapter.cancel_order(order.order_id)
        assert result is False
    
    def test_get_orders(self, adapter):
        """业务模块说明。"""
        adapter.set_quote("000001", 10.0)
        adapter.buy("000001", 100, 10.0)
        adapter.buy("000001", 200, 10.0)
        
        orders = adapter.get_orders()
        assert len(orders) == 2
        
        # 按股票代码筛选
        orders = adapter.get_orders(stock_code="000001")
        assert len(orders) == 2
        
        # 按状态筛选
        orders = adapter.get_orders(status=OrderStatus.FILLED)
        assert len(orders) == 2


class TestRiskManager:
    """业务模块说明。"""
    
    @pytest.fixture
    def risk_manager(self):
        return RiskManager({
            "max_single_order_amount": 50000,
            "max_daily_amount": 100000,
            "max_position_ratio": 0.3,
            "stop_loss_ratio": 0.08,
            "take_profit_ratio": 0.15,
        })
    
    @pytest.fixture
    def account(self):
        return Account(
            account_id="TEST",
            broker="模拟",
            total_assets=Decimal("100000"),
            available_cash=Decimal("80000"),
            frozen_cash=Decimal("0"),
            market_value=Decimal("20000"),
            profit_loss=Decimal("0"),
            profit_loss_ratio=0.0,
        )
    
    @pytest.fixture
    def positions(self):
        return [
            Position(
                stock_code="000001",
                stock_name="平安银行",
                quantity=1000,
                available_quantity=1000,
                avg_cost=Decimal("10.0"),
                current_price=Decimal("10.0"),
                market_value=Decimal("10000"),
                profit_loss=Decimal("0"),
                profit_loss_ratio=0.0,
            ),
        ]
    
    def test_check_order_pass(self, risk_manager, account, positions):
        """业务模块说明。"""
        order = Order(
            order_id="TEST",
            stock_code="000002",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=100,
            price=Decimal("10.0"),
        )
        
        passed, reason = risk_manager.check_order(order, account, positions)
        
        assert passed is True
        assert "通过" in reason
    
    def test_check_order_exceed_single_limit(self, risk_manager, account, positions):
        """业务模块说明。"""
        order = Order(
            order_id="TEST",
            stock_code="000002",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=10000,
            price=Decimal("10.0"),  # 100000 > 50000
        )
        
        passed, reason = risk_manager.check_order(order, account, positions)
        
        assert passed is False
        assert "单笔" in reason
    
    def test_check_order_insufficient_funds(self, risk_manager, account, positions):
        """业务模块说明。"""
        order = Order(
            order_id="TEST",
            stock_code="000002",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=10000,
            price=Decimal("9.0"),  # 90000 > 80000 available
        )
        
        # 先通过单笔限额，但会在资金检查失败
        # 需要调整配置
        rm = RiskManager({"max_single_order_amount": 100000})
        passed, reason = rm.check_order(order, account, positions)
        
        assert passed is False
        assert "可用资金" in reason
    
    def test_check_position_concentration(self, risk_manager, account, positions):
        """业务模块说明。"""
        order = Order(
            order_id="TEST",
            stock_code="000001",  # 已有持仓
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=2500,
            price=Decimal("10.0"),  # 增加 25000，总计 35000 > 30000 (30%)
        )
        
        passed, reason = risk_manager.check_order(order, account, positions)
        
        assert passed is False
        assert "集中度" in reason
    
    def test_check_stop_loss(self, risk_manager):
        """业务模块说明。"""
        position = Position(
            stock_code="000001",
            stock_name="平安银行",
            quantity=1000,
            available_quantity=1000,
            avg_cost=Decimal("10.0"),
            current_price=Decimal("9.0"),
            market_value=Decimal("9000"),
            profit_loss=Decimal("-1000"),
            profit_loss_ratio=-0.10,  # 亏损 10% > 8%
        )
        
        assert risk_manager.check_stop_loss(position) is True
    
    def test_check_take_profit(self, risk_manager):
        """业务模块说明。"""
        position = Position(
            stock_code="000001",
            stock_name="平安银行",
            quantity=1000,
            available_quantity=1000,
            avg_cost=Decimal("10.0"),
            current_price=Decimal("12.0"),
            market_value=Decimal("12000"),
            profit_loss=Decimal("2000"),
            profit_loss_ratio=0.20,  # 盈利 20% > 15%
        )
        
        assert risk_manager.check_take_profit(position) is True


class TestTradingService:
    """业务模块说明。"""
    
    @pytest.fixture
    def service(self):
        service = TradingService()
        service.connect("simulation", {"initial_cash": 100000})
        return service
    
    def test_connect(self, service):
        """业务模块说明。"""
        assert service.adapter.is_connected is True
    
    def test_get_account(self, service):
        """业务模块说明。"""
        account = service.get_account()
        
        assert "total_assets" in account
        assert "available_cash" in account
    
    def test_buy(self, service):
        """业务模块说明。"""
        result = service.buy(
            stock_code="000001",
            quantity=100,
            price=10.0,
        )
        
        assert result["status"] == "filled"
        assert result["filled_quantity"] == 100
    
    def test_buy_invalid_quantity(self, service):
        """业务模块说明。"""
        with pytest.raises(TradingException) as exc_info:
            service.buy(
                stock_code="000001",
                quantity=50,  # 不是100的倍数
                price=10.0,
            )
        
        assert "100的整数倍" in str(exc_info.value.message)
    
    def test_sell(self, service):
        """业务模块说明。"""
        # 先买入
        service.buy("000001", 100, 10.0)
        
        # 再卖出
        result = service.sell(
            stock_code="000001",
            quantity=100,
            price=10.0,
        )
        
        assert result["status"] == "filled"
    
    def test_sell_no_position(self, service):
        """业务模块说明。"""
        with pytest.raises(TradingException) as exc_info:
            service.sell(
                stock_code="000002",
                quantity=100,
                price=10.0,
            )
        
        assert "持仓不足" in str(exc_info.value.message)
    
    def test_get_orders(self, service):
        """业务模块说明。"""
        service.buy("000001", 100, 10.0)
        service.buy("000001", 200, 10.0)
        
        orders = service.get_orders()
        
        assert len(orders) == 2
    
    def test_auto_trade_disabled(self, service):
        """业务模块说明。"""
        result = service.execute_signal(
            stock_code="000001",
            signal_type="BUY_1",
            signal_strength=0.8,
            price=10.0,
        )
        
        assert result is None  # 自动交易默认禁用
    
    def test_auto_trade_enabled(self, service):
        """业务模块说明。"""
        service.enable_auto_trade(True)
        
        result = service.execute_signal(
            stock_code="000001",
            signal_type="BUY_1",
            signal_strength=0.8,
            price=10.0,
            position_ratio=0.1,
        )
        
        assert result is not None
        assert result["status"] == "filled"
