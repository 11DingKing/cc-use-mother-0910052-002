"""业务模块说明。"""

from datetime import datetime, timedelta
from typing import List, Optional
import logging

from app.data.fetcher import DataFetcher, FetchResult
from app.chan.models import RawCandle
from app.config import DATA_SOURCE_CONFIG

logger = logging.getLogger(__name__)


class AKShareFetcher(DataFetcher):
    """业务模块说明。"""
    
    def __init__(self):
        self.config = DATA_SOURCE_CONFIG.get("akshare", {})
        self.timeout = self.config.get("timeout", 30)
        self._akshare = None
    
    @property
    def source_name(self) -> str:
        return "akshare"
    
    def _get_akshare(self):
        """业务模块说明。"""
        if self._akshare is None:
            try:
                import akshare as ak
                self._akshare = ak
            except ImportError:
                logger.error("akshare not installed")
                raise ImportError("akshare library not installed")
        return self._akshare
    
    def is_available(self) -> bool:
        """业务模块说明。"""
        if not self.config.get("enabled", True):
            return False
        try:
            self._get_akshare()
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
            ak = self._get_akshare()
            
            # 标准化股票代码
            code = self._normalize_code(stock_code)
            
            # 设置默认日期范围
            if end_date is None:
                end_date = datetime.now()
            if start_date is None:
                start_date = end_date - timedelta(days=365)
            
            # 根据周期获取数据
            if period == "daily":
                candles = self._fetch_daily(ak, code, start_date, end_date)
            elif period in ("60min", "30min", "15min"):
                candles = self._fetch_intraday(ak, code, period, start_date, end_date)
            else:
                return FetchResult(
                    candles=[],
                    stock_code=stock_code,
                    period=period,
                    start_time=start_date,
                    end_time=end_date,
                    source=self.source_name,
                    success=False,
                    error_message=f"Unsupported period: {period}",
                )
            
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
            logger.error(f"AKShare fetch error: {e}")
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
    
    def _normalize_code(self, stock_code: str) -> str:
        """业务模块说明。"""
        # 移除前缀
        code = stock_code.lower()
        for prefix in ("sh", "sz", "bj"):
            if code.startswith(prefix):
                code = code[2:]
                break
        return code
    
    def _fetch_daily(
        self,
        ak,
        code: str,
        start_date: datetime,
        end_date: datetime,
    ) -> List[RawCandle]:
        """业务模块说明。"""
        import time
        max_retries = 3
        
        for retry in range(max_retries):
            try:
                logger.info(f"Fetching daily data for {code} (attempt {retry + 1}/{max_retries})")
                
                df = ak.stock_zh_a_hist(
                    symbol=code,
                    period="daily",
                    start_date=start_date.strftime("%Y%m%d"),
                    end_date=end_date.strftime("%Y%m%d"),
                    adjust="qfq",
                )
                
                if df is None or df.empty:
                    logger.warning(f"No data returned for {code}")
                    return []
                
                candles = []
                for _, row in df.iterrows():
                    try:
                        candle = RawCandle(
                            timestamp=datetime.strptime(str(row["日期"]), "%Y-%m-%d"),
                            open=float(row["开盘"]),
                            high=float(row["最高"]),
                            low=float(row["最低"]),
                            close=float(row["收盘"]),
                            volume=float(row["成交量"]),
                        )
                        candles.append(candle)
                    except (KeyError, ValueError) as e:
                        logger.warning(f"Skip invalid row: {e}")
                        continue
                
                logger.info(f"Successfully fetched {len(candles)} candles for {code}")
                return candles
                
            except Exception as e:
                logger.error(f"Fetch daily error (attempt {retry + 1}): {e}")
                if retry < max_retries - 1:
                    time.sleep(1)
                continue
        
        return []
    
    def _fetch_intraday(
        self,
        ak,
        code: str,
        period: str,
        start_date: datetime,
        end_date: datetime,
    ) -> List[RawCandle]:
        """业务模块说明。"""
        try:
            # 映射周期
            period_map = {
                "60min": "60",
                "30min": "30",
                "15min": "15",
            }
            ak_period = period_map.get(period, "60")
            
            # 使用 stock_zh_a_hist_min_em 获取分钟数据
            df = ak.stock_zh_a_hist_min_em(
                symbol=code,
                period=ak_period,
                adjust="qfq",
            )
            
            if df is None or df.empty:
                return []
            
            candles = []
            for _, row in df.iterrows():
                try:
                    ts = row["时间"]
                    if isinstance(ts, str):
                        ts = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                    
                    # 过滤日期范围
                    if ts < start_date or ts > end_date:
                        continue
                    
                    candle = RawCandle(
                        timestamp=ts,
                        open=float(row["开盘"]),
                        high=float(row["最高"]),
                        low=float(row["最低"]),
                        close=float(row["收盘"]),
                        volume=float(row["成交量"]),
                    )
                    candles.append(candle)
                except (KeyError, ValueError) as e:
                    logger.warning(f"Skip invalid row: {e}")
                    continue
            
            return candles
            
        except Exception as e:
            logger.error(f"Fetch intraday error: {e}")
            return []
