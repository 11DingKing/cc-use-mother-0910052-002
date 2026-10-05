"""业务模块说明。"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Index
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class AnalysisResult(Base):
    """业务模块说明。"""
    __tablename__ = "analysis_results"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(20), nullable=False, index=True)
    period = Column(String(10), nullable=False, index=True)  # daily, 60min, 30min
    
    # 分析时间范围
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    
    # 分析结果（JSON序列化存储）
    fractals_json = Column(Text, nullable=True)    # 分型列表
    bis_json = Column(Text, nullable=True)         # 笔列表
    duans_json = Column(Text, nullable=True)       # 段列表
    zhongshus_json = Column(Text, nullable=True)   # 中枢列表
    signals_json = Column(Text, nullable=True)     # 买卖点列表
    
    # 统计信息
    fractal_count = Column(Integer, default=0)
    bi_count = Column(Integer, default=0)
    duan_count = Column(Integer, default=0)
    zhongshu_count = Column(Integer, default=0)
    signal_count = Column(Integer, default=0)
    
    # 最新信号摘要（便于快速查询）
    latest_signal_type = Column(String(20), nullable=True)
    latest_signal_time = Column(DateTime, nullable=True)
    latest_signal_price = Column(Float, nullable=True)
    
    # 元数据
    analysis_version = Column(String(10), default="1.0")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('ix_analysis_stock_period', 'stock_code', 'period'),
        Index('ix_analysis_latest_signal', 'stock_code', 'latest_signal_type'),
    )
    
    def __repr__(self):
        return (
            f"<AnalysisResult(code={self.stock_code}, period={self.period}, "
            f"signals={self.signal_count})>"
        )
    
    def to_dict(self) -> dict:
        """业务模块说明。"""
        return {
            "id": self.id,
            "stock_code": self.stock_code,
            "period": self.period,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "fractal_count": self.fractal_count,
            "bi_count": self.bi_count,
            "duan_count": self.duan_count,
            "zhongshu_count": self.zhongshu_count,
            "signal_count": self.signal_count,
            "latest_signal_type": self.latest_signal_type,
            "latest_signal_time": self.latest_signal_time.isoformat() if self.latest_signal_time else None,
            "latest_signal_price": self.latest_signal_price,
            "analysis_version": self.analysis_version,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
