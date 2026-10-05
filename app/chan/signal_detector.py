"""业务模块说明。"""

import logging
from typing import List, Optional, Tuple

from app.chan.models import (
    Bi,
    Direction,
    Duan,
    Signal,
    SignalType,
    Zhongshu,
)
from app.chan.macd import calculate_macd, calculate_macd_area

logger = logging.getLogger(__name__)


class SignalDetector:
    """业务模块说明。"""

    def __init__(self, stock_code: str, level: str):
        self.stock_code = stock_code
        self.level = level

    def detect_buy_1(
        self,
        bi_list: List[Bi],
        zhongshu_list: List[Zhongshu],
        close_prices: Optional[List[float]] = None,
    ) -> List[Signal]:
        """业务模块说明。"""
        signals: List[Signal] = []
        if len(bi_list) < 4:
            return signals

        dif, dea = None, None
        if close_prices and len(close_prices) >= 26:
            dif, dea, _ = calculate_macd(close_prices)

        for i in range(3, len(bi_list)):
            bi_curr = bi_list[i]
            if bi_curr.direction != Direction.DOWN:
                continue

            bi_prev_down = None
            for j in range(i - 2, -1, -1):
                if bi_list[j].direction == Direction.DOWN:
                    bi_prev_down = bi_list[j]
                    break
            if bi_prev_down is None:
                continue

            curr_low = min(bi_curr.start_price, bi_curr.end_price)
            prev_low = min(bi_prev_down.start_price, bi_prev_down.end_price)
            if curr_low >= prev_low:
                continue

            is_divergence = False
            strength = 0.5
            if dif is not None and dea is not None:
                is_divergence, strength = self._check_macd_divergence_down(
                    bi_prev_down, bi_curr, dif, dea,
                )
            else:
                is_divergence, strength = self._check_price_divergence_down(
                    bi_prev_down, bi_curr,
                )

            if is_divergence:
                signals.append(Signal(
                    stock_code=self.stock_code,
                    signal_type=SignalType.BUY_1,
                    timestamp=bi_curr.end_fractal.timestamp,
                    price=curr_low,
                    level=self.level,
                    strength=strength,
                    details={
                        "prev_low": prev_low,
                        "curr_low": curr_low,
                        "divergence_type": "bottom",
                        "bi_index": i,
                    },
                ))

        logger.info("Buy 1 detection: %d bis -> %d signals", len(bi_list), len(signals))
        return signals

    def detect_sell_1(
        self,
        bi_list: List[Bi],
        zhongshu_list: List[Zhongshu],
        close_prices: Optional[List[float]] = None,
    ) -> List[Signal]:
        """业务模块说明。"""
        signals: List[Signal] = []
        if len(bi_list) < 4:
            return signals

        dif, dea = None, None
        if close_prices and len(close_prices) >= 26:
            dif, dea, _ = calculate_macd(close_prices)

        for i in range(3, len(bi_list)):
            bi_curr = bi_list[i]
            if bi_curr.direction != Direction.UP:
                continue

            bi_prev_up = None
            for j in range(i - 2, -1, -1):
                if bi_list[j].direction == Direction.UP:
                    bi_prev_up = bi_list[j]
                    break
            if bi_prev_up is None:
                continue

            curr_high = max(bi_curr.start_price, bi_curr.end_price)
            prev_high = max(bi_prev_up.start_price, bi_prev_up.end_price)
            if curr_high <= prev_high:
                continue

            is_divergence = False
            strength = 0.5
            if dif is not None and dea is not None:
                is_divergence, strength = self._check_macd_divergence_up(
                    bi_prev_up, bi_curr, dif, dea,
                )
            else:
                is_divergence, strength = self._check_price_divergence_up(
                    bi_prev_up, bi_curr,
                )

            if is_divergence:
                signals.append(Signal(
                    stock_code=self.stock_code,
                    signal_type=SignalType.SELL_1,
                    timestamp=bi_curr.end_fractal.timestamp,
                    price=curr_high,
                    level=self.level,
                    strength=strength,
                    details={
                        "prev_high": prev_high,
                        "curr_high": curr_high,
                        "divergence_type": "top",
                        "bi_index": i,
                    },
                ))

        logger.info("Sell 1 detection: %d bis -> %d signals", len(bi_list), len(signals))
        return signals

    # ------------------------------------------------------------------
    # 第二类买卖点
    # ------------------------------------------------------------------

    def detect_buy_2(
        self,
        bi_list: List[Bi],
        buy_1_signals: List[Signal],
    ) -> List[Signal]:
        """业务模块说明。"""
        signals: List[Signal] = []
        if not buy_1_signals or len(bi_list) < 2:
            return signals

        for buy_1 in buy_1_signals:
            buy_1_bi_index = buy_1.details.get("bi_index")
            buy_1_price = buy_1.price
            if buy_1_bi_index is None:
                continue

            pullback_idx = None
            for k in range(buy_1_bi_index + 1, len(bi_list)):
                if bi_list[k].direction == Direction.DOWN:
                    pullback_idx = k
                    break
            if pullback_idx is None:
                continue

            pullback_bi = bi_list[pullback_idx]
            pullback_low = min(pullback_bi.start_price, pullback_bi.end_price)

            if pullback_low > buy_1_price:
                strength = min(
                    1.0,
                    (pullback_low - buy_1_price) / max(buy_1_price, 1e-9),
                )
                strength = min(0.9, 0.4 + strength * 5)
                signals.append(Signal(
                    stock_code=self.stock_code,
                    signal_type=SignalType.BUY_2,
                    timestamp=pullback_bi.end_fractal.timestamp,
                    price=pullback_low,
                    level=self.level,
                    strength=strength,
                    details={
                        "buy_1_price": buy_1_price,
                        "pullback_low": pullback_low,
                        "bi_index": pullback_idx,
                    },
                ))

        logger.info("Buy 2 detection: %d buy_1 -> %d buy_2", len(buy_1_signals), len(signals))
        return signals

    def detect_sell_2(
        self,
        bi_list: List[Bi],
        sell_1_signals: List[Signal],
    ) -> List[Signal]:
        """业务模块说明。"""
        signals: List[Signal] = []
        if not sell_1_signals or len(bi_list) < 2:
            return signals

        for sell_1 in sell_1_signals:
            sell_1_bi_index = sell_1.details.get("bi_index")
            sell_1_price = sell_1.price
            if sell_1_bi_index is None:
                continue

            rebound_idx = None
            for k in range(sell_1_bi_index + 1, len(bi_list)):
                if bi_list[k].direction == Direction.UP:
                    rebound_idx = k
                    break
            if rebound_idx is None:
                continue

            rebound_bi = bi_list[rebound_idx]
            rebound_high = max(rebound_bi.start_price, rebound_bi.end_price)

            if rebound_high < sell_1_price:
                strength = min(
                    1.0,
                    (sell_1_price - rebound_high) / max(sell_1_price, 1e-9),
                )
                strength = min(0.9, 0.4 + strength * 5)
                signals.append(Signal(
                    stock_code=self.stock_code,
                    signal_type=SignalType.SELL_2,
                    timestamp=rebound_bi.end_fractal.timestamp,
                    price=rebound_high,
                    level=self.level,
                    strength=strength,
                    details={
                        "sell_1_price": sell_1_price,
                        "rebound_high": rebound_high,
                        "bi_index": rebound_idx,
                    },
                ))

        logger.info("Sell 2 detection: %d sell_1 -> %d sell_2", len(sell_1_signals), len(signals))
        return signals

    # ------------------------------------------------------------------
    # 第三类买卖点
    # ------------------------------------------------------------------

    def detect_buy_3(
        self,
        bi_list: List[Bi],
        zhongshu_list: List[Zhongshu],
    ) -> List[Signal]:
        """业务模块说明。"""
        signals: List[Signal] = []
        if not zhongshu_list or len(bi_list) < 2:
            return signals

        for zs in zhongshu_list:
            zs_end_time = zs.end_time
            zs_high = zs.high

            after_indices = [
                idx for idx, bi in enumerate(bi_list)
                if bi.start_fractal.timestamp >= zs_end_time
            ]
            if not after_indices:
                continue

            breakout_idx = None
            for idx in after_indices:
                bi = bi_list[idx]
                if bi.direction == Direction.UP:
                    if max(bi.start_price, bi.end_price) > zs_high:
                        breakout_idx = idx
                        break
            if breakout_idx is None:
                continue

            pullback_idx = None
            for k in range(breakout_idx + 1, len(bi_list)):
                if bi_list[k].direction == Direction.DOWN:
                    pullback_idx = k
                    break
            if pullback_idx is None:
                continue

            pb = bi_list[pullback_idx]
            pb_low = min(pb.start_price, pb.end_price)

            if pb_low > zs_high:
                s = min(0.9, 0.3 + min(1.0, (pb_low - zs_high) / max(zs_high, 1e-9)) * 5)
                signals.append(Signal(
                    stock_code=self.stock_code,
                    signal_type=SignalType.BUY_3,
                    timestamp=pb.end_fractal.timestamp,
                    price=pb_low,
                    level=self.level,
                    strength=s,
                    details={
                        "zhongshu_high": zs_high,
                        "zhongshu_low": zs.low,
                        "pullback_low": pb_low,
                        "bi_index": pullback_idx,
                    },
                ))

        logger.info("Buy 3 detection: %d zhongshus -> %d signals", len(zhongshu_list), len(signals))
        return signals

    def detect_sell_3(
        self,
        bi_list: List[Bi],
        zhongshu_list: List[Zhongshu],
    ) -> List[Signal]:
        """业务模块说明。"""
        signals: List[Signal] = []
        if not zhongshu_list or len(bi_list) < 2:
            return signals

        for zs in zhongshu_list:
            zs_end_time = zs.end_time
            zs_low = zs.low

            after_indices = [
                idx for idx, bi in enumerate(bi_list)
                if bi.start_fractal.timestamp >= zs_end_time
            ]
            if not after_indices:
                continue

            breakdown_idx = None
            for idx in after_indices:
                bi = bi_list[idx]
                if bi.direction == Direction.DOWN:
                    if min(bi.start_price, bi.end_price) < zs_low:
                        breakdown_idx = idx
                        break
            if breakdown_idx is None:
                continue

            rebound_idx = None
            for k in range(breakdown_idx + 1, len(bi_list)):
                if bi_list[k].direction == Direction.UP:
                    rebound_idx = k
                    break
            if rebound_idx is None:
                continue

            rb = bi_list[rebound_idx]
            rb_high = max(rb.start_price, rb.end_price)

            if rb_high < zs_low:
                s = min(0.9, 0.3 + min(1.0, (zs_low - rb_high) / max(zs_low, 1e-9)) * 5)
                signals.append(Signal(
                    stock_code=self.stock_code,
                    signal_type=SignalType.SELL_3,
                    timestamp=rb.end_fractal.timestamp,
                    price=rb_high,
                    level=self.level,
                    strength=s,
                    details={
                        "zhongshu_high": zs.high,
                        "zhongshu_low": zs_low,
                        "rebound_high": rb_high,
                        "bi_index": rebound_idx,
                    },
                ))

        logger.info("Sell 3 detection: %d zhongshus -> %d signals", len(zhongshu_list), len(signals))
        return signals

    # ------------------------------------------------------------------
    # 综合识别
    # ------------------------------------------------------------------

    def detect_all(
        self,
        bi_list: List[Bi],
        duan_list: List[Duan],
        zhongshu_list: List[Zhongshu],
        close_prices: Optional[List[float]] = None,
    ) -> List[Signal]:
        """业务模块说明。"""
        all_signals: List[Signal] = []

        buy_1 = self.detect_buy_1(bi_list, zhongshu_list, close_prices)
        sell_1 = self.detect_sell_1(bi_list, zhongshu_list, close_prices)
        buy_2 = self.detect_buy_2(bi_list, buy_1)
        sell_2 = self.detect_sell_2(bi_list, sell_1)
        buy_3 = self.detect_buy_3(bi_list, zhongshu_list)
        sell_3 = self.detect_sell_3(bi_list, zhongshu_list)

        all_signals.extend(buy_1)
        all_signals.extend(sell_1)
        all_signals.extend(buy_2)
        all_signals.extend(sell_2)
        all_signals.extend(buy_3)
        all_signals.extend(sell_3)

        all_signals.sort(key=lambda s: s.timestamp)

        logger.info(
            "Total signal detection: %d signals (B1=%d S1=%d B2=%d S2=%d B3=%d S3=%d)",
            len(all_signals), len(buy_1), len(sell_1),
            len(buy_2), len(sell_2), len(buy_3), len(sell_3),
        )
        return all_signals

    # ------------------------------------------------------------------
    # 私有辅助方法：背驰判定
    # ------------------------------------------------------------------

    def _check_macd_divergence_down(
        self, bi_prev: Bi, bi_curr: Bi,
        dif: List[float], dea: List[float],
    ) -> Tuple[bool, float]:
        """业务模块说明。"""
        try:
            prev_start = bi_prev.start_fractal.candle_index
            prev_end = bi_prev.end_fractal.candle_index
            curr_start = bi_curr.start_fractal.candle_index
            curr_end = bi_curr.end_fractal.candle_index

            max_idx = len(dif) - 1
            prev_start = min(max(prev_start, 0), max_idx)
            prev_end = min(max(prev_end, 0), max_idx)
            curr_start = min(max(curr_start, 0), max_idx)
            curr_end = min(max(curr_end, 0), max_idx)

            if prev_start > prev_end or curr_start > curr_end:
                return False, 0.5

            area_prev = calculate_macd_area(dif, dea, prev_start, prev_end)
            area_curr = calculate_macd_area(dif, dea, curr_start, curr_end)

            if area_prev > 0 and area_curr < area_prev:
                ratio = area_curr / area_prev
                strength = min(0.95, 0.5 + (1.0 - ratio) * 0.5)
                return True, strength
        except (ValueError, IndexError):
            pass
        return False, 0.5

    def _check_macd_divergence_up(
        self, bi_prev: Bi, bi_curr: Bi,
        dif: List[float], dea: List[float],
    ) -> Tuple[bool, float]:
        """业务模块说明。"""
        try:
            prev_start = bi_prev.start_fractal.candle_index
            prev_end = bi_prev.end_fractal.candle_index
            curr_start = bi_curr.start_fractal.candle_index
            curr_end = bi_curr.end_fractal.candle_index

            max_idx = len(dif) - 1
            prev_start = min(max(prev_start, 0), max_idx)
            prev_end = min(max(prev_end, 0), max_idx)
            curr_start = min(max(curr_start, 0), max_idx)
            curr_end = min(max(curr_end, 0), max_idx)

            if prev_start > prev_end or curr_start > curr_end:
                return False, 0.5

            area_prev = calculate_macd_area(dif, dea, prev_start, prev_end)
            area_curr = calculate_macd_area(dif, dea, curr_start, curr_end)

            if area_prev > 0 and area_curr < area_prev:
                ratio = area_curr / area_prev
                strength = min(0.95, 0.5 + (1.0 - ratio) * 0.5)
                return True, strength
        except (ValueError, IndexError):
            pass
        return False, 0.5

    def _check_price_divergence_down(
        self, bi_prev: Bi, bi_curr: Bi,
    ) -> Tuple[bool, float]:
        """业务模块说明。"""
        prev_range = abs(bi_prev.start_price - bi_prev.end_price)
        curr_range = abs(bi_curr.start_price - bi_curr.end_price)

        if prev_range > 0 and curr_range < prev_range:
            ratio = curr_range / prev_range
            strength = min(0.8, 0.3 + (1.0 - ratio) * 0.5)
            return True, strength
        return False, 0.5

    def _check_price_divergence_up(
        self, bi_prev: Bi, bi_curr: Bi,
    ) -> Tuple[bool, float]:
        """业务模块说明。"""
        prev_range = abs(bi_prev.start_price - bi_prev.end_price)
        curr_range = abs(bi_curr.start_price - bi_curr.end_price)

        if prev_range > 0 and curr_range < prev_range:
            ratio = curr_range / prev_range
            strength = min(0.8, 0.3 + (1.0 - ratio) * 0.5)
            return True, strength
        return False, 0.5
