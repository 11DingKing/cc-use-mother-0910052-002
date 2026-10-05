from datetime import datetime
from typing import List, Optional, Dict, Any
import logging
from app.config import db_session_scope
from app.mappers.stock_mapper import StockMapper
from app.data.fetcher import FetchResult
from app.data.akshare_fetcher import AKShareFetcher
from app.data.yahoo_fetcher import YahooFetcher
from app.chan.models import RawCandle
from app.utils.validators import validate_stock_code, validate_time_range, validate_period
from app.middleware.exception_handler import DataFetchException
logger = logging.getLogger(__name__)
class StockService:
    def __init__(self):
        self.fetchers = self._init_fetchers()
    def _init_fetchers(self):
        fetchers = {}
        try:
            akshare = AKShareFetcher()
            if akshare.is_available():
                fetchers['akshare'] = akshare
        except Exception as e:
            logger.warning(f'AKShare not available: {e}')
        try:
            yahoo = YahooFetcher()
            if yahoo.is_available():
                fetchers['yahoo'] = yahoo
        except Exception as e:
            logger.warning(f'Yahoo Finance not available: {e}')
        return fetchers
    def get_candles(self, stock_code, period, start_date=None, end_date=None, use_cache=True):
        stock_code = validate_stock_code(stock_code)
        period = validate_period(period)
        start_date, end_date = validate_time_range(start_date, end_date)
        if use_cache:
            cached = self._get_from_cache(stock_code, period, start_date, end_date)
            if cached:
                return cached
        result = self._fetch_from_source(stock_code, period, start_date, end_date)
        if not result.success:
            raise DataFetchException(message=result.error_message or 'Failed', stock_code=stock_code, source=result.source)
        if result.candles:
            self._save_to_cache(result.candles, stock_code, period)
        return result.candles
    def _get_from_cache(self, stock_code, period, start_date, end_date):
        try:
            with db_session_scope() as session:
                mapper = StockMapper(session)
                candles = mapper.get_candles(stock_code, period, start_date, end_date)
                if not candles:
                    return None
                return mapper.to_raw_candles(candles)
        except Exception as e:
            logger.warning(f'Cache read error: {e}')
            return None
    def _save_to_cache(self, candles, stock_code, period):
        try:
            with db_session_scope() as session:
                mapper = StockMapper(session)
                entities = mapper.from_raw_candles(candles, stock_code, period)
                mapper.upsert_candles(entities)
        except Exception as e:
            logger.warning(f'Cache write error: {e}')
    def _fetch_from_source(self, stock_code, period, start_date, end_date):
        sources = ['akshare', 'yahoo'] if stock_code[0].isdigit() else ['yahoo', 'akshare']
        last_error = None
        for source_name in sources:
            fetcher = self.fetchers.get(source_name)
            if not fetcher:
                continue
            try:
                result = fetcher.fetch_candles(stock_code, period, start_date, end_date)
                if result.success and result.candles:
                    return result
                last_error = result.error_message
            except Exception as e:
                last_error = str(e)
        return FetchResult([], stock_code, period, start_date, end_date, 'none', False, last_error)
    def fetch_and_update(self, stock_code, period, start_date=None, end_date=None):
        stock_code = validate_stock_code(stock_code)
        period = validate_period(period)
        start_date, end_date = validate_time_range(start_date, end_date)
        result = self._fetch_from_source(stock_code, period, start_date, end_date)
        if result.success and result.candles:
            self._save_to_cache(result.candles, stock_code, period)
        return {'stock_code': stock_code, 'period': period, 'start_date': start_date.isoformat(), 'end_date': end_date.isoformat(), 'success': result.success, 'count': len(result.candles), 'source': result.source, 'error': result.error_message}
