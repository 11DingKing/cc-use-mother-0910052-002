"""业务模块说明。"""

from typing import Dict, Any, List
from datetime import datetime

from app.backtest.engine import BacktestResult, Trade


class BacktestReportGenerator:
    """业务模块说明。"""
    
    def generate(self, result: BacktestResult) -> Dict[str, Any]:
        """业务模块说明。"""
        return {
            "summary": self._generate_summary(result),
            "performance": self._generate_performance(result),
            "trades": self._generate_trades_summary(result),
            "equity_curve": result.equity_curve,
        }
    
    def _generate_summary(self, result: BacktestResult) -> Dict[str, Any]:
        """业务模块说明。"""
        config = result.config
        return {
            "stock_code": config.stock_code,
            "period": config.period,
            "start_date": config.start_date.isoformat(),
            "end_date": config.end_date.isoformat(),
            "initial_capital": config.initial_capital,
            "final_capital": result.final_capital,
            "total_return": f"{result.total_return * 100:.2f}%",
            "annual_return": f"{result.annual_return * 100:.2f}%",
        }
    
    def _generate_performance(self, result: BacktestResult) -> Dict[str, Any]:
        """业务模块说明。"""
        return {
            "total_return": result.total_return,
            "annual_return": result.annual_return,
            "max_drawdown": result.max_drawdown,
            "sharpe_ratio": result.sharpe_ratio,
            "win_rate": result.win_rate,
            "profit_loss_ratio": result.profit_loss_ratio,
            "total_trades": result.total_trades,
            "winning_trades": result.winning_trades,
            "losing_trades": result.losing_trades,
        }
    
    def _generate_trades_summary(self, result: BacktestResult) -> List[Dict[str, Any]]:
        """业务模块说明。"""
        return [
            {
                "entry_time": t.entry_time.isoformat(),
                "entry_price": t.entry_price,
                "entry_signal": t.entry_signal.value if t.entry_signal else None,
                "exit_time": t.exit_time.isoformat() if t.exit_time else None,
                "exit_price": t.exit_price,
                "exit_signal": t.exit_signal.value if t.exit_signal else None,
                "shares": t.shares,
                "profit": t.profit,
                "profit_pct": f"{t.profit_pct * 100:.2f}%",
                "is_closed": t.is_closed,
            }
            for t in result.trades
        ]


def format_report_text(result: BacktestResult) -> str:
    """业务模块说明。"""
    config = result.config
    
    lines = [
        "=" * 60,
        "回测报告",
        "=" * 60,
        "",
        "【基本信息】",
        f"股票代码: {config.stock_code}",
        f"K线周期: {config.period}",
        f"回测区间: {config.start_date.strftime('%Y-%m-%d')} ~ {config.end_date.strftime('%Y-%m-%d')}",
        f"初始资金: {config.initial_capital:,.2f}",
        "",
        "【收益指标】",
        f"最终资金: {result.final_capital:,.2f}",
        f"总收益率: {result.total_return * 100:.2f}%",
        f"年化收益: {result.annual_return * 100:.2f}%",
        f"最大回撤: {result.max_drawdown * 100:.2f}%",
        f"夏普比率: {result.sharpe_ratio:.2f}",
        "",
        "【交易统计】",
        f"总交易次数: {result.total_trades}",
        f"盈利次数: {result.winning_trades}",
        f"亏损次数: {result.losing_trades}",
        f"胜率: {result.win_rate * 100:.2f}%",
        f"盈亏比: {result.profit_loss_ratio:.2f}",
        "",
        "=" * 60,
    ]
    
    return "\n".join(lines)
