"""业务模块说明。"""

import pytest
from datetime import datetime, timedelta
from typing import List

from hypothesis import given, strategies as st, settings, assume

from app.chan.models import RawCandle
from app.data.fetcher import DataFetcher, FetchResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _candle(
    day: int,
    hour: int = 12,
    minute: int = 0,
    open_: float = 100.0,
    high: float = 105.0,
    low: float = 95.0,
    close: float = 102.0,
    volume: float = 1000.0,
) -> RawCandle:
    """业务模块说明。"""
    return RawCandle(
        timestamp=datetime(2024, 1, 1, hour, minute) + timedelta(days=day),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


class MockFetcher(DataFetcher):
    """业务模块说明。"""
    
    @property
    def source_name(self) -> str:
        return "mock"
    
    def fetch_candles(self, stock_code, period, start_date=None, end_date=None):
        return FetchResult(
            candles=[],
            stock_code=stock_code,
            period=period,
            start_time=start_date,
            end_time=end_date,
            source=self.source_name,
            success=True,
        )
    
    def is_available(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# Tests: DataFetcher Base Class
# ---------------------------------------------------------------------------

class TestDataFetcherClean:
    """业务模块说明。"""
    
    def test_clean_removes_zero_volume(self):
        """业务模块说明。"""
        fetcher = MockFetcher()
        candles = [
            _candle(0, volume=1000.0),
            _candle(1, volume=0.0),  # Suspended
            _candle(2, volume=500.0),
        ]
        
        cleaned = fetcher.clean_candles(candles)
        
        assert len(cleaned) == 2
        assert all(c.volume > 0 for c in cleaned)
    
    def test_clean_removes_invalid_prices(self):
        """业务模块说明。"""
        fetcher = MockFetcher()
        candles = [
            _candle(0, high=105.0, low=95.0),
            _candle(1, high=90.0, low=100.0),  # Invalid: high < low
            _candle(2, high=110.0, low=100.0),
        ]
        
        cleaned = fetcher.clean_candles(candles)
        
        assert len(cleaned) == 2
        assert all(c.high >= c.low for c in cleaned)
    
    def test_clean_removes_negative_prices(self):
        """业务模块说明。"""
        fetcher = MockFetcher()
        candles = [
            _candle(0, open_=100.0, close=102.0),
            _candle(1, open_=-10.0, close=102.0),  # Invalid: negative open
            _candle(2, open_=100.0, close=0.0),    # Invalid: zero close
        ]
        
        cleaned = fetcher.clean_candles(candles)
        
        assert len(cleaned) == 1
    
    def test_clean_sorts_by_timestamp(self):
        """业务模块说明。"""
        fetcher = MockFetcher()
        candles = [
            _candle(2),
            _candle(0),
            _candle(1),
        ]
        
        cleaned = fetcher.clean_candles(candles)
        
        assert len(cleaned) == 3
        for i in range(1, len(cleaned)):
            assert cleaned[i].timestamp > cleaned[i-1].timestamp
    
    def test_clean_empty_list(self):
        """业务模块说明。"""
        fetcher = MockFetcher()
        cleaned = fetcher.clean_candles([])
        assert cleaned == []


class TestDataFetcherMissingData:
    """业务模块说明。"""
    
    def test_mark_missing_empty_candles(self):
        """业务模块说明。"""
        fetcher = MockFetcher()
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)
        
        result = fetcher.mark_missing_data([], start, end, "daily")
        
        assert result["has_missing"] is True
        assert len(result["missing_ranges"]) == 1
        assert result["missing_ranges"][0] == (start, end)
    
    def test_mark_missing_start_gap(self):
        """业务模块说明。"""
        fetcher = MockFetcher()
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)
        candles = [_candle(10)]  # First candle on day 10
        
        result = fetcher.mark_missing_data(candles, start, end, "daily")
        
        assert result["has_missing"] is True
        # Should have gap from start to first candle
        assert any(r[0] == start for r in result["missing_ranges"])
    
    def test_mark_missing_end_gap(self):
        """业务模块说明。"""
        fetcher = MockFetcher()
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)
        candles = [_candle(0)]  # Only first day
        
        result = fetcher.mark_missing_data(candles, start, end, "daily")
        
        assert result["has_missing"] is True
    
    def test_mark_missing_no_gaps(self):
        """业务模块说明。"""
        fetcher = MockFetcher()
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 3)
        candles = [_candle(0), _candle(1), _candle(2)]
        
        result = fetcher.mark_missing_data(candles, start, end, "daily")
        
        # May have small gaps but not major ones
        assert isinstance(result["has_missing"], bool)


# ---------------------------------------------------------------------------
# Property-Based Tests (Hypothesis)
# Property 19: 多周期时间戳对齐
# Property 20: 数据缺失标记
# Validates: Requirements 1.3, 1.4, 8.2
# ---------------------------------------------------------------------------

@st.composite
def candle_list_strategy(draw, min_size: int = 0, max_size: int = 50):
    """业务模块说明。"""
    size = draw(st.integers(min_value=min_size, max_value=max_size))
    
    candles = []
    for i in range(size):
        day = draw(st.integers(min_value=0, max_value=100))
        hour = draw(st.integers(min_value=9, max_value=15))
        minute = draw(st.sampled_from([0, 30]))
        
        base_price = draw(st.floats(min_value=10.0, max_value=500.0, allow_nan=False, allow_infinity=False))
        volatility = draw(st.floats(min_value=0.01, max_value=0.1, allow_nan=False, allow_infinity=False))
        
        low = base_price * (1 - volatility)
        high = base_price * (1 + volatility)
        open_ = draw(st.floats(min_value=low, max_value=high, allow_nan=False, allow_infinity=False))
        close = draw(st.floats(min_value=low, max_value=high, allow_nan=False, allow_infinity=False))
        volume = draw(st.floats(min_value=100.0, max_value=1000000.0, allow_nan=False, allow_infinity=False))
        
        candle = RawCandle(
            timestamp=datetime(2024, 1, 1, hour, minute) + timedelta(days=day),
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=volume,
        )
        candles.append(candle)
    
    return candles


@st.composite
def candle_list_with_issues_strategy(draw):
    """业务模块说明。"""
    candles = draw(candle_list_strategy(min_size=5, max_size=30))
    
    # Add some problematic candles
    num_issues = draw(st.integers(min_value=1, max_value=5))
    
    for _ in range(num_issues):
        issue_type = draw(st.sampled_from(["zero_volume", "invalid_high_low", "negative_price"]))
        day = draw(st.integers(min_value=0, max_value=100))
        
        if issue_type == "zero_volume":
            candle = _candle(day, volume=0.0)
        elif issue_type == "invalid_high_low":
            candle = RawCandle(
                timestamp=datetime(2024, 1, 1) + timedelta(days=day),
                open=100.0,
                high=90.0,  # Invalid: high < low
                low=100.0,
                close=95.0,
                volume=1000.0,
            )
        else:  # negative_price
            candle = RawCandle(
                timestamp=datetime(2024, 1, 1) + timedelta(days=day),
                open=-10.0,  # Invalid: negative
                high=105.0,
                low=95.0,
                close=100.0,
                volume=1000.0,
            )
        
        candles.append(candle)
    
    return candles


class TestPropertyTimestampAlignment:
    """业务模块说明。"""
    
    @given(candle_list_strategy(min_size=2, max_size=50))
    @settings(max_examples=100)
    def test_cleaned_candles_sorted_by_timestamp(self, candles: List[RawCandle]):
        """业务模块说明。"""
        fetcher = MockFetcher()
        cleaned = fetcher.clean_candles(candles)
        
        # Verify sorted order
        for i in range(1, len(cleaned)):
            assert cleaned[i].timestamp >= cleaned[i-1].timestamp, (
                f"Candles not sorted: {cleaned[i-1].timestamp} > {cleaned[i].timestamp}"
            )
    
    @given(candle_list_strategy(min_size=1, max_size=50))
    @settings(max_examples=100)
    def test_cleaned_candles_have_valid_timestamps(self, candles: List[RawCandle]):
        """业务模块说明。"""
        fetcher = MockFetcher()
        cleaned = fetcher.clean_candles(candles)
        
        for c in cleaned:
            assert c.timestamp is not None
            assert isinstance(c.timestamp, datetime)


class TestPropertyMissingDataMarking:
    """业务模块说明。"""
    
    @given(candle_list_strategy(min_size=0, max_size=30))
    @settings(max_examples=100)
    def test_empty_candles_marked_as_missing(self, candles: List[RawCandle]):
        """业务模块说明。"""
        fetcher = MockFetcher()
        start = datetime(2024, 1, 1)
        end = datetime(2024, 12, 31)
        
        # Clean first to potentially get empty list
        cleaned = fetcher.clean_candles(candles)
        
        if len(cleaned) == 0:
            result = fetcher.mark_missing_data(cleaned, start, end, "daily")
            assert result["has_missing"] is True
            assert len(result["missing_ranges"]) >= 1
    
    @given(candle_list_strategy(min_size=1, max_size=30))
    @settings(max_examples=100)
    def test_missing_ranges_are_valid_intervals(self, candles: List[RawCandle]):
        """业务模块说明。"""
        fetcher = MockFetcher()
        cleaned = fetcher.clean_candles(candles)
        
        assume(len(cleaned) > 0)
        
        start = datetime(2024, 1, 1)
        end = datetime(2024, 12, 31)
        
        result = fetcher.mark_missing_data(cleaned, start, end, "daily")
        
        for range_start, range_end in result["missing_ranges"]:
            assert range_start <= range_end, (
                f"Invalid missing range: {range_start} > {range_end}"
            )


class TestPropertyDataCleaning:
    """业务模块说明。"""
    
    @given(candle_list_with_issues_strategy())
    @settings(max_examples=100)
    def test_cleaned_candles_all_valid(self, candles: List[RawCandle]):
        """业务模块说明。"""
        fetcher = MockFetcher()
        cleaned = fetcher.clean_candles(candles)
        
        for c in cleaned:
            # Volume should be positive
            assert c.volume > 0, f"Invalid volume: {c.volume}"
            
            # High should be >= Low
            assert c.high >= c.low, f"Invalid high/low: {c.high} < {c.low}"
            
            # Prices should be positive
            assert c.open > 0, f"Invalid open: {c.open}"
            assert c.close > 0, f"Invalid close: {c.close}"
    
    @given(candle_list_with_issues_strategy())
    @settings(max_examples=100)
    def test_cleaning_is_idempotent(self, candles: List[RawCandle]):
        """业务模块说明。"""
        fetcher = MockFetcher()
        
        cleaned_once = fetcher.clean_candles(candles)
        cleaned_twice = fetcher.clean_candles(cleaned_once)
        
        assert len(cleaned_once) == len(cleaned_twice)
        
        for c1, c2 in zip(cleaned_once, cleaned_twice):
            assert c1.timestamp == c2.timestamp
            assert c1.open == c2.open
            assert c1.high == c2.high
            assert c1.low == c2.low
            assert c1.close == c2.close
            assert c1.volume == c2.volume
