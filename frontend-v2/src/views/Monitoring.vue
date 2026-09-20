<template>
  <div class="monitoring-page">
    <!-- 页面标题 + WS 状态 + 刷新控制 -->
    <div class="page-header">
      <div class="page-title">
        <h1>📊 实时监控仪表盘</h1>
        <p class="page-desc">Agent 实时状态 · WebSocket 推送 · 系统资源趋势</p>
      </div>
      <div class="page-actions">
        <!-- WebSocket 连接状态指示器 -->
        <span class="ws-indicator" :class="{ connected: wsConnected, connecting: wsConnecting }">
          <span class="ws-dot"></span>
          {{ wsConnected ? '实时推送' : wsConnecting ? '连接中...' : '离线轮询' }}
        </span>
        <!-- 自动刷新开关 -->
        <el-switch
          v-model="autoRefresh"
          active-text="自动刷新"
          inactive-text="手动"
          size="small"
        />
        <!-- 手动刷新按钮 -->
        <el-button
          type="primary"
          size="small"
          :loading="loading"
          :icon="Refresh"
          @click="refreshData"
        >
          刷新
        </el-button>
      </div>
    </div>

    <!-- 全局统计摘要 -->
    <el-row :gutter="16" class="stats-row">
      <el-col :xs="12" :sm="8" :md="4" v-for="stat in summaryStats" :key="stat.label">
        <div class="stat-card" :class="stat.class">
          <div class="stat-icon">{{ stat.icon }}</div>
          <span class="stat-label">{{ stat.label }}</span>
          <span class="stat-value">{{ stat.value }}</span>
        </div>
      </el-col>
    </el-row>

    <div
      v-if="memoryHealth"
      class="memory-health-card"
      :class="`memory-${memoryHealth.status}`"
    >
      <div class="memory-health-header">
        <div>
          <div class="memory-health-title">🧠 记忆系统健康门禁</div>
          <div class="memory-health-subtitle">
            端到端验证飞书身份、3021 权威记忆、检索通道与 graph-memory 部署
          </div>
        </div>
        <el-tag :type="memoryTagType" effect="dark" round>
          {{ memoryStatusLabel(memoryHealth.status) }}
        </el-tag>
      </div>

      <div class="memory-health-metrics">
        <div class="memory-health-metric">
          <span>最后检查</span>
          <strong>{{ memoryHealth.checked_at ? formatDateTime(memoryHealth.checked_at) : '无记录' }}</strong>
          <small>{{ formatAge(memoryHealth.age_seconds) }}</small>
        </div>
        <div class="memory-health-metric">
          <span>权威来源</span>
          <strong>{{ memoryHealth.summary.authority || '未知' }}</strong>
          <small>{{ memoryHealth.summary.identity_bound ? '身份已绑定' : '身份未确认' }}</small>
        </div>
        <div class="memory-health-metric">
          <span>可用记忆</span>
          <strong>{{ memoryHealth.summary.remembered_items ?? 0 }} 条</strong>
          <small>{{ memoryCountsText }}</small>
        </div>
        <div class="memory-health-metric">
          <span>桥接部署</span>
          <strong>{{ memoryHealth.summary.bridge_deployment?.plugin_version || '未知版本' }}</strong>
          <small>{{ memoryHealth.summary.bridge_deployment?.ready ? '版本与哈希已验证' : '部署校验未通过' }}</small>
        </div>
      </div>

      <div class="memory-channel-list">
        <span
          class="memory-channel-chip"
          :class="memoryHealth.matrix?.healthy ? 'channel-ready' : 'channel-failed'"
        >
          <i></i>多 Agent 矩阵 · {{ memoryHealth.matrix?.summary.passed_cases ?? 0 }}/{{ memoryHealth.matrix?.summary.total_cases ?? 0 }}
        </span>
        <span
          v-for="channel in memoryChannelRows"
          :key="channel.name"
          class="memory-channel-chip"
          :class="channel.ready ? 'channel-ready' : 'channel-failed'"
        >
          <i></i>{{ channel.label }} · {{ channel.status }}
        </span>
      </div>

      <div class="memory-operations-row">
        <div class="memory-operation-item" :class="`slo-${primarySlo?.status || 'insufficient_data'}`">
          <span>7 天主门禁 SLO</span>
          <strong>{{ formatPercent(primarySlo?.success_rate_percent) }}</strong>
          <small>
            目标 {{ primarySlo?.target_percent ?? 99 }}% · {{ primarySlo?.sample_count ?? 0 }} 个样本
            <template v-if="memoryHealth.slo?.data_quality.excluded_samples">
              · 排除 {{ memoryHealth.slo.data_quality.excluded_samples }} 个环境无效样本
            </template>
          </small>
        </div>
        <div class="memory-operation-item">
          <span>P95 门禁耗时</span>
          <strong>{{ formatDuration(primarySlo?.p95_duration_ms) }}</strong>
          <small>事件 {{ primarySlo?.incident_count ?? 0 }} · 错误预算 {{ formatPercent(primarySlo?.error_budget_remaining_percent) }}</small>
        </div>
        <div class="memory-operation-item" :class="memoryHealth.drill?.healthy ? 'slo-healthy' : 'slo-breached'">
          <span>非破坏性故障演练</span>
          <strong>{{ memoryHealth.drill?.summary.passed_scenarios ?? 0 }}/{{ memoryHealth.drill?.summary.total_scenarios ?? 0 }}</strong>
          <small>{{ memoryHealth.drill?.checked_at ? `${formatAge(memoryHealth.drill.age_seconds)}完成` : '尚未执行' }}</small>
        </div>
        <div class="memory-operation-item" :class="releaseStatusClass">
          <span>记忆变更发布门禁</span>
          <strong>{{ releaseStatusLabel }}</strong>
          <small v-if="memoryHealth.release?.risk?.label">
            {{ memoryHealth.release.risk.label }} · {{ releaseApprovalModeLabel }}
          </small>
          <small v-if="memoryHealth.release?.status === 'completed'">
            {{ memoryHealth.release.version }} · {{ formatDateTime(memoryHealth.release.completed_at!) }} 完成
          </small>
          <small v-else>{{ memoryHealth.release?.version || '无候选版本' }} · Optimus 灰度后全矩阵</small>
          <el-button
            v-if="canChangeReleaseApproval"
            class="release-approval-button"
            :type="memoryHealth.release?.promotion_ready ? 'danger' : 'warning'"
            plain
            size="small"
            :loading="releaseApproving"
            @click="changeReleaseApproval"
          >
            {{ memoryHealth.release?.promotion_ready ? '撤销审批' : '审批候选' }}
          </el-button>
          <el-button
            class="release-history-button"
            plain
            size="small"
            @click="releaseHistoryVisible = true"
          >
            发布历史
          </el-button>
        </div>
      </div>

      <el-alert
        v-if="memoryHealth.failures.length"
        class="memory-health-alert"
        type="error"
        :closable="false"
        show-icon
        :title="`门禁失败：${memoryFailureText}`"
      />
    </div>

    <!-- Agent 实时状态卡片 -->
    <div class="section-header">
      <h2>🤖 Agent 实时状态</h2>
      <span class="refresh-hint">
        <el-icon><Loading /></el-icon>
        {{ autoRefresh ? '每3秒自动刷新' : `上次刷新: ${lastRefreshTime}` }}
      </span>
    </div>

    <el-row :gutter="16" class="agent-cards-row">
      <el-col
        :xs="24" :sm="12" :md="8" :lg="6"
        v-for="agent in agents"
        :key="agent.agent_id"
      >
        <div class="agent-card" :class="`status-${agent.status}`">
          <!-- 卡片头部：名称 + 状态灯 -->
          <div class="card-header">
            <div class="agent-avatar">{{ agent.agent_name.charAt(0).toUpperCase() }}</div>
            <div class="agent-info">
              <span class="agent-name">{{ agent.agent_name }}</span>
              <span class="agent-id">{{ agent.agent_id }}</span>
            </div>
            <span class="status-badge" :class="agent.status">
              {{ statusLabel(agent.status) }}
            </span>
          </div>

          <!-- 心跳信息 -->
          <div class="card-section heartbeat-section">
            <div class="section-label">💓 心跳</div>
            <div class="section-value">
              {{ agent.last_heartbeat ? formatTime(agent.last_heartbeat) : '--:--:--' }}
              <span class="heartbeat-age" :class="heartbeatAgeClass(agent.heartbeat_age_seconds)">
                {{ heartbeatAgeText(agent.heartbeat_age_seconds) }}
              </span>
            </div>
          </div>

          <!-- CPU / 内存指标 -->
          <div class="card-metrics">
            <div class="metric">
              <div class="metric-header">
                <span class="metric-label">🔥 CPU</span>
                <span class="metric-value" :class="cpuColor(agent.cpu_usage)">
                  {{ agent.cpu_usage != null ? `${agent.cpu_usage.toFixed(1)}%` : '--' }}
                </span>
              </div>
              <el-progress
                :percentage="agent.cpu_usage ?? 0"
                :color="cpuProgressColor(agent.cpu_usage)"
                :stroke-width="6"
                :show-text="false"
              />
            </div>
            <div class="metric">
              <div class="metric-header">
                <span class="metric-label">🧠 内存</span>
                <span class="metric-value" :class="memoryColor(agent.memory_usage)">
                  {{ agent.memory_usage != null ? `${agent.memory_usage.toFixed(1)}%` : '--' }}
                </span>
              </div>
              <el-progress
                :percentage="agent.memory_usage ?? 0"
                :color="memoryProgressColor(agent.memory_usage)"
                :stroke-width="6"
                :show-text="false"
              />
            </div>
          </div>

          <!-- 当前任务 -->
          <div class="card-section task-section" v-if="agent.current_task">
            <div class="section-label">📋 当前任务</div>
            <div class="section-value task-text">{{ agent.current_task }}</div>
          </div>

          <!-- 健康度 -->
          <div class="card-section" v-if="agent.health_score != null">
            <div class="section-label">❤️ 健康度</div>
            <div class="health-score">
              <span class="score-value" :class="healthClass(agent.health_score)">
                {{ agent.health_score.toFixed(0) }}
              </span>
              <span class="score-max">/ 100</span>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>

    <div class="section-header">
      <h2>🖥️ 设备与节点</h2>
      <span class="refresh-hint">{{ devices.length }} 台设备 · 已并入系统监视</span>
    </div>

    <el-row :gutter="16" class="device-cards-row">
      <el-col
        v-for="device in devices"
        :key="device.id"
        :xs="24"
        :sm="12"
        :lg="8"
      >
        <div class="device-card" :class="`status-${device.status || 'unknown'}`">
          <div class="device-header">
            <div>
              <div class="device-name">{{ device.name }}</div>
              <div class="device-address">{{ device.ip }} · {{ device.location || '未知位置' }}</div>
            </div>
            <span class="status-badge" :class="device.status || 'unknown'">
              {{ statusLabel(device.status || 'unknown') }}
            </span>
          </div>

          <div class="device-meta">
            <div>
              <span>系统</span>
              <strong>{{ device.os || '未知' }}</strong>
            </div>
            <div>
              <span>角色</span>
              <strong>{{ device.role || '未设置' }}</strong>
            </div>
            <div>
              <span>端口</span>
              <strong>{{ device.ports?.length ? device.ports.join(', ') : '无' }}</strong>
            </div>
          </div>

          <div class="device-agents">
            <span
              v-for="agent in device.assigned_agents_details || []"
              :key="agent.id"
              class="agent-chip"
            >
              {{ agent.name }}
            </span>
            <span v-if="!device.assigned_agents_details?.length" class="empty-chip">
              暂无绑定智能体
            </span>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- ECharts 图表区域 -->
    <el-row :gutter="16" class="charts-row">
      <!-- CPU 趋势 -->
      <el-col :xs="24" :md="12">
        <div class="chart-card">
          <div class="chart-title">🔥 CPU 使用率趋势</div>
          <div ref="cpuChartRef" class="chart-container"></div>
        </div>
      </el-col>
      <!-- 内存趋势 -->
      <el-col :xs="24" :md="12">
        <div class="chart-card">
          <div class="chart-title">🧠 内存使用率趋势</div>
          <div ref="memoryChartRef" class="chart-container"></div>
        </div>
      </el-col>
      <!-- Agent 在线数趋势 -->
      <el-col :xs="24" :md="12">
        <div class="chart-card">
          <div class="chart-title">🤖 在线 Agent 数</div>
          <div ref="agentsChartRef" class="chart-container"></div>
        </div>
      </el-col>
      <!-- 健康度分布饼图 -->
      <el-col :xs="24" :md="12">
        <div class="chart-card">
          <div class="chart-title">❤️ 健康度分布</div>
          <div ref="healthPieRef" class="chart-container"></div>
        </div>
      </el-col>
    </el-row>

    <el-drawer
      v-model="releaseHistoryVisible"
      title="记忆系统发布历史"
      size="min(520px, 92vw)"
    >
      <el-empty
        v-if="!memoryHealth?.release_history?.length"
        description="暂无发布历史"
      />
      <el-timeline v-else class="release-timeline">
        <el-timeline-item
          v-for="item in memoryHealth.release_history"
          :key="item.release_id"
          :timestamp="item.updated_at ? formatDateTime(item.updated_at) : '时间未知'"
          :type="releaseHistoryType(item.status)"
          placement="top"
        >
          <div class="release-history-card">
            <div class="release-history-title">
              <strong>{{ item.version || item.release_id }}</strong>
              <el-tag :type="releaseHistoryType(item.status)" size="small">
                {{ releaseHistoryStatusLabel(item.status) }}
              </el-tag>
            </div>
            <div>{{ item.risk?.label || '未分级' }} · {{ item.change_type || '未知变更' }}</div>
            <div>发布 ID：{{ item.release_id.slice(-12) }}</div>
            <div>审批：{{ item.approved_by || '未审批' }} · 审计事件 {{ item.event_count }}</div>
            <div v-if="item.execution_status">执行结果：{{ item.execution_status }}</div>
          </div>
        </el-timeline-item>
      </el-timeline>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { Refresh, Loading } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox, ElNotification } from 'element-plus'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import {
  getMonitoringLive,
  getMemorySystemHealth,
  approveMemoryRelease,
  createMonitoringWs,
  revokeMemoryRelease,
  type MemorySystemHealth,
  type MonitoringAgent
} from '@/api/monitoring'
import { getDevices, type DeviceItem } from '@/api/openclaw'
import { useAuthStore } from '@/stores/auth'

// ─── Reactive State ─────────────────────────────────────────────────────────

const agents = ref<MonitoringAgent[]>([])
const devices = ref<DeviceItem[]>([])
const memoryHealth = ref<MemorySystemHealth | null>(null)
const lastMemoryStatus = ref<string | null>(null)
const authStore = useAuthStore()
const releaseApproving = ref(false)
const releaseHistoryVisible = ref(false)
const loading = ref(false)
const wsConnected = ref(false)
const wsConnecting = ref(false)
const autoRefresh = ref(true)
const lastRefreshTime = ref('--:--:--')

let refreshTimer: ReturnType<typeof setInterval> | null = null
let deviceRefreshTimer: ReturnType<typeof setInterval> | null = null
let ws: WebSocket | null = null
let wsReconnectTimer: ReturnType<typeof setTimeout> | null = null

// Chart refs
const cpuChartRef = ref<HTMLDivElement>()
const memoryChartRef = ref<HTMLDivElement>()
const agentsChartRef = ref<HTMLDivElement>()
const healthPieRef = ref<HTMLDivElement>()

// Chart instances
let cpuChart: echarts.ECharts | null = null
let memoryChart: echarts.ECharts | null = null
let agentsChart: echarts.ECharts | null = null
let healthPieChart: echarts.ECharts | null = null

// Historical data for charts
const cpuHistory = ref<{ time: string; name: string; value: number }[]>([])
const memoryHistory = ref<{ time: string; name: string; value: number }[]>([])
const agentCountHistory = ref<{ time: string; count: number }[]>([])

const chartTheme = {
  text: '#c9d1d9',
  muted: '#8b949e',
  line: '#30363d',
  panel: '#161b22',
  card: '#21262d',
  primary: '#58a6ff',
  success: '#3fb950',
  warning: '#d29922',
  danger: '#f85149'
}

function chartBase(): EChartsOption {
  return {
    backgroundColor: 'transparent',
    color: [chartTheme.primary, chartTheme.success, chartTheme.warning, chartTheme.danger, chartTheme.muted],
    textStyle: { color: chartTheme.text },
    legend: { textStyle: { color: chartTheme.muted } }
  }
}

function chartTooltip(trigger: 'axis' | 'item' = 'axis') {
  return {
    trigger,
    backgroundColor: chartTheme.panel,
    borderColor: chartTheme.line,
    textStyle: { color: chartTheme.text }
  }
}

function categoryAxis(data: string[], rotate = 0) {
  return {
    type: 'category' as const,
    data,
    axisLabel: { color: chartTheme.muted, rotate },
    axisLine: { lineStyle: { color: chartTheme.line } },
    axisTick: { lineStyle: { color: chartTheme.line } }
  }
}

function valueAxis(name: string, extra: Record<string, unknown> = {}) {
  return {
    type: 'value' as const,
    name,
    nameTextStyle: { color: chartTheme.muted },
    axisLabel: { color: chartTheme.muted },
    axisLine: { lineStyle: { color: chartTheme.line } },
    splitLine: { lineStyle: { color: chartTheme.line } },
    ...extra
  }
}

// ─── Computed ────────────────────────────────────────────────────────────────

const summaryStats = computed(() => [
  {
    label: '全部',
    value: agents.value.length,
    icon: '🤖',
    class: 'stat-total'
  },
  {
    label: '在线',
    value: agents.value.filter(a => a.status === 'online').length,
    icon: '🟢',
    class: 'stat-online'
  },
  {
    label: '忙碌',
    value: agents.value.filter(a => a.status === 'busy').length,
    icon: '🔵',
    class: 'stat-busy'
  },
  {
    label: '空闲',
    value: agents.value.filter(a => a.status === 'idle').length,
    icon: '🟡',
    class: 'stat-idle'
  },
  {
    label: '离线',
    value: agents.value.filter(a => a.status === 'offline').length,
    icon: '⚫',
    class: 'stat-offline'
  },
  {
    label: '设备',
    value: devices.value.length,
    icon: '🖥️',
    class: 'stat-devices'
  },
  {
    label: '平均CPU',
    value: avgCpu.value,
    icon: '🔥',
    class: 'stat-avg-cpu'
  }
])

const avgCpu = computed(() => {
  const withCpu = agents.value.filter(a => a.cpu_usage != null)
  if (withCpu.length === 0) return '--'
  const sum = withCpu.reduce((s, a) => s + a.cpu_usage!, 0)
  return `${(sum / withCpu.length).toFixed(1)}%`
})

const memoryTagType = computed(() => {
  if (memoryHealth.value?.status === 'healthy') return 'success'
  if (memoryHealth.value?.status === 'stale') return 'warning'
  return 'danger'
})

const memoryChannelLabels: Record<string, string> = {
  local_markdown: 'Markdown',
  openclaw_lexical_index: '词法索引',
  approved_graph_projection: '审批图谱投影',
  native_private_graph: '私有图谱'
}

const memoryChannelRows = computed(() => Object.entries(memoryHealth.value?.summary.channels || {}).map(
  ([name, status]) => ({
    name,
    label: memoryChannelLabels[name] || name,
    status,
    ready: status === 'ready'
  })
))

const memoryCountsText = computed(() => {
  const counts = memoryHealth.value?.summary.counts || {}
  return `事实 ${counts.profile_facts ?? 0} · 项目 ${counts.project_memories ?? 0} · Agent ${counts.agent_memories ?? 0}`
})

const memoryFailureText = computed(() => memoryHealth.value?.failures
  .map(item => item.check || '未知检查')
  .join('、') || '')

const primarySlo = computed(() => memoryHealth.value?.slo?.monitors.primary)

const releaseStatusLabel = computed(() => {
  const release = memoryHealth.value?.release
  if (!release) return '未配置'
  if (release.status === 'completed') return '已验证发布'
  if (release.status === 'execution_failed') return '发布验证失败'
  if (release.promotion_ready) return '允许发布'
  if (release.technical_ready) return '技术就绪 · 待审批'
  return `已阻断 · ${release.blocking_failures.length} 项`
})

const releaseStatusClass = computed(() => {
  const release = memoryHealth.value?.release
  if (release?.status === 'completed') return 'slo-healthy'
  if (release?.status === 'execution_failed') return 'slo-breached'
  if (release?.promotion_ready) return 'slo-healthy'
  if (release?.technical_ready) return 'slo-at_risk'
  return 'slo-breached'
})

const canChangeReleaseApproval = computed(() => {
  const release = memoryHealth.value?.release
  return authStore.isAdmin
    && !!release?.candidate_digest
    && release.technical_ready
    && !release.release_completed
})

const releaseApprovalModeLabel = computed(() => {
  const mode = memoryHealth.value?.release?.risk?.approval_mode
  return mode === 'human-admin-separated' ? '创建与管理员分离审批' : (mode || '人工审批')
})

// ─── Helpers ─────────────────────────────────────────────────────────────────

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    online: '在线',
    busy: '忙碌',
    idle: '空闲',
    offline: '离线',
    unknown: '未知'
  }
  return map[status] || status
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('zh-CN', { hour12: false })
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString('zh-CN', { hour12: false })
}

function formatAge(age: number | null): string {
  if (age == null) return '时间不可用'
  if (age < 60) return `${age} 秒前`
  if (age < 3600) return `${Math.floor(age / 60)} 分钟前`
  return `${(age / 3600).toFixed(1)} 小时前`
}

function formatPercent(value: number | null | undefined): string {
  return value == null ? '数据不足' : `${value.toFixed(value >= 99 ? 2 : 1)}%`
}

function formatDuration(value: number | null | undefined): string {
  if (value == null) return '数据不足'
  if (value < 1000) return `${Math.round(value)} ms`
  return `${(value / 1000).toFixed(1)} 秒`
}

function memoryStatusLabel(status: MemorySystemHealth['status']): string {
  const labels: Record<MemorySystemHealth['status'], string> = {
    healthy: '健康',
    unhealthy: '异常',
    stale: '过期',
    missing: '缺失',
    invalid: '无效'
  }
  return labels[status]
}

function releaseHistoryStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    completed: '已完成',
    rolled_back: '已回滚',
    rollback_failed: '回滚失败',
    failed: '失败',
    ready: '可发布',
    awaiting_approval: '待审批',
    blocked: '已阻断',
    unknown: '未知'
  }
  return labels[status] || status
}

function releaseHistoryType(status: string): 'success' | 'warning' | 'danger' | 'primary' | 'info' {
  if (status === 'completed') return 'success'
  if (status === 'awaiting_approval' || status === 'rolled_back') return 'warning'
  if (status === 'failed' || status === 'rollback_failed' || status === 'blocked') return 'danger'
  if (status === 'ready') return 'primary'
  return 'info'
}

function heartbeatAgeText(age: number | null): string {
  if (age == null) return ''
  if (age < 60) return `${Math.round(age)}s前`
  if (age < 3600) return `${Math.round(age / 60)}m前`
  return `${(age / 3600).toFixed(1)}h前`
}

function heartbeatAgeClass(age: number | null): string {
  if (age == null) return 'age-offline'
  if (age <= 60) return 'age-healthy'
  if (age <= 300) return 'age-warning'
  return 'age-critical'
}

function cpuColor(v: number | null): string {
  if (v == null) return ''
  if (v > 90) return 'danger'
  if (v > 70) return 'warning'
  return 'success'
}

function memoryColor(v: number | null): string {
  if (v == null) return ''
  if (v > 90) return 'danger'
  if (v > 75) return 'warning'
  return 'success'
}

function cpuProgressColor(v: number | null): string {
  if (v == null) return chartTheme.muted
  if (v > 90) return chartTheme.danger
  if (v > 70) return chartTheme.warning
  return chartTheme.success
}

function memoryProgressColor(v: number | null): string {
  if (v == null) return chartTheme.muted
  if (v > 90) return chartTheme.danger
  if (v > 75) return chartTheme.warning
  return chartTheme.primary
}

function healthClass(score: number): string {
  if (score >= 80) return 'score-healthy'
  if (score >= 50) return 'score-warning'
  return 'score-critical'
}

// ─── Data Fetching ───────────────────────────────────────────────────────────

async function fetchMonitoringData() {
  loading.value = true
  try {
    const data = await getMonitoringLive()
    agents.value = data.map(a => ({
      ...a,
      health: computeHealth(a.heartbeat_age_seconds)
    }))

    // Record history for charts
    const now = new Date().toLocaleTimeString('zh-CN', { hour12: false })
    agents.value.forEach(a => {
      if (a.cpu_usage != null) {
        cpuHistory.value.push({ time: now, name: a.agent_name, value: a.cpu_usage })
      }
      if (a.memory_usage != null) {
        memoryHistory.value.push({ time: now, name: a.agent_name, value: a.memory_usage })
      }
    })

    // Keep last 20 data points per chart
    const maxPoints = 20
    cpuHistory.value = cpuHistory.value.slice(-maxPoints * agents.value.length)
    memoryHistory.value = memoryHistory.value.slice(-maxPoints * agents.value.length)

    // Agent count history
    agentCountHistory.value.push({
      time: now,
      count: agents.value.filter(a => a.status === 'online' || a.status === 'busy').length
    })
    agentCountHistory.value = agentCountHistory.value.slice(-maxPoints)

    lastRefreshTime.value = now
    updateCharts()
  } catch {
    ElMessage.error('获取监控数据失败')
  } finally {
    loading.value = false
  }
}

async function fetchDevices() {
  try {
    const data = await getDevices()
    devices.value = data.devices
  } catch {
    ElMessage.error('设备数据加载失败')
  }
}

async function fetchMemoryHealth() {
  try {
    const next = await getMemorySystemHealth()
    const previous = lastMemoryStatus.value
    memoryHealth.value = next
    lastMemoryStatus.value = next.status
    if (previous && previous !== next.status) {
      ElNotification({
        title: next.healthy ? '记忆系统已恢复' : '记忆系统状态变更',
        message: next.healthy ? '所有记忆通道和部署校验已恢复。' : `当前状态：${memoryStatusLabel(next.status)}`,
        type: next.healthy ? 'success' : 'error',
        duration: 8000
      })
    }
  } catch {
    memoryHealth.value = {
      schema_version: 'memory-system-monitor.v1',
      status: 'missing',
      healthy: false,
      checked_at: null,
      age_seconds: null,
      stale_after_seconds: 0,
      summary: {},
      failures: [{ check: 'monitoring_api' }]
    }
  }
}

async function changeReleaseApproval() {
  const release = memoryHealth.value?.release
  if (!release?.candidate_digest || releaseApproving.value) return
  const revoke = release.promotion_ready
  const action = revoke ? '撤销审批' : '审批候选'
  const effect = revoke
    ? '撤销后该候选将恢复为“待审批”，不会改变已验证的代码。'
    : '审批只授权候选进入发布流程，不会立即部署或重启服务。'
  try {
    await ElMessageBox.confirm(
      `${effect}\n\n版本：${release.version}\n风险：${release.risk?.label || '未分级'}\n审批：${releaseApprovalModeLabel.value}\n摘要：${release.candidate_digest.slice(0, 12)}…`,
      action,
      {
        confirmButtonText: `确认${action}`,
        cancelButtonText: '取消',
        type: revoke ? 'warning' : 'info',
        distinguishCancelAndClose: true
      }
    )
  } catch {
    return
  }
  releaseApproving.value = true
  try {
    const decision = revoke
      ? await revokeMemoryRelease(release.candidate_digest)
      : await approveMemoryRelease(release.candidate_digest)
    if (memoryHealth.value) memoryHealth.value.release = decision
    ElMessage.success(revoke ? '已撤销候选审批' : '候选已审批，等待独立发布执行')
  } finally {
    releaseApproving.value = false
  }
}

function computeHealth(ageSeconds: number | null | undefined): MonitoringAgent['health'] {
  if (ageSeconds == null) return 'offline'
  if (ageSeconds <= 60) return 'healthy'
  if (ageSeconds <= 300) return 'warning'
  return 'critical'
}

function refreshData() {
  fetchMonitoringData()
  fetchDevices()
  fetchMemoryHealth()
}

// ─── Auto Refresh (3s interval) ──────────────────────────────────────────────

function startAutoRefresh() {
  stopAutoRefresh()
  refreshTimer = setInterval(() => {
    if (autoRefresh.value) {
      fetchMonitoringData()
    }
  }, 3000)
}

function stopAutoRefresh() {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

function startDeviceRefresh() {
  stopDeviceRefresh()
  deviceRefreshTimer = setInterval(() => {
    fetchDevices()
    fetchMemoryHealth()
  }, 15000)
}

function stopDeviceRefresh() {
  if (deviceRefreshTimer) {
    clearInterval(deviceRefreshTimer)
    deviceRefreshTimer = null
  }
}

// ─── WebSocket ───────────────────────────────────────────────────────────────

function connectWebSocket() {
  const token = localStorage.getItem('jwt_token') || ''
  wsConnecting.value = true

  try {
    ws = createMonitoringWs(token)

    ws.onopen = () => {
      wsConnected.value = true
      wsConnecting.value = false
      console.log('[Monitoring] WebSocket 已连接')
    }

    ws.onmessage = (event: MessageEvent) => {
      try {
        const msg = JSON.parse(event.data)
        handleWsMessage(msg)
      } catch {
        console.warn('[Monitoring] WS消息解析失败', event.data)
      }
    }

    ws.onclose = () => {
      wsConnected.value = false
      wsConnecting.value = false
      console.log('[Monitoring] WebSocket 断开，5秒后重连...')
      wsReconnectTimer = setTimeout(connectWebSocket, 5000)
    }

    ws.onerror = () => {
      wsConnected.value = false
      wsConnecting.value = false
      console.error('[Monitoring] WebSocket 错误')
    }
  } catch {
    wsConnecting.value = false
    console.warn('[Monitoring] WebSocket 初始化失败，降级为轮询模式')
  }
}

function disconnectWebSocket() {
  if (ws) {
    ws.close()
    ws = null
  }
  if (wsReconnectTimer) {
    clearTimeout(wsReconnectTimer)
    wsReconnectTimer = null
  }
  wsConnected.value = false
  wsConnecting.value = false
}

function handleWsMessage(msg: { type?: string; data?: Record<string, unknown> }) {
  if (msg.type === 'agent_status_change' && msg.data?.agent_id) {
    const agent = agents.value.find(a => a.agent_id === msg.data!.agent_id)
    if (agent && msg.data!.to_status) {
      agent.status = msg.data!.to_status as MonitoringAgent['status']
      if (msg.data!.current_task) agent.current_task = msg.data!.current_task as string
    }
  }
  if (msg.type === 'heartbeat_update' && msg.data?.agent_id) {
    const agent = agents.value.find(a => a.agent_id === msg.data!.agent_id)
    if (agent) {
      agent.last_heartbeat = new Date().toISOString()
      agent.heartbeat_age_seconds = 0
      if (msg.data!.cpu_usage != null) agent.cpu_usage = msg.data!.cpu_usage as number
      if (msg.data!.memory_usage != null) agent.memory_usage = msg.data!.memory_usage as number
      agent.health = 'healthy'
      updateCharts()
    }
  }
}

// ─── Charts ──────────────────────────────────────────────────────────────────

function initCharts() {
  nextTick(() => {
    if (cpuChartRef.value) cpuChart = echarts.init(cpuChartRef.value)
    if (memoryChartRef.value) memoryChart = echarts.init(memoryChartRef.value)
    if (agentsChartRef.value) agentsChart = echarts.init(agentsChartRef.value)
    if (healthPieRef.value) healthPieChart = echarts.init(healthPieRef.value)
  })
}

function updateCharts() {
  updateCpuChart()
  updateMemoryChart()
  updateAgentsChart()
  updateHealthPie()
}

function updateCpuChart() {
  if (!cpuChart) return

  // Group by agent name
  const agentNames = [...new Set(agents.value.map(a => a.agent_name))]
  const times = [...new Set(cpuHistory.value.map(d => d.time))]

  const series = agentNames.map(name => ({
    name,
    type: 'line' as const,
    smooth: true,
    data: times.map(t => {
      const point = cpuHistory.value.find(d => d.time === t && d.name === name)
      return point ? point.value : null
    })
  }))

  const option: EChartsOption = {
    ...chartBase(),
    tooltip: chartTooltip('axis'),
    legend: { data: agentNames, bottom: 0 },
    grid: { top: 10, right: 20, bottom: 40, left: 50 },
    xAxis: categoryAxis(times),
    yAxis: valueAxis('CPU %', { max: 100, min: 0 }),
    series
  }
  cpuChart.setOption(option, true)
}

function updateMemoryChart() {
  if (!memoryChart) return

  const agentNames = [...new Set(agents.value.map(a => a.agent_name))]
  const times = [...new Set(memoryHistory.value.map(d => d.time))]

  const series = agentNames.map(name => ({
    name,
    type: 'line' as const,
    smooth: true,
    data: times.map(t => {
      const point = memoryHistory.value.find(d => d.time === t && d.name === name)
      return point ? point.value : null
    })
  }))

  const option: EChartsOption = {
    ...chartBase(),
    tooltip: chartTooltip('axis'),
    legend: { data: agentNames, bottom: 0 },
    grid: { top: 10, right: 20, bottom: 40, left: 50 },
    xAxis: categoryAxis(times),
    yAxis: valueAxis('内存 %', { max: 100, min: 0 }),
    series
  }
  memoryChart.setOption(option, true)
}

function updateAgentsChart() {
  if (!agentsChart) return

  const data = agentCountHistory.value
  const option: EChartsOption = {
    ...chartBase(),
    tooltip: chartTooltip('axis'),
    grid: { top: 10, right: 20, bottom: 30, left: 50 },
    xAxis: categoryAxis(data.map(d => d.time)),
    yAxis: valueAxis('Agent数', { minInterval: 1 }),
    series: [{
      name: '在线Agent',
      type: 'line' as const,
      smooth: true,
      areaStyle: { opacity: 0.3 },
      data: data.map(d => d.count),
      itemStyle: { color: chartTheme.primary }
    }]
  }
  agentsChart.setOption(option, true)
}

function updateHealthPie() {
  if (!healthPieChart) return

  const counts = {
    healthy: agents.value.filter(a => a.health === 'healthy' || (a.health_score != null && a.health_score >= 80)).length,
    warning: agents.value.filter(a => a.health === 'warning' || (a.health_score != null && a.health_score >= 50 && a.health_score < 80)).length,
    critical: agents.value.filter(a => a.health === 'critical' || (a.health_score != null && a.health_score < 50)).length,
    offline: agents.value.filter(a => a.status === 'offline').length
  }

  const option: EChartsOption = {
    ...chartBase(),
    tooltip: chartTooltip('item'),
    legend: { bottom: 0, data: ['健康', '警告', '严重', '离线'] },
    series: [{
      name: '健康度',
      type: 'pie' as const,
      radius: ['40%', '70%'],
      avoidLabelOverlap: true,
      itemStyle: { borderRadius: 6, borderColor: chartTheme.card, borderWidth: 2 },
      label: { show: true, formatter: '{b}: {c}', color: chartTheme.text },
      data: [
        { value: counts.healthy, name: '健康', itemStyle: { color: chartTheme.success } },
        { value: counts.warning, name: '警告', itemStyle: { color: chartTheme.warning } },
        { value: counts.critical, name: '严重', itemStyle: { color: chartTheme.danger } },
        { value: counts.offline, name: '离线', itemStyle: { color: chartTheme.muted } }
      ]
    }]
  }
  healthPieChart.setOption(option, true)
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await Promise.all([fetchMonitoringData(), fetchDevices(), fetchMemoryHealth()])
  initCharts()
  startAutoRefresh()
  startDeviceRefresh()
  connectWebSocket()
})

onUnmounted(() => {
  stopAutoRefresh()
  stopDeviceRefresh()
  disconnectWebSocket()
  cpuChart?.dispose()
  memoryChart?.dispose()
  agentsChart?.dispose()
  healthPieChart?.dispose()
})
</script>

<style scoped>
.monitoring-page {
  min-height: 100%;
  color: var(--text-primary);
  background: transparent;
}

/* ─── Page Header ─────────────────────────────────────────────── */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 12px;
}

.page-title h1 {
  margin: 0 0 4px;
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
}

.page-desc {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary);
}

.page-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* ─── WS Indicator ────────────────────────────────────────────── */
.ws-indicator {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary);
  padding: 4px 10px;
  border-radius: 12px;
  border: 1px solid var(--line-color);
  background: var(--panel-bg);
  transition: all 0.3s;
}

.ws-indicator.connected {
  color: #3fb950;
  border-color: rgba(63, 185, 80, 0.28);
  background: rgba(63, 185, 80, 0.08);
}

.ws-indicator.connecting {
  color: #d29922;
  border-color: rgba(210, 153, 34, 0.28);
  background: rgba(210, 153, 34, 0.08);
}

.ws-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-secondary);
}

.connected .ws-dot {
  background: #3fb950;
  animation: pulse-green 2s infinite;
}

.connecting .ws-dot {
  background: #d29922;
  animation: pulse-yellow 1s infinite;
}

@keyframes pulse-green {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

@keyframes pulse-yellow {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

/* ─── Stats Row ───────────────────────────────────────────────── */
.stats-row {
  margin-bottom: 24px;
}

.stat-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 16px 12px;
  min-height: 92px;
  color: var(--text-primary);
  background: var(--card-bg);
  border: 1px solid var(--line-color);
  border-radius: 8px;
  box-shadow: none;
  transition: border-color 0.2s, transform 0.2s;
}

.stat-card:hover {
  transform: translateY(-2px);
  border-color: var(--view-color-border);
}

.stat-icon {
  font-size: 24px;
  margin-bottom: 4px;
}

.stat-label {
  font-size: 12px;
  color: var(--text-secondary);
}

.stat-value {
  font-size: 22px;
  font-weight: 700;
  margin-top: 2px;
}

.stat-total .stat-value,
.stat-busy .stat-value,
.stat-devices .stat-value { color: var(--view-color); }
.stat-online .stat-value { color: #3fb950; }
.stat-idle .stat-value,
.stat-avg-cpu .stat-value { color: #d29922; }
.stat-offline .stat-value { color: var(--text-secondary); }

/* ─── Memory System Gate ─── */
.memory-health-card {
  margin-bottom: 28px;
  padding: 18px;
  color: var(--text-primary);
  background: var(--card-bg);
  border: 1px solid var(--line-color);
  border-left: 4px solid var(--text-secondary);
  border-radius: 10px;
}

.memory-health-card.memory-healthy { border-left-color: #3fb950; }
.memory-health-card.memory-stale { border-left-color: #d29922; }
.memory-health-card.memory-unhealthy,
.memory-health-card.memory-missing,
.memory-health-card.memory-invalid { border-left-color: #f85149; }

.memory-health-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.memory-health-title { font-size: 17px; font-weight: 700; }
.memory-health-subtitle { margin-top: 4px; color: var(--text-secondary); font-size: 12px; }

.memory-health-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.memory-health-metric {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
  padding: 12px;
  background: var(--panel-bg);
  border: 1px solid var(--line-color);
  border-radius: 8px;
}

.memory-health-metric span,
.memory-health-metric small { color: var(--text-secondary); font-size: 11px; }
.memory-health-metric strong {
  overflow: hidden;
  color: var(--text-primary);
  font-size: 14px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.memory-channel-list { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
.memory-channel-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 9px;
  color: var(--text-secondary);
  background: var(--panel-bg);
  border: 1px solid var(--line-color);
  border-radius: 12px;
  font-size: 11px;
}
.memory-channel-chip i {
  width: 7px;
  height: 7px;
  background: var(--text-secondary);
  border-radius: 50%;
}
.memory-channel-chip.channel-ready i { background: #3fb950; }
.memory-channel-chip.channel-failed i { background: #f85149; }
.memory-health-alert { margin-top: 14px; }

.memory-operations-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-top: 14px;
}
.memory-operation-item {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 10px 12px;
  background: var(--panel-bg);
  border: 1px solid var(--line-color);
  border-radius: 8px;
}
.memory-operation-item span,
.memory-operation-item small { color: var(--text-secondary); font-size: 11px; }
.memory-operation-item strong { color: var(--text-primary); font-size: 15px; }
.release-approval-button,
.release-history-button { align-self: flex-start; margin-top: 4px; margin-left: 0; }
.memory-operation-item.slo-healthy { border-color: rgba(63, 185, 80, 0.35); }
.memory-operation-item.slo-at_risk { border-color: rgba(210, 153, 34, 0.45); }
.memory-operation-item.slo-breached { border-color: rgba(248, 81, 73, 0.45); }

.release-timeline { padding: 4px 8px; }
.release-history-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px;
  color: var(--text-secondary);
  background: var(--panel-bg);
  border: 1px solid var(--line-color);
  border-radius: 8px;
  font-size: 12px;
}
.release-history-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: var(--text-primary);
}

@media (max-width: 900px) {
  .memory-health-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .memory-operations-row { grid-template-columns: 1fr; }
}

@media (max-width: 560px) {
  .memory-health-metrics { grid-template-columns: 1fr; }
  .memory-health-header { align-items: flex-start; }
}

/* ─── Section Header ──────────────────────────────────────────── */
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.section-header h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

.refresh-hint {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-secondary);
}

/* ─── Agent Cards ─────────────────────────────────────────────── */
.agent-cards-row {
  margin-bottom: 28px;
}

.agent-card {
  color: var(--text-primary);
  background: var(--card-bg);
  border: 1px solid var(--line-color);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
  box-shadow: none;
  border-left: 4px solid var(--text-secondary);
  transition: border-color 0.2s, transform 0.2s;
}

.agent-card:hover {
  transform: translateY(-2px);
  border-color: var(--view-color-border);
}

.agent-card.status-online { border-left-color: #3fb950; }
.agent-card.status-busy { border-left-color: var(--view-color); }
.agent-card.status-idle { border-left-color: #d29922; }
.agent-card.status-offline { border-left-color: var(--text-secondary); }

.card-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.agent-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--view-color), #3fb950);
  color: #08111f;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: 700;
  flex-shrink: 0;
}

.agent-info {
  flex: 1;
  min-width: 0;
}

.agent-name {
  display: block;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.agent-id {
  font-size: 11px;
  color: var(--text-secondary);
  font-family: monospace;
}

.status-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 500;
  white-space: nowrap;
}

.status-badge.online {
  background: rgba(63, 185, 80, 0.1);
  color: #3fb950;
}

.status-badge.busy {
  background: rgba(var(--view-rgb), 0.1);
  color: var(--view-color);
}

.status-badge.idle {
  background: rgba(210, 153, 34, 0.1);
  color: #d29922;
}

.status-badge.offline {
  background: rgba(139, 148, 158, 0.1);
  color: var(--text-secondary);
}

.status-badge.unknown {
  background: rgba(139, 148, 158, 0.1);
  color: var(--text-secondary);
}

.card-section {
  margin-bottom: 10px;
}

.section-label {
  font-size: 11px;
  color: var(--text-secondary);
  margin-bottom: 2px;
}

.section-value {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

.heartbeat-age {
  font-size: 11px;
  margin-left: 6px;
  font-weight: 400;
}

.heartbeat-age.age-healthy { color: #3fb950; }
.heartbeat-age.age-warning { color: #d29922; }
.heartbeat-age.age-critical { color: #f85149; }
.heartbeat-age.age-offline { color: var(--text-secondary); }

.card-metrics {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 10px;
}

.metric-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.metric-label {
  font-size: 12px;
  color: var(--text-secondary);
}

.metric-value {
  font-size: 13px;
  font-weight: 600;
}

.metric-value.success { color: #3fb950; }
.metric-value.warning { color: #d29922; }
.metric-value.danger { color: #f85149; }

:deep(.el-progress-bar__outer) {
  background-color: var(--panel-bg);
}

.task-text {
  font-size: 12px;
  color: var(--view-color);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.health-score {
  display: flex;
  align-items: baseline;
  gap: 2px;
}

.score-value {
  font-size: 20px;
  font-weight: 700;
}

.score-value.score-healthy { color: #3fb950; }
.score-value.score-warning { color: #d29922; }
.score-value.score-critical { color: #f85149; }

.score-max {
  font-size: 12px;
  color: var(--text-secondary);
}

/* ─── Device Cards ───────────────────────────────────────────── */
.device-cards-row {
  margin-bottom: 28px;
}

.device-card {
  color: var(--text-primary);
  background: var(--card-bg);
  border: 1px solid var(--line-color);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
  box-shadow: none;
  border-left: 4px solid var(--text-secondary);
  transition: border-color 0.2s, transform 0.2s;
}

.device-card:hover {
  transform: translateY(-2px);
  border-color: var(--view-color-border);
}

.device-card.status-online { border-left-color: #3fb950; }
.device-card.status-busy { border-left-color: var(--view-color); }
.device-card.status-idle { border-left-color: #d29922; }
.device-card.status-offline,
.device-card.status-unknown { border-left-color: var(--text-secondary); }

.device-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.device-name {
  color: var(--text-primary);
  font-size: 15px;
  font-weight: 700;
}

.device-address {
  color: var(--text-secondary);
  font-size: 12px;
  margin-top: 3px;
}

.device-meta {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--line-color);
  border-radius: 8px;
  background: var(--panel-bg);
}

.device-meta div {
  min-width: 0;
}

.device-meta span {
  display: block;
  color: var(--text-secondary);
  font-size: 11px;
  margin-bottom: 4px;
}

.device-meta strong {
  display: block;
  color: var(--text-primary);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.device-agents {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 12px;
}

.agent-chip,
.empty-chip {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
}

.agent-chip {
  color: var(--view-color);
  background: rgba(var(--view-rgb), 0.1);
}

.empty-chip {
  color: var(--text-secondary);
  background: rgba(139, 148, 158, 0.1);
}

/* ─── Charts ──────────────────────────────────────────────────── */
.charts-row {
  margin-bottom: 20px;
}

.chart-card {
  color: var(--text-primary);
  background: var(--card-bg);
  border: 1px solid var(--line-color);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
  box-shadow: none;
}

.chart-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 12px;
}

.chart-container {
  width: 100%;
  height: 280px;
}

/* ─── Responsive ──────────────────────────────────────────────── */
@media (max-width: 768px) {
  .monitoring-page {
    padding: 12px;
  }

  .page-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .page-actions {
    width: 100%;
    justify-content: space-between;
  }

  .chart-container {
    height: 220px;
  }
}
</style>
