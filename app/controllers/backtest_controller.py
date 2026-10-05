"""业务模块说明。"""

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.services.backtest_service import BacktestService

router = APIRouter(prefix="/api/backtest", tags=["backtest"])
backtest_service = BacktestService()


class RunBacktestRequest(BaseModel):
    """业务模块说明。"""
    stock_code: str
    period: str = "daily"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    initial_capital: float = 100000.0
    position_size: float = 1.0


@router.post("/run")
async def run_backtest(request: RunBacktestRequest):
    """业务模块说明。"""
    start = datetime.strptime(request.start_date, "%Y-%m-%d") if request.start_date else None
    end = datetime.strptime(request.end_date, "%Y-%m-%d") if request.end_date else None
    
    return backtest_service.run_backtest(
        request.stock_code,
        request.period,
        start,
        end,
        request.initial_capital,
        request.position_size,
    )


@router.get("/{result_id}/report")
async def get_report(result_id: int):
    """业务模块说明。"""
    return backtest_service.get_result(result_id)


@router.get("/list")
async def list_results(
    stock_code: Optional[str] = Query(default=None, description="股票代码"),
    limit: int = Query(default=20, description="返回数量"),
):
    """业务模块说明。"""
    results = backtest_service.list_results(stock_code, limit)
    return {
        "count": len(results),
        "results": results,
    }
