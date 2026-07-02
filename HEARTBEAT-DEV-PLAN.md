# 开发计划模块 - 定时任务配置

## 心跳检查配置

将以下内容添加到 `HEARTBEAT.md`:

### 定期检查项

```markdown
## 📋 开发计划与分工检查

**频率**: 每 4 小时

**检查内容**:
- [ ] 扫描空闲智能体
- [ ] 生成开发计划建议
- [ ] 标记高优先级 (空闲>24h)
- [ ] 记录分配历史

**API 检查**:
```bash
# 空闲统计
curl -s http://localhost:3020/api/idle-agents/stats | jq .

# 开发计划
curl -s http://localhost:3020/api/development-plans | jq '.total'
```

**告警阈值**:
- 空闲率 > 50%: 提醒任务不足
- 空闲率 < 10%: 团队负载正常
- 单个智能体空闲 > 48h: 高优先级告警
```

## Cron 配置 (可选)

如需精确时间控制，可添加 cron 任务:

```bash
# 每 4 小时检查一次 (9:00, 13:00, 17:00, 21:00)
0 9,13,17,21 * * * curl http://localhost:3020/api/idle-agents/stats >> ~/WorkSpace/team-dashboard/logs/idle-check.log 2>&1

# 每日生成报告 (8:00)
0 8 * * * curl http://localhost:3020/api/development-plans > ~/WorkSpace/team-dashboard/logs/daily-plans.json 2>&1
```

## 监控指标

### 关键指标

| 指标 | 健康范围 | 告警阈值 |
|------|----------|----------|
| 空闲率 | 10-30% | >50% |
| 平均空闲时长 | <4 小时 | >24 小时 |
| 计划生成数 | >0 | =0 (有任务时) |
| 分配成功率 | >80% | <50% |

### 日志位置

- 空闲检测日志：`backend/data/idle_agent_state.json`
- 分配历史：同上文件 `assignment_history` 字段
- API 访问日志：`backend/backend.log`

## 手动触发

```bash
# 查看当前空闲智能体
curl http://localhost:3020/api/idle-agents | jq .

# 查看开发计划
curl http://localhost:3020/api/development-plans | jq .

# 查看分配历史
curl http://localhost:3020/api/assignment-history | jq .
```

## 故障排查

### 问题：开发计划为空

**可能原因**:
1. 没有空闲智能体
2. 没有待分配任务
3. 匹配算法问题

**解决步骤**:
```bash
# 1. 检查智能体状态
curl http://localhost:3020/api/agents | jq '.agents[] | {id, status, current_task}'

# 2. 检查任务列表
curl http://localhost:3020/api/tasks | jq '.tasks[] | {id, title, status}'

# 3. 检查空闲检测
curl http://localhost:3020/api/idle-agents | jq .
```

### 问题：分配失败

**可能原因**:
1. 智能体 ID 不存在
2. 任务 ID 不存在
3. 智能体已分配其他任务

**解决步骤**:
```bash
# 验证智能体
curl http://localhost:3020/api/agents/raphael

# 验证任务
curl http://localhost:3020/api/tasks

# 查看错误日志
tail -50 backend/backend.log
```

---

**更新日期**: 2026-04-07  
**维护者**: 李奥纳多 (架构师 🟦)
