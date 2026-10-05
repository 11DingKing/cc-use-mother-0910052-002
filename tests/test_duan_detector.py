"""业务模块说明。"""

from datetime import datetime, timedelta
from typing import List

import pytest

from app.chan.duan_detector import DuanDetector
from app.chan.models import Direction, FractalType, MergedCandle, Fractal, Bi, Duan


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


def _make_zigzag_bis_up(
    n: int,
    base_low: float = 10.0,
    step: float = 2.0,
    bi_span: int = 6,
) -> List[Bi]:
    """业务模块说明。"""
    bis: List[Bi] = []
    idx = 0
    for i in range(n):
        if i % 2 == 0:
            # UP bi
            start_price = base_low + i * step
            end_price = base_low + (i + 1) * step + step
            direction = Direction.UP
        else:
            # DOWN bi (retracement, but higher lows)
            start_price = base_low + i * step + step
            end_price = base_low + i * step
            direction = Direction.DOWN

        bi = _make_bi(idx, idx + bi_span - 1, direction, start_price, end_price)
        bis.append(bi)
        idx += bi_span
    return bis


def _make_zigzag_bis_down(
    n: int,
    base_high: float = 30.0,
    step: float = 2.0,
    bi_span: int = 6,
) -> List[Bi]:
    """业务模块说明。"""
    bis: List[Bi] = []
    idx = 0
    for i in range(n):
        if i % 2 == 0:
            # DOWN bi
            start_price = base_high - i * step
            end_price = base_high - (i + 1) * step - step
            direction = Direction.DOWN
        else:
            # UP bi (retracement, but lower highs)
            start_price = base_high - i * step - step
            end_price = base_high - i * step
            direction = Direction.UP

        bi = _make_bi(idx, idx + bi_span - 1, direction, start_price, end_price)
        bis.append(bi)
        idx += bi_span
    return bis


# ---------------------------------------------------------------------------
# Tests for DuanDetector.detect()
# ---------------------------------------------------------------------------

class TestDuanDetectorDetect:
    def setup_method(self):
        self.detector = DuanDetector()

    def test_empty_bi_list(self):
        """业务模块说明。"""
        assert self.detector.detect([]) == []

    def test_single_bi(self):
        """业务模块说明。"""
        bis = [_make_bi(0, 5, Direction.UP, 10.0, 15.0)]
        assert self.detector.detect(bis) == []

    def test_two_bis(self):
        """业务模块说明。"""
        bis = [
            _make_bi(0, 5, Direction.UP, 10.0, 15.0),
            _make_bi(5, 10, Direction.DOWN, 15.0, 12.0),
        ]
        assert self.detector.detect(bis) == []

    def test_minimum_3_bis_upward_with_fractal(self):
        """业务模块说明。"""
        # Upward segment: UP, DOWN, UP, DOWN, UP
        # Characteristic sequence (indices 0, 2, 4): three UP bis
        # For top fractal: mid.high > left.high and mid.high > right.high
        bis = [
            _make_bi(0, 5, Direction.UP, 10.0, 20.0),     # char[0]: h=20, l=10
            _make_bi(5, 10, Direction.DOWN, 20.0, 15.0),
            _make_bi(10, 15, Direction.UP, 15.0, 25.0),    # char[1]: h=25, l=15
            _make_bi(15, 20, Direction.DOWN, 25.0, 18.0),
            _make_bi(20, 25, Direction.UP, 18.0, 22.0),    # char[2]: h=22, l=18
        ]
        # char seq: (20,10), (25,15), (22,18)
        # Top fractal: mid(25,15) > left(20,10) and mid(25,15) > right(22,18)
        # 25>20 ✓, 25>22 ✓, 15>10 ✓, 15>18 ✗ → NOT a top fractal (strict)
        # Actually: mid.high > left.high (25>20 ✓) AND mid.high > right.high (25>22 ✓)
        #           mid.low > left.low (15>10 ✓) AND mid.low > right.low (18? no, 15<18)
        # So this doesn't form a top fractal. Let me adjust.

        # Adjusted: make the 3rd UP bi have lower low
        bis = [
            _make_bi(0, 5, Direction.UP, 10.0, 20.0),     # char[0]: h=20, l=10
            _make_bi(5, 10, Direction.DOWN, 20.0, 15.0),
            _make_bi(10, 15, Direction.UP, 15.0, 25.0),    # char[1]: h=25, l=15
            _make_bi(15, 20, Direction.DOWN, 25.0, 12.0),
            _make_bi(20, 25, Direction.UP, 12.0, 22.0),    # char[2]: h=22, l=12
        ]
        # char seq: (20,10), (25,15), (22,12)
        # Top fractal check: mid.high(25) > left.high(20) ✓, mid.high(25) > right.high(22) ✓
        #                     mid.low(15) > left.low(10) ✓, mid.low(15) > right.low(12) ✓
        # → Top fractal confirmed!

        result = self.detector.detect(bis)
        assert len(result) >= 1
        duan = result[0]
        assert duan.direction == Direction.UP
        assert len(duan.bi_list) >= 3

    def test_minimum_3_bis_downward_with_fractal(self):
        """业务模块说明。"""
        bis = [
            _make_bi(0, 5, Direction.DOWN, 30.0, 20.0),     # char[0]: h=30, l=20
            _make_bi(5, 10, Direction.UP, 20.0, 25.0),
            _make_bi(10, 15, Direction.DOWN, 25.0, 15.0),    # char[1]: h=25, l=15
            _make_bi(15, 20, Direction.UP, 15.0, 28.0),
            _make_bi(20, 25, Direction.DOWN, 28.0, 18.0),    # char[2]: h=28, l=18
        ]
        # char seq: (30,20), (25,15), (28,18)
        # Bottom fractal check: mid.low(15) < left.low(20) ✓, mid.low(15) < right.low(18) ✓
        #                        mid.high(25) < left.high(30) ✓, mid.high(25) < right.high(28) ✓
        # → Bottom fractal confirmed!

        result = self.detector.detect(bis)
        assert len(result) >= 1
        duan = result[0]
        assert duan.direction == Direction.DOWN
        assert len(duan.bi_list) >= 3

    def test_duan_has_correct_prices_upward(self):
        """业务模块说明。"""
        bis = [
            _make_bi(0, 5, Direction.UP, 10.0, 20.0),
            _make_bi(5, 10, Direction.DOWN, 20.0, 15.0),
            _make_bi(10, 15, Direction.UP, 15.0, 25.0),
            _make_bi(15, 20, Direction.DOWN, 25.0, 12.0),
            _make_bi(20, 25, Direction.UP, 12.0, 22.0),
        ]
        result = self.detector.detect(bis)
        assert len(result) >= 1
        duan = result[0]
        assert duan.direction == Direction.UP
        # Start price should be the low of the first bi
        assert duan.start_price == 10.0

    def test_duan_has_correct_prices_downward(self):
        """业务模块说明。"""
        bis = [
            _make_bi(0, 5, Direction.DOWN, 30.0, 20.0),
            _make_bi(5, 10, Direction.UP, 20.0, 25.0),
            _make_bi(10, 15, Direction.DOWN, 25.0, 15.0),
            _make_bi(15, 20, Direction.UP, 15.0, 28.0),
            _make_bi(20, 25, Direction.DOWN, 28.0, 18.0),
        ]
        result = self.detector.detect(bis)
        assert len(result) >= 1
        duan = result[0]
        assert duan.direction == Direction.DOWN
        # Start price should be the high of the first bi
        assert duan.start_price == 30.0

    def test_no_fractal_in_characteristic_sequence(self):
        """业务模块说明。"""
        # Create 3 UP bis with monotonically increasing highs and lows
        # char seq will be monotonically increasing → no top fractal
        bis = [
            _make_bi(0, 5, Direction.UP, 10.0, 15.0),     # char[0]: h=15, l=10
            _make_bi(5, 10, Direction.DOWN, 15.0, 12.0),
            _make_bi(10, 15, Direction.UP, 12.0, 18.0),    # char[1]: h=18, l=12
        ]
        # Only 2 elements in char seq, need 3 for fractal
        result = self.detector.detect(bis)
        assert len(result) == 0

    def test_duan_bi_list_populated(self):
        """业务模块说明。"""
        bis = [
            _make_bi(0, 5, Direction.UP, 10.0, 20.0),
            _make_bi(5, 10, Direction.DOWN, 20.0, 15.0),
            _make_bi(10, 15, Direction.UP, 15.0, 25.0),
            _make_bi(15, 20, Direction.DOWN, 25.0, 12.0),
            _make_bi(20, 25, Direction.UP, 12.0, 22.0),
        ]
        result = self.detector.detect(bis)
        assert len(result) >= 1
        for duan in result:
            assert len(duan.bi_list) >= 3
            assert duan.start_bi is duan.bi_list[0]
            assert duan.end_bi is duan.bi_list[-1]

    def test_multiple_duans_from_long_sequence(self):
        """业务模块说明。"""
        # First upward segment (5 bis)
        bis = [
            _make_bi(0, 5, Direction.UP, 10.0, 20.0),
            _make_bi(5, 10, Direction.DOWN, 20.0, 15.0),
            _make_bi(10, 15, Direction.UP, 15.0, 25.0),
            _make_bi(15, 20, Direction.DOWN, 25.0, 12.0),
            _make_bi(20, 25, Direction.UP, 12.0, 22.0),
            # Then downward segment (5 bis)
            _make_bi(25, 30, Direction.DOWN, 22.0, 12.0),
            _make_bi(30, 35, Direction.UP, 12.0, 18.0),
            _make_bi(35, 40, Direction.DOWN, 18.0, 8.0),
            _make_bi(40, 45, Direction.UP, 8.0, 15.0),
            _make_bi(45, 50, Direction.DOWN, 15.0, 5.0),
        ]
        result = self.detector.detect(bis)
        # Should find at least one duan
        assert len(result) >= 1

    def test_duan_direction_matches_first_bi(self):
        """业务模块说明。"""
        bis = [
            _make_bi(0, 5, Direction.UP, 10.0, 20.0),
            _make_bi(5, 10, Direction.DOWN, 20.0, 15.0),
            _make_bi(10, 15, Direction.UP, 15.0, 25.0),
            _make_bi(15, 20, Direction.DOWN, 25.0, 12.0),
            _make_bi(20, 25, Direction.UP, 12.0, 22.0),
        ]
        result = self.detector.detect(bis)
        if result:
            assert result[0].direction == bis[0].direction


# ---------------------------------------------------------------------------
# Tests for DuanDetector.update()
# ---------------------------------------------------------------------------

class TestDuanDetectorUpdate:
    def setup_method(self):
        self.detector = DuanDetector()

    def test_empty_existing_falls_back_to_detect(self):
        """业务模块说明。"""
        bis = [
            _make_bi(0, 5, Direction.UP, 10.0, 20.0),
            _make_bi(5, 10, Direction.DOWN, 20.0, 15.0),
            _make_bi(10, 15, Direction.UP, 15.0, 25.0),
            _make_bi(15, 20, Direction.DOWN, 25.0, 12.0),
            _make_bi(20, 25, Direction.UP, 12.0, 22.0),
        ]
        result = self.detector.update(bis, [])
        full = self.detector.detect(bis)
        assert len(result) == len(full)

    def test_update_with_new_bis_added(self):
        """业务模块说明。"""
        bis_v1 = [
            _make_bi(0, 5, Direction.UP, 10.0, 20.0),
            _make_bi(5, 10, Direction.DOWN, 20.0, 15.0),
            _make_bi(10, 15, Direction.UP, 15.0, 25.0),
            _make_bi(15, 20, Direction.DOWN, 25.0, 12.0),
            _make_bi(20, 25, Direction.UP, 12.0, 22.0),
        ]
        existing = self.detector.detect(bis_v1)

        # Add more bis
        bis_v2 = bis_v1 + [
            _make_bi(25, 30, Direction.DOWN, 22.0, 12.0),
            _make_bi(30, 35, Direction.UP, 12.0, 18.0),
            _make_bi(35, 40, Direction.DOWN, 18.0, 8.0),
            _make_bi(40, 45, Direction.UP, 8.0, 15.0),
            _make_bi(45, 50, Direction.DOWN, 15.0, 5.0),
        ]
        result = self.detector.update(bis_v2, existing)
        full = self.detector.detect(bis_v2)

        # Update result should match full detect
        assert len(result) == len(full)

    def test_update_with_insufficient_bis(self):
        """业务模块说明。"""
        bis = [_make_bi(0, 5, Direction.UP, 10.0, 15.0)]
        result = self.detector.update(bis, [])
        assert result == []

    def test_update_preserves_valid_duans(self):
        """业务模块说明。"""
        bis = [
            _make_bi(0, 5, Direction.UP, 10.0, 20.0),
            _make_bi(5, 10, Direction.DOWN, 20.0, 15.0),
            _make_bi(10, 15, Direction.UP, 15.0, 25.0),
            _make_bi(15, 20, Direction.DOWN, 25.0, 12.0),
            _make_bi(20, 25, Direction.UP, 12.0, 22.0),
        ]
        existing = self.detector.detect(bis)

        if existing:
            # Update with same bis should return same result
            result = self.detector.update(bis, existing)
            assert len(result) == len(existing)


# ---------------------------------------------------------------------------
# Tests for characteristic sequence logic
# ---------------------------------------------------------------------------

class TestCharacteristicSequence:
    def setup_method(self):
        self.detector = DuanDetector()

    def test_build_characteristic_sequence_upward(self):
        """业务模块说明。"""
        bis = [
            _make_bi(0, 5, Direction.UP, 10.0, 20.0),     # included (idx 0)
            _make_bi(5, 10, Direction.DOWN, 20.0, 15.0),   # excluded (idx 1)
            _make_bi(10, 15, Direction.UP, 15.0, 25.0),    # included (idx 2)
        ]
        char_seq = self.detector._build_characteristic_sequence(
            bis, Direction.UP,
        )
        assert len(char_seq) == 2
        # First element: UP bi (10→20), high=20, low=10
        assert char_seq[0] == (20.0, 10.0)
        # Second element: UP bi (15→25), high=25, low=15
        assert char_seq[1] == (25.0, 15.0)

    def test_build_characteristic_sequence_downward(self):
        """业务模块说明。"""
        bis = [
            _make_bi(0, 5, Direction.DOWN, 30.0, 20.0),   # included (idx 0)
            _make_bi(5, 10, Direction.UP, 20.0, 25.0),     # excluded (idx 1)
            _make_bi(10, 15, Direction.DOWN, 25.0, 15.0),  # included (idx 2)
        ]
        char_seq = self.detector._build_characteristic_sequence(
            bis, Direction.DOWN,
        )
        assert len(char_seq) == 2
        # First element: DOWN bi (30→20), high=30, low=20
        assert char_seq[0] == (30.0, 20.0)
        # Second element: DOWN bi (25→15), high=25, low=15
        assert char_seq[1] == (25.0, 15.0)

    def test_top_fractal_in_characteristic_sequence(self):
        """业务模块说明。"""
        bis = [
            _make_bi(0, 5, Direction.UP, 10.0, 20.0),     # char[0]: (20, 10)
            _make_bi(5, 10, Direction.DOWN, 20.0, 15.0),
            _make_bi(10, 15, Direction.UP, 15.0, 25.0),    # char[1]: (25, 15)
            _make_bi(15, 20, Direction.DOWN, 25.0, 12.0),
            _make_bi(20, 25, Direction.UP, 12.0, 22.0),    # char[2]: (22, 12)
        ]
        # Top fractal: mid(25,15) > left(20,10) and mid(25,15) > right(22,12)
        assert self.detector._has_characteristic_fractal(
            bis, Direction.UP,
        ) is True

    def test_bottom_fractal_in_characteristic_sequence(self):
        """业务模块说明。"""
        bis = [
            _make_bi(0, 5, Direction.DOWN, 30.0, 20.0),     # char[0]: (30, 20)
            _make_bi(5, 10, Direction.UP, 20.0, 25.0),
            _make_bi(10, 15, Direction.DOWN, 25.0, 15.0),    # char[1]: (25, 15)
            _make_bi(15, 20, Direction.UP, 15.0, 28.0),
            _make_bi(20, 25, Direction.DOWN, 28.0, 18.0),    # char[2]: (28, 18)
        ]
        # Bottom fractal: mid(25,15) < left(30,20) and mid(25,15) < right(28,18)
        assert self.detector._has_characteristic_fractal(
            bis, Direction.DOWN,
        ) is True

    def test_no_fractal_monotonic_up(self):
        """业务模块说明。"""
        bis = [
            _make_bi(0, 5, Direction.UP, 10.0, 15.0),     # char[0]: (15, 10)
            _make_bi(5, 10, Direction.DOWN, 15.0, 12.0),
            _make_bi(10, 15, Direction.UP, 12.0, 20.0),    # char[1]: (20, 12)
            _make_bi(15, 20, Direction.DOWN, 20.0, 16.0),
            _make_bi(20, 25, Direction.UP, 16.0, 25.0),    # char[2]: (25, 16)
        ]
        # Monotonically increasing: (15,10), (20,12), (25,16) → no top fractal
        assert self.detector._has_characteristic_fractal(
            bis, Direction.UP,
        ) is False

    def test_no_fractal_monotonic_down(self):
        """业务模块说明。"""
        bis = [
            _make_bi(0, 5, Direction.DOWN, 30.0, 25.0),   # char[0]: (30, 25)
            _make_bi(5, 10, Direction.UP, 25.0, 28.0),
            _make_bi(10, 15, Direction.DOWN, 28.0, 20.0),  # char[1]: (28, 20)
            _make_bi(15, 20, Direction.UP, 20.0, 23.0),
            _make_bi(20, 25, Direction.DOWN, 23.0, 15.0),  # char[2]: (23, 15)
        ]
        # Monotonically decreasing: (30,25), (28,20), (23,15) → no bottom fractal
        assert self.detector._has_characteristic_fractal(
            bis, Direction.DOWN,
        ) is False

    def test_insufficient_char_seq_length(self):
        """业务模块说明。"""
        bis = [
            _make_bi(0, 5, Direction.UP, 10.0, 20.0),
            _make_bi(5, 10, Direction.DOWN, 20.0, 15.0),
            _make_bi(10, 15, Direction.UP, 15.0, 25.0),
        ]
        # Only 2 elements in char seq
        assert self.detector._has_characteristic_fractal(
            bis, Direction.UP,
        ) is False


# ---------------------------------------------------------------------------
# Property-Based Tests (Hypothesis)
# Property 7: 段有效性约束
# Validates: Requirements 4.1, 4.2
# ---------------------------------------------------------------------------

from hypothesis import given, strategies as st, settings, assume


@st.composite
def bi_strategy(draw, start_idx=None, direction=None):
    """业务模块说明。"""
    if start_idx is None:
        start_idx = draw(st.integers(min_value=0, max_value=500))
    if direction is None:
        direction = draw(st.sampled_from([Direction.UP, Direction.DOWN]))
    
    bi_span = draw(st.integers(min_value=5, max_value=10))
    end_idx = start_idx + bi_span - 1
    
    start_price = draw(st.floats(min_value=1.0, max_value=500.0, allow_nan=False, allow_infinity=False))
    end_price = draw(st.floats(min_value=1.0, max_value=500.0, allow_nan=False, allow_infinity=False))
    
    return _make_bi(start_idx, end_idx, direction, start_price, end_price)


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


class TestDuanPropertyValidityConstraints:
    """业务模块说明。"""

    @given(alternating_bi_list_strategy(min_size=5, max_size=15))
    @settings(max_examples=100)
    def test_duan_has_at_least_3_bis(self, bis):
        """业务模块说明。"""
        detector = DuanDetector()
        duans = detector.detect(bis)
        
        for duan in duans:
            assert len(duan.bi_list) >= 3, (
                f"Duan should have >= 3 bis, got {len(duan.bi_list)}"
            )

    @given(alternating_bi_list_strategy(min_size=5, max_size=15))
    @settings(max_examples=100)
    def test_duan_has_characteristic_fractal(self, bis):
        """业务模块说明。"""
        detector = DuanDetector()
        duans = detector.detect(bis)
        
        for duan in duans:
            # Verify the characteristic sequence has a fractal
            has_fractal = detector._has_characteristic_fractal(
                duan.bi_list, duan.direction
            )
            assert has_fractal, (
                f"Duan should have characteristic fractal, "
                f"direction={duan.direction}, bi_count={len(duan.bi_list)}"
            )

    @given(alternating_bi_list_strategy(min_size=5, max_size=15))
    @settings(max_examples=100)
    def test_duan_direction_matches_first_bi(self, bis):
        """业务模块说明。"""
        detector = DuanDetector()
        duans = detector.detect(bis)
        
        for duan in duans:
            assert duan.direction == duan.bi_list[0].direction, (
                f"Duan direction ({duan.direction}) should match "
                f"first bi direction ({duan.bi_list[0].direction})"
            )

    @given(alternating_bi_list_strategy(min_size=5, max_size=15))
    @settings(max_examples=100)
    def test_duan_start_end_bi_consistency(self, bis):
        """业务模块说明。"""
        detector = DuanDetector()
        duans = detector.detect(bis)
        
        for duan in duans:
            assert duan.start_bi is duan.bi_list[0], (
                "Duan start_bi should be first element of bi_list"
            )
            assert duan.end_bi is duan.bi_list[-1], (
                "Duan end_bi should be last element of bi_list"
            )

    @given(alternating_bi_list_strategy(min_size=5, max_size=15))
    @settings(max_examples=100)
    def test_duan_prices_valid(self, bis):
        """业务模块说明。"""
        detector = DuanDetector()
        duans = detector.detect(bis)
        
        for duan in duans:
            # Collect all prices from the duan's bis
            all_prices = []
            for bi in duan.bi_list:
                all_prices.extend([bi.start_price, bi.end_price])
            
            min_price = min(all_prices)
            max_price = max(all_prices)
            
            # Duan prices should be within the range of its bis
            assert min_price <= duan.start_price <= max_price
            assert min_price <= duan.end_price <= max_price
