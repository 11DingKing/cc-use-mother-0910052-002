"""业务模块说明。"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from app.services.analysis_service import AnalysisService
from app.chan.multi_level import MultiLevelLinkage, CombinedSignal, PERIOD_PRIORITY
from app.chan.models import Signal, SignalType


class TestMultiLevelLinkageIntegration:
    """业务模块说明。"""
    
    @pytest.fixture
    def analysis_service(self):
        return AnalysisService()
    
    @pytest.fixture
    def linkage(self):
        return MultiLevelLinkage()
    
    @pytest.fixture
    def mock_signals(self):
        """业务模块说明。"""
        base_time = datetime(2024, 1, 15, 10, 0, 0)
        
        return {
            "daily": [
                Signal(
                    stock_code="000001",
                    signal_type=SignalType.BUY_1,
                    timestamp=base_time,
                    price=10.5,
                    strength=0.8,
                    level=1,
                ),
            ],
            "60min": [
                Signal(
                    stock_code="000001",
                    signal_type=SignalType.BUY_2,
                    timestamp=base_time + timedelta(hours=1),
                    price=10.55,
                    strength=0.7,
                    level=1,
                ),
            ],
            "30min": [
                Signal(
                    stock_code="000001",
                    signal_type=SignalType.BUY_2,
                    timestamp=base_time + timedelta(minutes=30),
                    price=10.52,
                    strength=0.6,
                    level=1,
                ),
            ],
        }
    
    def test_period_priority(self):
        """业务模块说明。"""
        assert PERIOD_PRIORITY["daily"] > PERIOD_PRIORITY["60min"]
        assert PERIOD_PRIORITY["60min"] > PERIOD_PRIORITY["30min"]
        assert PERIOD_PRIORITY["weekly"] > PERIOD_PRIORITY["daily"]
    
    def test_align_results(self, linkage, mock_signals):
        """业务模块说明。"""
        aligned = linkage.align_results(mock_signals, time_window_minutes=120)
        
        assert len(aligned) > 0
        for window_time, period_signals in aligned.items():
            assert isinstance(window_time, datetime)
            assert isinstance(period_signals, dict)
    
    def test_generate_combined_signal(self, linkage, mock_signals):
        """业务模块说明。"""
        combined = linkage.generate_combined_signal(mock_signals)
        
        assert len(combined) > 0
        for signal in combined:
            assert isinstance(signal, CombinedSignal)
            assert signal.stock_code == "000001"
    
    def test_strong_confirmation(self, linkage):
        """业务模块说明。"""
        base_time = datetime(2024, 1, 15, 10, 0, 0)
        
        signals = {
            "daily": [
                Signal(
                    stock_code="000001",
                    signal_type=SignalType.BUY_1,
                    timestamp=base_time,
                    price=10.5,
                    strength=0.8,
                    level=1,
                ),
            ],
            "30min": [
                Signal(
                    stock_code="000001",
                    signal_type=SignalType.BUY_2,
                    timestamp=base_time,
                    price=10.52,
                    strength=0.7,
                    level=1,
                ),
            ],
        }
        
        combined = linkage.generate_combined_signal(signals)
        
        strong_signals = [s for s in combined if s.is_strong_confirmation]
        assert len(strong_signals) > 0
        assert strong_signals[0].strength > 0.8  # 强确认有加成
    
    def test_conflict_detection(self, linkage):
        """业务模块说明。"""
        base_time = datetime(2024, 1, 15, 10, 0, 0)
        
        signals = {
            "daily": [
                Signal(
                    stock_code="000001",
                    signal_type=SignalType.BUY_1,
                    timestamp=base_time,
                    price=10.5,
                    strength=0.8,
                    level=1,
                ),
            ],
            "30min": [
                Signal(
                    stock_code="000001",
                    signal_type=SignalType.SELL_1,
                    timestamp=base_time,
                    price=10.6,
                    strength=0.7,
                    level=1,
                ),
            ],
        }
        
        combined = linkage.generate_combined_signal(signals)
        
        conflict_signals = [s for s in combined if s.has_conflict]
        assert len(conflict_signals) > 0
        assert conflict_signals[0].strength < 0.8  # 冲突有惩罚
    
    def test_empty_signals(self, linkage):
        """业务模块说明。"""
        combined = linkage.generate_combined_signal({})
        assert combined == []
    
    def test_single_period_signals(self, linkage):
        """业务模块说明。"""
        base_time = datetime(2024, 1, 15, 10, 0, 0)
        
        signals = {
            "daily": [
                Signal(
                    stock_code="000001",
                    signal_type=SignalType.BUY_1,
                    timestamp=base_time,
                    price=10.5,
                    strength=0.8,
                    level=1,
                ),
            ],
        }
        
        combined = linkage.generate_combined_signal(signals)
        
        assert len(combined) == 1
        assert combined[0].primary_level == "daily"
        assert not combined[0].is_strong_confirmation
        assert not combined[0].has_conflict


class TestAnalysisServiceMultiLevel:
    """业务模块说明。"""
    
    @pytest.fixture
    def service(self):
        return AnalysisService()
    
    def test_multi_level_service_init(self, service):
        """业务模块说明。"""
        assert hasattr(service, 'multi_level_linkage')
        assert isinstance(service.multi_level_linkage, MultiLevelLinkage)
    
    @patch.object(AnalysisService, 'stock_service')
    def test_run_multi_level_analysis_no_data(self, mock_stock_service, service):
        """业务模块说明。"""
        mock_stock_service.get_candles.return_value = []
        
        with pytest.raises(Exception):
            service.run_multi_level_analysis(
                stock_code="000001",
                primary_period="daily",
                secondary_periods=["30min"],
            )
    
    def test_generate_recommendation(self, service):
        """业务模块说明。"""
        base_time = datetime(2024, 1, 15, 10, 0, 0)
        
        # 强确认信号
        strong_signal = CombinedSignal(
            stock_code="000001",
            signal_type=SignalType.BUY_1,
            timestamp=base_time,
            price=10.5,
            primary_level="daily",
            secondary_levels=["30min"],
            strength=0.9,
            is_strong_confirmation=True,
            has_conflict=False,
        )
        
        rec = service._generate_recommendation([strong_signal], "daily")
        assert "强确认" in rec
        assert "买入" in rec
        
        # 冲突信号
        conflict_signal = CombinedSignal(
            stock_code="000001",
            signal_type=SignalType.BUY_1,
            timestamp=base_time,
            price=10.5,
            primary_level="daily",
            strength=0.5,
            is_strong_confirmation=False,
            has_conflict=True,
            conflict_details={"primary_direction": "buy"},
        )
        
        rec = service._generate_recommendation([conflict_signal], "daily")
        assert "冲突" in rec
        
        # 无信号
        rec = service._generate_recommendation([], "daily")
        assert "观望" in rec
