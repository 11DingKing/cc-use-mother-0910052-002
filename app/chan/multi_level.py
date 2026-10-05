"""业务模块说明。"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from app.chan.models import Signal, SignalType

logger = logging.getLogger(__name__)


# 周期级别优先级（数字越大级别越大）
PERIOD_PRIORITY = {
    "monthly": 5,
    "weekly": 4,
    "daily": 3,
    "60min": 2,
    "30min": 1,
    "15min": 0,
}


@dataclass
class CombinedSignal:
    """业务模块说明。"""
    stock_code: str
    signal_type: SignalType
    timestamp: datetime
    price: float
    primary_level: str  # 主级别（大级别）
    secondary_levels: List[str] = field(default_factory=list)  # 辅助级别
    strength: float = 0.0
    is_strong_confirmation: bool = False  # 是否为强确认信号
    has_conflict: bool = False  # 是否存在冲突
    conflict_details: Dict = field(default_factory=dict)


class MultiLevelLinkage:
    """业务模块说明。"""

    def __init__(self):
        self.period_priority = PERIOD_PRIORITY

    def align_results(
        self,
        results_by_period: Dict[str, List[Signal]],
        time_window_minutes: int = 60,
    ) -> Dict[datetime, Dict[str, List[Signal]]]:
        """业务模块说明。"""
        if not results_by_period:
            return {}

        # 收集所有信号的时间戳
        all_timestamps: List[datetime] = []
        for signals in results_by_period.values():
            for signal in signals:
                all_timestamps.append(signal.timestamp)

        if not all_timestamps:
            return {}

        # 按时间排序
        all_timestamps.sort()

        # 按时间窗口分组
        aligned: Dict[datetime, Dict[str, List[Signal]]] = {}
        window_delta = time_window_minutes * 60  # 转换为秒

        for period, signals in results_by_period.items():
            for signal in signals:
                # 找到最近的时间窗口
                window_start = self._get_window_start(
                    signal.timestamp, window_delta,
                )
                if window_start not in aligned:
                    aligned[window_start] = {}
                if period not in aligned[window_start]:
                    aligned[window_start][period] = []
                aligned[window_start][period].append(signal)

        logger.info(
            "Aligned %d periods into %d time windows",
            len(results_by_period),
            len(aligned),
        )
        return aligned

    def generate_combined_signal(
        self,
        signals_by_period: Dict[str, List[Signal]],
    ) -> List[CombinedSignal]:
        """业务模块说明。"""
        if not signals_by_period:
            return []

        combined_signals: List[CombinedSignal] = []

        # 按时间对齐
        aligned = self.align_results(signals_by_period)

        for window_time, period_signals in aligned.items():
            # 获取各级别的信号
            signals_with_priority = self._get_signals_with_priority(period_signals)

            if not signals_with_priority:
                continue

            # 分析信号组合
            combined = self._analyze_signal_combination(
                window_time, signals_with_priority,
            )
            if combined:
                combined_signals.extend(combined)

        # 按时间排序
        combined_signals.sort(key=lambda s: s.timestamp)

        logger.info(
            "Generated %d combined signals from %d periods",
            len(combined_signals),
            len(signals_by_period),
        )
        return combined_signals

    def _get_window_start(
        self, timestamp: datetime, window_seconds: int,
    ) -> datetime:
        """业务模块说明。"""
        epoch = datetime(1970, 1, 1)
        total_seconds = int((timestamp - epoch).total_seconds())
        window_start_seconds = (total_seconds // window_seconds) * window_seconds
        return epoch + __import__("datetime").timedelta(seconds=window_start_seconds)

    def _get_signals_with_priority(
        self,
        period_signals: Dict[str, List[Signal]],
    ) -> List[Tuple[int, str, Signal]]:
        """业务模块说明。"""
        result = []
        for period, signals in period_signals.items():
            priority = self.period_priority.get(period, 0)
            for signal in signals:
                result.append((priority, period, signal))

        # 按优先级降序排列（大级别在前）
        result.sort(key=lambda x: -x[0])
        return result

    def _analyze_signal_combination(
        self,
        window_time: datetime,
        signals_with_priority: List[Tuple[int, str, Signal]],
    ) -> List[CombinedSignal]:
        """业务模块说明。"""
        if not signals_with_priority:
            return []

        combined_signals: List[CombinedSignal] = []

        # 获取最大级别的信号作为主信号
        primary_priority, primary_period, primary_signal = signals_with_priority[0]

        # 检查是否有冲突
        has_conflict, conflict_details = self._check_conflict(signals_with_priority)

        # 检查是否为强确认信号
        is_strong, secondary_levels = self._check_strong_confirmation(
            signals_with_priority,
        )

        # 计算综合强度
        strength = self._calculate_combined_strength(
            signals_with_priority, is_strong, has_conflict,
        )

        combined = CombinedSignal(
            stock_code=primary_signal.stock_code,
            signal_type=primary_signal.signal_type,
            timestamp=window_time,
            price=primary_signal.price,
            primary_level=primary_period,
            secondary_levels=secondary_levels,
            strength=strength,
            is_strong_confirmation=is_strong,
            has_conflict=has_conflict,
            conflict_details=conflict_details,
        )
        combined_signals.append(combined)

        return combined_signals

    def _check_conflict(
        self,
        signals_with_priority: List[Tuple[int, str, Signal]],
    ) -> Tuple[bool, Dict]:
        """业务模块说明。"""
        if len(signals_with_priority) < 2:
            return False, {}

        # 获取主信号方向
        _, primary_period, primary_signal = signals_with_priority[0]
        primary_is_buy = primary_signal.signal_type in (
            SignalType.BUY_1, SignalType.BUY_2, SignalType.BUY_3,
        )

        conflict_periods = []
        for priority, period, signal in signals_with_priority[1:]:
            signal_is_buy = signal.signal_type in (
                SignalType.BUY_1, SignalType.BUY_2, SignalType.BUY_3,
            )
            if signal_is_buy != primary_is_buy:
                conflict_periods.append({
                    "period": period,
                    "signal_type": signal.signal_type.value,
                    "direction": "buy" if signal_is_buy else "sell",
                })

        if conflict_periods:
            return True, {
                "primary_period": primary_period,
                "primary_direction": "buy" if primary_is_buy else "sell",
                "conflicting_periods": conflict_periods,
            }

        return False, {}

    def _check_strong_confirmation(
        self,
        signals_with_priority: List[Tuple[int, str, Signal]],
    ) -> Tuple[bool, List[str]]:
        """业务模块说明。"""
        if len(signals_with_priority) < 2:
            return False, []

        _, primary_period, primary_signal = signals_with_priority[0]
        secondary_levels = []

        # 检查大级别是否为第一类买卖点
        if primary_signal.signal_type == SignalType.BUY_1:
            # 查找小级别的第二类买点
            for priority, period, signal in signals_with_priority[1:]:
                if signal.signal_type == SignalType.BUY_2:
                    secondary_levels.append(period)

        elif primary_signal.signal_type == SignalType.SELL_1:
            # 查找小级别的第二类卖点
            for priority, period, signal in signals_with_priority[1:]:
                if signal.signal_type == SignalType.SELL_2:
                    secondary_levels.append(period)

        is_strong = len(secondary_levels) > 0
        return is_strong, secondary_levels

    def _calculate_combined_strength(
        self,
        signals_with_priority: List[Tuple[int, str, Signal]],
        is_strong: bool,
        has_conflict: bool,
    ) -> float:
        """业务模块说明。"""
        if not signals_with_priority:
            return 0.0

        _, _, primary_signal = signals_with_priority[0]
        base_strength = primary_signal.strength

        # 强确认加成
        if is_strong:
            base_strength += 0.2

        # 冲突惩罚
        if has_conflict:
            base_strength -= 0.2

        # 多级别共振加成
        primary_is_buy = primary_signal.signal_type in (
            SignalType.BUY_1, SignalType.BUY_2, SignalType.BUY_3,
        )
        resonance_count = 0
        for _, _, signal in signals_with_priority[1:]:
            signal_is_buy = signal.signal_type in (
                SignalType.BUY_1, SignalType.BUY_2, SignalType.BUY_3,
            )
            if signal_is_buy == primary_is_buy:
                resonance_count += 1

        base_strength += resonance_count * 0.1

        # 限制在 [0, 1] 范围内
        return max(0.0, min(1.0, base_strength))

