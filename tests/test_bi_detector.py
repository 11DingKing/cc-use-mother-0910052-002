"""业务模块说明。"""

from datetime import datetime, timedelta
from typing import List

import pytest

from app.chan.bi_detector import BiDetector
from app.chan.models import Direction, FractalType, MergedCandle, Fractal, Bi


def _make_merged(index: int, high: float, low: float) -> MergedCandle:
    return MergedCandle(
        timestamp=datetime(2024, 1, 1) + timedelta(days=index),
        high=high, low=low,
        start_index=index, end_index=index,
        direction=Direction.UP,
    )


def _make_fractal(
    ftype: FractalType, index: int, price: float,
) -> Fractal:
    return Fractal(
        type=ftype,
        timestamp=datetime(2024, 1, 1) + timedelta(days=index),
        price=price,
        candle_index=index,
        candles=[],
    )


class TestBiDetectorDetect:
    def setup_method(self):
        self.detector = BiDetector()
        self.merged = [_make_merged(i, 10.0 + i, 8.0 + i) for i in range(20)]

    def test_empty_fractals(self):
        assert self.detector.detect([], self.merged) == []

    def test_single_fractal(self):
        fractals = [_make_fractal(FractalType.TOP, 1, 12.0)]
        assert self.detector.detect(fractals, self.merged) == []

    def test_basic_down_bi(self):
        """业务模块说明。"""
        fractals = [
            _make_fractal(FractalType.TOP, 0, 15.0),
            _make_fractal(FractalType.BOTTOM, 5, 8.0),
        ]
        result = self.detector.detect(fractals, self.merged)
        assert len(result) == 1
        bi = result[0]
        assert bi.direction == Direction.DOWN
        assert bi.candle_count == 6
        assert bi.start_price == 15.0
        assert bi.end_price == 8.0

    def test_basic_up_bi(self):
        """业务模块说明。"""
        fractals = [
            _make_fractal(FractalType.BOTTOM, 0, 8.0),
            _make_fractal(FractalType.TOP, 6, 15.0),
        ]
        result = self.detector.detect(fractals, self.merged)
        assert len(result) == 1
        assert result[0].direction == Direction.UP
        assert result[0].candle_count == 7

    def test_insufficient_candle_count_skipped(self):
        """业务模块说明。"""
        fractals = [
            _make_fractal(FractalType.TOP, 0, 15.0),
            _make_fractal(FractalType.BOTTOM, 3, 8.0),  # only 4 candles
        ]
        result = self.detector.detect(fractals, self.merged)
        assert len(result) == 0

    def test_exactly_5_candles(self):
        """业务模块说明。"""
        fractals = [
            _make_fractal(FractalType.TOP, 0, 15.0),
            _make_fractal(FractalType.BOTTOM, 4, 8.0),  # 5 candles
        ]
        result = self.detector.detect(fractals, self.merged)
        assert len(result) == 1
        assert result[0].candle_count == 5

    def test_multiple_bis(self):
        """业务模块说明。"""
        fractals = [
            _make_fractal(FractalType.TOP, 0, 15.0),
            _make_fractal(FractalType.BOTTOM, 5, 8.0),
            _make_fractal(FractalType.TOP, 10, 16.0),
            _make_fractal(FractalType.BOTTOM, 15, 7.0),
        ]
        result = self.detector.detect(fractals, self.merged)
        assert len(result) == 3
        assert result[0].direction == Direction.DOWN
        assert result[1].direction == Direction.UP
        assert result[2].direction == Direction.DOWN

    def test_consecutive_tops_takes_highest(self):
        """业务模块说明。"""
        fractals = [
            _make_fractal(FractalType.BOTTOM, 0, 8.0),
            _make_fractal(FractalType.TOP, 5, 14.0),
            _make_fractal(FractalType.TOP, 7, 16.0),  # higher, should replace
            _make_fractal(FractalType.BOTTOM, 12, 7.0),
        ]
        result = self.detector.detect(fractals, self.merged)
        # After filtering: BOTTOM(0,8) → TOP(7,16) → BOTTOM(12,7)
        assert len(result) == 2
        assert result[0].end_price == 16.0  # took the higher top

    def test_consecutive_bottoms_takes_lowest(self):
        """业务模块说明。"""
        fractals = [
            _make_fractal(FractalType.TOP, 0, 15.0),
            _make_fractal(FractalType.BOTTOM, 5, 9.0),
            _make_fractal(FractalType.BOTTOM, 7, 7.0),  # lower, should replace
            _make_fractal(FractalType.TOP, 12, 16.0),
        ]
        result = self.detector.detect(fractals, self.merged)
        assert len(result) == 2
        assert result[0].end_price == 7.0  # took the lower bottom

    def test_consecutive_tops_keeps_first_if_higher(self):
        """业务模块说明。"""
        fractals = [
            _make_fractal(FractalType.BOTTOM, 0, 8.0),
            _make_fractal(FractalType.TOP, 5, 18.0),  # higher
            _make_fractal(FractalType.TOP, 7, 14.0),
            _make_fractal(FractalType.BOTTOM, 12, 7.0),
        ]
        result = self.detector.detect(fractals, self.merged)
        assert len(result) == 2
        assert result[0].end_price == 18.0


class TestBiDetectorUpdate:
    def setup_method(self):
        self.detector = BiDetector()
        self.merged = [_make_merged(i, 10.0 + i, 8.0 + i) for i in range(30)]

    def test_empty_existing_falls_back_to_detect(self):
        fractals = [
            _make_fractal(FractalType.TOP, 0, 15.0),
            _make_fractal(FractalType.BOTTOM, 5, 8.0),
        ]
        result = self.detector.update(fractals, [], self.merged)
        full = self.detector.detect(fractals, self.merged)
        assert len(result) == len(full)

    def test_incremental_adds_new_bi(self):
        fractals_v1 = [
            _make_fractal(FractalType.TOP, 0, 15.0),
            _make_fractal(FractalType.BOTTOM, 5, 8.0),
        ]
        existing = self.detector.detect(fractals_v1, self.merged)
        assert len(existing) == 1

        fractals_v2 = fractals_v1 + [
            _make_fractal(FractalType.TOP, 10, 16.0),
        ]
        result = self.detector.update(fractals_v2, existing, self.merged)
        assert len(result) == 2

    def test_update_matches_full_detect(self):
        all_fractals = [
            _make_fractal(FractalType.TOP, 0, 15.0),
            _make_fractal(FractalType.BOTTOM, 5, 8.0),
            _make_fractal(FractalType.TOP, 10, 16.0),
            _make_fractal(FractalType.BOTTOM, 15, 7.0),
            _make_fractal(FractalType.TOP, 20, 17.0),
        ]

        # Detect first 2
        existing = self.detector.detect(all_fractals[:2], self.merged)
        # Update with all
        result = self.detector.update(all_fractals, existing, self.merged)
        full = self.detector.detect(all_fractals, self.merged)

        assert len(result) == len(full)
        for r, f in zip(result, full):
            assert r.direction == f.direction
            assert r.start_price == f.start_price
            assert r.end_price == f.end_price


# ---------------------------------------------------------------------------
# Property-Based Tests (Hypothesis)
# Property 4: 笔有效性约束
# Property 5: 连续同类型分型极值选取
# Validates: Requirements 3.1, 3.2, 3.3, 3.4
# ---------------------------------------------------------------------------

from hypothesis import given, strategies as st, settings, assume


@st.composite
def fractal_strategy(draw, index=None):
    """业务模块说明。"""
    if index is None:
        index = draw(st.integers(min_value=0, max_value=100))
    
    ftype = draw(st.sampled_from([FractalType.TOP, FractalType.BOTTOM]))
    price = draw(st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False))
    
    return Fractal(
        type=ftype,
        timestamp=datetime(2024, 1, 1) + timedelta(days=index),
        price=price,
        candle_index=index,
        candles=[],
    )


@st.composite
def alternating_fractal_list_strategy(draw, min_size=2, max_size=20):
    """业务模块说明。"""
    size = draw(st.integers(min_value=min_size, max_value=max_size))
    fractals = []
    
    # Start with random type
    start_type = draw(st.sampled_from([FractalType.TOP, FractalType.BOTTOM]))
    current_type = start_type
    current_index = 0
    
    for i in range(size):
        price = draw(st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False))
        
        f = Fractal(
            type=current_type,
            timestamp=datetime(2024, 1, 1) + timedelta(days=current_index),
            price=price,
            candle_index=current_index,
            candles=[],
        )
        fractals.append(f)
        
        # Alternate type and ensure >= 5 candles between fractals
        current_type = FractalType.BOTTOM if current_type == FractalType.TOP else FractalType.TOP
        current_index += draw(st.integers(min_value=5, max_value=10))
    
    return fractals


@st.composite
def fractal_list_with_consecutive_same_type(draw, min_size=4, max_size=15):
    """业务模块说明。"""
    size = draw(st.integers(min_value=min_size, max_value=max_size))
    fractals = []
    current_index = 0
    
    for i in range(size):
        ftype = draw(st.sampled_from([FractalType.TOP, FractalType.BOTTOM]))
        price = draw(st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False))
        
        f = Fractal(
            type=ftype,
            timestamp=datetime(2024, 1, 1) + timedelta(days=current_index),
            price=price,
            candle_index=current_index,
            candles=[],
        )
        fractals.append(f)
        current_index += draw(st.integers(min_value=5, max_value=10))
    
    return fractals


class TestBiPropertyValidityConstraints:
    """业务模块说明。"""

    @given(alternating_fractal_list_strategy(min_size=2, max_size=20))
    @settings(max_examples=100)
    def test_bi_has_different_fractal_types(self, fractals):
        """业务模块说明。"""
        detector = BiDetector()
        merged = [_make_merged(i, 10.0 + i, 8.0 + i) for i in range(200)]
        bis = detector.detect(fractals, merged)
        
        for bi in bis:
            assert bi.start_fractal.type != bi.end_fractal.type, (
                f"Bi should have different fractal types: "
                f"start={bi.start_fractal.type}, end={bi.end_fractal.type}"
            )

    @given(alternating_fractal_list_strategy(min_size=2, max_size=20))
    @settings(max_examples=100)
    def test_bi_has_at_least_5_candles(self, fractals):
        """业务模块说明。"""
        detector = BiDetector()
        merged = [_make_merged(i, 10.0 + i, 8.0 + i) for i in range(200)]
        bis = detector.detect(fractals, merged)
        
        for bi in bis:
            assert bi.candle_count >= 5, (
                f"Bi should have >= 5 candles, got {bi.candle_count}"
            )

    @given(alternating_fractal_list_strategy(min_size=2, max_size=20))
    @settings(max_examples=100)
    def test_bi_direction_matches_fractal_types(self, fractals):
        """业务模块说明。"""
        detector = BiDetector()
        merged = [_make_merged(i, 10.0 + i, 8.0 + i) for i in range(200)]
        bis = detector.detect(fractals, merged)
        
        for bi in bis:
            if (bi.start_fractal.type == FractalType.BOTTOM 
                    and bi.end_fractal.type == FractalType.TOP):
                assert bi.direction == Direction.UP
            elif (bi.start_fractal.type == FractalType.TOP 
                    and bi.end_fractal.type == FractalType.BOTTOM):
                assert bi.direction == Direction.DOWN


class TestBiPropertyConsecutiveSameTypeExtreme:
    """业务模块说明。"""

    @given(fractal_list_with_consecutive_same_type(min_size=4, max_size=15))
    @settings(max_examples=100)
    def test_consecutive_same_type_filtered_correctly(self, fractals):
        """业务模块说明。"""
        detector = BiDetector()
        filtered = detector._filter_consecutive_same_type(fractals)
        
        for i in range(len(filtered) - 1):
            assert filtered[i].type != filtered[i + 1].type, (
                f"Adjacent fractals should have different types after filtering: "
                f"filtered[{i}].type={filtered[i].type}, "
                f"filtered[{i+1}].type={filtered[i+1].type}"
            )

    def test_consecutive_tops_selects_highest(self):
        """业务模块说明。"""
        fractals = [
            _make_fractal(FractalType.BOTTOM, 0, 8.0),
            _make_fractal(FractalType.TOP, 5, 14.0),
            _make_fractal(FractalType.TOP, 10, 18.0),  # highest
            _make_fractal(FractalType.TOP, 15, 16.0),
            _make_fractal(FractalType.BOTTOM, 20, 7.0),
        ]
        detector = BiDetector()
        filtered = detector._filter_consecutive_same_type(fractals)
        
        # Should have: BOTTOM(0,8) → TOP(10,18) → BOTTOM(20,7)
        assert len(filtered) == 3
        top_fractal = [f for f in filtered if f.type == FractalType.TOP][0]
        assert top_fractal.price == 18.0

    def test_consecutive_bottoms_selects_lowest(self):
        """业务模块说明。"""
        fractals = [
            _make_fractal(FractalType.TOP, 0, 15.0),
            _make_fractal(FractalType.BOTTOM, 5, 9.0),
            _make_fractal(FractalType.BOTTOM, 10, 6.0),  # lowest
            _make_fractal(FractalType.BOTTOM, 15, 8.0),
            _make_fractal(FractalType.TOP, 20, 16.0),
        ]
        detector = BiDetector()
        filtered = detector._filter_consecutive_same_type(fractals)
        
        # Should have: TOP(0,15) → BOTTOM(10,6) → TOP(20,16)
        assert len(filtered) == 3
        bottom_fractal = [f for f in filtered if f.type == FractalType.BOTTOM][0]
        assert bottom_fractal.price == 6.0

    @given(fractal_list_with_consecutive_same_type(min_size=4, max_size=15))
    @settings(max_examples=100)
    def test_filtered_preserves_extreme_values(self, fractals):
        """业务模块说明。"""
        detector = BiDetector()
        filtered = detector._filter_consecutive_same_type(fractals)
        
        # Group consecutive same-type fractals from original
        groups = []
        current_group = [fractals[0]]
        for i in range(1, len(fractals)):
            if fractals[i].type == current_group[-1].type:
                current_group.append(fractals[i])
            else:
                groups.append(current_group)
                current_group = [fractals[i]]
        groups.append(current_group)
        
        # For each group, verify the extreme is in filtered
        for group in groups:
            if group[0].type == FractalType.TOP:
                extreme_price = max(f.price for f in group)
            else:
                extreme_price = min(f.price for f in group)
            
            # Find the corresponding fractal in filtered
            matching = [f for f in filtered 
                       if f.type == group[0].type 
                       and any(g.candle_index == f.candle_index for g in group)]
            
            if matching:
                assert matching[0].price == extreme_price, (
                    f"Filtered should contain extreme value {extreme_price}, "
                    f"got {matching[0].price}"
                )
