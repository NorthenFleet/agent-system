# 🔒 API 安全中间件

本目录包含团队状态看板 API 的安全中间件实现。

## 中间件列表

### 1. 速率限制中间件 (`rate_limiter.py`)

**功能**: 限制每个 IP 地址的请求频率，防止 DDoS 攻击和滥用。

**配置**:
- 限制：100 次请求/分钟/IP
- 算法：滑动窗口
- 存储：内存（可替换为 Redis）

**响应头**:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
Retry-After: 60  (当触发限制时)
```

**超限响应**:
```json
{
  "error": "Too Many Requests",
  "detail": "Rate limit exceeded. Maximum 100 requests per minute.",
  "retry_after": 60
}
```

---

### 2. API Key 认证中间件 (`auth.py`)

**功能**: 提供 API Key 认证机制，支持多种认证方式。

**支持的认证方式**:
1. Header: `X-API-Key: <your-key>`
2. Bearer Token: `Authorization: Bearer <your-key>`
3. Query Parameter: `?api_key=<your-key>`

**默认 API Keys**:
- `dashboard-key-001` (标准权限)
- `dashboard-key-002` (标准权限)
- `admin-key-master` (管理员权限)

**环境变量**:
```bash
export API_KEYS="key1,key2,key3"
export AUTH_REQUIRED=true  # 强制所有 API 需要认证
```

**认证失败响应**:
```json
{
  "error": "Unauthorized",
  "detail": "Invalid API Key"
}
```

---

### 3. 请求日志中间件 (`request_logger.py`)

**功能**: 记录所有请求的详细信息，用于审计和分析。

**记录内容**:
- 请求方法、路径、查询参数
- 客户端 IP、User-Agent
- 响应状态码、耗时
- API Key（脱敏）
- 请求体（可选）

**日志文件**: `request_logs.jsonl` (JSON Lines 格式)

**查询 API**:
- `GET /api/monitor/logs?limit=100` - 获取最近日志
- `GET /api/monitor/security/stats` - 获取统计信息

---

### 4. 异常检测中间件 (`anomaly_detector.py`)

**功能**: 实时检测可疑访问模式并触发告警。

**检测类型**:

| 类型 | 触发条件 | 严重级别 |
|------|----------|----------|
| FAILED_AUTH_THRESHOLD | 5 次/5 分钟 认证失败 | HIGH |
| PATH_PROBING | 探测 3+ 敏感路径 | MEDIUM |
| ABNORMAL_REQUEST_RATE | >200 次/分钟 | HIGH |
| IP_BLOCKED | 手动封禁 | CRITICAL |

**敏感路径**:
- `/admin`, `/api/admin`
- `/.env`, `/.git`
- `/config`, `/backup`
- `/debug`, `/test`
- `/phpmyadmin`, `/wp-admin`

**告警文件**: `security_alerts.jsonl`

**管理 API**:
- `POST /api/admin/security/block-ip?ip=1.2.3.4&reason=...` - 封禁 IP
- `POST /api/admin/security/unblock-ip?ip=1.2.3.4` - 解除封禁

---

## 使用方法

### 在 main.py 中加载中间件

```python
from middleware.rate_limiter import RateLimiterMiddleware
from middleware.auth import APIKeyAuthMiddleware
from middleware.request_logger import RequestLoggerMiddleware
from middleware.anomaly_detector import AnomalyDetectorMiddleware

app = FastAPI()

# 添加中间件（顺序很重要！）
app.add_middleware(RateLimiterMiddleware, requests_per_minute=100)
app.add_middleware(APIKeyAuthMiddleware, require_auth=False)
app.add_middleware(RequestLoggerMiddleware)
app.add_middleware(AnomalyDetectorMiddleware)
```

### 监控 API 状态

```bash
# 获取速率限制统计
curl http://localhost:3020/api/monitor/rate-limit

# 获取认证统计
curl http://localhost:3020/api/monitor/auth

# 获取安全告警
curl http://localhost:3020/api/monitor/alerts

# 获取整体安全统计
curl http://localhost:3020/api/monitor/security/stats
```

### 使用 API Key 访问

```bash
# 方式 1: Header
curl -H "X-API-Key: dashboard-key-001" http://localhost:3020/api/agents

# 方式 2: Bearer Token
curl -H "Authorization: Bearer dashboard-key-001" http://localhost:3020/api/agents

# 方式 3: Query Parameter
curl "http://localhost:3020/api/agents?api_key=dashboard-key-001"
```

---

## 环境变量配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `RATE_LIMIT_REQUESTS` | 100 | 每分钟请求限制 |
| `API_KEYS` | dashboard-key-001,... | API Keys 列表 |
| `AUTH_REQUIRED` | false | 是否强制认证 |
| `LOG_FILE_PATH` | request_logs.jsonl | 日志文件路径 |
| `ALERT_FAILED_AUTH` | 5 | 失败认证告警阈值 |
| `ALERT_WEBHOOK_URL` | - | 告警 Webhook URL |

---

## 生产环境建议

1. **使用 Redis 存储**: 将速率限制数据从内存迁移到 Redis，支持多实例部署
2. **HTTPS**: 始终使用 HTTPS 传输 API Key
3. **定期轮换 Keys**: 定期更换 API Keys
4. **日志轮转**: 配置日志轮转防止文件过大
5. **告警集成**: 配置 Slack/钉钉/邮件告警
6. **IP 白名单**: 为内部管理 API 配置 IP 白名单

---

## 开发者

- 李奥纳多 (Leonardo) - 架构师
- 创建时间：2026-04-01
- 版本：1.0.0
