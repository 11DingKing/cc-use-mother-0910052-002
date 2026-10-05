"""业务模块说明。"""

import logging
from typing import List, Optional

from app.chan.models import Bi, Zhongshu

logger = logging.getLogger(__name__)


class ZhongshuDetector:
    """业务模块说明。"""

    MIN_BI_COUNT = 3

    def detect(self, bi_list: List[Bi]) -> List[Zhongshu]:
        """业务模块说明。"""
        if len(bi_list) < self.MIN_BI_COUNT:
            return []

        zhongshu_list: List[Zhongshu] = []
        i = 0

        while i <= len(bi_list) - self.MIN_BI_COUNT:
            # Try to form a zhongshu from 3 consecutive bis starting at i
            window = bi_list[i:i + self.MIN_BI_COUNT]
            overlap = self._calculate_overlap(window)

            if overlap is None:
                # No overlap, slide window forward by 1
                i += 1
                continue

            high, low = overlap

            # Zhongshu formed with initial 3 bis
            zs_bis = list(window)

            # Check subsequent bis for extension
            j = i + self.MIN_BI_COUNT
            while j < len(bi_list):
                bi = bi_list[j]
                bi_high = max(bi.start_price, bi.end_price)
                bi_low = min(bi.start_price, bi.end_price)

                # A bi extends the zhongshu if it enters the overlap zone
                # i.e., the bi's price range intersects with [low, high]
                if bi_low < high and bi_high > low:
                    zs_bis.append(bi)
                    j += 1
                else:
                    break

            # Determine start_time and end_time from the bis
            start_time = zs_bis[0].start_fractal.timestamp
            end_time = zs_bis[-1].end_fractal.timestamp

            zhongshu = Zhongshu(
                high=high,
                low=low,
                start_time=start_time,
                end_time=end_time,
                bi_list=zs_bis,
                level=1,
            )
            zhongshu_list.append(zhongshu)

            # Move past the current zhongshu's bis to find the next one
            # Start from the bi after the last bi in this zhongshu
            i = i + len(zs_bis)

        logger.info(
            "Zhongshu detection complete: %d bis → %d zhongshus",
            len(bi_list),
            len(zhongshu_list),
        )
        return zhongshu_list

    def classify_trend(
        self, zhongshu_list: List[Zhongshu],
    ) -> List[Zhongshu]:
        """业务模块说明。"""
        if len(zhongshu_list) < 2:
            return list(zhongshu_list)

        # Create copies to avoid mutating the input
        result = [
            Zhongshu(
                high=zs.high,
                low=zs.low,
                start_time=zs.start_time,
                end_time=zs.end_time,
                bi_list=list(zs.bi_list),
                level=zs.level,
            )
            for zs in zhongshu_list
        ]

        for i in range(1, len(result)):
            prev = result[i - 1]
            curr = result[i]

            # Up trend: current low > previous high
            if curr.low > prev.high:
                prev.level = 2
                curr.level = 2

            # Down trend: current high < previous low
            elif curr.high < prev.low:
                prev.level = 2
                curr.level = 2

        logger.info(
            "Trend classification complete: %d zhongshus, %d trend zhongshus",
            len(result),
            sum(1 for zs in result if zs.level == 2),
        )
        return result

    @staticmethod
    def _calculate_overlap(
        bis: List[Bi],
    ) -> Optional[tuple]:
        """业务模块说明。"""
        if not bis:
            return None

        bi_highs = []
        bi_lows = []

        for bi in bis:
            bi_high = max(bi.start_price, bi.end_price)
            bi_low = min(bi.start_price, bi.end_price)
            bi_highs.append(bi_high)
            bi_lows.append(bi_low)

        overlap_high = min(bi_highs)
        overlap_low = max(bi_lows)

        if overlap_high > overlap_low:
            return (overlap_high, overlap_low)

        return None
