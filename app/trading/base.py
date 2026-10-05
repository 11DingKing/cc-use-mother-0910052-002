"""业务模块说明。"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Callable

logger = logging.getLogger(__name__)


class OrderSide(Enum):
    """业务模块说明。"""
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    """业务模块说明。"""
    MARKET = "market"       # 市价单
    LIMIT = "limit"         # 限价单
    STOP = "stop"           # 止损单
    STOP_LIMIT = "stop_limit"  # 止损限价单


class OrderStatus(Enum):
    """业务模块说明。"""
    PENDING = "pending"           # 待提交
    SUBMITTED = "submitted"       # 已提交
    PARTIAL_FILLED = "partial"    # 部分成交
    FILLED = "filled"             # 全部成交
    CANCELLED = "cancelled"       # 已撤销
    REJECTED = "rejected"         # 已拒绝
    FAILED = "failed"             # 失败


@dataclass
class Order:
    """业务模块说明。"""
    order_id: str
    stock_code: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    price: Optional[Decimal] = None       # 限价单价格
    stop_price: Optional[Decimal] = None  # 止损触发价
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: int = 0
    filled_price: Optional[Decimal] = None
    commission: Decimal = Decimal("0")
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    error_message: Optional[str] = None
    
    # 策略相关
    strategy_name: Optional[str] = None
    signal_type: Optional[str] = None     # 买卖点类型，如 BUY_1, SELL_2
    signal_strength: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            "order_id": self.order_id,
            "stock_code": self.stock_code,
            "side": self.side.value,
            "order_type": self.order_type.value,
            "quantity": self.quantity,
            "price": float(self.price) if self.price else None,
            "stop_price": float(self.stop_price) if self.stop_price else None,
            "status": self.status.value,
            "filled_quantity": self.filled_quantity,
            "filled_price": float(self.filled_price) if self.filled_price else None,
            "commission": float(self.commission),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "error_message": self.error_message,
            "strategy_name": self.strategy_name,
            "signal_type": self.signal_type,
            "signal_strength": self.signal_strength,
        }


@dataclass
class Position:
    """业务模块说明。"""
    stock_code: str
    stock_name: str
    quantity: int                         # 持仓数量
    available_quantity: int               # 可用数量
    avg_cost: Decimal                     # 持仓成本
    current_price: Decimal                # 当前价格
    market_value: Decimal                 # 市值
    profit_loss: Decimal                  # 盈亏金额
    profit_loss_ratio: float              # 盈亏比例
    updated_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict:
        return {
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "quantity": self.quantity,
            "available_quantity": self.available_quantity,
            "avg_cost": float(self.avg_cost),
            "current_price": float(self.current_price),
            "market_value": float(self.market_value),
            "profit_loss": float(self.profit_loss),
            "profit_loss_ratio": self.profit_loss_ratio,
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class Account:
    """业务模块说明。"""
    account_id: str
    broker: str                           # 券商/平台名称
    total_assets: Decimal                 # 总资产
    available_cash: Decimal               # 可用资金
    frozen_cash: Decimal                  # 冻结资金
    market_value: Decimal                 # 持仓市值
    profit_loss: Decimal                  # 当日盈亏
    profit_loss_ratio: float              # 当日盈亏比例
    updated_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict:
        return {
            "account_id": self.account_id,
            "broker": self.broker,
            "total_assets": float(self.total_assets),
            "available_cash": float(self.available_cash),
            "frozen_cash": float(self.frozen_cash),
            "market_value": float(self.market_value),
            "profit_loss": float(self.profit_loss),
            "profit_loss_ratio": self.profit_loss_ratio,
            "updated_at": self.updated_at.isoformat(),
        }


class TradingAdapter(ABC):
    """业务模块说明。"""
    
    def __init__(self, config: Dict):
        self.config = config
        self._connected = False
        self._callbacks: Dict[str, List[Callable]] = {
            "on_order": [],
            "on_trade": [],
            "on_position": [],
            "on_account": [],
            "on_error": [],
        }
    
    @property
    def is_connected(self) -> bool:
        return self._connected
    
    def register_callback(self, event: str, callback: Callable) -> None:
        """业务模块说明。"""
        if event in self._callbacks:
            self._callbacks[event].append(callback)
    
    def _emit(self, event: str, data) -> None:
        """业务模块说明。"""
        for callback in self._callbacks.get(event, []):
            try:
                callback(data)
            except Exception as e:
                logger.error(f"Callback error: {e}")
    
    @abstractmethod
    def connect(self) -> bool:
        """业务模块说明。"""
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """业务模块说明。"""
        pass
    
    @abstractmethod
    def get_account(self) -> Optional[Account]:
        """业务模块说明。"""
        pass
    
    @abstractmethod
    def get_positions(self) -> List[Position]:
        """业务模块说明。"""
        pass
    
    @abstractmethod
    def get_position(self, stock_code: str) -> Optional[Position]:
        """业务模块说明。"""
        pass
    
    @abstractmethod
    def place_order(self, order: Order) -> Order:
        """业务模块说明。"""
        pass
    
    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """业务模块说明。"""
        pass
    
    @abstractmethod
    def get_order(self, order_id: str) -> Optional[Order]:
        """业务模块说明。"""
        pass
    
    @abstractmethod
    def get_orders(
        self,
        stock_code: Optional[str] = None,
        status: Optional[OrderStatus] = None,
    ) -> List[Order]:
        """业务模块说明。"""
        pass
    
    @abstractmethod
    def get_quote(self, stock_code: str) -> Optional[Dict]:
        """业务模块说明。"""
        pass
    
    def buy(
        self,
        stock_code: str,
        quantity: int,
        price: Optional[float] = None,
        order_type: OrderType = OrderType.LIMIT,
        **kwargs,
    ) -> Order:
        """业务模块说明。"""
        order = Order(
            order_id=self._generate_order_id(),
            stock_code=stock_code,
            side=OrderSide.BUY,
            order_type=order_type,
            quantity=quantity,
            price=Decimal(str(price)) if price else None,
            **kwargs,
        )
        return self.place_order(order)
    
    def sell(
        self,
        stock_code: str,
        quantity: int,
        price: Optional[float] = None,
        order_type: OrderType = OrderType.LIMIT,
        **kwargs,
    ) -> Order:
        """业务模块说明。"""
        order = Order(
            order_id=self._generate_order_id(),
            stock_code=stock_code,
            side=OrderSide.SELL,
            order_type=order_type,
            quantity=quantity,
            price=Decimal(str(price)) if price else None,
            **kwargs,
        )
        return self.place_order(order)
    
    def _generate_order_id(self) -> str:
        """业务模块说明。"""
        import uuid
        return f"ORD_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"


class RiskManager:
    """业务模块说明。"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.max_single_order_amount = Decimal(
            str(self.config.get("max_single_order_amount", 100000))
        )
        self.max_daily_amount = Decimal(
            str(self.config.get("max_daily_amount", 500000))
        )
        self.max_position_ratio = self.config.get("max_position_ratio", 0.3)
        self.stop_loss_ratio = self.config.get("stop_loss_ratio", 0.08)
        self.take_profit_ratio = self.config.get("take_profit_ratio", 0.15)
        
        self._daily_traded_amount = Decimal("0")
        self._last_reset_date = datetime.now().date()
    
    def check_order(
        self,
        order: Order,
        account: Account,
        positions: List[Position],
    ) -> tuple[bool, str]:
        """业务模块说明。"""
        self._reset_daily_if_needed()
        
        if order.price is None:
            return False, "限价单必须指定价格"
        
        order_amount = order.price * order.quantity
        
        if order_amount > self.max_single_order_amount:
            return False, f"单笔交易金额 {order_amount} 超过限额 {self.max_single_order_amount}"
        
        if self._daily_traded_amount + order_amount > self.max_daily_amount:
            return False, f"当日累计交易金额超过限额 {self.max_daily_amount}"
        
        if order.side == OrderSide.BUY:
            if order_amount > account.available_cash:
                return False, f"可用资金不足，需要 {order_amount}，可用 {account.available_cash}"
            
            existing_position = next(
                (p for p in positions if p.stock_code == order.stock_code), None
            )
            current_value = existing_position.market_value if existing_position else Decimal("0")
            new_value = current_value + order_amount
            
            if account.total_assets > 0:
                new_ratio = float(new_value / account.total_assets)
                if new_ratio > self.max_position_ratio:
                    return False, f"持仓集中度 {new_ratio:.2%} 超过限额 {self.max_position_ratio:.2%}"
        
        return True, "通过风控检查"
    
    def record_trade(self, amount: Decimal) -> None:
        """业务模块说明。"""
        self._reset_daily_if_needed()
        self._daily_traded_amount += amount
    
    def _reset_daily_if_needed(self) -> None:
        """业务模块说明。"""
        today = datetime.now().date()
        if today != self._last_reset_date:
            self._daily_traded_amount = Decimal("0")
            self._last_reset_date = today
    
    def check_stop_loss(self, position: Position) -> bool:
        """业务模块说明。"""
        return position.profit_loss_ratio <= -self.stop_loss_ratio
    
    def check_take_profit(self, position: Position) -> bool:
        """业务模块说明。"""
        return position.profit_loss_ratio >= self.take_profit_ratio
