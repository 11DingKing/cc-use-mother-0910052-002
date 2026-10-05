"""业务模块说明。"""

import logging
from typing import List, Optional, Tuple

from app.chan.models import Bi, Duan, Direction

logger = logging.getLogger(__name__)


class DuanDetector:
    """业务模块说明。"""

    MIN_BI_COUNT = 3

    def detect(self, bi_list: List[Bi]) -> List[Duan]:
        """业务模块说明。"""
        if len(bi_list) < self.MIN_BI_COUNT:
            return []

        duan_list: List[Duan] = []
        start_idx = 0

        while start_idx < len(bi_list):
            result = self._find_next_duan(bi_list, start_idx)
            if result is None:
                break

            duan, end_idx = result
            duan_list.append(duan)

            # Next segment starts from the last bi of the current segment
            # (segments share the boundary bi)
            start_idx = end_idx

        logger.info(
            "Duan detection complete: %d bis → %d duans",
            len(bi_list),
            len(duan_list),
        )
        return duan_list

    def update(
        self,
        bi_list: List[Bi],
        existing_duans: List[Duan],
    ) -> List[Duan]:
        """业务模块说明。"""
        if not existing_duans:
            return self.detect(bi_list)

        if len(bi_list) < self.MIN_BI_COUNT:
            return []

        # Find the index in bi_list where the last existing duan's start_bi is
        last_duan = existing_duans[-1]
        recompute_bi_idx = self._find_bi_index(bi_list, last_duan.start_bi)

        if recompute_bi_idx is None:
            # Can't find the start bi of the last duan; recompute everything
            return self.detect(bi_list)

        # Keep all duans except the last one (which may need recomputation)
        kept_duans = list(existing_duans[:-1])

        # Recompute from the start of the last duan
        remaining_bis = bi_list[recompute_bi_idx:]
        new_duans = self.detect(remaining_bis)

        result = kept_duans + new_duans

        logger.info(
            "Duan update complete: kept %d, new %d, total %d",
            len(kept_duans),
            len(new_duans),
            len(result),
        )
        return result

    def _find_next_duan(
        self,
        bi_list: List[Bi],
        start_idx: int,
    ) -> Optional[Tuple[Duan, int]]:
        """业务模块说明。"""
        remaining = len(bi_list) - start_idx
        if remaining < self.MIN_BI_COUNT:
            return None

        # The direction of the segment is the same as the first bi's direction
        direction = bi_list[start_idx].direction

        # We need at least 3 bis to form a segment.
        # Then we extend and check the characteristic sequence for a fractal
        # that signals the end of the segment.
        # The characteristic sequence is built from the odd-numbered bis
        # (1st, 3rd, 5th... counting from 1) within the candidate segment.
        # These are the bis that go in the same direction as the segment.

        # Start with minimum 3 bis and try to find where the segment ends
        for end_idx in range(start_idx + 2, len(bi_list)):
            candidate_bis = bi_list[start_idx:end_idx + 1]
            bi_count = len(candidate_bis)

            if bi_count < self.MIN_BI_COUNT:
                continue

            # Check if the characteristic sequence shows a fractal reversal
            if self._has_characteristic_fractal(candidate_bis, direction):
                duan = self._create_duan(candidate_bis, direction)
                return duan, end_idx

        # If no fractal found but we have enough bis, check if the last
        # group of bis forms a valid segment (end of data case)
        return None

    def _has_characteristic_fractal(
        self,
        bis: List[Bi],
        direction: Direction,
    ) -> bool:
        """业务模块说明。"""
        # Extract characteristic sequence: odd-numbered bis (0-indexed: 0, 2, 4...)
        # These are the bis that go in the same direction as the segment
        char_seq = self._build_characteristic_sequence(bis, direction)

        if len(char_seq) < 3:
            return False

        # Check the last 3 elements for a fractal
        # We only need to check the most recent potential fractal
        for i in range(2, len(char_seq)):
            left = char_seq[i - 2]
            mid = char_seq[i - 1]
            right = char_seq[i]

            if direction == Direction.UP:
                # For upward segment, check for top fractal in char sequence
                if (mid[0] > left[0] and mid[0] > right[0]
                        and mid[1] > left[1] and mid[1] > right[1]):
                    return True
            else:
                # For downward segment, check for bottom fractal in char sequence
                if (mid[1] < left[1] and mid[1] < right[1]
                        and mid[0] < left[0] and mid[0] < right[0]):
                    return True

        return False

    @staticmethod
    def _build_characteristic_sequence(
        bis: List[Bi],
        direction: Direction,
    ) -> List[Tuple[float, float]]:
        """业务模块说明。"""
        char_seq: List[Tuple[float, float]] = []

        # Odd-numbered bis (1st, 3rd, 5th... = indices 0, 2, 4...)
        for i in range(0, len(bis), 2):
            bi = bis[i]
            if direction == Direction.UP:
                # Upward bi: high = end_price (top), low = start_price (bottom)
                high = max(bi.start_price, bi.end_price)
                low = min(bi.start_price, bi.end_price)
            else:
                # Downward bi: high = start_price (top), low = end_price (bottom)
                high = max(bi.start_price, bi.end_price)
                low = min(bi.start_price, bi.end_price)
            char_seq.append((high, low))

        return char_seq

    @staticmethod
    def _create_duan(bis: List[Bi], direction: Direction) -> Duan:
        """业务模块说明。"""
        start_bi = bis[0]
        end_bi = bis[-1]

        if direction == Direction.UP:
            start_price = min(start_bi.start_price, start_bi.end_price)
            end_price = max(end_bi.start_price, end_bi.end_price)
        else:
            start_price = max(start_bi.start_price, start_bi.end_price)
            end_price = min(end_bi.start_price, end_bi.end_price)

        return Duan(
            start_bi=start_bi,
            end_bi=end_bi,
            direction=direction,
            bi_list=list(bis),
            start_price=start_price,
            end_price=end_price,
        )

    @staticmethod
    def _find_bi_index(bi_list: List[Bi], target_bi: Bi) -> Optional[int]:
        """业务模块说明。"""
        for i, bi in enumerate(bi_list):
            if (bi.start_fractal.timestamp == target_bi.start_fractal.timestamp
                    and bi.end_fractal.timestamp == target_bi.end_fractal.timestamp
                    and bi.start_price == target_bi.start_price
                    and bi.end_price == target_bi.end_price):
                return i
        return None
