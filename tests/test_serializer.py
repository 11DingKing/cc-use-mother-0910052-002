"""业务模块说明。"""

import pytest
from datetime import datetime

from app.chan.models import (
    Direction, FractalType, SignalType,
    RawCandle, MergedCandle, Fractal, Bi, Duan, Zhongshu, Signal,
)
from app.chan.serializer import ChanSerializer


@pytest.fixture
def serializer():
    return ChanSerializer()


# ── Helper factories ────────────────────────────────────────────────────────

def _make_merged_candle(index=0, direction=Direction.UP):
    return MergedCandle(
        timestamp=datetime(2024, 1, 1 + index),
        high=10.0 + index,
        low=5.0 + index,
        start_index=index,
        end_index=index,
        direction=direction,
    )


def _make_fractal(fractal_type=FractalType.TOP, index=1, price=12.0):
    candles = [_make_merged_candle(i) for i in range(3)]
    return Fractal(
        type=fractal_type,
        timestamp=datetime(2024, 1, 1 + index),
        price=price,
        candle_index=index,
        candles=candles,
    )


def _make_bi(direction=Direction.DOWN):
    top = _make_fractal(FractalType.TOP, index=1, price=15.0)
    bottom = _make_fractal(FractalType.BOTTOM, index=6, price=8.0)
    return Bi(
        start_fractal=top,
        end_fractal=bottom,
        direction=direction,
        candle_count=6,
        start_price=15.0,
        end_price=8.0,
    )


# ── MergedCandle Tests ──────────────────────────────────────────────────────


class TestSerializeMergedCandle:
    def test_round_trip(self, serializer):
        mc = _make_merged_candle()
        data = serializer.serialize(mc)
        restored = serializer.deserialize(data, MergedCandle)
        assert restored == mc

    def test_serialized_format(self, serializer):
        mc = _make_merged_candle()
        data = serializer.serialize(mc)
        assert data["__type__"] == "MergedCandle"
        assert isinstance(data["timestamp"], str)
        assert data["direction"] == "up"
        assert data["high"] == mc.high
        assert data["low"] == mc.low


# ── Fractal Tests ───────────────────────────────────────────────────────────


class TestSerializeFractal:
    def test_round_trip_top(self, serializer):
        f = _make_fractal(FractalType.TOP)
        data = serializer.serialize(f)
        restored = serializer.deserialize(data, Fractal)
        assert restored == f

    def test_round_trip_bottom(self, serializer):
        f = _make_fractal(FractalType.BOTTOM, price=5.0)
        data = serializer.serialize(f)
        restored = serializer.deserialize(data, Fractal)
        assert restored == f

    def test_empty_candles(self, serializer):
        f = Fractal(
            type=FractalType.TOP,
            timestamp=datetime(2024, 6, 15),
            price=20.0,
            candle_index=3,
            candles=[],
        )
        data = serializer.serialize(f)
        restored = serializer.deserialize(data, Fractal)
        assert restored == f
        assert restored.candles == []

    def test_nested_candles_serialized(self, serializer):
        f = _make_fractal()
        data = serializer.serialize(f)
        assert isinstance(data["candles"], list)
        assert len(data["candles"]) == 3
        assert data["candles"][0]["__type__"] == "MergedCandle"


# ── Bi Tests ────────────────────────────────────────────────────────────────


class TestSerializeBi:
    def test_round_trip(self, serializer):
        bi = _make_bi()
        data = serializer.serialize(bi)
        restored = serializer.deserialize(data, Bi)
        assert restored == bi

    def test_nested_fractals(self, serializer):
        bi = _make_bi()
        data = serializer.serialize(bi)
        assert data["start_fractal"]["__type__"] == "Fractal"
        assert data["end_fractal"]["__type__"] == "Fractal"


# ── Duan Tests ──────────────────────────────────────────────────────────────


class TestSerializeDuan:
    def test_round_trip_with_defaults(self, serializer):
        bi = _make_bi()
        duan = Duan(start_bi=bi, end_bi=bi, direction=Direction.DOWN)
        data = serializer.serialize(duan)
        restored = serializer.deserialize(data, Duan)
        assert restored == duan

    def test_round_trip_with_bi_list(self, serializer):
        bi1 = _make_bi(Direction.DOWN)
        bi2 = _make_bi(Direction.UP)
        duan = Duan(
            start_bi=bi1,
            end_bi=bi2,
            direction=Direction.DOWN,
            bi_list=[bi1, bi2],
            start_price=15.0,
            end_price=8.0,
        )
        data = serializer.serialize(duan)
        restored = serializer.deserialize(data, Duan)
        assert restored == duan
        assert len(restored.bi_list) == 2


# ── Zhongshu Tests ──────────────────────────────────────────────────────────


class TestSerializeZhongshu:
    def test_round_trip_minimal(self, serializer):
        zs = Zhongshu(high=12.0, low=9.0)
        data = serializer.serialize(zs)
        restored = serializer.deserialize(data, Zhongshu)
        assert restored == zs

    def test_round_trip_full(self, serializer):
        bi = _make_bi()
        zs = Zhongshu(
            high=12.0,
            low=9.0,
            start_time=datetime(2024, 1, 1),
            end_time=datetime(2024, 1, 15),
            bi_list=[bi],
            level=2,
        )
        data = serializer.serialize(zs)
        restored = serializer.deserialize(data, Zhongshu)
        assert restored == zs

    def test_optional_none_fields(self, serializer):
        zs = Zhongshu(high=12.0, low=9.0, start_time=None, end_time=None)
        data = serializer.serialize(zs)
        assert data["start_time"] is None
        assert data["end_time"] is None
        restored = serializer.deserialize(data, Zhongshu)
        assert restored.start_time is None
        assert restored.end_time is None


# ── Signal Tests ────────────────────────────────────────────────────────────


class TestSerializeSignal:
    def test_round_trip_defaults(self, serializer):
        sig = Signal(
            stock_code="000001",
            signal_type=SignalType.BUY_1,
            timestamp=datetime(2024, 3, 15, 9, 30),
            price=10.5,
            level="daily",
        )
        data = serializer.serialize(sig)
        restored = serializer.deserialize(data, Signal)
        assert restored == sig

    def test_round_trip_with_details(self, serializer):
        details = {"macd_area": 1.5, "divergence": True, "note": "strong signal"}
        sig = Signal(
            stock_code="600000",
            signal_type=SignalType.SELL_3,
            timestamp=datetime(2024, 6, 1, 14, 0),
            price=25.0,
            level="60min",
            strength=0.85,
            details=details,
        )
        data = serializer.serialize(sig)
        restored = serializer.deserialize(data, Signal)
        assert restored == sig
        assert restored.details == details

    def test_all_signal_types_round_trip(self, serializer):
        for st in SignalType:
            sig = Signal(
                stock_code="000001",
                signal_type=st,
                timestamp=datetime(2024, 1, 1),
                price=10.0,
                level="daily",
            )
            data = serializer.serialize(sig)
            restored = serializer.deserialize(data, Signal)
            assert restored == sig


# ── Datetime Handling ───────────────────────────────────────────────────────


class TestDatetimeSerialization:
    def test_datetime_to_iso_string(self, serializer):
        mc = _make_merged_candle()
        data = serializer.serialize(mc)
        assert isinstance(data["timestamp"], str)
        # Should be parseable back
        parsed = datetime.fromisoformat(data["timestamp"])
        assert parsed == mc.timestamp

    def test_datetime_with_time_component(self, serializer):
        sig = Signal(
            stock_code="000001",
            signal_type=SignalType.BUY_1,
            timestamp=datetime(2024, 3, 15, 14, 30, 45),
            price=10.0,
            level="60min",
        )
        data = serializer.serialize(sig)
        restored = serializer.deserialize(data, Signal)
        assert restored.timestamp == sig.timestamp


# ── Enum Handling ───────────────────────────────────────────────────────────


class TestEnumSerialization:
    def test_direction_serialized_as_value(self, serializer):
        mc = _make_merged_candle(direction=Direction.DOWN)
        data = serializer.serialize(mc)
        assert data["direction"] == "down"

    def test_fractal_type_serialized_as_value(self, serializer):
        f = _make_fractal(FractalType.BOTTOM)
        data = serializer.serialize(f)
        assert data["type"] == "bottom"

    def test_signal_type_serialized_as_value(self, serializer):
        sig = Signal(
            stock_code="000001",
            signal_type=SignalType.SELL_2,
            timestamp=datetime(2024, 1, 1),
            price=10.0,
            level="daily",
        )
        data = serializer.serialize(sig)
        assert data["signal_type"] == "sell_2"


# ── Error Handling ──────────────────────────────────────────────────────────


class TestErrorHandling:
    def test_serialize_non_dataclass_raises(self, serializer):
        with pytest.raises(TypeError, match="dataclass instance"):
            serializer.serialize("not a dataclass")

    def test_serialize_class_not_instance_raises(self, serializer):
        with pytest.raises(TypeError, match="dataclass instance"):
            serializer.serialize(Fractal)

    def test_deserialize_non_dataclass_target_raises(self, serializer):
        with pytest.raises(TypeError, match="dataclass"):
            serializer.deserialize({}, str)

    def test_deserialize_non_dict_data_raises(self, serializer):
        with pytest.raises(TypeError, match="dict"):
            serializer.deserialize("not a dict", Fractal)

    def test_deserialize_missing_required_field_raises(self, serializer):
        with pytest.raises(ValueError, match="Missing required field"):
            serializer.deserialize({"__type__": "Fractal"}, Fractal)


# ── RawCandle Tests ─────────────────────────────────────────────────────────


class TestSerializeRawCandle:
    def test_round_trip(self, serializer):
        candle = RawCandle(
            timestamp=datetime(2024, 1, 1),
            open=10.0,
            high=12.0,
            low=9.0,
            close=11.0,
            volume=1000.0,
        )
        data = serializer.serialize(candle)
        restored = serializer.deserialize(data, RawCandle)
        assert restored == candle


# ── Property-Based Tests (Hypothesis) ───────────────────────────────────────
# **Property 18: 缠论对象序列化往返一致性**
# **Validates: Requirements 12.3**

from hypothesis import given, strategies as st, settings


# ── Hypothesis Strategies ───────────────────────────────────────────────────

# Strategy for datetime
datetime_strategy = st.datetimes(
    min_value=datetime(2000, 1, 1),
    max_value=datetime(2030, 12, 31),
)

# Strategy for Direction enum
direction_strategy = st.sampled_from([Direction.UP, Direction.DOWN])

# Strategy for FractalType enum
fractal_type_strategy = st.sampled_from([FractalType.TOP, FractalType.BOTTOM])

# Strategy for SignalType enum
signal_type_strategy = st.sampled_from(list(SignalType))

# Strategy for positive floats (prices)
price_strategy = st.floats(min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False)

# Strategy for non-negative floats (volume)
volume_strategy = st.floats(min_value=0.0, max_value=1e12, allow_nan=False, allow_infinity=False)

# Strategy for non-negative integers (indices)
index_strategy = st.integers(min_value=0, max_value=10000)

# Strategy for strength (0-1)
strength_strategy = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)


@st.composite
def merged_candle_strategy(draw):
    """业务模块说明。"""
    ts = draw(datetime_strategy)
    high = draw(price_strategy)
    low = draw(st.floats(min_value=0.01, max_value=high, allow_nan=False, allow_infinity=False))
    start_idx = draw(index_strategy)
    end_idx = draw(st.integers(min_value=start_idx, max_value=start_idx + 100))
    direction = draw(direction_strategy)
    return MergedCandle(
        timestamp=ts,
        high=high,
        low=low,
        start_index=start_idx,
        end_index=end_idx,
        direction=direction,
    )


@st.composite
def fractal_strategy(draw):
    """业务模块说明。"""
    ftype = draw(fractal_type_strategy)
    ts = draw(datetime_strategy)
    price = draw(price_strategy)
    candle_index = draw(index_strategy)
    # Generate 0-3 candles for the fractal
    num_candles = draw(st.integers(min_value=0, max_value=3))
    candles = [draw(merged_candle_strategy()) for _ in range(num_candles)]
    return Fractal(
        type=ftype,
        timestamp=ts,
        price=price,
        candle_index=candle_index,
        candles=candles,
    )


@st.composite
def bi_strategy(draw):
    """业务模块说明。"""
    direction = draw(direction_strategy)
    start_fractal = draw(fractal_strategy())
    end_fractal = draw(fractal_strategy())
    candle_count = draw(st.integers(min_value=5, max_value=100))
    start_price = draw(price_strategy)
    end_price = draw(price_strategy)
    return Bi(
        start_fractal=start_fractal,
        end_fractal=end_fractal,
        direction=direction,
        candle_count=candle_count,
        start_price=start_price,
        end_price=end_price,
    )


@st.composite
def duan_strategy(draw):
    """业务模块说明。"""
    direction = draw(direction_strategy)
    start_bi = draw(bi_strategy())
    end_bi = draw(bi_strategy())
    num_bis = draw(st.integers(min_value=0, max_value=3))
    bi_list = [draw(bi_strategy()) for _ in range(num_bis)]
    start_price = draw(price_strategy)
    end_price = draw(price_strategy)
    return Duan(
        start_bi=start_bi,
        end_bi=end_bi,
        direction=direction,
        bi_list=bi_list,
        start_price=start_price,
        end_price=end_price,
    )


@st.composite
def zhongshu_strategy(draw):
    """业务模块说明。"""
    high = draw(price_strategy)
    low = draw(st.floats(min_value=0.01, max_value=high, allow_nan=False, allow_infinity=False))
    # Optional datetime fields
    start_time = draw(st.one_of(st.none(), datetime_strategy))
    end_time = draw(st.one_of(st.none(), datetime_strategy))
    num_bis = draw(st.integers(min_value=0, max_value=3))
    bi_list = [draw(bi_strategy()) for _ in range(num_bis)]
    level = draw(st.integers(min_value=1, max_value=5))
    return Zhongshu(
        high=high,
        low=low,
        start_time=start_time,
        end_time=end_time,
        bi_list=bi_list,
        level=level,
    )


@st.composite
def signal_strategy(draw):
    """业务模块说明。"""
    stock_code = draw(st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'))))
    signal_type = draw(signal_type_strategy)
    ts = draw(datetime_strategy)
    price = draw(price_strategy)
    level = draw(st.sampled_from(["daily", "60min", "30min", "15min", "5min"]))
    strength = draw(strength_strategy)
    # Simple details dict with primitive values
    details = draw(st.fixed_dictionaries({}, optional={
        "note": st.text(max_size=50),
        "value": st.floats(allow_nan=False, allow_infinity=False),
        "count": st.integers(min_value=0, max_value=1000),
    }))
    return Signal(
        stock_code=stock_code,
        signal_type=signal_type,
        timestamp=ts,
        price=price,
        level=level,
        strength=strength,
        details=details,
    )


# ── Property Tests ──────────────────────────────────────────────────────────


class TestSerializerRoundTripProperty:
    """业务模块说明。"""

    @given(merged_candle_strategy())
    @settings(max_examples=100)
    def test_merged_candle_round_trip(self, mc):
        """业务模块说明。"""
        serializer = ChanSerializer()
        data = serializer.serialize(mc)
        restored = serializer.deserialize(data, MergedCandle)
        assert restored == mc

    @given(fractal_strategy())
    @settings(max_examples=100)
    def test_fractal_round_trip(self, fractal):
        """业务模块说明。"""
        serializer = ChanSerializer()
        data = serializer.serialize(fractal)
        restored = serializer.deserialize(data, Fractal)
        assert restored == fractal

    @given(bi_strategy())
    @settings(max_examples=100)
    def test_bi_round_trip(self, bi):
        """业务模块说明。"""
        serializer = ChanSerializer()
        data = serializer.serialize(bi)
        restored = serializer.deserialize(data, Bi)
        assert restored == bi

    @given(duan_strategy())
    @settings(max_examples=100)
    def test_duan_round_trip(self, duan):
        """业务模块说明。"""
        serializer = ChanSerializer()
        data = serializer.serialize(duan)
        restored = serializer.deserialize(data, Duan)
        assert restored == duan

    @given(zhongshu_strategy())
    @settings(max_examples=100)
    def test_zhongshu_round_trip(self, zhongshu):
        """业务模块说明。"""
        serializer = ChanSerializer()
        data = serializer.serialize(zhongshu)
        restored = serializer.deserialize(data, Zhongshu)
        assert restored == zhongshu

    @given(signal_strategy())
    @settings(max_examples=100)
    def test_signal_round_trip(self, signal):
        """业务模块说明。"""
        serializer = ChanSerializer()
        data = serializer.serialize(signal)
        restored = serializer.deserialize(data, Signal)
        assert restored == signal
