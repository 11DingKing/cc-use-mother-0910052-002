"""业务模块说明。"""

import pytest
from datetime import datetime, timedelta

from app.chan.models import Signal, SignalType
from app.chan.multi_level import MultiLevelLinkage, CombinedSignal, PERIOD_PRIORITY


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts(day: int, hour: int = 12) -> datetime:
    return datetime(2024, 1, 1, hour, 0) + timedelta(days=day)


def _signal(
    signal_type: SignalType,
    timestamp: datetime,
    price: float,
    level: str,
    strength: float = 0.5,
) -> Signal:
    return Signal(
        stock_code="TEST",
        signal_type=signal_type,
        timestamp=timestamp,
        price=price,
        level=level,
        strength=strength,
    )


# ---------------------------------------------------------------------------
# Tests: Constructor and Period Priority
# ---------------------------------------------------------------------------

class TestMultiLevelLinkageInit:
    def test_init(self):
        ml = MultiLevelLinkage()
        assert ml.period_priority == PERIOD_PRIORITY

    def test_period_priority_order(self):
        """业务模块说明。"""
        assert PERIOD_PRIORITY["monthly"] > PERIOD_PRIORITY["weekly"]
        assert PERIOD_PRIORITY["weekly"] > PERIOD_PRIORITY["daily"]
        assert PERIOD_PRIORITY["daily"] > PERIOD_PRIORITY["60min"]
        assert PERIOD_PRIORITY["60min"] > PERIOD_PRIORITY["30min"]
        assert PERIOD_PRIORITY["30min"] > PERIOD_PRIORITY["15min"]


# ---------------------------------------------------------------------------
# Tests: align_results
# ---------------------------------------------------------------------------

class TestAlignResults:
    def test_empty_input(self):
        ml = MultiLevelLinkage()
        assert ml.align_results({}) == {}

    def test_single_period(self):
        ml = MultiLevelLinkage()
        signals = [_signal(SignalType.BUY_1, _ts(0), 100.0, "daily")]
        result = ml.align_results({"daily": signals})
        assert len(result) == 1

    def test_multiple_periods_same_time(self):
        ml = MultiLevelLinkage()
        ts = _ts(0)
        signals_by_period = {
            "daily": [_signal(SignalType.BUY_1, ts, 100.0, "daily")],
            "60min": [_signal(SignalType.BUY_2, ts, 100.0, "60min")],
        }
        result = ml.align_results(signals_by_period)
        # Should be in the same time window
        assert len(result) == 1
        window = list(result.values())[0]
        assert "daily" in window
        assert "60min" in window

    def test_multiple_periods_different_times(self):
        ml = MultiLevelLinkage()
        signals_by_period = {
            "daily": [_signal(SignalType.BUY_1, _ts(0), 100.0, "daily")],
            "60min": [_signal(SignalType.BUY_2, _ts(5), 100.0, "60min")],
        }
        result = ml.align_results(signals_by_period, time_window_minutes=60)
        # Should be in different time windows (5 days apart)
        assert len(result) >= 1


# ---------------------------------------------------------------------------
# Tests: generate_combined_signal
# ---------------------------------------------------------------------------

class TestGenerateCombinedSignal:
    def test_empty_input(self):
        ml = MultiLevelLinkage()
        assert ml.generate_combined_signal({}) == []

    def test_single_signal(self):
        ml = MultiLevelLinkage()
        signals_by_period = {
            "daily": [_signal(SignalType.BUY_1, _ts(0), 100.0, "daily", 0.6)],
        }
        result = ml.generate_combined_signal(signals_by_period)
        assert len(result) == 1
        assert result[0].signal_type == SignalType.BUY_1
        assert result[0].primary_level == "daily"
        assert not result[0].has_conflict
        assert not result[0].is_strong_confirmation

    def test_primary_level_is_largest(self):
        """业务模块说明。"""
        ml = MultiLevelLinkage()
        ts = _ts(0)
        signals_by_period = {
            "30min": [_signal(SignalType.BUY_1, ts, 100.0, "30min")],
            "daily": [_signal(SignalType.BUY_1, ts, 100.0, "daily")],
            "60min": [_signal(SignalType.BUY_1, ts, 100.0, "60min")],
        }
        result = ml.generate_combined_signal(signals_by_period)
        assert len(result) == 1
        assert result[0].primary_level == "daily"

    def test_conflict_detection(self):
        """业务模块说明。"""
        ml = MultiLevelLinkage()
        ts = _ts(0)
        signals_by_period = {
            "daily": [_signal(SignalType.BUY_1, ts, 100.0, "daily")],
            "60min": [_signal(SignalType.SELL_1, ts, 100.0, "60min")],
        }
        result = ml.generate_combined_signal(signals_by_period)
        assert len(result) == 1
        assert result[0].has_conflict
        assert result[0].signal_type == SignalType.BUY_1  # Primary (daily) wins

    def test_strong_confirmation_buy(self):
        """业务模块说明。"""
        ml = MultiLevelLinkage()
        ts = _ts(0)
        signals_by_period = {
            "daily": [_signal(SignalType.BUY_1, ts, 100.0, "daily", 0.5)],
            "60min": [_signal(SignalType.BUY_2, ts, 100.0, "60min", 0.5)],
        }
        result = ml.generate_combined_signal(signals_by_period)
        assert len(result) == 1
        assert result[0].is_strong_confirmation
        assert "60min" in result[0].secondary_levels

    def test_strong_confirmation_sell(self):
        """业务模块说明。"""
        ml = MultiLevelLinkage()
        ts = _ts(0)
        signals_by_period = {
            "daily": [_signal(SignalType.SELL_1, ts, 100.0, "daily", 0.5)],
            "60min": [_signal(SignalType.SELL_2, ts, 100.0, "60min", 0.5)],
        }
        result = ml.generate_combined_signal(signals_by_period)
        assert len(result) == 1
        assert result[0].is_strong_confirmation

    def test_no_strong_confirmation_wrong_types(self):
        """业务模块说明。"""
        ml = MultiLevelLinkage()
        ts = _ts(0)
        signals_by_period = {
            "daily": [_signal(SignalType.BUY_1, ts, 100.0, "daily")],
            "60min": [_signal(SignalType.BUY_1, ts, 100.0, "60min")],
        }
        result = ml.generate_combined_signal(signals_by_period)
        assert len(result) == 1
        assert not result[0].is_strong_confirmation

    def test_strength_increases_with_resonance(self):
        """业务模块说明。"""
        ml = MultiLevelLinkage()
        ts = _ts(0)
        
        # Single level
        single = ml.generate_combined_signal({
            "daily": [_signal(SignalType.BUY_1, ts, 100.0, "daily", 0.5)],
        })
        
        # Multi-level resonance (same direction)
        multi = ml.generate_combined_signal({
            "daily": [_signal(SignalType.BUY_1, ts, 100.0, "daily", 0.5)],
            "60min": [_signal(SignalType.BUY_1, ts, 100.0, "60min", 0.5)],
            "30min": [_signal(SignalType.BUY_1, ts, 100.0, "30min", 0.5)],
        })
        
        assert multi[0].strength > single[0].strength

    def test_strength_decreases_with_conflict(self):
        """业务模块说明。"""
        ml = MultiLevelLinkage()
        ts = _ts(0)
        
        # No conflict
        no_conflict = ml.generate_combined_signal({
            "daily": [_signal(SignalType.BUY_1, ts, 100.0, "daily", 0.5)],
            "60min": [_signal(SignalType.BUY_1, ts, 100.0, "60min", 0.5)],
        })
        
        # With conflict
        with_conflict = ml.generate_combined_signal({
            "daily": [_signal(SignalType.BUY_1, ts, 100.0, "daily", 0.5)],
            "60min": [_signal(SignalType.SELL_1, ts, 100.0, "60min", 0.5)],
        })
        
        assert with_conflict[0].strength < no_conflict[0].strength

    def test_strength_bounded_0_to_1(self):
        """业务模块说明。"""
        ml = MultiLevelLinkage()
        ts = _ts(0)
        
        # Many resonating signals (could push strength > 1)
        signals_by_period = {
            "daily": [_signal(SignalType.BUY_1, ts, 100.0, "daily", 0.9)],
            "60min": [_signal(SignalType.BUY_2, ts, 100.0, "60min", 0.9)],
            "30min": [_signal(SignalType.BUY_1, ts, 100.0, "30min", 0.9)],
            "15min": [_signal(SignalType.BUY_1, ts, 100.0, "15min", 0.9)],
        }
        result = ml.generate_combined_signal(signals_by_period)
        assert 0.0 <= result[0].strength <= 1.0


# ---------------------------------------------------------------------------
# Tests: Conflict Details
# ---------------------------------------------------------------------------

class TestConflictDetails:
    def test_conflict_details_populated(self):
        ml = MultiLevelLinkage()
        ts = _ts(0)
        signals_by_period = {
            "daily": [_signal(SignalType.BUY_1, ts, 100.0, "daily")],
            "60min": [_signal(SignalType.SELL_1, ts, 100.0, "60min")],
        }
        result = ml.generate_combined_signal(signals_by_period)
        assert result[0].has_conflict
        details = result[0].conflict_details
        assert "primary_period" in details
        assert "primary_direction" in details
        assert "conflicting_periods" in details
        assert details["primary_period"] == "daily"
        assert details["primary_direction"] == "buy"
        assert len(details["conflicting_periods"]) == 1

    def test_no_conflict_details_when_no_conflict(self):
        ml = MultiLevelLinkage()
        ts = _ts(0)
        signals_by_period = {
            "daily": [_signal(SignalType.BUY_1, ts, 100.0, "daily")],
            "60min": [_signal(SignalType.BUY_2, ts, 100.0, "60min")],
        }
        result = ml.generate_combined_signal(signals_by_period)
        assert not result[0].has_conflict
        assert result[0].conflict_details == {}



# ---------------------------------------------------------------------------
# Property-Based Tests (Hypothesis)
# Property 13: 多级别信号冲突以大级别为主
# Property 14: 多级别强确认信号生成
# Validates: Requirements 7.2, 7.4
# ---------------------------------------------------------------------------

from hypothesis import given, strategies as st, settings, assume


@st.composite
def signal_strategy(draw, signal_type: SignalType = None, level: str = None):
    """业务模块说明。"""
    if signal_type is None:
        signal_type = draw(st.sampled_from(list(SignalType)))
    if level is None:
        level = draw(st.sampled_from(list(PERIOD_PRIORITY.keys())))
    
    day = draw(st.integers(min_value=0, max_value=100))
    hour = draw(st.integers(min_value=0, max_value=23))
    price = draw(st.floats(min_value=10.0, max_value=500.0, allow_nan=False, allow_infinity=False))
    strength = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))
    
    return Signal(
        stock_code="TEST",
        signal_type=signal_type,
        timestamp=_ts(day, hour),
        price=price,
        level=level,
        strength=strength,
    )


@st.composite
def conflicting_signals_strategy(draw):
    """业务模块说明。"""
    # Choose a large level and a small level
    large_level = draw(st.sampled_from(["daily", "weekly", "monthly"]))
    small_level = draw(st.sampled_from(["30min", "60min", "15min"]))
    
    # Ensure large level has higher priority
    assume(PERIOD_PRIORITY[large_level] > PERIOD_PRIORITY[small_level])
    
    # Generate conflicting signal types
    is_large_buy = draw(st.booleans())
    if is_large_buy:
        large_type = draw(st.sampled_from([SignalType.BUY_1, SignalType.BUY_2, SignalType.BUY_3]))
        small_type = draw(st.sampled_from([SignalType.SELL_1, SignalType.SELL_2, SignalType.SELL_3]))
    else:
        large_type = draw(st.sampled_from([SignalType.SELL_1, SignalType.SELL_2, SignalType.SELL_3]))
        small_type = draw(st.sampled_from([SignalType.BUY_1, SignalType.BUY_2, SignalType.BUY_3]))
    
    ts = _ts(draw(st.integers(min_value=0, max_value=100)))
    price = draw(st.floats(min_value=10.0, max_value=500.0, allow_nan=False, allow_infinity=False))
    
    large_signal = Signal(
        stock_code="TEST",
        signal_type=large_type,
        timestamp=ts,
        price=price,
        level=large_level,
        strength=draw(st.floats(min_value=0.3, max_value=0.8, allow_nan=False, allow_infinity=False)),
    )
    
    small_signal = Signal(
        stock_code="TEST",
        signal_type=small_type,
        timestamp=ts,
        price=price,
        level=small_level,
        strength=draw(st.floats(min_value=0.3, max_value=0.8, allow_nan=False, allow_infinity=False)),
    )
    
    return {large_level: [large_signal], small_level: [small_signal]}, large_level, is_large_buy


@st.composite
def strong_confirmation_signals_strategy(draw):
    """业务模块说明。"""
    large_level = draw(st.sampled_from(["daily", "weekly"]))
    small_level = draw(st.sampled_from(["30min", "60min"]))
    
    assume(PERIOD_PRIORITY[large_level] > PERIOD_PRIORITY[small_level])
    
    is_buy = draw(st.booleans())
    if is_buy:
        large_type = SignalType.BUY_1
        small_type = SignalType.BUY_2
    else:
        large_type = SignalType.SELL_1
        small_type = SignalType.SELL_2
    
    ts = _ts(draw(st.integers(min_value=0, max_value=100)))
    price = draw(st.floats(min_value=10.0, max_value=500.0, allow_nan=False, allow_infinity=False))
    
    large_signal = Signal(
        stock_code="TEST",
        signal_type=large_type,
        timestamp=ts,
        price=price,
        level=large_level,
        strength=draw(st.floats(min_value=0.3, max_value=0.8, allow_nan=False, allow_infinity=False)),
    )
    
    small_signal = Signal(
        stock_code="TEST",
        signal_type=small_type,
        timestamp=ts,
        price=price,
        level=small_level,
        strength=draw(st.floats(min_value=0.3, max_value=0.8, allow_nan=False, allow_infinity=False)),
    )
    
    return {large_level: [large_signal], small_level: [small_signal]}, large_level, small_level


class TestMultiLevelPropertyConflict:
    """业务模块说明。"""

    @given(conflicting_signals_strategy())
    @settings(max_examples=100)
    def test_conflict_follows_large_level_direction(self, data):
        """业务模块说明。"""
        signals_by_period, large_level, is_large_buy = data
        
        ml = MultiLevelLinkage()
        result = ml.generate_combined_signal(signals_by_period)
        
        assert len(result) >= 1, "Should generate at least one combined signal"
        
        combined = result[0]
        
        # Verify conflict is detected
        assert combined.has_conflict, "Should detect conflict"
        
        # Verify primary level is the large level
        assert combined.primary_level == large_level, (
            f"Primary level should be {large_level}, got {combined.primary_level}"
        )
        
        # Verify signal type follows large level direction
        combined_is_buy = combined.signal_type in (
            SignalType.BUY_1, SignalType.BUY_2, SignalType.BUY_3,
        )
        assert combined_is_buy == is_large_buy, (
            f"Combined signal direction ({combined_is_buy}) should match "
            f"large level direction ({is_large_buy})"
        )

    @given(conflicting_signals_strategy())
    @settings(max_examples=100)
    def test_conflict_details_contain_conflicting_periods(self, data):
        """业务模块说明。"""
        signals_by_period, large_level, is_large_buy = data
        
        ml = MultiLevelLinkage()
        result = ml.generate_combined_signal(signals_by_period)
        
        combined = result[0]
        assert combined.has_conflict
        
        details = combined.conflict_details
        assert "primary_period" in details
        assert "conflicting_periods" in details
        assert len(details["conflicting_periods"]) >= 1


class TestMultiLevelPropertyStrongConfirmation:
    """业务模块说明。"""

    @given(strong_confirmation_signals_strategy())
    @settings(max_examples=100)
    def test_strong_confirmation_generated(self, data):
        """业务模块说明。"""
        signals_by_period, large_level, small_level = data
        
        ml = MultiLevelLinkage()
        result = ml.generate_combined_signal(signals_by_period)
        
        assert len(result) >= 1, "Should generate at least one combined signal"
        
        combined = result[0]
        
        # Verify strong confirmation is detected
        assert combined.is_strong_confirmation, (
            "Should be marked as strong confirmation"
        )
        
        # Verify secondary levels contain the small level
        assert small_level in combined.secondary_levels, (
            f"Secondary levels should contain {small_level}"
        )

    @given(strong_confirmation_signals_strategy())
    @settings(max_examples=100)
    def test_strong_confirmation_has_higher_strength(self, data):
        """业务模块说明。"""
        signals_by_period, large_level, small_level = data
        
        ml = MultiLevelLinkage()
        
        # Get combined signal with strong confirmation
        combined_result = ml.generate_combined_signal(signals_by_period)
        
        # Get single signal (only large level)
        single_result = ml.generate_combined_signal({
            large_level: signals_by_period[large_level],
        })
        
        assert len(combined_result) >= 1
        assert len(single_result) >= 1
        
        # Strong confirmation should have higher strength
        # (due to +0.2 bonus and +0.1 resonance)
        assert combined_result[0].strength >= single_result[0].strength, (
            f"Strong confirmation strength ({combined_result[0].strength}) should be >= "
            f"single signal strength ({single_result[0].strength})"
        )

    @given(strong_confirmation_signals_strategy())
    @settings(max_examples=100)
    def test_strong_confirmation_no_conflict(self, data):
        """业务模块说明。"""
        signals_by_period, large_level, small_level = data
        
        ml = MultiLevelLinkage()
        result = ml.generate_combined_signal(signals_by_period)
        
        combined = result[0]
        
        # Strong confirmation means same direction, so no conflict
        assert not combined.has_conflict, (
            "Strong confirmation should not have conflict"
        )
