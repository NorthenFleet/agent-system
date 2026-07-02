# CI 集成检查报告 — 项目 C（情报资讯真实数据联调准备）

> **作者**: 拉斐尔 (raphael)  
> **日期**: 2026-07-02  
> **任务**: task-007 项目 C 真实数据联调后端接口确认  

---

## 一、代理接口代码审查 ✅

情报资讯代理接口代码**已完整实现**，位于 MacBook Pro 上的 `one-sim` 项目：

```
~/工作桌面/Workspace/one-sim/backend/api/v2/intelligence/
├── __init__.py
├── config.py              # 配置 (pydantic-settings + env)
├── router.py              # FastAPI Router (prefix=/intelligence)
├── redroom_client.py      # 简化版 tRPC 客户端（单文件实现）
├── schemas.py             # Pydantic 响应模型
├── schemas/
│   ├── article.py
│   └── category.py
├── endpoints/
│   ├── articles.py        # GET /articles + GET /articles/{id}
│   └── categories.py      # GET /categories
└── services/
    ├── redroom_client.py  # 完整版 tRPC 客户端（支持 batch + 重试）
    └── cache.py           # LRU + Redis 双层缓存
```

### 已实现端点

| 端点 | 文件 | 状态 |
|------|------|------|
| `GET /api/v2/intelligence/articles` | `endpoints/articles.py` | ✅ |
| `GET /api/v2/intelligence/articles/{id}` | `endpoints/articles.py` | ✅ |
| `GET /api/v2/intelligence/categories` | `endpoints/categories.py` | ✅ |

---

## 二、路由注册检查 ⚠️

**关键发现**: 代理接口代码已存在，但**尚未注册到 main.py 入口**。

### 当前 main.py（本机 team-dashboard）
- 本机 `main.py`（slim 版，<100行）**没有**引入 intelligence 模块
- 本机 routers 目录**没有** intelligence 相关文件
- 本机 backend 目录下**没有** intelligence 相关代码

### 远程 one-sim（MacBook Pro 192.168.31.144）
- intelligence 模块代码已完整
- **但项目没有 main.py** — 只有 `api/v2/` 目录结构
- 意味着 **one-sim 服务可能尚未启动**，或入口文件在其他位置

### 结论
⚠️ **代理接口未注册到任何运行中的 FastAPI 服务。**  
代码就绪，但路由不可访问。需要确认：
1. one-sim 服务是否正在运行？入口文件是什么？
2. intelligence router 是否已被导入 main 入口？

---

## 三、tRPC 代理端点验证 ⏳

代码实现已就绪，包含：
- `RedroomClient` 两个版本（简化版 + 完整版）
- 完整版支持：
  - 单过程 POST 调用
  - 批量调用 (`batch_query`)
  - 自动重试（指数退避）
  - tRPC 错误 → HTTP 状态码转换
  - API Key / Bearer Token / Cookie 认证支持

**⏳ 需要启动服务后测试** — 当前无法确认 `/api/trpc/*` 能否正常转发。

待验证项：
- Redroom 实际服务地址（config 默认 `localhost:3000`，需确认远程值）
- 环境变量 `intelligence_redroom_base_url` 的实际配置值
- Redroom tRPC 路由名称是否与代码假设匹配（`articles.list`, `articles.getById`, `categories.list`）

---

## 四、缓存配置检查 ✅（代码就绪）

`services/cache.py` 实现了完整的双层缓存：

| 层级 | 实现 | 容量/TTL |
|------|------|----------|
| L1: LRU | 内存 OrderedDict | max 256 条，TTL 可配置 |
| L2: Redis | `redis.asyncio` | 可选，自动降级 |

缓存 TTL 配置（`config.py`）：
- 文章列表：300s（5min）
- 文章详情：1800s（30min）  
- 分类列表：3600s（1h）

**⚠️ 环境变量 `intelligence_redis_url` 未配置时自动降级为纯 LRU**，这是正确的回退策略。

---

## 五、前端切换指引

### 5.1 前端已完成的切换

根据 queue.json 记录，多纳泰罗已完成：
- ✅ `src/api/intelligence.js` — 创建真实接口调用模块
- ✅ `Intelligence.vue` + `IntelligenceDetail.vue` — 从 mock 切换到真实 API

### 5.2 前端调用的端点

```javascript
// src/api/intelligence.js
GET  /api/v2/intelligence/articles?page=&page_size=&category_id=&keyword=
GET  /api/v2/intelligence/articles/{id}
GET  /api/v2/intelligence/categories
```

### 5.3 响应格式

```json
// 列表响应
{ "code": 0, "data": { "items": [...], "pagination": { "page", "page_size", "total", "total_pages" } } }

// 详情响应
{ "code": 0, "data": { "id", "title", "content", "content_type", "category", "author", "created_at", ... } }

// 分类响应
{ "code": 0, "data": [{ "id", "name", "parent_id", "article_count" }, ...] }
```

### 5.4 前端已处理降级

`intelligence.js` 实现：超时降级到 mock 数据，返回格式统一。

---

## 六、阻塞项与下一步

### 当前阻塞
| 阻塞项 | 状态 | 需要 |
|--------|------|------|
| 代理接口未注册到运行中的服务 | 🔴 阻塞 | 确认 one-sim 入口 + 注册 router |
| Redroom 实际地址未知 | 🟡 待确认 | 环境变量配置 |
| tRPC 路由名称需验证 | 🟡 待确认 | 通过 DevTools 抓取或访问 Redroom |

### 建议下一步
1. **确认 one-sim 服务入口** — 在 MacBook Pro 上找到启动脚本或 main 文件
2. **注册 intelligence router** — 在 main.py 中 `include_router`
3. **启动服务** — 确保端口可访问
4. **端到端测试** — 用 curl 验证三个端点能返回数据
5. **通知米开朗基罗** — 后端就绪后可开始 CI-007 全链路测试

---

## 七、总结

| 检查项 | 结果 |
|--------|------|
| 代码完整性 | ✅ 代理接口代码完整 |
| 路由注册 | ⚠️ 未注册到运行中的服务 |
| tRPC 代理 | ⏳ 需启动后验证 |
| 双层缓存 | ✅ LRU+Redis 实现完整 |
| 前端对接 | ✅ 前端已切换到真实 API 端点 |
| 联调就绪度 | 🔴 需先解决路由注册和服务启动 |

---

*报告由拉斐尔生成，待擎天柱指示下一步行动。*
