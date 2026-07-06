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
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { Refresh, Loading } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import { getMonitoringLive, createMonitoringWs, type MonitoringAgent } from '@/api/monitoring'

// ─── Reactive State ─────────────────────────────────────────────────────────

const agents = ref<MonitoringAgent[]>([])
const loading = ref(false)
const wsConnected = ref(false)
const wsConnecting = ref(false)
const autoRefresh = ref(true)
const lastRefreshTime = ref('--:--:--')

let refreshTimer: ReturnType<typeof setInterval> | null = null
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

// ─── Helpers ─────────────────────────────────────────────────────────────────

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    online: '在线',
    busy: '忙碌',
    idle: '空闲',
    offline: '离线'
  }
  return map[status] || status
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('zh-CN', { hour12: false })
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
  if (v == null) return '#909399'
  if (v > 90) return '#F56C6C'
  if (v > 70) return '#E6A23C'
  return '#67C23A'
}

function memoryProgressColor(v: number | null): string {
  if (v == null) return '#909399'
  if (v > 90) return '#F56C6C'
  if (v > 75) return '#E6A23C'
  return '#409EFF'
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

function computeHealth(ageSeconds: number | null | undefined): MonitoringAgent['health'] {
  if (ageSeconds == null) return 'offline'
  if (ageSeconds <= 60) return 'healthy'
  if (ageSeconds <= 300) return 'warning'
  return 'critical'
}

function refreshData() {
  fetchMonitoringData()
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
    tooltip: { trigger: 'axis' },
    legend: { data: agentNames, bottom: 0 },
    grid: { top: 10, right: 20, bottom: 40, left: 50 },
    xAxis: { type: 'category', data: times },
    yAxis: { type: 'value', name: 'CPU %', max: 100, min: 0 },
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
    tooltip: { trigger: 'axis' },
    legend: { data: agentNames, bottom: 0 },
    grid: { top: 10, right: 20, bottom: 40, left: 50 },
    xAxis: { type: 'category', data: times },
    yAxis: { type: 'value', name: '内存 %', max: 100, min: 0 },
    series
  }
  memoryChart.setOption(option, true)
}

function updateAgentsChart() {
  if (!agentsChart) return

  const data = agentCountHistory.value
  const option: EChartsOption = {
    tooltip: { trigger: 'axis' },
    grid: { top: 10, right: 20, bottom: 30, left: 50 },
    xAxis: { type: 'category', data: data.map(d => d.time) },
    yAxis: { type: 'value', name: 'Agent数', minInterval: 1 },
    series: [{
      name: '在线Agent',
      type: 'line' as const,
      smooth: true,
      areaStyle: { opacity: 0.3 },
      data: data.map(d => d.count),
      itemStyle: { color: '#409EFF' }
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
    tooltip: { trigger: 'item' },
    legend: { bottom: 0, data: ['健康', '警告', '严重', '离线'] },
    series: [{
      name: '健康度',
      type: 'pie' as const,
      radius: ['40%', '70%'],
      avoidLabelOverlap: true,
      itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
      label: { show: true, formatter: '{b}: {c}' },
      data: [
        { value: counts.healthy, name: '健康', itemStyle: { color: '#67C23A' } },
        { value: counts.warning, name: '警告', itemStyle: { color: '#E6A23C' } },
        { value: counts.critical, name: '严重', itemStyle: { color: '#F56C6C' } },
        { value: counts.offline, name: '离线', itemStyle: { color: '#909399' } }
      ]
    }]
  }
  healthPieChart.setOption(option, true)
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await fetchMonitoringData()
  initCharts()
  startAutoRefresh()
  connectWebSocket()
})

onUnmounted(() => {
  stopAutoRefresh()
  disconnectWebSocket()
  cpuChart?.dispose()
  memoryChart?.dispose()
  agentsChart?.dispose()
  healthPieChart?.dispose()
})
</script>

<style scoped>
.monitoring-page {
  padding: 20px;
  min-height: 100vh;
  background: #f5f7fa;
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
  color: #1d2b3a;
}

.page-desc {
  margin: 0;
  font-size: 13px;
  color: #909399;
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
  color: #909399;
  padding: 4px 10px;
  border-radius: 12px;
  background: #f0f0f0;
  transition: all 0.3s;
}

.ws-indicator.connected {
  color: #67C23A;
  background: #f0f9eb;
}

.ws-indicator.connecting {
  color: #E6A23C;
  background: #fdf6ec;
}

.ws-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #909399;
}

.connected .ws-dot {
  background: #67C23A;
  animation: pulse-green 2s infinite;
}

.connecting .ws-dot {
  background: #E6A23C;
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
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  transition: transform 0.2s;
}

.stat-card:hover {
  transform: translateY(-2px);
}

.stat-icon {
  font-size: 24px;
  margin-bottom: 4px;
}

.stat-label {
  font-size: 12px;
  color: #909399;
}

.stat-value {
  font-size: 22px;
  font-weight: 700;
  margin-top: 2px;
}

.stat-total .stat-value { color: #409EFF; }
.stat-online .stat-value { color: #67C23A; }
.stat-busy .stat-value { color: #409EFF; }
.stat-idle .stat-value { color: #E6A23C; }
.stat-offline .stat-value { color: #909399; }
.stat-avg-cpu .stat-value { color: #E6A23C; }

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
  color: #1d2b3a;
}

.refresh-hint {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #909399;
}

/* ─── Agent Cards ─────────────────────────────────────────────── */
.agent-cards-row {
  margin-bottom: 28px;
}

.agent-card {
  background: #fff;
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 16px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  border-left: 4px solid #909399;
  transition: all 0.2s;
}

.agent-card:hover {
  box-shadow: 0 4px 16px rgba(0,0,0,0.12);
  transform: translateY(-2px);
}

.agent-card.status-online { border-left-color: #67C23A; }
.agent-card.status-busy { border-left-color: #409EFF; }
.agent-card.status-idle { border-left-color: #E6A23C; }
.agent-card.status-offline { border-left-color: #909399; }

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
  background: linear-gradient(135deg, #409EFF, #67C23A);
  color: #fff;
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
  color: #1d2b3a;
}

.agent-id {
  font-size: 11px;
  color: #909399;
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
  background: #f0f9eb;
  color: #67C23A;
}

.status-badge.busy {
  background: #ecf5ff;
  color: #409EFF;
}

.status-badge.idle {
  background: #fdf6ec;
  color: #E6A23C;
}

.status-badge.offline {
  background: #f4f4f5;
  color: #909399;
}

.card-section {
  margin-bottom: 10px;
}

.section-label {
  font-size: 11px;
  color: #909399;
  margin-bottom: 2px;
}

.section-value {
  font-size: 13px;
  font-weight: 500;
  color: #303133;
}

.heartbeat-age {
  font-size: 11px;
  margin-left: 6px;
  font-weight: 400;
}

.heartbeat-age.age-healthy { color: #67C23A; }
.heartbeat-age.age-warning { color: #E6A23C; }
.heartbeat-age.age-critical { color: #F56C6C; }
.heartbeat-age.age-offline { color: #909399; }

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
  color: #606266;
}

.metric-value {
  font-size: 13px;
  font-weight: 600;
}

.metric-value.success { color: #67C23A; }
.metric-value.warning { color: #E6A23C; }
.metric-value.danger { color: #F56C6C; }

.task-text {
  font-size: 12px;
  color: #409EFF;
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

.score-value.score-healthy { color: #67C23A; }
.score-value.score-warning { color: #E6A23C; }
.score-value.score-critical { color: #F56C6C; }

.score-max {
  font-size: 12px;
  color: #909399;
}

/* ─── Charts ──────────────────────────────────────────────────── */
.charts-row {
  margin-bottom: 20px;
}

.chart-card {
  background: #fff;
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 16px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

.chart-title {
  font-size: 14px;
  font-weight: 600;
  color: #1d2b3a;
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
