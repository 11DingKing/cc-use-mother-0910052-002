"""业务模块说明。"""

import pytest
from datetime import datetime, timedelta

from hypothesis import given, strategies as st, settings, assume

from app.utils.validators import (
    validate_stock_code,
    validate_time_range,
    validate_period,
    validate_positive_number,
    validate_list_not_empty,
    parse_date,
)
from app.middleware.exception_handler import ValidationException


# ---------------------------------------------------------------------------
# Tests: Stock Code Validation
# ---------------------------------------------------------------------------

class TestValidateStockCode:
    """业务模块说明。"""
    
    def test_valid_a_stock_6_digits(self):
        """业务模块说明。"""
        assert validate_stock_code("000001") == "sz000001"
        assert validate_stock_code("600000") == "sh600000"
        assert validate_stock_code("300001") == "sz300001"
    
    def test_valid_a_stock_with_prefix(self):
        """业务模块说明。"""
        assert validate_stock_code("sh600000") == "sh600000"
        assert validate_stock_code("SZ000001") == "sz000001"
        assert validate_stock_code("bj430001") == "bj430001"
    
    def test_valid_us_stock(self):
        """业务模块说明。"""
        assert validate_stock_code("AAPL") == "AAPL"
        assert validate_stock_code("msft") == "MSFT"
        assert validate_stock_code("A") == "A"
    
    def test_invalid_empty_code(self):
        """业务模块说明。"""
        with pytest.raises(ValidationException) as exc_info:
            validate_stock_code("")
        assert exc_info.value.code == "VALIDATION_ERROR"
    
    def test_invalid_code_format(self):
        """业务模块说明。"""
        with pytest.raises(ValidationException):
            validate_stock_code("1234567")  # 7 digits
        with pytest.raises(ValidationException):
            validate_stock_code("ABCDEF")  # 6 letters
        with pytest.raises(ValidationException):
            validate_stock_code("abc123")  # mixed invalid
    
    def test_market_specific_validation(self):
        """业务模块说明。"""
        # CN market
        assert validate_stock_code("000001", market="cn") == "sz000001"
        with pytest.raises(ValidationException):
            validate_stock_code("AAPL", market="cn")
        
        # US market
        assert validate_stock_code("AAPL", market="us") == "AAPL"
        with pytest.raises(ValidationException):
            validate_stock_code("000001", market="us")


class TestValidateTimeRange:
    """业务模块说明。"""
    
    def test_valid_range(self):
        """业务模块说明。"""
        start = datetime(2024, 1, 1)
        end = datetime(2024, 6, 30)
        result = validate_time_range(start, end)
        assert result == (start, end)
    
    def test_default_values(self):
        """业务模块说明。"""
        start, end = validate_time_range(None, None)
        assert start is not None
        assert end is not None
        assert start < end
    
    def test_invalid_reversed_range(self):
        """业务模块说明。"""
        start = datetime(2024, 6, 30)
        end = datetime(2024, 1, 1)
        with pytest.raises(ValidationException) as exc_info:
            validate_time_range(start, end)
        assert "before" in exc_info.value.message.lower()
    
    def test_invalid_future_start(self):
        """业务模块说明。"""
        future = datetime.now() + timedelta(days=30)
        with pytest.raises(ValidationException) as exc_info:
            validate_time_range(future, future + timedelta(days=10))
        assert "future" in exc_info.value.message.lower()
    
    def test_invalid_too_large_range(self):
        """业务模块说明。"""
        start = datetime(2010, 1, 1)
        end = datetime(2024, 12, 31)
        with pytest.raises(ValidationException) as exc_info:
            validate_time_range(start, end, max_days=365)
        assert "exceed" in exc_info.value.message.lower()


class TestValidatePeriod:
    """业务模块说明。"""
    
    def test_valid_periods(self):
        """业务模块说明。"""
        assert validate_period("daily") == "daily"
        assert validate_period("60min") == "60min"
        assert validate_period("30min") == "30min"
    
    def test_period_aliases(self):
        """业务模块说明。"""
        assert validate_period("d") == "daily"
        assert validate_period("1d") == "daily"
        assert validate_period("60m") == "60min"
        assert validate_period("1h") == "60min"
    
    def test_case_insensitive(self):
        """业务模块说明。"""
        assert validate_period("DAILY") == "daily"
        assert validate_period("Daily") == "daily"
    
    def test_invalid_period(self):
        """业务模块说明。"""
        with pytest.raises(ValidationException):
            validate_period("weekly")
        with pytest.raises(ValidationException):
            validate_period("")
        with pytest.raises(ValidationException):
            validate_period("5min")


class TestParseDate:
    """业务模块说明。"""
    
    def test_valid_formats(self):
        """业务模块说明。"""
        assert parse_date("2024-01-15") == datetime(2024, 1, 15)
        assert parse_date("20240115") == datetime(2024, 1, 15)
        assert parse_date("2024/01/15") == datetime(2024, 1, 15)
    
    def test_invalid_format(self):
        """业务模块说明。"""
        with pytest.raises(ValidationException):
            parse_date("15-01-2024")
        with pytest.raises(ValidationException):
            parse_date("2024.01.15")
        with pytest.raises(ValidationException):
            parse_date("")


class TestValidatePositiveNumber:
    """业务模块说明。"""
    
    def test_valid_positive(self):
        """业务模块说明。"""
        assert validate_positive_number(100.0, "price") == 100.0
        assert validate_positive_number(0.01, "rate") == 0.01
    
    def test_invalid_zero(self):
        """业务模块说明。"""
        with pytest.raises(ValidationException):
            validate_positive_number(0, "price")
    
    def test_invalid_negative(self):
        """业务模块说明。"""
        with pytest.raises(ValidationException):
            validate_positive_number(-10, "price")
    
    def test_min_max_bounds(self):
        """业务模块说明。"""
        assert validate_positive_number(50, "price", min_value=10, max_value=100) == 50
        
        with pytest.raises(ValidationException):
            validate_positive_number(5, "price", min_value=10)
        
        with pytest.raises(ValidationException):
            validate_positive_number(150, "price", max_value=100)


class TestValidateListNotEmpty:
    """业务模块说明。"""
    
    def test_valid_list(self):
        """业务模块说明。"""
        assert validate_list_not_empty([1, 2, 3], "items") == [1, 2, 3]
    
    def test_invalid_empty(self):
        """业务模块说明。"""
        with pytest.raises(ValidationException):
            validate_list_not_empty([], "items")
    
    def test_max_items(self):
        """业务模块说明。"""
        with pytest.raises(ValidationException):
            validate_list_not_empty([1, 2, 3, 4, 5], "items", max_items=3)


# ---------------------------------------------------------------------------
# Property-Based Tests (Hypothesis)
# Property 21: 输入验证拒绝无效输入
# Validates: Requirements 11.5
# ---------------------------------------------------------------------------

@st.composite
def invalid_stock_code_strategy(draw):
    """业务模块说明。"""
    invalid_type = draw(st.sampled_from([
        "empty",
        "too_short",
        "too_long",
        "special_chars",
        "mixed_invalid",
    ]))
    
    if invalid_type == "empty":
        return ""
    elif invalid_type == "too_short":
        return draw(st.text(alphabet="0123456789", min_size=1, max_size=4))
    elif invalid_type == "too_long":
        return draw(st.text(alphabet="0123456789", min_size=7, max_size=10))
    elif invalid_type == "special_chars":
        return draw(st.text(alphabet="!@#$%^&*()", min_size=1, max_size=6))
    else:  # mixed_invalid
        return draw(st.text(alphabet="0123456789abcdef!@#", min_size=3, max_size=8))


@st.composite
def invalid_period_strategy(draw):
    """业务模块说明。"""
    # Generate strings that are not valid periods
    invalid = draw(st.text(min_size=1, max_size=10))
    valid_periods = ["daily", "60min", "30min", "d", "1d", "60m", "1h", "30m", "15m", "15min"]
    assume(invalid.lower() not in valid_periods)
    return invalid


class TestPropertyInputValidation:
    """业务模块说明。"""
    
    @given(invalid_stock_code_strategy())
    @settings(max_examples=100)
    def test_invalid_stock_codes_rejected(self, code: str):
        """业务模块说明。"""
        # Skip codes that might accidentally be valid
        if code and len(code) == 6 and code.isdigit():
            return  # This is actually valid A-share
        if code and 1 <= len(code) <= 5 and code.isalpha():
            return  # This is valid US stock
        if code and len(code) == 5 and code.startswith("0") and code.isdigit():
            return  # This is valid HK stock
        
        with pytest.raises(ValidationException):
            validate_stock_code(code)
    
    @given(st.text(min_size=0, max_size=5))
    @settings(max_examples=100)
    def test_empty_and_short_codes_handled(self, code: str):
        """业务模块说明。"""
        if not code or not code.strip():
            with pytest.raises(ValidationException):
                validate_stock_code(code)
    
    @given(
        st.datetimes(min_value=datetime(2000, 1, 1), max_value=datetime(2030, 12, 31)),
        st.datetimes(min_value=datetime(2000, 1, 1), max_value=datetime(2030, 12, 31)),
    )
    @settings(max_examples=100)
    def test_reversed_time_range_rejected(self, start: datetime, end: datetime):
        """业务模块说明。"""
        assume(start > end)
        
        with pytest.raises(ValidationException):
            validate_time_range(start, end)
    
    @given(st.floats(max_value=0, allow_nan=False, allow_infinity=False))
    @settings(max_examples=100)
    def test_non_positive_numbers_rejected(self, value: float):
        """业务模块说明。"""
        with pytest.raises(ValidationException):
            validate_positive_number(value, "test_field")
    
    @given(st.lists(st.integers(), max_size=0))
    @settings(max_examples=50)
    def test_empty_lists_rejected(self, items: list):
        """业务模块说明。"""
        with pytest.raises(ValidationException):
            validate_list_not_empty(items, "test_field")


class TestPropertyValidInputsAccepted:
    """业务模块说明。"""
    
    @given(st.sampled_from(["000001", "600000", "300001", "sh600000", "sz000001"]))
    @settings(max_examples=50)
    def test_valid_a_stock_codes_accepted(self, code: str):
        """业务模块说明。"""
        result = validate_stock_code(code)
        assert result is not None
        assert len(result) >= 6
    
    @given(st.sampled_from(["AAPL", "MSFT", "GOOGL", "A", "FB"]))
    @settings(max_examples=50)
    def test_valid_us_stock_codes_accepted(self, code: str):
        """业务模块说明。"""
        result = validate_stock_code(code)
        assert result is not None
        assert result == code.upper()
    
    @given(st.sampled_from(["daily", "60min", "30min", "d", "1d", "60m", "1h"]))
    @settings(max_examples=50)
    def test_valid_periods_accepted(self, period: str):
        """业务模块说明。"""
        result = validate_period(period)
        assert result in ["daily", "60min", "30min", "15min"]
    
    @given(st.floats(min_value=0.01, max_value=1000000, allow_nan=False, allow_infinity=False))
    @settings(max_examples=100)
    def test_positive_numbers_accepted(self, value: float):
        """业务模块说明。"""
        result = validate_positive_number(value, "test_field")
        assert result == value
    
    @given(st.lists(st.integers(), min_size=1, max_size=100))
    @settings(max_examples=100)
    def test_non_empty_lists_accepted(self, items: list):
        """业务模块说明。"""
        result = validate_list_not_empty(items, "test_field")
        assert result == items
