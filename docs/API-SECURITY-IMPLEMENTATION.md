# 🔒 API 限流与安全认证机制实现报告

**作者**: 李奥纳多 (Leonardo) - 架构师  
**完成时间**: 2026-04-01  
**截止时间**: 2026-04-02 18:00  
**状态**: ✅ 已完成

---

## 📋 任务概述

为团队状态看板 API 实现完整的安全防护机制，包括：
1. 速率限制中间件 (100 次/分钟/IP)
2. API Key 认证机制
3. 请求日志记录
4. 异常访问告警

---

## ✅ 实现内容

### 1. 速率限制中间件

**文件**: `backend/middleware/rate_limiter.py`

**核心功能**:
- 基于 IP 的请求频率限制
- 滑动窗口算法实现
- 100 次请求/分钟/IP
- 支持 X-Forwarded-For 头（代理场景）

**技术实现**:
```python
class RateLimiterMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, requests_per_minute: int = 100):
        self.request_history: Dict[str, List[float]] = defaultdict(list)
```

**响应头**:
- `X-RateLimit-Limit`: 总限制数
- `X-RateLimit-Remaining`: 剩余请求数
- `Retry-After`: 重试时间（触发限制时）

**限流响应**:
```json
{
  "error": "Too Many Requests",
  "detail": "Rate limit exceeded. Maximum 100 requests per minute.",
  "retry_after": 60
}
```

---

### 2. API Key 认证机制

**文件**: `backend/middleware/auth.py`

**支持的认证方式**:
1. `X-API-Key` Header
2. `Authorization: Bearer <token>`
3. Query Parameter: `?api_key=<key>`

**默认 API Keys**:
- `dashboard-key-001` - 标准权限
- `dashboard-key-002` - 标准权限
- `admin-key-master` - 管理员权限

**认证流程**:
```
请求 → 提取 API Key → 验证 → 通过/拒绝
         ↓
    记录统计信息
```

**认证失败响应**:
```json
{
  "error": "Unauthorized",
  "detail": "Invalid API Key"
}
```

---

### 3. 请求日志记录

**文件**: `backend/middleware/request_logger.py`

**记录内容**:
- 请求方法、路径、查询参数
- 客户端 IP、User-Agent、Referer
- 响应状态码、响应大小
- 请求耗时（毫秒）
- API Key（脱敏显示）
- 是否被限流

**日志格式** (JSONL):
```json
{
  "timestamp": "2026-04-01T20:00:00",
  "method": "GET",
  "path": "/api/agents",
  "client": {"ip": "192.168.1.1", "user_agent": "..."},
  "status_code": 200,
  "duration_ms": 45.23,
  "api_key": "dashboar..."
}
```

**统计信息**:
- 总请求数
- 平均响应时间
- 慢请求数 (>1000ms)
- 错误请求数 (4xx/5xx)

---

### 4. 异常访问告警

**文件**: `backend/middleware/anomaly_detector.py`

**检测类型**:

| 告警类型 | 触发条件 | 严重级别 |
|---------|---------|---------|
| FAILED_AUTH_THRESHOLD | 5 次认证失败/5 分钟 | HIGH |
| PATH_PROBING | 探测 3+ 敏感路径 | MEDIUM |
| ABNORMAL_REQUEST_RATE | >200 次请求/分钟 | HIGH |
| IP_BLOCKED | 手动封禁 | CRITICAL |

**敏感路径列表**:
- `/admin`, `/api/admin`
- `/.env`, `/.git`
- `/config`, `/backup`
- `/debug`, `/test`
- `/phpmyadmin`, `/wp-admin`

**告警输出**:
- 控制台打印（带 emoji）
- 文件记录：`security_alerts.jsonl`
- 支持 Webhook 扩展

---

## 📊 监控 API

### 速率限制监控
```bash
GET /api/monitor/rate-limit
```

### 认证统计
```bash
GET /api/monitor/auth
```

### 请求日志查询
```bash
GET /api/monitor/logs?limit=100
```

### 安全告警查询
```bash
GET /api/monitor/alerts?limit=50
```

### 整体安全统计
```bash
GET /api/monitor/security/stats
```

**响应示例**:
```json
{
  "rate_limiting": {
    "active_ips": 5,
    "total_requests_last_minute": 45,
    "rate_limited_ips_count": 0
  },
  "authentication": {
    "total_requests": 100,
    "authenticated_requests": 95,
    "failed_auth_attempts": 5
  },
  "anomaly_detection": {
    "total_alerts": 2,
    "alerts_by_type": {"PATH_PROBING": 1, "FAILED_AUTH_THRESHOLD": 1}
  }
}
```

### IP 管理
```bash
# 封禁 IP
POST /api/admin/security/block-ip?ip=1.2.3.4&reason=Suspicious+activity

# 解除封禁
POST /api/admin/security/unblock-ip?ip=1.2.3.4
```

---

## 🔧 配置说明

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `RATE_LIMIT_REQUESTS` | 100 | 每分钟请求限制 |
| `API_KEYS` | dashboard-key-001,... | API Keys 列表 |
| `AUTH_REQUIRED` | false | 强制认证 |
| `LOG_FILE_PATH` | request_logs.jsonl | 日志路径 |
| `ALERT_FAILED_AUTH` | 5 | 失败认证阈值 |
| `ALERT_WEBHOOK_URL` | - | 告警 Webhook |

### 使用 .env 文件

```bash
# 复制示例配置
cp .env.example .env

# 编辑配置
vim .env
```

---

## 🧪 测试方法

### 1. 启动服务器
```bash
cd /Users/apple/WorkSpace/team-dashboard/backend
python main.py
```

### 2. 运行自动化测试
```bash
python test_middleware.py
```

### 3. 手动测试

**测试速率限制**:
```bash
# 快速发送 110 个请求
for i in {1..110}; do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -H "X-API-Key: dashboard-key-001" \
    http://localhost:3020/api/agents
done
```

**测试认证**:
```bash
# 有效 Key
curl -H "X-API-Key: dashboard-key-001" http://localhost:3020/api/agents

# 无效 Key
curl -H "X-API-Key: invalid" http://localhost:3020/api/agents

# 无 Key
curl http://localhost:3020/api/agents
```

**测试路径探测告警**:
```bash
# 探测敏感路径
curl http://localhost:3020/admin
curl http://localhost:3020/.env
curl http://localhost:3020/.git/config

# 查看告警
curl http://localhost:3020/api/monitor/alerts
```

---

## 📁 文件结构

```
backend/
├── main.py                    # 主应用（已更新）
├── security_config.py         # 安全配置模块
├── requirements.txt           # 依赖（已更新）
├── .env.example              # 环境变量示例
├── test_middleware.py         # 测试脚本
├── middleware/
│   ├── __init__.py           # 包初始化
│   ├── rate_limiter.py       # 速率限制
│   ├── auth.py               # API Key 认证
│   ├── request_logger.py     # 请求日志
│   ├── anomaly_detector.py   # 异常检测
│   └── README.md             # 中间件文档
└── logs/
    ├── request_logs.jsonl    # 请求日志（运行时生成）
    └── security_alerts.jsonl # 安全告警（运行时生成）
```

---

## 🚀 生产环境建议

### 1. 使用 Redis 存储
当前使用内存存储，生产环境建议迁移到 Redis：
```python
import redis
r = redis.Redis(host='localhost', port=6379)
r.setex(f"rate_limit:{ip}", 60, request_count)
```

### 2. HTTPS 加密
- 始终使用 HTTPS 传输 API Key
- 配置 SSL 证书
- 启用 HSTS

### 3. 密钥管理
- 定期轮换 API Keys
- 使用环境变量或密钥管理服务
- 不要将密钥提交到版本控制

### 4. 日志管理
- 配置日志轮转（logrotate）
- 设置日志保留策略
- 敏感信息脱敏

### 5. 告警集成
- Slack Webhook
- 钉钉机器人
- 邮件通知
- PagerDuty

### 6. IP 白名单
为内部管理 API 配置 IP 白名单：
```python
ALLOWED_IPS = {"192.168.1.100", "10.0.0.50"}
```

---

## 📝 后续优化

- [ ] Redis 存储支持（多实例部署）
- [ ] JWT Token 认证
- [ ] 设备绑定机制
- [ ] 会话管理
- [ ] 告警渠道集成（Slack/钉钉/邮件）
- [ ] 可视化监控面板
- [ ] 自动封禁策略

---

## ✅ 验收清单

- [x] 速率限制中间件实现（100 次/分钟/IP）
- [x] API Key 认证机制（3 种认证方式）
- [x] 请求日志记录（JSONL 格式）
- [x] 异常访问告警（4 种检测类型）
- [x] 监控 API 实现（7 个端点）
- [x] 配置文件和文档
- [x] 测试脚本
- [x] 任务文档更新

---

**交付时间**: 2026-04-01 20:00  
**提前完成**: ✅ 比截止时间提前 22 小时

---

*李奥纳多 - 架构师 🟦*
