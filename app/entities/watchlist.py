"""业务模块说明。"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Index, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class WatchlistItem(Base):
    """业务模块说明。"""
    __tablename__ = "watchlist_items"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(20), nullable=False, index=True)
    stock_name = Column(String(50), nullable=True)
    
    # 排序和分组
    sort_order = Column(Integer, default=0)
    group_name = Column(String(50), nullable=True)  # 分组名称（可选）
    
    # 缠论状态摘要（便于列表展示）
    latest_signal_type = Column(String(20), nullable=True)
    latest_signal_time = Column(DateTime, nullable=True)
    latest_signal_price = Column(Float, nullable=True)
    signal_strength = Column(Float, nullable=True)  # 信号强度 0-1
    
    # 当前价格信息
    current_price = Column(Float, nullable=True)
    price_change_pct = Column(Float, nullable=True)  # 涨跌幅
    
    # 标记
    is_new_signal = Column(Integer, default=0)  # 新信号标记（用于高亮）
    notes = Column(String(500), nullable=True)  # 用户备注
    
    # 元数据
    added_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint('stock_code', name='uix_watchlist_stock_code'),
        Index('ix_watchlist_signal_strength', 'signal_strength'),
        Index('ix_watchlist_latest_signal', 'latest_signal_type'),
    )
    
    def __repr__(self):
        return (
            f"<WatchlistItem(code={self.stock_code}, name={self.stock_name}, "
            f"signal={self.latest_signal_type})>"
        )
    
    def to_dict(self) -> dict:
        """业务模块说明。"""
        return {
            "id": self.id,
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "sort_order": self.sort_order,
            "group_name": self.group_name,
            "latest_signal_type": self.latest_signal_type,
            "latest_signal_time": self.latest_signal_time.isoformat() if self.latest_signal_time else None,
            "latest_signal_price": self.latest_signal_price,
            "signal_strength": self.signal_strength,
            "current_price": self.current_price,
            "price_change_pct": self.price_change_pct,
            "is_new_signal": bool(self.is_new_signal),
            "notes": self.notes,
            "added_at": self.added_at.isoformat() if self.added_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
