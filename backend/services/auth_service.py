"""
JWT 认证服务
- 密码哈希: bcrypt (直接使用 bcrypt 库，替代 passlib)
- JWT: python-jose
"""
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import bcrypt
from jose import jwt, JWTError

# 从环境变量读取；缺失时使用进程级临时密钥，避免硬编码可预测签名密钥。
SECRET_KEY = os.getenv("DASHBOARD_JWT_SECRET")
if not SECRET_KEY:
    SECRET_KEY = secrets.token_urlsafe(32)
    print("[Auth] DASHBOARD_JWT_SECRET 未设置，已使用临时 JWT 密钥；重启后既有 token 会失效")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 小时
REFRESH_TOKEN_EXPIRE_DAYS = 7  # 7 天

# 内存中的 token 黑名单 (登出用)
_token_blacklist: set = set()


def hash_password(password: str) -> str:
    """使用 bcrypt 哈希密码"""
    pwd_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """验证密码"""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: Dict[str, Any]) -> str:
    """创建刷新 token（7 天有效期）"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc), "type": "refresh"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        if token in _token_blacklist:
            return None
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


def revoke_token(token: str):
    _token_blacklist.add(token)


def generate_default_admin_password() -> str:
    """生成首次 admin 密码；可用环境变量显式指定，否则使用随机值。"""
    configured = os.getenv("DASHBOARD_INITIAL_ADMIN_PASSWORD")
    if configured:
        return configured
    return secrets.token_urlsafe(18)
