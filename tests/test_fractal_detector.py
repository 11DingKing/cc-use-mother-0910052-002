"""业务模块说明。"""

from datetime import datetime, timedelta
from typing import List

import pytest

from app.chan.fractal_detector import FractalDetector
from app.chan.models import Direction, FractalType, MergedCandle, Fractal


def _make_merged(
    index: int,
    high: float,
    low: float,
    direction: Direction = Direction.UP,
) -> MergedCandle:
    """业务模块说明。"""
    return MergedCandle(
        timestamp=datetime(2024, 1, 1) + timedelta(days=index),
        high=high,
        low=low,
        start_index=index,
        end_index=index,
        direction=direction,
    )


class TestFractalDetectorDetect:
    """业务模块说明。"""

    def setup_method(self):
        self.detector = FractalDetector()

    # --- Empty / insufficient input ---

    def test_empty_input_returns_empty_list(self):
        result = self.detector.detect([])
        assert result == []

    def test_one_candle_returns_empty_list(self):
        candles = [_make_merged(0, high=10.0, low=8.0)]
        result = self.detector.detect(candles)
        assert result == []

    def test_two_candles_returns_empty_list(self):
        candles = [
            _make_merged(0, high=10.0, low=8.0),
            _make_merged(1, high=12.0, low=9.0),
        ]
        result = self.detector.detect(candles)
        assert result == []

    # --- Top fractal detection (Requirement 2.4) ---

    def test_top_fractal_basic(self):
        """业务模块说明。"""
        candles = [
            _make_merged(0, high=10.0, low=8.0),
            _make_merged(1, high=12.0, low=9.0),   # top: highest high & low
            _make_merged(2, high=11.0, low=7.0),
        ]
        result = self.detector.detect(candles)
        assert len(result) == 1
        f = result[0]
        assert f.type == FractalType.TOP
        assert f.price == 12.0  # mid.high
        assert f.candle_index == 1
        assert f.timestamp == candles[1].timestamp

    def test_top_fractal_stores_three_candles(self):
        candles = [
            _make_merged(0, high=10.0, low=8.0),
            _make_merged(1, high=12.0, low=9.0),
            _make_merged(2, high=11.0, low=7.0),
        ]
        result = self.detector.detect(candles)
        assert len(result) == 1
        assert len(result[0].candles) == 3
        assert result[0].candles[0] is candles[0]
        assert result[0].candles[1] is candles[1]
        assert result[0].candles[2] is candles[2]

    # --- Bottom fractal detection (Requirement 2.5) ---

    def test_bottom_fractal_basic(self):
        """业务模块说明。"""
        candles = [
            _make_merged(0, high=12.0, low=9.0),
            _make_merged(1, high=10.0, low=7.0),   # bottom: lowest high & low
            _make_merged(2, high=11.0, low=8.0),
        ]
        result = self.detector.detect(candles)
        assert len(result) == 1
        f = result[0]
        assert f.type == FractalType.BOTTOM
        assert f.price == 7.0  # mid.low
        assert f.candle_index == 1
        assert f.timestamp == candles[1].timestamp

    def test_bottom_fractal_stores_three_candles(self):
        candles = [
            _make_merged(0, high=12.0, low=9.0),
            _make_merged(1, high=10.0, low=7.0),
            _make_merged(2, high=11.0, low=8.0),
        ]
        result = self.detector.detect(candles)
        assert len(result) == 1
        assert len(result[0].candles) == 3

    # --- No fractal cases ---

    def test_no_fractal_when_mid_high_not_highest(self):
        """业务模块说明。"""
        candles = [
            _make_merged(0, high=13.0, low=8.0),
            _make_merged(1, high=12.0, low=9.0),   # high < left.high
            _make_merged(2, high=11.0, low=7.0),
        ]
        result = self.detector.detect(candles)
        assert len(result) == 0

    def test_no_fractal_when_mid_low_not_highest_for_top(self):
        """业务模块说明。"""
        candles = [
            _make_merged(0, high=10.0, low=9.5),
            _make_merged(1, high=12.0, low=9.0),   # high highest, but low < left.low
            _make_merged(2, high=11.0, low=7.0),
        ]
        result = self.detector.detect(candles)
        assert len(result) == 0

    def test_no_fractal_when_mid_low_not_lowest(self):
        """业务模块说明。"""
        candles = [
            _make_merged(0, high=12.0, low=6.0),
            _make_merged(1, high=10.0, low=7.0),   # low > left.low
            _make_merged(2, high=11.0, low=8.0),
        ]
        result = self.detector.detect(candles)
        assert len(result) == 0

    def test_no_fractal_when_mid_high_not_lowest_for_bottom(self):
        """业务模块说明。"""
        candles = [
            _make_merged(0, high=10.0, low=9.0),
            _make_merged(1, high=11.0, low=7.0),   # low lowest, but high > left.high
            _make_merged(2, high=12.0, low=8.0),
        ]
        result = self.detector.detect(candles)
        assert len(result) == 0

    def test_no_fractal_equal_highs(self):
        """业务模块说明。"""
        candles = [
            _make_merged(0, high=12.0, low=8.0),
            _make_merged(1, high=12.0, low=9.0),   # high == left.high
            _make_merged(2, high=11.0, low=7.0),
        ]
        result = self.detector.detect(candles)
        assert len(result) == 0

    def test_no_fractal_equal_lows(self):
        """业务模块说明。"""
        candles = [
            _make_merged(0, high=12.0, low=7.0),
            _make_merged(1, high=10.0, low=7.0),   # low == left.low
            _make_merged(2, high=11.0, low=8.0),
        ]
        result = self.detector.detect(candles)
        assert len(result) == 0

    # --- Monotonic sequences ---

    def test_monotonic_up_no_fractals(self):
        """业务模块说明。"""
        candles = [
            _make_merged(0, high=10.0, low=8.0),
            _make_merged(1, high=12.0, low=9.0),
            _make_merged(2, high=14.0, low=11.0),
            _make_merged(3, high=16.0, low=13.0),
        ]
        result = self.detector.detect(candles)
        assert len(result) == 0

    def test_monotonic_down_no_fractals(self):
        """业务模块说明。"""
        candles = [
            _make_merged(0, high=16.0, low=13.0),
            _make_merged(1, high=14.0, low=11.0),
            _make_merged(2, high=12.0, low=9.0),
            _make_merged(3, high=10.0, low=7.0),
        ]
        result = self.detector.detect(candles)
        assert len(result) == 0

    # --- Multiple fractals ---

    def test_multiple_fractals_alternating(self):
        """业务模块说明。"""
        candles = [
            _make_merged(0, high=10.0, low=8.0),
            _make_merged(1, high=14.0, low=11.0),  # top
            _make_merged(2, high=12.0, low=9.0),
            _make_merged(3, high=8.0, low=6.0),    # bottom
            _make_merged(4, high=11.0, low=8.0),
        ]
        result = self.detector.detect(candles)
        assert len(result) == 2
        assert result[0].type == FractalType.TOP
        assert result[0].candle_index == 1
        assert result[1].type == FractalType.BOTTOM
        assert result[1].candle_index == 3

    def test_consecutive_top_fractals(self):
        """业务模块说明。"""
        candles = [
            _make_merged(0, high=10.0, low=8.0),
            _make_merged(1, high=14.0, low=11.0),  # top
            _make_merged(2, high=12.0, low=9.0),   # bottom (high<14, high<13, low<11, low<10)
            _make_merged(3, high=13.0, low=10.0),  # top (12<13>11, 9<10>7)
            _make_merged(4, high=11.0, low=7.0),
        ]
        result = self.detector.detect(candles)
        assert len(result) == 3
        assert result[0].type == FractalType.TOP
        assert result[0].candle_index == 1
        assert result[1].type == FractalType.BOTTOM
        assert result[1].candle_index == 2
        assert result[2].type == FractalType.TOP
        assert result[2].candle_index == 3

    # --- Exactly 3 candles ---

    def test_exactly_three_candles_top_fractal(self):
        candles = [
            _make_merged(0, high=10.0, low=8.0),
            _make_merged(1, high=12.0, low=9.0),
            _make_merged(2, high=11.0, low=7.0),
        ]
        result = self.detector.detect(candles)
        assert len(result) == 1
        assert result[0].type == FractalType.TOP

    def test_exactly_three_candles_bottom_fractal(self):
        candles = [
            _make_merged(0, high=12.0, low=9.0),
            _make_merged(1, high=10.0, low=7.0),
            _make_merged(2, high=11.0, low=8.0),
        ]
        result = self.detector.detect(candles)
        assert len(result) == 1
        assert result[0].type == FractalType.BOTTOM

    # --- Fractal ordering ---

    def test_fractals_ordered_by_candle_index(self):
        """业务模块说明。"""
        candles = [
            _make_merged(0, high=10.0, low=8.0),
            _make_merged(1, high=14.0, low=11.0),  # top
            _make_merged(2, high=12.0, low=9.0),
            _make_merged(3, high=8.0, low=6.0),    # bottom
            _make_merged(4, high=11.0, low=8.0),
            _make_merged(5, high=15.0, low=12.0),  # top
            _make_merged(6, high=13.0, low=10.0),
        ]
        result = self.detector.detect(candles)
        indices = [f.candle_index for f in result]
        assert indices == sorted(indices)


class TestFractalDetectorDetectIncremental:
    """业务模块说明。"""

    def setup_method(self):
        self.detector = FractalDetector()

    # --- Empty / edge cases ---

    def test_empty_existing_fractals_falls_back_to_full_detect(self):
        candles = [
            _make_merged(0, high=10.0, low=8.0),
            _make_merged(1, high=12.0, low=9.0),
            _make_merged(2, high=11.0, low=7.0),
        ]
        result = self.detector.detect_incremental(candles, [])
        full_result = self.detector.detect(candles)
        assert len(result) == len(full_result)
        for r, f in zip(result, full_result):
            assert r.type == f.type
            assert r.candle_index == f.candle_index
            assert r.price == f.price

    def test_insufficient_candles_returns_existing(self):
        existing = [
            Fractal(
                type=FractalType.TOP,
                timestamp=datetime(2024, 1, 2),
                price=12.0,
                candle_index=1,
                candles=[],
            )
        ]
        candles = [_make_merged(0, high=10.0, low=8.0)]
        result = self.detector.detect_incremental(candles, existing)
        assert len(result) == 1
        assert result[0].type == FractalType.TOP

    # --- Incremental consistency with full detect ---

    def test_incremental_matches_full_detect_simple(self):
        """业务模块说明。"""
        candles = [
            _make_merged(0, high=10.0, low=8.0),
            _make_merged(1, high=14.0, low=11.0),  # top
            _make_merged(2, high=12.0, low=9.0),
            _make_merged(3, high=8.0, low=6.0),    # bottom
            _make_merged(4, high=11.0, low=8.0),
        ]

        # First detect on first 3 candles
        first_half = candles[:3]
        existing = self.detector.detect(first_half)
        assert len(existing) == 1  # top at index 1

        # Incremental on full sequence
        result = self.detector.detect_incremental(candles, existing)

        # Full detect on full sequence
        full_result = self.detector.detect(candles)

        assert len(result) == len(full_result)
        for r, f in zip(result, full_result):
            assert r.type == f.type
            assert r.candle_index == f.candle_index
            assert r.price == f.price

    def test_incremental_with_no_new_fractals(self):
        """业务模块说明。"""
        candles = [
            _make_merged(0, high=10.0, low=8.0),
            _make_merged(1, high=12.0, low=9.0),
            _make_merged(2, high=14.0, low=11.0),
        ]
        existing = self.detector.detect(candles)
        assert len(existing) == 0  # monotonic up, no fractals

        # Add another candle continuing the uptrend (no fractal)
        extended = candles + [_make_merged(3, high=16.0, low=13.0)]
        result = self.detector.detect_incremental(extended, existing)

        # Still no fractals
        assert len(result) == 0

    def test_incremental_detects_new_fractal(self):
        """业务模块说明。"""
        candles = [
            _make_merged(0, high=10.0, low=8.0),
            _make_merged(1, high=14.0, low=11.0),  # top
            _make_merged(2, high=12.0, low=9.0),
        ]
        existing = self.detector.detect(candles)

        # Add candles that form a bottom fractal
        extended = candles + [
            _make_merged(3, high=8.0, low=6.0),    # bottom candidate
            _make_merged(4, high=11.0, low=8.0),
        ]
        result = self.detector.detect_incremental(extended, existing)

        assert len(result) == 2
        assert result[0].type == FractalType.TOP
        assert result[0].candle_index == 1
        assert result[1].type == FractalType.BOTTOM
        assert result[1].candle_index == 3

    def test_incremental_multiple_rounds(self):
        """业务模块说明。"""
        all_candles = [
            _make_merged(0, high=10.0, low=8.0),
            _make_merged(1, high=14.0, low=11.0),  # top
            _make_merged(2, high=12.0, low=9.0),
            _make_merged(3, high=8.0, low=6.0),    # bottom
            _make_merged(4, high=11.0, low=8.0),
            _make_merged(5, high=15.0, low=12.0),  # top
            _make_merged(6, high=13.0, low=10.0),
        ]

        # Round 1: first 3 candles
        existing = self.detector.detect(all_candles[:3])

        # Round 2: first 5 candles
        existing = self.detector.detect_incremental(all_candles[:5], existing)

        # Round 3: all candles
        result = self.detector.detect_incremental(all_candles, existing)

        # Compare with full detect
        full_result = self.detector.detect(all_candles)

        assert len(result) == len(full_result)
        for r, f in zip(result, full_result):
            assert r.type == f.type
            assert r.candle_index == f.candle_index
            assert r.price == f.price

    def test_incremental_preserves_early_fractals(self):
        """业务模块说明。"""
        candles = [
            _make_merged(0, high=10.0, low=8.0),
            _make_merged(1, high=14.0, low=11.0),  # top at index 1
            _make_merged(2, high=12.0, low=9.0),
            _make_merged(3, high=8.0, low=6.0),    # bottom at index 3
            _make_merged(4, high=11.0, low=8.0),
        ]
        existing = self.detector.detect(candles)
        assert len(existing) == 2

        # Extend with more candles far from existing fractals
        extended = candles + [
            _make_merged(5, high=7.0, low=5.0),
            _make_merged(6, high=5.0, low=3.0),    # bottom at index 6
            _make_merged(7, high=8.0, low=6.0),
        ]
        result = self.detector.detect_incremental(extended, existing)

        # The first top fractal at index 1 should be preserved
        assert result[0].type == FractalType.TOP
        assert result[0].candle_index == 1


# ---------------------------------------------------------------------------
# Property-Based Tests (Hypothesis)
# Property 2: 分型定义有效性
# Property 3: 分型增量更新一致性
# Validates: Requirements 2.3, 2.4, 2.5, 2.6
# ---------------------------------------------------------------------------

from hypothesis import given, strategies as st, settings, assume


@st.composite
def merged_candle_strategy(draw, index=None):
    """业务模块说明。"""
    if index is None:
        index = draw(st.integers(min_value=0, max_value=1000))
    
    low = draw(st.floats(min_value=1.0, max_value=500.0, allow_nan=False, allow_infinity=False))
    high = draw(st.floats(min_value=low + 0.01, max_value=1000.0, allow_nan=False, allow_infinity=False))
    direction = draw(st.sampled_from([Direction.UP, Direction.DOWN]))
    
    return MergedCandle(
        timestamp=datetime(2024, 1, 1) + timedelta(days=index),
        high=high,
        low=low,
        start_index=index,
        end_index=index,
        direction=direction,
    )


@st.composite
def merged_candle_list_strategy(draw, min_size=3, max_size=30):
    """业务模块说明。"""
    size = draw(st.integers(min_value=min_size, max_value=max_size))
    candles = []
    for i in range(size):
        candle = draw(merged_candle_strategy(index=i))
        candles.append(candle)
    return candles


class TestFractalPropertyDefinitionValidity:
    """业务模块说明。"""

    @given(merged_candle_list_strategy(min_size=3, max_size=50))
    @settings(max_examples=100)
    def test_all_fractals_satisfy_definition(self, candles):
        """业务模块说明。"""
        detector = FractalDetector()
        fractals = detector.detect(candles)
        
        for f in fractals:
            idx = f.candle_index
            # Ensure we have valid indices
            assert 0 < idx < len(candles) - 1, f"Invalid candle_index: {idx}"
            
            left = candles[idx - 1]
            mid = candles[idx]
            right = candles[idx + 1]
            
            if f.type == FractalType.TOP:
                # Top fractal definition
                assert mid.high > left.high, (
                    f"Top fractal at {idx}: mid.high ({mid.high}) should be > "
                    f"left.high ({left.high})"
                )
                assert mid.high > right.high, (
                    f"Top fractal at {idx}: mid.high ({mid.high}) should be > "
                    f"right.high ({right.high})"
                )
                assert mid.low > left.low, (
                    f"Top fractal at {idx}: mid.low ({mid.low}) should be > "
                    f"left.low ({left.low})"
                )
                assert mid.low > right.low, (
                    f"Top fractal at {idx}: mid.low ({mid.low}) should be > "
                    f"right.low ({right.low})"
                )
                # Price should be mid.high for top fractal
                assert f.price == mid.high
                
            elif f.type == FractalType.BOTTOM:
                # Bottom fractal definition
                assert mid.low < left.low, (
                    f"Bottom fractal at {idx}: mid.low ({mid.low}) should be < "
                    f"left.low ({left.low})"
                )
                assert mid.low < right.low, (
                    f"Bottom fractal at {idx}: mid.low ({mid.low}) should be < "
                    f"right.low ({right.low})"
                )
                assert mid.high < left.high, (
                    f"Bottom fractal at {idx}: mid.high ({mid.high}) should be < "
                    f"left.high ({left.high})"
                )
                assert mid.high < right.high, (
                    f"Bottom fractal at {idx}: mid.high ({mid.high}) should be < "
                    f"right.high ({right.high})"
                )
                # Price should be mid.low for bottom fractal
                assert f.price == mid.low

    @given(merged_candle_list_strategy(min_size=3, max_size=30))
    @settings(max_examples=100)
    def test_fractal_candles_stored_correctly(self, candles):
        """业务模块说明。"""
        detector = FractalDetector()
        fractals = detector.detect(candles)
        
        for f in fractals:
            assert len(f.candles) == 3, f"Fractal should have 3 candles, got {len(f.candles)}"
            idx = f.candle_index
            assert f.candles[0] is candles[idx - 1]
            assert f.candles[1] is candles[idx]
            assert f.candles[2] is candles[idx + 1]


class TestFractalPropertyIncrementalConsistency:
    """业务模块说明。"""

    @given(merged_candle_list_strategy(min_size=6, max_size=30))
    @settings(max_examples=100)
    def test_incremental_equals_full_detection(self, candles):
        """业务模块说明。"""
        detector = FractalDetector()
        
        # Split at roughly half
        split_point = len(candles) // 2
        if split_point < 3:
            split_point = 3
        
        # First half detection
        first_half = candles[:split_point]
        existing = detector.detect(first_half)
        
        # Incremental on full sequence
        incremental_result = detector.detect_incremental(candles, existing)
        
        # Full detection on full sequence
        full_result = detector.detect(candles)
        
        # Compare results
        assert len(incremental_result) == len(full_result), (
            f"Incremental found {len(incremental_result)} fractals, "
            f"full found {len(full_result)}"
        )
        
        for inc, full in zip(incremental_result, full_result):
            assert inc.type == full.type
            assert inc.candle_index == full.candle_index
            assert inc.price == full.price

    @given(merged_candle_list_strategy(min_size=9, max_size=30))
    @settings(max_examples=50)
    def test_multiple_incremental_rounds_consistency(self, candles):
        """业务模块说明。"""
        detector = FractalDetector()
        
        # Three rounds of incremental detection
        n = len(candles)
        split1 = max(3, n // 3)
        split2 = max(split1 + 3, 2 * n // 3)
        
        # Round 1
        existing = detector.detect(candles[:split1])
        
        # Round 2
        existing = detector.detect_incremental(candles[:split2], existing)
        
        # Round 3 (full)
        incremental_result = detector.detect_incremental(candles, existing)
        
        # Full detection
        full_result = detector.detect(candles)
        
        assert len(incremental_result) == len(full_result)
        for inc, full in zip(incremental_result, full_result):
            assert inc.type == full.type
            assert inc.candle_index == full.candle_index
