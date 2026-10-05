"""业务模块说明。"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from app.chan.models import RawCandle


@dataclass
class FetchResult:
    """业务模块说明。"""
    candles: List[RawCandle]
    stock_code: str
    period: str
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    source: str
    success: bool
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class DataFetcher(ABC):
    """业务模块说明。"""
    
    @property
    @abstractmethod
    def source_name(self) -> str:
        """业务模块说明。"""
        pass
    
    @abstractmethod
    def fetch_candles(
        self,
        stock_code: str,
        period: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> FetchResult:
        """业务模块说明。"""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """业务模块说明。"""
        pass
    
    def clean_candles(self, candles: List[RawCandle]) -> List[RawCandle]:
        """业务模块说明。"""
        cleaned = []
        for c in candles:
            # 跳过停牌数据
            if c.volume == 0:
                continue
            # 跳过价格异常
            if c.high < c.low:
                continue
            if c.open <= 0 or c.close <= 0:
                continue
            cleaned.append(c)
        
        # 按时间排序
        cleaned.sort(key=lambda x: x.timestamp)
        return cleaned
    
    def align_timestamps(
        self,
        candles: List[RawCandle],
        period: str,
    ) -> List[RawCandle]:
        """业务模块说明。"""
        # 基础实现：直接返回，子类可覆盖
        return candles
    
    def mark_missing_data(
        self,
        candles: List[RawCandle],
        start_date: datetime,
        end_date: datetime,
        period: str,
    ) -> Dict[str, Any]:
        """业务模块说明。"""
        if not candles:
            return {
                "has_missing": True,
                "missing_ranges": [(start_date, end_date)],
            }
        
        missing_ranges = []
        
        # 检查开始时间之前的缺失
        if candles[0].timestamp > start_date:
            missing_ranges.append((start_date, candles[0].timestamp))
        
        # 检查结束时间之后的缺失
        if candles[-1].timestamp < end_date:
            missing_ranges.append((candles[-1].timestamp, end_date))
        
        # 检查中间的缺失（简化实现，只检查日线）
        if period == "daily" and len(candles) > 1:
            from datetime import timedelta
            for i in range(1, len(candles)):
                gap = (candles[i].timestamp - candles[i-1].timestamp).days
                if gap > 3:  # 超过3天视为缺失（考虑周末）
                    missing_ranges.append((
                        candles[i-1].timestamp,
                        candles[i].timestamp,
                    ))
        
        return {
            "has_missing": len(missing_ranges) > 0,
            "missing_ranges": missing_ranges,
        }
