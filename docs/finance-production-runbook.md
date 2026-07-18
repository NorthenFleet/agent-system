# 财务管理系统生产运行手册

## 部署门槛

1. 对 SQLite、WAL 和 Obsidian 财务目录执行 `backend/scripts/backup_finance.sh`。
2. 配置 PostgreSQL TLS 连接、最小权限数据库用户和私有 S3/MinIO 桶。
3. 执行 `alembic upgrade head`；`/health/ready` 必须返回 `ready`。
4. 先以 `POST /api/finance/imports` 的 `dry_run=true` 核对旧库统计，再执行正式导入。
5. 影子读取期间按项目、状态、数量和金额核对；禁止双写 SQLite 与 PostgreSQL。
6. 切换后运行 1000 次刷新：`python backend/scripts/finance_fd_stability.py`。

## 回滚

应用回滚仅切换读取入口和旧版本应用，SQLite 保持只读；不得把 PostgreSQL 新数据反写旧库。数据库迁移降级前必须完成快照并在恢复演练环境验证。

## 备份与恢复

- 每日全量备份，WAL 连续归档并至少每 15 分钟确认归档延迟。
- 默认目标为 RPO 15 分钟、RTO 2 小时。
- 每季度在隔离环境恢复 PostgreSQL 与对象存储，校验核心表数量、项目金额、孤立明细和附件哈希。

## 监控

采集进程文件描述符、数据库池使用率/等待时间、HTTP P95、慢查询、后台导入任务、OCR/验真成功率、审批积压、对账差异和对象存储错误。日志禁止输出 Token、完整卡号、身份证号和附件正文。

## 权限

财务角色由 `finance_user_roles` 管理，项目范围由 `finance_project_memberships` 管理。`finance_admin` 不能修改已付款记录；`auditor` 全局只读；申请、审批和付款执行岗位分离。
