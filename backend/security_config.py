"""
安全配置文件
集中管理所有安全相关的配置项
"""
import os
from typing import Set, List


# ============================================
# 速率限制配置
# ============================================
RATE_LIMIT_REQUESTS_PER_MINUTE = int(os.getenv("RATE_LIMIT_REQUESTS", "100"))
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"


# ============================================
# API Key 认证配置
# ============================================
API_KEYS: Set[str] = set(
    os.getenv("API_KEYS", "dashboard-key-001,dashboard-key-002,admin-key-master").split(",")
)
AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "false").lower() == "true"
AUTH_EXCLUDE_PATHS: Set[str] = {
    "/",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/static",
    "/health",
    "/api/public"
}


# ============================================
# 请求日志配置
# ============================================
LOG_FILE_PATH = os.getenv("LOG_FILE_PATH", "request_logs.jsonl")
LOG_MAX_MEMORY_ENTRIES = int(os.getenv("LOG_MAX_MEMORY", "1000"))
LOG_INCLUDE_BODY = os.getenv("LOG_INCLUDE_BODY", "false").lower() == "true"
LOG_EXCLUDE_PATHS: List[str] = ["/static", "/favicon.ico"]


# ============================================
# 异常检测配置
# ============================================
ALERT_FAILED_AUTH_THRESHOLD = int(os.getenv("ALERT_FAILED_AUTH", "5"))
ALERT_TIME_WINDOW_SECONDS = int(os.getenv("ALERT_TIME_WINDOW", "300"))
ALERT_REQUEST_RATE_THRESHOLD = int(os.getenv("ALERT_REQUEST_RATE", "200"))

SENSITIVE_PATHS: List[str] = [
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


# ============================================
# 告警配置
# ============================================
ALERT_EMAIL_ENABLED = os.getenv("ALERT_EMAIL_ENABLED", "false").lower() == "true"
ALERT_EMAIL_RECIPIENTS = os.getenv("ALERT_EMAIL_RECIPIENTS", "").split(",")
ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "")


# ============================================
# 导出配置
# ============================================
def get_security_config() -> dict:
    """获取完整的安全配置"""
    return {
        "rate_limiting": {
            "enabled": RATE_LIMIT_ENABLED,
            "requests_per_minute": RATE_LIMIT_REQUESTS_PER_MINUTE
        },
        "authentication": {
            "required": AUTH_REQUIRED,
            "api_keys_count": len(API_KEYS),
            "exclude_paths": list(AUTH_EXCLUDE_PATHS)
        },
        "logging": {
            "file_path": LOG_FILE_PATH,
            "max_memory_entries": LOG_MAX_MEMORY_ENTRIES,
            "include_body": LOG_INCLUDE_BODY
        },
        "anomaly_detection": {
            "failed_auth_threshold": ALERT_FAILED_AUTH_THRESHOLD,
            "time_window_seconds": ALERT_TIME_WINDOW_SECONDS,
            "request_rate_threshold": ALERT_REQUEST_RATE_THRESHOLD,
            "sensitive_paths_count": len(SENSITIVE_PATHS)
        },
        "alerts": {
            "email_enabled": ALERT_EMAIL_ENABLED,
            "email_recipients": ALERT_EMAIL_RECIPIENTS,
            "webhook_url": ALERT_WEBHOOK_URL
        }
    }
