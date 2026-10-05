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


class VnpyAdapter(TradingAdapter):
    """业务模块说明。"""
    
    def __init__(self, config: Dict):
        super().__init__(config)
        self.gateway = config.get("gateway", "XTP")
        self._main_engine = None
        self._orders: Dict[str, Order] = {}
        self._positions: Dict[str, Position] = {}
        self._account: Optional[Account] = None
    
    def connect(self) -> bool:
        """业务模块说明。"""
        try:
            # 延迟导入，避免未安装 vnpy 时报错
            from vnpy.event import EventEngine
            from vnpy.trader.engine import MainEngine
            
            self._event_engine = EventEngine()
            self._main_engine = MainEngine(self._event_engine)
            
            # 根据配置加载网关
            gateway_name = self._load_gateway()
            
            if gateway_name:
                # 连接网关
                setting = {
                    "账号": self.config.get("account", ""),
                    "密码": self.config.get("password", ""),
                    "客户号": self.config.get("client_id", "1"),
                    "行情地址": self.config.get("md_address", ""),
                    "交易地址": self.config.get("td_address", ""),
                }
                self._main_engine.connect(setting, gateway_name)
                self._connected = True
                logger.info(f"Connected to {gateway_name}")
                return True
            
            return False
            
        except ImportError:
            logger.warning("VN.py not installed, using simulation mode")
            return self._connect_simulation()
        except Exception as e:
            logger.error(f"VN.py connection error: {e}")
            return False
    
    def _load_gateway(self) -> Optional[str]:
        """业务模块说明。"""
        gateway_map = {
            "XTP": "vnpy_xtp",      # 华泰 XTP
            "CTP": "vnpy_ctp",      # CTP（期货）
            "MINI": "vnpy_mini",    # Mini 接口
        }
        
        module_name = gateway_map.get(self.gateway)
        if not module_name:
            logger.error(f"Unknown gateway: {self.gateway}")
            return None
        
        try:
            import importlib
            module = importlib.import_module(module_name)
            gateway_class = getattr(module, f"{self.gateway.upper()}Gateway")
            self._main_engine.add_gateway(gateway_class)
            return self.gateway.upper()
        except ImportError:
            logger.error(f"Gateway module not installed: {module_name}")
            return None
    
    def _connect_simulation(self) -> bool:
        """业务模块说明。"""
        self._connected = True
        self._account = Account(
            account_id="SIM_001",
            broker="模拟",
            total_assets=Decimal("1000000"),
            available_cash=Decimal("1000000"),
            frozen_cash=Decimal("0"),
            market_value=Decimal("0"),
            profit_loss=Decimal("0"),
            profit_loss_ratio=0.0,
        )
        logger.info("Connected in simulation mode")
        return True
    
    def disconnect(self) -> None:
        """业务模块说明。"""
        if self._main_engine:
            self._main_engine.close()
        self._connected = False
        logger.info("Disconnected")
    
    def get_account(self) -> Optional[Account]:
        """业务模块说明。"""
        if not self._connected:
            return None
        
        if self._main_engine:
            try:
                accounts = self._main_engine.get_all_accounts()
                if accounts:
                    acc = accounts[0]
                    self._account = Account(
                        account_id=acc.accountid,
                        broker=self.gateway,
                        total_assets=Decimal(str(acc.balance)),
                        available_cash=Decimal(str(acc.available)),
                        frozen_cash=Decimal(str(acc.frozen)),
                        market_value=Decimal(str(acc.balance - acc.available - acc.frozen)),
                        profit_loss=Decimal("0"),
                        profit_loss_ratio=0.0,
                    )
            except Exception as e:
                logger.error(f"Get account error: {e}")
        
        return self._account
    
    def get_positions(self) -> List[Position]:
        """业务模块说明。"""
        if not self._connected:
            return []
        
        if self._main_engine:
            try:
                positions = self._main_engine.get_all_positions()
                result = []
                for pos in positions:
                    if pos.volume > 0:
                        p = Position(
                            stock_code=pos.symbol,
                            stock_name=pos.symbol,
                            quantity=int(pos.volume),
                            available_quantity=int(pos.volume - pos.frozen),
                            avg_cost=Decimal(str(pos.price)),
                            current_price=Decimal(str(pos.price)),  # 需要实时行情
                            market_value=Decimal(str(pos.volume * pos.price)),
                            profit_loss=Decimal(str(pos.pnl)),
                            profit_loss_ratio=0.0,
                        )
                        result.append(p)
                        self._positions[pos.symbol] = p
                return result
            except Exception as e:
                logger.error(f"Get positions error: {e}")
        
        return list(self._positions.values())
    
    def get_position(self, stock_code: str) -> Optional[Position]:
        """业务模块说明。"""
        self.get_positions()  # 刷新持仓
        return self._positions.get(stock_code)
    
    def place_order(self, order: Order) -> Order:
        """业务模块说明。"""
        if not self._connected:
            order.status = OrderStatus.FAILED
            order.error_message = "交易连接已断开"
            return order
        
        try:
            if self._main_engine:
                from vnpy.trader.constant import Direction, Offset, OrderType as VnOrderType
                from vnpy.trader.object import OrderRequest
                
                # 转换订单类型
                direction = Direction.LONG if order.side == OrderSide.BUY else Direction.SHORT
                offset = Offset.OPEN if order.side == OrderSide.BUY else Offset.CLOSE
                
                vn_order_type = VnOrderType.LIMIT
                if order.order_type == OrderType.MARKET:
                    vn_order_type = VnOrderType.MARKET
                
                req = OrderRequest(
                    symbol=order.stock_code,
                    exchange=self._get_exchange(order.stock_code),
                    direction=direction,
                    offset=offset,
                    type=vn_order_type,
                    volume=order.quantity,
                    price=float(order.price) if order.price else 0,
                )
                
                vn_order_id = self._main_engine.send_order(req, self.gateway.upper())
                
                if vn_order_id:
                    order.order_id = vn_order_id
                    order.status = OrderStatus.SUBMITTED
                    self._orders[vn_order_id] = order
                    self._emit("on_order", order)
                else:
                    order.status = OrderStatus.REJECTED
                    order.error_message = "下单被拒绝"
            else:
                # 模拟模式
                order.status = OrderStatus.FILLED
                order.filled_quantity = order.quantity
                order.filled_price = order.price
                order.updated_at = datetime.now()
                self._orders[order.order_id] = order
                
                # 更新持仓
                self._update_simulation_position(order)
                self._emit("on_order", order)
                self._emit("on_trade", order)
            
        except Exception as e:
            logger.error(f"Place order error: {e}")
            order.status = OrderStatus.FAILED
            order.error_message = str(e)
        
        return order
    
    def _get_exchange(self, stock_code: str):
        """业务模块说明。"""
        from vnpy.trader.constant import Exchange
        
        if stock_code.startswith(("60", "68")):
            return Exchange.SSE  # 上交所
        elif stock_code.startswith(("00", "30")):
            return Exchange.SZSE  # 深交所
        else:
            return Exchange.SSE
    
    def _update_simulation_position(self, order: Order) -> None:
        """业务模块说明。"""
        if order.stock_code not in self._positions:
            if order.side == OrderSide.BUY:
                self._positions[order.stock_code] = Position(
                    stock_code=order.stock_code,
                    stock_name=order.stock_code,
                    quantity=order.filled_quantity,
                    available_quantity=order.filled_quantity,
                    avg_cost=order.filled_price,
                    current_price=order.filled_price,
                    market_value=order.filled_price * order.filled_quantity,
                    profit_loss=Decimal("0"),
                    profit_loss_ratio=0.0,
                )
        else:
            pos = self._positions[order.stock_code]
            if order.side == OrderSide.BUY:
                total_cost = pos.avg_cost * pos.quantity + order.filled_price * order.filled_quantity
                new_qty = pos.quantity + order.filled_quantity
                pos.quantity = new_qty
                pos.available_quantity = new_qty
                pos.avg_cost = total_cost / new_qty if new_qty > 0 else Decimal("0")
            else:
                pos.quantity -= order.filled_quantity
                pos.available_quantity = pos.quantity
            
            pos.market_value = pos.current_price * pos.quantity
            pos.updated_at = datetime.now()
            
            if pos.quantity <= 0:
                del self._positions[order.stock_code]
        
        # 更新账户
        if self._account:
            if order.side == OrderSide.BUY:
                self._account.available_cash -= order.filled_price * order.filled_quantity
            else:
                self._account.available_cash += order.filled_price * order.filled_quantity
            
            self._account.market_value = sum(
                p.market_value for p in self._positions.values()
            )
            self._account.total_assets = self._account.available_cash + self._account.market_value
            self._account.updated_at = datetime.now()
    
    def cancel_order(self, order_id: str) -> bool:
        """业务模块说明。"""
        if not self._connected:
            return False
        
        try:
            if self._main_engine:
                from vnpy.trader.object import CancelRequest
                
                order = self._orders.get(order_id)
                if not order:
                    return False
                
                req = CancelRequest(
                    orderid=order_id,
                    symbol=order.stock_code,
                    exchange=self._get_exchange(order.stock_code),
                )
                self._main_engine.cancel_order(req, self.gateway.upper())
                
                order.status = OrderStatus.CANCELLED
                order.updated_at = datetime.now()
                self._emit("on_order", order)
                return True
            else:
                # 模拟模式
                order = self._orders.get(order_id)
                if order and order.status == OrderStatus.SUBMITTED:
                    order.status = OrderStatus.CANCELLED
                    order.updated_at = datetime.now()
                    self._emit("on_order", order)
                    return True
                return False
                
        except Exception as e:
            logger.error(f"Cancel order error: {e}")
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
        
        return orders
    
    def get_quote(self, stock_code: str) -> Optional[Dict]:
        """业务模块说明。"""
        if not self._connected:
            return None
        
        try:
            if self._main_engine:
                from vnpy.trader.object import SubscribeRequest
                
                req = SubscribeRequest(
                    symbol=stock_code,
                    exchange=self._get_exchange(stock_code),
                )
                self._main_engine.subscribe(req, self.gateway.upper())
                
                tick = self._main_engine.get_tick(stock_code)
                if tick:
                    return {
                        "stock_code": stock_code,
                        "last_price": tick.last_price,
                        "open": tick.open_price,
                        "high": tick.high_price,
                        "low": tick.low_price,
                        "volume": tick.volume,
                        "bid_price_1": tick.bid_price_1,
                        "ask_price_1": tick.ask_price_1,
                        "bid_volume_1": tick.bid_volume_1,
                        "ask_volume_1": tick.ask_volume_1,
                        "datetime": tick.datetime.isoformat() if tick.datetime else None,
                    }
            else:
                # 模拟数据
                return {
                    "stock_code": stock_code,
                    "last_price": 10.0,
                    "open": 10.0,
                    "high": 10.5,
                    "low": 9.8,
                    "volume": 1000000,
                    "bid_price_1": 9.99,
                    "ask_price_1": 10.01,
                    "bid_volume_1": 1000,
                    "ask_volume_1": 1000,
                    "datetime": datetime.now().isoformat(),
                }
        except Exception as e:
            logger.error(f"Get quote error: {e}")
        
        return None
