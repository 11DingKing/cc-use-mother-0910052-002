"""业务模块说明。"""

from datetime import datetime, timedelta
from typing import List, Optional
import logging

from app.data.fetcher import DataFetcher, FetchResult
from app.chan.models import RawCandle
from app.config import DATA_SOURCE_CONFIG

logger = logging.getLogger(__name__)


class YahooFetcher(DataFetcher):
    """业务模块说明。"""
    
    def __init__(self):
        self.config = DATA_SOURCE_CONFIG.get("yahoo", {})
        self.timeout = self.config.get("timeout", 30)
        self._yfinance = None
    
    @property
    def source_name(self) -> str:
        return "yahoo"
    
    def _get_yfinance(self):
        """业务模块说明。"""
        if self._yfinance is None:
            try:
                import yfinance as yf
                self._yfinance = yf
            except ImportError:
                logger.error("yfinance not installed")
                raise ImportError("yfinance library not installed")
        return self._yfinance
    
    def is_available(self) -> bool:
        """业务模块说明。"""
        if not self.config.get("enabled", True):
            return False
        try:
            self._get_yfinance()
            return True
        except ImportError:
            return False
    
    def fetch_candles(
        self,
        stock_code: str,
        period: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> FetchResult:
        """业务模块说明。"""
        try:
            yf = self._get_yfinance()
            
            # 设置默认日期范围
            if end_date is None:
                end_date = datetime.now()
            if start_date is None:
                start_date = end_date - timedelta(days=365)
            
            # 映射周期到 yfinance interval
            interval_map = {
                "daily": "1d",
                "60min": "1h",
                "30min": "30m",
                "15min": "15m",
            }
            interval = interval_map.get(period, "1d")
            
            # 转换中国股票代码格式
            yahoo_code = self.convert_china_code(stock_code)
            logger.info(f"Fetching {yahoo_code} from Yahoo Finance (original: {stock_code})")
            
            # 获取数据
            ticker = yf.Ticker(yahoo_code)
            df = ticker.history(
                start=start_date,
                end=end_date,
                interval=interval,
            )
            
            if df is None or df.empty:
                return FetchResult(
                    candles=[],
                    stock_code=stock_code,
                    period=period,
                    start_time=start_date,
                    end_time=end_date,
                    source=self.source_name,
                    success=True,
                    metadata={"message": "No data available"},
                )
            
            # 转换为 RawCandle
            candles = []
            for idx, row in df.iterrows():
                try:
                    ts = idx.to_pydatetime()
                    if ts.tzinfo is not None:
                        ts = ts.replace(tzinfo=None)
                    
                    candle = RawCandle(
                        timestamp=ts,
                        open=float(row["Open"]),
                        high=float(row["High"]),
                        low=float(row["Low"]),
                        close=float(row["Close"]),
                        volume=float(row["Volume"]),
                    )
                    candles.append(candle)
                except (KeyError, ValueError) as e:
                    logger.warning(f"Skip invalid row: {e}")
                    continue
            
            # 清洗数据
            cleaned = self.clean_candles(candles)
            
            # 标记缺失
            missing_info = self.mark_missing_data(cleaned, start_date, end_date, period)
            
            return FetchResult(
                candles=cleaned,
                stock_code=stock_code,
                period=period,
                start_time=start_date,
                end_time=end_date,
                source=self.source_name,
                success=True,
                metadata={"missing_info": missing_info},
            )
            
        except Exception as e:
            logger.error(f"Yahoo fetch error: {e}")
            return FetchResult(
                candles=[],
                stock_code=stock_code,
                period=period,
                start_time=start_date,
                end_time=end_date,
                source=self.source_name,
                success=False,
                error_message=str(e),
            )
    
    def convert_china_code(self, code: str) -> str:
        """业务模块说明。"""
        # 移除前缀
        clean_code = code.lower()
        for prefix in ("sh", "sz", "bj"):
            if clean_code.startswith(prefix):
                clean_code = clean_code[2:]
                break
        
        # 根据代码判断交易所
        if clean_code.startswith("6"):
            return f"{clean_code}.SS"  # 上海
        elif clean_code.startswith(("0", "3")):
            return f"{clean_code}.SZ"  # 深圳
        elif clean_code.startswith(("4", "8")):
            return f"{clean_code}.BJ"  # 北京
        else:
            return code  # 保持原样
