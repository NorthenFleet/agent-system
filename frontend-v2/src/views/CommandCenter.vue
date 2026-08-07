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
        <strong class="amber">{{ summary.pending_approvals }}</strong>
      </div>
      <div class="summary-item">
        <span>待发送回执</span>
        <strong>{{ summary.outbox_pending }}</strong>
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
              <el-tag size="small" effect="plain">
                风险 {{ riskLabel(selectedMission.plan.risk_level) }}
              </el-tag>
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
                  <div
                    v-if="step.work_run_id || step.context_binding || step.result?.output || step.result?.error"
                    class="step-result"
                  >
                    <span v-if="step.work_run_id">执行记录 {{ step.work_run_id }}</span>
                    <span v-if="step.context_binding" class="context-reference">
                      背景 {{ step.context_binding.context_pack_id || '降级' }}
                      V{{ step.context_binding.context_pack_version }}
                      · {{ step.context_binding.citation_count }} 条引用
                    </span>
                    <p v-if="step.result?.output">{{ compactText(step.result.output) }}</p>
                    <p v-if="step.result?.error" class="error-text">{{ compactText(step.result.error) }}</p>
                  </div>
                </div>
              </article>
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
  approveCommandCenterMemoryCandidate,
  cancelCommandCenterMission,
  createCommandCenterMission,
  getCommandCenterMission,
  getCommandCenterSummary,
  listCommandCenterMessages,
  listCommandCenterMemoryCandidates,
  listCommandCenterMissions,
  listCommandCenterTaskWorkbench,
  rejectCommandCenterMemoryCandidate,
  rejectCommandCenterMission,
  sendCommandCenterFeedback,
  type CommandCenterEvent,
  type CommandCenterMemoryCandidate,
  type CommandCenterMission,
  type CommandCenterRoutedMessage,
  type CommandCenterSummary,
  type CommandCenterWorkbenchItem
} from '@/api/commandCenter'
import { getProjects, type Project } from '@/api/projects'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const loading = ref(false)
const creating = ref(false)
const actionLoading = ref(false)
const memoryLoading = ref(false)
const memoryActionId = ref('')
const memoryReviewAllowed = ref(false)
const autoRefresh = ref(true)
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
const selectedMissionId = ref('')
const selectedMission = ref<CommandCenterMission>()
const decisionComment = ref('')
const feedbackText = ref('')
const summary = reactive<CommandCenterSummary>({
  total: 0,
  active: 0,
  pending_approvals: 0,
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
    ready: '待执行',
    running: '执行中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消'
  }
  return labels[status] || status
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
    const [summaryData] = await Promise.all([
      getCommandCenterSummary(),
      refreshMissions(),
      refreshMemoryCandidates(true),
      refreshRoutedMessages()
    ])
    Object.assign(summary, summaryData)
    await refreshSelected()
  } finally {
    if (!silent) loading.value = false
  }
}

async function selectMission(missionId: string) {
  selectedMissionId.value = missionId
  await refreshSelected()
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
  margin-bottom: 14px;
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

.plan-block,
.timeline-block,
.ledger-block {
  padding-top: 16px;
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

.step-result {
  margin-top: 8px;
  padding: 8px 10px;
  border-left: 2px solid var(--view-color-border);
  background: #0d1117;
  font-size: 11px;
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
}

@media (max-width: 820px) {
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
}
</style>
