"""业务模块说明。"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any

from app.trading.base import (
    TradingAdapter,
    Order,
    OrderStatus,
    OrderType,
    OrderSide,
    Position,
    Account,
    RiskManager,
)
from app.trading.simulation_adapter import SimulationAdapter
from app.trading.vnpy_adapter import VnpyAdapter
from app.services.analysis_service import AnalysisService
from app.middleware.exception_handler import AppException

logger = logging.getLogger(__name__)


class TradingException(AppException):
    """业务模块说明。"""
    
    def __init__(
        self,
        message: str,
        order_id: Optional[str] = None,
        stock_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            code="TRADING_ERROR",
            status_code=400,
            details={
                "order_id": order_id,
                "stock_code": stock_code,
                **(details or {}),
            },
        )


class TradingService:
    """业务模块说明。"""
    
    def __init__(self, adapter: Optional[TradingAdapter] = None):
        self.adapter = adapter or SimulationAdapter()
        self.risk_manager = RiskManager()
        self.analysis_service = AnalysisService()
        self._auto_trade_enabled = False
    
    def connect(self, adapter_type: str = "simulation", config: Optional[Dict] = None) -> bool:
        """业务模块说明。"""
        if adapter_type == "vnpy":
            self.adapter = VnpyAdapter(config or {})
        else:
            self.adapter = SimulationAdapter(config)
        
        return self.adapter.connect()
    
    def disconnect(self) -> None:
        """业务模块说明。"""
        if self.adapter:
            self.adapter.disconnect()
    
    def get_account(self) -> Dict[str, Any]:
        """业务模块说明。"""
        account = self.adapter.get_account()
        if not account:
            raise TradingException("无法获取账户信息，请检查交易连接")
        return account.to_dict()
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """业务模块说明。"""
        positions = self.adapter.get_positions()
        return [p.to_dict() for p in positions]
    
    def get_position(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """业务模块说明。"""
        position = self.adapter.get_position(stock_code)
        return position.to_dict() if position else None
    
    def buy(
        self,
        stock_code: str,
        quantity: int,
        price: Optional[float] = None,
        order_type: str = "limit",
        signal_type: Optional[str] = None,
        signal_strength: float = 0.0,
        client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """业务模块说明。"""
        # 数量校验
        if quantity <= 0 or quantity % 100 != 0:
            raise TradingException(
                "买入数量必须是100的整数倍",
                stock_code=stock_code,
            )

        # 构建订单
        ot = OrderType.LIMIT if order_type == "limit" else OrderType.MARKET

        if ot == OrderType.LIMIT and price is None:
            raise TradingException("限价单必须指定价格", stock_code=stock_code)

        order = Order(
            order_id=self.adapter._generate_order_id(),
            stock_code=stock_code,
            side=OrderSide.BUY,
            order_type=ot,
            quantity=quantity,
            price=Decimal(str(price)) if price else None,
            signal_type=signal_type,
            signal_strength=signal_strength,
            client_order_id=client_order_id,
        )

        # 风控预检（advisory）；真正的额度承诺由适配器在锁内原子冻结，
        # 因此并发下即使预检与下单之间有竞争，也不会超额冻结
        account = self.adapter.get_account()
        positions = self.adapter.get_positions()

        passed, reason = self.risk_manager.check_order(order, account, positions)
        if not passed:
            raise TradingException(
                f"风控检查未通过: {reason}",
                stock_code=stock_code,
            )

        # 执行下单（确认即冻结；冻结失败会以 REJECTED 返回，账户零变动）
        result = self.adapter.place_order(order)

        if result.status in (OrderStatus.REJECTED, OrderStatus.FAILED):
            raise TradingException(
                f"下单失败: {result.error_message}",
                order_id=result.order_id,
                stock_code=stock_code,
            )

        # 记录交易金额
        if result.status == OrderStatus.FILLED:
            self.risk_manager.record_trade(result.filled_price * result.filled_quantity)

        return result.to_dict()
    
    def sell(
        self,
        stock_code: str,
        quantity: int,
        price: Optional[float] = None,
        order_type: str = "limit",
        signal_type: Optional[str] = None,
        signal_strength: float = 0.0,
        client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """业务模块说明。"""
        # 数量校验（卖出允许零股，不强制 100 整数倍）
        if quantity <= 0:
            raise TradingException(
                "卖出数量必须为正",
                stock_code=stock_code,
            )

        # 构建订单
        ot = OrderType.LIMIT if order_type == "limit" else OrderType.MARKET

        if ot == OrderType.LIMIT and price is None:
            raise TradingException("限价单必须指定价格", stock_code=stock_code)

        order = Order(
            order_id=self.adapter._generate_order_id(),
            stock_code=stock_code,
            side=OrderSide.SELL,
            order_type=ot,
            quantity=quantity,
            price=Decimal(str(price)) if price else None,
            signal_type=signal_type,
            signal_strength=signal_strength,
            client_order_id=client_order_id,
        )

        # 可用持仓的预检仅用于友好报错；真正的占用由适配器在锁内原子
        # 预留，两个并发卖单不会承诺同一批持仓
        position = self.adapter.get_position(stock_code)
        if not position or position.available_quantity < quantity:
            available = position.available_quantity if position else 0
            raise TradingException(
                f"可用持仓不足，需要 {quantity}，可用 {available}",
                stock_code=stock_code,
            )

        # 执行下单（确认即冻结持仓；冻结失败以 REJECTED 返回，零变动）
        result = self.adapter.place_order(order)

        if result.status in (OrderStatus.REJECTED, OrderStatus.FAILED):
            raise TradingException(
                f"下单失败: {result.error_message}",
                order_id=result.order_id,
                stock_code=stock_code,
            )

        return result.to_dict()

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """业务模块说明。"""
        order = self.adapter.get_order(order_id)
        if not order:
            raise TradingException("订单不存在", order_id=order_id)

        if order.status not in (
            OrderStatus.PENDING,
            OrderStatus.SUBMITTED,
            OrderStatus.PARTIAL_FILLED,
        ):
            raise TradingException(
                f"订单状态为 {order.status.value}，无法撤销",
                order_id=order_id,
            )

        success = self.adapter.cancel_order(order_id)
        if not success:
            raise TradingException("撤单失败", order_id=order_id)

        order = self.adapter.get_order(order_id)
        return order.to_dict()

    def apply_fill(
        self,
        order_id: str,
        fill_quantity: Optional[int] = None,
        fill_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """驱动挂起限价单产生（部分）成交，主要用于模拟成交回报 / 测试。"""
        try:
            order = self.adapter.apply_fill(order_id, fill_quantity, fill_price)
        except AttributeError:
            raise TradingException("当前交易适配器不支持手工成交回报", order_id=order_id)
        except Exception as exc:
            raise TradingException(f"成交回报失败: {exc}", order_id=order_id)
        return order.to_dict()

    def recover(self) -> Dict[str, Any]:
        """重连 / 故障恢复后对冻结台账做对账，修平漂移、回收孤儿冻结。"""
        if not hasattr(self.adapter, "recover"):
            return {"supported": False, "repaired": [], "orphans": []}
        report = self.adapter.recover()
        report["supported"] = True
        return report

    def get_freeze_events(self, order_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """查询冻结流水：每笔现金 / 持仓的预留、结算、释放都可追溯。"""
        if not hasattr(self.adapter, "get_freeze_events"):
            return []
        return self.adapter.get_freeze_events(order_id)

    def get_reservations(self) -> List[Dict[str, Any]]:
        """查询当前在途占用（未成交完的买单现金 / 卖单持仓）。"""
        if not hasattr(self.adapter, "get_reservations"):
            return []
        return self.adapter.get_reservations()
    
    def get_order(self, order_id: str) -> Dict[str, Any]:
        """业务模块说明。"""
        order = self.adapter.get_order(order_id)
        if not order:
            raise TradingException("订单不存在", order_id=order_id)
        return order.to_dict()
    
    def get_orders(
        self,
        stock_code: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """业务模块说明。"""
        order_status = OrderStatus(status) if status else None
        orders = self.adapter.get_orders(stock_code, order_status)
        return [o.to_dict() for o in orders]
    
    def get_quote(self, stock_code: str) -> Dict[str, Any]:
        """业务模块说明。"""
        quote = self.adapter.get_quote(stock_code)
        if not quote:
            raise TradingException("无法获取行情数据", stock_code=stock_code)
        return quote
    
    def execute_signal(
        self,
        stock_code: str,
        signal_type: str,
        signal_strength: float,
        price: float,
        position_ratio: float = 0.1,
    ) -> Optional[Dict[str, Any]]:
        """业务模块说明。"""
        if not self._auto_trade_enabled:
            logger.info(f"Auto trade disabled, signal ignored: {signal_type}")
            return None
        
        account = self.adapter.get_account()
        if not account:
            return None
        
        is_buy = signal_type.startswith("BUY")
        
        if is_buy:
            # 计算买入数量
            available = float(account.available_cash)
            buy_amount = available * position_ratio * signal_strength
            quantity = int(buy_amount / price / 100) * 100  # 100股整数倍
            
            if quantity >= 100:
                return self.buy(
                    stock_code=stock_code,
                    quantity=quantity,
                    price=price,
                    order_type="limit",
                    signal_type=signal_type,
                    signal_strength=signal_strength,
                )
        else:
            # 卖出
            position = self.adapter.get_position(stock_code)
            if position and position.available_quantity > 0:
                # 根据信号强度决定卖出比例
                sell_quantity = int(position.available_quantity * signal_strength / 100) * 100
                if sell_quantity >= 100:
                    return self.sell(
                        stock_code=stock_code,
                        quantity=sell_quantity,
                        price=price,
                        order_type="limit",
                        signal_type=signal_type,
                        signal_strength=signal_strength,
                    )
        
        return None
    
    def enable_auto_trade(self, enabled: bool = True) -> None:
        """业务模块说明。"""
        self._auto_trade_enabled = enabled
        logger.info(f"Auto trade {'enabled' if enabled else 'disabled'}")
    
    def check_stop_loss_take_profit(self) -> List[Dict[str, Any]]:
        """业务模块说明。"""
        results = []
        positions = self.adapter.get_positions()
        
        for pos in positions:
            if self.risk_manager.check_stop_loss(pos):
                # 触发止损
                quote = self.adapter.get_quote(pos.stock_code)
                if quote:
                    try:
                        result = self.sell(
                            stock_code=pos.stock_code,
                            quantity=pos.available_quantity,
                            price=quote["bid_price_1"],
                            order_type="limit",
                            signal_type="STOP_LOSS",
                        )
                        result["trigger"] = "stop_loss"
                        results.append(result)
                    except TradingException as e:
                        logger.error(f"Stop loss failed: {e}")
            
            elif self.risk_manager.check_take_profit(pos):
                # 触发止盈
                quote = self.adapter.get_quote(pos.stock_code)
                if quote:
                    try:
                        result = self.sell(
                            stock_code=pos.stock_code,
                            quantity=pos.available_quantity,
                            price=quote["bid_price_1"],
                            order_type="limit",
                            signal_type="TAKE_PROFIT",
                        )
                        result["trigger"] = "take_profit"
                        results.append(result)
                    except TradingException as e:
                        logger.error(f"Take profit failed: {e}")
        
        return results
