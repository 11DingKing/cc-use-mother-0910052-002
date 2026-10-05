"""业务模块说明。"""

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
        self._pending_orders: List[Order] = []
        
        # 交易成本配置
        self.commission_rate = Decimal(str(config.get("commission_rate", 0.0003))) if config else Decimal("0.0003")
        self.min_commission = Decimal(str(config.get("min_commission", 5))) if config else Decimal("5")
        self.stamp_tax_rate = Decimal(str(config.get("stamp_tax_rate", 0.001))) if config else Decimal("0.001")
        self.slippage_rate = config.get("slippage_rate", 0.001) if config else 0.001
        self.default_quote_price = Decimal(
            str(config.get("default_quote_price", 10)) if config else "10"
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
        return list(self._positions.values())
    
    def get_position(self, stock_code: str) -> Optional[Position]:
        """业务模块说明。"""
        return self._positions.get(stock_code)
    
    def place_order(self, order: Order) -> Order:
        """业务模块说明。"""
        if not self._connected:
            order.status = OrderStatus.FAILED
            order.error_message = "交易连接已断开"
            return order
        
        # 获取行情
        quote = self.get_quote(order.stock_code)
        if not quote:
            order.status = OrderStatus.REJECTED
            order.error_message = "无法获取行情数据"
            return order
        
        current_price = Decimal(str(quote["last_price"]))
        
        # 资金/持仓检查
        if order.side == OrderSide.BUY:
            required_amount = (order.price or current_price) * order.quantity
            if required_amount > self._account.available_cash:
                order.status = OrderStatus.REJECTED
                order.error_message = f"可用资金不足，需要 {required_amount:.2f}，可用 {self._account.available_cash:.2f}"
                return order
        else:
            position = self._positions.get(order.stock_code)
            if not position or position.available_quantity < order.quantity:
                order.status = OrderStatus.REJECTED
                order.error_message = f"可用持仓不足，需要 {order.quantity}，可用 {position.available_quantity if position else 0}"
                return order
        
        order.status = OrderStatus.SUBMITTED
        order.updated_at = datetime.now()
        self._orders[order.order_id] = order
        
        # 尝试撮合
        self._try_fill_order(order, current_price)
        
        self._emit("on_order", order)
        return order
    
    def _try_fill_order(self, order: Order, current_price: Decimal) -> None:
        """业务模块说明。"""
        fill_price = None
        
        if order.order_type == OrderType.MARKET:
            # 市价单立即成交，加入滑点
            slippage = current_price * Decimal(str(self.slippage_rate))
            if order.side == OrderSide.BUY:
                fill_price = current_price + slippage
            else:
                fill_price = current_price - slippage
        
        elif order.order_type == OrderType.LIMIT:
            # 限价单检查是否可成交
            if order.side == OrderSide.BUY:
                if current_price <= order.price:
                    fill_price = order.price
            else:
                if current_price >= order.price:
                    fill_price = order.price
        
        if fill_price:
            self._execute_fill(order, fill_price)
    
    def _execute_fill(self, order: Order, fill_price: Decimal) -> None:
        """业务模块说明。"""
        order.status = OrderStatus.FILLED
        order.filled_quantity = order.quantity
        order.filled_price = fill_price
        order.updated_at = datetime.now()
        
        # 计算手续费
        trade_amount = fill_price * order.quantity
        commission = max(trade_amount * self.commission_rate, self.min_commission)
        
        # 卖出加收印花税
        if order.side == OrderSide.SELL:
            commission += trade_amount * self.stamp_tax_rate
        
        order.commission = commission
        
        # 更新持仓
        self._update_position(order)
        
        # 更新账户
        self._update_account(order)
        
        self._emit("on_trade", order)
        logger.info(
            f"Order filled: {order.order_id} {order.side.value} "
            f"{order.stock_code} {order.quantity}@{fill_price}"
        )
    
    def _update_position(self, order: Order) -> None:
        """业务模块说明。"""
        stock_code = order.stock_code
        
        if order.side == OrderSide.BUY:
            if stock_code in self._positions:
                pos = self._positions[stock_code]
                total_cost = pos.avg_cost * pos.quantity + order.filled_price * order.filled_quantity
                new_qty = pos.quantity + order.filled_quantity
                pos.avg_cost = total_cost / new_qty
                pos.quantity = new_qty
                pos.available_quantity = new_qty
            else:
                self._positions[stock_code] = Position(
                    stock_code=stock_code,
                    stock_name=stock_code,
                    quantity=order.filled_quantity,
                    available_quantity=order.filled_quantity,
                    avg_cost=order.filled_price,
                    current_price=order.filled_price,
                    market_value=order.filled_price * order.filled_quantity,
                    profit_loss=Decimal("0"),
                    profit_loss_ratio=0.0,
                )
        else:
            pos = self._positions[stock_code]
            pos.quantity -= order.filled_quantity
            pos.available_quantity = pos.quantity
            
            if pos.quantity <= 0:
                del self._positions[stock_code]
        
        # 更新持仓市值和盈亏
        for pos in self._positions.values():
            pos.market_value = pos.current_price * pos.quantity
            if pos.avg_cost > 0:
                pos.profit_loss = (pos.current_price - pos.avg_cost) * pos.quantity
                pos.profit_loss_ratio = float((pos.current_price - pos.avg_cost) / pos.avg_cost)
            pos.updated_at = datetime.now()
    
    def _update_account(self, order: Order) -> None:
        """业务模块说明。"""
        trade_amount = order.filled_price * order.filled_quantity
        
        if order.side == OrderSide.BUY:
            self._account.available_cash -= trade_amount + order.commission
        else:
            self._account.available_cash += trade_amount - order.commission
        
        self._account.market_value = sum(p.market_value for p in self._positions.values())
        self._account.total_assets = self._account.available_cash + self._account.market_value
        self._account.profit_loss = sum(p.profit_loss for p in self._positions.values())
        
        if self._account.total_assets > 0:
            self._account.profit_loss_ratio = float(
                self._account.profit_loss / (self._account.total_assets - self._account.profit_loss)
            )
        
        self._account.updated_at = datetime.now()
    
    def cancel_order(self, order_id: str) -> bool:
        """业务模块说明。"""
        order = self._orders.get(order_id)
        if not order:
            return False
        
        if order.status in (OrderStatus.SUBMITTED, OrderStatus.PENDING):
            order.status = OrderStatus.CANCELLED
            order.updated_at = datetime.now()
            self._emit("on_order", order)
            return True
        
        return False
    
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
            self._positions[stock_code].current_price = Decimal(str(quote["last_price"]))
            self._update_position_pnl(stock_code)
        
        return quote
    
    def _update_position_pnl(self, stock_code: str) -> None:
        """业务模块说明。"""
        pos = self._positions.get(stock_code)
        if pos:
            pos.market_value = pos.current_price * pos.quantity
            if pos.avg_cost > 0:
                pos.profit_loss = (pos.current_price - pos.avg_cost) * pos.quantity
                pos.profit_loss_ratio = float((pos.current_price - pos.avg_cost) / pos.avg_cost)
            pos.updated_at = datetime.now()
    
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
