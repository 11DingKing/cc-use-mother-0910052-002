"""业务模块说明。"""

from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.entities.stock import StockCandle
from app.chan.models import RawCandle


class StockMapper:
    """业务模块说明。"""
    
    def __init__(self, session: Session):
        self.session = session
    
    def create(self, candle: StockCandle) -> StockCandle:
        """业务模块说明。"""
        self.session.add(candle)
        self.session.flush()
        return candle
    
    def create_batch(self, candles: List[StockCandle]) -> int:
        """业务模块说明。"""
        self.session.add_all(candles)
        self.session.flush()
        return len(candles)
    
    def get_by_id(self, candle_id: int) -> Optional[StockCandle]:
        """业务模块说明。"""
        return self.session.query(StockCandle).filter(
            StockCandle.id == candle_id
        ).first()
    
    def get_candles(
        self,
        stock_code: str,
        period: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[StockCandle]:
        """业务模块说明。"""
        query = self.session.query(StockCandle).filter(
            and_(
                StockCandle.stock_code == stock_code,
                StockCandle.period == period,
            )
        )
        
        if start_time:
            query = query.filter(StockCandle.timestamp >= start_time)
        if end_time:
            query = query.filter(StockCandle.timestamp <= end_time)
        
        query = query.order_by(StockCandle.timestamp.asc())
        
        if limit:
            query = query.limit(limit)
        
        return query.all()
    
    def get_latest_candle(
        self,
        stock_code: str,
        period: str,
    ) -> Optional[StockCandle]:
        """业务模块说明。"""
        return self.session.query(StockCandle).filter(
            and_(
                StockCandle.stock_code == stock_code,
                StockCandle.period == period,
            )
        ).order_by(StockCandle.timestamp.desc()).first()
    
    def update(self, candle: StockCandle) -> StockCandle:
        """业务模块说明。"""
        self.session.merge(candle)
        self.session.flush()
        return candle
    
    def delete_by_stock_period(
        self,
        stock_code: str,
        period: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> int:
        """业务模块说明。"""
        query = self.session.query(StockCandle).filter(
            and_(
                StockCandle.stock_code == stock_code,
                StockCandle.period == period,
            )
        )
        
        if start_time:
            query = query.filter(StockCandle.timestamp >= start_time)
        if end_time:
            query = query.filter(StockCandle.timestamp <= end_time)
        
        count = query.delete(synchronize_session=False)
        self.session.flush()
        return count
    
    def upsert_candles(self, candles: List[StockCandle]) -> int:
        """业务模块说明。"""
        count = 0
        for candle in candles:
            existing = self.session.query(StockCandle).filter(
                and_(
                    StockCandle.stock_code == candle.stock_code,
                    StockCandle.period == candle.period,
                    StockCandle.timestamp == candle.timestamp,
                )
            ).first()
            
            if existing:
                existing.open = candle.open
                existing.high = candle.high
                existing.low = candle.low
                existing.close = candle.close
                existing.volume = candle.volume
                existing.amount = candle.amount
                existing.is_limit_up = candle.is_limit_up
                existing.is_limit_down = candle.is_limit_down
                existing.is_suspended = candle.is_suspended
            else:
                self.session.add(candle)
            count += 1
        
        self.session.flush()
        return count
    
    def to_raw_candles(self, candles: List[StockCandle]) -> List[RawCandle]:
        """业务模块说明。"""
        return [
            RawCandle(
                timestamp=c.timestamp,
                open=c.open,
                high=c.high,
                low=c.low,
                close=c.close,
                volume=c.volume,
            )
            for c in candles
        ]
    
    def from_raw_candles(
        self,
        candles: List[RawCandle],
        stock_code: str,
        period: str,
    ) -> List[StockCandle]:
        """业务模块说明。"""
        return [
            StockCandle(
                stock_code=stock_code,
                period=period,
                timestamp=c.timestamp,
                open=c.open,
                high=c.high,
                low=c.low,
                close=c.close,
                volume=c.volume,
            )
            for c in candles
        ]
    
    def count_candles(self, stock_code: str, period: str) -> int:
        """业务模块说明。"""
        return self.session.query(StockCandle).filter(
            and_(
                StockCandle.stock_code == stock_code,
                StockCandle.period == period,
            )
        ).count()
