"""业务模块说明。"""

from app.backtest.engine import (
    BacktestEngine,
    BacktestConfig,
    BacktestResult,
    Trade,
)
from app.backtest.report import (
    BacktestReportGenerator,
    format_report_text,
)

__all__ = [
    "BacktestEngine",
    "BacktestConfig",
    "BacktestResult",
    "Trade",
    "BacktestReportGenerator",
    "format_report_text",
]
