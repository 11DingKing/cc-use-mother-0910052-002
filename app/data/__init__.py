"""业务模块说明。"""

from app.data.fetcher import DataFetcher, FetchResult
from app.data.akshare_fetcher import AKShareFetcher
from app.data.yahoo_fetcher import YahooFetcher

__all__ = [
    "DataFetcher",
    "FetchResult",
    "AKShareFetcher",
    "YahooFetcher",
]
