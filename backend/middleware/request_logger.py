"""
请求日志记录中间件
记录所有请求的详细信息，用于审计和分析
"""
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Optional, List
import json
import time
from datetime import datetime
from collections import deque
import os


class RequestLoggerMiddleware(BaseHTTPMiddleware):
    """
    请求日志记录中间件
    记录请求方法、路径、IP、响应状态码、耗时等信息
    """
    
    def __init__(
        self,
        app,
        log_file: Optional[str] = None,
        max_memory_logs: int = 1000,
        include_body: bool = False,
        exclude_paths: Optional[List[str]] = None
    ):
        super().__init__(app)
        self.log_file = log_file or os.path.join(
            os.path.dirname(__file__),
            "..",
            "request_logs.jsonl"
        )
        self.max_memory_logs = max_memory_logs
        self.include_body = include_body
        self.exclude_paths = exclude_paths or ["/static", "/favicon.ico"]
        
        # 内存中的日志队列（用于实时查询）
        self.memory_logs: deque = deque(maxlen=max_memory_logs)
        
        # 统计信息
        self.stats = {
            "total_requests": 0,
            "total_response_time_ms": 0,
            "requests_by_method": {},
            "requests_by_status": {},
            "slow_requests": 0,  # > 1000ms
            "error_requests": 0  # 4xx and 5xx
        }
    
    def _should_log(self, path: str) -> bool:
        """检查是否应该记录此请求"""
        for exclude_path in self.exclude_paths:
            if path.startswith(exclude_path):
                return False
        return True
    
    def _get_client_info(self, request: Request) -> dict:
        """获取客户端信息"""
        forwarded_for = request.headers.get("x-forwarded-for")
        real_ip = request.headers.get("x-real-ip")
        
        client_ip = request.client.host if request.client else "unknown"
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        elif real_ip:
            client_ip = real_ip.strip()
        
        return {
            "ip": client_ip,
            "user_agent": request.headers.get("user-agent", "unknown"),
            "referer": request.headers.get("referer", "")
        }
    
    async def _get_request_body(self, request: Request) -> Optional[str]:
        """获取请求体（如果配置了记录）"""
        if not self.include_body:
            return None
        
        try:
            body = await request.body()
            if body:
                # 尝试解码为 JSON，否则返回原始字符串
                try:
                    return json.loads(body.decode("utf-8"))
                except:
                    return body.decode("utf-8", errors="ignore")[:1000]  # 限制长度
        except:
            pass
        return None
    
    def _log_request(self, log_entry: dict) -> None:
        """记录请求日志"""
        # 添加到内存队列
        self.memory_logs.append(log_entry)
        
        # 写入文件
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[RequestLogger] Failed to write log: {e}")
    
    def _update_stats(self, method: str, status: int, duration_ms: float) -> None:
        """更新统计信息"""
        self.stats["total_requests"] += 1
        self.stats["total_response_time_ms"] += duration_ms
        
        # 按方法统计
        self.stats["requests_by_method"][method] = \
            self.stats["requests_by_method"].get(method, 0) + 1
        
        # 按状态码统计
        status_category = f"{status // 100}xx"
        self.stats["requests_by_status"][status_category] = \
            self.stats["requests_by_status"].get(status_category, 0) + 1
        
        # 慢请求统计
        if duration_ms > 1000:
            self.stats["slow_requests"] += 1
        
        # 错误请求统计
        if status >= 400:
            self.stats["error_requests"] += 1
    
    async def dispatch(self, request: Request, call_next) -> Response:
        if not self._should_log(request.url.path):
            return await call_next(request)
        
        # 记录开始时间
        start_time = time.time()
        
        # 获取请求信息
        client_info = self._get_client_info(request)
        request_body = await self._get_request_body(request) if self.include_body else None
        
        # 处理请求
        response = await call_next(request)
        
        # 计算耗时
        duration_ms = (time.time() - start_time) * 1000
        
        # 构建日志条目
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "method": request.method,
            "path": request.url.path,
            "query_params": dict(request.query_params) if request.query_params else None,
            "client": client_info,
            "status_code": response.status_code,
            "duration_ms": round(duration_ms, 2),
            "request_body": request_body,
            "response_size": int(response.headers.get("content-length", 0)),
            "api_key": getattr(request.state, "api_key", None),
            "rate_limited": response.status_code == 429
        }
        
        # 记录日志
        self._log_request(log_entry)
        
        # 更新统计
        self._update_stats(request.method, response.status_code, duration_ms)
        
        # 添加请求 ID 到头（用于追踪）
        response.headers["X-Request-Logged"] = "true"
        response.headers["X-Response-Time-Ms"] = str(round(duration_ms, 2))
        
        return response
    
    def get_recent_logs(self, limit: int = 100, filter_status: Optional[int] = None) -> List[dict]:
        """获取最近的日志"""
        logs = list(self.memory_logs)
        
        if filter_status:
            logs = [log for log in logs if log["status_code"] // 100 == filter_status // 100]
        
        return logs[-limit:]
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        total = self.stats["total_requests"]
        avg_response_time = (
            self.stats["total_response_time_ms"] / total if total > 0 else 0
        )
        
        return {
            **self.stats,
            "average_response_time_ms": round(avg_response_time, 2),
            "memory_logs_count": len(self.memory_logs)
        }
    
    def search_logs(
        self,
        ip: Optional[str] = None,
        path: Optional[str] = None,
        status_min: Optional[int] = None,
        status_max: Optional[int] = None,
        duration_min_ms: Optional[float] = None,
        limit: int = 100
    ) -> List[dict]:
        """搜索日志"""
        results = []
        
        for log in reversed(self.memory_logs):
            if ip and log["client"]["ip"] != ip:
                continue
            if path and path not in log["path"]:
                continue
            if status_min and log["status_code"] < status_min:
                continue
            if status_max and log["status_code"] > status_max:
                continue
            if duration_min_ms and log["duration_ms"] < duration_min_ms:
                continue
            
            results.append(log)
            
            if len(results) >= limit:
                break
        
        return results
    
    def reset_stats(self) -> None:
        """重置统计数据"""
        self.stats = {
            "total_requests": 0,
            "total_response_time_ms": 0,
            "requests_by_method": {},
            "requests_by_status": {},
            "slow_requests": 0,
            "error_requests": 0
        }


# 全局实例
logger_instance: RequestLoggerMiddleware = None


def get_request_logger() -> RequestLoggerMiddleware:
    """获取全局日志记录器实例"""
    return logger_instance
