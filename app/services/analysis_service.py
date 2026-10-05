"""业务模块说明。"""

from datetime import datetime
from typing import List, Optional, Dict, Any
import logging

from app.config import db_session_scope
from app.mappers.analysis_mapper import AnalysisMapper
from app.services.stock_service import StockService
from app.chan.kline_processor import KLineProcessor
from app.chan.fractal_detector import FractalDetector
from app.chan.bi_detector import BiDetector
from app.chan.duan_detector import DuanDetector
from app.chan.zhongshu_detector import ZhongshuDetector
from app.chan.signal_detector import SignalDetector
from app.chan.multi_level import MultiLevelLinkage, CombinedSignal
from app.chan.models import Fractal, Bi, Duan, Zhongshu, Signal
from app.utils.validators import validate_stock_code, validate_time_range, validate_period
from app.middleware.exception_handler import AnalysisException, NotFoundException

logger = logging.getLogger(__name__)


class AnalysisService:
    """业务模块说明。"""
    stock_service = StockService()
    
    def __init__(self):
        self.stock_service = self.__class__.stock_service
        self.kline_processor = KLineProcessor()
        self.fractal_detector = FractalDetector()
        self.bi_detector = BiDetector()
        self.duan_detector = DuanDetector()
        self.zhongshu_detector = ZhongshuDetector()
        self.multi_level_linkage = MultiLevelLinkage()
    
    def run_analysis(
        self,
        stock_code: str,
        period: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """业务模块说明。"""
        stock_code = validate_stock_code(stock_code)
        period = validate_period(period)
        start_date, end_date = validate_time_range(start_date, end_date)
        
        try:
            # 获取K线数据
            candles = self.stock_service.get_candles(
                stock_code, period, start_date, end_date
            )
            
            if not candles:
                raise AnalysisException(
                    message="No candle data available",
                    stock_code=stock_code,
                    period=period,
                )
            
            # 清洗和合并K线
            cleaned, _ = self.kline_processor.clean(candles)
            merged = self.kline_processor.merge(cleaned)
            
            # 识别分型
            fractals = self.fractal_detector.detect(merged)
            
            # 识别笔
            bis = self.bi_detector.detect(fractals, merged)
            
            # 识别段
            duans = self.duan_detector.detect(bis)
            
            # 识别中枢
            zhongshus = self.zhongshu_detector.detect(bis)
            
            # 识别买卖点
            signal_detector = SignalDetector(stock_code, period)
            signals = signal_detector.detect_all(bis, duans, zhongshus)
            
            # 保存结果
            self._save_result(
                stock_code, period, start_date, end_date,
                fractals, bis, duans, zhongshus, signals
            )
            
            return {
                "stock_code": stock_code,
                "period": period,
                "candle_count": len(candles),
                "merged_count": len(merged),
                "fractal_count": len(fractals),
                "bi_count": len(bis),
                "duan_count": len(duans),
                "zhongshu_count": len(zhongshus),
                "signal_count": len(signals),
                "latest_signal": signals[-1].signal_type.value if signals else None,
            }
            
        except AnalysisException:
            raise
        except Exception as e:
            logger.error(f"Analysis error: {e}", exc_info=True)
            raise AnalysisException(
                message=f"Analysis failed: {str(e)}",
                stock_code=stock_code,
                period=period,
            )
    
    def _save_result(
        self,
        stock_code: str,
        period: str,
        start_date: datetime,
        end_date: datetime,
        fractals: List[Fractal],
        bis: List[Bi],
        duans: List[Duan],
        zhongshus: List[Zhongshu],
        signals: List[Signal],
    ) -> None:
        """业务模块说明。"""
        try:
            with db_session_scope() as session:
                mapper = AnalysisMapper(session)
                mapper.save_analysis(
                    stock_code, period, start_date, end_date,
                    fractals, bis, duans, zhongshus, signals
                )
        except Exception as e:
            logger.warning(f"Save result error: {e}")
    
    def get_result(
        self,
        stock_code: str,
        period: str,
    ) -> Dict[str, Any]:
        """业务模块说明。"""
        stock_code = validate_stock_code(stock_code)
        period = validate_period(period)
        
        with db_session_scope() as session:
            mapper = AnalysisMapper(session)
            result = mapper.get_latest(stock_code, period)
            
            if not result:
                raise NotFoundException(
                    message="Analysis result not found",
                    resource_type="AnalysisResult",
                    resource_id=f"{stock_code}:{period}",
                )
            
            return {
                "stock_code": result.stock_code,
                "period": result.period,
                "start_time": result.start_time.isoformat(),
                "end_time": result.end_time.isoformat(),
                "fractal_count": result.fractal_count,
                "bi_count": result.bi_count,
                "duan_count": result.duan_count,
                "zhongshu_count": result.zhongshu_count,
                "signal_count": result.signal_count,
                "latest_signal_type": result.latest_signal_type,
                "latest_signal_time": result.latest_signal_time.isoformat() if result.latest_signal_time else None,
                "latest_signal_price": result.latest_signal_price,
                "updated_at": result.updated_at.isoformat(),
            }
    
    def get_signals(
        self,
        stock_code: str,
        period: str,
    ) -> List[Dict[str, Any]]:
        """业务模块说明。"""
        stock_code = validate_stock_code(stock_code)
        period = validate_period(period)
        
        with db_session_scope() as session:
            mapper = AnalysisMapper(session)
            result = mapper.get_latest(stock_code, period)
            
            if not result:
                return []
            
            signals = mapper.load_signals(result)
            return [
                {
                    "signal_type": s.signal_type.value,
                    "timestamp": s.timestamp.isoformat(),
                    "price": s.price,
                    "strength": s.strength,
                    "level": s.level,
                }
                for s in signals
            ]
    
    def get_full_result(
        self,
        stock_code: str,
        period: str,
    ) -> Dict[str, Any]:
        """业务模块说明。"""
        stock_code = validate_stock_code(stock_code)
        period = validate_period(period)
        
        with db_session_scope() as session:
            mapper = AnalysisMapper(session)
            result = mapper.get_latest(stock_code, period)
            
            if not result:
                raise NotFoundException(
                    message="Analysis result not found",
                    resource_type="AnalysisResult",
                    resource_id=f"{stock_code}:{period}",
                )
            
            data = mapper.load_all(result)
            
            return {
                "stock_code": result.stock_code,
                "period": result.period,
                "fractals": [self._fractal_to_dict(f) for f in data["fractals"]],
                "bis": [self._bi_to_dict(b) for b in data["bis"]],
                "duans": [self._duan_to_dict(d) for d in data["duans"]],
                "zhongshus": [self._zhongshu_to_dict(z) for z in data["zhongshus"]],
                "signals": [self._signal_to_dict(s) for s in data["signals"]],
            }
    
    def _fractal_to_dict(self, f: Fractal) -> Dict[str, Any]:
        return {
            "type": f.type.value,
            "timestamp": f.timestamp.isoformat(),
            "price": f.price,
            "index": f.candle_index,
        }
    
    def _bi_to_dict(self, b: Bi) -> Dict[str, Any]:
        return {
            "direction": b.direction.value,
            "start_time": b.start_fractal.timestamp.isoformat(),
            "end_time": b.end_fractal.timestamp.isoformat(),
            "start_price": b.start_price,
            "end_price": b.end_price,
        }
    
    def _duan_to_dict(self, d: Duan) -> Dict[str, Any]:
        return {
            "direction": d.direction.value,
            "bi_count": len(d.bi_list),
            "start_time": d.bi_list[0].start_fractal.timestamp.isoformat() if d.bi_list else None,
            "end_time": d.bi_list[-1].end_fractal.timestamp.isoformat() if d.bi_list else None,
        }
    
    def _zhongshu_to_dict(self, z: Zhongshu) -> Dict[str, Any]:
        return {
            "high": z.high,
            "low": z.low,
            "bi_count": len(z.bi_list),
            "start_time": z.start_time.isoformat() if z.start_time else (
                z.bi_list[0].start_fractal.timestamp.isoformat() if z.bi_list else None
            ),
            "end_time": z.end_time.isoformat() if z.end_time else (
                z.bi_list[-1].end_fractal.timestamp.isoformat() if z.bi_list else None
            ),
        }
    
    def _signal_to_dict(self, s: Signal) -> Dict[str, Any]:
        return {
            "signal_type": s.signal_type.value,
            "timestamp": s.timestamp.isoformat(),
            "price": s.price,
            "strength": s.strength,
            "level": s.level,
        }
    
    def run_multi_level_analysis(
        self,
        stock_code: str,
        primary_period: str = "daily",
        secondary_periods: Optional[List[str]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """业务模块说明。"""
        stock_code = validate_stock_code(stock_code)
        primary_period = validate_period(primary_period)
        start_date, end_date = validate_time_range(start_date, end_date)
        
        if secondary_periods is None:
            secondary_periods = ["60min", "30min"]
        
        secondary_periods = [validate_period(p) for p in secondary_periods]
        all_periods = [primary_period] + secondary_periods
        
        try:
            signals_by_period: Dict[str, List[Signal]] = {}
            results_by_period: Dict[str, Dict[str, Any]] = {}
            
            for period in all_periods:
                candles = self.stock_service.get_candles(
                    stock_code, period, start_date, end_date
                )
                
                if not candles:
                    logger.warning(f"No candle data for {stock_code} {period}")
                    continue
                
                cleaned, _ = self.kline_processor.clean(candles)
                merged = self.kline_processor.merge(cleaned)
                fractals = self.fractal_detector.detect(merged)
                bis = self.bi_detector.detect(fractals, merged)
                duans = self.duan_detector.detect(bis)
                zhongshus = self.zhongshu_detector.detect(bis)
                
                signal_detector = SignalDetector(stock_code, period)
                signals = signal_detector.detect_all(bis, duans, zhongshus)
                
                signals_by_period[period] = signals
                results_by_period[period] = {
                    "candle_count": len(candles),
                    "merged_count": len(merged),
                    "fractal_count": len(fractals),
                    "bi_count": len(bis),
                    "duan_count": len(duans),
                    "zhongshu_count": len(zhongshus),
                    "signal_count": len(signals),
                    "latest_signal": signals[-1].signal_type.value if signals else None,
                    "signals": [self._signal_to_dict(s) for s in signals],
                }

            if primary_period not in results_by_period:
                raise AnalysisException(
                    message="No candle data available for primary period",
                    stock_code=stock_code,
                    period=primary_period,
                )
            
            combined_signals = self.multi_level_linkage.generate_combined_signal(
                signals_by_period
            )
            
            strong_confirmations = [s for s in combined_signals if s.is_strong_confirmation]
            conflicts = [s for s in combined_signals if s.has_conflict]
            
            return {
                "stock_code": stock_code,
                "primary_period": primary_period,
                "secondary_periods": secondary_periods,
                "period_results": results_by_period,
                "combined_signals": [
                    self._combined_signal_to_dict(s) for s in combined_signals
                ],
                "summary": {
                    "total_combined_signals": len(combined_signals),
                    "strong_confirmations": len(strong_confirmations),
                    "conflicts": len(conflicts),
                    "recommendation": self._generate_recommendation(
                        combined_signals, primary_period
                    ),
                },
            }
            
        except AnalysisException:
            raise
        except Exception as e:
            logger.error(f"Multi-level analysis error: {e}", exc_info=True)
            raise AnalysisException(
                message=f"多周期联立分析失败: {str(e)}",
                stock_code=stock_code,
                period=primary_period,
            )
    
    def _combined_signal_to_dict(self, s: CombinedSignal) -> Dict[str, Any]:
        """业务模块说明。"""
        return {
            "stock_code": s.stock_code,
            "signal_type": s.signal_type.value,
            "timestamp": s.timestamp.isoformat(),
            "price": s.price,
            "primary_level": s.primary_level,
            "secondary_levels": s.secondary_levels,
            "strength": s.strength,
            "is_strong_confirmation": s.is_strong_confirmation,
            "has_conflict": s.has_conflict,
            "conflict_details": s.conflict_details,
        }
    
    def _generate_recommendation(
        self,
        combined_signals: List[CombinedSignal],
        primary_period: str,
    ) -> str:
        """业务模块说明。"""
        if not combined_signals:
            return "暂无明确信号，建议观望"
        
        latest = combined_signals[-1]
        
        if latest.is_strong_confirmation:
            signal_type = "买入" if latest.signal_type.value.startswith("buy") else "卖出"
            return f"【强确认】{primary_period}级别第一类{signal_type}点 + 次级别第二类{signal_type}点共振，信号强度: {latest.strength:.2f}"
        
        if latest.has_conflict:
            primary_dir = latest.conflict_details.get("primary_direction", "")
            return f"【冲突】大级别看{primary_dir}，但次级别存在反向信号，建议等待确认"
        
        if latest.strength >= 0.7:
            signal_type = "买入" if latest.signal_type.value.startswith("buy") else "卖出"
            return f"【正常】{primary_period}级别{signal_type}信号，多周期共振，信号强度: {latest.strength:.2f}"
        
        return f"信号强度较弱 ({latest.strength:.2f})，建议观望或轻仓"
