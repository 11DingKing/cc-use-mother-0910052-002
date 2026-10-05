"""业务模块说明。"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
import logging
import statistics

from app.chan.models import Signal, SignalType, RawCandle

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    """业务模块说明。"""
    entry_time: datetime
    entry_price: float
    entry_signal: SignalType
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_signal: Optional[SignalType] = None
    shares: float = 0.0
    profit: float = 0.0
    profit_pct: float = 0.0
    is_closed: bool = False


@dataclass
class BacktestConfig:
    """业务模块说明。"""
    stock_code: str
    period: str
    start_date: datetime
    end_date: datetime
    initial_capital: float = 100000.0
    position_size: float = 1.0  # 仓位比例 0-1
    commission_rate: float = 0.001  # 手续费率
    slippage: float = 0.001  # 滑点


@dataclass
class BacktestResult:
    """业务模块说明。"""
    config: BacktestConfig
    trades: List[Trade] = field(default_factory=list)
    equity_curve: List[Dict[str, Any]] = field(default_factory=list)
    
    # 统计指标
    final_capital: float = 0.0
    total_return: float = 0.0
    annual_return: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_loss_ratio: float = 0.0
    sharpe_ratio: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0


class BacktestStatistics:
    """业务模块说明。"""
    
    @classmethod
    def calculate(
        cls,
        config: BacktestConfig,
        trades: List[Trade],
        equity_curve: List[Dict[str, Any]],
        final_capital: float,
    ) -> BacktestResult:
        """业务模块说明。"""
        result = BacktestResult(config=config)
        result.trades = trades
        result.equity_curve = equity_curve
        
        result.final_capital = final_capital
        result.total_return = (final_capital - config.initial_capital) / config.initial_capital
        result.total_trades = len(trades)
        
        closed_trades = [t for t in trades if t.is_closed]
        if closed_trades:
            result.winning_trades = sum(1 for t in closed_trades if t.profit > 0)
            result.losing_trades = sum(1 for t in closed_trades if t.profit <= 0)
            result.win_rate = result.winning_trades / len(closed_trades)
            
            avg_win = sum(t.profit for t in closed_trades if t.profit > 0) / max(result.winning_trades, 1)
            avg_loss = abs(sum(t.profit for t in closed_trades if t.profit <= 0)) / max(result.losing_trades, 1)
            result.profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0
        
        if equity_curve:
            equities = [e["equity"] for e in equity_curve]
            result.max_drawdown = cls._calculate_max_drawdown(equities)
        
        if config.start_date and config.end_date:
            days = (config.end_date - config.start_date).days
            if days > 0:
                result.annual_return = (1 + result.total_return) ** (365 / days) - 1
        
        if equity_curve and len(equity_curve) > 1:
            returns = []
            for i in range(1, len(equity_curve)):
                prev = equity_curve[i-1]["equity"]
                curr = equity_curve[i]["equity"]
                if prev > 0:
                    returns.append((curr - prev) / prev)
            
            if returns:
                avg_return = statistics.mean(returns)
                std_return = statistics.stdev(returns) if len(returns) > 1 else 0
                risk_free_rate = 0.03 / 252
                if std_return > 0:
                    result.sharpe_ratio = (avg_return - risk_free_rate) / std_return * (252 ** 0.5)
        
        return result
    
    @staticmethod
    def _calculate_max_drawdown(equities: List[float]) -> float:
        """业务模块说明。"""
        if not equities:
            return 0.0
        
        max_equity = equities[0]
        max_drawdown = 0.0
        
        for equity in equities:
            if equity > max_equity:
                max_equity = equity
            drawdown = (max_equity - equity) / max_equity if max_equity > 0 else 0
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        return max_drawdown


class BacktestEngine:
    """业务模块说明。"""
    
    def __init__(self):
        self.position = 0.0
        self.capital = 0.0
        self.trades: List[Trade] = []
        self.equity_curve: List[Dict[str, Any]] = []
    
    def run(
        self,
        config: BacktestConfig,
        candles: List[RawCandle],
        signals: List[Signal],
    ) -> BacktestResult:
        """业务模块说明。"""
        self.position = 0.0
        self.capital = config.initial_capital
        self.trades = []
        self.equity_curve = []
        
        candles = sorted(candles, key=lambda x: x.timestamp)
        signals = sorted(signals, key=lambda x: x.timestamp)
        
        signal_map = {}
        for s in signals:
            date_key = s.timestamp.strftime("%Y-%m-%d")
            signal_map[date_key] = s
        
        logger.info(f"Backtest signals: {len(signals)}, signal_dates: {list(signal_map.keys())}")
        
        current_trade: Optional[Trade] = None
        
        for candle in candles:
            candle_date = candle.timestamp.strftime("%Y-%m-%d")
            signal = signal_map.get(candle_date)
            
            if signal:
                if signal.signal_type in (SignalType.BUY_1, SignalType.BUY_2, SignalType.BUY_3):
                    if self.position == 0:
                        current_trade = self._open_position(
                            config, candle, signal.signal_type
                        )
                
                elif signal.signal_type in (SignalType.SELL_1, SignalType.SELL_2, SignalType.SELL_3):
                    if self.position > 0 and current_trade:
                        self._close_position(
                            config, candle, signal.signal_type, current_trade
                        )
                        current_trade = None
            
            equity = self.capital + self.position * candle.close
            self.equity_curve.append({
                "timestamp": candle.timestamp.isoformat(),
                "equity": equity,
                "position": self.position,
                "price": candle.close,
            })
        
        if self.position > 0 and current_trade and candles:
            self._close_position(
                config, candles[-1], None, current_trade
            )
        
        result = BacktestStatistics.calculate(
            config=config,
            trades=self.trades,
            equity_curve=self.equity_curve,
            final_capital=self.capital,
        )
        
        return result
    
    def _open_position(
        self,
        config: BacktestConfig,
        candle: RawCandle,
        signal_type: SignalType,
    ) -> Trade:
        """业务模块说明。"""
        price = candle.close * (1 + config.slippage)
        
        available = self.capital * config.position_size
        commission = available * config.commission_rate
        shares = (available - commission) / price
        
        cost = shares * price + commission
        self.capital -= cost
        self.position = shares
        
        trade = Trade(
            entry_time=candle.timestamp,
            entry_price=price,
            entry_signal=signal_type,
            shares=shares,
        )
        self.trades.append(trade)
        
        logger.debug(f"Open position: {shares:.2f} shares at {price:.2f}")
        
        return trade
    
    def _close_position(
        self,
        config: BacktestConfig,
        candle: RawCandle,
        signal_type: Optional[SignalType],
        trade: Trade,
    ) -> None:
        """业务模块说明。"""
        price = candle.close * (1 - config.slippage)
        
        revenue = self.position * price
        commission = revenue * config.commission_rate
        net_revenue = revenue - commission
        
        cost = trade.shares * trade.entry_price
        profit = net_revenue - cost
        profit_pct = profit / cost if cost > 0 else 0
        
        trade.exit_time = candle.timestamp
        trade.exit_price = price
        trade.exit_signal = signal_type
        trade.profit = profit
        trade.profit_pct = profit_pct
        trade.is_closed = True
        
        self.capital += net_revenue
        self.position = 0.0
        
        logger.debug(f"Close position: {trade.shares:.2f} shares at {price:.2f}, profit: {profit:.2f}")
