"""业务模块说明。"""

import time
import logging
from typing import Callable
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """业务模块说明。"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """业务模块说明。"""
        start_time = time.time()
        
        # 获取请求信息
        method = request.method
        path = request.url.path
        query = str(request.query_params) if request.query_params else ""
        client_ip = request.client.host if request.client else "unknown"
        
        # 处理请求
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            logger.error(f"Request failed: {method} {path} - {e}")
            raise
        
        # 计算响应时间
        duration_ms = (time.time() - start_time) * 1000
        
        # 记录日志
        log_message = (
            f"{method} {path}"
            f"{' ?' + query if query else ''}"
            f" - {status_code}"
            f" - {duration_ms:.2f}ms"
            f" - {client_ip}"
        )
        
        if status_code >= 500:
            logger.error(log_message)
        elif status_code >= 400:
            logger.warning(log_message)
        else:
            logger.info(log_message)
        
        return response


def register_logging_middleware(app: FastAPI) -> None:
    """业务模块说明。"""
    app.add_middleware(LoggingMiddleware)


def setup_logging(level: str = "INFO", format_str: str = None) -> None:
    """业务模块说明。"""
    if format_str is None:
        format_str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=format_str,
    )
