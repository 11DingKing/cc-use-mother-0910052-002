"""业务模块说明。"""

import pytest
from datetime import datetime, timedelta

from app.chan.models import (
    Bi, Direction, Duan, Fractal, FractalType,
    MergedCandle, Signal, SignalType, Zhongshu,
)
from app.chan.signal_detector import SignalDetector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts(day: int) -> datetime:
    return datetime(2024, 1, 1) + timedelta(days=day)


def _fractal(ftype: FractalType, day: int, price: float, idx: int) -> Fractal:
    return Fractal(type=ftype, timestamp=_ts(day), price=price, candle_index=idx)


def _bi(start_day, start_price, end_day, end_price, direction, candle_count=6, start_idx=0, end_idx=5):
    sf = _fractal(
        FractalType.BOTTOM if direction == Direction.UP else FractalType.TOP,
        start_day, start_price, start_idx,
    )
    ef = _fractal(
        FractalType.TOP if direction == Direction.UP else FractalType.BOTTOM,
        end_day, end_price, end_idx,
    )
    return Bi(
        start_fractal=sf, end_fractal=ef, direction=direction,
        candle_count=candle_count, start_price=start_price, end_price=end_price,
    )


def _make_downtrend_bis_with_divergence():
    """业务模块说明。"""
    bis = [
        _bi(0, 100, 5, 120, Direction.UP, start_idx=0, end_idx=5),
        _bi(5, 120, 10, 90, Direction.DOWN, start_idx=5, end_idx=10),
        _bi(10, 90, 15, 110, Direction.UP, start_idx=10, end_idx=15),
        _bi(15, 110, 20, 85, Direction.DOWN, start_idx=15, end_idx=20),
    ]
    return bis


def _make_uptrend_bis_with_divergence():
    """业务模块说明。"""
    bis = [
        _bi(0, 120, 5, 100, Direction.DOWN, start_idx=0, end_idx=5),
        _bi(5, 100, 10, 130, Direction.UP, start_idx=5, end_idx=10),
        _bi(10, 130, 15, 110, Direction.DOWN, start_idx=10, end_idx=15),
        _bi(15, 110, 20, 135, Direction.UP, start_idx=15, end_idx=20),
    ]
    return bis


# ---------------------------------------------------------------------------
# Tests: Constructor
# ---------------------------------------------------------------------------

class TestSignalDetectorInit:
    def test_init(self):
        sd = SignalDetector("SH600000", "daily")
        assert sd.stock_code == "SH600000"
        assert sd.level == "daily"


# ---------------------------------------------------------------------------
# Tests: Buy 1
# ---------------------------------------------------------------------------

class TestDetectBuy1:
    def test_empty_bi_list(self):
        sd = SignalDetector("TEST", "daily")
        assert sd.detect_buy_1([], []) == []

    def test_too_few_bis(self):
        sd = SignalDetector("TEST", "daily")
        bis = [_bi(0, 100, 5, 90, Direction.DOWN)]
        assert sd.detect_buy_1(bis, []) == []

    def test_divergence_detected_price_mode(self):
        sd = SignalDetector("TEST", "daily")
        bis = _make_downtrend_bis_with_divergence()
        signals = sd.detect_buy_1(bis, [])
        assert len(signals) >= 1
        assert all(s.signal_type == SignalType.BUY_1 for s in signals)

    def test_no_divergence_when_range_increases(self):
        sd = SignalDetector("TEST", "daily")
        bis = [
            _bi(0, 100, 5, 120, Direction.UP, start_idx=0, end_idx=5),
            _bi(5, 120, 10, 95, Direction.DOWN, start_idx=5, end_idx=10),
            _bi(10, 95, 15, 115, Direction.UP, start_idx=10, end_idx=15),
            # Bigger drop than previous -> no divergence
            _bi(15, 115, 20, 60, Direction.DOWN, start_idx=15, end_idx=20),
        ]
        signals = sd.detect_buy_1(bis, [])
        assert len(signals) == 0


# ---------------------------------------------------------------------------
# Tests: Sell 1
# ---------------------------------------------------------------------------

class TestDetectSell1:
    def test_empty_bi_list(self):
        sd = SignalDetector("TEST", "daily")
        assert sd.detect_sell_1([], []) == []

    def test_divergence_detected_price_mode(self):
        sd = SignalDetector("TEST", "daily")
        bis = _make_uptrend_bis_with_divergence()
        signals = sd.detect_sell_1(bis, [])
        assert len(signals) >= 1
        assert all(s.signal_type == SignalType.SELL_1 for s in signals)

    def test_no_divergence_when_range_increases(self):
        sd = SignalDetector("TEST", "daily")
        bis = [
            _bi(0, 120, 5, 100, Direction.DOWN, start_idx=0, end_idx=5),
            _bi(5, 100, 10, 125, Direction.UP, start_idx=5, end_idx=10),
            _bi(10, 125, 15, 105, Direction.DOWN, start_idx=10, end_idx=15),
            # Bigger rise than previous -> no divergence
            _bi(15, 105, 20, 160, Direction.UP, start_idx=15, end_idx=20),
        ]
        signals = sd.detect_sell_1(bis, [])
        assert len(signals) == 0


# ---------------------------------------------------------------------------
# Tests: Buy 2
# ---------------------------------------------------------------------------

class TestDetectBuy2:
    def test_empty_inputs(self):
        sd = SignalDetector("TEST", "daily")
        assert sd.detect_buy_2([], []) == []

    def test_buy_2_after_buy_1(self):
        sd = SignalDetector("TEST", "daily")
        bis = _make_downtrend_bis_with_divergence()
        # Add a pullback bi after the buy_1 that doesn't make new low
        bis.append(_bi(20, 85, 25, 100, Direction.UP, start_idx=20, end_idx=25))
        bis.append(_bi(25, 100, 30, 88, Direction.DOWN, start_idx=25, end_idx=30))

        buy_1_signals = sd.detect_buy_1(bis, [])
        assert len(buy_1_signals) >= 1

        buy_2_signals = sd.detect_buy_2(bis, buy_1_signals)
        assert len(buy_2_signals) >= 1
        assert all(s.signal_type == SignalType.BUY_2 for s in buy_2_signals)

    def test_no_buy_2_when_new_low(self):
        sd = SignalDetector("TEST", "daily")
        bis = _make_downtrend_bis_with_divergence()
        bis.append(_bi(20, 85, 25, 100, Direction.UP, start_idx=20, end_idx=25))
        # Pullback goes below buy_1 price
        bis.append(_bi(25, 100, 30, 80, Direction.DOWN, start_idx=25, end_idx=30))

        buy_1_signals = sd.detect_buy_1(bis, [])
        buy_2_signals = sd.detect_buy_2(bis, buy_1_signals)
        assert len(buy_2_signals) == 0


# ---------------------------------------------------------------------------
# Tests: Sell 2
# ---------------------------------------------------------------------------

class TestDetectSell2:
    def test_empty_inputs(self):
        sd = SignalDetector("TEST", "daily")
        assert sd.detect_sell_2([], []) == []

    def test_sell_2_after_sell_1(self):
        sd = SignalDetector("TEST", "daily")
        bis = _make_uptrend_bis_with_divergence()
        bis.append(_bi(20, 135, 25, 115, Direction.DOWN, start_idx=20, end_idx=25))
        bis.append(_bi(25, 115, 30, 130, Direction.UP, start_idx=25, end_idx=30))

        sell_1_signals = sd.detect_sell_1(bis, [])
        assert len(sell_1_signals) >= 1

        sell_2_signals = sd.detect_sell_2(bis, sell_1_signals)
        assert len(sell_2_signals) >= 1
        assert all(s.signal_type == SignalType.SELL_2 for s in sell_2_signals)


# ---------------------------------------------------------------------------
# Tests: Buy 3
# ---------------------------------------------------------------------------

class TestDetectBuy3:
    def test_empty_inputs(self):
        sd = SignalDetector("TEST", "daily")
        assert sd.detect_buy_3([], []) == []

    def test_buy_3_breakout_pullback_above(self):
        sd = SignalDetector("TEST", "daily")
        # Create zhongshu with high=110, low=100
        zs_bis = [
            _bi(0, 95, 5, 112, Direction.UP, start_idx=0, end_idx=5),
            _bi(5, 112, 10, 98, Direction.DOWN, start_idx=5, end_idx=10),
            _bi(10, 98, 15, 115, Direction.UP, start_idx=10, end_idx=15),
        ]
        zs = Zhongshu(high=110, low=100, start_time=_ts(0), end_time=_ts(15), bi_list=zs_bis)

        # After zhongshu: breakout up then pullback stays above zs_high
        bis = zs_bis + [
            _bi(15, 115, 20, 105, Direction.DOWN, start_idx=15, end_idx=20),
            _bi(20, 105, 25, 125, Direction.UP, start_idx=20, end_idx=25),  # breakout
            _bi(25, 125, 30, 112, Direction.DOWN, start_idx=25, end_idx=30),  # pullback above 110
        ]

        signals = sd.detect_buy_3(bis, [zs])
        assert len(signals) >= 1
        assert all(s.signal_type == SignalType.BUY_3 for s in signals)

    def test_no_buy_3_when_pullback_enters_zhongshu(self):
        sd = SignalDetector("TEST", "daily")
        zs_bis = [
            _bi(0, 95, 5, 112, Direction.UP, start_idx=0, end_idx=5),
            _bi(5, 112, 10, 98, Direction.DOWN, start_idx=5, end_idx=10),
            _bi(10, 98, 15, 115, Direction.UP, start_idx=10, end_idx=15),
        ]
        zs = Zhongshu(high=110, low=100, start_time=_ts(0), end_time=_ts(15), bi_list=zs_bis)

        bis = zs_bis + [
            _bi(15, 115, 20, 105, Direction.DOWN, start_idx=15, end_idx=20),
            _bi(20, 105, 25, 125, Direction.UP, start_idx=20, end_idx=25),
            _bi(25, 125, 30, 105, Direction.DOWN, start_idx=25, end_idx=30),  # enters zhongshu
        ]

        signals = sd.detect_buy_3(bis, [zs])
        assert len(signals) == 0


# ---------------------------------------------------------------------------
# Tests: Sell 3
# ---------------------------------------------------------------------------

class TestDetectSell3:
    def test_empty_inputs(self):
        sd = SignalDetector("TEST", "daily")
        assert sd.detect_sell_3([], []) == []

    def test_sell_3_breakdown_rebound_below(self):
        sd = SignalDetector("TEST", "daily")
        zs_bis = [
            _bi(0, 115, 5, 98, Direction.DOWN, start_idx=0, end_idx=5),
            _bi(5, 98, 10, 112, Direction.UP, start_idx=5, end_idx=10),
            _bi(10, 112, 15, 95, Direction.DOWN, start_idx=10, end_idx=15),
        ]
        zs = Zhongshu(high=110, low=100, start_time=_ts(0), end_time=_ts(15), bi_list=zs_bis)

        bis = zs_bis + [
            _bi(15, 95, 20, 105, Direction.UP, start_idx=15, end_idx=20),
            _bi(20, 105, 25, 90, Direction.DOWN, start_idx=20, end_idx=25),  # breakdown
            _bi(25, 90, 30, 97, Direction.UP, start_idx=25, end_idx=30),  # rebound below 100
        ]

        signals = sd.detect_sell_3(bis, [zs])
        assert len(signals) >= 1
        assert all(s.signal_type == SignalType.SELL_3 for s in signals)


# ---------------------------------------------------------------------------
# Tests: detect_all
# ---------------------------------------------------------------------------

class TestDetectAll:
    def test_empty_inputs(self):
        sd = SignalDetector("TEST", "daily")
        signals = sd.detect_all([], [], [])
        assert signals == []

    def test_detect_all_returns_sorted(self):
        sd = SignalDetector("TEST", "daily")
        bis = _make_downtrend_bis_with_divergence()
        bis.append(_bi(20, 85, 25, 100, Direction.UP, start_idx=20, end_idx=25))
        bis.append(_bi(25, 100, 30, 88, Direction.DOWN, start_idx=25, end_idx=30))

        signals = sd.detect_all(bis, [], [])
        # Verify sorted by timestamp
        for i in range(len(signals) - 1):
            assert signals[i].timestamp <= signals[i + 1].timestamp

    def test_detect_all_includes_multiple_types(self):
        sd = SignalDetector("TEST", "daily")
        bis = _make_downtrend_bis_with_divergence()
        # Extend with pullback for buy_2
        bis.append(_bi(20, 85, 25, 100, Direction.UP, start_idx=20, end_idx=25))
        bis.append(_bi(25, 100, 30, 88, Direction.DOWN, start_idx=25, end_idx=30))

        signals = sd.detect_all(bis, [], [])
        signal_types = {s.signal_type for s in signals}
        # Should have at least buy_1
        assert SignalType.BUY_1 in signal_types


# ---------------------------------------------------------------------------
# Property-Based Tests (Hypothesis)
# Property 10: 第一类买卖点背驰判定
# Property 11: 第二类买卖点条件判定
# Property 12: 第三类买卖点中枢判定
# Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.8
# ---------------------------------------------------------------------------

from hypothesis import given, strategies as st, settings, assume


@st.composite
def fractal_strategy(draw, ftype: FractalType, day: int, idx: int):
    """业务模块说明。"""
    price = draw(st.floats(min_value=10.0, max_value=500.0, allow_nan=False, allow_infinity=False))
    return Fractal(type=ftype, timestamp=_ts(day), price=price, candle_index=idx)


@st.composite
def bi_strategy(draw, start_day: int, start_idx: int, direction: Direction):
    """业务模块说明。"""
    bi_span = draw(st.integers(min_value=5, max_value=10))
    end_day = start_day + bi_span
    end_idx = start_idx + bi_span
    
    start_price = draw(st.floats(min_value=10.0, max_value=500.0, allow_nan=False, allow_infinity=False))
    end_price = draw(st.floats(min_value=10.0, max_value=500.0, allow_nan=False, allow_infinity=False))
    
    return _bi(start_day, start_price, end_day, end_price, direction, 
               candle_count=bi_span, start_idx=start_idx, end_idx=end_idx)


@st.composite
def downtrend_divergence_bis_strategy(draw):
    """业务模块说明。"""
    bis = []
    day = 0
    idx = 0
    
    # First UP bi
    bi_span = draw(st.integers(min_value=5, max_value=8))
    start_price = draw(st.floats(min_value=80.0, max_value=100.0, allow_nan=False, allow_infinity=False))
    up_amount = draw(st.floats(min_value=15.0, max_value=30.0, allow_nan=False, allow_infinity=False))
    end_price = start_price + up_amount
    bis.append(_bi(day, start_price, day + bi_span, end_price, Direction.UP, 
                   candle_count=bi_span, start_idx=idx, end_idx=idx + bi_span))
    day += bi_span
    idx += bi_span
    
    # First DOWN bi (big drop)
    bi_span = draw(st.integers(min_value=5, max_value=8))
    start_price = end_price
    big_drop = draw(st.floats(min_value=30.0, max_value=50.0, allow_nan=False, allow_infinity=False))
    end_price = start_price - big_drop
    first_low = end_price
    first_drop_range = big_drop
    bis.append(_bi(day, start_price, day + bi_span, end_price, Direction.DOWN,
                   candle_count=bi_span, start_idx=idx, end_idx=idx + bi_span))
    day += bi_span
    idx += bi_span
    
    # Second UP bi
    bi_span = draw(st.integers(min_value=5, max_value=8))
    start_price = end_price
    up_amount = draw(st.floats(min_value=15.0, max_value=25.0, allow_nan=False, allow_infinity=False))
    end_price = start_price + up_amount
    second_high = end_price
    bis.append(_bi(day, start_price, day + bi_span, end_price, Direction.UP,
                   candle_count=bi_span, start_idx=idx, end_idx=idx + bi_span))
    day += bi_span
    idx += bi_span
    
    # Second DOWN bi (smaller drop, but makes new low) - creates divergence
    bi_span = draw(st.integers(min_value=5, max_value=8))
    start_price = end_price
    # Small drop ratio: 0.3 to 0.7 of first drop
    small_drop_ratio = draw(st.floats(min_value=0.3, max_value=0.7, allow_nan=False, allow_infinity=False))
    small_drop = first_drop_range * small_drop_ratio
    # But we need to make a new low, so end_price must be below first_low
    # Calculate minimum drop needed to make new low
    min_drop_for_new_low = second_high - first_low + 1.0
    # Use the smaller of the two to ensure divergence (smaller range) AND new low
    actual_drop = max(small_drop, min_drop_for_new_low)
    end_price = start_price - actual_drop
    
    # Ensure we have divergence: actual range should be smaller than first drop
    # If not possible, adjust
    if actual_drop >= first_drop_range:
        # Can't create divergence with new low, skip this case
        # Make the drop smaller but still create new low
        end_price = first_low - draw(st.floats(min_value=1.0, max_value=5.0, allow_nan=False, allow_infinity=False))
    
    bis.append(_bi(day, start_price, day + bi_span, end_price, Direction.DOWN,
                   candle_count=bi_span, start_idx=idx, end_idx=idx + bi_span))
    
    return bis


@st.composite
def uptrend_divergence_bis_strategy(draw):
    """业务模块说明。"""
    bis = []
    day = 0
    idx = 0
    
    # First DOWN bi
    bi_span = draw(st.integers(min_value=5, max_value=8))
    start_price = draw(st.floats(min_value=100.0, max_value=120.0, allow_nan=False, allow_infinity=False))
    down_amount = draw(st.floats(min_value=15.0, max_value=25.0, allow_nan=False, allow_infinity=False))
    end_price = start_price - down_amount
    bis.append(_bi(day, start_price, day + bi_span, end_price, Direction.DOWN,
                   candle_count=bi_span, start_idx=idx, end_idx=idx + bi_span))
    day += bi_span
    idx += bi_span
    
    # First UP bi (big rise)
    bi_span = draw(st.integers(min_value=5, max_value=8))
    start_price = end_price
    big_rise = draw(st.floats(min_value=35.0, max_value=55.0, allow_nan=False, allow_infinity=False))
    end_price = start_price + big_rise
    first_high = end_price
    first_rise_range = big_rise
    bis.append(_bi(day, start_price, day + bi_span, end_price, Direction.UP,
                   candle_count=bi_span, start_idx=idx, end_idx=idx + bi_span))
    day += bi_span
    idx += bi_span
    
    # Second DOWN bi
    bi_span = draw(st.integers(min_value=5, max_value=8))
    start_price = end_price
    down_amount = draw(st.floats(min_value=15.0, max_value=25.0, allow_nan=False, allow_infinity=False))
    end_price = start_price - down_amount
    second_low = end_price
    bis.append(_bi(day, start_price, day + bi_span, end_price, Direction.DOWN,
                   candle_count=bi_span, start_idx=idx, end_idx=idx + bi_span))
    day += bi_span
    idx += bi_span
    
    # Second UP bi (smaller rise, but makes new high) - creates divergence
    bi_span = draw(st.integers(min_value=5, max_value=8))
    start_price = end_price
    # Small rise ratio: 0.3 to 0.7 of first rise
    small_rise_ratio = draw(st.floats(min_value=0.3, max_value=0.7, allow_nan=False, allow_infinity=False))
    small_rise = first_rise_range * small_rise_ratio
    # But we need to make a new high, so end_price must be above first_high
    # Calculate minimum rise needed to make new high
    min_rise_for_new_high = first_high - second_low + 1.0
    # Use the smaller of the two to ensure divergence (smaller range) AND new high
    actual_rise = max(small_rise, min_rise_for_new_high)
    end_price = start_price + actual_rise
    
    # Ensure we have divergence: actual range should be smaller than first rise
    # If not possible, adjust
    if actual_rise >= first_rise_range:
        # Can't create divergence with new high, make the rise smaller but still create new high
        end_price = first_high + draw(st.floats(min_value=1.0, max_value=5.0, allow_nan=False, allow_infinity=False))
    
    bis.append(_bi(day, start_price, day + bi_span, end_price, Direction.UP,
                   candle_count=bi_span, start_idx=idx, end_idx=idx + bi_span))
    
    return bis


class TestBuy1PropertyDivergence:
    """业务模块说明。"""

    @given(downtrend_divergence_bis_strategy())
    @settings(max_examples=100)
    def test_buy_1_detected_on_divergence(self, bis):
        """业务模块说明。"""
        sd = SignalDetector("TEST", "daily")
        signals = sd.detect_buy_1(bis, [])
        
        # Should detect at least one buy_1 signal
        assert len(signals) >= 1, "Should detect Buy 1 on divergence pattern"
        
        for signal in signals:
            assert signal.signal_type == SignalType.BUY_1
            assert signal.stock_code == "TEST"
            assert signal.level == "daily"

    @given(downtrend_divergence_bis_strategy())
    @settings(max_examples=100)
    def test_buy_1_signal_has_valid_details(self, bis):
        """业务模块说明。"""
        sd = SignalDetector("TEST", "daily")
        signals = sd.detect_buy_1(bis, [])
        
        for signal in signals:
            assert "prev_low" in signal.details
            assert "curr_low" in signal.details
            assert "divergence_type" in signal.details
            assert signal.details["divergence_type"] == "bottom"
            # Current low should be lower than previous (new low)
            assert signal.details["curr_low"] < signal.details["prev_low"]

    @given(downtrend_divergence_bis_strategy())
    @settings(max_examples=100)
    def test_buy_1_strength_in_valid_range(self, bis):
        """业务模块说明。"""
        sd = SignalDetector("TEST", "daily")
        signals = sd.detect_buy_1(bis, [])
        
        for signal in signals:
            assert 0.0 <= signal.strength <= 1.0, (
                f"Signal strength {signal.strength} should be in [0, 1]"
            )


class TestSell1PropertyDivergence:
    """业务模块说明。"""

    @given(uptrend_divergence_bis_strategy())
    @settings(max_examples=100)
    def test_sell_1_detected_on_divergence(self, bis):
        """业务模块说明。"""
        sd = SignalDetector("TEST", "daily")
        signals = sd.detect_sell_1(bis, [])
        
        assert len(signals) >= 1, "Should detect Sell 1 on divergence pattern"
        
        for signal in signals:
            assert signal.signal_type == SignalType.SELL_1

    @given(uptrend_divergence_bis_strategy())
    @settings(max_examples=100)
    def test_sell_1_signal_has_valid_details(self, bis):
        """业务模块说明。"""
        sd = SignalDetector("TEST", "daily")
        signals = sd.detect_sell_1(bis, [])
        
        for signal in signals:
            assert "prev_high" in signal.details
            assert "curr_high" in signal.details
            assert "divergence_type" in signal.details
            assert signal.details["divergence_type"] == "top"
            # Current high should be higher than previous (new high)
            assert signal.details["curr_high"] > signal.details["prev_high"]


class TestBuy2PropertyCondition:
    """业务模块说明。"""

    @given(downtrend_divergence_bis_strategy())
    @settings(max_examples=100)
    def test_buy_2_after_buy_1_no_new_low(self, bis):
        """业务模块说明。"""
        sd = SignalDetector("TEST", "daily")
        buy_1_signals = sd.detect_buy_1(bis, [])
        
        if not buy_1_signals:
            return  # Skip if no buy_1 detected
        
        # Add pullback that doesn't make new low
        last_bi = bis[-1]
        buy_1_price = buy_1_signals[0].price
        
        # UP bi after buy_1
        day = last_bi.end_fractal.timestamp.day + 5
        idx = last_bi.end_fractal.candle_index + 5
        up_bi = _bi(day, buy_1_price, day + 5, buy_1_price + 15, Direction.UP,
                    candle_count=5, start_idx=idx, end_idx=idx + 5)
        
        # DOWN bi that stays above buy_1 price
        day += 5
        idx += 5
        pullback_low = buy_1_price + 3  # Above buy_1 price
        down_bi = _bi(day, buy_1_price + 15, day + 5, pullback_low, Direction.DOWN,
                      candle_count=5, start_idx=idx, end_idx=idx + 5)
        
        extended_bis = bis + [up_bi, down_bi]
        buy_2_signals = sd.detect_buy_2(extended_bis, buy_1_signals)
        
        assert len(buy_2_signals) >= 1, "Should detect Buy 2 when pullback doesn't make new low"
        for signal in buy_2_signals:
            assert signal.signal_type == SignalType.BUY_2
            assert signal.details["pullback_low"] > signal.details["buy_1_price"]


class TestBuy3PropertyZhongshu:
    """业务模块说明。"""

    @given(st.floats(min_value=100.0, max_value=120.0, allow_nan=False, allow_infinity=False),
           st.floats(min_value=5.0, max_value=15.0, allow_nan=False, allow_infinity=False))
    @settings(max_examples=100)
    def test_buy_3_breakout_pullback_above_zhongshu(self, zs_low, zs_spread):
        """业务模块说明。"""
        zs_high = zs_low + zs_spread
        
        # Create zhongshu
        zs_bis = [
            _bi(0, zs_low - 5, 5, zs_high + 2, Direction.UP, start_idx=0, end_idx=5),
            _bi(5, zs_high + 2, 10, zs_low - 2, Direction.DOWN, start_idx=5, end_idx=10),
            _bi(10, zs_low - 2, 15, zs_high + 5, Direction.UP, start_idx=10, end_idx=15),
        ]
        zs = Zhongshu(high=zs_high, low=zs_low, start_time=_ts(0), end_time=_ts(15), bi_list=zs_bis)
        
        # Breakout and pullback above zhongshu
        bis = zs_bis + [
            _bi(15, zs_high + 5, 20, zs_low + 5, Direction.DOWN, start_idx=15, end_idx=20),
            _bi(20, zs_low + 5, 25, zs_high + 15, Direction.UP, start_idx=20, end_idx=25),  # breakout
            _bi(25, zs_high + 15, 30, zs_high + 2, Direction.DOWN, start_idx=25, end_idx=30),  # pullback above
        ]
        
        sd = SignalDetector("TEST", "daily")
        signals = sd.detect_buy_3(bis, [zs])
        
        assert len(signals) >= 1, "Should detect Buy 3 on breakout with pullback above zhongshu"
        for signal in signals:
            assert signal.signal_type == SignalType.BUY_3
            assert signal.details["pullback_low"] > signal.details["zhongshu_high"]


class TestSell3PropertyZhongshu:
    """业务模块说明。"""

    @given(st.floats(min_value=100.0, max_value=120.0, allow_nan=False, allow_infinity=False),
           st.floats(min_value=5.0, max_value=15.0, allow_nan=False, allow_infinity=False))
    @settings(max_examples=100)
    def test_sell_3_breakdown_rebound_below_zhongshu(self, zs_low, zs_spread):
        """业务模块说明。"""
        zs_high = zs_low + zs_spread
        
        # Create zhongshu
        zs_bis = [
            _bi(0, zs_high + 5, 5, zs_low - 2, Direction.DOWN, start_idx=0, end_idx=5),
            _bi(5, zs_low - 2, 10, zs_high + 2, Direction.UP, start_idx=5, end_idx=10),
            _bi(10, zs_high + 2, 15, zs_low - 5, Direction.DOWN, start_idx=10, end_idx=15),
        ]
        zs = Zhongshu(high=zs_high, low=zs_low, start_time=_ts(0), end_time=_ts(15), bi_list=zs_bis)
        
        # Breakdown and rebound below zhongshu
        bis = zs_bis + [
            _bi(15, zs_low - 5, 20, zs_high - 5, Direction.UP, start_idx=15, end_idx=20),
            _bi(20, zs_high - 5, 25, zs_low - 15, Direction.DOWN, start_idx=20, end_idx=25),  # breakdown
            _bi(25, zs_low - 15, 30, zs_low - 2, Direction.UP, start_idx=25, end_idx=30),  # rebound below
        ]
        
        sd = SignalDetector("TEST", "daily")
        signals = sd.detect_sell_3(bis, [zs])
        
        assert len(signals) >= 1, "Should detect Sell 3 on breakdown with rebound below zhongshu"
        for signal in signals:
            assert signal.signal_type == SignalType.SELL_3
            assert signal.details["rebound_high"] < signal.details["zhongshu_low"]
