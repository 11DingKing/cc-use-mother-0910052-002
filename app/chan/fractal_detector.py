"""业务模块说明。"""

import logging
from typing import List

from app.chan.models import MergedCandle, Fractal, FractalType

logger = logging.getLogger(__name__)


class FractalDetector:
    """业务模块说明。"""

    def detect(self, merged_candles: List[MergedCandle]) -> List[Fractal]:
        """业务模块说明。"""
        if len(merged_candles) < 3:
            logger.info(
                "Fractal detection skipped: need at least 3 merged candles, "
                "got %d",
                len(merged_candles),
            )
            return []

        fractals: List[Fractal] = []

        for i in range(1, len(merged_candles) - 1):
            left = merged_candles[i - 1]
            mid = merged_candles[i]
            right = merged_candles[i + 1]

            fractal = self._check_fractal(left, mid, right, i)
            if fractal is not None:
                fractals.append(fractal)

        logger.info(
            "Fractal detection complete: %d merged candles → %d fractals "
            "(top=%d, bottom=%d)",
            len(merged_candles),
            len(fractals),
            sum(1 for f in fractals if f.type == FractalType.TOP),
            sum(1 for f in fractals if f.type == FractalType.BOTTOM),
        )

        return fractals

    def detect_incremental(
        self,
        merged_candles: List[MergedCandle],
        existing_fractals: List[Fractal],
    ) -> List[Fractal]:
        """业务模块说明。"""
        if len(merged_candles) < 3:
            logger.info(
                "Incremental fractal detection skipped: need at least 3 "
                "merged candles, got %d",
                len(merged_candles),
            )
            return list(existing_fractals)

        if not existing_fractals:
            return self.detect(merged_candles)

        # Find the candle_index of the last existing fractal
        last_fractal_index = existing_fractals[-1].candle_index

        # Start scanning from 2 positions before the last fractal's index
        # to ensure we don't miss any fractals near the boundary.
        # The sliding window needs index i-1, i, i+1, so we need to start
        # the scan at max(1, last_fractal_index - 1) to re-check the
        # last fractal's neighborhood.
        scan_start = max(1, last_fractal_index - 1)

        # Keep existing fractals that are before the scan region
        # (i.e., their candle_index < scan_start)
        kept_fractals = [
            f for f in existing_fractals if f.candle_index < scan_start
        ]

        # Scan from scan_start to the end
        new_fractals: List[Fractal] = []
        for i in range(scan_start, len(merged_candles) - 1):
            left = merged_candles[i - 1]
            mid = merged_candles[i]
            right = merged_candles[i + 1]

            fractal = self._check_fractal(left, mid, right, i)
            if fractal is not None:
                new_fractals.append(fractal)

        result = kept_fractals + new_fractals

        logger.info(
            "Incremental fractal detection complete: kept %d existing, "
            "found %d new, total %d fractals",
            len(kept_fractals),
            len(new_fractals),
            len(result),
        )

        return result

    @staticmethod
    def _check_fractal(
        left: MergedCandle,
        mid: MergedCandle,
        right: MergedCandle,
        mid_index: int,
    ) -> Fractal | None:
        """业务模块说明。"""
        candles = [left, mid, right]

        # Top fractal: mid.high > left.high AND mid.high > right.high
        #              AND mid.low > left.low AND mid.low > right.low
        if (
            mid.high > left.high
            and mid.high > right.high
            and mid.low > left.low
            and mid.low > right.low
        ):
            return Fractal(
                type=FractalType.TOP,
                timestamp=mid.timestamp,
                price=mid.high,
                candle_index=mid_index,
                candles=candles,
            )

        # Bottom fractal: mid.low < left.low AND mid.low < right.low
        #                 AND mid.high < left.high AND mid.high < right.high
        if (
            mid.low < left.low
            and mid.low < right.low
            and mid.high < left.high
            and mid.high < right.high
        ):
            return Fractal(
                type=FractalType.BOTTOM,
                timestamp=mid.timestamp,
                price=mid.low,
                candle_index=mid_index,
                candles=candles,
            )

        return None
