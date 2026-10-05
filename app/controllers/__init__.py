"""业务模块说明。"""

from app.controllers.stock_controller import router as stock_router
from app.controllers.analysis_controller import router as analysis_router
from app.controllers.watchlist_controller import router as watchlist_router
from app.controllers.backtest_controller import router as backtest_router
from app.controllers.trading_controller import router as trading_router

__all__ = [
    "stock_router",
    "analysis_router",
    "watchlist_router",
    "backtest_router",
    "trading_router",
]
