"""业务模块说明。"""

import pytest
from datetime import datetime, timedelta
from typing import List

from hypothesis import given, strategies as st, settings, assume

from app.chan.models import RawCandle, Signal, SignalType
from app.backtest.engine import BacktestEngine, BacktestConfig, BacktestResult, Trade


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _candle(day: int, price: float = 100.0, volume: float = 1000.0) -> RawCandle:
    """业务模块说明。"""
    return RawCandle(
        timestamp=datetime(2024, 1, 1) + timedelta(days=day),
        open=price * 0.99,
        high=price * 1.02,
        low=price * 0.98,
        close=price,
        volume=volume,
    )


def _signal(day: int, signal_type: SignalType, price: float = 100.0) -> Signal:
    """业务模块说明。"""
    return Signal(
        stock_code="TEST",
        signal_type=signal_type,
        timestamp=datetime(2024, 1, 1) + timedelta(days=day),
        price=price,
        level="daily",
        strength=0.5,
    )


def _config(days: int = 100) -> BacktestConfig:
    """业务模块说明。"""
    return BacktestConfig(
        stock_code="TEST",
        period="daily",
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 1, 1) + timedelta(days=days),
        initial_capital=100000.0,
        position_size=1.0,
    )


# ---------------------------------------------------------------------------
# Tests: Basic Backtest
# ---------------------------------------------------------------------------

class TestBacktestEngine:
    """业务模块说明。"""
    
    def test_empty_signals(self):
        """业务模块说明。"""
        engine = BacktestEngine()
        config = _config()
        candles = [_candle(i) for i in range(10)]
        
        result = engine.run(config, candles, [])
        
        assert result.total_trades == 0
        assert result.final_capital == config.initial_capital
    
    def test_single_buy_sell(self):
        """业务模块说明。"""
        engine = BacktestEngine()
        config = _config()
        candles = [_candle(i, 100 + i) for i in range(10)]
        signals = [
            _signal(2, SignalType.BUY_1, 102),
            _signal(7, SignalType.SELL_1, 107),
        ]
        
        result = engine.run(config, candles, signals)
        
        assert result.total_trades == 1
        assert result.trades[0].is_closed
        assert result.trades[0].profit > 0  # Price went up
    
    def test_multiple_trades(self):
        """业务模块说明。"""
        engine = BacktestEngine()
        config = _config(30)
        candles = [_candle(i, 100 + (i % 10)) for i in range(30)]
        signals = [
            _signal(2, SignalType.BUY_1),
            _signal(5, SignalType.SELL_1),
            _signal(12, SignalType.BUY_2),
            _signal(18, SignalType.SELL_2),
        ]
        
        result = engine.run(config, candles, signals)
        
        assert result.total_trades == 2
        assert all(t.is_closed for t in result.trades)
    
    def test_unclosed_position(self):
        """业务模块说明。"""
        engine = BacktestEngine()
        config = _config()
        candles = [_candle(i) for i in range(10)]
        signals = [_signal(2, SignalType.BUY_1)]  # No sell signal
        
        result = engine.run(config, candles, signals)
        
        assert result.total_trades == 1
        assert result.trades[0].is_closed  # Should be closed at end
    
    def test_equity_curve(self):
        """业务模块说明。"""
        engine = BacktestEngine()
        config = _config()
        candles = [_candle(i) for i in range(10)]
        signals = []
        
        result = engine.run(config, candles, signals)
        
        assert len(result.equity_curve) == len(candles)
        assert all("equity" in e for e in result.equity_curve)
        assert all("timestamp" in e for e in result.equity_curve)


class TestBacktestStatistics:
    """业务模块说明。"""
    
    def test_win_rate(self):
        """业务模块说明。"""
        engine = BacktestEngine()
        config = _config(50)
        
        # Create candles with known price pattern
        candles = []
        for i in range(50):
            if i < 10:
                price = 100 + i  # Rising
            elif i < 20:
                price = 110 - (i - 10)  # Falling
            elif i < 30:
                price = 100 + (i - 20)  # Rising
            else:
                price = 110 - (i - 30)  # Falling
            candles.append(_candle(i, price))
        
        signals = [
            _signal(2, SignalType.BUY_1),   # Buy at ~102
            _signal(8, SignalType.SELL_1),  # Sell at ~108 (win)
            _signal(22, SignalType.BUY_2),  # Buy at ~102
            _signal(28, SignalType.SELL_2), # Sell at ~108 (win)
        ]
        
        result = engine.run(config, candles, signals)
        
        assert result.total_trades == 2
        assert result.winning_trades >= 0
        assert result.win_rate >= 0
    
    def test_max_drawdown(self):
        """业务模块说明。"""
        engine = BacktestEngine()
        config = _config()
        candles = [_candle(i, 100 - i * 2) for i in range(10)]  # Declining prices
        signals = [_signal(0, SignalType.BUY_1)]
        
        result = engine.run(config, candles, signals)
        
        assert result.max_drawdown >= 0
        assert result.max_drawdown <= 1
    
    def test_sharpe_ratio(self):
        """业务模块说明。"""
        engine = BacktestEngine()
        config = _config()
        candles = [_candle(i, 100 + i * 0.5) for i in range(20)]  # Steady growth
        signals = [_signal(0, SignalType.BUY_1)]
        
        result = engine.run(config, candles, signals)
        
        # Sharpe ratio should be defined
        assert isinstance(result.sharpe_ratio, float)


# ---------------------------------------------------------------------------
# Property-Based Tests (Hypothesis)
# Property 15: 回测交易记录完整性
# Validates: Requirements 8.3
# ---------------------------------------------------------------------------

@st.composite
def candle_series_strategy(draw, min_size: int = 10, max_size: int = 50):
    """业务模块说明。"""
    size = draw(st.integers(min_value=min_size, max_value=max_size))
    base_price = draw(st.floats(min_value=50.0, max_value=200.0, allow_nan=False, allow_infinity=False))
    
    candles = []
    price = base_price
    for i in range(size):
        # Random walk
        change = draw(st.floats(min_value=-0.05, max_value=0.05, allow_nan=False, allow_infinity=False))
        price = price * (1 + change)
        price = max(price, 1.0)  # Ensure positive
        candles.append(_candle(i, price))
    
    return candles


@st.composite
def signal_series_strategy(draw, candle_count: int):
    """业务模块说明。"""
    if candle_count < 4:
        return []
    
    signals = []
    position_open = False
    
    # Generate 0-3 trade pairs
    num_trades = draw(st.integers(min_value=0, max_value=min(3, candle_count // 4)))
    
    used_days = set()
    for _ in range(num_trades):
        # Find available days for buy
        available_buy = [d for d in range(candle_count - 2) if d not in used_days]
        if not available_buy:
            break
        
        buy_day = draw(st.sampled_from(available_buy))
        used_days.add(buy_day)
        
        # Find available days for sell (after buy)
        available_sell = [d for d in range(buy_day + 1, candle_count) if d not in used_days]
        if not available_sell:
            break
        
        sell_day = draw(st.sampled_from(available_sell))
        used_days.add(sell_day)
        
        buy_type = draw(st.sampled_from([SignalType.BUY_1, SignalType.BUY_2, SignalType.BUY_3]))
        sell_type = draw(st.sampled_from([SignalType.SELL_1, SignalType.SELL_2, SignalType.SELL_3]))
        
        signals.append(_signal(buy_day, buy_type))
        signals.append(_signal(sell_day, sell_type))
    
    return sorted(signals, key=lambda s: s.timestamp)


class TestPropertyBacktestCompleteness:
    """业务模块说明。"""
    
    @given(candle_series_strategy())
    @settings(max_examples=50, deadline=None)
    def test_trade_count_matches_signals(self, candles: List[RawCandle]):
        """业务模块说明。"""
        assume(len(candles) >= 10)
        
        engine = BacktestEngine()
        config = BacktestConfig(
            stock_code="TEST",
            period="daily",
            start_date=candles[0].timestamp,
            end_date=candles[-1].timestamp,
            initial_capital=100000.0,
        )
        
        # Generate signals
        signals = []
        if len(candles) >= 4:
            signals.append(_signal(1, SignalType.BUY_1))
            signals.append(_signal(len(candles) - 2, SignalType.SELL_1))
        
        result = engine.run(config, candles, signals)
        
        # Count buy signals
        buy_signals = [s for s in signals if s.signal_type in (
            SignalType.BUY_1, SignalType.BUY_2, SignalType.BUY_3
        )]
        
        # Each buy signal should create a trade
        assert result.total_trades == len(buy_signals), (
            f"Expected {len(buy_signals)} trades, got {result.total_trades}"
        )
    
    @given(candle_series_strategy(min_size=20, max_size=50))
    @settings(max_examples=50, deadline=None)
    def test_all_trades_have_entry_info(self, candles: List[RawCandle]):
        """业务模块说明。"""
        engine = BacktestEngine()
        config = BacktestConfig(
            stock_code="TEST",
            period="daily",
            start_date=candles[0].timestamp,
            end_date=candles[-1].timestamp,
            initial_capital=100000.0,
        )
        
        signals = [
            _signal(2, SignalType.BUY_1),
            _signal(10, SignalType.SELL_1),
        ]
        
        result = engine.run(config, candles, signals)
        
        for trade in result.trades:
            assert trade.entry_time is not None
            assert trade.entry_price > 0
            assert trade.entry_signal is not None
            assert trade.shares > 0
    
    @given(candle_series_strategy(min_size=20, max_size=50))
    @settings(max_examples=50, deadline=None)
    def test_closed_trades_have_exit_info(self, candles: List[RawCandle]):
        """业务模块说明。"""
        engine = BacktestEngine()
        config = BacktestConfig(
            stock_code="TEST",
            period="daily",
            start_date=candles[0].timestamp,
            end_date=candles[-1].timestamp,
            initial_capital=100000.0,
        )
        
        signals = [
            _signal(2, SignalType.BUY_1),
            _signal(10, SignalType.SELL_1),
        ]
        
        result = engine.run(config, candles, signals)
        
        for trade in result.trades:
            if trade.is_closed:
                assert trade.exit_time is not None
                assert trade.exit_price > 0
    
    @given(candle_series_strategy())
    @settings(max_examples=50, deadline=None)
    def test_capital_conservation(self, candles: List[RawCandle]):
        """业务模块说明。"""
        assume(len(candles) >= 5)
        
        engine = BacktestEngine()
        config = BacktestConfig(
            stock_code="TEST",
            period="daily",
            start_date=candles[0].timestamp,
            end_date=candles[-1].timestamp,
            initial_capital=100000.0,
        )
        
        # No signals = no trades = capital unchanged
        result = engine.run(config, candles, [])
        
        assert result.final_capital == config.initial_capital, (
            f"Capital changed without trades: {config.initial_capital} -> {result.final_capital}"
        )
    
    @given(candle_series_strategy())
    @settings(max_examples=50, deadline=None)
    def test_equity_curve_length_matches_candles(self, candles: List[RawCandle]):
        """业务模块说明。"""
        engine = BacktestEngine()
        config = BacktestConfig(
            stock_code="TEST",
            period="daily",
            start_date=candles[0].timestamp,
            end_date=candles[-1].timestamp,
            initial_capital=100000.0,
        )
        
        result = engine.run(config, candles, [])
        
        assert len(result.equity_curve) == len(candles), (
            f"Equity curve length {len(result.equity_curve)} != candles {len(candles)}"
        )
