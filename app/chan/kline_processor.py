"""业务模块说明。"""

import logging
from typing import List, Tuple

from app.chan.models import RawCandle, MergedCandle, Direction

logger = logging.getLogger(__name__)


class KLineProcessor:
    """业务模块说明。"""

    def __init__(
        self,
        limit_up_threshold: float = 0.095,
        limit_down_threshold: float = -0.095,
    ) -> None:
        self.limit_up_threshold = limit_up_threshold
        self.limit_down_threshold = limit_down_threshold

    def clean(
        self, candles: List[RawCandle]
    ) -> Tuple[List[RawCandle], dict]:
        """业务模块说明。"""
        if not candles:
            return [], {
                "removed_count": 0,
                "suspended_count": 0,
                "anomaly_count": 0,
                "limit_up_count": 0,
                "limit_down_count": 0,
            }

        suspended_count = 0
        anomaly_count = 0
        limit_up_count = 0
        limit_down_count = 0
        cleaned: List[RawCandle] = []

        for i, candle in enumerate(candles):
            # 1. 过滤停牌数据（volume == 0）
            if candle.volume == 0:
                suspended_count += 1
                logger.debug(
                    "Filtered suspended candle at index %d, timestamp=%s",
                    i,
                    candle.timestamp,
                )
                continue

            # 2. 移除价格异常值（high < low）
            if candle.high < candle.low:
                anomaly_count += 1
                logger.debug(
                    "Filtered anomaly candle at index %d, timestamp=%s "
                    "(high=%.4f < low=%.4f)",
                    i,
                    candle.timestamp,
                    candle.high,
                    candle.low,
                )
                continue

            # 3. 标记涨跌停（不移除，仅计数）
            if i > 0:
                prev_close = candles[i - 1].close
                if prev_close > 0:
                    price_change = (candle.close - prev_close) / prev_close

                    if (
                        candle.close == candle.high
                        and price_change > self.limit_up_threshold
                    ):
                        limit_up_count += 1
                        logger.debug(
                            "Limit-up candle at index %d, timestamp=%s, "
                            "change=%.2f%%",
                            i,
                            candle.timestamp,
                            price_change * 100,
                        )

                    if (
                        candle.close == candle.low
                        and price_change < self.limit_down_threshold
                    ):
                        limit_down_count += 1
                        logger.debug(
                            "Limit-down candle at index %d, timestamp=%s, "
                            "change=%.2f%%",
                            i,
                            candle.timestamp,
                            price_change * 100,
                        )

            cleaned.append(candle)

        removed_count = suspended_count + anomaly_count

        report = {
            "removed_count": removed_count,
            "suspended_count": suspended_count,
            "anomaly_count": anomaly_count,
            "limit_up_count": limit_up_count,
            "limit_down_count": limit_down_count,
        }

        logger.info(
            "K-line cleaning complete: %d input, %d output, "
            "%d removed (suspended=%d, anomaly=%d), "
            "limit_up=%d, limit_down=%d",
            len(candles),
            len(cleaned),
            removed_count,
            suspended_count,
            anomaly_count,
            limit_up_count,
            limit_down_count,
        )

        return cleaned, report

    def merge(self, candles: List[RawCandle]) -> List[MergedCandle]:
        """业务模块说明。"""
        if not candles:
            return []

        if len(candles) == 1:
            c = candles[0]
            return [
                MergedCandle(
                    timestamp=c.timestamp,
                    high=c.high,
                    low=c.low,
                    start_index=0,
                    end_index=0,
                    direction=Direction.UP,
                )
            ]

        # Determine initial direction from first two candles
        if candles[1].high >= candles[0].high:
            direction = Direction.UP
        else:
            direction = Direction.DOWN

        # Initialize merged list with the first candle
        first = candles[0]
        merged: List[MergedCandle] = [
            MergedCandle(
                timestamp=first.timestamp,
                high=first.high,
                low=first.low,
                start_index=0,
                end_index=0,
                direction=direction,
            )
        ]

        for i in range(1, len(candles)):
            c = candles[i]
            last = merged[-1]

            # Check inclusion relationship (either direction)
            if self._has_inclusion(last, c):
                # Merge based on current trend direction
                if direction == Direction.UP:
                    new_high = max(last.high, c.high)
                    new_low = max(last.low, c.low)
                else:
                    new_high = min(last.high, c.high)
                    new_low = min(last.low, c.low)

                # Update the last merged candle in-place
                last.high = new_high
                last.low = new_low
                last.end_index = i
            else:
                # Update direction based on the relationship between c and last
                if c.high > last.high and c.low > last.low:
                    direction = Direction.UP
                elif c.high < last.high and c.low < last.low:
                    direction = Direction.DOWN
                # If neither condition is met, keep current direction

                merged.append(
                    MergedCandle(
                        timestamp=c.timestamp,
                        high=c.high,
                        low=c.low,
                        start_index=i,
                        end_index=i,
                        direction=direction,
                    )
                )

        logger.info(
            "K-line merge complete: %d input, %d output",
            len(candles),
            len(merged),
        )

        return merged

    @staticmethod
    def _has_inclusion(last: MergedCandle, candle: RawCandle) -> bool:
        """业务模块说明。"""
        # last includes candle
        if last.high >= candle.high and last.low <= candle.low:
            return True
        # candle includes last
        if candle.high >= last.high and candle.low <= last.low:
            return True
        return False


