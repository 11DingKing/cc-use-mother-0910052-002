"""业务模块说明。"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
from datetime import datetime


class Direction(Enum):
    """业务模块说明。"""
    UP = "up"
    DOWN = "down"


class FractalType(Enum):
    """业务模块说明。"""
    TOP = "top"
    BOTTOM = "bottom"


class SignalType(Enum):
    """业务模块说明。"""
    BUY_1 = "buy_1"
    BUY_2 = "buy_2"
    BUY_3 = "buy_3"
    SELL_1 = "sell_1"
    SELL_2 = "sell_2"
    SELL_3 = "sell_3"


@dataclass
class RawCandle:
    """业务模块说明。"""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class MergedCandle:
    """业务模块说明。"""
    timestamp: datetime
    high: float
    low: float
    start_index: int
    end_index: int
    direction: Direction


@dataclass
class Fractal:
    """业务模块说明。"""
    type: FractalType
    timestamp: datetime
    price: float  # 顶分型取high，底分型取low
    candle_index: int
    candles: List[MergedCandle] = field(default_factory=list)


@dataclass
class Bi:
    """业务模块说明。"""
    start_fractal: Fractal
    end_fractal: Fractal
    direction: Direction
    candle_count: int
    start_price: float
    end_price: float


@dataclass
class Duan:
    """业务模块说明。"""
    start_bi: Bi
    end_bi: Bi
    direction: Direction
    bi_list: List[Bi] = field(default_factory=list)
    start_price: float = 0.0
    end_price: float = 0.0


@dataclass
class Zhongshu:
    """业务模块说明。"""
    high: float       # 上沿
    low: float        # 下沿
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    bi_list: List[Bi] = field(default_factory=list)
    level: int = 1


@dataclass
class Signal:
    """业务模块说明。"""
    stock_code: str
    signal_type: SignalType
    timestamp: datetime
    price: float
    level: str        # 时间周期级别
    strength: float = 0.0  # 信号强度 0-1
    details: dict = field(default_factory=dict)
