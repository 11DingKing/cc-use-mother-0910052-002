"""业务模块说明。"""

import json
from datetime import datetime
from typing import Optional, Dict, Any
import logging

from app.config import db_session_scope
from app.entities.backtest import BacktestResult as BacktestResultEntity
from app.backtest.engine import BacktestEngine, BacktestConfig, BacktestResult
from app.backtest.report import BacktestReportGenerator
from app.services.stock_service import StockService
from app.services.analysis_service import AnalysisService
from app.utils.validators import validate_stock_code, validate_time_range, validate_period
from app.middleware.exception_handler import NotFoundException, AnalysisException

logger = logging.getLogger(__name__)


class BacktestService:
    """业务模块说明。"""
    
    def __init__(self):
        self.stock_service = StockService()
        self.analysis_service = AnalysisService()
        self.engine = BacktestEngine()
        self.report_generator = BacktestReportGenerator()
    
    def run_backtest(
        self,
        stock_code: str,
        period: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        initial_capital: float = 100000.0,
        position_size: float = 1.0,
    ) -> Dict[str, Any]:
        """业务模块说明。"""
        stock_code = validate_stock_code(stock_code)
        period = validate_period(period)
        start_date, end_date = validate_time_range(start_date, end_date)
        
        # 创建回测配置
        config = BacktestConfig(
            stock_code=stock_code,
            period=period,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            position_size=position_size,
        )
        
        try:
            # 获取K线数据
            candles = self.stock_service.get_candles(
                stock_code, period, start_date, end_date
            )
            
            if not candles:
                raise AnalysisException(
                    message="No candle data available for backtest",
                    stock_code=stock_code,
                    period=period,
                )
            
            # 执行分析获取信号（使用完整数据范围以获得更多信号）
            self.analysis_service.run_analysis(stock_code, period, None, None)
            
            # 获取信号
            with db_session_scope() as session:
                from app.mappers.analysis_mapper import AnalysisMapper
                mapper = AnalysisMapper(session)
                analysis_result = mapper.get_latest(stock_code, period)
                
                if not analysis_result:
                    raise AnalysisException(
                        message="No analysis result available",
                        stock_code=stock_code,
                        period=period,
                    )
                
                signals = mapper.load_signals(analysis_result)
            
            # 执行回测
            result = self.engine.run(config, candles, signals)
            
            # 保存结果
            result_id = self._save_result(result)
            
            # 生成报告
            report = self.report_generator.generate(result)
            report["id"] = result_id
            
            return report
            
        except AnalysisException:
            raise
        except Exception as e:
            logger.error(f"Backtest error: {e}", exc_info=True)
            raise AnalysisException(
                message=f"Backtest failed: {str(e)}",
                stock_code=stock_code,
                period=period,
            )
    
    def _save_result(self, result: BacktestResult) -> int:
        """业务模块说明。"""
        try:
            with db_session_scope() as session:
                entity = BacktestResultEntity(
                    stock_code=result.config.stock_code,
                    period=result.config.period,
                    start_date=result.config.start_date,
                    end_date=result.config.end_date,
                    initial_capital=result.config.initial_capital,
                    final_capital=result.final_capital,
                    total_return=result.total_return,
                    annual_return=result.annual_return,
                    max_drawdown=result.max_drawdown,
                    win_rate=result.win_rate,
                    profit_loss_ratio=result.profit_loss_ratio,
                    sharpe_ratio=result.sharpe_ratio,
                    total_trades=result.total_trades,
                    winning_trades=result.winning_trades,
                    losing_trades=result.losing_trades,
                    trades_json=json.dumps([
                        {
                            "entry_time": t.entry_time.isoformat(),
                            "entry_price": t.entry_price,
                            "entry_signal": t.entry_signal.value if t.entry_signal else None,
                            "exit_time": t.exit_time.isoformat() if t.exit_time else None,
                            "exit_price": t.exit_price,
                            "exit_signal": t.exit_signal.value if t.exit_signal else None,
                            "shares": t.shares,
                            "profit": t.profit,
                            "profit_pct": t.profit_pct,
                        }
                        for t in result.trades
                    ]),
                    equity_curve_json=json.dumps(result.equity_curve),
                    status="completed",
                    completed_at=datetime.utcnow(),
                )
                session.add(entity)
                session.flush()
                return entity.id
        except Exception as e:
            logger.warning(f"Save backtest result error: {e}")
            return 0
    
    def get_result(self, result_id: int) -> Dict[str, Any]:
        """业务模块说明。"""
        with db_session_scope() as session:
            entity = session.query(BacktestResultEntity).filter(
                BacktestResultEntity.id == result_id
            ).first()
            
            if not entity:
                raise NotFoundException(
                    message="Backtest result not found",
                    resource_type="BacktestResult",
                    resource_id=str(result_id),
                )
            
            return {
                "id": entity.id,
                "summary": {
                    "stock_code": entity.stock_code,
                    "period": entity.period,
                    "start_date": entity.start_date.isoformat(),
                    "end_date": entity.end_date.isoformat(),
                    "initial_capital": entity.initial_capital,
                    "final_capital": entity.final_capital,
                },
                "performance": {
                    "total_return": entity.total_return,
                    "annual_return": entity.annual_return,
                    "max_drawdown": entity.max_drawdown,
                    "sharpe_ratio": entity.sharpe_ratio,
                    "win_rate": entity.win_rate,
                    "profit_loss_ratio": entity.profit_loss_ratio,
                    "total_trades": entity.total_trades,
                    "winning_trades": entity.winning_trades,
                    "losing_trades": entity.losing_trades,
                },
                "trades": json.loads(entity.trades_json) if entity.trades_json else [],
                "equity_curve": json.loads(entity.equity_curve_json) if entity.equity_curve_json else [],
                "status": entity.status,
                "created_at": entity.created_at.isoformat(),
                "completed_at": entity.completed_at.isoformat() if entity.completed_at else None,
            }
    
    def list_results(
        self,
        stock_code: Optional[str] = None,
        limit: int = 20,
    ) -> list:
        """业务模块说明。"""
        with db_session_scope() as session:
            query = session.query(BacktestResultEntity)
            
            if stock_code:
                stock_code = validate_stock_code(stock_code)
                query = query.filter(BacktestResultEntity.stock_code == stock_code)
            
            results = query.order_by(
                BacktestResultEntity.created_at.desc()
            ).limit(limit).all()
            
            return [
                {
                    "id": r.id,
                    "stock_code": r.stock_code,
                    "period": r.period,
                    "total_return": r.total_return,
                    "win_rate": r.win_rate,
                    "status": r.status,
                    "created_at": r.created_at.isoformat(),
                }
                for r in results
            ]
