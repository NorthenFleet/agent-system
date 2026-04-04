"""
异常访问检测中间件
检测并告警异常访问模式：
1. 高频失败认证
2. 异常 IP 访问
3. 敏感路径探测
4. 异常时间访问
"""
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Dict, List, Optional, Callable
from collections import defaultdict
from datetime import datetime, timedelta
import time
import json
import os


class AnomalyDetectorMiddleware(BaseHTTPMiddleware):
    """
    异常访问检测中间件
    实时检测可疑访问模式并触发告警
    """
    
    def __init__(
        self,
        app,
        alert_callback: Optional[Callable[[dict], None]] = None,
        failed_auth_threshold: int = 5,  # 5 次失败认证触发告警
        time_window_seconds: int = 300,  # 5 分钟窗口
        sensitive_paths: Optional[List[str]] = None
    ):
        super().__init__(app)
        
        self.alert_callback = alert_callback or self._default_alert_handler
        self.failed_auth_threshold = failed_auth_threshold
        self.time_window_seconds = time_window_seconds
        
        # 敏感路径（探测这些路径会触发告警）
        self.sensitive_paths = sensitive_paths or [
            "/admin",
            "/api/admin",
            "/.env",
            "/.git",
            "/config",
            "/backup",
            "/debug",
            "/test",
            "/phpmyadmin",
            "/wp-admin"
        ]
        
        # 跟踪数据
        self.failed_auth_by_ip: Dict[str, List[float]] = defaultdict(list)
        self.path_probe_by_ip: Dict[str, List[str]] = defaultdict(list)
        self.request_rate_by_ip: Dict[str, List[float]] = defaultdict(list)
        
        # 告警历史
        self.alerts: List[dict] = []
        self.alerted_ips: Dict[str, float] = {}  # IP -> 最后告警时间
        
        # 告警统计
        self.stats = {
            "total_alerts": 0,
            "alerts_by_type": defaultdict(int),
            "blocked_ips": set()
        }
    
    def _default_alert_handler(self, alert: dict) -> None:
        """默认告警处理器 - 打印到控制台并写入文件"""
        self.alerts.append(alert)
        self.stats["total_alerts"] += 1
        self.stats["alerts_by_type"][alert["type"]] += 1
        
        # 写入告警文件
        alert_file = os.path.join(
            os.path.dirname(__file__),
            "..",
            "security_alerts.jsonl"
        )
        try:
            with open(alert_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(alert, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[AnomalyDetector] Failed to write alert: {e}")
        
        # 打印告警
        print(f"\n🚨 [SECURITY ALERT] {alert['type']}: {alert['message']}")
        print(f"   IP: {alert['ip']}")
        print(f"   Time: {alert['timestamp']}")
        print(f"   Severity: {alert['severity']}\n")
    
    def _should_alert(self, ip: str) -> bool:
        """检查是否应该为此 IP 发送告警（避免重复告警）"""
        last_alert = self.alerted_ips.get(ip, 0)
        return time.time() - last_alert > 300  # 同一 IP 5 分钟内只告警一次
    
    def _record_alert(self, ip: str) -> None:
        """记录告警时间"""
        self.alerted_ips[ip] = time.time()
    
    def _clean_old_records(self, current_time: float) -> None:
        """清理过期的记录"""
        cutoff = current_time - self.time_window_seconds
        
        # 清理失败认证记录
        for ip in list(self.failed_auth_by_ip.keys()):
            self.failed_auth_by_ip[ip] = [
                t for t in self.failed_auth_by_ip[ip] if t > cutoff
            ]
            if not self.failed_auth_by_ip[ip]:
                del self.failed_auth_by_ip[ip]
        
        # 清理请求速率记录
        for ip in list(self.request_rate_by_ip.keys()):
            self.request_rate_by_ip[ip] = [
                t for t in self.request_rate_by_ip[ip] if t > cutoff
            ]
            if not self.request_rate_by_ip[ip]:
                del self.request_rate_by_ip[ip]
    
    def _check_failed_auth(self, ip: str, status_code: int) -> Optional[dict]:
        """检查失败认证是否达到阈值"""
        current_time = time.time()
        
        if status_code == 401:
            self.failed_auth_by_ip[ip].append(current_time)
            
            # 检查是否超过阈值
            if len(self.failed_auth_by_ip[ip]) >= self.failed_auth_threshold:
                if self._should_alert(ip):
                    self._record_alert(ip)
                    return {
                        "type": "FAILED_AUTH_THRESHOLD",
                        "severity": "HIGH",
                        "ip": ip,
                        "message": f"Multiple failed authentication attempts ({len(self.failed_auth_by_ip[ip])} times)",
                        "timestamp": datetime.now().isoformat(),
                        "details": {
                            "failed_attempts": len(self.failed_auth_by_ip[ip]),
                            "threshold": self.failed_auth_threshold,
                            "time_window_seconds": self.time_window_seconds
                        }
                    }
        return None
    
    def _check_path_probing(self, ip: str, path: str) -> Optional[dict]:
        """检查敏感路径探测"""
        for sensitive_path in self.sensitive_paths:
            if path.startswith(sensitive_path) or sensitive_path in path.lower():
                self.path_probe_by_ip[ip].append(path)
                
                # 如果探测了多个敏感路径，触发告警
                if len(self.path_probe_by_ip[ip]) >= 3 and self._should_alert(ip):
                    self._record_alert(ip)
                    return {
                        "type": "PATH_PROBING",
                        "severity": "MEDIUM",
                        "ip": ip,
                        "message": f"Suspicious path probing detected ({len(self.path_probe_by_ip[ip])} sensitive paths)",
                        "timestamp": datetime.now().isoformat(),
                        "details": {
                            "probed_paths": self.path_probe_by_ip[ip][-10:],
                            "sensitive_paths_matched": len(self.path_probe_by_ip[ip])
                        }
                    }
        return None
    
    def _check_request_rate(self, ip: str) -> Optional[dict]:
        """检查异常请求速率"""
        current_time = time.time()
        self.request_rate_by_ip[ip].append(current_time)
        
        # 清理旧记录
        cutoff = current_time - 60  # 1 分钟窗口
        self.request_rate_by_ip[ip] = [
            t for t in self.request_rate_by_ip[ip] if t > cutoff
        ]
        
        # 如果速率异常高（> 200 次/分钟），触发告警
        if len(self.request_rate_by_ip[ip]) > 200 and self._should_alert(ip):
            self._record_alert(ip)
            return {
                "type": "ABNORMAL_REQUEST_RATE",
                "severity": "HIGH",
                "ip": ip,
                "message": f"Abnormally high request rate ({len(self.request_rate_by_ip[ip])} requests/minute)",
                "timestamp": datetime.now().isoformat(),
                "details": {
                    "requests_per_minute": len(self.request_rate_by_ip[ip]),
                    "threshold": 200
                }
            }
        return None
    
    def _check_time_anomaly(self) -> Optional[dict]:
        """检查异常时间访问（可选功能）"""
        # 可以在此添加基于时间的异常检测
        # 例如：凌晨时段的异常访问
        return None
    
    async def dispatch(self, request: Request, call_next) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        
        # 处理请求
        response = await call_next(request)
        
        # 清理过期记录
        self._clean_old_records(time.time())
        
        # 检查各种异常模式
        alerts = []
        
        # 1. 检查失败认证
        alert = self._check_failed_auth(client_ip, response.status_code)
        if alert:
            alerts.append(alert)
        
        # 2. 检查路径探测
        alert = self._check_path_probing(client_ip, request.url.path)
        if alert:
            alerts.append(alert)
        
        # 3. 检查请求速率
        alert = self._check_request_rate(client_ip)
        if alert:
            alerts.append(alert)
        
        # 发送告警
        for alert in alerts:
            self.alert_callback(alert)
        
        return response
    
    def get_alerts(self, limit: int = 100) -> List[dict]:
        """获取最近的告警"""
        return self.alerts[-limit:]
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            **self.stats,
            "alerts_by_type": dict(self.stats["alerts_by_type"]),
            "blocked_ips_count": len(self.stats["blocked_ips"]),
            "active_threats": len(self.alerted_ips)
        }
    
    def block_ip(self, ip: str, reason: str = "Manual block") -> None:
        """手动封禁 IP"""
        self.stats["blocked_ips"].add(ip)
        self.alert_callback({
            "type": "IP_BLOCKED",
            "severity": "CRITICAL",
            "ip": ip,
            "message": f"IP manually blocked: {reason}",
            "timestamp": datetime.now().isoformat(),
            "details": {"reason": reason}
        })
    
    def unblock_ip(self, ip: str) -> None:
        """解除 IP 封禁"""
        self.stats["blocked_ips"].discard(ip)
    
    def is_blocked(self, ip: str) -> bool:
        """检查 IP 是否被封禁"""
        return ip in self.stats["blocked_ips"]
    
    def reset_stats(self) -> None:
        """重置统计数据"""
        self.stats = {
            "total_alerts": 0,
            "alerts_by_type": defaultdict(int),
            "blocked_ips": set()
        }
        self.alerts.clear()
        self.alerted_ips.clear()


# 全局实例
anomaly_instance: AnomalyDetectorMiddleware = None


def get_anomaly_detector() -> AnomalyDetectorMiddleware:
    """获取全局异常检测器实例"""
    return anomaly_instance
