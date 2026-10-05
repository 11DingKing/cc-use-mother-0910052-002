"""业务模块说明。"""

import pytest
from datetime import datetime
from typing import List

from hypothesis import given, strategies as st, settings, assume

from app.config import init_database, get_engine
from app.entities.watchlist import Base as WatchlistBase
from app.services.watchlist_service import WatchlistService
from app.middleware.exception_handler import NotFoundException


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def setup_database():
    """业务模块说明。"""
    engine = get_engine()
    WatchlistBase.metadata.drop_all(bind=engine)
    WatchlistBase.metadata.create_all(bind=engine)
    yield
    WatchlistBase.metadata.drop_all(bind=engine)


@pytest.fixture
def service():
    """业务模块说明。"""
    return WatchlistService()


# ---------------------------------------------------------------------------
# Tests: Basic CRUD Operations
# ---------------------------------------------------------------------------

class TestWatchlistCRUD:
    """业务模块说明。"""
    
    def test_add_stock(self, service):
        """业务模块说明。"""
        result = service.add_stock("000001", "平安银行", "银行")
        
        assert result["stock_code"] == "sz000001"
        assert result["stock_name"] == "平安银行"
        assert result["group_name"] == "银行"
    
    def test_add_duplicate_stock(self, service):
        """业务模块说明。"""
        service.add_stock("000001", "平安银行")
        result = service.add_stock("000001", "新名称")
        
        # Should return existing, not create new
        assert result["stock_name"] == "平安银行"
    
    def test_remove_stock(self, service):
        """业务模块说明。"""
        service.add_stock("000001")
        
        success = service.remove_stock("000001")
        assert success is True
        
        # Should not exist anymore
        assert service.exists("000001") is False
    
    def test_remove_nonexistent_stock(self, service):
        """业务模块说明。"""
        with pytest.raises(NotFoundException):
            service.remove_stock("999999")
    
    def test_get_all(self, service):
        """业务模块说明。"""
        service.add_stock("000001", "平安银行")
        service.add_stock("600000", "浦发银行")
        
        items = service.get_all()
        
        assert len(items) == 2
    
    def test_get_stock(self, service):
        """业务模块说明。"""
        service.add_stock("000001", "平安银行", notes="测试备注")
        
        result = service.get_stock("000001")
        
        assert result["stock_code"] == "sz000001"
        assert result["stock_name"] == "平安银行"
        assert result["notes"] == "测试备注"
    
    def test_update_stock(self, service):
        """业务模块说明。"""
        service.add_stock("000001", "平安银行")
        
        result = service.update_stock("000001", stock_name="新名称", notes="新备注")
        
        assert result["stock_name"] == "新名称"
        assert result["notes"] == "新备注"
    
    def test_exists(self, service):
        """业务模块说明。"""
        assert service.exists("000001") is False
        
        service.add_stock("000001")
        
        assert service.exists("000001") is True


class TestWatchlistOrdering:
    """业务模块说明。"""
    
    def test_reorder(self, service):
        """业务模块说明。"""
        service.add_stock("000001")
        service.add_stock("600000")
        service.add_stock("300001")
        
        # Reorder
        service.reorder(["sz300001", "sh600000", "sz000001"])
        
        items = service.get_all(order_by="sort_order")
        codes = [item["stock_code"] for item in items]
        
        assert codes == ["sz300001", "sh600000", "sz000001"]
    
    def test_order_by_signal_strength(self, service):
        """业务模块说明。"""
        service.add_stock("000001")
        service.add_stock("600000")
        service.add_stock("300001")
        
        # Update signal strengths
        service.update_signal_info("000001", signal_strength=0.3)
        service.update_signal_info("600000", signal_strength=0.9)
        service.update_signal_info("300001", signal_strength=0.6)
        
        items = service.get_all(order_by="signal_strength")
        strengths = [item["signal_strength"] for item in items]
        
        # Should be descending
        assert strengths == sorted(strengths, reverse=True)


class TestWatchlistGroups:
    """业务模块说明。"""
    
    def test_get_groups(self, service):
        """业务模块说明。"""
        service.add_stock("000001", group_name="银行")
        service.add_stock("600000", group_name="银行")
        service.add_stock("300001", group_name="科技")
        
        groups = service.get_groups()
        
        assert "银行" in groups
        assert "科技" in groups
    
    def test_filter_by_group(self, service):
        """业务模块说明。"""
        service.add_stock("000001", group_name="银行")
        service.add_stock("600000", group_name="银行")
        service.add_stock("300001", group_name="科技")
        
        bank_items = service.get_all(group_name="银行")
        
        assert len(bank_items) == 2
        assert all(item["group_name"] == "银行" for item in bank_items)


# ---------------------------------------------------------------------------
# Property-Based Tests (Hypothesis)
# Property 16: 自选股增删一致性
# Property 17: 自选股排序正确性
# Validates: Requirements 9.1, 9.2, 9.4
# ---------------------------------------------------------------------------

@st.composite
def valid_stock_code_strategy(draw):
    """业务模块说明。"""
    prefix = draw(st.sampled_from(["000", "600", "300", "002"]))
    suffix = draw(st.text(alphabet="0123456789", min_size=3, max_size=3))
    return prefix + suffix


@st.composite
def stock_info_strategy(draw):
    """业务模块说明。"""
    code = draw(valid_stock_code_strategy())
    name = draw(st.text(min_size=2, max_size=10, alphabet="测试股票银行科技"))
    group = draw(st.sampled_from([None, "银行", "科技", "消费"]))
    notes = draw(st.text(min_size=0, max_size=50) | st.none())
    return {"code": code, "name": name, "group": group, "notes": notes}


class TestPropertyWatchlistConsistency:
    """业务模块说明。"""
    
    @given(valid_stock_code_strategy())
    @settings(max_examples=20, deadline=None)
    def test_add_then_exists(self, code: str):
        """业务模块说明。"""
        # Fresh database for each test
        engine = get_engine()
        WatchlistBase.metadata.drop_all(bind=engine)
        WatchlistBase.metadata.create_all(bind=engine)
        
        service = WatchlistService()
        
        # Add stock
        service.add_stock(code)
        
        # Should exist
        assert service.exists(code), f"Stock {code} should exist after adding"
    
    @given(valid_stock_code_strategy())
    @settings(max_examples=20, deadline=None)
    def test_add_then_delete_then_not_exists(self, code: str):
        """业务模块说明。"""
        engine = get_engine()
        WatchlistBase.metadata.drop_all(bind=engine)
        WatchlistBase.metadata.create_all(bind=engine)
        
        service = WatchlistService()
        
        # Add then delete
        service.add_stock(code)
        service.remove_stock(code)
        
        # Should not exist
        assert not service.exists(code), f"Stock {code} should not exist after deletion"
    
    @given(stock_info_strategy())
    @settings(max_examples=20, deadline=None)
    def test_add_preserves_info(self, info: dict):
        """业务模块说明。"""
        engine = get_engine()
        WatchlistBase.metadata.drop_all(bind=engine)
        WatchlistBase.metadata.create_all(bind=engine)
        
        service = WatchlistService()
        
        # Add with info
        result = service.add_stock(
            info["code"],
            info["name"] if info["name"] else None,
            info["group"],
            info["notes"] if info["notes"] else None,
        )
        
        # Verify info preserved
        if info["name"]:
            assert result["stock_name"] == info["name"]
        if info["group"]:
            assert result["group_name"] == info["group"]
        if info["notes"]:
            assert result["notes"] == info["notes"]


class TestPropertyWatchlistOrdering:
    """业务模块说明。"""
    
    @given(st.lists(
        st.tuples(
            valid_stock_code_strategy(),
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        ),
        min_size=2,
        max_size=5,
        unique_by=lambda x: x[0][:3],  # Unique by first 3 digits to avoid duplicates
    ))
    @settings(max_examples=20, deadline=None)
    def test_order_by_signal_strength_is_descending(self, stocks: List):
        """业务模块说明。"""
        engine = get_engine()
        WatchlistBase.metadata.drop_all(bind=engine)
        WatchlistBase.metadata.create_all(bind=engine)
        
        service = WatchlistService()
        
        # Add stocks with signal strengths
        for code, strength in stocks:
            service.add_stock(code)
            service.update_signal_info(code, signal_strength=strength)
        
        # Get ordered by signal strength
        items = service.get_all(order_by="signal_strength")
        
        # Verify descending order
        strengths = [item["signal_strength"] for item in items if item["signal_strength"] is not None]
        
        for i in range(1, len(strengths)):
            assert strengths[i-1] >= strengths[i], (
                f"Signal strengths not in descending order: {strengths}"
            )
    
    @given(st.lists(
        valid_stock_code_strategy(),
        min_size=2,
        max_size=5,
        unique_by=lambda x: x[:3],
    ))
    @settings(max_examples=20, deadline=None)
    def test_reorder_preserves_all_items(self, codes: List[str]):
        """业务模块说明。"""
        engine = get_engine()
        WatchlistBase.metadata.drop_all(bind=engine)
        WatchlistBase.metadata.create_all(bind=engine)
        
        service = WatchlistService()
        
        # Add stocks
        added_codes = []
        for code in codes:
            result = service.add_stock(code)
            added_codes.append(result["stock_code"])
        
        # Reorder (reverse)
        reversed_codes = list(reversed(added_codes))
        service.reorder(reversed_codes)
        
        # All items should still exist
        items = service.get_all()
        assert len(items) == len(codes), "Reorder should not change item count"
        
        # Order should match
        item_codes = [item["stock_code"] for item in items]
        assert item_codes == reversed_codes, "Order should match reorder request"
