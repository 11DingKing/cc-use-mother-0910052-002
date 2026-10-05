"""业务模块说明。"""

import pytest
from app.chan.macd import calculate_ema, calculate_macd, calculate_macd_area


class TestCalculateEma:
    """业务模块说明。"""

    def test_single_value(self):
        """业务模块说明。"""
        result = calculate_ema([100.0], 12)
        assert result == [100.0]

    def test_constant_series(self):
        """业务模块说明。"""
        data = [50.0] * 20
        result = calculate_ema(data, 12)
        for val in result:
            assert val == pytest.approx(50.0)

    def test_period_1_returns_original(self):
        """业务模块说明。"""
        data = [10.0, 20.0, 30.0, 40.0, 50.0]
        result = calculate_ema(data, 1)
        assert result == pytest.approx(data)

    def test_ema_smoothing_effect(self):
        """业务模块说明。"""
        data = [10.0, 10.0, 10.0, 100.0, 10.0, 10.0]
        result = calculate_ema(data, 5)
        # After the spike at index 3, EMA should be between 10 and 100
        assert 10.0 < result[3] < 100.0
        # After the spike drops back, EMA should still be above 10
        assert result[4] > 10.0

    def test_ema_length_matches_input(self):
        """业务模块说明。"""
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = calculate_ema(data, 3)
        assert len(result) == len(data)

    def test_empty_data_raises(self):
        """业务模块说明。"""
        with pytest.raises(ValueError, match="Input data cannot be empty"):
            calculate_ema([], 12)

    def test_invalid_period_raises(self):
        """业务模块说明。"""
        with pytest.raises(ValueError, match="Period must be at least 1"):
            calculate_ema([1.0, 2.0], 0)

    def test_ema_known_values(self):
        """业务模块说明。"""
        # With period=3, multiplier = 2/(3+1) = 0.5
        data = [10.0, 20.0, 30.0, 40.0]
        result = calculate_ema(data, 3)
        # EMA[0] = 10.0
        # EMA[1] = 20 * 0.5 + 10 * 0.5 = 15.0
        # EMA[2] = 30 * 0.5 + 15 * 0.5 = 22.5
        # EMA[3] = 40 * 0.5 + 22.5 * 0.5 = 31.25
        assert result[0] == pytest.approx(10.0)
        assert result[1] == pytest.approx(15.0)
        assert result[2] == pytest.approx(22.5)
        assert result[3] == pytest.approx(31.25)


class TestCalculateMacd:
    """业务模块说明。"""

    def test_output_lengths_match_input(self):
        """业务模块说明。"""
        prices = [float(i) for i in range(50)]
        dif, dea, hist = calculate_macd(prices)
        assert len(dif) == 50
        assert len(dea) == 50
        assert len(hist) == 50

    def test_constant_prices_zero_macd(self):
        """业务模块说明。"""
        prices = [100.0] * 50
        dif, dea, hist = calculate_macd(prices)
        for i in range(len(prices)):
            assert dif[i] == pytest.approx(0.0)
            assert dea[i] == pytest.approx(0.0)
            assert hist[i] == pytest.approx(0.0)

    def test_histogram_formula(self):
        """业务模块说明。"""
        prices = [10.0 + i * 0.5 for i in range(50)]
        dif, dea, hist = calculate_macd(prices)
        for i in range(len(prices)):
            expected = 2.0 * (dif[i] - dea[i])
            assert hist[i] == pytest.approx(expected)

    def test_dif_is_fast_minus_slow_ema(self):
        """业务模块说明。"""
        prices = [10.0 + i * 0.3 for i in range(50)]
        dif, dea, hist = calculate_macd(prices, fast=12, slow=26, signal=9)
        ema_fast = calculate_ema(prices, 12)
        ema_slow = calculate_ema(prices, 26)
        for i in range(len(prices)):
            assert dif[i] == pytest.approx(ema_fast[i] - ema_slow[i])

    def test_dea_is_ema_of_dif(self):
        """业务模块说明。"""
        prices = [10.0 + i * 0.3 for i in range(50)]
        dif, dea, hist = calculate_macd(prices, fast=12, slow=26, signal=9)
        expected_dea = calculate_ema(dif, 9)
        for i in range(len(prices)):
            assert dea[i] == pytest.approx(expected_dea[i])

    def test_uptrend_positive_dif(self):
        """业务模块说明。"""
        prices = [10.0 + i * 1.0 for i in range(60)]
        dif, dea, hist = calculate_macd(prices)
        # After enough data, DIF should be positive in an uptrend
        assert dif[-1] > 0

    def test_downtrend_negative_dif(self):
        """业务模块说明。"""
        prices = [100.0 - i * 1.0 for i in range(60)]
        dif, dea, hist = calculate_macd(prices)
        assert dif[-1] < 0

    def test_empty_prices_raises(self):
        """业务模块说明。"""
        with pytest.raises(ValueError, match="Close prices cannot be empty"):
            calculate_macd([])

    def test_invalid_periods_raises(self):
        """业务模块说明。"""
        prices = [10.0] * 50
        with pytest.raises(ValueError, match="All periods must be at least 1"):
            calculate_macd(prices, fast=0, slow=26, signal=9)

    def test_fast_ge_slow_raises(self):
        """业务模块说明。"""
        prices = [10.0] * 50
        with pytest.raises(ValueError, match="Fast period must be less than slow period"):
            calculate_macd(prices, fast=26, slow=26, signal=9)

    def test_custom_periods(self):
        """业务模块说明。"""
        prices = [10.0 + i * 0.5 for i in range(50)]
        dif, dea, hist = calculate_macd(prices, fast=5, slow=10, signal=3)
        assert len(dif) == 50
        assert len(dea) == 50
        assert len(hist) == 50

    def test_single_price(self):
        """业务模块说明。"""
        dif, dea, hist = calculate_macd([100.0], fast=1, slow=2, signal=1)
        assert dif == [pytest.approx(0.0)]
        assert dea == [pytest.approx(0.0)]
        assert hist == [pytest.approx(0.0)]


class TestCalculateMacdArea:
    """业务模块说明。"""

    def test_basic_area_calculation(self):
        """业务模块说明。"""
        dif = [1.0, 2.0, 3.0, 4.0, 5.0]
        dea = [0.5, 1.0, 1.5, 2.0, 2.5]
        area = calculate_macd_area(dif, dea, 0, 4)
        # abs(0.5) + abs(1.0) + abs(1.5) + abs(2.0) + abs(2.5) = 7.5
        assert area == pytest.approx(7.5)

    def test_area_with_negative_diff(self):
        """业务模块说明。"""
        dif = [1.0, 2.0, 3.0]
        dea = [3.0, 4.0, 5.0]
        area = calculate_macd_area(dif, dea, 0, 2)
        # abs(-2) + abs(-2) + abs(-2) = 6.0
        assert area == pytest.approx(6.0)

    def test_area_with_mixed_signs(self):
        """业务模块说明。"""
        dif = [1.0, 3.0, 2.0]
        dea = [2.0, 1.0, 4.0]
        area = calculate_macd_area(dif, dea, 0, 2)
        # abs(-1) + abs(2) + abs(-2) = 5.0
        assert area == pytest.approx(5.0)

    def test_area_partial_range(self):
        """业务模块说明。"""
        dif = [1.0, 2.0, 3.0, 4.0, 5.0]
        dea = [0.0, 0.0, 0.0, 0.0, 0.0]
        area = calculate_macd_area(dif, dea, 1, 3)
        # abs(2) + abs(3) + abs(4) = 9.0
        assert area == pytest.approx(9.0)

    def test_area_single_point(self):
        """业务模块说明。"""
        dif = [5.0, 10.0, 15.0]
        dea = [3.0, 7.0, 12.0]
        area = calculate_macd_area(dif, dea, 1, 1)
        assert area == pytest.approx(3.0)

    def test_area_zero_when_equal(self):
        """业务模块说明。"""
        dif = [1.0, 2.0, 3.0]
        dea = [1.0, 2.0, 3.0]
        area = calculate_macd_area(dif, dea, 0, 2)
        assert area == pytest.approx(0.0)

    def test_area_is_non_negative(self):
        """业务模块说明。"""
        dif = [-5.0, -3.0, -1.0]
        dea = [-2.0, -4.0, -6.0]
        area = calculate_macd_area(dif, dea, 0, 2)
        assert area >= 0.0

    def test_empty_lists_raises(self):
        """业务模块说明。"""
        with pytest.raises(ValueError, match="cannot be empty"):
            calculate_macd_area([], [], 0, 0)

    def test_mismatched_lengths_raises(self):
        """业务模块说明。"""
        with pytest.raises(ValueError, match="same length"):
            calculate_macd_area([1.0, 2.0], [1.0], 0, 0)

    def test_negative_index_raises(self):
        """业务模块说明。"""
        with pytest.raises(ValueError, match="non-negative"):
            calculate_macd_area([1.0], [1.0], -1, 0)

    def test_start_greater_than_end_raises(self):
        """业务模块说明。"""
        with pytest.raises(ValueError, match="start_idx must be <= end_idx"):
            calculate_macd_area([1.0, 2.0], [1.0, 2.0], 1, 0)

    def test_end_idx_out_of_range_raises(self):
        """业务模块说明。"""
        with pytest.raises(ValueError, match="out of range"):
            calculate_macd_area([1.0, 2.0], [1.0, 2.0], 0, 5)

    def test_area_with_real_macd_data(self):
        """业务模块说明。"""
        # Generate a simple uptrend
        prices = [10.0 + i * 0.5 for i in range(50)]
        dif, dea, hist = calculate_macd(prices, fast=5, slow=10, signal=3)

        # Calculate area for the last 10 bars
        area = calculate_macd_area(dif, dea, 40, 49)
        assert area >= 0.0
        assert isinstance(area, float)
