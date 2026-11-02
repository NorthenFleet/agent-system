# 阶段一、二部署与验收记录

日期：2026-09-25（Asia/Shanghai）。本记录是此次发布回执，不代替实时监控。

## 结论与范围

资产登记、只读监控及页面基础功能已发布到 Mac mini 的现有 3021 服务。
七台目标节点已登记，三台取得持续硬件采集回执；全节点硬件接入尚未验收完成。
没有新增任务调度/任意远程命令接口，没有修改 One-Sim 的调度、Windows SSH、
Tailscale 网络策略、节点 authorized_keys 或其他业务工作进程。

入口：http://100.81.208.50:3021/monitoring

代码库：`/Users/apple/工作桌面/Workspace/agent-system`。
基线提交：`bb41970`；本次改动尚未 commit/push。原有未跟踪文档
`docs/SYSTEM-CLOSURE-MASTER-PLAN.md` 保留。

## 节点结果

| 稳定节点 ID | Tailscale IPv4 | 当前验收结果 | 剩余条件 |
|---|---|---|---|
| mac-mini-01 | 100.81.208.50 | 网络在线，硬件持续采集，3021 健康探测通过 | Apple GPU 指标未采集 |
| macbook-pro-01 | 100.69.152.73 | 网络在线，硬件持续采集 | Docker 查询未取得结果，不等于未安装 |
| compute-05 | 100.91.246.95 | 网络在线，104 逻辑 CPU、约 125.4 GiB 内存、2 张 RTX 3090、Docker 29.5.3 | 未登记其他业务服务探针 |
| compute-04 | 100.73.142.95 | 网络在线，硬件采集失败 | Mac mini 的现有 SSH 密钥未通过该节点认证 |
| simulation-01 | 100.108.76.114 | 网络在线，身份待确认，采集未配置 | 确认仿真角色、登录账户和主机密钥 |
| yoga-01 | 100.126.39.39 | 网络在线，身份待确认，采集未配置 | 确认 Yoga 对应关系及 SSH 访问条件；此前端口探测超时 |
| public-windows-01 | 100.123.114.16 | 网络在线，身份待确认，采集未配置 | 确认对外 Windows 对应关系及访问方式；此前 SSH 端口拒绝连接 |

另有七台未纳管/历史 peer 单独折叠显示，不执行 SSH/HTTP 探针。不会用 IP/主机名
自动合并身份；重装 Tailscale 后需重新核验稳定 ID。全部节点明确不可调度。

## 主要交付

- `backend/models/cluster_inventory.py`、`services/cluster_inventory_service.py`：
  唯一节点身份、发现/硬件/服务独立时间戳、90 秒过期、缺失不补零。
- `backend/routers/cluster_inventory_router.py`：复用现有鉴权的只读快照 API。
- `backend/services/cluster_collector.py`、`scripts/run_cluster_monitor.py`：
  独立受控探针、严格 SSH 主机密钥、单实例锁、失败隔离。
- `backend/ai.openclaw.cluster-monitor.plist`：现有 apple GUI 会话的 LaunchAgent。
  已验证重启恢复；未实际重启整机，未宣称登录前的系统级常驻保障。
- `frontend-v2/src/components/monitoring/ClusterMonitoringPanel.vue`：新集群面板，
  旧设备区保留兼容；网络、采集、服务、身份分开显示，请求失败保留陈旧快照。
- 既有心跳过期修复：过期设备不能再被 `busy` 字段覆盖成在线。

## 验证证据

隔离副本目录：`/private/tmp/agent-system-cluster-20260925`；Python 使用生产现有
`backend/venv/bin/python`。测试通过不代表执行了整个仓库测试套件。

```bash
# 在隔离副本 backend 目录，最终结果：51 passed，7 条既有弃用警告
PYTHONPATH=. /Users/apple/工作桌面/Workspace/agent-system/backend/venv/bin/python -m pytest tests/test_monitoring_heartbeat_freshness.py tests/test_cluster_readonly_collector.py tests/test_cluster_inventory.py tests/test_cluster_additive_rollout.py tests/test_monitoring_api.py -q --disable-warnings

# 在隔离副本 frontend-v2 目录，结果：7 passed
PATH=/opt/homebrew/bin:$PATH npm run test:run -- ClusterMonitoringPanel

# Vue 类型检查及 Vite 构建成功，2988 modules；仍有既有大 chunk 警告
PATH=/opt/homebrew/bin:$PATH npm run build
```

- 生产 API：带现有开发会话的浏览器请求 HTTP 200；无凭据请求 HTTP 401。
- Playwright 实际访问生产页面（经临时本机 SSH 隧道），核对七张目标卡片、
  七台历史节点、明确的失败原因和调度禁用；控制台 0 error。
- 后台连续回执：发现时间从 `2026-09-25T05:21:32.445095Z` 前进到
  `05:22:10.205879Z`；两轮均 `discovery=fresh, collected=3`。
- 只重启 collector 后，发现时间前进到 `05:22:33.762946Z`，三台硬件样本均
  更新；3021 及原 command-center worker 未因此次恢复测试重启。
- 发布清单内 25 个源码/测试/配置/文档逐一与隔离验收副本 `cmp` 相同；
  生产 `git diff --check` 通过。本验收文档为额外第 26 个交付文件。

实际常驻验收发现 Tailscale macOS App 在无终端环境误入 GUI 模式，已增加回归
测试并采用官方 `TAILSCALE_BE_CLI=1` 修复；未切换 Tailscale 安装方式。
依据：[Tailscale CLI](https://tailscale.com/docs/reference/tailscale-cli?tab=macos)。

截图保存在操作端：
`/Users/sunyi/工作桌面/WorkSpace/one-sim/output/playwright/cluster-phase12-20260925.png`。

## 数据与回退

SQLite 全局 Alembic revision 保持 `41670c742a60`。仅通过受写锁保护的窄迁移
添加三张 cluster 表，未运行全链升级或 stamp。生产发布前备份目录：

`/Users/apple/工作桌面/Workspace/agent-system/backend/data/cluster-phase12-pgJTI9`

其中 `database-before.db` 为一致性数据库备份，`source-and-ui.tgz` 为原有改动
文件及前端构建备份。前端旧哈希资源保留。

优先回退流程见 `CLUSTER-MONITORING-PHASE12.md`：停本次 collector、恢复代码及
前端入口、重启 3021；新增表可保留。禁止把旧整库备份直接覆盖持续写入的生产库。

## 剩余风险与下一步

1. 四台硬件采集未闭环；三台角色身份还需用户确认。不得用“网络在线”代替验收。
2. 沿用现有运维 SSH 密钥，专用最小权限采集身份尚未发放；未擅自扩大权限。
3. 3021 仍沿用原 `login_enabled=false, mode=development` 设置，前端可取得开发
   会话。HTTP 401 仅证明无 token 路由拒绝，不代表正式生产登录已启用；公网开放
   前需另行完成正式认证、权限及访问范围收紧。
4. macOS 的内存百分比为物理已用占比，不是内存压力/可分配容量；Apple GPU 及
   不可得指标保持未采集。日志轮转与更多业务服务健康探针留作后续小阶段。

下一步先补齐上述身份和采集访问条件，达到七台回执验收，再进入调度/执行阶段。
