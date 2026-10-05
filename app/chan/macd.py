"""业务模块说明。"""

from typing import List, Tuple


def calculate_ema(data: List[float], period: int) -> List[float]:
    """业务模块说明。"""
    if not data:
        raise ValueError("Input data cannot be empty")
    if period < 1:
        raise ValueError("Period must be at least 1")

    multiplier = 2.0 / (period + 1)
    ema_values: List[float] = []

    # 第一个值使用数据本身作为初始EMA
    ema_values.append(data[0])

    for i in range(1, len(data)):
        ema = data[i] * multiplier + ema_values[i - 1] * (1 - multiplier)
        ema_values.append(ema)

    return ema_values


def calculate_macd(
    close_prices: List[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Tuple[List[float], List[float], List[float]]:
    """业务模块说明。"""
    if not close_prices:
        raise ValueError("Close prices cannot be empty")
    if fast < 1 or slow < 1 or signal < 1:
        raise ValueError("All periods must be at least 1")
    if fast >= slow:
        raise ValueError("Fast period must be less than slow period")

    # 计算快线和慢线EMA
    ema_fast = calculate_ema(close_prices, fast)
    ema_slow = calculate_ema(close_prices, slow)

    # DIF = EMA(fast) - EMA(slow)
    dif_list = [ema_fast[i] - ema_slow[i] for i in range(len(close_prices))]

    # DEA = EMA(DIF, signal)
    dea_list = calculate_ema(dif_list, signal)

    # MACD柱状图 = 2 * (DIF - DEA)
    macd_histogram_list = [
        2.0 * (dif_list[i] - dea_list[i]) for i in range(len(close_prices))
    ]

    return dif_list, dea_list, macd_histogram_list


def calculate_macd_area(
    dif: List[float], dea: List[float], start_idx: int, end_idx: int
) -> float:
    """业务模块说明。"""
    if not dif or not dea:
        raise ValueError("DIF and DEA lists cannot be empty")
    if len(dif) != len(dea):
        raise ValueError("DIF and DEA lists must have the same length")
    if start_idx < 0 or end_idx < 0:
        raise ValueError("Indices must be non-negative")
    if start_idx > end_idx:
        raise ValueError("start_idx must be <= end_idx")
    if end_idx >= len(dif):
        raise ValueError(
            f"end_idx ({end_idx}) out of range (length={len(dif)})"
        )

    area = 0.0
    for i in range(start_idx, end_idx + 1):
        area += abs(dif[i] - dea[i])

    return area
