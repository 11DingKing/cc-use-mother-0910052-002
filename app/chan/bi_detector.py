"""业务模块说明。"""

import logging
from typing import List

from app.chan.models import MergedCandle, Fractal, FractalType, Bi, Direction

logger = logging.getLogger(__name__)


class BiDetector:
    """业务模块说明。"""

    MIN_CANDLE_COUNT = 5

    def detect(
        self,
        fractals: List[Fractal],
        merged_candles: List[MergedCandle],
    ) -> List[Bi]:
        """业务模块说明。"""
        if len(fractals) < 2:
            return []

        # Step 1: 处理连续同类型分型，选取极值
        filtered = self._filter_consecutive_same_type(fractals)

        if len(filtered) < 2:
            return []

        # Step 2: 使用改进的笔识别算法
        # 核心思想：找到能够成笔的分型对，未能成笔的中间分型需要被合并处理
        bi_list: List[Bi] = []
        
        # 构建候选分型列表，用于笔的识别
        candidates = self._build_bi_candidates(filtered)
        
        if len(candidates) < 2:
            return []
        
        # 从候选列表中连接笔
        i = 0
        while i < len(candidates) - 1:
            start_f = candidates[i]
            end_f = candidates[i + 1]
            
            # 确保类型不同
            if start_f.type == end_f.type:
                i += 1
                continue
            
            candle_count = abs(end_f.candle_index - start_f.candle_index) + 1
            
            # 确定方向
            if (start_f.type == FractalType.BOTTOM
                    and end_f.type == FractalType.TOP):
                direction = Direction.UP
            else:
                direction = Direction.DOWN
            
            bi = Bi(
                start_fractal=start_f,
                end_fractal=end_f,
                direction=direction,
                candle_count=candle_count,
                start_price=start_f.price,
                end_price=end_f.price,
            )
            bi_list.append(bi)
            i += 1

        logger.info(
            "Bi detection complete: %d fractals → %d bis",
            len(fractals),
            len(bi_list),
        )
        return bi_list
    
    def _build_bi_candidates(self, filtered: List[Fractal]) -> List[Fractal]:
        """业务模块说明。"""
        if len(filtered) < 2:
            return filtered
        
        candidates: List[Fractal] = []
        i = 0
        
        while i < len(filtered):
            start_f = filtered[i]
            
            if not candidates:
                candidates.append(start_f)
                i += 1
                continue
            
            last_candidate = candidates[-1]
            
            # 如果类型相同，选取极值
            if start_f.type == last_candidate.type:
                if start_f.type == FractalType.TOP:
                    if start_f.price > last_candidate.price:
                        candidates[-1] = start_f
                else:
                    if start_f.price < last_candidate.price:
                        candidates[-1] = start_f
                i += 1
                continue
            
            # 类型不同，检查是否满足成笔条件
            candle_count = abs(start_f.candle_index - last_candidate.candle_index) + 1
            
            if candle_count >= self.MIN_CANDLE_COUNT:
                # 满足成笔条件，添加为新候选
                candidates.append(start_f)
                i += 1
            else:
                # 不满足成笔条件，需要向后查找
                # 在后续分型中找到同类型的极值分型，或者找到满足条件的异类型分型
                found_valid = False
                best_same_type = start_f  # 当前分型作为同类型的初始候选
                
                j = i + 1
                while j < len(filtered):
                    next_f = filtered[j]
                    
                    if next_f.type == start_f.type:
                        # 同类型，更新极值
                        if start_f.type == FractalType.TOP:
                            if next_f.price > best_same_type.price:
                                best_same_type = next_f
                        else:
                            if next_f.price < best_same_type.price:
                                best_same_type = next_f
                        j += 1
                    else:
                        # 异类型，检查 best_same_type 与 last_candidate 是否能成笔
                        check_count = abs(best_same_type.candle_index - last_candidate.candle_index) + 1
                        if check_count >= self.MIN_CANDLE_COUNT:
                            candidates.append(best_same_type)
                            i = j  # 从异类型分型继续
                            found_valid = True
                            break
                        else:
                            # 仍不满足，继续向后
                            best_same_type = next_f
                            j += 1
                
                if not found_valid:
                    # 检查最后的 best_same_type
                    if best_same_type.type != last_candidate.type:
                        check_count = abs(best_same_type.candle_index - last_candidate.candle_index) + 1
                        if check_count >= self.MIN_CANDLE_COUNT:
                            candidates.append(best_same_type)
                    i = len(filtered)  # 结束循环
        
        return candidates

    def update(
        self,
        fractals: List[Fractal],
        existing_bis: List[Bi],
        merged_candles: List[MergedCandle],
    ) -> List[Bi]:
        """业务模块说明。"""
        if not existing_bis:
            return self.detect(fractals, merged_candles)

        # 找到最后一笔的结束分型索引
        last_bi = existing_bis[-1]
        last_end_index = last_bi.end_fractal.candle_index

        # 保留结束分型在 last_end_index 之前的笔
        kept_bis = [
            bi for bi in existing_bis
            if bi.end_fractal.candle_index < last_end_index
        ]

        # 从最后一笔的起始分型位置开始重新检测
        last_start_index = last_bi.start_fractal.candle_index
        remaining_fractals = [
            f for f in fractals
            if f.candle_index >= last_start_index
        ]

        new_bis = self.detect(remaining_fractals, merged_candles)

        result = kept_bis + new_bis

        logger.info(
            "Bi update complete: kept %d, new %d, total %d",
            len(kept_bis),
            len(new_bis),
            len(result),
        )
        return result

    @staticmethod
    def _filter_consecutive_same_type(
        fractals: List[Fractal],
    ) -> List[Fractal]:
        """业务模块说明。"""
        if not fractals:
            return []

        filtered: List[Fractal] = [fractals[0]]

        for i in range(1, len(fractals)):
            current = fractals[i]
            last = filtered[-1]

            if current.type == last.type:
                # 同类型：选取极值
                if current.type == FractalType.TOP:
                    if current.price > last.price:
                        filtered[-1] = current
                elif current.type == FractalType.BOTTOM:
                    if current.price < last.price:
                        filtered[-1] = current
            else:
                filtered.append(current)

        return filtered
