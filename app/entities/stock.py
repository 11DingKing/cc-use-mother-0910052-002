"""业务模块说明。"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Index, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class StockCandle(Base):
    """业务模块说明。"""
    __tablename__ = "stock_candles"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(20), nullable=False, index=True)
    period = Column(String(10), nullable=False, index=True)  # daily, 60min, 30min
    timestamp = Column(DateTime, nullable=False, index=True)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False, default=0.0)
    amount = Column(Float, nullable=True)  # 成交额（可选）
    
    # 数据质量标记
    is_limit_up = Column(Integer, default=0)    # 涨停标记
    is_limit_down = Column(Integer, default=0)  # 跌停标记
    is_suspended = Column(Integer, default=0)   # 停牌标记
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint('stock_code', 'period', 'timestamp', name='uix_stock_period_time'),
        Index('ix_stock_code_period', 'stock_code', 'period'),
        Index('ix_stock_code_timestamp', 'stock_code', 'timestamp'),
    )
    
    def __repr__(self):
        return (
            f"<StockCandle(code={self.stock_code}, period={self.period}, "
            f"time={self.timestamp}, O={self.open}, H={self.high}, "
            f"L={self.low}, C={self.close})>"
        )
    
    def to_dict(self) -> dict:
        """业务模块说明。"""
        return {
            "id": self.id,
            "stock_code": self.stock_code,
            "period": self.period,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "amount": self.amount,
            "is_limit_up": bool(self.is_limit_up),
            "is_limit_down": bool(self.is_limit_down),
            "is_suspended": bool(self.is_suspended),
        }
