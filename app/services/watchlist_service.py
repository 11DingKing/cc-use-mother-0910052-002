"""业务模块说明。"""

from datetime import datetime
from typing import List, Optional, Dict, Any
import logging

from app.config import db_session_scope
from app.mappers.watchlist_mapper import WatchlistMapper
from app.entities.watchlist import WatchlistItem
from app.utils.validators import validate_stock_code
from app.middleware.exception_handler import NotFoundException, ValidationException

logger = logging.getLogger(__name__)


class WatchlistService:
    """业务模块说明。"""
    
    def add_stock(
        self,
        stock_code: str,
        stock_name: Optional[str] = None,
        group_name: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """业务模块说明。"""
        stock_code = validate_stock_code(stock_code)
        
        with db_session_scope() as session:
            mapper = WatchlistMapper(session)
            
            # 检查是否已存在
            if mapper.exists(stock_code):
                existing = mapper.get_by_stock_code(stock_code)
                return existing.to_dict()
            
            item = mapper.add_stock(stock_code, stock_name, group_name, notes)
            return item.to_dict()
    
    def remove_stock(self, stock_code: str) -> bool:
        """业务模块说明。"""
        stock_code = validate_stock_code(stock_code)
        
        with db_session_scope() as session:
            mapper = WatchlistMapper(session)
            
            if not mapper.exists(stock_code):
                raise NotFoundException(
                    message="Stock not in watchlist",
                    resource_type="WatchlistItem",
                    resource_id=stock_code,
                )
            
            return mapper.delete_by_stock_code(stock_code)
    
    def get_all(
        self,
        group_name: Optional[str] = None,
        order_by: str = "sort_order",
    ) -> List[Dict[str, Any]]:
        """业务模块说明。"""
        with db_session_scope() as session:
            mapper = WatchlistMapper(session)
            items = mapper.get_all(group_name, order_by)
            return [item.to_dict() for item in items]
    
    def get_stock(self, stock_code: str) -> Dict[str, Any]:
        """业务模块说明。"""
        stock_code = validate_stock_code(stock_code)
        
        with db_session_scope() as session:
            mapper = WatchlistMapper(session)
            item = mapper.get_by_stock_code(stock_code)
            
            if not item:
                raise NotFoundException(
                    message="Stock not in watchlist",
                    resource_type="WatchlistItem",
                    resource_id=stock_code,
                )
            
            return item.to_dict()
    
    def update_stock(
        self,
        stock_code: str,
        stock_name: Optional[str] = None,
        group_name: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """业务模块说明。"""
        stock_code = validate_stock_code(stock_code)
        
        with db_session_scope() as session:
            mapper = WatchlistMapper(session)
            item = mapper.get_by_stock_code(stock_code)
            
            if not item:
                raise NotFoundException(
                    message="Stock not in watchlist",
                    resource_type="WatchlistItem",
                    resource_id=stock_code,
                )
            
            if stock_name is not None:
                item.stock_name = stock_name
            if group_name is not None:
                item.group_name = group_name
            if notes is not None:
                item.notes = notes
            
            mapper.update(item)
            return item.to_dict()
    
    def update_signal_info(
        self,
        stock_code: str,
        signal_type: Optional[str] = None,
        signal_time: Optional[datetime] = None,
        signal_price: Optional[float] = None,
        signal_strength: Optional[float] = None,
        is_new_signal: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """业务模块说明。"""
        stock_code = validate_stock_code(stock_code)
        
        with db_session_scope() as session:
            mapper = WatchlistMapper(session)
            item = mapper.update_signal_info(
                stock_code, signal_type, signal_time,
                signal_price, signal_strength, is_new_signal
            )
            return item.to_dict() if item else None
    
    def reorder(self, stock_codes: List[str]) -> int:
        """业务模块说明。"""
        if not stock_codes:
            raise ValidationException(
                message="Stock codes list cannot be empty",
                field="stock_codes",
            )
        
        # 验证所有代码
        validated_codes = [validate_stock_code(code) for code in stock_codes]
        
        with db_session_scope() as session:
            mapper = WatchlistMapper(session)
            return mapper.reorder(validated_codes)
    
    def get_with_new_signals(self) -> List[Dict[str, Any]]:
        """业务模块说明。"""
        with db_session_scope() as session:
            mapper = WatchlistMapper(session)
            items = mapper.get_with_new_signals()
            return [item.to_dict() for item in items]
    
    def clear_new_signal_flags(self) -> int:
        """业务模块说明。"""
        with db_session_scope() as session:
            mapper = WatchlistMapper(session)
            return mapper.clear_new_signal_flags()
    
    def get_groups(self) -> List[str]:
        """业务模块说明。"""
        with db_session_scope() as session:
            mapper = WatchlistMapper(session)
            return mapper.get_groups()
    
    def count(self, group_name: Optional[str] = None) -> int:
        """业务模块说明。"""
        with db_session_scope() as session:
            mapper = WatchlistMapper(session)
            return mapper.count(group_name)
    
    def exists(self, stock_code: str) -> bool:
        """业务模块说明。"""
        stock_code = validate_stock_code(stock_code)
        
        with db_session_scope() as session:
            mapper = WatchlistMapper(session)
            return mapper.exists(stock_code)
