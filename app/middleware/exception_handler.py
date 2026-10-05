"""业务模块说明。"""

import logging
from typing import Optional, Dict, Any
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 错误代码与用户友好消息映射
# ---------------------------------------------------------------------------

ERROR_MESSAGES = {
    "APP_ERROR": "系统处理出现异常，请稍后重试",
    "DATA_FETCH_ERROR": "数据获取失败，请检查股票代码或稍后重试",
    "ANALYSIS_ERROR": "分析处理失败，可能是数据不足或参数错误",
    "VALIDATION_ERROR": "输入参数不正确，请检查后重新提交",
    "NOT_FOUND": "请求的资源不存在",
    "TRADING_ERROR": "交易操作失败，请检查账户状态和订单参数",
    "VALUE_ERROR": "参数值不符合要求",
    "INTERNAL_ERROR": "服务器内部错误，我们正在处理中",
}

COMMON_ERROR_HINTS = {
    "股票代码": "请输入正确的股票代码（如 000001、600000）",
    "数据不足": "该股票的历史数据可能不足，请尝试缩短时间范围",
    "网络超时": "网络请求超时，请检查网络连接后重试",
    "资金不足": "账户可用资金不足，请调整买入数量或先卖出持仓",
    "持仓不足": "可用持仓数量不足，请检查持仓状态",
    "交易时间": "当前非交易时间，请在交易时段内操作",
}


def get_friendly_message(code: str, original_message: str) -> str:
    """业务模块说明。"""
    base_message = ERROR_MESSAGES.get(code, ERROR_MESSAGES["APP_ERROR"])
    
    # 检查是否包含常见错误关键词，添加提示
    hints = []
    for keyword, hint in COMMON_ERROR_HINTS.items():
        if keyword in original_message:
            hints.append(hint)
    
    if hints:
        return f"{base_message}。提示：{hints[0]}"
    
    # 如果原始消息是中文，直接使用
    if any('\u4e00' <= char <= '\u9fff' for char in original_message):
        return original_message
    
    return base_message


# ---------------------------------------------------------------------------
# 异常基类
# ---------------------------------------------------------------------------

class AppException(Exception):
    """业务模块说明。"""
    
    def __init__(
        self,
        message: str,
        code: str = "APP_ERROR",
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
        user_message: Optional[str] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        self.user_message = user_message or get_friendly_message(code, message)
    
    def to_dict(self) -> Dict[str, Any]:
        """业务模块说明。"""
        return {
            "error": {
                "code": self.code,
                "message": self.user_message,
                "technical_message": self.message,
                "details": self.details,
            }
        }


class DataFetchException(AppException):
    """业务模块说明。"""
    
    # 数据源相关的友好提示
    SOURCE_MESSAGES = {
        "akshare": "AKShare 数据源暂时不可用，请稍后重试",
        "yahoo": "Yahoo Finance 数据获取失败，可能需要检查网络连接",
    }
    
    def __init__(
        self,
        message: str,
        stock_code: Optional[str] = None,
        source: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        # 生成用户友好消息
        if stock_code:
            user_msg = f"获取股票 {stock_code} 数据失败"
        else:
            user_msg = "数据获取失败"
        
        if source and source in self.SOURCE_MESSAGES:
            user_msg += f"：{self.SOURCE_MESSAGES[source]}"
        else:
            user_msg += "，请检查股票代码是否正确或稍后重试"
        
        super().__init__(
            message=message,
            code="DATA_FETCH_ERROR",
            status_code=502,
            details={
                "stock_code": stock_code,
                "source": source,
                **(details or {}),
            },
            user_message=user_msg,
        )


class AnalysisException(AppException):
    """业务模块说明。"""
    
    def __init__(
        self,
        message: str,
        stock_code: Optional[str] = None,
        period: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        # 生成用户友好消息
        period_names = {
            "daily": "日线",
            "weekly": "周线",
            "monthly": "月线",
            "60min": "60分钟",
            "30min": "30分钟",
            "15min": "15分钟",
        }
        period_name = period_names.get(period, period) if period else ""
        
        if stock_code:
            user_msg = f"股票 {stock_code} "
            if period_name:
                user_msg += f"的{period_name}周期"
            user_msg += "分析失败"
        else:
            user_msg = "缠论分析处理失败"
        
        # 常见原因提示
        if "data" in message.lower() or "数据" in message:
            user_msg += "，可能是数据不足或质量问题"
        elif "timeout" in message.lower():
            user_msg += "，处理超时，请稍后重试"
        else:
            user_msg += "，请检查参数设置"
        
        super().__init__(
            message=message,
            code="ANALYSIS_ERROR",
            status_code=500,
            details={
                "stock_code": stock_code,
                "period": period,
                **(details or {}),
            },
            user_message=user_msg,
        )


class ValidationException(AppException):
    """业务模块说明。"""
    
    # 字段名称中文映射
    FIELD_NAMES = {
        "stock_code": "股票代码",
        "period": "K线周期",
        "start_date": "开始日期",
        "end_date": "结束日期",
        "quantity": "数量",
        "price": "价格",
    }
    
    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        value: Optional[Any] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        # 生成用户友好消息
        field_name = self.FIELD_NAMES.get(field, field) if field else "参数"
        user_msg = f"{field_name}输入不正确"
        
        if value is not None:
            user_msg += f"，当前值为 '{value}'"
        
        # 根据字段提供具体建议
        if field == "stock_code":
            user_msg += "。请输入6位数字的股票代码，如 000001 或 600000"
        elif field == "period":
            user_msg += "。支持的周期：daily（日线）、weekly（周线）、60min、30min、15min"
        elif field in ("start_date", "end_date"):
            user_msg += "。日期格式应为 YYYY-MM-DD，如 2024-01-01"
        elif field == "quantity":
            user_msg += "。买入数量必须是100的整数倍"
        
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            status_code=400,
            details={
                "field": field,
                "value": str(value) if value is not None else None,
                **(details or {}),
            },
            user_message=user_msg,
        )


class NotFoundException(AppException):
    """业务模块说明。"""
    
    # 资源类型中文映射
    RESOURCE_NAMES = {
        "Stock": "股票",
        "AnalysisResult": "分析结果",
        "Watchlist": "自选股",
        "Order": "订单",
        "Position": "持仓",
    }
    
    def __init__(
        self,
        message: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        # 生成用户友好消息
        resource_name = self.RESOURCE_NAMES.get(resource_type, "资源") if resource_type else "资源"
        
        if resource_id:
            user_msg = f"未找到{resource_name}「{resource_id}」"
        else:
            user_msg = f"未找到相关{resource_name}"
        
        # 提供建议
        if resource_type == "AnalysisResult":
            user_msg += "，请先执行分析"
        elif resource_type == "Stock":
            user_msg += "，请检查股票代码是否正确"
        
        super().__init__(
            message=message,
            code="NOT_FOUND",
            status_code=404,
            details={
                "resource_type": resource_type,
                "resource_id": resource_id,
                **(details or {}),
            },
            user_message=user_msg,
        )


# ---------------------------------------------------------------------------
# 异常处理器注册
# ---------------------------------------------------------------------------

def register_exception_handlers(app: FastAPI) -> None:
    """业务模块说明。"""
    
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        """业务模块说明。"""
        logger.warning(
            f"AppException: {exc.code} - {exc.message}",
            extra={"details": exc.details, "path": request.url.path},
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_dict(),
        )
    
    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        """业务模块说明。"""
        logger.warning(f"ValueError: {exc}", extra={"path": request.url.path})
        
        # 尝试从错误消息中提取有用信息
        error_msg = str(exc)
        user_msg = "输入参数不正确"
        
        # 常见 ValueError 的中文翻译
        if "invalid literal" in error_msg:
            user_msg = "输入格式不正确，请检查数值类型"
        elif "time data" in error_msg and "format" in error_msg:
            user_msg = "日期格式不正确，请使用 YYYY-MM-DD 格式"
        elif "empty" in error_msg.lower():
            user_msg = "输入不能为空"
        elif any('\u4e00' <= char <= '\u9fff' for char in error_msg):
            user_msg = error_msg  # 已经是中文消息
        
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "VALUE_ERROR",
                    "message": user_msg,
                    "technical_message": error_msg,
                    "details": {},
                }
            },
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """业务模块说明。"""
        logger.error(
            f"Unhandled exception: {type(exc).__name__} - {exc}",
            extra={"path": request.url.path},
            exc_info=True,
        )
        
        # 根据异常类型提供更友好的消息
        exc_name = type(exc).__name__
        error_msg = str(exc)
        
        user_messages = {
            "ConnectionError": "网络连接失败，请检查网络后重试",
            "TimeoutError": "请求超时，服务器响应较慢，请稍后重试",
            "FileNotFoundError": "系统文件缺失，请联系技术支持",
            "PermissionError": "权限不足，无法执行此操作",
            "KeyError": "数据格式异常，请联系技术支持",
            "IndexError": "数据处理异常，请稍后重试",
        }
        
        user_msg = user_messages.get(exc_name, "系统内部错误，我们正在处理中，请稍后重试")
        
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": user_msg,
                    "technical_message": f"{exc_name}: {error_msg}" if app.debug else None,
                    "details": {},
                }
            },
        )
