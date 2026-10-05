"""业务模块说明。"""

from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

from app.entities.watchlist import WatchlistItem


class WatchlistMapper:
    """业务模块说明。"""
    
    def __init__(self, session: Session):
        self.session = session
    
    def create(self, item: WatchlistItem) -> WatchlistItem:
        """业务模块说明。"""
        self.session.add(item)
        self.session.flush()
        return item
    
    def get_by_id(self, item_id: int) -> Optional[WatchlistItem]:
        """业务模块说明。"""
        return self.session.query(WatchlistItem).filter(
            WatchlistItem.id == item_id
        ).first()
    
    def get_by_stock_code(self, stock_code: str) -> Optional[WatchlistItem]:
        """业务模块说明。"""
        return self.session.query(WatchlistItem).filter(
            WatchlistItem.stock_code == stock_code
        ).first()
    
    def get_all(
        self,
        group_name: Optional[str] = None,
        order_by: str = "sort_order",
    ) -> List[WatchlistItem]:
        """业务模块说明。"""
        query = self.session.query(WatchlistItem)
        
        if group_name:
            query = query.filter(WatchlistItem.group_name == group_name)
        
        if order_by == "signal_strength":
            query = query.order_by(desc(WatchlistItem.signal_strength))
        elif order_by == "added_at":
            query = query.order_by(desc(WatchlistItem.added_at))
        else:
            query = query.order_by(WatchlistItem.sort_order)
        
        return query.all()
    
    def update(self, item: WatchlistItem) -> WatchlistItem:
        """业务模块说明。"""
        self.session.merge(item)
        self.session.flush()
        return item
    
    def delete(self, item_id: int) -> bool:
        """业务模块说明。"""
        item = self.get_by_id(item_id)
        if item:
            self.session.delete(item)
            self.session.flush()
            return True
        return False
    
    def delete_by_stock_code(self, stock_code: str) -> bool:
        """业务模块说明。"""
        item = self.get_by_stock_code(stock_code)
        if item:
            self.session.delete(item)
            self.session.flush()
            return True
        return False
    
    def exists(self, stock_code: str) -> bool:
        """业务模块说明。"""
        return self.session.query(WatchlistItem).filter(
            WatchlistItem.stock_code == stock_code
        ).count() > 0
    
    def add_stock(
        self,
        stock_code: str,
        stock_name: Optional[str] = None,
        group_name: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> WatchlistItem:
        """业务模块说明。"""
        existing = self.get_by_stock_code(stock_code)
        if existing:
            return existing
        
        # 获取当前最大排序号
        max_order = self.session.query(WatchlistItem).count()
        
        item = WatchlistItem(
            stock_code=stock_code,
            stock_name=stock_name,
            group_name=group_name,
            notes=notes,
            sort_order=max_order,
        )
        return self.create(item)
    
    def update_signal_info(
        self,
        stock_code: str,
        signal_type: Optional[str] = None,
        signal_time: Optional[datetime] = None,
        signal_price: Optional[float] = None,
        signal_strength: Optional[float] = None,
        is_new_signal: bool = False,
    ) -> Optional[WatchlistItem]:
        """业务模块说明。"""
        item = self.get_by_stock_code(stock_code)
        if not item:
            return None
        
        if signal_type is not None:
            item.latest_signal_type = signal_type
        if signal_time is not None:
            item.latest_signal_time = signal_time
        if signal_price is not None:
            item.latest_signal_price = signal_price
        if signal_strength is not None:
            item.signal_strength = signal_strength
        item.is_new_signal = 1 if is_new_signal else 0
        
        self.session.flush()
        return item
    
    def update_price_info(
        self,
        stock_code: str,
        current_price: float,
        price_change_pct: Optional[float] = None,
    ) -> Optional[WatchlistItem]:
        """业务模块说明。"""
        item = self.get_by_stock_code(stock_code)
        if not item:
            return None
        
        item.current_price = current_price
        if price_change_pct is not None:
            item.price_change_pct = price_change_pct
        
        self.session.flush()
        return item
    
    def clear_new_signal_flags(self) -> int:
        """业务模块说明。"""
        count = self.session.query(WatchlistItem).filter(
            WatchlistItem.is_new_signal == 1
        ).update({"is_new_signal": 0}, synchronize_session=False)
        self.session.flush()
        return count
    
    def get_with_new_signals(self) -> List[WatchlistItem]:
        """业务模块说明。"""
        return self.session.query(WatchlistItem).filter(
            WatchlistItem.is_new_signal == 1
        ).order_by(desc(WatchlistItem.signal_strength)).all()
    
    def reorder(self, stock_codes: List[str]) -> int:
        """业务模块说明。"""
        count = 0
        for i, code in enumerate(stock_codes):
            item = self.get_by_stock_code(code)
            if item:
                item.sort_order = i
                count += 1
        
        self.session.flush()
        return count
    
    def count(self, group_name: Optional[str] = None) -> int:
        """业务模块说明。"""
        query = self.session.query(WatchlistItem)
        if group_name:
            query = query.filter(WatchlistItem.group_name == group_name)
        return query.count()
    
    def get_groups(self) -> List[str]:
        """业务模块说明。"""
        results = self.session.query(WatchlistItem.group_name).distinct().all()
        return [r[0] for r in results if r[0] is not None]
