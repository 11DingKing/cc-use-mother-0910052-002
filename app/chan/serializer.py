"""业务模块说明。"""

import dataclasses
from datetime import datetime
from enum import Enum
from typing import get_type_hints, get_origin, get_args, List, Optional

from app.chan.models import (
    Direction, FractalType, SignalType,
    RawCandle, MergedCandle, Fractal, Bi, Duan, Zhongshu, Signal,
)

# All supported dataclass types for deserialization lookup
_DATACLASS_TYPES = {
    "RawCandle": RawCandle,
    "MergedCandle": MergedCandle,
    "Fractal": Fractal,
    "Bi": Bi,
    "Duan": Duan,
    "Zhongshu": Zhongshu,
    "Signal": Signal,
}

# All supported enum types for deserialization lookup
_ENUM_TYPES = {
    "Direction": Direction,
    "FractalType": FractalType,
    "SignalType": SignalType,
}


class ChanSerializer:
    """业务模块说明。"""

    # ── Serialization ───────────────────────────────────────────────────

    def serialize(self, obj) -> dict:
        """业务模块说明。"""
        if not dataclasses.is_dataclass(obj) or isinstance(obj, type):
            raise TypeError(
                f"serialize() expects a dataclass instance, got {type(obj).__name__}"
            )
        return self._serialize_value(obj)

    def _serialize_value(self, value):
        """业务模块说明。"""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, Enum):
            return value.value
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            result = {"__type__": type(value).__name__}
            for f in dataclasses.fields(value):
                result[f.name] = self._serialize_value(getattr(value, f.name))
            return result
        if isinstance(value, list):
            return [self._serialize_value(item) for item in value]
        if isinstance(value, dict):
            return {
                self._serialize_value(k): self._serialize_value(v)
                for k, v in value.items()
            }
        # Primitive types (int, float, str, bool) pass through
        return value

    # ── Deserialization ─────────────────────────────────────────────────

    def deserialize(self, data: dict, target_type: type):
        """业务模块说明。"""
        if not dataclasses.is_dataclass(target_type):
            raise TypeError(
                f"deserialize() target_type must be a dataclass, got {target_type}"
            )
        if not isinstance(data, dict):
            raise TypeError(
                f"deserialize() expects a dict, got {type(data).__name__}"
            )
        return self._deserialize_value(data, target_type)

    def _deserialize_value(self, value, expected_type):
        """业务模块说明。"""
        if value is None:
            return None

        # Unwrap Optional[X] → X
        origin = get_origin(expected_type)
        args = get_args(expected_type)
        if origin is type(None):
            return None
        # Handle Optional (Union[X, None])
        if _is_optional(expected_type):
            inner_type = _unwrap_optional(expected_type)
            return self._deserialize_value(value, inner_type)

        # Handle List[X]
        if origin is list:
            if not isinstance(value, list):
                raise TypeError(f"Expected list, got {type(value).__name__}")
            elem_type = args[0] if args else None
            if elem_type is None:
                return value
            return [self._deserialize_value(item, elem_type) for item in value]

        # Handle dict
        if expected_type is dict or origin is dict:
            if not isinstance(value, dict):
                raise TypeError(f"Expected dict, got {type(value).__name__}")
            return value

        # Handle datetime
        if expected_type is datetime:
            if isinstance(value, datetime):
                return value
            if isinstance(value, str):
                return datetime.fromisoformat(value)
            raise TypeError(f"Cannot convert {type(value).__name__} to datetime")

        # Handle Enum subclasses
        if isinstance(expected_type, type) and issubclass(expected_type, Enum):
            if isinstance(value, expected_type):
                return value
            return expected_type(value)

        # Handle dataclass
        if dataclasses.is_dataclass(expected_type):
            if not isinstance(value, dict):
                raise TypeError(
                    f"Expected dict for dataclass {expected_type.__name__}, "
                    f"got {type(value).__name__}"
                )
            return self._deserialize_dataclass(value, expected_type)

        # Primitive types pass through
        return value

    def _deserialize_dataclass(self, data: dict, target_type: type):
        """业务模块说明。"""
        hints = get_type_hints(target_type)
        kwargs = {}
        for f in dataclasses.fields(target_type):
            if f.name == "__type__":
                continue
            if f.name not in data:
                # Use default if available
                if f.default is not dataclasses.MISSING:
                    kwargs[f.name] = f.default
                elif f.default_factory is not dataclasses.MISSING:
                    kwargs[f.name] = f.default_factory()
                else:
                    raise ValueError(
                        f"Missing required field '{f.name}' for {target_type.__name__}"
                    )
                continue
            field_type = hints.get(f.name, f.type)
            kwargs[f.name] = self._deserialize_value(data[f.name], field_type)
        return target_type(**kwargs)


# ── Helper functions ────────────────────────────────────────────────────────


def _is_optional(tp) -> bool:
    """业务模块说明。"""
    origin = get_origin(tp)
    if origin is not None:
        # Python 3.10+ uses types.UnionType for X | None
        import sys
        if sys.version_info >= (3, 10):
            import types
            if isinstance(tp, types.UnionType):
                args = get_args(tp)
                return type(None) in args
        # typing.Union
        import typing
        if origin is typing.Union:
            args = get_args(tp)
            return type(None) in args
    return False


def _unwrap_optional(tp):
    """业务模块说明。"""
    args = get_args(tp)
    non_none = [a for a in args if a is not type(None)]
    if len(non_none) == 1:
        return non_none[0]
    # Fallback: return the first non-None type
    return non_none[0] if non_none else tp
