# 记忆生产闭环阶段 A 验收记录

> 阶段：A — 诊断一致性与基线冻结  
> 完成日期：2026-09-20  
> 结论：通过  
> 线上排序影响：无，仍为 `shadow` / `score-sort-baseline`

## 1. 完成内容

1. 新增共享运行配置诊断模块：
   - 统一生成向量、Embedding、融合策略和图谱配置摘要；
   - 对数据库和 HTTP 目标进行脱敏；
   - 不读取或输出密码、HMAC 密钥、JWT 密钥；
   - 基于非敏感有效配置生成稳定 SHA-256 指纹。
2. 扩展向量预检：
   - 保留并强化 `--env-file`；
   - 新增 `--require-config-source`；
   - 输出配置来源、配置指纹和运行环境；
   - 将执行环境权限限制标记为 `environment_restricted`；
   - 将真实依赖不可用标记为 `dependency_unavailable`。
3. 扩展 3021 健康信息：
   - 公共 `/health` 只返回精简、无敏感信息的运行配置摘要；
   - 管理员接口 `/api/v2/monitoring/memory-system/configuration` 返回完整脱敏摘要。
4. 统一启动来源标识：
   - launchd 标记 `AGENT_SYSTEM_RUNTIME_KIND=launchd`；
   - launchd 在声明的 `.env` 缺失或不可读时以状态码 78 拒绝启动；
   - `start.sh` 标记 `AGENT_SYSTEM_RUNTIME_KIND=manual`；
   - 两种方式均声明 `AGENT_SYSTEM_ENV_FILE`；
   - `start.sh` 严格预检要求配置来源有效。
5. 重载并重启 `ai.openclaw.agent-system-3021`，新配置已进入运行进程。

## 2. 配置一致性证据

### CLI 严格预检

在具备本机访问权限的环境执行：

```bash
backend/venv/bin/python \
  backend/scripts/memory_vector_preflight.py \
  --env-file .env \
  --probe-embedding \
  --require-infrastructure \
  --require-config-source
```

结果：

- `status=ready`；
- `infrastructure_ready=true`；
- `ready_for_vector_rollout=true`；
- PostgreSQL、pgvector、投影表、Ollama、Embedding 维度和队列全部通过；
- 配置指纹：`sha256:4a98f110fa7eaa41a65c218a78beb402e9efd3d4843c5e97a7d271e82bcdaa18`。

### 3021 运行进程

重启后的 `/health` 返回：

```json
{
  "status": "ok",
  "port": 3021,
  "memory_runtime": {
    "schema_version": "memory-runtime-config.v1",
    "runtime_kind": "launchd",
    "configuration_source": "declared_env_file",
    "env_file_status": "present",
    "configuration_fingerprint": "sha256:4a98f110fa7eaa41a65c218a78beb402e9efd3d4843c5e97a7d271e82bcdaa18",
    "vector_enabled": true,
    "embedding_model": "nomic-embed-text:v1.5",
    "embedding_dimension": 768,
    "fusion_mode": "shadow",
    "graph_enabled": true,
    "graph_default_mode": "rerank"
  }
}
```

CLI 与 launchd 指纹完全一致，证明二者使用同一套有效记忆配置。

## 3. 误报消除验证

在受限沙箱中执行同一预检：

- `.env` 正确加载；
- 配置来源有效；
- 配置指纹与真实环境一致；
- PostgreSQL 和 Ollama 探测失败均返回 `reason_code=environment_restricted`；
- 不再把受限环境的 `Operation not permitted` 解释为基础设施未安装或配置缺失。

测试同时覆盖：

- 缺少 `.env` 且没有进程环境配置时，`configuration_source_valid=false`；
- 数据库密码变化不会进入配置指纹，也不会出现在输出中；
- Graph Memory URL 中的凭证不会出现在输出中；
- 融合模式等有效非敏感配置变化会改变指纹。

## 4. 质量验证

### 静态检查

- `python -m py_compile`：通过；
- `bash -n start.sh`：通过；
- `plutil -lint backend/ai.openclaw.agent-system-3021.plist`：通过；
- `git diff --check`：通过。

### 自动化回归

定向测试：15 项通过。

扩大后的记忆与上下文相关回归：

```text
49 passed, 0 failed
```

覆盖：

- 运行配置脱敏与指纹；
- 向量预检；
- 监控接口；
- Context Retrieval；
- Memory Retrieval；
- Context API；
- 记忆访问控制。

现有警告为 SQLAlchemy、Pydantic 和 FastAPI 生命周期 API 的弃用提示，与本阶段变更无关。

## 5. 变更文件

- `backend/services/memory_runtime_config.py`
- `backend/scripts/memory_vector_preflight.py`
- `backend/routers/monitoring_router.py`
- `backend/main_slim_v2.py`
- `backend/ai.openclaw.agent-system-3021.plist`
- `start.sh`
- `backend/tests/test_memory_runtime_config.py`
- `backend/tests/test_memory_vector_preflight.py`
- `backend/tests/test_memory_system_health_status.py`

## 6. 阶段验收

| 条件 | 结果 |
| --- | --- |
| launchd、CLI 使用同一配置 | 通过，指纹一致 |
| 受限环境错误不再误报依赖故障 | 通过 |
| 缺失配置来源可明确阻断 | 通过 |
| 健康端点暴露脱敏有效配置 | 通过 |
| 敏感信息不进入响应和指纹 | 通过 |
| 线上检索排序未改变 | 通过，仍为 `shadow` |
| 服务重启后健康 | 通过 |

阶段 A 完成。下一步进入阶段 B：权威记忆、生命周期账本、pgvector 与 Graph Memory 的统一对账和退役演练。
