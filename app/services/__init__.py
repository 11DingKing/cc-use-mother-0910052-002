"""业务模块说明。"""

# 延迟导入以避免循环依赖
def get_stock_service():
    from app.services.stock_service import StockService
    return StockService

def get_analysis_service():
    from app.services.analysis_service import AnalysisService
    return AnalysisService

def get_watchlist_service():
    from app.services.watchlist_service import WatchlistService
    return WatchlistService
