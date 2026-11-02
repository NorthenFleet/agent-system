# 集群资产与只读监控（阶段一、二）

## 范围与权威边界

3021 是统一展示入口。`cluster_nodes` 保存物理节点身份与人工登记用途，
`cluster_discovery` 保存网络发现的新鲜度，`cluster_telemetry` 保存最近成功的
硬件样本及最近采集错误。业务事实仍归各产品；One-Sim 的训练调度不在本阶段变更。

`backend/config/cluster_nodes.json` 仅为显式登记种子和受控采集配置，不是可并行
编辑的第二份运行时资产库。`run_cluster_monitor.py --register` 显式登记后，HTTP
GET 不做发现、不探测、不登记。旧 `/api/devices` 保持兼容，监控页折叠显示。

稳定身份采用 `node_id` + 唯一 `tailscale_id`，不得通过同名或同 IP 自动合并。
Tailscale 重装导致身份变化时，必须重新核验，不能自动接管旧节点的角色或凭据。
未纳管的历史 peer 仅展示网络观测，不执行任何 SSH/HTTP 探针。

## 状态定义

- 网络在线不等于采集器可用，更不等于业务健康或可调度。
- 网络、硬件和服务分别计时，超过 90 秒降级；未来时间不视为新鲜。
- 从可见 peer 列表消失只能判定未知，不能断言关机。
- 采集失败保留最近成功样本和原时间，显示失败；缺失值为 null，不补零。
- 服务健康需命中明确的 JSON 健康契约；401/403、重定向和登录页不能冒充健康。
- macOS 内存百分比是 top 的物理已用占比，并非内存压力或可分配容量；Linux
  可用内存来自 MemAvailable。Apple GPU/NVIDIA 指标不可互相推断。
- GPU 探针不可用时显示未采集；Docker 查询失败只表示未知，不断言没有安装。
- 本阶段所有节点 `scheduling.eligible=false`，不存在执行任务或部署按钮/API。

## 凭据与探测

独立进程每轮读取 Tailscale JSON，仅对种子中受管且身份匹配的在线节点执行固定
探针。SSH 禁用交互密码、代理转发及用户配置；启用 `IdentitiesOnly` 和严格主机
密钥验证。Linux/macOS 执行固定 Python stdin 脚本，Windows 执行固定 PowerShell
编码脚本。没有接受用户命令、远端 hostname 命令片段或任意 URL 的接口。

`prepare_cluster_known_hosts.py` 只复制 Mac mini 现有 known_hosts 中已信任的
登记节点条目，以 0600 独占创建专用文件；不会执行 ssh-keyscan 或接受新密钥。
阶段二沿用已有运维密钥（credential_scope=existing_operator_key，
least_privilege=deferred），不复制私钥、不增加 authorized_keys、不启用 Windows
SSH 服务。专用最小权限采集身份的发放需另行确认；现有密钥权限边界仍是残余风险。

## 数据库发布门

已核验的 3021 主数据库为 `backend/data/dashboard_v2.db`，全局 Alembic 版本
`41670c742a60`，不能为本阶段运行 `alembic upgrade head` 或 `stamp head`。
迁移唯一源是 `20260925_cluster_inventory.py`，仍保持正常迁移链前驱。

对这个旧 SQLite 部署使用 `scripts/apply_cluster_inventory_schema.py`：

1. 校验预期全局 revision；取得 `BEGIN IMMEDIATE` 写保留锁冻结其他写入，再用
   独立只读连接的 SQLite backup API 创建一致备份并校验完整性。
2. 在同一显式事务/写锁内通过 Alembic Operations 仅调用本次迁移，再次调用复验。
3. 断言所有非 cluster 表/索引的 schema 及全局 revision 不变。
4. 重复应用时严格验证字段类型、非空、主外键、check 和唯一索引后 no-op。

必须先完成迁移再加载新应用代码，避免既有 SQLite 启动 create_all 绕过迁移记录。
将来正式升级完整迁移链时，相同 migration 验证既有结构并正常推进全局版本。
不要把“已单独应用 cluster 迁移”描述为“完整数据库已升级到最新”。

## 独立采集进程

使用 `backend/ai.openclaw.cluster-monitor.plist`，固定工作目录、数据库、Tailscale
路径和专用 known_hosts。先运行 `--register` 和 `--once` 检查回执，再交给 launchd。
macOS Tailscale App 可执行文件根据环境选择 GUI/CLI 模式，因此 plist 显式设置
官方脚本选项 `TAILSCALE_BE_CLI=1`；不能只以 SSH 终端里的单次成功替代 launchd
常驻验收。参见 [Tailscale CLI 文档](https://tailscale.com/docs/reference/tailscale-cli?tab=macos)。
`fcntl.flock` 保证单实例；不在 FastAPI lifespan 中重复启动采集循环。
日志仅记录轮次结果/计数/错误类别，不记录凭据、进程 stderr 或任意业务响应体。

## 验证与回退

隔离目录验证：

```bash
PYTHONPATH=. python -m pytest tests/test_cluster_inventory.py tests/test_cluster_readonly_collector.py tests/test_cluster_additive_rollout.py tests/test_monitoring_heartbeat_freshness.py -q
npm run test:run -- ClusterMonitoringPanel
npm run build
```

上线验收需要：七台登记节点不重复、历史 peer 分区、90 秒过期降级、未认证 API
拒绝、真实采集回执与页面一致、启动管理恢复后继续采集。没有取得 SSH 访问条件
或角色确认的节点保持待确认/采集失败，不得宣称全部硬件已经纳管验收通过。

回退优先停用本次独立采集进程，恢复备份代码和前端入口，再重启 3021；保留新增
三张表不影响旧代码。不要直接用旧整库备份覆盖仍有业务写入的数据库；整库恢复
只用于明确停机并核对之后的灾难恢复。不要清理其他服务、旧节点或无关工作区改动。
