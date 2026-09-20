<template>
  <div class="command-center">
    <header class="page-header">
      <div>
        <div class="title-row">
          <el-icon><Platform /></el-icon>
          <h1>擎天柱指挥中心</h1>
          <span class="live-indicator">运行中</span>
        </div>
        <p>统一任务入口 · 审批后执行 · 异步协作与反馈</p>
      </div>
      <div class="header-actions">
        <el-switch v-model="autoRefresh" active-text="自动刷新" />
        <el-button :icon="Refresh" :loading="loading" @click="refreshAll">刷新</el-button>
      </div>
    </header>

    <section class="summary-strip">
      <div class="summary-item">
        <span>全部任务</span>
        <strong>{{ summary.total }}</strong>
      </div>
      <div class="summary-item">
        <span>项目</span>
        <strong class="blue">{{ projectSummary.total }}</strong>
      </div>
      <div class="summary-item">
        <span>正在推进</span>
        <strong class="blue">{{ summary.active }}</strong>
      </div>
      <div class="summary-item">
        <span>等待批准</span>
        <div class="context-summary-value">
          <strong class="amber">{{ summary.pending_approvals + summary.pending_step_approvals }}</strong>
          <small v-if="summary.pending_step_approvals">高风险步骤 {{ summary.pending_step_approvals }}</small>
        </div>
      </div>
      <div class="summary-item">
        <span>待发送回执</span>
        <strong>{{ summary.outbox_pending }}</strong>
      </div>
      <div class="summary-item">
        <span>待处理补偿</span>
        <strong :class="{ amber: summary.pending_compensations }">{{ summary.pending_compensations }}</strong>
      </div>
      <div class="summary-item">
        <span>上下文快照</span>
        <div class="context-summary-value">
          <strong class="blue">{{ summary.context_ready }}</strong>
          <small v-if="summary.context_degraded">降级 {{ summary.context_degraded }}</small>
        </div>
      </div>
      <div class="summary-item">
        <span>待审核记忆</span>
        <strong class="amber">{{ summary.memory_candidates.pending_review }}</strong>
      </div>
      <div class="summary-item">
        <span>一般讨论</span>
        <strong>{{ summary.discussion_count }}</strong>
      </div>
      <div class="summary-item">
        <span>待澄清</span>
        <strong class="amber">{{ summary.clarification_pending }}</strong>
      </div>
    </section>

    <section
      v-if="auth.isAdmin && productionHealth"
      class="reliability-strip"
      :class="{ degraded: productionHealth.status !== 'ready' }"
      aria-label="生产运行门禁"
    >
      <div class="reliability-title">
        <el-icon><Connection /></el-icon>
        <span>生产运行门禁</span>
        <el-tag size="small" :type="productionHealth.status === 'ready' ? 'success' : 'danger'">
          {{ productionHealth.status === 'ready' ? '就绪' : '降级' }}
        </el-tag>
      </div>
      <div>
        <span>事实库</span>
        <strong>{{ productionHealth.storage.backend.toUpperCase() }}</strong>
      </div>
      <div>
        <span>连接池</span>
        <strong v-if="productionHealth.storage_runtime.pool">
          {{ productionHealth.storage_runtime.pool.in_use }}/{{ productionHealth.storage_runtime.pool.max_size }}
        </strong>
        <strong v-else>本地直连</strong>
        <small v-if="productionHealth.storage_runtime.pool">
          峰值 {{ productionHealth.storage_runtime.pool.peak_in_use }} · 超时 {{ productionHealth.storage_runtime.pool.acquire_timeouts_total }} · 失败 {{ productionHealth.storage_runtime.pool.connection_failures_total || 0 }} · 重连 {{ productionHealth.storage_runtime.pool.reconnects_total || 0 }}
        </small>
      </div>
      <div>
        <span>执行租约</span>
        <strong :class="{ danger: productionHealth.work_runs.expired_active_leases > 0 }">
          {{ productionHealth.work_runs.expired_active_leases }} 个过期
        </strong>
        <small>活跃 {{ productionHealth.work_runs.active }} · 重试 {{ productionHealth.work_runs.retry_attempts }}</small>
      </div>
      <div>
        <span>流程检查点</span>
        <strong>{{ productionHealth.workflow_runtime.checkpoint_storage.backend }}</strong>
        <small>{{ productionHealth.workflow_runtime.checkpoint_storage.status }} · 禁止运行时建表</small>
      </div>
      <div>
        <span>执行实例</span>
        <strong :class="{ danger: productionHealth.workers.live < productionHealth.workers.required }">
          {{ productionHealth.workers.live }}/{{ productionHealth.workers.required }} 在线
        </strong>
        <small>失联 {{ productionHealth.workers.stale }} · {{ productionHealth.workers.status }}</small>
      </div>
    </section>

    <el-tabs v-model="activeWorkspaceTab" class="command-workshop-tabs">
      <el-tab-pane label="工作坊" name="workshop" />
    </el-tabs>

    <main class="workspace">
      <aside class="mission-column">
        <div class="panel-heading workbench-heading">
          <div>
            <strong>任务工作台</strong>
            <span>{{ projectSummary.total }} 个项目 · {{ workbenchItems.length }} 项任务</span>
          </div>
        </div>
        <div class="workbench-filters">
          <el-input
            v-model="workbenchSearch"
            size="small"
            placeholder="搜索任务/项目/智能体"
            clearable
            @input="refreshMissions"
          />
          <div class="filter-grid">
            <el-select v-model="statusFilter" size="small" placeholder="状态" clearable @change="refreshMissions">
              <el-option label="全部状态" value="" />
              <el-option
                v-for="option in statusOptions"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
            <el-select v-model="missionTypeFilter" size="small" placeholder="类型" clearable @change="refreshMissions">
              <el-option label="全部类型" value="" />
              <el-option v-for="option in missionTypeOptions" :key="option.value" :label="option.label" :value="option.value" />
            </el-select>
            <el-select v-model="projectFilter" size="small" placeholder="项目" clearable filterable @change="refreshMissions">
              <el-option label="全部项目" value="" />
              <el-option v-for="project in projects" :key="project.id" :label="project.name" :value="project.id" />
            </el-select>
            <el-select v-model="agentFilter" size="small" placeholder="智能体" clearable filterable @change="refreshMissions">
              <el-option label="全部智能体" value="" />
              <el-option v-for="option in agentOptions" :key="option.value" :label="option.label" :value="option.value" />
            </el-select>
            <el-select v-model="sourceFilter" size="small" placeholder="来源" clearable @change="refreshMissions">
              <el-option label="全部来源" value="" />
              <el-option label="指挥中心" value="command-center" />
              <el-option label="程序开发" value="project-dev" />
              <el-option label="文档撰写" value="project-doc" />
            </el-select>
          </div>
          <div class="project-scope-row">
            <span>项目范围</span>
            <strong>{{ selectedProjectFilter?.name || '全部项目' }}</strong>
          </div>
        </div>
        <div class="mission-list">
          <button
            v-for="item in workbenchItems"
            :key="item.mission_id"
            class="mission-item"
            :class="{ selected: item.mission_id === selectedMissionId }"
            @click="selectMission(item.mission_id)"
          >
            <div class="mission-item-head">
              <span class="status-dot" :class="statusTone(item.mission_status)"></span>
              <strong>{{ item.mission_title }}</strong>
              <el-tag size="small" effect="plain" :type="tagType(item.mission_status)">
                {{ statusLabel(item.mission_status) }}
              </el-tag>
            </div>
            <div class="mission-meta stacked-meta">
              <span>
                <b>所属项目</b>
                {{ item.project_name || '未绑定项目' }}
              </span>
              <span>
                <b>任务类型</b>
                {{ missionTypeLabel(item.mission_type) }}
              </span>
              <span>
                <b>执行智能体</b>
                {{ item.current_agent_name }}
              </span>
              <span>
                <b>当前步骤</b>
                {{ item.active_step?.title || '等待擎天柱规划' }}
              </span>
              <span>{{ formatTime(item.updated_at) }}</span>
            </div>
            <div v-if="item.waiting_reason" class="waiting-reason">{{ compactText(item.waiting_reason, 80) }}</div>
            <div class="mission-progress">
              <span
                :style="{ width: `${item.progress}%` }"
                :class="{ completed: item.mission_status === 'completed' }"
              ></span>
            </div>
            <div class="workbench-foot">
              <span>{{ item.steps_summary.completed }}/{{ item.steps_summary.total }} 步骤</span>
              <span>{{ item.linked_tasks.length }} 个总账记录</span>
            </div>
          </button>
          <el-empty
            v-if="!loading && !workbenchItems.length"
            description="暂无指挥任务"
          />
        </div>
      </aside>

      <section class="mission-detail">
        <section class="space-panel">
          <div class="space-heading">
            <div>
              <strong>智能体空间</strong>
              <span>{{ spaceGraph?.mission.title || '等待擎天柱接收任务' }}</span>
            </div>
            <div class="space-heading-meta">
              <el-tag size="small" effect="plain" type="success">唯一入口：擎天柱</el-tag>
              <el-tag size="small" effect="plain" :type="tagType(spaceGraph?.mission.status || '')">
                {{ statusLabel(spaceGraph?.mission.status || 'received') }}
              </el-tag>
            </div>
          </div>
          <div class="space-stage">
            <div
              v-for="lane in spaceGraph?.lanes || []"
              :key="lane.id"
              class="space-lane"
              :class="`lane-${lane.id}`"
            >
              <span>{{ lane.label }}</span>
            </div>
            <span
              v-for="edge in visibleSpaceEdges"
              :key="edge.id"
              class="space-edge"
              :class="[{ active: edge.active }, `edge-${edge.type}`]"
              :style="spaceEdgeStyle(edge)"
            ></span>
            <button
              v-for="node in spaceNodes"
              :key="node.id"
              type="button"
              class="space-node"
              :class="[
                `space-status-${spaceStatusTone(node.status)}`,
                `space-lane-${node.lane}`,
                { selected: selectedSpaceNode?.id === node.id, commander: node.is_commander }
              ]"
              :style="spaceNodeStyle(node)"
              @click="selectSpaceNode(node.id)"
            >
              <span class="space-platform"></span>
              <span class="space-avatar">{{ node.emoji || node.name.slice(0, 1) }}</span>
              <span class="space-node-body">
                <strong>{{ node.name }}</strong>
                <small>{{ node.role || node.agent_id }}</small>
              </span>
              <span class="space-node-progress">
                <span :style="{ width: `${Math.max(0, Math.min(node.progress, 100))}%` }"></span>
              </span>
            </button>
          </div>
          <div class="space-inspector">
            <template v-if="selectedSpaceNode">
              <div>
                <strong>{{ selectedSpaceNode.name }}</strong>
                <span>{{ selectedSpaceNode.role || selectedSpaceNode.agent_id }}</span>
              </div>
              <el-tag size="small" effect="plain" :type="spaceTagType(selectedSpaceNode.status)">
                {{ spaceStatusLabel(selectedSpaceNode.status) }}
              </el-tag>
              <p>{{ selectedSpaceNode.current_task || (selectedSpaceNode.is_commander ? '负责拆分、分工、协同、验收与汇报' : '等待擎天柱分配任务') }}</p>
              <small>
                {{ selectedSpaceNode.is_commander ? '用户只通过擎天柱下达任务' : '该智能体仅接受擎天柱或上级编排调度' }}
              </small>
            </template>
          </div>
        </section>

        <section class="agent-status-panel">
          <header class="section-title">
            <div>
              <strong>全员状态</strong>
              <span>随自动刷新同步 · {{ formatTime(spaceGraph?.updated_at) || '等待同步' }}</span>
            </div>
            <div class="agent-status-summary">
              <span><b>{{ agentStatusSummary.working }}</b> 工作中</span>
              <span><b>{{ agentStatusSummary.assigned }}</b> 已分配</span>
              <span><b>{{ agentStatusSummary.blocked }}</b> 阻塞</span>
              <span><b>{{ agentStatusSummary.idle }}</b> 待命</span>
            </div>
          </header>
          <div class="agent-status-grid" role="table" aria-label="智能体工作状态">
            <div class="agent-status-row head" role="row">
              <span role="columnheader">智能体</span>
              <span role="columnheader">状态</span>
              <span role="columnheader">当前任务</span>
              <span role="columnheader">项目</span>
              <span role="columnheader">进度</span>
              <span role="columnheader">更新时间</span>
            </div>
            <button
              v-for="row in agentStatusRows"
              :key="row.node.id"
              type="button"
              class="agent-status-row"
              :class="{ selected: selectedSpaceNode?.id === row.node.id }"
              role="row"
              @click="selectSpaceNode(row.node.id)"
            >
              <span class="agent-cell identity" role="cell">
                <i>{{ row.node.emoji || row.node.name.slice(0, 1) }}</i>
                <span>
                  <strong>{{ row.node.name }}</strong>
                  <small>{{ row.node.role || row.node.agent_id }}</small>
                </span>
              </span>
              <span role="cell">
                <el-tag size="small" effect="plain" :type="spaceTagType(row.node.status)">
                  {{ spaceStatusLabel(row.node.status) }}
                </el-tag>
              </span>
              <span class="agent-cell task" role="cell" :title="row.currentTask">
                {{ row.currentTask || (row.node.is_commander ? '统筹待接入任务' : '等待调度') }}
                <small v-if="row.activeMissionCount > 1">并行 {{ row.activeMissionCount }} 项</small>
              </span>
              <span class="agent-cell project" role="cell" :title="row.projectName">{{ row.projectName }}</span>
              <span class="agent-progress-cell" role="cell">
                <el-progress
                  :percentage="Math.max(0, Math.min(row.node.progress, 100))"
                  :stroke-width="5"
                  :show-text="false"
                />
                <small>{{ Math.max(0, Math.min(row.node.progress, 100)) }}%</small>
              </span>
              <span class="agent-cell time" role="cell">{{ formatTime(row.updatedAt) || '-' }}</span>
            </button>
          </div>
        </section>

        <template v-if="selectedMission">
          <div class="detail-heading">
            <div>
              <div class="detail-title">
                <h2>{{ selectedMission.title }}</h2>
                <el-tag effect="plain" :type="tagType(selectedMission.status)">
                  {{ statusLabel(selectedMission.status) }}
                </el-tag>
              </div>
              <span>{{ selectedMission.id }}</span>
            </div>
            <el-button
              v-if="!terminalStatuses.has(selectedMission.status)"
              type="danger"
              plain
              :icon="CircleClose"
              @click="cancelSelected"
            >
              取消任务
            </el-button>
          </div>

          <div class="objective-block">
            <span class="block-label">目标</span>
            <p>{{ selectedMission.objective }}</p>
          </div>

          <section class="governance-overview" aria-label="规范业务流进度">
            <div class="section-title governance-heading">
              <div>
                <strong>规范执行链</strong>
                <span>真实状态驱动 · 从任务接收到交付与故障恢复</span>
              </div>
              <div class="trace-identity">
                <span>Run {{ selectedMission.mission_run?.id?.slice(0, 12) || '待创建' }}</span>
                <span>Trace {{ selectedMission.mission_run?.correlation_id?.slice(0, 18) || '-' }}</span>
                <span>Plan V{{ selectedMission.plan_version }}</span>
              </div>
            </div>

            <div :class="['control-point', `tone-${missionControlPoint.tone}`]">
              <div class="control-point-icon">
                <el-icon v-if="missionControlPoint.tone === 'success'"><Check /></el-icon>
                <el-icon v-else-if="missionControlPoint.tone === 'danger'"><Close /></el-icon>
                <el-icon v-else-if="missionControlPoint.tone === 'warning'"><Warning /></el-icon>
                <el-icon v-else><Position /></el-icon>
              </div>
              <div>
                <span>当前控制点</span>
                <strong>{{ missionControlPoint.title }}</strong>
                <p>{{ missionControlPoint.description }}</p>
              </div>
              <div class="control-next-action">
                <span>下一步</span>
                <p>{{ missionControlPoint.action }}</p>
              </div>
            </div>

            <div class="lifecycle-track">
              <article
                v-for="(stage, index) in missionLifecycle"
                :key="stage.id"
                :class="['lifecycle-stage', `stage-${stage.state}`]"
              >
                <div class="stage-marker">
                  <el-icon v-if="stage.state === 'completed'"><Check /></el-icon>
                  <el-icon v-else-if="stage.state === 'blocked'"><Close /></el-icon>
                  <el-icon v-else-if="stage.state === 'warning'"><Warning /></el-icon>
                  <span v-else>{{ index + 1 }}</span>
                </div>
                <span class="stage-state">{{ lifecycleStateLabel(stage.state) }}</span>
                <strong>{{ stage.label }}</strong>
                <small>{{ stage.description }}</small>
                <p>{{ stage.detail }}</p>
              </article>
            </div>

            <div class="governance-metrics">
              <div><span>步骤</span><strong>{{ completedStepCount }}/{{ selectedMission.steps.length }}</strong></div>
              <div><span>产物</span><strong>{{ selectedMission.artifacts?.length || 0 }}</strong></div>
              <div><span>证据</span><strong>{{ selectedMission.evidence?.length || 0 }}</strong></div>
              <div><span>验收门禁</span><strong>{{ acceptedGateCount }}/{{ selectedMission.acceptance_gates?.length || 0 }}</strong></div>
              <div><span>副作用</span><strong>{{ selectedMission.effects?.length || 0 }}</strong></div>
              <div><span>未解决补偿</span><strong :class="{ danger: unresolvedCompensationCount }">{{ unresolvedCompensationCount }}</strong></div>
            </div>
          </section>

          <section v-if="selectedWorkbench" class="ledger-block">
            <div class="section-title">
              <div>
                <strong>统一任务视图</strong>
                <span>{{ selectedWorkbench.project_name || '未绑定项目' }} · {{ selectedWorkbench.current_agent_name }}</span>
              </div>
              <el-tag size="small" effect="plain">{{ selectedWorkbench.linked_tasks.length }} 个总账记录</el-tag>
            </div>
            <div v-if="selectedWorkbench.active_step" class="current-step-card">
              <span>当前步骤</span>
              <strong>{{ selectedWorkbench.active_step.title }}</strong>
              <small>{{ agentName(selectedWorkbench.active_step.agent_id) }} · {{ taskTypeLabel(selectedWorkbench.active_step.task_type) }} · {{ stepStatusLabel(selectedWorkbench.active_step.status) }}</small>
            </div>
            <div v-if="selectedWorkbench.linked_tasks.length" class="ledger-task-list">
              <article v-for="task in selectedWorkbench.linked_tasks" :key="task.task_id" class="ledger-task-row">
                <div>
                  <strong>{{ task.title }}</strong>
                  <span>{{ task.task_id }}</span>
                </div>
                <div>
                  <el-tag size="small" effect="plain">{{ sourceLabel(task.source) }}</el-tag>
                  <el-tag size="small" effect="plain" :type="tagType(task.status)">{{ ledgerStatusLabel(task.status) }}</el-tag>
                  <span>{{ task.assignee_name || agentName(task.assignee || '') }}</span>
                </div>
              </article>
            </div>
          </section>

          <section v-if="selectedMission.plan" class="plan-block">
            <div class="section-title">
              <div>
                <strong>执行计划 V{{ selectedMission.plan_version }}</strong>
                <span>{{ selectedMission.plan.summary || '待完善' }}</span>
              </div>
              <div class="plan-badges">
                <el-tag
                  v-if="selectedMission.plan.plan_quality"
                  size="small"
                  effect="plain"
                  :type="planQualityTagType(selectedMission.plan.plan_quality.status)"
                >
                  质检 {{ selectedMission.plan.plan_quality.score }}
                </el-tag>
                <el-tag size="small" effect="plain">
                  风险 {{ riskLabel(selectedMission.plan.risk_level) }}
                </el-tag>
              </div>
            </div>

            <div v-if="selectedMission.plan.plan_quality" class="plan-quality-card">
              <div class="plan-quality-head">
                <strong>{{ planQualityLabel(selectedMission.plan.plan_quality.status) }}</strong>
                <span>检查 {{ selectedMission.plan.plan_quality.checked_rules.length }} 项规则</span>
              </div>
              <div v-if="selectedMission.plan.plan_quality.blockers.length" class="quality-issue-list blocker">
                <strong>阻断项</strong>
                <span v-for="item in selectedMission.plan.plan_quality.blockers" :key="`blocker-${item}`">{{ item }}</span>
              </div>
              <div v-if="selectedMission.plan.plan_quality.warnings.length" class="quality-issue-list warning">
                <strong>警告</strong>
                <span v-for="item in selectedMission.plan.plan_quality.warnings" :key="`warning-${item}`">{{ item }}</span>
              </div>
              <div v-if="selectedMission.plan.plan_quality.suggestions.length" class="quality-issue-list">
                <strong>建议</strong>
                <span v-for="item in selectedMission.plan.plan_quality.suggestions" :key="`suggestion-${item}`">{{ item }}</span>
              </div>
            </div>

            <div class="step-list">
              <article
                v-for="(step, index) in selectedMission.steps"
                :key="step.id"
                class="step-row"
              >
                <div class="step-index" :class="statusTone(step.status)">
                  <el-icon v-if="step.status === 'completed'"><Check /></el-icon>
                  <el-icon v-else-if="step.status === 'failed'"><Close /></el-icon>
                  <span v-else>{{ index + 1 }}</span>
                </div>
                <div class="step-body">
                  <div class="step-head">
                    <strong>{{ step.title }}</strong>
                    <span>{{ agentName(step.agent_id) }} · {{ taskTypeLabel(step.task_type) }}</span>
                    <el-tag size="small" effect="plain" :type="tagType(step.status)">
                      {{ stepStatusLabel(step.status) }}
                    </el-tag>
                  </div>
                  <p>{{ step.description || '暂无说明' }}</p>
                  <div class="step-governance-meta">
                    <span>阶段 {{ step.phase || step.order_index }}</span>
                    <span>风险 {{ step.risk_class || step.risk_level || 'L1' }}</span>
                    <span v-if="step.dependencies.length">依赖 {{ step.dependencies.map(stepDependencyLabel).join('、') }}</span>
                    <span v-else>无前置依赖</span>
                    <span v-if="step.side_effect" class="danger">有副作用</span>
                    <span v-if="step.idempotency_key" :title="step.idempotency_key">幂等 {{ compactText(step.idempotency_key, 26) }}</span>
                  </div>
                  <div
                    v-if="hasStepContract(step)"
                    class="step-contract"
                  >
                    <div v-if="step.tool_requirements?.length || step.required_tools?.length">
                      <strong>工具</strong>
                      <span
                        v-for="tool in step.tool_requirements || []"
                        :key="`${step.id}-tool-${tool.id}`"
                        :class="['contract-chip', `tool-status-${tool.status || 'unknown'}`]"
                      >
                        {{ tool.name || tool.id }}
                      </span>
                      <span
                        v-for="tool in fallbackTools(step)"
                        :key="`${step.id}-raw-tool-${tool}`"
                        class="contract-chip"
                      >
                        {{ tool }}
                      </span>
                    </div>
                    <div v-if="step.deliverables?.length">
                      <strong>产物</strong>
                      <span v-for="item in step.deliverables" :key="`${step.id}-deliverable-${item}`">{{ item }}</span>
                    </div>
                    <div v-if="step.acceptance_criteria?.length">
                      <strong>验收</strong>
                      <span v-for="item in step.acceptance_criteria" :key="`${step.id}-acceptance-${item}`">{{ item }}</span>
                    </div>
                    <div v-if="step.evidence_required?.length">
                      <strong>证据</strong>
                      <span v-for="item in step.evidence_required" :key="`${step.id}-evidence-${item}`">{{ item }}</span>
                    </div>
                  </div>
                  <div
                    v-if="step.status === 'awaiting_approval' && step.step_approval"
                    class="step-approval-card"
                  >
                    <div>
                      <strong>高风险动作需要单独授权</strong>
                      <el-tag size="small" type="danger" effect="plain">
                        {{ step.step_approval.risk_class }}
                      </el-tag>
                    </div>
                    <p>{{ step.step_approval.action_summary }}</p>
                    <span>影响资源：{{ step.resources?.join('、') || '未声明' }}</span>
                    <span>回滚方案：{{ step.rollback_plan || '未声明' }}</span>
                    <span>合同指纹：{{ step.step_approval.contract_hash.slice(0, 12) }}</span>
                    <div v-if="auth.isAdmin && step.step_approval.status === 'pending'" class="step-approval-actions">
                      <el-button
                        size="small"
                        :loading="stepApprovalLoadingId === step.id"
                        @click="rejectStepApproval(step)"
                      >
                        拒绝
                      </el-button>
                      <el-button
                        size="small"
                        type="danger"
                        :loading="stepApprovalLoadingId === step.id"
                        @click="approveStepApproval(step)"
                      >
                        批准本次执行
                      </el-button>
                    </div>
                    <span v-else-if="!auth.isAdmin">仅管理员可批准高风险动作</span>
                  </div>
                  <div
                    v-for="compensation in step.compensations || []"
                    :key="compensation.id"
                    class="compensation-card"
                  >
                    <div>
                      <strong>副作用补偿</strong>
                      <el-tag
                        size="small"
                        effect="plain"
                        :type="compensation.status === 'completed' ? 'success' : compensation.status === 'failed' || compensation.status === 'rejected' ? 'danger' : 'warning'"
                      >
                        {{ compensationStatusLabel(compensation.status) }}
                      </el-tag>
                    </div>
                    <p>{{ compensation.instructions }}</p>
                    <span>资源：{{ compensation.resource }}</span>
                    <span>补偿幂等键：{{ compensation.idempotency_key }}</span>
                    <span>合同指纹：{{ compensation.contract_hash.slice(0, 12) }}</span>
                    <div
                      v-if="auth.isAdmin && compensation.status === 'pending_approval'"
                      class="step-approval-actions"
                    >
                      <el-button
                        size="small"
                        :loading="compensationLoadingId === compensation.id"
                        @click="rejectCompensation(compensation)"
                      >拒绝</el-button>
                      <el-button
                        size="small"
                        type="warning"
                        :loading="compensationLoadingId === compensation.id"
                        @click="approveCompensation(compensation)"
                      >批准补偿</el-button>
                    </div>
                  </div>
                  <div v-if="step.effects?.length" class="effect-journal">
                    <div class="subsection-label">
                      <strong>Effect Journal</strong>
                      <span>{{ step.effects.length }} 条副作用记录</span>
                    </div>
                    <div v-for="effect in step.effects" :key="effect.id" class="effect-row">
                      <span :class="['effect-status', `effect-${effect.status}`]">{{ effectStatusLabel(effect.status) }}</span>
                      <strong>{{ effect.action }}</strong>
                      <small>{{ effect.resource }} · {{ effect.receipt_ref || '无回执' }} · {{ effect.evidence_refs.length }} 条证据</small>
                    </div>
                  </div>
                  <div
                    v-if="step.acceptance_gate"
                    :class="['acceptance-gate-card', { blocked: step.acceptance_gate.enforced && !step.acceptance_gate.accepted }]"
                  >
                    <div>
                      <strong>执行证据门禁</strong>
                      <el-tag
                        size="small"
                        effect="plain"
                        :type="step.acceptance_gate.accepted ? 'success' : step.acceptance_gate.enforced ? 'danger' : 'warning'"
                      >
                        {{ step.acceptance_gate.accepted ? '通过' : step.acceptance_gate.enforced ? '强制阻断' : 'Shadow 观察' }} · {{ step.acceptance_gate.score }}
                      </el-tag>
                    </div>
                    <p v-if="step.acceptance_gate.blockers.length">阻断：{{ step.acceptance_gate.blockers.join('；') }}</p>
                    <p v-else-if="step.acceptance_gate.warnings.length">警告：{{ step.acceptance_gate.warnings.join('；') }}</p>
                    <span>{{ step.acceptance_gate.mode }} · {{ formatTime(step.acceptance_gate.evaluated_at) }}</span>
                  </div>
                  <div
                    v-if="step.work_run_id || step.context_binding || step.result?.output || step.result?.error"
                    class="step-result"
                  >
                    <span v-if="step.work_run_id">执行记录 {{ step.work_run_id }}</span>
                    <el-tag
                      v-if="step.result?.execution_quality"
                      size="small"
                      effect="plain"
                      :type="executionQualityTagType(step.result.execution_quality.status)"
                    >
                      证据 {{ step.result.execution_quality.score }}
                    </el-tag>
                    <span v-if="step.context_binding" class="context-reference">
                      背景 {{ step.context_binding.context_pack_id || '降级' }}
                      V{{ step.context_binding.context_pack_version }}
                      · {{ step.context_binding.citation_count }} 条引用
                    </span>
                    <p v-if="step.result?.output">{{ compactText(step.result.output) }}</p>
                    <p v-if="step.result?.error" class="error-text">{{ compactText(step.result.error) }}</p>
                    <p v-if="step.result?.execution_quality?.warnings?.length" class="quality-warning-text">
                      {{ executionQualityLabel(step.result.execution_quality.status) }}：{{ step.result.execution_quality.warnings.slice(0, 2).join('；') }}
                    </p>
                  </div>
                </div>
              </article>
            </div>

            <div
              v-if="selectedMission.delivery_gate"
              :class="['delivery-gate-card', { blocked: selectedMission.delivery_gate.enforced && !selectedMission.delivery_gate.accepted }]"
            >
              <div>
                <span>最终交付门禁</span>
                <strong>{{ selectedMission.delivery_gate.accepted ? '可交付' : selectedMission.delivery_gate.enforced ? '交付阻断' : '观察中' }}</strong>
              </div>
              <div class="delivery-score">{{ selectedMission.delivery_gate.score }}<small>/100</small></div>
              <p v-if="selectedMission.delivery_gate.blockers.length">{{ selectedMission.delivery_gate.blockers.join('；') }}</p>
              <p v-else>产物、证据、执行验收和补偿状态已统一评估。</p>
              <span>模式 {{ selectedMission.delivery_gate.mode }} · {{ formatTime(selectedMission.delivery_gate.evaluated_at) }}</span>
            </div>
          </section>

          <section class="timeline-block">
            <div class="section-title">
              <div>
                <strong>任务动态</strong>
                <span>持久化事件记录</span>
              </div>
            </div>
            <el-timeline>
              <el-timeline-item
                v-for="event in reversedEvents"
                :key="event.id"
                :timestamp="formatTime(event.created_at)"
                placement="top"
                :type="eventType(event)"
              >
                <strong>{{ eventLabel(event.event_type) }}</strong>
                <p>{{ event.detail }}</p>
                <span>{{ agentName(event.actor || '') }}</span>
              </el-timeline-item>
            </el-timeline>
          </section>
        </template>
        <el-empty v-else description="选择一个任务查看执行详情" />
      </section>

      <aside class="optimus-column">
        <section class="optimus-profile">
          <div class="optimus-avatar">擎</div>
          <div>
            <strong>擎天柱</strong>
            <span>总项目管理 · 唯一任务入口</span>
          </div>
          <span class="online-dot"></span>
        </section>

        <section class="action-panel conversation-panel">
          <div class="action-heading">
            <el-icon><ChatLineRound /></el-icon>
            <strong>最近会话分流</strong>
            <el-tag size="small" effect="plain">{{ routedMessages.length }} 条</el-tag>
          </div>
          <div v-if="!routedMessages.length" class="memory-empty">暂无会话记录</div>
          <div v-else class="routed-message-list">
            <article
              v-for="message in routedMessages.slice(0, 8)"
              :key="message.id"
              class="routed-message-row"
            >
              <div class="routed-message-head">
                <el-tag size="small" effect="plain" :type="intentTagType(message.intent_type)">
                  {{ intentLabel(message.intent_type) }}
                </el-tag>
                <span>{{ formatTime(message.created_at) }}</span>
              </div>
              <p>{{ compactText(message.content, 180) }}</p>
              <small>{{ compactText(message.intent_reason, 150) }}</small>
              <div v-if="message.response" class="routed-response">
                <strong>擎天柱</strong>
                <p>{{ compactText(message.response.content, 180) }}</p>
              </div>
            </article>
          </div>
        </section>

        <section v-if="selectedMission?.planning_context" class="action-panel context-panel">
          <div class="action-heading">
            <el-icon><Connection /></el-icon>
            <strong>任务背景上下文</strong>
            <el-tag
              size="small"
              effect="plain"
              :type="contextTagType(selectedMission.planning_context.status)"
            >
              {{ contextStatusLabel(selectedMission.planning_context.status) }}
            </el-tag>
          </div>
          <div class="context-pack-meta">
            <strong>{{ selectedMission.planning_context.context_pack_id || '未生成快照' }}</strong>
            <span>
              V{{ selectedMission.planning_context.context_pack_version }}
              · {{ selectedMission.planning_context.item_count }} 条内容
              · {{ selectedMission.planning_context.citation_count }} 条引用
            </span>
          </div>
          <div v-if="selectedMission.planning_context.source_types.length" class="context-source-list">
            <span
              v-for="sourceType in selectedMission.planning_context.source_types"
              :key="sourceType"
            >
              {{ sourceTypeLabel(sourceType) }}
            </span>
          </div>
          <p v-if="selectedMission.planning_context.error" class="error-text">
            {{ compactText(selectedMission.planning_context.error, 260) }}
          </p>
          <div v-if="selectedMission.planning_context.citations.length" class="citation-list">
            <div
              v-for="citation in selectedMission.planning_context.citations.slice(0, 5)"
              :key="`${citation.rank}-${citation.source_ref}`"
              :title="citation.source_ref"
            >
              <span>[C{{ citation.rank }}]</span>
              <p>{{ citation.title }}</p>
            </div>
          </div>
        </section>

        <section class="action-panel memory-panel">
          <div class="action-heading">
            <el-icon><DocumentChecked /></el-icon>
            <strong>长期记忆候选</strong>
            <el-tag
              size="small"
              effect="plain"
              :type="memoryCandidates.length ? 'warning' : 'info'"
            >
              待审核 {{ memoryCandidates.length }}
            </el-tag>
          </div>
          <p class="memory-panel-note">
            擎天柱从已完成任务中提炼。审核发布后，仅影响后续任务的背景检索。
          </p>
          <div v-if="memoryLoading" class="memory-empty">正在同步候选…</div>
          <div v-else-if="!memoryCandidates.length" class="memory-empty">
            暂无待审核的长期记忆
          </div>
          <div v-else class="memory-candidate-list">
            <article
              v-for="candidate in memoryCandidates.slice(0, 6)"
              :key="candidate.id"
              class="memory-candidate-row"
            >
              <div class="memory-candidate-head">
                <strong>{{ candidate.title }}</strong>
                <el-tag size="small" effect="plain">
                  {{ memoryTargetLabel(candidate.target_scope) }}
                </el-tag>
              </div>
              <p>{{ compactText(candidate.content, 260) }}</p>
              <div class="memory-candidate-meta">
                <span>{{ candidate.memory_key }}</span>
                <span>{{ importanceLabel(candidate.importance) }}</span>
                <span>可信度 {{ confidenceLabel(candidate.confidence) }}</span>
              </div>
              <div v-if="candidate.evidence_refs.length" class="memory-evidence">
                {{ candidate.evidence_refs.slice(0, 4).join(' · ') }}
              </div>
              <div v-if="canReviewMemory" class="memory-candidate-actions">
                <el-button
                  size="small"
                  :loading="memoryActionId === candidate.id"
                  @click="rejectMemoryCandidate(candidate)"
                >
                  驳回
                </el-button>
                <el-button
                  size="small"
                  type="primary"
                  :loading="memoryActionId === candidate.id"
                  @click="publishMemoryCandidate(candidate)"
                >
                  审核发布
                </el-button>
              </div>
            </article>
          </div>
          <p v-if="memoryCandidates.length && !canReviewMemory" class="memory-review-hint">
            当前账号可查看候选，只有管理员可以审核发布。
          </p>
        </section>

        <section v-if="selectedMission?.status === 'awaiting_approval'" class="action-panel approval-panel">
          <div class="action-heading">
            <el-icon><DocumentChecked /></el-icon>
            <strong>计划待批准</strong>
          </div>
          <p>{{ selectedMission.plan?.summary }}</p>
          <el-input
            v-model="decisionComment"
            type="textarea"
            :rows="3"
            placeholder="填写批准意见或调整要求"
          />
          <div class="action-buttons">
            <el-button :loading="actionLoading" @click="rejectSelected">驳回重规划</el-button>
            <el-button type="primary" :loading="actionLoading" @click="approveSelected">
              批准并执行
            </el-button>
          </div>
        </section>

        <section v-if="selectedMission?.status === 'waiting_feedback'" class="action-panel feedback-panel">
          <div class="action-heading">
            <el-icon><Warning /></el-icon>
            <strong>需要反馈</strong>
          </div>
          <p>{{ selectedMission.last_error || '执行遇到阻塞，请补充信息。' }}</p>
          <el-input
            v-model="feedbackText"
            type="textarea"
            :rows="4"
            placeholder="补充范围、约束、凭据或处理意见"
          />
          <el-button
            type="primary"
            :loading="actionLoading"
            :disabled="!feedbackText.trim()"
            @click="sendFeedback"
          >
            提交反馈并继续
          </el-button>
        </section>

        <section class="action-panel command-panel">
          <div class="action-heading">
            <el-icon><Promotion /></el-icon>
            <strong>启动项目任务</strong>
          </div>
          <el-segmented
            v-model="newMission.mission_type"
            :options="missionTypeOptions"
            size="small"
          />
          <el-select v-model="newMission.project_id" placeholder="选择任务所属项目" filterable>
            <el-option
              v-for="project in availableProjects"
              :key="project.id"
              :label="project.name"
              :value="project.id"
            />
          </el-select>
          <el-input v-model="newMission.title" placeholder="任务名称（可选）" />
          <el-input
            v-model="newMission.objective"
            type="textarea"
            :rows="6"
            placeholder="描述目标、约束、期望结果和完成标准"
          />
          <el-button
            type="primary"
            :icon="Position"
            :loading="creating"
            :disabled="!newMission.objective.trim() || !newMission.project_id"
            @click="createMission"
          >
            交给擎天柱
          </el-button>
        </section>

        <section v-if="selectedMission?.messages?.length" class="message-panel">
          <div class="action-heading">
            <el-icon><ChatLineRound /></el-icon>
            <strong>关联对话</strong>
          </div>
          <div class="message-list">
            <div
              v-for="message in selectedMission.messages.slice(-6)"
              :key="message.id"
              class="message-row"
              :class="message.direction"
            >
              <span>{{ message.direction === 'inbound' ? '用户' : '擎天柱' }}</span>
              <p>{{ compactText(message.content, 220) }}</p>
            </div>
          </div>
        </section>
      </aside>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  ChatLineRound,
  Check,
  CircleClose,
  Close,
  Connection,
  DocumentChecked,
  Platform,
  Position,
  Promotion,
  Refresh,
  Warning
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  approveCommandCenterMission,
  approveCommandCenterCompensation,
  approveCommandCenterStep,
  approveCommandCenterMemoryCandidate,
  cancelCommandCenterMission,
  createCommandCenterMission,
  getCommandCenterAgentSpace,
  getCommandCenterMission,
  getCommandCenterProductionHealth,
  getCommandCenterSummary,
  listCommandCenterMessages,
  listCommandCenterMemoryCandidates,
  listCommandCenterMissions,
  listCommandCenterTaskWorkbench,
  rejectCommandCenterMemoryCandidate,
  rejectCommandCenterMission,
  rejectCommandCenterCompensation,
  rejectCommandCenterStep,
  sendCommandCenterFeedback,
  type CommandCenterAgentSpace,
  type CommandCenterEvent,
  type CommandCenterCompensation,
  type CommandCenterMemoryCandidate,
  type CommandCenterMission,
  type CommandCenterProductionHealth,
  type CommandCenterRoutedMessage,
  type CommandCenterSpaceEdge,
  type CommandCenterSpaceNode,
  type CommandCenterStep,
  type CommandCenterSummary,
  type CommandCenterWorkbenchItem
} from '@/api/commandCenter'
import { getProjects, type Project } from '@/api/projects'
import { useAuthStore } from '@/stores/auth'
import {
  buildMissionLifecycle,
  deriveMissionControlPoint,
  type LifecycleStageState
} from '@/utils/commandCenterLifecycle'

const auth = useAuthStore()
const route = useRoute()
const loading = ref(false)
const creating = ref(false)
const actionLoading = ref(false)
const stepApprovalLoadingId = ref('')
const compensationLoadingId = ref('')
const memoryLoading = ref(false)
const memoryActionId = ref('')
const memoryReviewAllowed = ref(false)
const autoRefresh = ref(true)
const activeWorkspaceTab = ref('workshop')
const statusFilter = ref('')
const missionTypeFilter = ref('')
const projectFilter = ref('')
const agentFilter = ref('')
const sourceFilter = ref('')
const workbenchSearch = ref('')
const missions = ref<CommandCenterMission[]>([])
const workbenchItems = ref<CommandCenterWorkbenchItem[]>([])
const projects = ref<Project[]>([])
const routedMessages = ref<CommandCenterRoutedMessage[]>([])
const memoryCandidates = ref<CommandCenterMemoryCandidate[]>([])
const spaceGraph = ref<CommandCenterAgentSpace>()
const selectedSpaceNodeId = ref('optimus')
const selectedMissionId = ref('')
const selectedMission = ref<CommandCenterMission>()
const productionHealth = ref<CommandCenterProductionHealth>()
const decisionComment = ref('')
const feedbackText = ref('')
const summary = reactive<CommandCenterSummary>({
  total: 0,
  active: 0,
  pending_approvals: 0,
  pending_step_approvals: 0,
  pending_compensations: 0,
  outbox_pending: 0,
  context_ready: 0,
  context_degraded: 0,
  context_by_status: {},
  discussion_count: 0,
  clarification_pending: 0,
  routed_by_intent: {},
  memory_candidates: {
    total: 0,
    pending_review: 0,
    published: 0,
    rejected: 0,
    by_status: {}
  },
  by_status: {}
})
const newMission = reactive({
  title: '',
  project_id: '',
  mission_type: 'software' as 'software' | 'document',
  objective: ''
})
const terminalStatuses = new Set(['completed', 'failed', 'cancelled'])
let refreshTimer: number | undefined

const statusOptions = [
  { label: '待规划', value: 'received' },
  { label: '规划中', value: 'planning' },
  { label: '等待批准', value: 'awaiting_approval' },
  { label: '执行中', value: 'running' },
  { label: '等待反馈', value: 'waiting_feedback' },
  { label: '评估中', value: 'evaluating' },
  { label: '已完成', value: 'completed' },
  { label: '已取消', value: 'cancelled' }
]

const missionTypeOptions = [
  { label: '程序开发', value: 'software' },
  { label: '文档撰写', value: 'document' }
]

const agentNames: Record<string, string> = {
  optimus: '擎天柱',
  wheeljack: '千斤顶',
  ironhide: '铁皮',
  'ultra-magnus': '通天晓',
  ratchet: '救护车',
  perceptor: '感知器',
  jazz: '爵士',
  shockwave: '震荡波',
  soundwave: '声波',
  bumblebee: '大黄蜂',
  leonardo: '李奥纳多',
  raphael: '拉斐尔',
  donatello: '多纳泰罗',
  michelangelo: '米开朗基罗',
  'command-center': '指挥中心'
}

const agentOptions = computed(() =>
  Object.entries(agentNames).map(([value, label]) => ({ value, label }))
)
const projectSummary = computed(() => ({
  total: projects.value.length,
  software: projects.value.filter(project => projectType(project) === 'software').length,
  document: projects.value.filter(project => projectType(project) === 'document').length,
  active: projects.value.filter(project => !['completed', 'archived', 'cancelled'].includes(String(project.status || ''))).length
}))
const selectedWorkbench = computed(() =>
  workbenchItems.value.find(item => item.mission_id === selectedMissionId.value)
)
const missionLifecycle = computed(() =>
  selectedMission.value ? buildMissionLifecycle(selectedMission.value) : []
)
const missionControlPoint = computed(() =>
  selectedMission.value
    ? deriveMissionControlPoint(selectedMission.value)
    : { tone: 'info' as const, title: '等待选择任务', description: '', action: '' }
)
const completedStepCount = computed(() =>
  selectedMission.value?.steps.filter(step => step.status === 'completed').length || 0
)
const acceptedGateCount = computed(() =>
  selectedMission.value?.acceptance_gates?.filter(gate => gate.accepted).length || 0
)
const unresolvedCompensationCount = computed(() =>
  selectedMission.value?.compensations?.filter(item => item.status !== 'completed' && item.status !== 'cancelled').length || 0
)
const spaceNodes = computed(() => spaceGraph.value?.nodes || [])
const spaceNodeMap = computed(() =>
  new Map(spaceNodes.value.map(node => [node.id, node]))
)
const selectedSpaceNode = computed(() =>
  spaceNodeMap.value.get(selectedSpaceNodeId.value) || spaceNodeMap.value.get('optimus')
)
const visibleSpaceEdges = computed(() =>
  (spaceGraph.value?.edges || []).filter(edge =>
    spaceNodeMap.value.has(edge.from) && spaceNodeMap.value.has(edge.to)
  )
)
const activeMissionByAgent = computed(() => {
  const byAgent = new Map<string, CommandCenterWorkbenchItem>()
  workbenchItems.value
    .filter(item => !terminalStatuses.has(item.mission_status))
    .forEach(item => {
      const agentId = item.current_agent_id || 'optimus'
      const existing = byAgent.get(agentId)
      if (!existing || String(item.updated_at || '') > String(existing.updated_at || '')) {
        byAgent.set(agentId, item)
      }
    })
  return byAgent
})
const agentStatusRows = computed(() => {
  const laneRank: Record<string, number> = {
    commander: 0,
    assistant: 1,
    pm: 2,
    development: 3,
    support: 4,
    agent: 5
  }
  const statusRank: Record<string, number> = {
    blocked: 0,
    working: 1,
    coordinating: 1,
    assigned: 2,
    completed: 3,
    idle: 4
  }
  return spaceNodes.value
    .map(node => {
      const mission = activeMissionByAgent.value.get(node.agent_id)
      return {
        node,
        mission,
        currentTask: node.current_task || mission?.active_step?.title || mission?.mission_title || '',
        projectName: mission?.project_name || '未绑定项目',
        updatedAt: mission?.updated_at || spaceGraph.value?.updated_at || '',
        activeMissionCount: node.active_mission_count || (mission ? 1 : 0)
      }
    })
    .sort((left, right) => (
      (statusRank[left.node.status] ?? 9) - (statusRank[right.node.status] ?? 9)
      || (laneRank[left.node.lane] ?? 9) - (laneRank[right.node.lane] ?? 9)
      || left.node.name.localeCompare(right.node.name, 'zh-CN')
    ))
})
const agentStatusSummary = computed(() => {
  const summary = { working: 0, assigned: 0, blocked: 0, idle: 0 }
  agentStatusRows.value.forEach(row => {
    if (row.node.status === 'blocked') summary.blocked += 1
    else if (row.node.status === 'assigned') summary.assigned += 1
    else if (['working', 'coordinating'].includes(row.node.status)) summary.working += 1
    else summary.idle += 1
  })
  return summary
})
const selectedProjectFilter = computed(() =>
  projects.value.find(project => project.id === projectFilter.value)
)
const reversedEvents = computed(() =>
  [...(selectedMission.value?.events || [])].reverse().slice(0, 30)
)
const canReviewMemory = computed(() => auth.isAdmin && memoryReviewAllowed.value)
const availableProjects = computed(() =>
  projects.value.filter(project =>
    (project.project_type || project.type || 'software') === newMission.mission_type
  )
)

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    received: '待规划',
    planning: '规划中',
    awaiting_approval: '等待批准',
    dispatching: '调度中',
    running: '执行中',
    waiting_feedback: '等待反馈',
    evaluating: '评估中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消'
  }
  return labels[status] || status
}

function stepStatusLabel(status: string) {
  const labels: Record<string, string> = {
    draft: '待批准',
    awaiting_approval: '等待步骤审批',
    ready: '待执行',
    running: '执行中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消'
  }
  return labels[status] || status
}

function compensationStatusLabel(status: string) {
  const labels: Record<string, string> = {
    pending_approval: '等待补偿审批',
    ready: '等待执行',
    running: '补偿执行中',
    completed: '已补偿',
    failed: '补偿失败',
    rejected: '已拒绝',
    cancelled: '已取消'
  }
  return labels[status] || status
}

function lifecycleStateLabel(state: LifecycleStageState) {
  return {
    pending: '待进入',
    active: '进行中',
    completed: '已完成',
    warning: '需关注',
    blocked: '已阻断'
  }[state]
}

function effectStatusLabel(status: string) {
  return {
    applied: '已生效',
    not_applied: '未生效',
    unknown: '状态未知',
    reverted: '已恢复'
  }[status] || status
}

function stepDependencyLabel(stepId: string) {
  const step = selectedMission.value?.steps.find(item => item.id === stepId)
  return step ? `#${step.order_index} ${step.title}` : stepId.slice(0, 8)
}

function statusTone(status: string) {
  if (status === 'completed') return 'success'
  if (status === 'failed' || status === 'cancelled') return 'danger'
  if (status === 'awaiting_approval' || status === 'waiting_feedback') return 'warning'
  if (status === 'received' || status === 'draft' || status === 'ready') return 'muted'
  return 'active'
}

function tagType(status: string): 'success' | 'warning' | 'danger' | 'info' | 'primary' {
  if (status === 'completed') return 'success'
  if (status === 'failed' || status === 'cancelled') return 'danger'
  if (status === 'awaiting_approval' || status === 'waiting_feedback') return 'warning'
  if (status === 'received' || status === 'draft' || status === 'ready') return 'info'
  return 'primary'
}

function taskTypeLabel(type: string) {
  const labels: Record<string, string> = {
    architecture: '架构',
    backend: '后端',
    frontend: '前端',
    testing: '测试',
    research: '研究',
    knowledge: '知识',
    writing: '撰写',
    operations: '运维',
    finance: '财务',
    sales: '销售',
    review: '评估',
    coordination: '统筹',
    general: '通用'
  }
  return labels[type] || type
}

function missionTypeLabel(type?: string) {
  if (type === 'document') return '文档撰写'
  if (type === 'software') return '程序开发'
  return '历史任务'
}

function projectType(project: Project) {
  return String(project.project_type || project.type || project.context?.project_type || 'software')
}

function sourceLabel(source: string) {
  return {
    'command-center': '指挥中心',
    'project-dev': '程序开发',
    'project-doc': '文档撰写',
    manual: '手动',
    system: '系统',
    airflow: '调度'
  }[source] || source || '来源未知'
}

function ledgerStatusLabel(status: string) {
  return {
    pending: '待处理',
    assigned: '已分配',
    in_progress: '进行中',
    review: '审查中',
    testing: '测试中',
    done: '已完成',
    archived: '已归档'
  }[status] || status
}

function intentLabel(type: string) {
  const labels: Record<string, string> = {
    discussion: '一般讨论',
    software_project: '程序开发',
    document_project: '文档撰写',
    mission_control: '任务控制',
    clarification_required: '待澄清'
  }
  return labels[type] || type
}

function intentTagType(type: string): 'success' | 'warning' | 'danger' | 'info' | 'primary' {
  if (type === 'discussion') return 'info'
  if (type === 'clarification_required') return 'warning'
  if (type === 'mission_control') return 'success'
  return 'primary'
}

function sourceTypeLabel(type: string) {
  const labels: Record<string, string> = {
    profile: '用户档案',
    profile_fact: '关键事实',
    project: '项目背景',
    knowledge: '知识库',
    agent_memory: '智能体记忆'
  }
  return labels[type] || type
}

function contextStatusLabel(status: string) {
  const labels: Record<string, string> = {
    ready: '已冻结',
    empty: '内容为空',
    degraded: '检索降级',
    failed: '检索失败',
    pending: '检索中'
  }
  return labels[status] || status
}

function contextTagType(status: string): 'success' | 'warning' | 'danger' | 'info' {
  if (status === 'ready') return 'success'
  if (status === 'degraded' || status === 'empty') return 'warning'
  if (status === 'failed') return 'danger'
  return 'info'
}

function planQualityLabel(status: string) {
  return {
    pass: '计划质检通过',
    warning: '计划有警告',
    blocked: '计划被阻断'
  }[status] || status || '未检查'
}

function planQualityTagType(status: string): 'success' | 'warning' | 'danger' | 'info' {
  if (status === 'pass') return 'success'
  if (status === 'warning') return 'warning'
  if (status === 'blocked') return 'danger'
  return 'info'
}

function executionQualityLabel(status: string) {
  return {
    pass: '执行证据通过',
    warning: '执行证据有警告',
    blocked: '执行证据不足'
  }[status] || status || '未检查'
}

function executionQualityTagType(status: string): 'success' | 'warning' | 'danger' | 'info' {
  if (status === 'pass') return 'success'
  if (status === 'warning') return 'warning'
  if (status === 'blocked') return 'danger'
  return 'info'
}

function hasStepContract(step: CommandCenterStep) {
  return Boolean(
    step.tool_requirements?.length ||
    step.required_tools?.length ||
    step.deliverables?.length ||
    step.acceptance_criteria?.length ||
    step.evidence_required?.length
  )
}

function fallbackTools(step: CommandCenterStep) {
  if (step.tool_requirements?.length) return []
  return step.required_tools || []
}

function memoryTargetLabel(target: string) {
  return {
    profile: '用户档案',
    project: '项目知识',
    agent: '智能体经验'
  }[target] || target
}

function importanceLabel(importance: string) {
  return {
    critical: '关键',
    high: '重要',
    normal: '常规',
    low: '低'
  }[importance] || importance
}

function confidenceLabel(confidence: number) {
  return `${Math.round(Math.max(0, Math.min(Number(confidence) || 0, 1)) * 100)}%`
}

function agentName(agentId: string) {
  return agentNames[agentId] || agentId || '系统'
}

function riskLabel(risk?: string) {
  return { low: '低', medium: '中', high: '高' }[risk || ''] || risk || '中'
}

function eventLabel(type: string) {
  const labels: Record<string, string> = {
    mission_received: '任务已接收',
    context_pack_bound: '背景上下文已冻结',
    context_retrieval_degraded: '背景检索已降级',
    planning_started: '开始制定计划',
    planning_resumed: '继续制定计划',
    plan_proposed: '计划已提交',
    plan_approved: '计划已批准',
    plan_rejected: '计划已驳回',
    state_changed: '状态更新',
    step_started: '步骤开始',
    step_completed: '步骤完成',
    step_failed: '步骤失败',
    step_requeued: '步骤已恢复',
    feedback_received: '收到反馈',
    evaluation_started: '开始评估',
    mission_completed: '任务完成',
    memory_candidates_proposed: '长期记忆候选已生成',
    memory_candidate_generation_failed: '长期记忆提炼降级',
    memory_candidate_published: '长期记忆已审核发布',
    memory_candidate_rejected: '长期记忆候选已驳回',
    mission_blocked: '任务阻塞',
    mission_cancelled: '任务取消'
  }
  return labels[type] || type
}

function eventType(event: CommandCenterEvent): 'primary' | 'success' | 'warning' | 'danger' | 'info' {
  if (
    event.event_type.includes('completed') ||
    event.event_type.includes('published') ||
    event.event_type === 'plan_approved'
  ) return 'success'
  if (event.event_type.includes('failed') || event.event_type.includes('blocked')) return 'danger'
  if (
    event.event_type.includes('feedback') ||
    event.event_type.includes('degraded') ||
    event.event_type.includes('rejected') ||
    event.event_type === 'plan_proposed'
  ) return 'warning'
  return 'primary'
}

function spaceStatusTone(status: string) {
  if (status === 'coordinating' || status === 'working') return 'active'
  if (status === 'completed') return 'success'
  if (status === 'blocked') return 'danger'
  if (status === 'assigned') return 'warning'
  return 'idle'
}

function spaceStatusLabel(status: string) {
  const labels: Record<string, string> = {
    coordinating: '统筹中',
    working: '执行中',
    assigned: '已分配',
    completed: '已完成',
    blocked: '阻塞',
    idle: '待命'
  }
  return labels[status] || status || '待命'
}

function spaceTagType(status: string): 'success' | 'warning' | 'danger' | 'info' | 'primary' {
  if (status === 'completed') return 'success'
  if (status === 'blocked') return 'danger'
  if (status === 'assigned') return 'warning'
  if (status === 'coordinating' || status === 'working') return 'primary'
  return 'info'
}

function selectSpaceNode(nodeId: string) {
  selectedSpaceNodeId.value = nodeId
}

function spaceNodeStyle(node: CommandCenterSpaceNode) {
  return {
    left: `${node.x}%`,
    top: `${node.y}%`,
  }
}

function spaceEdgeStyle(edge: CommandCenterSpaceEdge) {
  const source = spaceNodeMap.value.get(edge.from)
  const target = spaceNodeMap.value.get(edge.to)
  if (!source || !target) return {}
  const dx = target.x - source.x
  const dy = target.y - source.y
  const length = Math.sqrt(dx * dx + dy * dy)
  const angle = Math.atan2(dy, dx) * 180 / Math.PI
  return {
    left: `${source.x}%`,
    top: `${source.y}%`,
    width: `${length}%`,
    transform: `rotate(${angle}deg)`,
  }
}

function formatTime(value?: string) {
  if (!value) return ''
  return new Date(value).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

function compactText(value?: string, limit = 360) {
  const text = String(value || '').replace(/\s+/g, ' ').trim()
  return text.length > limit ? `${text.slice(0, limit)}…` : text
}

async function refreshMissions() {
  const [workbenchData, missionData] = await Promise.all([
    listCommandCenterTaskWorkbench({
      status: statusFilter.value || undefined,
      mission_type: missionTypeFilter.value || undefined,
      project_id: projectFilter.value || undefined,
      agent_id: agentFilter.value || undefined,
      source: sourceFilter.value || undefined,
      search: workbenchSearch.value || undefined,
      limit: 150
    }),
    listCommandCenterMissions({
      status: statusFilter.value || undefined,
      limit: 150
    })
  ])
  workbenchItems.value = workbenchData.items
  missions.value = missionData.missions
  const selectedMissionIsVisible = workbenchItems.value.some(
    item => item.mission_id === selectedMissionId.value
  )
  if (selectedMissionId.value && selectedMissionIsVisible) {
    await refreshSelected()
    return
  }
  if (!workbenchItems.value.length) {
    selectedMissionId.value = ''
    selectedMission.value = undefined
    return
  }
  selectedMissionId.value = workbenchItems.value[0].mission_id
  await refreshSelected()
}

async function refreshSelected() {
  if (!selectedMissionId.value) {
    selectedMission.value = undefined
    return
  }
  selectedMission.value = await getCommandCenterMission(selectedMissionId.value)
}

async function refreshSpace() {
  spaceGraph.value = await getCommandCenterAgentSpace({
    mission_id: selectedMissionId.value || undefined
  })
  if (!spaceNodeMap.value.has(selectedSpaceNodeId.value)) {
    selectedSpaceNodeId.value = 'optimus'
  }
}

async function refreshMemoryCandidates(silent = false) {
  if (!silent) memoryLoading.value = true
  try {
    const data = await listCommandCenterMemoryCandidates({
      status: 'pending_review',
      limit: 50
    })
    memoryCandidates.value = data.candidates
    memoryReviewAllowed.value = data.can_review
    Object.assign(summary.memory_candidates, data.summary)
  } finally {
    if (!silent) memoryLoading.value = false
  }
}

async function refreshRoutedMessages() {
  const data = await listCommandCenterMessages({ limit: 30 })
  routedMessages.value = data.messages
}

async function refreshProjects() {
  const data = await getProjects()
  projects.value = data.projects
}

async function refreshAll(silent = false) {
  if (!silent) loading.value = true
  try {
    const productionHealthRequest = auth.isAdmin
      ? getCommandCenterProductionHealth().catch(() => undefined)
      : Promise.resolve(undefined)
    const [summaryData, healthData] = await Promise.all([
      getCommandCenterSummary(),
      productionHealthRequest,
      refreshMissions(),
      refreshMemoryCandidates(true),
      refreshRoutedMessages()
    ])
    Object.assign(summary, summaryData)
    productionHealth.value = healthData
    await refreshSelected()
    await refreshSpace()
  } finally {
    if (!silent) loading.value = false
  }
}

async function selectMission(missionId: string) {
  selectedMissionId.value = missionId
  await refreshSelected()
  await refreshSpace()
}

async function createMission() {
  if (!newMission.project_id) {
    ElMessage.warning('请先选择任务所属项目')
    return
  }
  creating.value = true
  try {
    const response = await createCommandCenterMission({
      title: newMission.title.trim() || undefined,
      project_id: newMission.project_id,
      mission_type: newMission.mission_type,
      objective: newMission.objective.trim()
    })
    newMission.title = ''
    newMission.project_id = ''
    newMission.objective = ''
    selectedMissionId.value = response.mission.id
    ElMessage.success('任务已交给擎天柱，正在生成审批计划')
    await refreshAll(true)
  } finally {
    creating.value = false
  }
}

async function approveSelected() {
  if (!selectedMission.value) return
  actionLoading.value = true
  try {
    await approveCommandCenterMission(selectedMission.value.id, decisionComment.value.trim())
    decisionComment.value = ''
    ElMessage.success('计划已批准，智能体开始执行')
    await refreshAll(true)
  } finally {
    actionLoading.value = false
  }
}

async function rejectSelected() {
  if (!selectedMission.value) return
  if (!decisionComment.value.trim()) {
    ElMessage.warning('请填写调整要求')
    return
  }
  actionLoading.value = true
  try {
    await rejectCommandCenterMission(selectedMission.value.id, decisionComment.value.trim())
    decisionComment.value = ''
    ElMessage.success('已退回擎天柱重新规划')
    await refreshAll(true)
  } finally {
    actionLoading.value = false
  }
}

async function approveStepApproval(step: CommandCenterStep) {
  if (!selectedMission.value || !step.step_approval) return
  try {
    await ElMessageBox.confirm(
      `即将授权“${step.title}”。授权仅绑定当前合同快照且只能消费一次，请确认影响资源和回滚方案。`,
      '确认高风险步骤',
      {
        confirmButtonText: '批准本次执行',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
  } catch {
    return
  }
  stepApprovalLoadingId.value = step.id
  try {
    await approveCommandCenterStep(
      selectedMission.value.id,
      step.id,
      step.step_approval,
      '已在指挥中心确认当前合同快照'
    )
    ElMessage.success('步骤已授权，将在有效期内执行')
    await refreshAll(true)
  } finally {
    stepApprovalLoadingId.value = ''
  }
}

async function rejectStepApproval(step: CommandCenterStep) {
  if (!selectedMission.value || !step.step_approval) return
  let comment = ''
  try {
    const response = await ElMessageBox.prompt(
      `拒绝“${step.title}”后任务将暂停并等待调整。`,
      '拒绝高风险步骤',
      {
        confirmButtonText: '确认拒绝',
        cancelButtonText: '取消',
        inputPlaceholder: '请输入拒绝原因',
        inputValidator: value => Boolean(value?.trim()) || '拒绝原因不能为空',
        type: 'warning'
      }
    )
    comment = response.value.trim()
  } catch {
    return
  }
  stepApprovalLoadingId.value = step.id
  try {
    await rejectCommandCenterStep(
      selectedMission.value.id,
      step.id,
      step.step_approval,
      comment
    )
    ElMessage.success('步骤已拒绝，任务等待调整')
    await refreshAll(true)
  } finally {
    stepApprovalLoadingId.value = ''
  }
}

async function approveCompensation(compensation: CommandCenterCompensation) {
  if (!selectedMission.value) return
  try {
    await ElMessageBox.confirm(
      `即将执行对“${compensation.resource}”的补偿操作。该操作本身可能产生副作用，请确认补偿说明和合同指纹。`,
      '确认补偿执行',
      {
        confirmButtonText: '批准补偿',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
  } catch {
    return
  }
  compensationLoadingId.value = compensation.id
  try {
    await approveCommandCenterCompensation(
      selectedMission.value.id,
      compensation,
      '已确认当前补偿合同快照'
    )
    ElMessage.success('补偿已批准，等待恢复执行器处理')
    await refreshAll(true)
  } finally {
    compensationLoadingId.value = ''
  }
}

async function rejectCompensation(compensation: CommandCenterCompensation) {
  if (!selectedMission.value) return
  let comment = ''
  try {
    const response = await ElMessageBox.prompt(
      '拒绝补偿后原副作用将保持未解决状态，原步骤不会自动重试。',
      '拒绝补偿',
      {
        confirmButtonText: '确认拒绝',
        cancelButtonText: '取消',
        inputPlaceholder: '请输入拒绝原因或人工处理方案',
        inputValidator: value => Boolean(value?.trim()) || '原因不能为空',
        type: 'warning'
      }
    )
    comment = response.value.trim()
  } catch {
    return
  }
  compensationLoadingId.value = compensation.id
  try {
    await rejectCommandCenterCompensation(
      selectedMission.value.id,
      compensation,
      comment
    )
    ElMessage.success('补偿已拒绝，任务保持阻塞')
    await refreshAll(true)
  } finally {
    compensationLoadingId.value = ''
  }
}

async function sendFeedback() {
  if (!selectedMission.value || !feedbackText.value.trim()) return
  actionLoading.value = true
  try {
    await sendCommandCenterFeedback(selectedMission.value.id, feedbackText.value.trim())
    feedbackText.value = ''
    ElMessage.success('反馈已提交，任务继续推进')
    await refreshAll(true)
  } finally {
    actionLoading.value = false
  }
}

async function publishMemoryCandidate(candidate: CommandCenterMemoryCandidate) {
  let editedContent = candidate.content
  try {
    const result = await ElMessageBox.prompt(
      '可在发布前修订内容。发布后将进入后续任务的背景检索。',
      `审核长期记忆：${candidate.title}`,
      {
        inputValue: candidate.content,
        inputType: 'textarea',
        inputPlaceholder: '长期保留的事实或经验',
        confirmButtonText: '采纳并发布',
        cancelButtonText: '取消',
        inputValidator: value => Boolean(String(value || '').trim()) || '记忆内容不能为空'
      }
    )
    editedContent = String(result.value || '').trim()
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    throw error
  }

  memoryActionId.value = candidate.id
  try {
    await approveCommandCenterMemoryCandidate(candidate.id, {
      content: editedContent,
      comment: editedContent === candidate.content ? '管理员确认发布' : '管理员修订后发布'
    })
    ElMessage.success('长期记忆已审核发布，将用于后续任务检索')
    await refreshAll(true)
  } finally {
    memoryActionId.value = ''
  }
}

async function rejectMemoryCandidate(candidate: CommandCenterMemoryCandidate) {
  let comment = ''
  try {
    const result = await ElMessageBox.prompt(
      '请说明该内容不应进入长期记忆的原因。',
      `驳回候选：${candidate.title}`,
      {
        inputType: 'textarea',
        inputPlaceholder: '例如：一次性状态、证据不足或内容重复',
        confirmButtonText: '确认驳回',
        cancelButtonText: '取消',
        inputValidator: value => Boolean(String(value || '').trim()) || '必须填写驳回原因'
      }
    )
    comment = String(result.value || '').trim()
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    throw error
  }

  memoryActionId.value = candidate.id
  try {
    await rejectCommandCenterMemoryCandidate(candidate.id, { comment })
    ElMessage.success('长期记忆候选已驳回')
    await refreshAll(true)
  } finally {
    memoryActionId.value = ''
  }
}

async function cancelSelected() {
  if (!selectedMission.value) return
  await ElMessageBox.confirm(
    `确认取消任务“${selectedMission.value.title}”？`,
    '取消任务',
    { type: 'warning', confirmButtonText: '确认取消', cancelButtonText: '返回' }
  )
  actionLoading.value = true
  try {
    await cancelCommandCenterMission(selectedMission.value.id, '用户从指挥中心取消')
    ElMessage.success('任务已取消')
    await refreshAll(true)
  } finally {
    actionLoading.value = false
  }
}

watch(autoRefresh, enabled => {
  if (refreshTimer) window.clearInterval(refreshTimer)
  refreshTimer = enabled
    ? window.setInterval(() => refreshAll(true), 5000)
    : undefined
})

watch(
  () => newMission.mission_type,
  () => {
    if (!availableProjects.value.some(project => project.id === newMission.project_id)) {
      newMission.project_id = ''
    }
  }
)

onMounted(async () => {
  await refreshProjects()
  await refreshAll()
  const missionId = typeof route.query.mission_id === 'string' ? route.query.mission_id : ''
  if (missionId) await selectMission(missionId)
  refreshTimer = window.setInterval(() => {
    if (autoRefresh.value) refreshAll(true)
  }, 5000)
})

onBeforeUnmount(() => {
  if (refreshTimer) window.clearInterval(refreshTimer)
})
</script>

<style scoped>
.command-center {
  color: var(--text-primary);
  min-width: 0;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 14px;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 9px;
}

.title-row .el-icon {
  color: var(--view-color);
  font-size: 22px;
}

.page-header h1 {
  margin: 0;
  font-size: 22px;
  line-height: 1.35;
  letter-spacing: 0;
}

.page-header p,
.section-title span,
.optimus-profile span,
.panel-heading span {
  color: var(--text-secondary);
  font-size: 12px;
}

.page-header p {
  margin: 5px 0 0;
}

.live-indicator {
  border: 1px solid rgba(63, 185, 80, 0.4);
  color: #56d364;
  padding: 2px 7px;
  border-radius: 4px;
  font-size: 11px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.summary-strip {
  display: grid;
  grid-template-columns: repeat(9, minmax(0, 1fr));
  border: 1px solid var(--line-color);
  background: var(--panel-bg);
  margin-bottom: 10px;
}

.reliability-strip {
  display: grid;
  grid-template-columns: 1.15fr repeat(5, minmax(0, 1fr));
  gap: 1px;
  margin-bottom: 10px;
  border: 1px solid rgba(63, 185, 80, 0.32);
  background: var(--line-color);
}

.reliability-strip.degraded {
  border-color: rgba(248, 81, 73, 0.48);
}

.reliability-strip > div {
  min-width: 0;
  padding: 9px 12px;
  background: var(--panel-bg);
}

.reliability-strip > div:not(.reliability-title) {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.reliability-strip span,
.reliability-strip small {
  color: var(--text-secondary);
  font-size: 11px;
}

.reliability-strip strong {
  font-size: 13px;
}

.reliability-strip strong.danger {
  color: #f85149;
}

.reliability-title {
  display: flex;
  align-items: center;
  gap: 7px;
}

.reliability-title .el-icon {
  color: #56d364;
}

.reliability-title span {
  color: var(--text-primary);
  font-weight: 600;
  font-size: 12px;
}

.command-workshop-tabs {
  min-width: 0;
  padding: 0 14px;
  border: 1px solid var(--line-color);
  border-bottom: 0;
  background: var(--panel-bg);
}

.command-workshop-tabs :deep(.el-tabs__header) {
  margin: 0;
}

.command-workshop-tabs :deep(.el-tabs__nav-wrap::after) {
  height: 1px;
  background: var(--line-color);
}

.command-workshop-tabs :deep(.el-tabs__item) {
  height: 42px;
  padding: 0 16px;
  color: var(--text-secondary);
  font-size: 13px;
}

.command-workshop-tabs :deep(.el-tabs__item.is-active) {
  color: var(--view-color);
}

.command-workshop-tabs :deep(.el-tabs__content) {
  display: none;
}

.summary-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 66px;
  padding: 0 18px;
  border-right: 1px solid var(--line-color);
}

.summary-item:last-child {
  border-right: 0;
}

.summary-item span {
  color: var(--text-secondary);
  font-size: 12px;
}

.summary-item strong {
  font-size: 24px;
}

.summary-item strong.blue {
  color: var(--view-color);
}

.summary-item strong.amber {
  color: #d29922;
}

.context-summary-value {
  display: flex;
  align-items: flex-end;
  gap: 7px;
}

.context-summary-value small {
  padding-bottom: 3px;
  color: #d29922;
  font-size: 10px;
}

.workspace {
  display: grid;
  grid-template-columns: minmax(250px, 320px) minmax(520px, 1fr) minmax(280px, 340px);
  min-height: calc(100vh - 235px);
  border: 1px solid var(--line-color);
  background: var(--panel-bg);
}

.mission-column,
.optimus-column {
  min-width: 0;
  background: #161b22;
}

.mission-column {
  border-right: 1px solid var(--line-color);
}

.optimus-column {
  border-left: 1px solid var(--line-color);
  padding: 14px;
}

.panel-heading,
.detail-heading,
.section-title,
.step-head,
.optimus-profile,
.action-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.panel-heading {
  height: 54px;
  padding: 0 12px;
  border-bottom: 1px solid var(--line-color);
}

.panel-heading > div {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.panel-heading .el-select {
  width: 112px;
}
.workbench-heading {
  height: auto;
  min-height: 54px;
}

.workbench-filters {
  display: grid;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--line-color);
}

.filter-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.filter-grid .el-select:last-child {
  grid-column: 1 / -1;
}

.project-scope-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 7px 9px;
  border: 1px solid var(--line-color);
  background: #0d1117;
  color: var(--text-secondary);
  font-size: 11px;
}

.project-scope-row strong {
  min-width: 0;
  overflow: hidden;
  color: var(--text-primary);
  text-overflow: ellipsis;
  white-space: nowrap;
}


.mission-list {
  max-height: calc(100vh - 291px);
  overflow-y: auto;
  padding: 8px;
}

.mission-item {
  width: 100%;
  display: block;
  color: inherit;
  background: transparent;
  border: 1px solid transparent;
  border-bottom-color: var(--line-color);
  border-radius: 4px;
  padding: 12px 10px;
  text-align: left;
  cursor: pointer;
}

.mission-item:hover {
  background: var(--view-color-faint);
}

.mission-item.selected {
  border-color: var(--view-color-strong-border);
  background: var(--view-color-soft);
}

.mission-item-head {
  display: grid;
  grid-template-columns: 8px minmax(0, 1fr) auto;
  align-items: center;
  gap: 7px;
}

.mission-item-head strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
}

.status-dot,
.online-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #6e7681;
}

.status-dot.active,
.online-dot {
  background: var(--view-color);
  box-shadow: 0 0 0 3px rgba(var(--view-rgb), 0.1);
}

.status-dot.success {
  background: #3fb950;
}

.status-dot.warning {
  background: #d29922;
}

.status-dot.danger {
  background: #f85149;
}

.mission-meta {
  display: flex;
  justify-content: space-between;
  margin: 9px 0 7px 15px;
  color: #6e7681;
  font-size: 10px;
}

.stacked-meta {
  flex-direction: column;
  gap: 3px;
}

.waiting-reason {
  margin: 0 0 7px 15px;
  color: #d29922;
  font-size: 11px;
  line-height: 1.4;
}

.workbench-foot {
  display: flex;
  justify-content: space-between;
  margin: 6px 0 0 15px;
  color: #8b949e;
  font-size: 10px;
}

.mission-progress {
  height: 3px;
  margin-left: 15px;
  background: #30363d;
}

.mission-progress span {
  display: block;
  height: 100%;
  background: var(--view-color);
  transition: width 0.25s ease;
}

.mission-progress span.completed {
  background: #3fb950;
}

.mission-detail {
  min-width: 0;
  padding: 18px;
  overflow-y: auto;
  max-height: calc(100vh - 235px);
}

.space-panel {
  margin-bottom: 18px;
  border: 1px solid var(--line-color);
  background: #0d1117;
}

.space-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--line-color);
}

.space-heading > div:first-child {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.space-heading strong {
  font-size: 14px;
}

.space-heading span {
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.space-heading-meta {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
}

.space-stage {
  position: relative;
  height: 430px;
  overflow: hidden;
  background:
    linear-gradient(rgba(48, 54, 61, 0.24) 1px, transparent 1px),
    linear-gradient(90deg, rgba(48, 54, 61, 0.24) 1px, transparent 1px),
    radial-gradient(circle at 50% 20%, rgba(var(--view-rgb), 0.14), transparent 36%),
    #0d1117;
  background-size: 72px 72px, 72px 72px, 100% 100%, 100% 100%;
}

.space-lane {
  position: absolute;
  left: 16px;
  right: 16px;
  border-top: 1px solid rgba(139, 148, 158, 0.12);
  pointer-events: none;
}

.space-lane span {
  position: absolute;
  left: 0;
  top: 7px;
  color: #6e7681;
  font-size: 10px;
}

.lane-commander { top: 24%; }
.lane-pm { top: 44%; }
.lane-development { top: 67%; }
.lane-support { top: 88%; }

.space-edge {
  position: absolute;
  z-index: 1;
  height: 1px;
  border-top: 1px solid rgba(139, 148, 158, 0.28);
  transform-origin: left center;
  pointer-events: none;
}

.space-edge.active {
  border-color: var(--view-color);
  box-shadow: 0 0 10px rgba(var(--view-rgb), 0.36);
}

.space-edge.edge-depends_on {
  border-top-style: dashed;
  border-color: rgba(210, 153, 34, 0.72);
}

.space-edge.edge-development {
  border-color: rgba(63, 185, 80, 0.36);
}

.space-node {
  position: absolute;
  z-index: 2;
  width: 118px;
  min-height: 82px;
  display: grid;
  justify-items: center;
  gap: 3px;
  padding: 0 8px 8px;
  color: var(--text-primary);
  background: transparent;
  border: 0;
  cursor: pointer;
  transform: translate(-50%, -50%);
}

.space-node:hover .space-platform,
.space-node.selected .space-platform {
  border-color: var(--view-color);
  box-shadow: 0 0 0 1px rgba(var(--view-rgb), 0.24), 0 16px 38px rgba(1, 4, 9, 0.44);
}

.space-node.commander {
  width: 138px;
}

.space-platform {
  position: absolute;
  left: 50%;
  bottom: 0;
  width: 106px;
  height: 38px;
  border: 1px solid rgba(88, 166, 255, 0.28);
  border-radius: 50%;
  background: linear-gradient(180deg, rgba(33, 38, 45, 0.92), rgba(13, 17, 23, 0.92));
  transform: translateX(-50%) perspective(160px) rotateX(58deg);
}

.space-node.commander .space-platform {
  width: 126px;
  border-color: rgba(var(--view-rgb), 0.75);
  box-shadow: 0 0 18px rgba(var(--view-rgb), 0.28);
}

.space-avatar {
  position: relative;
  z-index: 1;
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  margin-top: 2px;
  border: 1px solid #484f58;
  border-radius: 50%;
  background: #161b22;
  font-size: 17px;
}

.space-status-active .space-avatar {
  border-color: var(--view-color);
  box-shadow: 0 0 0 3px rgba(var(--view-rgb), 0.13);
}

.space-status-success .space-avatar {
  border-color: #3fb950;
}

.space-status-warning .space-avatar {
  border-color: #d29922;
}

.space-status-danger .space-avatar {
  border-color: #f85149;
}

.space-node-body {
  position: relative;
  z-index: 1;
  display: grid;
  gap: 1px;
  max-width: 100%;
  justify-items: center;
  text-align: center;
}

.space-node-body strong,
.space-node-body small {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.space-node-body strong {
  font-size: 12px;
}

.space-node-body small {
  color: var(--text-secondary);
  font-size: 9px;
}

.space-node-progress {
  position: relative;
  z-index: 1;
  width: 72px;
  height: 3px;
  overflow: hidden;
  background: #30363d;
}

.space-node-progress span {
  display: block;
  height: 100%;
  background: var(--view-color);
}

.space-status-success .space-node-progress span {
  background: #3fb950;
}

.space-status-warning .space-node-progress span {
  background: #d29922;
}

.space-status-danger .space-node-progress span {
  background: #f85149;
}

.space-inspector {
  min-height: 72px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 7px 12px;
  align-items: start;
  padding: 12px 14px;
  border-top: 1px solid var(--line-color);
}

.space-inspector > div {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.space-inspector strong {
  font-size: 13px;
}

.space-inspector span,
.space-inspector small,
.space-inspector p {
  color: var(--text-secondary);
  font-size: 11px;
}

.space-inspector p {
  grid-column: 1 / -1;
  margin: 0;
  line-height: 1.45;
}

.space-inspector small {
  grid-column: 1 / -1;
  color: #6e7681;
}

.agent-status-panel {
  display: grid;
  gap: 12px;
  margin-bottom: 18px;
  padding: 14px;
  border: 1px solid var(--line-color);
  background: var(--card-bg);
}

.agent-status-summary {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.agent-status-summary span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-height: 24px;
  padding: 0 8px;
  border: 1px solid var(--line-color);
  color: var(--text-secondary);
  font-size: 11px;
}

.agent-status-summary b {
  color: var(--text-primary);
  font-size: 13px;
}

.agent-status-grid {
  display: grid;
  min-width: 0;
  border-top: 1px solid var(--line-color);
}

.agent-status-row {
  display: grid;
  grid-template-columns: minmax(150px, 1.05fr) 86px minmax(190px, 1.5fr) minmax(120px, .85fr) 92px 112px;
  gap: 12px;
  align-items: center;
  min-width: 0;
  min-height: 46px;
  padding: 8px 0;
  border: 0;
  border-bottom: 1px solid var(--line-color);
  color: var(--text-primary);
  background: transparent;
  text-align: left;
}

.agent-status-row:not(.head) {
  cursor: pointer;
}

.agent-status-row:not(.head):hover,
.agent-status-row.selected {
  background: var(--view-color-faint);
}

.agent-status-row.head {
  min-height: 34px;
  color: var(--text-secondary);
  font-size: 10px;
  font-weight: 700;
}

.agent-status-row > span {
  min-width: 0;
}

.agent-cell {
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-cell.identity {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  gap: 8px;
  align-items: center;
  color: var(--text-primary);
}

.agent-cell.identity i {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border: 1px solid var(--line-color);
  border-radius: 50%;
  background: #161b22;
  font-style: normal;
}

.agent-cell.identity span,
.agent-cell.task {
  display: grid;
  gap: 2px;
}

.agent-cell.identity strong,
.agent-cell.identity small,
.agent-cell.task,
.agent-cell.project,
.agent-cell.time {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-cell.identity strong {
  color: var(--text-primary);
  font-size: 12px;
}

.agent-cell.identity small,
.agent-cell.task small {
  color: var(--text-secondary);
  font-size: 9px;
}

.agent-cell.task {
  color: var(--text-primary);
  line-height: 1.35;
}

.agent-progress-cell {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 32px;
  gap: 6px;
  align-items: center;
}

.agent-progress-cell small {
  color: var(--text-secondary);
  font-size: 10px;
  text-align: right;
}

.detail-heading {
  align-items: flex-start;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--line-color);
}

.detail-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.detail-heading h2 {
  margin: 0;
  font-size: 18px;
}

.detail-heading > div > span {
  color: var(--text-secondary);
  font-size: 11px;
}

.objective-block {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr);
  gap: 14px;
  padding: 16px 0;
  border-bottom: 1px solid var(--line-color);
}

.block-label {
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
}

.objective-block p {
  margin: 0;
  line-height: 1.7;
  white-space: pre-wrap;
}

.governance-overview {
  padding: 18px 0 16px;
  border-bottom: 1px solid var(--line-color);
}

.governance-heading {
  gap: 16px;
}

.trace-identity {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 5px;
}

.trace-identity span {
  padding: 3px 7px;
  border: 1px solid rgba(88, 166, 255, 0.24);
  background: rgba(88, 166, 255, 0.06);
  color: #8c959f;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 9px;
}

.control-point {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr) minmax(180px, 0.8fr);
  gap: 12px;
  align-items: center;
  margin-bottom: 14px;
  padding: 12px;
  border: 1px solid rgba(88, 166, 255, 0.3);
  border-left: 3px solid var(--view-color);
  background: linear-gradient(90deg, rgba(88, 166, 255, 0.1), rgba(13, 17, 23, 0.72));
}

.control-point.tone-warning {
  border-color: rgba(210, 153, 34, 0.42);
  border-left-color: #d29922;
  background: linear-gradient(90deg, rgba(210, 153, 34, 0.1), rgba(13, 17, 23, 0.72));
}

.control-point.tone-danger {
  border-color: rgba(248, 81, 73, 0.42);
  border-left-color: #f85149;
  background: linear-gradient(90deg, rgba(248, 81, 73, 0.1), rgba(13, 17, 23, 0.72));
}

.control-point.tone-success {
  border-color: rgba(63, 185, 80, 0.4);
  border-left-color: #3fb950;
  background: linear-gradient(90deg, rgba(63, 185, 80, 0.09), rgba(13, 17, 23, 0.72));
}

.control-point-icon {
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border: 1px solid currentColor;
  border-radius: 50%;
  color: var(--view-color);
}

.tone-warning .control-point-icon { color: #d29922; }
.tone-danger .control-point-icon { color: #ff7b72; }
.tone-success .control-point-icon { color: #3fb950; }

.control-point > div:nth-child(2) {
  display: grid;
  gap: 3px;
}

.control-point span,
.control-next-action span {
  color: #8c959f;
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.control-point strong {
  font-size: 13px;
}

.control-point p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1.5;
}

.control-next-action {
  min-width: 0;
  padding-left: 12px;
  border-left: 1px solid var(--line-color);
}

.lifecycle-track {
  display: grid;
  grid-template-columns: repeat(8, minmax(96px, 1fr));
  overflow-x: auto;
  padding: 2px 1px 10px;
}

.lifecycle-stage {
  position: relative;
  min-height: 134px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 9px 9px 9px 12px;
  border: 1px solid var(--line-color);
  border-right: 0;
  background: #0d1117;
}

.lifecycle-stage:last-child {
  border-right: 1px solid var(--line-color);
}

.lifecycle-stage::after {
  content: '';
  position: absolute;
  z-index: 2;
  top: 21px;
  right: -5px;
  width: 8px;
  height: 8px;
  border-top: 1px solid #484f58;
  border-right: 1px solid #484f58;
  background: #0d1117;
  transform: rotate(45deg);
}

.lifecycle-stage:last-child::after {
  display: none;
}

.stage-marker {
  width: 24px;
  height: 24px;
  display: grid;
  place-items: center;
  margin-bottom: 4px;
  border: 1px solid #484f58;
  border-radius: 50%;
  color: #8c959f;
  font-size: 10px;
}

.lifecycle-stage.stage-active {
  border-top-color: var(--view-color);
  background: linear-gradient(180deg, rgba(88, 166, 255, 0.11), #0d1117 44%);
}

.stage-active .stage-marker { border-color: var(--view-color); color: var(--view-color); }
.stage-completed .stage-marker { border-color: #3fb950; color: #3fb950; }
.stage-warning .stage-marker { border-color: #d29922; color: #d29922; }
.stage-blocked .stage-marker { border-color: #f85149; color: #ff7b72; }

.stage-state {
  position: absolute;
  top: 10px;
  right: 8px;
  color: #6e7681;
  font-size: 8px;
}

.stage-completed .stage-state { color: #3fb950; }
.stage-active .stage-state { color: var(--view-color); }
.stage-warning .stage-state { color: #d29922; }
.stage-blocked .stage-state { color: #ff7b72; }

.lifecycle-stage strong {
  font-size: 11px;
}

.lifecycle-stage small {
  color: #8c959f;
  font-size: 9px;
}

.lifecycle-stage p {
  margin: auto 0 0;
  color: var(--text-secondary);
  font-size: 9px;
  line-height: 1.45;
}

.governance-metrics {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  border: 1px solid var(--line-color);
}

.governance-metrics > div {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  border-right: 1px solid var(--line-color);
}

.governance-metrics > div:last-child { border-right: 0; }
.governance-metrics span { color: #8c959f; font-size: 9px; }
.governance-metrics strong { font-size: 12px; }
.governance-metrics strong.danger { color: #ff7b72; }

.plan-block,
.timeline-block,
.ledger-block {
  padding-top: 16px;
}

.plan-badges {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
}

.plan-quality-card {
  display: grid;
  gap: 8px;
  margin-top: 10px;
  padding: 10px 12px;
  border: 1px solid var(--line-color);
  background: #0d1117;
}

.plan-quality-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.plan-quality-head strong {
  font-size: 12px;
}

.plan-quality-head span {
  color: var(--text-secondary);
  font-size: 10px;
}

.quality-issue-list {
  display: grid;
  gap: 4px;
  padding-top: 7px;
  border-top: 1px solid var(--line-color);
}

.quality-issue-list strong {
  color: var(--text-primary);
  font-size: 11px;
}

.quality-issue-list span {
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1.45;
}

.quality-issue-list.blocker span {
  color: #ff7b72;
}

.quality-issue-list.warning span {
  color: #d29922;
}

.current-step-card {
  display: grid;
  gap: 5px;
  padding: 12px;
  border: 1px solid var(--line-color);
  background: #0d1117;
}

.current-step-card span,
.current-step-card small {
  color: var(--text-secondary);
  font-size: 11px;
}

.ledger-task-list {
  display: grid;
  gap: 8px;
  margin-top: 10px;
}

.ledger-task-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  padding: 10px 12px;
  border: 1px solid var(--line-color);
  background: #0d1117;
}

.ledger-task-row > div {
  min-width: 0;
}

.ledger-task-row strong,
.ledger-task-row span {
  display: block;
}

.ledger-task-row strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}

.ledger-task-row span {
  color: var(--text-secondary);
  font-size: 11px;
}

.ledger-task-row > div:last-child {
  display: flex;
  align-items: center;
  gap: 6px;
}

.section-title {
  align-items: flex-start;
  margin-bottom: 12px;
}

.section-title > div {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.step-list {
  border-top: 1px solid var(--line-color);
}

.step-row {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr);
  gap: 11px;
  padding: 13px 0;
  border-bottom: 1px solid var(--line-color);
}

.step-index {
  width: 26px;
  height: 26px;
  display: grid;
  place-items: center;
  border: 1px solid #484f58;
  border-radius: 50%;
  color: var(--text-secondary);
  font-size: 11px;
}

.step-index.active {
  border-color: var(--view-color);
  color: var(--view-color);
}

.step-index.success {
  border-color: #3fb950;
  color: #3fb950;
}

.step-index.danger {
  border-color: #f85149;
  color: #f85149;
}

.step-head {
  justify-content: flex-start;
  min-width: 0;
}

.step-head strong {
  font-size: 13px;
}

.step-head > span {
  color: var(--text-secondary);
  font-size: 11px;
}

.step-head .el-tag {
  margin-left: auto;
}

.step-body > p {
  margin: 5px 0 0;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.55;
}

.step-governance-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 7px;
}

.step-governance-meta span {
  max-width: 100%;
  padding: 2px 6px;
  border: 1px solid rgba(139, 148, 158, 0.2);
  color: #8c959f;
  font-size: 9px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.step-governance-meta span.danger {
  border-color: rgba(248, 81, 73, 0.35);
  color: #ff7b72;
}

.step-contract {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
  margin-top: 8px;
}

.step-contract > div {
  min-width: 0;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 5px;
  padding: 6px 8px;
  border: 1px solid rgba(139, 148, 158, 0.18);
  background: rgba(13, 17, 23, 0.72);
}

.step-contract strong {
  color: var(--text-secondary);
  font-size: 10px;
  font-weight: 600;
}

.step-contract span {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-primary);
  font-size: 11px;
}

.contract-chip {
  padding: 1px 6px;
  border: 1px solid rgba(88, 166, 255, 0.26);
  color: var(--view-color) !important;
}

.contract-chip.tool-status-unknown,
.contract-chip.tool-status-planned {
  border-color: rgba(248, 81, 73, 0.36);
  color: #ff7b72 !important;
}

.contract-chip.tool-status-manual {
  border-color: rgba(210, 153, 34, 0.36);
  color: #d29922 !important;
}

.step-result {
  margin-top: 8px;
  padding: 8px 10px;
  border-left: 2px solid var(--view-color-border);
  background: #0d1117;
  font-size: 11px;
}

.step-approval-card {
  display: grid;
  gap: 6px;
  margin-top: 9px;
  padding: 10px;
  border: 1px solid rgba(248, 81, 73, 0.42);
  background: rgba(248, 81, 73, 0.08);
  font-size: 11px;
}

.compensation-card {
  display: grid;
  gap: 6px;
  margin-top: 9px;
  padding: 10px;
  border: 1px solid rgba(210, 153, 34, 0.42);
  background: rgba(210, 153, 34, 0.08);
  font-size: 11px;
}

.compensation-card > div:first-child {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.compensation-card p {
  margin: 0;
  color: var(--text-primary);
  line-height: 1.5;
}

.compensation-card > span {
  color: var(--text-secondary);
  overflow-wrap: anywhere;
}

.effect-journal,
.acceptance-gate-card {
  display: grid;
  gap: 6px;
  margin-top: 9px;
  padding: 9px 10px;
  border: 1px solid rgba(139, 148, 158, 0.2);
  background: rgba(13, 17, 23, 0.72);
}

.subsection-label,
.acceptance-gate-card > div:first-child {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.subsection-label strong,
.acceptance-gate-card strong { font-size: 10px; }
.subsection-label span,
.acceptance-gate-card > span { color: #6e7681; font-size: 9px; }

.effect-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 3px 7px;
  align-items: center;
  padding-top: 6px;
  border-top: 1px solid rgba(139, 148, 158, 0.14);
}

.effect-row strong { min-width: 0; font-size: 10px; }
.effect-row small { grid-column: 2; color: #8c959f; font-size: 9px; overflow-wrap: anywhere; }

.effect-status {
  padding: 1px 5px;
  border: 1px solid #484f58;
  color: #8c959f;
  font-size: 8px;
}

.effect-applied { border-color: rgba(210, 153, 34, 0.4); color: #d29922; }
.effect-unknown { border-color: rgba(248, 81, 73, 0.4); color: #ff7b72; }
.effect-reverted { border-color: rgba(63, 185, 80, 0.4); color: #3fb950; }

.acceptance-gate-card.blocked {
  border-color: rgba(248, 81, 73, 0.38);
  background: rgba(248, 81, 73, 0.06);
}

.acceptance-gate-card p {
  margin: 0;
  color: #d29922;
  font-size: 10px;
  line-height: 1.5;
}

.acceptance-gate-card.blocked p { color: #ff7b72; }

.delivery-gate-card {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 4px 14px;
  align-items: center;
  margin-top: 14px;
  padding: 12px 14px;
  border: 1px solid rgba(63, 185, 80, 0.35);
  border-left: 3px solid #3fb950;
  background: rgba(63, 185, 80, 0.06);
}

.delivery-gate-card.blocked {
  border-color: rgba(248, 81, 73, 0.4);
  border-left-color: #f85149;
  background: rgba(248, 81, 73, 0.06);
}

.delivery-gate-card > div:first-child {
  display: grid;
  gap: 2px;
}

.delivery-gate-card > div:first-child span,
.delivery-gate-card > span { color: #8c959f; font-size: 9px; }
.delivery-gate-card > div:first-child strong { font-size: 13px; }
.delivery-score { color: #3fb950; font-size: 24px; font-weight: 700; }
.delivery-gate-card.blocked .delivery-score { color: #ff7b72; }
.delivery-score small { color: #8c959f; font-size: 9px; }
.delivery-gate-card > p { grid-column: 1 / -1; margin: 3px 0; color: var(--text-secondary); font-size: 10px; line-height: 1.5; }

.step-approval-card > div:first-child {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.step-approval-card p {
  margin: 0;
  color: var(--text-primary);
  line-height: 1.5;
}

.step-approval-card > span {
  color: var(--text-secondary);
}

.step-approval-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
  margin-top: 2px;
}

.step-result span {
  color: #6e7681;
}

.step-result .context-reference {
  display: block;
  margin-top: 3px;
  color: var(--view-color);
}

.step-result p {
  margin: 4px 0 0;
  line-height: 1.5;
}

.error-text {
  color: #ff7b72;
}

.quality-warning-text {
  color: #d29922;
}

.timeline-block :deep(.el-timeline) {
  padding-left: 5px;
}

.timeline-block :deep(.el-timeline-item__content p) {
  margin: 4px 0;
  color: var(--text-secondary);
  font-size: 12px;
}

.timeline-block :deep(.el-timeline-item__content span) {
  color: #6e7681;
  font-size: 11px;
}

.optimus-profile {
  justify-content: flex-start;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--line-color);
}

.optimus-avatar {
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  border: 1px solid var(--view-color-strong-border);
  border-radius: 6px;
  background: var(--view-color-soft);
  color: var(--view-color);
  font-weight: 700;
}

.optimus-profile > div:nth-child(2) {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 3px;
}

.action-panel,
.message-panel {
  padding: 14px 0;
  border-bottom: 1px solid var(--line-color);
}

.action-heading {
  justify-content: flex-start;
  margin-bottom: 10px;
}

.action-heading .el-icon {
  color: var(--view-color);
}

.action-panel > p {
  margin: 0 0 10px;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.55;
}

.context-panel .action-heading .el-tag {
  margin-left: auto;
}

.context-pack-meta {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.context-pack-meta strong {
  overflow: hidden;
  color: var(--view-color);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.context-pack-meta span {
  color: var(--text-secondary);
  font-size: 10px;
}

.context-source-list {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 9px;
}

.context-source-list span {
  padding: 2px 5px;
  border: 1px solid var(--view-color-border);
  border-radius: 3px;
  color: var(--view-color);
  font-size: 10px;
}

.citation-list {
  margin-top: 10px;
  border-top: 1px solid var(--line-color);
}

.citation-list > div {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 5px;
  padding: 6px 0;
  border-bottom: 1px solid var(--line-color);
}

.citation-list span {
  color: var(--view-color);
  font-size: 10px;
}

.citation-list p {
  overflow: hidden;
  margin: 0;
  color: var(--text-secondary);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.memory-panel .action-heading .el-tag {
  margin-left: auto;
}

.conversation-panel .action-heading .el-tag {
  margin-left: auto;
}

.routed-message-list {
  display: flex;
  flex-direction: column;
  gap: 7px;
  max-height: 360px;
  overflow-y: auto;
}

.routed-message-row {
  min-width: 0;
  padding: 8px;
  border: 1px solid var(--line-color);
  background: #0d1117;
}

.routed-message-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 7px;
}

.routed-message-head > span,
.routed-message-row > small {
  color: #6e7681;
  font-size: 9px;
}

.routed-message-row > p,
.routed-response p {
  margin: 6px 0;
  font-size: 11px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.routed-response {
  margin-top: 7px;
  padding: 7px 8px;
  border-left: 2px solid var(--view-color);
  background: var(--view-color-soft);
}

.routed-response strong {
  color: var(--view-color);
  font-size: 10px;
}

.memory-panel-note,
.memory-review-hint {
  margin-bottom: 10px;
}

.memory-empty {
  padding: 13px 8px;
  border: 1px dashed var(--line-color);
  color: var(--text-secondary);
  font-size: 11px;
  text-align: center;
}

.memory-candidate-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 430px;
  overflow-y: auto;
}

.memory-candidate-row {
  min-width: 0;
  padding: 9px;
  border: 1px solid var(--line-color);
  background: #0d1117;
}

.memory-candidate-head {
  display: flex;
  align-items: flex-start;
  gap: 7px;
}

.memory-candidate-head strong {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.memory-candidate-row > p {
  margin: 7px 0;
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.memory-candidate-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 5px 8px;
  color: #6e7681;
  font-size: 9px;
}

.memory-candidate-meta span:first-child {
  max-width: 100%;
  color: var(--view-color);
  overflow-wrap: anywhere;
}

.memory-evidence {
  margin-top: 7px;
  padding-top: 6px;
  border-top: 1px solid var(--line-color);
  color: #6e7681;
  font-size: 9px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.memory-candidate-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 7px;
  margin-top: 8px;
}

.memory-candidate-actions .el-button {
  width: 100%;
  margin: 0;
}

.action-panel :deep(.el-textarea),
.action-panel :deep(.el-input),
.action-panel :deep(.el-select),
.action-panel :deep(.el-segmented) {
  margin-bottom: 9px;
}

.action-panel :deep(.el-segmented) {
  width: 100%;
}

.action-buttons {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.action-buttons .el-button,
.command-panel > .el-button,
.feedback-panel > .el-button {
  width: 100%;
  margin: 0;
}

.message-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.message-row {
  padding-left: 9px;
  border-left: 2px solid #484f58;
}

.message-row.outbound {
  border-left-color: var(--view-color);
}

.message-row > span {
  color: #6e7681;
  font-size: 10px;
}

.message-row p {
  margin: 3px 0 0;
  font-size: 11px;
  line-height: 1.5;
}

@media (max-width: 1280px) {
  .reliability-strip {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .reliability-title {
    grid-column: 1 / -1;
  }

  .summary-strip {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .summary-item:nth-child(-n + 4) {
    border-bottom: 1px solid var(--line-color);
  }

  .summary-item:nth-child(4n) {
    border-right: 0;
  }

  .workspace {
    grid-template-columns: 260px minmax(480px, 1fr);
  }

  .optimus-column {
    grid-column: 1 / -1;
    border-top: 1px solid var(--line-color);
    border-left: 0;
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 16px;
  }

  .optimus-profile {
    grid-column: 1 / -1;
  }

  .space-stage {
    height: 390px;
  }

  .space-node {
    width: 104px;
  }

  .space-node.commander {
    width: 118px;
  }

  .space-platform {
    width: 94px;
  }

  .space-node.commander .space-platform {
    width: 108px;
  }

  .agent-status-row {
    grid-template-columns: minmax(140px, 1fr) 82px minmax(180px, 1.3fr) minmax(100px, .75fr) 86px;
  }

  .agent-status-row > span:nth-child(6) {
    display: none;
  }

  .governance-metrics {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .governance-metrics > div:nth-child(3) { border-right: 0; }

  .governance-metrics > div:nth-child(-n + 3) {
    border-bottom: 1px solid var(--line-color);
  }
}

@media (max-width: 820px) {
  .reliability-strip {
    grid-template-columns: 1fr;
  }

  .page-header {
    flex-direction: column;
    gap: 10px;
  }

  .header-actions {
    align-self: stretch;
    justify-content: flex-end;
  }

  .header-actions .el-switch {
    flex-shrink: 0;
  }

  .summary-strip {
    grid-template-columns: 1fr 1fr;
  }

  .summary-item:nth-child(2n) {
    border-right: 0;
  }

  .summary-item:nth-child(-n + 4) {
    border-bottom: 1px solid var(--line-color);
  }

  .summary-item:nth-child(n + 5):nth-child(-n + 6) {
    border-bottom: 1px solid var(--line-color);
  }

  .workspace {
    display: block;
  }

  .mission-column {
    border-right: 0;
    border-bottom: 1px solid var(--line-color);
  }

  .mission-list,
  .mission-detail {
    max-height: none;
  }

  .optimus-column {
    display: block;
  }

  .space-heading {
    display: grid;
  }

  .space-heading-meta {
    justify-content: flex-start;
  }

  .space-stage {
    height: 520px;
  }

  .space-node {
    width: 96px;
  }

  .space-node-body strong {
    font-size: 11px;
  }

  .space-node-body small {
    display: none;
  }

  .space-inspector {
    grid-template-columns: 1fr;
  }

  .agent-status-summary {
    justify-content: flex-start;
  }

  .agent-status-row.head {
    display: none;
  }

  .agent-status-row {
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 8px;
    padding: 10px 0;
  }

  .agent-status-row > span:nth-child(3),
  .agent-status-row > span:nth-child(4),
  .agent-status-row > span:nth-child(5),
  .agent-status-row > span:nth-child(6) {
    grid-column: 1 / -1;
    display: grid;
  }

  .agent-progress-cell {
    grid-template-columns: minmax(0, 1fr) 36px;
  }

  .step-contract {
    grid-template-columns: 1fr;
  }

  .control-point {
    grid-template-columns: 30px minmax(0, 1fr);
  }

  .control-next-action {
    grid-column: 1 / -1;
    padding: 9px 0 0;
    border-top: 1px solid var(--line-color);
    border-left: 0;
  }

  .trace-identity {
    justify-content: flex-start;
  }

  .governance-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .governance-metrics > div,
  .governance-metrics > div:nth-child(3) {
    border-right: 1px solid var(--line-color);
    border-bottom: 1px solid var(--line-color);
  }

  .governance-metrics > div:nth-child(2n) { border-right: 0; }
  .governance-metrics > div:nth-last-child(-n + 2) { border-bottom: 0; }
}
</style>
