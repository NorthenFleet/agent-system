"""
速率限制中间件 - 限制每个 IP 的请求频率
限制：100 次/分钟/IP
使用滑动窗口算法实现
"""
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from collections import defaultdict
import time
from datetime import datetime
from typing import Dict, List


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """
    基于 IP 的速率限制中间件
    使用滑动窗口算法，限制每个 IP 每分钟最多 100 次请求
    """
    
    def __init__(self, app, requests_per_minute: int = 100):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        # 存储每个 IP 的请求时间戳列表
        self.request_history: Dict[str, List[float]] = defaultdict(list)
        # 被限制的 IP 列表（用于告警）
        self.rate_limited_ips: Dict[str, int] = {}
    
    def _get_client_ip(self, request: Request) -> str:
        """获取客户端真实 IP，考虑代理情况"""
        # 检查 X-Forwarded-For 头
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # 取第一个 IP（原始客户端 IP）
            return forwarded_for.split(",")[0].strip()
        
        # 检查 X-Real-IP 头
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()
        
        # 直接使用连接 IP
        client_host = request.client.host if request.client else "unknown"
        return client_host
    
    def _clean_old_requests(self, ip: str, current_time: float) -> None:
        """清理超过时间窗口的请求记录"""
        window_start = current_time - 60  # 60 秒窗口
        self.request_history[ip] = [
            timestamp for timestamp in self.request_history[ip]
            if timestamp > window_start
        ]
    
    def _is_rate_limited(self, ip: str) -> bool:
        """检查 IP 是否超出速率限制"""
        current_time = time.time()
        self._clean_old_requests(ip, current_time)
        
        return len(self.request_history[ip]) >= self.requests_per_minute
    
    def _record_request(self, ip: str) -> None:
        """记录一次请求"""
        current_time = time.time()
        self._clean_old_requests(ip, current_time)
        self.request_history[ip].append(current_time)
    
    async def dispatch(self, request: Request, call_next) -> Response:
        # 跳过静态文件和某些路径
        skip_paths = ["/docs", "/redoc", "/openapi.json", "/static"]
        if any(request.url.path.startswith(path) for path in skip_paths):
            return await call_next(request)
        
        client_ip = self._get_client_ip(request)
        
        # 检查是否被限流
        if self._is_rate_limited(client_ip):
            # 记录限流事件
            if client_ip not in self.rate_limited_ips:
                self.rate_limited_ips[client_ip] = 0
            self.rate_limited_ips[client_ip] += 1
            
            # 返回 429 Too Many Requests
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too Many Requests",
                    "detail": f"Rate limit exceeded. Maximum {self.requests_per_minute} requests per minute.",
                    "retry_after": 60
                },
                headers={
                    "Retry-After": "60",
                    "X-RateLimit-Limit": str(self.requests_per_minute),
                    "X-RateLimit-Remaining": "0"
                }
            )
        
        # 记录请求
        self._record_request(client_ip)
        
        # 继续处理请求
        response = await call_next(request)
        
        # 添加速率限制头信息
        remaining = self.requests_per_minute - len(self.request_history[client_ip])
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))
        
        return response
    
    def get_stats(self) -> dict:
        """获取限流统计信息"""
        current_time = time.time()
        active_ips = {}
        
        for ip, timestamps in self.request_history.items():
            # 清理并计算活跃 IP
            self._clean_old_requests(ip, current_time)
            if timestamps:
                active_ips[ip] = len(timestamps)
        
        return {
            "active_ips": len(active_ips),
            "total_requests_last_minute": sum(active_ips.values()),
            "rate_limited_ips_count": len(self.rate_limited_ips),
            "rate_limited_total": sum(self.rate_limited_ips.values())
        }
    
    def get_limited_ips(self) -> dict:
        """获取被限流的 IP 列表"""
        return dict(self.rate_limited_ips)
    
    def reset_stats(self) -> None:
        """重置统计数据"""
        self.request_history.clear()
        self.rate_limited_ips.clear()


# 全局实例（用于监控和告警）
rate_limiter_instance: RateLimiterMiddleware = None


def get_rate_limiter() -> RateLimiterMiddleware:
    """获取全局限流器实例"""
    return rate_limiter_instance
