"""业务模块说明。"""

from typing import Optional, List
from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.services.watchlist_service import WatchlistService

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])
watchlist_service = WatchlistService()


class AddStockRequest(BaseModel):
    """业务模块说明。"""
    stock_code: str
    stock_name: Optional[str] = None
    group_name: Optional[str] = None
    notes: Optional[str] = None


class UpdateStockRequest(BaseModel):
    """业务模块说明。"""
    stock_name: Optional[str] = None
    group_name: Optional[str] = None
    notes: Optional[str] = None


class ReorderRequest(BaseModel):
    """业务模块说明。"""
    stock_codes: List[str]


@router.get("")
async def get_watchlist(
    group_name: Optional[str] = Query(default=None, description="分组名称"),
    order_by: str = Query(default="sort_order", description="排序字段"),
):
    """业务模块说明。"""
    items = watchlist_service.get_all(group_name, order_by)
    return {
        "count": len(items),
        "items": items,
    }


@router.post("")
async def add_stock(request: AddStockRequest):
    """业务模块说明。"""
    return watchlist_service.add_stock(
        request.stock_code,
        request.stock_name,
        request.group_name,
        request.notes,
    )


@router.get("/{code}")
async def get_stock(code: str):
    """业务模块说明。"""
    return watchlist_service.get_stock(code)


@router.put("/{code}")
async def update_stock(code: str, request: UpdateStockRequest):
    """业务模块说明。"""
    return watchlist_service.update_stock(
        code,
        request.stock_name,
        request.group_name,
        request.notes,
    )


@router.delete("/{code}")
async def remove_stock(code: str):
    """业务模块说明。"""
    success = watchlist_service.remove_stock(code)
    return {"success": success, "stock_code": code}


@router.post("/reorder")
async def reorder_watchlist(request: ReorderRequest):
    """业务模块说明。"""
    count = watchlist_service.reorder(request.stock_codes)
    return {"success": True, "updated_count": count}


@router.get("/groups/list")
async def get_groups():
    """业务模块说明。"""
    groups = watchlist_service.get_groups()
    return {"groups": groups}


@router.get("/signals/new")
async def get_new_signals():
    """业务模块说明。"""
    items = watchlist_service.get_with_new_signals()
    return {
        "count": len(items),
        "items": items,
    }


@router.post("/signals/clear")
async def clear_new_signals():
    """业务模块说明。"""
    count = watchlist_service.clear_new_signal_flags()
    return {"success": True, "cleared_count": count}
