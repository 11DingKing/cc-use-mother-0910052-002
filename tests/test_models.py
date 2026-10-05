"""业务模块说明。"""

import pytest
from datetime import datetime
from dataclasses import fields, FrozenInstanceError

from app.chan.models import (
    Direction, FractalType, SignalType,
    RawCandle, MergedCandle, Fractal, Bi, Duan, Zhongshu, Signal,
)


# ── Enum Tests ──────────────────────────────────────────────────────────────


class TestDirection:
    def test_values(self):
        assert Direction.UP.value == "up"
        assert Direction.DOWN.value == "down"

    def test_members(self):
        assert set(Direction) == {Direction.UP, Direction.DOWN}


class TestFractalType:
    def test_values(self):
        assert FractalType.TOP.value == "top"
        assert FractalType.BOTTOM.value == "bottom"

    def test_members(self):
        assert set(FractalType) == {FractalType.TOP, FractalType.BOTTOM}


class TestSignalType:
    def test_buy_values(self):
        assert SignalType.BUY_1.value == "buy_1"
        assert SignalType.BUY_2.value == "buy_2"
        assert SignalType.BUY_3.value == "buy_3"

    def test_sell_values(self):
        assert SignalType.SELL_1.value == "sell_1"
        assert SignalType.SELL_2.value == "sell_2"
        assert SignalType.SELL_3.value == "sell_3"

    def test_members_count(self):
        assert len(SignalType) == 6


# ── RawCandle Tests ─────────────────────────────────────────────────────────


class TestRawCandle:
    def test_creation(self):
        ts = datetime(2024, 1, 1)
        candle = RawCandle(timestamp=ts, open=10.0, high=12.0, low=9.0, close=11.0, volume=1000.0)
        assert candle.timestamp == ts
        assert candle.open == 10.0
        assert candle.high == 12.0
        assert candle.low == 9.0
        assert candle.close == 11.0
        assert candle.volume == 1000.0

    def test_equality(self):
        ts = datetime(2024, 1, 1)
        c1 = RawCandle(timestamp=ts, open=10.0, high=12.0, low=9.0, close=11.0, volume=1000.0)
        c2 = RawCandle(timestamp=ts, open=10.0, high=12.0, low=9.0, close=11.0, volume=1000.0)
        assert c1 == c2

    def test_field_count(self):
        assert len(fields(RawCandle)) == 6


# ── MergedCandle Tests ──────────────────────────────────────────────────────


class TestMergedCandle:
    def test_creation(self):
        ts = datetime(2024, 1, 1)
        mc = MergedCandle(timestamp=ts, high=12.0, low=9.0, start_index=0, end_index=2, direction=Direction.UP)
        assert mc.timestamp == ts
        assert mc.high == 12.0
        assert mc.low == 9.0
        assert mc.start_index == 0
        assert mc.end_index == 2
        assert mc.direction == Direction.UP

    def test_equality(self):
        ts = datetime(2024, 1, 1)
        mc1 = MergedCandle(timestamp=ts, high=12.0, low=9.0, start_index=0, end_index=2, direction=Direction.UP)
        mc2 = MergedCandle(timestamp=ts, high=12.0, low=9.0, start_index=0, end_index=2, direction=Direction.UP)
        assert mc1 == mc2


# ── Fractal Tests ───────────────────────────────────────────────────────────


class TestFractal:
    def test_creation_with_defaults(self):
        ts = datetime(2024, 1, 1)
        f = Fractal(type=FractalType.TOP, timestamp=ts, price=12.0, candle_index=1)
        assert f.type == FractalType.TOP
        assert f.timestamp == ts
        assert f.price == 12.0
        assert f.candle_index == 1
        assert f.candles == []

    def test_creation_with_candles(self):
        ts = datetime(2024, 1, 1)
        mc = MergedCandle(timestamp=ts, high=12.0, low=9.0, start_index=0, end_index=0, direction=Direction.UP)
        f = Fractal(type=FractalType.BOTTOM, timestamp=ts, price=9.0, candle_index=1, candles=[mc])
        assert len(f.candles) == 1
        assert f.candles[0] == mc

    def test_default_candles_not_shared(self):
        """业务模块说明。"""
        f1 = Fractal(type=FractalType.TOP, timestamp=datetime(2024, 1, 1), price=12.0, candle_index=0)
        f2 = Fractal(type=FractalType.TOP, timestamp=datetime(2024, 1, 2), price=13.0, candle_index=1)
        f1.candles.append(
            MergedCandle(timestamp=datetime(2024, 1, 1), high=12.0, low=9.0, start_index=0, end_index=0, direction=Direction.UP)
        )
        assert len(f2.candles) == 0


# ── Bi Tests ────────────────────────────────────────────────────────────────


class TestBi:
    def _make_fractals(self):
        ts1 = datetime(2024, 1, 1)
        ts2 = datetime(2024, 1, 10)
        top = Fractal(type=FractalType.TOP, timestamp=ts1, price=15.0, candle_index=0)
        bottom = Fractal(type=FractalType.BOTTOM, timestamp=ts2, price=8.0, candle_index=5)
        return top, bottom

    def test_creation(self):
        top, bottom = self._make_fractals()
        bi = Bi(start_fractal=top, end_fractal=bottom, direction=Direction.DOWN,
                candle_count=6, start_price=15.0, end_price=8.0)
        assert bi.start_fractal == top
        assert bi.end_fractal == bottom
        assert bi.direction == Direction.DOWN
        assert bi.candle_count == 6
        assert bi.start_price == 15.0
        assert bi.end_price == 8.0

    def test_equality(self):
        top, bottom = self._make_fractals()
        bi1 = Bi(start_fractal=top, end_fractal=bottom, direction=Direction.DOWN,
                 candle_count=6, start_price=15.0, end_price=8.0)
        bi2 = Bi(start_fractal=top, end_fractal=bottom, direction=Direction.DOWN,
                 candle_count=6, start_price=15.0, end_price=8.0)
        assert bi1 == bi2


# ── Duan Tests ──────────────────────────────────────────────────────────────


class TestDuan:
    def _make_bi(self):
        top = Fractal(type=FractalType.TOP, timestamp=datetime(2024, 1, 1), price=15.0, candle_index=0)
        bottom = Fractal(type=FractalType.BOTTOM, timestamp=datetime(2024, 1, 10), price=8.0, candle_index=5)
        return Bi(start_fractal=top, end_fractal=bottom, direction=Direction.DOWN,
                  candle_count=6, start_price=15.0, end_price=8.0)

    def test_creation_with_defaults(self):
        bi = self._make_bi()
        duan = Duan(start_bi=bi, end_bi=bi, direction=Direction.DOWN)
        assert duan.bi_list == []
        assert duan.start_price == 0.0
        assert duan.end_price == 0.0

    def test_creation_with_values(self):
        bi = self._make_bi()
        duan = Duan(start_bi=bi, end_bi=bi, direction=Direction.DOWN,
                    bi_list=[bi], start_price=15.0, end_price=8.0)
        assert len(duan.bi_list) == 1
        assert duan.start_price == 15.0
        assert duan.end_price == 8.0

    def test_default_bi_list_not_shared(self):
        bi = self._make_bi()
        d1 = Duan(start_bi=bi, end_bi=bi, direction=Direction.DOWN)
        d2 = Duan(start_bi=bi, end_bi=bi, direction=Direction.DOWN)
        d1.bi_list.append(bi)
        assert len(d2.bi_list) == 0


# ── Zhongshu Tests ──────────────────────────────────────────────────────────


class TestZhongshu:
    def test_creation_with_defaults(self):
        zs = Zhongshu(high=12.0, low=9.0)
        assert zs.high == 12.0
        assert zs.low == 9.0
        assert zs.start_time is None
        assert zs.end_time is None
        assert zs.bi_list == []
        assert zs.level == 1

    def test_creation_with_all_fields(self):
        ts1 = datetime(2024, 1, 1)
        ts2 = datetime(2024, 1, 15)
        zs = Zhongshu(high=12.0, low=9.0, start_time=ts1, end_time=ts2, level=2)
        assert zs.start_time == ts1
        assert zs.end_time == ts2
        assert zs.level == 2

    def test_default_bi_list_not_shared(self):
        zs1 = Zhongshu(high=12.0, low=9.0)
        zs2 = Zhongshu(high=12.0, low=9.0)
        top = Fractal(type=FractalType.TOP, timestamp=datetime(2024, 1, 1), price=15.0, candle_index=0)
        bottom = Fractal(type=FractalType.BOTTOM, timestamp=datetime(2024, 1, 10), price=8.0, candle_index=5)
        bi = Bi(start_fractal=top, end_fractal=bottom, direction=Direction.DOWN,
                candle_count=6, start_price=15.0, end_price=8.0)
        zs1.bi_list.append(bi)
        assert len(zs2.bi_list) == 0


# ── Signal Tests ────────────────────────────────────────────────────────────


class TestSignal:
    def test_creation_with_defaults(self):
        ts = datetime(2024, 1, 1)
        sig = Signal(stock_code="000001", signal_type=SignalType.BUY_1,
                     timestamp=ts, price=10.0, level="daily")
        assert sig.stock_code == "000001"
        assert sig.signal_type == SignalType.BUY_1
        assert sig.timestamp == ts
        assert sig.price == 10.0
        assert sig.level == "daily"
        assert sig.strength == 0.0
        assert sig.details == {}

    def test_creation_with_all_fields(self):
        ts = datetime(2024, 1, 1)
        details = {"macd_area": 1.5, "divergence": True}
        sig = Signal(stock_code="600000", signal_type=SignalType.SELL_3,
                     timestamp=ts, price=25.0, level="60min",
                     strength=0.85, details=details)
        assert sig.strength == 0.85
        assert sig.details == details

    def test_default_details_not_shared(self):
        ts = datetime(2024, 1, 1)
        s1 = Signal(stock_code="000001", signal_type=SignalType.BUY_1,
                    timestamp=ts, price=10.0, level="daily")
        s2 = Signal(stock_code="000002", signal_type=SignalType.BUY_2,
                    timestamp=ts, price=20.0, level="daily")
        s1.details["key"] = "value"
        assert "key" not in s2.details

    def test_all_signal_types(self):
        ts = datetime(2024, 1, 1)
        for st in SignalType:
            sig = Signal(stock_code="000001", signal_type=st,
                         timestamp=ts, price=10.0, level="daily")
            assert sig.signal_type == st
