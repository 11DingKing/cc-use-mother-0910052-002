"""业务模块说明。"""

import re
from datetime import datetime, timedelta
from typing import Optional, List, Tuple

from app.middleware.exception_handler import ValidationException
from app.config import SUPPORTED_PERIODS


# ---------------------------------------------------------------------------
# 股票代码验证
# ---------------------------------------------------------------------------

# A股代码正则：6位数字，可选前缀 sh/sz/bj
A_STOCK_PATTERN = re.compile(r"^(sh|sz|bj)?(\d{6})$", re.IGNORECASE)

# 美股代码正则：1-5位字母
US_STOCK_PATTERN = re.compile(r"^[A-Za-z]{1,5}$")

# 港股代码正则：5位数字（以0开头）
HK_STOCK_PATTERN = re.compile(r"^0\d{4}$")


def validate_stock_code(code: str, market: str = "auto") -> str:
    """业务模块说明。"""
    if not code:
        raise ValidationException(
            message="Stock code cannot be empty",
            field="stock_code",
            value=code,
        )
    
    code = code.strip()
    
    if market == "auto":
        # 自动检测市场
        if A_STOCK_PATTERN.match(code):
            return _normalize_a_stock_code(code)
        elif US_STOCK_PATTERN.match(code):
            return code.upper()
        elif HK_STOCK_PATTERN.match(code):
            return code
        else:
            raise ValidationException(
                message="Invalid stock code format",
                field="stock_code",
                value=code,
            )
    
    elif market == "cn":
        if not A_STOCK_PATTERN.match(code):
            raise ValidationException(
                message="Invalid A-share stock code format",
                field="stock_code",
                value=code,
                details={"expected_format": "6 digits, optional prefix sh/sz/bj"},
            )
        return _normalize_a_stock_code(code)
    
    elif market == "us":
        if not US_STOCK_PATTERN.match(code):
            raise ValidationException(
                message="Invalid US stock code format",
                field="stock_code",
                value=code,
                details={"expected_format": "1-5 letters"},
            )
        return code.upper()
    
    elif market == "hk":
        if not HK_STOCK_PATTERN.match(code):
            raise ValidationException(
                message="Invalid HK stock code format",
                field="stock_code",
                value=code,
                details={"expected_format": "4-5 digits"},
            )
        return code
    
    else:
        raise ValidationException(
            message="Invalid market type",
            field="market",
            value=market,
            details={"valid_values": ["auto", "cn", "us", "hk"]},
        )


def _normalize_a_stock_code(code: str) -> str:
    """业务模块说明。"""
    match = A_STOCK_PATTERN.match(code)
    if not match:
        return code
    
    prefix = match.group(1)
    digits = match.group(2)
    
    # 如果没有前缀，根据代码推断
    if not prefix:
        if digits.startswith("6"):
            prefix = "sh"
        elif digits.startswith(("0", "3")):
            prefix = "sz"
        elif digits.startswith(("4", "8")):
            prefix = "bj"
        else:
            prefix = ""
    
    return f"{prefix.lower()}{digits}" if prefix else digits


# ---------------------------------------------------------------------------
# 时间范围验证
# ---------------------------------------------------------------------------

def validate_time_range(
    start_date: Optional[datetime],
    end_date: Optional[datetime],
    max_days: int = 3650,  # 默认最多10年
) -> Tuple[datetime, datetime]:
    """业务模块说明。"""
    now = datetime.now()
    
    # 设置默认值
    if end_date is None:
        end_date = now
    if start_date is None:
        start_date = end_date - timedelta(days=365)
    
    # 验证顺序
    if start_date > end_date:
        raise ValidationException(
            message="Start date must be before end date",
            field="time_range",
            value=f"{start_date} - {end_date}",
        )
    
    # 验证不能是未来日期
    if start_date > now:
        raise ValidationException(
            message="Start date cannot be in the future",
            field="start_date",
            value=str(start_date),
        )
    
    # 验证范围不能太大
    days_diff = (end_date - start_date).days
    if days_diff > max_days:
        raise ValidationException(
            message=f"Time range cannot exceed {max_days} days",
            field="time_range",
            value=f"{days_diff} days",
            details={"max_days": max_days},
        )
    
    return start_date, end_date


def parse_date(date_str: str, field_name: str = "date") -> datetime:
    """业务模块说明。"""
    if not date_str:
        raise ValidationException(
            message="Date cannot be empty",
            field=field_name,
            value=date_str,
        )
    
    date_str = date_str.strip()
    
    formats = [
        "%Y-%m-%d",
        "%Y%m%d",
        "%Y/%m/%d",
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    raise ValidationException(
        message="Invalid date format",
        field=field_name,
        value=date_str,
        details={"supported_formats": ["YYYY-MM-DD", "YYYYMMDD", "YYYY/MM/DD"]},
    )


# ---------------------------------------------------------------------------
# 参数验证
# ---------------------------------------------------------------------------

def validate_period(period: str) -> str:
    """业务模块说明。"""
    if not period:
        raise ValidationException(
            message="Period cannot be empty",
            field="period",
            value=period,
        )
    
    period = period.strip().lower()
    
    # 别名映射
    aliases = {
        "d": "daily",
        "day": "daily",
        "1d": "daily",
        "60m": "60min",
        "1h": "60min",
        "30m": "30min",
        "15m": "15min",
    }
    
    period = aliases.get(period, period)
    
    if period not in SUPPORTED_PERIODS:
        raise ValidationException(
            message="Unsupported period",
            field="period",
            value=period,
            details={"supported_periods": SUPPORTED_PERIODS},
        )
    
    return period


def validate_positive_number(
    value: float,
    field_name: str,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
) -> float:
    """业务模块说明。"""
    if value <= 0:
        raise ValidationException(
            message=f"{field_name} must be positive",
            field=field_name,
            value=value,
        )
    
    if min_value is not None and value < min_value:
        raise ValidationException(
            message=f"{field_name} must be at least {min_value}",
            field=field_name,
            value=value,
            details={"min_value": min_value},
        )
    
    if max_value is not None and value > max_value:
        raise ValidationException(
            message=f"{field_name} must be at most {max_value}",
            field=field_name,
            value=value,
            details={"max_value": max_value},
        )
    
    return value


def validate_list_not_empty(
    items: List,
    field_name: str,
    max_items: Optional[int] = None,
) -> List:
    """业务模块说明。"""
    if not items:
        raise ValidationException(
            message=f"{field_name} cannot be empty",
            field=field_name,
            value=items,
        )
    
    if max_items is not None and len(items) > max_items:
        raise ValidationException(
            message=f"{field_name} cannot have more than {max_items} items",
            field=field_name,
            value=f"{len(items)} items",
            details={"max_items": max_items},
        )
    
    return items
