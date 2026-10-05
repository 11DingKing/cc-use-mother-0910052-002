"""业务模块说明。"""

from datetime import datetime, timedelta
from typing import List

import pytest

from app.chan.zhongshu_detector import ZhongshuDetector
from app.chan.models import Direction, FractalType, Fractal, Bi, Zhongshu


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def _make_fractal(
    ftype: FractalType, index: int, price: float,
) -> Fractal:
    """业务模块说明。"""
    return Fractal(
        type=ftype,
        timestamp=datetime(2024, 1, 1) + timedelta(days=index),
        price=price,
        candle_index=index,
        candles=[],
    )


def _make_bi(
    start_idx: int,
    end_idx: int,
    direction: Direction,
    start_price: float,
    end_price: float,
) -> Bi:
    """业务模块说明。"""
    if direction == Direction.UP:
        start_ftype = FractalType.BOTTOM
        end_ftype = FractalType.TOP
    else:
        start_ftype = FractalType.TOP
        end_ftype = FractalType.BOTTOM

    return Bi(
        start_fractal=_make_fractal(start_ftype, start_idx, start_price),
        end_fractal=_make_fractal(end_ftype, end_idx, end_price),
        direction=direction,
        candle_count=abs(end_idx - start_idx) + 1,
        start_price=start_price,
        end_price=end_price,
    )


# ---------------------------------------------------------------------------
# Tests for ZhongshuDetector.detect()
# ---------------------------------------------------------------------------

class TestZhongshuDetectorDetect:
    def setup_method(self):
        self.detector = ZhongshuDetector()

    def test_empty_bi_list(self):
        """业务模块说明。"""
        assert self.detector.detect([]) == []

    def test_single_bi(self):
        """业务模块说明。"""
        bis = [_make_bi(0, 5, Direction.UP, 10.0, 20.0)]
        assert self.detector.detect(bis) == []

    def test_two_bis(self):
        """业务模块说明。"""
        bis = [
            _make_bi(0, 5, Direction.UP, 10.0, 20.0),
            _make_bi(5, 10, Direction.DOWN, 20.0, 12.0),
        ]
        assert self.detector.detect(bis) == []

    def test_three_bis_with_overlap(self):
        """业务模块说明。"""
        bis = [
            _make_bi(0, 5, Direction.UP, 10.0, 20.0),
            _make_bi(5, 10, Direction.DOWN, 20.0, 12.0),
            _make_bi(10, 15, Direction.UP, 12.0, 18.0),
        ]
        result = self.detector.detect(bis)
        assert len(result) == 1
        zs = result[0]
        assert zs.high == 18.0
        assert zs.low == 12.0
        assert len(zs.bi_list) == 3
        assert zs.level == 1

    def test_three_bis_no_overlap(self):
        """业务模块说明。"""
        bis = [
            _make_bi(0, 5, Direction.UP, 10.0, 15.0),
            _make_bi(5, 10, Direction.DOWN, 25.0, 20.0),
            _make_bi(10, 15, Direction.UP, 30.0, 35.0),
        ]
        result = self.detector.detect(bis)
        assert len(result) == 0

    def test_zhongshu_has_correct_times(self):
        """业务模块说明。"""
        bis = [
            _make_bi(0, 5, Direction.UP, 10.0, 20.0),
            _make_bi(5, 10, Direction.DOWN, 20.0, 12.0),
            _make_bi(10, 15, Direction.UP, 12.0, 18.0),
        ]
        result = self.detector.detect(bis)
        assert len(result) == 1
        zs = result[0]
        assert zs.start_time == bis[0].start_fractal.timestamp
        assert zs.end_time == bis[-1].end_fractal.timestamp

    def test_zhongshu_extension(self):
        """业务模块说明。"""
        bis = [
            _make_bi(0, 5, Direction.UP, 10.0, 20.0),
            _make_bi(5, 10, Direction.DOWN, 20.0, 12.0),
            _make_bi(10, 15, Direction.UP, 12.0, 18.0),
            _make_bi(15, 20, Direction.DOWN, 18.0, 14.0),
        ]
        result = self.detector.detect(bis)
        assert len(result) == 1
        zs = result[0]
        assert len(zs.bi_list) == 4
        assert zs.end_time == bis[3].end_fractal.timestamp

    def test_zhongshu_no_extension_bi_outside(self):
        """业务模块说明。"""
        bis = [
            _make_bi(0, 5, Direction.UP, 10.0, 20.0),
            _make_bi(5, 10, Direction.DOWN, 20.0, 12.0),
            _make_bi(10, 15, Direction.UP, 12.0, 18.0),
            _make_bi(15, 20, Direction.DOWN, 25.0, 19.0),
        ]
        result = self.detector.detect(bis)
        assert len(result) == 1
        zs = result[0]
        assert len(zs.bi_list) == 3  # Only the initial 3

    def test_multiple_zhongshus(self):
        """业务模块说明。"""
        bis = [
            # First zhongshu region
            _make_bi(0, 5, Direction.UP, 10.0, 20.0),
            _make_bi(5, 10, Direction.DOWN, 20.0, 12.0),
            _make_bi(10, 15, Direction.UP, 12.0, 18.0),
            # Second zhongshu region (higher prices, no overlap with first)
            _make_bi(15, 20, Direction.UP, 30.0, 40.0),
            _make_bi(20, 25, Direction.DOWN, 40.0, 32.0),
            _make_bi(25, 30, Direction.UP, 32.0, 38.0),
        ]
        result = self.detector.detect(bis)
        assert len(result) == 2
        assert result[0].high == 18.0
        assert result[0].low == 12.0
        assert result[1].high == 38.0
        assert result[1].low == 32.0

    def test_sliding_window_skips_non_overlapping_then_finds(self):
        """业务模块说明。"""
        bis = [
            _make_bi(0, 5, Direction.UP, 1.0, 5.0),       # high=5, low=1
            _make_bi(5, 10, Direction.DOWN, 20.0, 15.0),   # high=20, low=15
            _make_bi(10, 15, Direction.UP, 14.0, 22.0),    # high=22, low=14
            _make_bi(15, 20, Direction.DOWN, 22.0, 16.0),  # high=22, low=16
        ]
        # Window [0,1,2]: high=min(5,20,22)=5, low=max(1,15,14)=15 → 5<15 no
        # Window [1,2,3]: high=min(20,22,22)=20, low=max(15,14,16)=16 → 20>16 yes!
        result = self.detector.detect(bis)
        assert len(result) == 1
        assert result[0].high == 20.0
        assert result[0].low == 16.0

    def test_zhongshu_multiple_extensions(self):
        """业务模块说明。"""
        bis = [
            _make_bi(0, 5, Direction.UP, 10.0, 20.0),
            _make_bi(5, 10, Direction.DOWN, 20.0, 12.0),
            _make_bi(10, 15, Direction.UP, 12.0, 18.0),
            # Overlap: high=18, low=12
            _make_bi(15, 20, Direction.DOWN, 18.0, 13.0),  # [13,18] ∩ [12,18] ✓
            _make_bi(20, 25, Direction.UP, 13.0, 17.0),    # [13,17] ∩ [12,18] ✓
            _make_bi(25, 30, Direction.DOWN, 17.0, 14.0),  # [14,17] ∩ [12,18] ✓
        ]
        result = self.detector.detect(bis)
        assert len(result) == 1
        assert len(result[0].bi_list) == 6

    def test_bi_high_low_uses_max_min_of_prices(self):
        """业务模块说明。"""
        bis = [
            _make_bi(0, 5, Direction.DOWN, 20.0, 10.0),   # high=20, low=10
            _make_bi(5, 10, Direction.UP, 10.0, 18.0),     # high=18, low=10
            _make_bi(10, 15, Direction.DOWN, 18.0, 11.0),  # high=18, low=11
        ]
        # Overlap: high = min(20, 18, 18) = 18, low = max(10, 10, 11) = 11
        result = self.detector.detect(bis)
        assert len(result) == 1
        assert result[0].high == 18.0
        assert result[0].low == 11.0

    def test_exact_boundary_no_overlap(self):
        """业务模块说明。"""
        bis = [
            _make_bi(0, 5, Direction.UP, 10.0, 15.0),
            _make_bi(5, 10, Direction.UP, 15.0, 20.0),
            _make_bi(10, 15, Direction.UP, 20.0, 25.0),
        ]
        result = self.detector.detect(bis)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Tests for ZhongshuDetector.classify_trend()
# ---------------------------------------------------------------------------

class TestZhongshuClassifyTrend:
    def setup_method(self):
        self.detector = ZhongshuDetector()

    def test_empty_list(self):
        """业务模块说明。"""
        assert self.detector.classify_trend([]) == []

    def test_single_zhongshu_stays_level_1(self):
        """业务模块说明。"""
        zs = Zhongshu(high=18.0, low=12.0, level=1)
        result = self.detector.classify_trend([zs])
        assert len(result) == 1
        assert result[0].level == 1

    def test_up_trend_zhongshus(self):
        """业务模块说明。"""
        zs1 = Zhongshu(high=18.0, low=12.0, level=1)
        zs2 = Zhongshu(high=30.0, low=25.0, level=1)
        result = self.detector.classify_trend([zs1, zs2])
        assert len(result) == 2
        assert result[0].level == 2
        assert result[1].level == 2

    def test_down_trend_zhongshus(self):
        """业务模块说明。"""
        zs1 = Zhongshu(high=30.0, low=25.0, level=1)
        zs2 = Zhongshu(high=20.0, low=15.0, level=1)
        result = self.detector.classify_trend([zs1, zs2])
        assert len(result) == 2
        assert result[0].level == 2
        assert result[1].level == 2

    def test_no_trend_overlapping_zhongshus(self):
        """业务模块说明。"""
        zs1 = Zhongshu(high=20.0, low=12.0, level=1)
        zs2 = Zhongshu(high=25.0, low=15.0, level=1)
        result = self.detector.classify_trend([zs1, zs2])
        assert len(result) == 2
        assert result[0].level == 1
        assert result[1].level == 1

    def test_three_zhongshus_up_trend(self):
        """业务模块说明。"""
        zs1 = Zhongshu(high=10.0, low=5.0, level=1)
        zs2 = Zhongshu(high=20.0, low=15.0, level=1)
        zs3 = Zhongshu(high=30.0, low=25.0, level=1)
        result = self.detector.classify_trend([zs1, zs2, zs3])
        assert all(zs.level == 2 for zs in result)

    def test_mixed_trend_and_non_trend(self):
        """业务模块说明。"""
        zs1 = Zhongshu(high=10.0, low=5.0, level=1)
        zs2 = Zhongshu(high=20.0, low=15.0, level=1)
        zs3 = Zhongshu(high=22.0, low=18.0, level=1)
        result = self.detector.classify_trend([zs1, zs2, zs3])
        assert result[0].level == 2  # part of up trend with zs2
        assert result[1].level == 2  # part of up trend with zs1
        assert result[2].level == 1  # not part of any trend

    def test_classify_does_not_mutate_input(self):
        """业务模块说明。"""
        zs1 = Zhongshu(high=10.0, low=5.0, level=1)
        zs2 = Zhongshu(high=20.0, low=15.0, level=1)
        original_level_1 = zs1.level
        original_level_2 = zs2.level
        self.detector.classify_trend([zs1, zs2])
        assert zs1.level == original_level_1
        assert zs2.level == original_level_2

    def test_exact_boundary_not_trend(self):
        """业务模块说明。"""
        zs1 = Zhongshu(high=15.0, low=10.0, level=1)
        zs2 = Zhongshu(high=25.0, low=15.0, level=1)
        result = self.detector.classify_trend([zs1, zs2])
        assert result[0].level == 1
        assert result[1].level == 1


# ---------------------------------------------------------------------------
# Tests for _calculate_overlap (internal helper)
# ---------------------------------------------------------------------------

class TestCalculateOverlap:
    def test_overlap_exists(self):
        """业务模块说明。"""
        bis = [
            _make_bi(0, 5, Direction.UP, 10.0, 20.0),     # high=20, low=10
            _make_bi(5, 10, Direction.DOWN, 20.0, 12.0),   # high=20, low=12
            _make_bi(10, 15, Direction.UP, 12.0, 18.0),    # high=18, low=12
        ]
        result = ZhongshuDetector._calculate_overlap(bis)
        assert result is not None
        high, low = result
        assert high == 18.0
        assert low == 12.0

    def test_no_overlap(self):
        """业务模块说明。"""
        bis = [
            _make_bi(0, 5, Direction.UP, 10.0, 15.0),     # high=15, low=10
            _make_bi(5, 10, Direction.DOWN, 25.0, 20.0),   # high=25, low=20
            _make_bi(10, 15, Direction.UP, 30.0, 35.0),    # high=35, low=30
        ]
        result = ZhongshuDetector._calculate_overlap(bis)
        assert result is None

    def test_empty_list(self):
        """业务模块说明。"""
        result = ZhongshuDetector._calculate_overlap([])
        assert result is None

    def test_overlap_with_down_bis(self):
        """业务模块说明。"""
        bis = [
            _make_bi(0, 5, Direction.DOWN, 20.0, 10.0),   # high=20, low=10
            _make_bi(5, 10, Direction.UP, 10.0, 18.0),     # high=18, low=10
            _make_bi(10, 15, Direction.DOWN, 18.0, 11.0),  # high=18, low=11
        ]
        result = ZhongshuDetector._calculate_overlap(bis)
        assert result is not None
        high, low = result
        assert high == 18.0
        assert low == 11.0


# ---------------------------------------------------------------------------
# Property-Based Tests (Hypothesis)
# Property 8: 中枢有效性约束
# Property 9: 趋势中枢递进性
# Validates: Requirements 5.1, 5.2, 5.3
# ---------------------------------------------------------------------------

from hypothesis import given, strategies as st, settings, assume


@st.composite
def alternating_bi_list_strategy(draw, min_size=3, max_size=15):
    """业务模块说明。"""
    size = draw(st.integers(min_value=min_size, max_value=max_size))
    bis = []
    
    start_direction = draw(st.sampled_from([Direction.UP, Direction.DOWN]))
    current_direction = start_direction
    current_idx = 0
    
    for i in range(size):
        bi_span = draw(st.integers(min_value=5, max_value=10))
        end_idx = current_idx + bi_span - 1
        
        start_price = draw(st.floats(min_value=1.0, max_value=500.0, allow_nan=False, allow_infinity=False))
        end_price = draw(st.floats(min_value=1.0, max_value=500.0, allow_nan=False, allow_infinity=False))
        
        bi = _make_bi(current_idx, end_idx, current_direction, start_price, end_price)
        bis.append(bi)
        
        # Alternate direction
        current_direction = Direction.DOWN if current_direction == Direction.UP else Direction.UP
        current_idx = end_idx
    
    return bis


@st.composite
def overlapping_bi_list_strategy(draw, min_size=3, max_size=10):
    """业务模块说明。"""
    size = draw(st.integers(min_value=min_size, max_value=max_size))
    bis = []
    
    # Use a base price range to ensure overlap
    base_low = draw(st.floats(min_value=10.0, max_value=50.0, allow_nan=False, allow_infinity=False))
    base_high = base_low + draw(st.floats(min_value=5.0, max_value=20.0, allow_nan=False, allow_infinity=False))
    
    start_direction = draw(st.sampled_from([Direction.UP, Direction.DOWN]))
    current_direction = start_direction
    current_idx = 0
    
    for i in range(size):
        bi_span = draw(st.integers(min_value=5, max_value=10))
        end_idx = current_idx + bi_span - 1
        
        # Generate prices within the overlapping range with some variation
        variation = draw(st.floats(min_value=-3.0, max_value=3.0, allow_nan=False, allow_infinity=False))
        
        if current_direction == Direction.UP:
            start_price = base_low + variation
            end_price = base_high + variation
        else:
            start_price = base_high + variation
            end_price = base_low + variation
        
        # Ensure prices are positive
        start_price = max(1.0, start_price)
        end_price = max(1.0, end_price)
        
        bi = _make_bi(current_idx, end_idx, current_direction, start_price, end_price)
        bis.append(bi)
        
        current_direction = Direction.DOWN if current_direction == Direction.UP else Direction.UP
        current_idx = end_idx
    
    return bis


class TestZhongshuPropertyValidityConstraints:
    """业务模块说明。"""

    @given(overlapping_bi_list_strategy(min_size=3, max_size=12))
    @settings(max_examples=100)
    def test_zhongshu_has_at_least_3_bis(self, bis):
        """业务模块说明。"""
        detector = ZhongshuDetector()
        zhongshus = detector.detect(bis)
        
        for zs in zhongshus:
            assert len(zs.bi_list) >= 3, (
                f"Zhongshu should have >= 3 bis, got {len(zs.bi_list)}"
            )

    @given(overlapping_bi_list_strategy(min_size=3, max_size=12))
    @settings(max_examples=100)
    def test_zhongshu_high_greater_than_low(self, bis):
        """业务模块说明。"""
        detector = ZhongshuDetector()
        zhongshus = detector.detect(bis)
        
        for zs in zhongshus:
            assert zs.high > zs.low, (
                f"Zhongshu high ({zs.high}) should be > low ({zs.low})"
            )

    @given(alternating_bi_list_strategy(min_size=3, max_size=15))
    @settings(max_examples=100)
    def test_zhongshu_overlap_derived_from_bis(self, bis):
        """业务模块说明。"""
        detector = ZhongshuDetector()
        zhongshus = detector.detect(bis)
        
        for zs in zhongshus:
            # Calculate expected overlap from the zhongshu's bis
            bi_highs = [max(bi.start_price, bi.end_price) for bi in zs.bi_list[:3]]
            bi_lows = [min(bi.start_price, bi.end_price) for bi in zs.bi_list[:3]]
            
            expected_high = min(bi_highs)
            expected_low = max(bi_lows)
            
            # The zhongshu's high/low should match the initial 3 bis overlap
            assert zs.high == pytest.approx(expected_high, rel=1e-6), (
                f"Zhongshu high ({zs.high}) should match expected ({expected_high})"
            )
            assert zs.low == pytest.approx(expected_low, rel=1e-6), (
                f"Zhongshu low ({zs.low}) should match expected ({expected_low})"
            )

    @given(overlapping_bi_list_strategy(min_size=3, max_size=12))
    @settings(max_examples=100)
    def test_zhongshu_times_from_bis(self, bis):
        """业务模块说明。"""
        detector = ZhongshuDetector()
        zhongshus = detector.detect(bis)
        
        for zs in zhongshus:
            assert zs.start_time == zs.bi_list[0].start_fractal.timestamp, (
                "Zhongshu start_time should match first bi's start"
            )
            assert zs.end_time == zs.bi_list[-1].end_fractal.timestamp, (
                "Zhongshu end_time should match last bi's end"
            )


class TestZhongshuPropertyTrendProgression:
    """业务模块说明。"""

    @given(st.lists(
        st.tuples(
            st.floats(min_value=1.0, max_value=100.0, allow_nan=False, allow_infinity=False),
            st.floats(min_value=1.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        ),
        min_size=2,
        max_size=5,
    ))
    @settings(max_examples=100)
    def test_up_trend_zhongshu_progression(self, price_pairs):
        """业务模块说明。"""
        # Create zhongshus with progressively higher ranges
        zhongshus = []
        base = 0.0
        for i, (delta_low, delta_high) in enumerate(price_pairs):
            low = base + delta_low
            high = low + abs(delta_high) + 1.0  # Ensure high > low
            zhongshus.append(Zhongshu(high=high, low=low, level=1))
            base = high + 1.0  # Next zhongshu starts above this one
        
        detector = ZhongshuDetector()
        result = detector.classify_trend(zhongshus)
        
        # Verify up trend progression
        for i in range(1, len(result)):
            if result[i].level == 2 and result[i-1].level == 2:
                # This is a trend pair - verify the progression
                assert result[i].low > result[i-1].high, (
                    f"Up trend: zhongshu[{i}].low ({result[i].low}) should be > "
                    f"zhongshu[{i-1}].high ({result[i-1].high})"
                )

    @given(st.lists(
        st.tuples(
            st.floats(min_value=1.0, max_value=100.0, allow_nan=False, allow_infinity=False),
            st.floats(min_value=1.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        ),
        min_size=2,
        max_size=5,
    ))
    @settings(max_examples=100)
    def test_down_trend_zhongshu_progression(self, price_pairs):
        """业务模块说明。"""
        # Create zhongshus with progressively lower ranges
        zhongshus = []
        base = 500.0
        for i, (delta_low, delta_high) in enumerate(price_pairs):
            high = base - delta_low
            low = high - abs(delta_high) - 1.0  # Ensure high > low
            if low < 1.0:
                low = 1.0
                high = low + abs(delta_high) + 1.0
            zhongshus.append(Zhongshu(high=high, low=low, level=1))
            base = low - 1.0  # Next zhongshu ends below this one
        
        detector = ZhongshuDetector()
        result = detector.classify_trend(zhongshus)
        
        # Verify down trend progression
        for i in range(1, len(result)):
            if result[i].level == 2 and result[i-1].level == 2:
                # This is a trend pair - verify the progression
                assert result[i].high < result[i-1].low, (
                    f"Down trend: zhongshu[{i}].high ({result[i].high}) should be < "
                    f"zhongshu[{i-1}].low ({result[i-1].low})"
                )

    @given(st.lists(
        st.tuples(
            st.floats(min_value=10.0, max_value=50.0, allow_nan=False, allow_infinity=False),
            st.floats(min_value=5.0, max_value=20.0, allow_nan=False, allow_infinity=False),
        ),
        min_size=2,
        max_size=5,
    ))
    @settings(max_examples=100)
    def test_overlapping_zhongshus_pair_not_trend(self, price_pairs):
        """业务模块说明。"""
        # Create overlapping zhongshus (not a trend)
        zhongshus = []
        for low, spread in price_pairs:
            high = low + spread
            zhongshus.append(Zhongshu(high=high, low=low, level=1))
        
        detector = ZhongshuDetector()
        result = detector.classify_trend(zhongshus)
        
        # Check each pair - if they overlap, the trend classification should not
        # be due to THIS pair's relationship
        for i in range(1, len(result)):
            prev = result[i-1]
            curr = result[i]
            
            # Check if this pair overlaps
            is_up_trend = curr.low > prev.high
            is_down_trend = curr.high < prev.low
            
            # If they don't form a trend (overlap), verify the logic is correct
            if not is_up_trend and not is_down_trend:
                # This specific pair overlaps - they should not BOTH be level 2
                # UNLESS one of them forms a trend with another zhongshu
                # For a simple 2-zhongshu case, neither should be level 2
                if len(result) == 2:
                    assert prev.level == 1 or curr.level == 1, (
                        f"Two overlapping zhongshus should not both be trend level 2"
                    )

    @given(alternating_bi_list_strategy(min_size=6, max_size=15))
    @settings(max_examples=100)
    def test_classify_trend_does_not_mutate_input(self, bis):
        """业务模块说明。"""
        detector = ZhongshuDetector()
        zhongshus = detector.detect(bis)
        
        if len(zhongshus) < 2:
            return  # Need at least 2 for trend classification
        
        # Record original levels
        original_levels = [zs.level for zs in zhongshus]
        
        # Call classify_trend
        detector.classify_trend(zhongshus)
        
        # Verify original list unchanged
        for i, zs in enumerate(zhongshus):
            assert zs.level == original_levels[i], (
                f"classify_trend should not mutate input: "
                f"zhongshu[{i}].level changed from {original_levels[i]} to {zs.level}"
            )
