"""业务模块说明。"""

from app.entities.stock import StockCandle
from app.entities.analysis_result import AnalysisResult
from app.entities.watchlist import WatchlistItem
from app.entities.backtest import BacktestResult

__all__ = [
    "StockCandle",
    "AnalysisResult",
    "WatchlistItem",
    "BacktestResult",
]
