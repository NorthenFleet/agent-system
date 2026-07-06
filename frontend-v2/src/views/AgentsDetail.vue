<template>
  <div class="agent-detail-page">
    <!-- Loading 骨架屏 -->
    <div v-if="loading" class="detail-skeleton">
      <div class="skeleton-header">
        <div class="skeleton-avatar"></div>
        <div class="skeleton-lines">
          <div class="skeleton-line w-160"></div>
          <div class="skeleton-line w-100"></div>
        </div>
      </div>
      <el-row :gutter="16">
        <el-col v-for="i in 4" :key="i" :span="6">
          <div class="skeleton-card"></div>
        </el-col>
      </el-row>
      <div class="skeleton-chart"></div>
    </div>

    <!-- 错误状态 -->
    <el-result
      v-else-if="error"
      icon="error"
      title="加载失败"
      :sub-title="error"
    >
      <template #extra>
        <el-button type="primary" @click="loadAll">重试</el-button>
        <el-button @click="$router.back()">返回列表</el-button>
      </template>
    </el-result>

    <!-- 详情内容 -->
    <template v-else-if="agent">
      <!-- 页面导航 -->
      <div class="page-nav">
        <el-button text @click="$router.back()" :icon="ArrowLeft">
          返回智能体列表
        </el-button>
        <el-tag :type="statusType(agent.status)" size="small">
          {{ statusEmoji(agent.status) }} {{ statusLabel(agent.status) }}
        </el-tag>
      </div>

      <!-- Agent 基本信息卡片 -->
      <el-card class="info-card" shadow="never">
        <div class="agent-header">
          <div class="agent-avatar-lg" :style="{ background: avatarColor(agent.agent_id) }">
            <span class="avatar-emoji">{{ agentEmoji(agent.agent_id) }}</span>
            <span class="status-ring" :class="statusType(agent.status)"></span>
          </div>
          <div class="agent-basic-info">
            <div class="agent-name-row">
              <h1 class="agent-name">{{ agent.agent_name || agent.agent_id }}</h1>
              <el-tag
                :type="statusType(agent.status)"
                effect="dark"
                size="default"
              >
                {{ statusLabel(agent.status) }}
              </el-tag>
            </div>
            <p class="agent-id-row muted">
              <span class="id-prefix">ID:</span> {{ agent.agent_id }}
              <span v-if="agent.metadata?.role" class="agent-role">
                · {{ agent.metadata.role }}
              </span>
            </p>
            <div class="agent-quick-stats">
              <div class="quick-stat" :class="heartbeatClass(agent)">
                <span class="qs-icon">💓</span>
                <span class="qs-label">最后心跳</span>
                <span class="qs-value">{{ heartbeatText(agent) }}</span>
              </div>
              <div class="quick-stat">
                <span class="qs-icon">📋</span>
                <span class="qs-label">当前任务</span>
                <span class="qs-value">{{ agent.current_task || '待分配' }}</span>
              </div>
              <div class="quick-stat">
                <span class="qs-icon">🏥</span>
                <span class="qs-label">健康状态</span>
                <span class="qs-value">{{ healthLabel(agent.health) }}</span>
              </div>
            </div>
          </div>
        </div>
      </el-card>

      <!-- 核心指标 -->
      <el-row :gutter="16" class="metrics-row">
        <el-col :xs="12" :sm="6">
          <el-card class="metric-card metric-heartbeat" shadow="hover">
            <div class="metric-icon">💓</div>
            <div class="metric-body">
              <span class="metric-label">心跳时间</span>
              <span class="metric-value">{{ formatTimestamp(agent.last_heartbeat) }}</span>
              <span class="metric-sub">{{ heartbeatText(agent) }}</span>
            </div>
          </el-card>
        </el-col>
        <el-col :xs="12" :sm="6">
          <el-card class="metric-card metric-cpu" shadow="hover">
            <div class="metric-icon">⚙️</div>
            <div class="metric-body">
              <span class="metric-label">CPU 使用率</span>
              <span class="metric-value">
                {{ agent.cpu_usage != null ? `${agent.cpu_usage}%` : '—' }}
              </span>
              <el-progress
                v-if="agent.cpu_usage != null"
                :percentage="agent.cpu_usage"
                :stroke-width="4"
                :show-text="false"
                :status="metricProgressStatus(agent.cpu_usage)"
                class="metric-bar"
              />
            </div>
          </el-card>
        </el-col>
        <el-col :xs="12" :sm="6">
          <el-card class="metric-card metric-memory" shadow="hover">
            <div class="metric-icon">🧠</div>
            <div class="metric-body">
              <span class="metric-label">内存使用率</span>
              <span class="metric-value">
                {{ agent.memory_usage != null ? `${agent.memory_usage}%` : '—' }}
              </span>
              <el-progress
                v-if="agent.memory_usage != null"
                :percentage="agent.memory_usage"
                :stroke-width="4"
                :show-text="false"
                :status="metricProgressStatus(agent.memory_usage)"
                class="metric-bar"
              />
            </div>
          </el-card>
        </el-col>
        <el-col :xs="12" :sm="6">
          <el-card class="metric-card metric-health" shadow="hover">
            <div class="metric-icon">🏥</div>
            <div class="metric-body">
              <span class="metric-label">健康评分</span>
              <span class="metric-value">
                {{ agent.health_score != null ? `${agent.health_score}` : '—' }}
              </span>
              <span class="metric-sub" :class="healthScoreClass(agent.health_score)">
                {{ healthScoreLabel(agent.health_score) }}
              </span>
            </div>
          </el-card>
        </el-col>
      </el-row>

      <!-- 健康趋势图 -->
      <el-card class="trend-card" shadow="never" v-if="healthTrend.length > 0">
        <template #header>
          <div class="card-header">
            <span>📈 健康趋势（{{ trendHours }} 小时）</span>
            <el-select v-model="trendHours" size="small" class="trend-select" @change="fetchHealthTrend">
              <el-option label="12 小时" :value="12" />
              <el-option label="24 小时" :value="24" />
              <el-option label="48 小时" :value="48" />
            </el-select>
          </div>
        </template>
        <div ref="trendChartRef" class="trend-chart"></div>
      </el-card>

      <!-- 当前任务详情 -->
      <el-card class="task-card" shadow="never">
        <template #header>
          <span>📋 当前任务</span>
        </template>
        <div v-if="agent.current_task" class="task-info">
          <div class="task-name">{{ agent.current_task }}</div>
          <div class="task-meta muted">
            Agent: {{ agent.agent_id }} · 状态: {{ statusLabel(agent.status) }}
          </div>
        </div>
        <el-empty v-else description="暂无分配任务" :image-size="80" />
      </el-card>

      <!-- 状态变更历史 -->
      <el-card class="history-card" shadow="never">
        <template #header>
          <div class="card-header">
            <span>📜 状态变更历史</span>
            <el-select v-model="historyLimit" size="small" class="history-select" @change="fetchHistory">
              <el-option label="最近 10 条" :value="10" />
              <el-option label="最近 20 条" :value="20" />
              <el-option label="最近 50 条" :value="50" />
            </el-select>
          </div>
        </template>

        <el-empty
          v-if="history.length === 0"
          description="暂无状态变更记录"
          :image-size="80"
        />

        <el-timeline v-else class="status-timeline">
          <el-timeline-item
            v-for="(item, index) in history"
            :key="item.id || index"
            :type="statusType(item.to_status)"
            :hollow="index > 0"
            placement="top"
          >
            <div class="history-entry">
              <div class="history-main">
                <span class="history-status-badge from" :class="statusType(item.from_status ?? '')">
                  {{ statusLabel(item.from_status ?? '') }}
                </span>
                <span class="history-arrow">→</span>
                <span class="history-status-badge to" :class="statusType(item.to_status ?? '')">
                  {{ statusLabel(item.to_status ?? '') }}
                </span>
              </div>
              <div v-if="item.current_task" class="history-task muted">
                📋 {{ item.current_task }}
              </div>
              <div v-if="item.triggered_by" class="history-trigger muted">
                触发者: {{ item.triggered_by }}
              </div>
              <div class="history-time">
                {{ formatHistoryTime(item.changed_at) }}
              </div>
            </div>
          </el-timeline-item>
        </el-timeline>
      </el-card>

      <!-- 元数据 -->
      <el-card v-if="agent.metadata && Object.keys(agent.metadata).length > 0" class="meta-card" shadow="never">
        <template #header>
          <span>📝 元数据</span>
        </template>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item
            v-for="(val, key) in agent.metadata"
            :key="String(key)"
            :label="String(key)"
          >
            {{ typeof val === 'object' ? JSON.stringify(val) : String(val) }}
          </el-descriptions-item>
        </el-descriptions>
      </el-card>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import { useAgentsStore, type Agent, type AgentStatusHistory } from '@/stores/agents'
import { getAgentHistory } from '@/api/agents'
import { getHealthTrend, type HealthTrendPoint } from '@/api/health'

const route = useRoute()
const agentsStore = useAgentsStore()

// ===================== 状态 =====================
const agent = ref<Agent | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const history = ref<AgentStatusHistory[]>([])
const historyLimit = ref(20)
const healthTrend = ref<HealthTrendPoint[]>([])
const trendHours = ref(24)
const trendChartRef = ref<HTMLElement | null>(null)
let trendChart: echarts.ECharts | null = null

// 心跳轮询
let heartbeatTimer: ReturnType<typeof setInterval> | null = null
const HEARTBEAT_INTERVAL = 10_000 // 10 秒

// ===================== 计算属性 =====================
const agentId = computed(() => route.params.id as string)

// ===================== 核心操作 =====================
async function loadAll() {
  loading.value = true
  error.value = null
  try {
    await Promise.all([
      fetchAgent(),
      fetchHistory(),
      fetchHealthTrend()
    ])
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : '加载 Agent 详情失败'
    error.value = msg
    ElMessage.error(msg)
  } finally {
    loading.value = false
  }
}

async function fetchAgent() {
  // 从 store 查找或重新获取
  await agentsStore.fetchAgents()
  const found = agentsStore.agents.find(a => a.agent_id === agentId.value)
  if (found) {
    agent.value = { ...found }
  } else {
    error.value = `未找到智能体: ${agentId.value}`
    agent.value = null
  }
}

async function fetchHistory() {
  if (!agentId.value) return
  try {
    const res = await getAgentHistory(agentId.value, { limit: historyLimit.value })
    history.value = res.history || []
  } catch {
    history.value = []
  }
}

async function fetchHealthTrend() {
  if (!agentId.value) return
  try {
    const res = await getHealthTrend(agentId.value, trendHours.value)
    healthTrend.value = res.trend || []
    await nextTick()
    renderTrendChart()
  } catch {
    healthTrend.value = []
  }
}

// ===================== 心跳轮询 =====================
function startHeartbeatPoll() {
  stopHeartbeatPoll()
  heartbeatTimer = setInterval(async () => {
    try {
      await agentsStore.fetchAgents()
      const found = agentsStore.agents.find(a => a.agent_id === agentId.value)
      if (found) {
        agent.value = { ...found }
      }
    } catch {
      // silent fail during polling
    }
  }, HEARTBEAT_INTERVAL)
}

function stopHeartbeatPoll() {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer)
    heartbeatTimer = null
  }
}

// ===================== 健康趋势图表 =====================
function renderTrendChart() {
  if (!trendChartRef.value) return
  if (trendChart) {
    trendChart.dispose()
  }
  trendChart = echarts.init(trendChartRef.value)

  const option: EChartsOption = {
    tooltip: {
      trigger: 'axis',
      formatter: (params: any) => {
        const p = params[0]
        return `${p.axisValue}<br/>健康评分: ${p.value}`
      }
    },
    grid: { left: 40, right: 20, top: 20, bottom: 30 },
    xAxis: {
      type: 'category',
      data: healthTrend.value.map(p => {
        try {
          return new Date(p.timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
        } catch {
          return p.timestamp
        }
      }),
      axisLabel: { fontSize: 11, color: '#888', interval: 2 },
      axisLine: { lineStyle: { color: '#333' } }
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 100,
      splitLine: { lineStyle: { color: '#2a2a2a' } },
      axisLabel: { fontSize: 11, color: '#888' }
    },
    series: [{
      type: 'line',
      smooth: true,
      symbol: 'circle',
      symbolSize: 6,
      data: healthTrend.value.map(p => p.score),
      lineStyle: { color: '#409eff', width: 2 },
      itemStyle: { color: '#409eff' },
      areaStyle: {
        color: {
          type: 'linear',
          x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(64, 158, 255, 0.3)' },
            { offset: 1, color: 'rgba(64, 158, 255, 0.02)' }
          ]
        }
      }
    }]
  }

  trendChart.setOption(option)
}

// ===================== 路由监听 =====================
watch(() => route.params.id, () => {
  loadAll()
})

// ===================== 工具函数 =====================
function statusType(status: string): '' | 'success' | 'warning' | 'info' | 'danger' {
  const map: Record<string, '' | 'success' | 'warning' | 'info' | 'danger'> = {
    online: 'success',
    busy: 'warning',
    idle: 'info',
    offline: 'danger'
  }
  return map[status] || 'info'
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    online: '在线',
    busy: '忙碌',
    idle: '空闲',
    pending: '待命',
    offline: '离线'
  }
  return map[status] || status || '未知'
}

function statusEmoji(status: string): string {
  const map: Record<string, string> = {
    online: '🟢',
    busy: '🟡',
    idle: '🔵',
    offline: '⚫'
  }
  return map[status] || '❓'
}

function healthLabel(health: string): string {
  const map: Record<string, string> = {
    healthy: '健康',
    warning: '警告',
    critical: '严重',
    offline: '离线'
  }
  return map[health] || health
}

function metricProgressStatus(value: number): '' | 'success' | 'warning' | 'exception' {
  if (value >= 80) return 'exception'
  if (value >= 60) return 'warning'
  return 'success'
}

function heartbeatText(a: Agent): string {
  if (a.status === 'offline') return '离线'
  const s = a.heartbeat_age_seconds ?? a.seconds_ago
  if (s == null) return '未知'
  if (s < 10) return '刚刚'
  if (s < 60) return `${Math.round(s)}秒前`
  if (s < 3600) return `${Math.round(s / 60)}分钟前`
  return `${Math.round(s / 3600)}小时前`
}

function heartbeatClass(a: Agent): string {
  if (a.status === 'offline') return 'heartbeat-offline'
  const s = a.heartbeat_age_seconds ?? a.seconds_ago ?? Infinity
  if (s <= 60) return 'heartbeat-ok'
  if (s <= 300) return 'heartbeat-warn'
  return 'heartbeat-critical'
}

function healthScoreClass(score: number | null | undefined): string {
  if (score == null) return 'score-unknown'
  if (score >= 80) return 'score-good'
  if (score >= 60) return 'score-warn'
  return 'score-bad'
}

function healthScoreLabel(score: number | null | undefined): string {
  if (score == null) return '暂无数据'
  if (score >= 80) return '优秀'
  if (score >= 60) return '良好'
  if (score >= 40) return '一般'
  return '需关注'
}

function formatTimestamp(iso: string | null): string {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    return d.toLocaleString('zh-CN', { hour12: false })
  } catch {
    return iso
  }
}

function formatHistoryTime(iso: string): string {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    return d.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    })
  } catch {
    return iso
  }
}

function agentEmoji(id: string): string {
  const map: Record<string, string> = {
    optimus: '🤖',
    leonardo: '🟦',
    raphael: '🟥',
    donatello: '🟪',
    michelangelo: '🟧',
    ironhide: '🛡️',
    perceptor: '🚗',
    ratchet: '🚑',
    wheeljack: '🔧',
    soundwave: '🔷',
    jazz: '🎷',
    bumblebee: '🐝',
    shockwave: '🟣',
    'ultra-magnus': '🔵'
  }
  return map[id] || '🤖'
}

function avatarColor(id: string): string {
  let hash = 0
  for (let i = 0; i < id.length; i++) {
    hash = id.charCodeAt(i) + ((hash << 5) - hash)
  }
  const h = Math.abs(hash) % 360
  return `hsl(${h}, 45%, 35%)`
}

// ===================== 生命周期 =====================
onMounted(async () => {
  await loadAll()
  startHeartbeatPoll()

  // WebSocket 实时推送
  const token = localStorage.getItem('jwt_token')
  if (token) {
    agentsStore.connectWebSocket(token)
  }
})

onUnmounted(() => {
  stopHeartbeatPoll()
  agentsStore.disconnectWebSocket()
  if (trendChart) {
    trendChart.dispose()
    trendChart = null
  }
})
</script>

<style scoped>
.agent-detail-page {
  padding: 16px;
  min-height: 100%;
  max-width: 960px;
  margin: 0 auto;
}

/* ===================== 骨架屏 ===================== */
.detail-skeleton {
  animation: pulse-skeleton 1.5s ease-in-out infinite;
}

.skeleton-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px;
  background: #1a1a1a;
  border-radius: 10px;
  margin-bottom: 16px;
}

.skeleton-avatar {
  width: 64px;
  height: 64px;
  border-radius: 14px;
  background: #2a2a2a;
  flex-shrink: 0;
}

.skeleton-lines {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.skeleton-line {
  height: 16px;
  border-radius: 4px;
  background: #2a2a2a;
}

.skeleton-line.w-160 { width: 160px; }
.skeleton-line.w-100 { width: 100px; }

.skeleton-card {
  height: 80px;
  border-radius: 8px;
  background: #1a1a1a;
  margin-bottom: 8px;
}

.skeleton-chart {
  height: 200px;
  border-radius: 8px;
  background: #1a1a1a;
}

@keyframes pulse-skeleton {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* ===================== 导航 ===================== */
.page-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

/* ===================== Agent 头部 ===================== */
.info-card {
  border-radius: 12px;
  border: 1px solid #333;
  background: #1a1a1a;
  margin-bottom: 16px;
}

:deep(.el-card__body) {
  padding: 24px;
}

.agent-header {
  display: flex;
  align-items: center;
  gap: 20px;
}

.agent-avatar-lg {
  width: 64px;
  height: 64px;
  border-radius: 14px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  position: relative;
}

.avatar-emoji {
  font-size: 30px;
}

.status-ring {
  position: absolute;
  bottom: -2px;
  right: -2px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 2px solid #1a1a1a;
}

.status-ring.success { background: #67c23a; }
.status-ring.warning { background: #e6a23c; }
.status-ring.danger { background: #f56c6c; }
.status-ring.info { background: #409eff; }

.agent-name-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.agent-name {
  margin: 0;
  font-size: 22px;
  font-weight: 800;
  color: #e0e0e0;
}

.agent-id-row {
  margin: 4px 0 12px;
  font-size: 13px;
  color: #666;
}

.id-prefix {
  color: #888;
}

.agent-role {
  color: #409eff;
}

.muted { color: #888; }

/* 快速统计 */
.agent-quick-stats {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.quick-stat {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.qs-icon { font-size: 16px; }
.qs-label { color: #888; }
.qs-value { color: #b0b0b0; font-weight: 600; }

/* 心跳状态色 */
.heartbeat-ok .qs-value { color: #67c23a; }
.heartbeat-warn .qs-value { color: #e6a23c; }
.heartbeat-critical .qs-value { color: #f56c6c; }
.heartbeat-offline .qs-value { color: #909399; }

/* ===================== 指标卡片 ===================== */
.metrics-row {
  margin-bottom: 16px;
}

.metric-card {
  border-radius: 10px;
  border: 1px solid #333;
  background: #1a1a1a;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px;
  transition: transform 0.15s, box-shadow 0.15s;
  height: 80px;
}

.metric-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

.metric-icon {
  font-size: 28px;
  flex-shrink: 0;
}

.metric-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.metric-label {
  font-size: 12px;
  color: #888;
}

.metric-value {
  font-size: 16px;
  font-weight: 700;
  color: #e0e0e0;
  line-height: 1.3;
}

.metric-sub {
  font-size: 11px;
  color: #666;
}

.metric-bar {
  margin-top: 4px;
}

.score-good { color: #67c23a; }
.score-warn { color: #e6a23c; }
.score-bad { color: #f56c6c; }
.score-unknown { color: #909399; }

/* ===================== 趋势图 ===================== */
.trend-card {
  border-radius: 10px;
  border: 1px solid #333;
  background: #1a1a1a;
  margin-bottom: 16px;
}

:deep(.el-card__header) {
  border-bottom: 1px solid #333;
  padding: 12px 16px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 700;
  font-size: 14px;
  color: #e0e0e0;
}

.trend-select,
.history-select {
  width: 120px;
}

.trend-chart {
  width: 100%;
  height: 200px;
}

/* ===================== 当前任务 ===================== */
.task-card {
  border-radius: 10px;
  border: 1px solid #333;
  background: #1a1a1a;
  margin-bottom: 16px;
}

.task-info {
  padding: 8px 0;
}

.task-name {
  font-size: 15px;
  font-weight: 600;
  color: #e0e0e0;
  margin-bottom: 4px;
}

.task-meta {
  font-size: 12px;
}

:deep(.el-empty) {
  padding: 16px 0;
}

/* ===================== 状态历史 ===================== */
.history-card {
  border-radius: 10px;
  border: 1px solid #333;
  background: #1a1a1a;
  margin-bottom: 16px;
}

.status-timeline {
  padding: 0 8px;
}

.history-entry {
  background: #222;
  border-radius: 8px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.history-main {
  display: flex;
  align-items: center;
  gap: 6px;
}

.history-status-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
}

.history-status-badge.success {
  background: rgba(103, 194, 58, 0.15);
  color: #67c23a;
}

.history-status-badge.warning {
  background: rgba(230, 162, 60, 0.15);
  color: #e6a23c;
}

.history-status-badge.danger {
  background: rgba(245, 108, 108, 0.15);
  color: #f56c6c;
}

.history-status-badge.info {
  background: rgba(64, 158, 255, 0.15);
  color: #409eff;
}

.history-arrow {
  color: #666;
  font-size: 14px;
}

.history-task,
.history-trigger {
  font-size: 12px;
}

.history-time {
  font-size: 11px;
  color: #555;
  margin-top: 2px;
}

/* ===================== 元数据 ===================== */
.meta-card {
  border-radius: 10px;
  border: 1px solid #333;
  background: #1a1a1a;
  margin-bottom: 16px;
}

:deep(.el-descriptions__label) {
  color: #888;
}

:deep(.el-descriptions__content) {
  color: #b0b0b0;
}

/* ===================== 响应式 ===================== */
@media (max-width: 768px) {
  .agent-detail-page {
    padding: 12px;
  }

  .agent-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }

  .agent-quick-stats {
    flex-direction: column;
    gap: 8px;
  }

  .agent-name {
    font-size: 18px;
  }

  .metric-card {
    height: auto;
    min-height: 70px;
  }
}

@media (max-width: 480px) {
  .metrics-row .el-col {
    margin-bottom: 8px;
  }

  .trend-chart {
    height: 160px;
  }
}
</style>
