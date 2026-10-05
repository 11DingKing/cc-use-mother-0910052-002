"""业务模块说明。"""

from datetime import datetime, timedelta

import pytest

from app.chan.kline_processor import KLineProcessor
from app.chan.models import RawCandle


def _make_candle(
    day_offset: int = 0,
    open_: float = 10.0,
    high: float = 11.0,
    low: float = 9.0,
    close: float = 10.5,
    volume: float = 1000.0,
) -> RawCandle:
    """业务模块说明。"""
    return RawCandle(
        timestamp=datetime(2024, 1, 1) + timedelta(days=day_offset),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


class TestKLineProcessorClean:
    """业务模块说明。"""

    def setup_method(self):
        self.processor = KLineProcessor()

    # --- Empty / minimal input ---

    def test_empty_input_returns_empty_list_and_zero_report(self):
        cleaned, report = self.processor.clean([])
        assert cleaned == []
        assert report == {
            "removed_count": 0,
            "suspended_count": 0,
            "anomaly_count": 0,
            "limit_up_count": 0,
            "limit_down_count": 0,
        }

    def test_single_normal_candle_passes_through(self):
        candle = _make_candle()
        cleaned, report = self.processor.clean([candle])
        assert len(cleaned) == 1
        assert cleaned[0] is candle
        assert report["removed_count"] == 0

    # --- Suspended filtering (volume == 0) ---

    def test_suspended_candle_is_removed(self):
        candles = [
            _make_candle(day_offset=0),
            _make_candle(day_offset=1, volume=0),  # suspended
            _make_candle(day_offset=2),
        ]
        cleaned, report = self.processor.clean(candles)
        assert len(cleaned) == 2
        assert report["suspended_count"] == 1
        assert report["removed_count"] == 1

    def test_all_suspended_candles_removed(self):
        candles = [
            _make_candle(day_offset=0, volume=0),
            _make_candle(day_offset=1, volume=0),
        ]
        cleaned, report = self.processor.clean(candles)
        assert len(cleaned) == 0
        assert report["suspended_count"] == 2
        assert report["removed_count"] == 2

    # --- Price anomaly filtering (high < low) ---

    def test_anomaly_candle_high_less_than_low_is_removed(self):
        candles = [
            _make_candle(day_offset=0),
            _make_candle(day_offset=1, high=8.0, low=10.0),  # anomaly
            _make_candle(day_offset=2),
        ]
        cleaned, report = self.processor.clean(candles)
        assert len(cleaned) == 2
        assert report["anomaly_count"] == 1
        assert report["removed_count"] == 1

    def test_candle_with_equal_high_low_is_kept(self):
        """业务模块说明。"""
        candles = [
            _make_candle(day_offset=0, high=10.0, low=10.0, open_=10.0, close=10.0),
        ]
        cleaned, report = self.processor.clean(candles)
        assert len(cleaned) == 1
        assert report["anomaly_count"] == 0

    # --- Mixed suspended + anomaly ---

    def test_mixed_suspended_and_anomaly(self):
        candles = [
            _make_candle(day_offset=0),
            _make_candle(day_offset=1, volume=0),        # suspended
            _make_candle(day_offset=2, high=5.0, low=8.0),  # anomaly
            _make_candle(day_offset=3),
        ]
        cleaned, report = self.processor.clean(candles)
        assert len(cleaned) == 2
        assert report["suspended_count"] == 1
        assert report["anomaly_count"] == 1
        assert report["removed_count"] == 2

    # --- Limit-up detection ---

    def test_limit_up_detected(self):
        """业务模块说明。"""
        prev_close = 10.0
        new_close = 11.0  # +10%
        candles = [
            _make_candle(day_offset=0, close=prev_close, high=prev_close),
            _make_candle(
                day_offset=1,
                open_=10.5,
                high=new_close,   # close == high
                low=10.2,
                close=new_close,
                volume=2000.0,
            ),
        ]
        cleaned, report = self.processor.clean(candles)
        assert len(cleaned) == 2  # limit-up candles are NOT removed
        assert report["limit_up_count"] == 1
        assert report["removed_count"] == 0

    def test_no_limit_up_when_close_not_equal_high(self):
        """业务模块说明。"""
        candles = [
            _make_candle(day_offset=0, close=10.0, high=10.0),
            _make_candle(
                day_offset=1,
                open_=10.5,
                high=11.5,
                low=10.2,
                close=11.0,  # close != high
                volume=2000.0,
            ),
        ]
        cleaned, report = self.processor.clean(candles)
        assert report["limit_up_count"] == 0

    def test_no_limit_up_when_change_below_threshold(self):
        """业务模块说明。"""
        candles = [
            _make_candle(day_offset=0, close=10.0, high=10.0),
            _make_candle(
                day_offset=1,
                open_=10.3,
                high=10.5,
                low=10.1,
                close=10.5,  # close == high, but only +5%
                volume=2000.0,
            ),
        ]
        cleaned, report = self.processor.clean(candles)
        assert report["limit_up_count"] == 0

    # --- Limit-down detection ---

    def test_limit_down_detected(self):
        """业务模块说明。"""
        prev_close = 10.0
        new_close = 9.0  # -10%
        candles = [
            _make_candle(day_offset=0, close=prev_close, high=prev_close),
            _make_candle(
                day_offset=1,
                open_=9.5,
                high=9.8,
                low=new_close,   # close == low
                close=new_close,
                volume=2000.0,
            ),
        ]
        cleaned, report = self.processor.clean(candles)
        assert len(cleaned) == 2  # limit-down candles are NOT removed
        assert report["limit_down_count"] == 1
        assert report["removed_count"] == 0

    def test_no_limit_down_when_close_not_equal_low(self):
        candles = [
            _make_candle(day_offset=0, close=10.0, high=10.0),
            _make_candle(
                day_offset=1,
                open_=9.5,
                high=9.8,
                low=8.9,
                close=9.0,  # close != low
                volume=2000.0,
            ),
        ]
        cleaned, report = self.processor.clean(candles)
        assert report["limit_down_count"] == 0

    def test_no_limit_down_when_change_above_threshold(self):
        """业务模块说明。"""
        candles = [
            _make_candle(day_offset=0, close=10.0, high=10.0),
            _make_candle(
                day_offset=1,
                open_=9.7,
                high=9.8,
                low=9.6,
                close=9.6,  # close == low, but only -4%
                volume=2000.0,
            ),
        ]
        cleaned, report = self.processor.clean(candles)
        assert report["limit_down_count"] == 0

    # --- First candle cannot be limit-up/down (no previous close) ---

    def test_first_candle_never_flagged_as_limit(self):
        candles = [
            _make_candle(day_offset=0, high=11.0, close=11.0, volume=1000.0),
        ]
        cleaned, report = self.processor.clean(candles)
        assert report["limit_up_count"] == 0
        assert report["limit_down_count"] == 0

    # --- Ordering preserved ---

    def test_cleaned_candles_preserve_order(self):
        candles = [
            _make_candle(day_offset=0),
            _make_candle(day_offset=1, volume=0),  # removed
            _make_candle(day_offset=2),
            _make_candle(day_offset=3, high=1.0, low=5.0),  # removed
            _make_candle(day_offset=4),
        ]
        cleaned, _ = self.processor.clean(candles)
        timestamps = [c.timestamp for c in cleaned]
        assert timestamps == sorted(timestamps)
        assert len(cleaned) == 3

    # --- Limit-up/down with suspended candle in between ---

    def test_limit_up_uses_original_previous_close(self):
        """业务模块说明。"""
        candles = [
            _make_candle(day_offset=0, close=10.0, high=10.0),
            _make_candle(day_offset=1, close=10.0, volume=0),  # suspended, will be removed
            _make_candle(
                day_offset=2,
                open_=10.5,
                high=11.0,
                low=10.2,
                close=11.0,  # close == high, +10% vs prev (suspended candle)
                volume=2000.0,
            ),
        ]
        cleaned, report = self.processor.clean(candles)
        # The limit-up check uses candles[1].close (the suspended one) as prev
        assert report["limit_up_count"] == 1
        assert report["suspended_count"] == 1

    # --- Custom threshold ---

    def test_custom_limit_threshold(self):
        processor = KLineProcessor(
            limit_up_threshold=0.05,
            limit_down_threshold=-0.05,
        )
        candles = [
            _make_candle(day_offset=0, close=10.0, high=10.0),
            _make_candle(
                day_offset=1,
                open_=10.3,
                high=10.6,
                low=10.1,
                close=10.6,  # close == high, +6% > 5% threshold
                volume=2000.0,
            ),
        ]
        cleaned, report = processor.clean(candles)
        assert report["limit_up_count"] == 1

    # --- Report totals consistency ---

    def test_report_removed_count_equals_suspended_plus_anomaly(self):
        candles = [
            _make_candle(day_offset=0),
            _make_candle(day_offset=1, volume=0),
            _make_candle(day_offset=2, volume=0),
            _make_candle(day_offset=3, high=1.0, low=5.0),
            _make_candle(day_offset=4),
        ]
        cleaned, report = self.processor.clean(candles)
        assert report["removed_count"] == report["suspended_count"] + report["anomaly_count"]
        assert len(cleaned) == len(candles) - report["removed_count"]


# ---------------------------------------------------------------------------
# Tests for KLineProcessor.merge()
# Validates: Requirements 2.2
# ---------------------------------------------------------------------------

from app.chan.models import MergedCandle, Direction


def _make_raw(
    day_offset: int = 0,
    high: float = 11.0,
    low: float = 9.0,
    open_: float = 10.0,
    close: float = 10.5,
    volume: float = 1000.0,
) -> RawCandle:
    """业务模块说明。"""
    return RawCandle(
        timestamp=datetime(2024, 1, 1) + timedelta(days=day_offset),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


class TestKLineProcessorMerge:
    """业务模块说明。"""

    def setup_method(self):
        self.processor = KLineProcessor()

    # --- Empty / minimal input ---

    def test_empty_input_returns_empty_list(self):
        result = self.processor.merge([])
        assert result == []

    def test_single_candle_returns_one_merged_candle(self):
        candle = _make_raw(day_offset=0, high=11.0, low=9.0)
        result = self.processor.merge([candle])
        assert len(result) == 1
        mc = result[0]
        assert mc.high == 11.0
        assert mc.low == 9.0
        assert mc.start_index == 0
        assert mc.end_index == 0
        assert mc.direction == Direction.UP

    def test_two_candles_no_inclusion(self):
        """业务模块说明。"""
        candles = [
            _make_raw(day_offset=0, high=10.0, low=8.0),
            _make_raw(day_offset=1, high=12.0, low=9.0),
        ]
        result = self.processor.merge(candles)
        assert len(result) == 2
        assert result[0].high == 10.0
        assert result[0].low == 8.0
        assert result[1].high == 12.0
        assert result[1].low == 9.0

    # --- Inclusion relationship detection ---

    def test_last_includes_current(self):
        """业务模块说明。"""
        candles = [
            _make_raw(day_offset=0, high=15.0, low=5.0),   # wide range
            _make_raw(day_offset=1, high=12.0, low=7.0),   # contained within first
        ]
        result = self.processor.merge(candles)
        assert len(result) == 1  # merged into one

    def test_current_includes_last(self):
        """业务模块说明。"""
        candles = [
            _make_raw(day_offset=0, high=12.0, low=7.0),   # narrow range
            _make_raw(day_offset=1, high=15.0, low=5.0),   # wider, includes first
        ]
        result = self.processor.merge(candles)
        assert len(result) == 1  # merged into one

    def test_equal_high_low_is_inclusion(self):
        """业务模块说明。"""
        candles = [
            _make_raw(day_offset=0, high=10.0, low=8.0),
            _make_raw(day_offset=1, high=10.0, low=8.0),
        ]
        result = self.processor.merge(candles)
        assert len(result) == 1

    # --- Up trend merge: max(high), max(low) ---

    def test_up_trend_merge_takes_max_high_max_low(self):
        """业务模块说明。"""
        candles = [
            _make_raw(day_offset=0, high=10.0, low=8.0),
            _make_raw(day_offset=1, high=12.0, low=9.0),   # up trend established
            _make_raw(day_offset=2, high=11.0, low=10.0),  # included in prev (12>=11, 9<=10 → no; 11>=12? no → check reverse: 12>=11 yes, 9<=10 yes → inclusion)
        ]
        result = self.processor.merge(candles)
        # First two: no inclusion (10<12, 8<9 → both higher → up trend, no inclusion)
        # Second and third: last=(12,9), c=(11,10) → 12>=11 and 9<=10 → inclusion
        # Up trend merge: max(12,11)=12, max(9,10)=10
        assert len(result) == 2
        assert result[1].high == 12.0
        assert result[1].low == 10.0

    # --- Down trend merge: min(high), min(low) ---

    def test_down_trend_merge_takes_min_high_min_low(self):
        """业务模块说明。"""
        candles = [
            _make_raw(day_offset=0, high=12.0, low=9.0),
            _make_raw(day_offset=1, high=10.0, low=7.0),   # down trend established
            _make_raw(day_offset=2, high=9.0, low=8.0),    # included in prev: last=(10,7), c=(9,8) → 10>=9 and 7<=8 → last includes c → inclusion
        ]
        result = self.processor.merge(candles)
        # First two: no inclusion (12>10, 9>7 → both lower → down trend)
        # Second and third: last=(10,7), c=(9,8) → 10>=9 and 7<=8 → inclusion
        # Down trend merge: min(10,9)=9, min(7,8)=7
        assert len(result) == 2
        assert result[1].high == 9.0
        assert result[1].low == 7.0

    # --- Direction tracking ---

    def test_initial_direction_up_when_second_high_greater(self):
        candles = [
            _make_raw(day_offset=0, high=10.0, low=8.0),
            _make_raw(day_offset=1, high=12.0, low=9.0),
        ]
        result = self.processor.merge(candles)
        assert result[0].direction == Direction.UP

    def test_initial_direction_down_when_second_high_lower(self):
        candles = [
            _make_raw(day_offset=0, high=12.0, low=9.0),
            _make_raw(day_offset=1, high=10.0, low=7.0),
        ]
        result = self.processor.merge(candles)
        assert result[0].direction == Direction.DOWN

    def test_direction_changes_on_non_inclusion(self):
        """业务模块说明。"""
        candles = [
            _make_raw(day_offset=0, high=10.0, low=8.0),
            _make_raw(day_offset=1, high=12.0, low=9.0),   # up
            _make_raw(day_offset=2, high=14.0, low=11.0),  # up
            _make_raw(day_offset=3, high=11.0, low=8.0),   # down (both lower)
        ]
        result = self.processor.merge(candles)
        assert len(result) == 4
        # Last candle should have DOWN direction
        assert result[3].direction == Direction.DOWN

    # --- Multiple consecutive inclusions ---

    def test_multiple_consecutive_inclusions_merge_into_one(self):
        """业务模块说明。"""
        candles = [
            _make_raw(day_offset=0, high=20.0, low=5.0),   # very wide
            _make_raw(day_offset=1, high=18.0, low=6.0),   # included
            _make_raw(day_offset=2, high=15.0, low=7.0),   # still included
        ]
        result = self.processor.merge(candles)
        assert len(result) == 1
        assert result[0].start_index == 0
        assert result[0].end_index == 2

    # --- Index tracking ---

    def test_start_end_index_tracking(self):
        """业务模块说明。"""
        candles = [
            _make_raw(day_offset=0, high=10.0, low=8.0),
            _make_raw(day_offset=1, high=12.0, low=9.0),   # no inclusion, new candle
            _make_raw(day_offset=2, high=11.0, low=10.0),  # included in prev
            _make_raw(day_offset=3, high=15.0, low=13.0),  # no inclusion, new candle
        ]
        result = self.processor.merge(candles)
        # First: index 0
        assert result[0].start_index == 0
        assert result[0].end_index == 0
        # Second merged (candles 1+2): start=1, end=2
        assert result[1].start_index == 1
        assert result[1].end_index == 2
        # Third: index 3
        assert result[2].start_index == 3
        assert result[2].end_index == 3

    # --- No inclusion in output ---

    def test_output_has_no_adjacent_inclusion(self):
        """业务模块说明。"""
        candles = [
            _make_raw(day_offset=0, high=10.0, low=8.0),
            _make_raw(day_offset=1, high=12.0, low=7.0),   # includes first
            _make_raw(day_offset=2, high=11.0, low=9.0),   # included in merged
            _make_raw(day_offset=3, high=15.0, low=13.0),  # no inclusion
            _make_raw(day_offset=4, high=14.0, low=11.0),  # no inclusion (both lower)
        ]
        result = self.processor.merge(candles)
        for i in range(len(result) - 1):
            a, b = result[i], result[i + 1]
            # Neither a includes b nor b includes a
            assert not (a.high >= b.high and a.low <= b.low), (
                f"Inclusion found: merged[{i}] includes merged[{i+1}]"
            )
            assert not (b.high >= a.high and b.low <= a.low), (
                f"Inclusion found: merged[{i+1}] includes merged[{i}]"
            )

    # --- Realistic scenario ---

    def test_realistic_up_trend_with_inclusions(self):
        """业务模块说明。"""
        candles = [
            _make_raw(day_offset=0, high=10.0, low=8.0),
            _make_raw(day_offset=1, high=11.0, low=9.0),
            _make_raw(day_offset=2, high=12.0, low=10.0),
            _make_raw(day_offset=3, high=11.5, low=10.5),  # included in prev (12>=11.5, 10<=10.5)
            _make_raw(day_offset=4, high=14.0, low=12.0),
        ]
        result = self.processor.merge(candles)
        # Candles 2 and 3 should merge (up trend: max high, max low)
        # Result should be 4 merged candles
        assert len(result) == 4
        # The merged candle (from candles 2+3) should have max(12,11.5)=12, max(10,10.5)=10.5
        assert result[2].high == 12.0
        assert result[2].low == 10.5

    def test_realistic_down_trend_with_inclusions(self):
        """业务模块说明。"""
        candles = [
            _make_raw(day_offset=0, high=14.0, low=12.0),
            _make_raw(day_offset=1, high=12.0, low=10.0),
            _make_raw(day_offset=2, high=10.0, low=8.0),
            _make_raw(day_offset=3, high=9.0, low=9.0),    # included in prev: last=(10,8), c=(9,9) → 10>=9 and 8<=9 → inclusion
            _make_raw(day_offset=4, high=8.0, low=6.0),
        ]
        result = self.processor.merge(candles)
        # Candles 2 and 3 should merge (down trend: min high, min low)
        # min(10,9)=9, min(8,9)=8
        assert len(result) == 4
        assert result[2].high == 9.0
        assert result[2].low == 8.0

    def test_timestamp_from_first_candle_in_merge(self):
        """业务模块说明。"""
        candles = [
            _make_raw(day_offset=0, high=10.0, low=8.0),
            _make_raw(day_offset=1, high=12.0, low=9.0),
            _make_raw(day_offset=2, high=11.0, low=10.0),  # included in prev
        ]
        result = self.processor.merge(candles)
        # The merged candle (candles 1+2) should keep candle 1's timestamp
        assert result[1].timestamp == datetime(2024, 1, 2)


# ---------------------------------------------------------------------------
# Property-Based Tests (Hypothesis)
# Property 1: 合并K线无包含关系
# Validates: Requirements 2.2
# ---------------------------------------------------------------------------

from hypothesis import given, strategies as st, settings, assume


# Strategy for generating valid RawCandle
@st.composite
def raw_candle_strategy(draw, day_offset=None):
    """业务模块说明。"""
    if day_offset is None:
        day_offset = draw(st.integers(min_value=0, max_value=1000))
    
    # Generate high and low ensuring high >= low
    low = draw(st.floats(min_value=1.0, max_value=500.0, allow_nan=False, allow_infinity=False))
    high = draw(st.floats(min_value=low, max_value=1000.0, allow_nan=False, allow_infinity=False))
    
    # open and close should be between low and high
    open_ = draw(st.floats(min_value=low, max_value=high, allow_nan=False, allow_infinity=False))
    close = draw(st.floats(min_value=low, max_value=high, allow_nan=False, allow_infinity=False))
    
    volume = draw(st.floats(min_value=1.0, max_value=1e9, allow_nan=False, allow_infinity=False))
    
    return RawCandle(
        timestamp=datetime(2024, 1, 1) + timedelta(days=day_offset),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


@st.composite
def raw_candle_list_strategy(draw, min_size=2, max_size=50):
    """业务模块说明。"""
    size = draw(st.integers(min_value=min_size, max_value=max_size))
    candles = []
    for i in range(size):
        candle = draw(raw_candle_strategy(day_offset=i))
        candles.append(candle)
    return candles


def has_inclusion(a: MergedCandle, b: MergedCandle) -> bool:
    """业务模块说明。"""
    # a includes b
    if a.high >= b.high and a.low <= b.low:
        return True
    # b includes a
    if b.high >= a.high and b.low <= a.low:
        return True
    return False


class TestMergePropertyNoInclusion:
    """业务模块说明。"""

    @given(raw_candle_list_strategy(min_size=2, max_size=50))
    @settings(max_examples=100)
    def test_no_adjacent_inclusion_after_merge(self, candles):
        """业务模块说明。"""
        processor = KLineProcessor()
        merged = processor.merge(candles)
        
        # Skip if less than 2 merged candles
        if len(merged) < 2:
            return
        
        # Check all adjacent pairs
        for i in range(len(merged) - 1):
            a = merged[i]
            b = merged[i + 1]
            assert not has_inclusion(a, b), (
                f"Inclusion found between merged[{i}] and merged[{i+1}]: "
                f"a=(high={a.high}, low={a.low}), b=(high={b.high}, low={b.low})"
            )

    @given(raw_candle_list_strategy(min_size=3, max_size=30))
    @settings(max_examples=100)
    def test_merged_count_less_or_equal_input(self, candles):
        """业务模块说明。"""
        processor = KLineProcessor()
        merged = processor.merge(candles)
        assert len(merged) <= len(candles)

    @given(raw_candle_list_strategy(min_size=1, max_size=30))
    @settings(max_examples=100)
    def test_merged_preserves_price_range(self, candles):
        """业务模块说明。"""
        processor = KLineProcessor()
        merged = processor.merge(candles)
        
        if not merged:
            return
        
        input_max_high = max(c.high for c in candles)
        input_min_low = min(c.low for c in candles)
        
        merged_max_high = max(m.high for m in merged)
        merged_min_low = min(m.low for m in merged)
        
        assert merged_max_high <= input_max_high
        assert merged_min_low >= input_min_low
