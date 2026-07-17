<template>
  <div class="analytics-page">
    <!-- 页面标题 + 时间范围切换 -->
    <div class="page-header">
      <div class="page-title">
        <h1>📊 数据分析</h1>
        <p class="page-desc">团队效率 · 任务趋势 · Sprint 燃尽 · Agent 产出</p>
      </div>
      <div class="page-actions">
        <el-segmented v-model="daysRange" :options="dayOptions" size="small" />
        <el-button
          type="primary"
          size="small"
          :loading="loading"
          @click="refreshAll"
        >
          刷新
        </el-button>
      </div>
    </div>

    <!-- 团队效率概览卡片 -->
    <el-row :gutter="16" class="stats-row">
      <el-col :xs="8" :sm="8" :md="8" v-for="stat in efficiencyStats" :key="stat.label">
        <div class="stat-card" :class="stat.class">
          <div class="stat-icon">{{ stat.icon }}</div>
          <span class="stat-label">{{ stat.label }}</span>
          <span class="stat-value">{{ stat.value }}</span>
        </div>
      </el-col>
    </el-row>

    <!-- 任务趋势折线图 -->
    <div class="section-header">
      <h2>📈 任务趋势</h2>
      <span class="refresh-hint">{{ taskTrend.length > 0 ? `共 ${taskTrend.length} 天数据` : '暂无数据' }}</span>
    </div>
    <div class="chart-card">
      <div ref="taskTrendRef" class="chart-container"></div>
      <el-empty v-if="!loading && taskTrend.length === 0" description="暂无任务趋势数据" />
    </div>

    <!-- Agent 产出 + Sprint 燃尽 -->
    <el-row :gutter="16" class="charts-row">
      <el-col :xs="24" :md="12">
        <div class="chart-card">
          <div class="chart-title">🏆 Agent 产出率</div>
          <div ref="agentProductivityRef" class="chart-container"></div>
          <el-empty v-if="!loading && agentProductivity.length === 0" description="暂无产出数据" />
        </div>
      </el-col>
      <el-col :xs="24" :md="12">
        <div class="chart-card">
          <div class="chart-title">🔥 Sprint 燃尽图</div>
          <div ref="sprintBurndownRef" class="chart-container"></div>
          <el-empty v-if="!loading && sprintBurndown.length === 0" description="暂无燃尽数据" />
        </div>
      </el-col>
    </el-row>

    <!-- 团队效率雷达图 -->
    <div class="section-header">
      <h2>🎯 团队效率雷达图</h2>
    </div>
    <div class="chart-card radar-card">
      <div ref="radarRef" class="chart-container radar-chart"></div>
      <el-empty v-if="!loading && !teamEfficiency" description="暂无效率数据" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import {
  getTaskTrend,
  getAgentProductivity,
  getSprintBurndown,
  getTeamEfficiency,
  type TaskTrendPoint,
  type AgentProductivity,
  type SprintBurndownPoint,
  type TeamEfficiency
} from '@/api/analytics'

// ─── Reactive State ─────────────────────────────────────────────────────────

const daysRange = ref<number>(30)
const dayOptions = [
  { label: '7天', value: 7 },
  { label: '14天', value: 14 },
  { label: '30天', value: 30 },
  { label: '90天', value: 90 }
]

const loading = ref(false)
const taskTrend = ref<TaskTrendPoint[]>([])
const agentProductivity = ref<AgentProductivity[]>([])
const sprintBurndown = ref<SprintBurndownPoint[]>([])
const teamEfficiency = ref<TeamEfficiency | null>(null)

// Chart refs
const taskTrendRef = ref<HTMLDivElement>()
const agentProductivityRef = ref<HTMLDivElement>()
const sprintBurndownRef = ref<HTMLDivElement>()
const radarRef = ref<HTMLDivElement>()

// Chart instances
let taskTrendChart: echarts.ECharts | null = null
let agentProductivityChart: echarts.ECharts | null = null
let sprintBurndownChart: echarts.ECharts | null = null
let radarChart: echarts.ECharts | null = null

const chartTheme = {
  text: '#c9d1d9',
  muted: '#8b949e',
  line: '#30363d',
  panel: '#161b22',
  primary: '#58a6ff',
  success: '#3fb950',
  warning: '#d29922',
  danger: '#f85149'
}

function chartBase(): EChartsOption {
  return {
    backgroundColor: 'transparent',
    color: [chartTheme.primary, chartTheme.success, chartTheme.danger, chartTheme.warning, chartTheme.muted],
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

const efficiencyStats = computed(() => {
  const e = teamEfficiency.value
  if (!e) {
    return [
      { label: '完成率', value: '--', icon: '✅', class: 'stat-rate' },
      { label: '平均周期', value: '--', icon: '⏱️', class: 'stat-cycle' },
      { label: '预估vs实际', value: '--', icon: '📐', class: 'stat-estimation' }
    ]
  }
  return [
    {
      label: '完成率',
      value: `${(e.completion_rate * 100).toFixed(1)}%`,
      icon: '✅',
      class: 'stat-rate'
    },
    {
      label: '平均周期',
      value: `${e.avg_cycle_days.toFixed(1)}天`,
      icon: '⏱️',
      class: 'stat-cycle'
    },
    {
      label: '预估vs实际',
      value: `${(e.estimated_vs_actual_ratio * 100).toFixed(0)}%`,
      icon: '📐',
      class: e.estimated_vs_actual_ratio >= 0.8 ? 'stat-good' : 'stat-warn'
    }
  ]
})

// ─── Mock Data (后端未就绪时的降级数据) ──────────────────────────────────────

function generateMockTaskTrend(days: number): TaskTrendPoint[] {
  const result: TaskTrendPoint[] = []
  const now = new Date()
  let totalCreated = 100
  let totalCompleted = 60
  let totalBlocked = 5

  for (let i = days - 1; i >= 0; i--) {
    const date = new Date(now)
    date.setDate(date.getDate() - i)
    const created = Math.floor(Math.random() * 8) + 2
    const completed = Math.floor(Math.random() * 6) + 1
    const blocked = Math.random() > 0.8 ? Math.floor(Math.random() * 3) + 1 : 0
    totalCreated += created
    totalCompleted += completed
    totalBlocked += blocked

    result.push({
      date: date.toISOString().slice(0, 10),
      created,
      completed,
      blocked
    })
  }
  return result
}

function generateMockAgentProductivity(): AgentProductivity[] {
  const agents = [
    { id: 'leonardo', name: '李奥纳多' },
    { id: 'raphael', name: '拉斐尔' },
    { id: 'donatello', name: '多纳泰罗' },
    { id: 'michelangelo', name: '米开朗基罗' },
    { id: 'wheeljack', name: '千斤顶' },
    { id: 'ironhide', name: '铁皮' }
  ]

  return agents.map(a => ({
    agent_id: a.id,
    agent_name: a.name,
    completed_count: Math.floor(Math.random() * 30) + 10,
    total_count: Math.floor(Math.random() * 20) + 20,
    completion_rate: Math.random() * 0.4 + 0.5,
    avg_duration_hours: Math.random() * 20 + 4
  }))
}

function generateMockSprintBurndown(): SprintBurndownPoint[] {
  const result: SprintBurndownPoint[] = []
  const now = new Date()
  const totalTasks = 42
  const days = 14

  for (let i = 0; i < days; i++) {
    const date = new Date(now)
    date.setDate(date.getDate() - (days - 1 - i))
    const idealRemaining = totalTasks - (totalTasks / days) * (i + 1)
    const actualRemaining = Math.max(0, totalTasks - (totalTasks / days) * (i + 1) + (Math.random() * 8 - 4))
    result.push({
      date: date.toISOString().slice(0, 10),
      ideal_remaining: Math.max(0, Math.round(idealRemaining)),
      actual_remaining: Math.max(0, Math.round(actualRemaining))
    })
  }
  return result
}

function generateMockTeamEfficiency(): TeamEfficiency {
  return {
    completion_rate: 0.73,
    avg_cycle_days: 8.5,
    estimated_vs_actual_ratio: 0.88,
    dimensions: {
      completion_rate: 0.73,
      velocity: 0.82,
      quality: 0.91,
      estimation_accuracy: 0.88,
      responsiveness: 0.65
    }
  }
}

// ─── Data Fetching ───────────────────────────────────────────────────────────

async function fetchTaskTrend() {
  try {
    const data = await getTaskTrend('daily', daysRange.value)
    taskTrend.value = data
  } catch {
    // 后端未就绪 → 降级 mock
    console.log('[Analytics] 任务趋势 API 不可用，使用 mock 数据')
    taskTrend.value = generateMockTaskTrend(daysRange.value)
  }
}

async function fetchAgentProductivity() {
  try {
    const data = await getAgentProductivity()
    agentProductivity.value = data
  } catch {
    console.log('[Analytics] Agent 产出 API 不可用，使用 mock 数据')
    agentProductivity.value = generateMockAgentProductivity()
  }
}

async function fetchSprintBurndown() {
  try {
    const data = await getSprintBurndown()
    sprintBurndown.value = data
  } catch {
    console.log('[Analytics] Sprint 燃尽 API 不可用，使用 mock 数据')
    sprintBurndown.value = generateMockSprintBurndown()
  }
}

async function fetchTeamEfficiency() {
  try {
    const data = await getTeamEfficiency(daysRange.value)
    teamEfficiency.value = data
  } catch {
    console.log('[Analytics] 团队效率 API 不可用，使用 mock 数据')
    teamEfficiency.value = generateMockTeamEfficiency()
  }
}

async function refreshAll() {
  loading.value = true
  try {
    await Promise.all([
      fetchTaskTrend(),
      fetchAgentProductivity(),
      fetchSprintBurndown(),
      fetchTeamEfficiency()
    ])
    updateAllCharts()
  } catch (e) {
    ElMessage.error('获取数据失败')
  } finally {
    loading.value = false
  }
}

// ─── Charts ──────────────────────────────────────────────────────────────────

function initCharts() {
  nextTick(() => {
    if (taskTrendRef.value) taskTrendChart = echarts.init(taskTrendRef.value)
    if (agentProductivityRef.value) agentProductivityChart = echarts.init(agentProductivityRef.value)
    if (sprintBurndownRef.value) sprintBurndownChart = echarts.init(sprintBurndownRef.value)
    if (radarRef.value) radarChart = echarts.init(radarRef.value)
  })
}

function updateAllCharts() {
  updateTaskTrendChart()
  updateAgentProductivityChart()
  updateSprintBurndownChart()
  updateRadarChart()
}

function updateTaskTrendChart() {
  if (!taskTrendChart) return

  const dates = taskTrend.value.map(d => d.date.slice(5))
  const option: EChartsOption = {
    ...chartBase(),
    tooltip: chartTooltip('axis'),
    legend: { data: ['创建', '完成', '阻塞'], bottom: 0 },
    grid: { top: 10, right: 20, bottom: 40, left: 50 },
    xAxis: categoryAxis(dates, 30),
    yAxis: valueAxis('任务数'),
    series: [
      {
        name: '创建',
        type: 'line',
        smooth: true,
        data: taskTrend.value.map(d => d.created),
        itemStyle: { color: chartTheme.primary },
        areaStyle: { opacity: 0.15 }
      },
      {
        name: '完成',
        type: 'line',
        smooth: true,
        data: taskTrend.value.map(d => d.completed),
        itemStyle: { color: chartTheme.success },
        areaStyle: { opacity: 0.15 }
      },
      {
        name: '阻塞',
        type: 'line',
        smooth: true,
        data: taskTrend.value.map(d => d.blocked),
        itemStyle: { color: chartTheme.danger },
        areaStyle: { opacity: 0.15 }
      }
    ]
  }
  taskTrendChart.setOption(option, true)
}

function updateAgentProductivityChart() {
  if (!agentProductivityChart) return

  const names = agentProductivity.value.map(a => a.agent_name)
  const rates = agentProductivity.value.map(a => Math.round(a.completion_rate * 100))
  const counts = agentProductivity.value.map(a => a.completed_count)

  const option: EChartsOption = {
    ...chartBase(),
    tooltip: {
      ...chartTooltip('axis'),
      trigger: 'axis',
      formatter: (params: any) => {
        const idx = params[0].dataIndex
        const a = agentProductivity.value[idx]
        return `${names[idx]}<br/>
          完成率: ${rates[idx]}%<br/>
          完成任务: ${counts[idx]}<br/>
          平均耗时: ${a.avg_duration_hours.toFixed(1)}h`
      }
    },
    grid: { top: 10, right: 20, bottom: 40, left: 60 },
    xAxis: categoryAxis(names, 30),
    yAxis: valueAxis('完成率 (%)', { max: 100 }),
    series: [{
      name: '完成率',
      type: 'bar',
      data: rates,
      itemStyle: {
        color: (params: any) => {
          const v = params.value
          if (v >= 80) return chartTheme.success
          if (v >= 60) return chartTheme.warning
          return chartTheme.danger
        }
      },
      label: { show: true, position: 'top', formatter: '{c}%', color: chartTheme.text }
    }]
  }
  agentProductivityChart.setOption(option, true)
}

function updateSprintBurndownChart() {
  if (!sprintBurndownChart) return

  const dates = sprintBurndown.value.map(d => d.date.slice(5))
  const option: EChartsOption = {
    ...chartBase(),
    tooltip: chartTooltip('axis'),
    legend: { data: ['理想线', '实际线'], bottom: 0 },
    grid: { top: 10, right: 20, bottom: 40, left: 50 },
    xAxis: categoryAxis(dates, 30),
    yAxis: valueAxis('剩余任务'),
    series: [
      {
        name: '理想线',
        type: 'line',
        smooth: false,
        data: sprintBurndown.value.map(d => d.ideal_remaining),
        itemStyle: { color: chartTheme.muted },
        lineStyle: { type: 'dashed' }
      },
      {
        name: '实际线',
        type: 'line',
        smooth: false,
        data: sprintBurndown.value.map(d => d.actual_remaining),
        itemStyle: { color: chartTheme.primary },
        areaStyle: { opacity: 0.1 }
      }
    ]
  }
  sprintBurndownChart.setOption(option, true)
}

function updateRadarChart() {
  if (!radarChart || !teamEfficiency.value) return

  const d = teamEfficiency.value.dimensions
  const option: EChartsOption = {
    ...chartBase(),
    tooltip: chartTooltip('item'),
    radar: {
      indicator: [
        { name: '完成率', max: 1 },
        { name: '速度', max: 1 },
        { name: '质量', max: 1 },
        { name: '预估准确', max: 1 },
        { name: '响应度', max: 1 }
      ],
      shape: 'polygon',
      splitNumber: 5,
      axisName: {
        color: chartTheme.muted,
        fontSize: 12
      },
      splitLine: {
        lineStyle: { color: chartTheme.line }
      },
      splitArea: {
        areaStyle: {
          color: ['rgba(88,166,255,0.04)', 'rgba(88,166,255,0.08)']
        }
      }
    },
    series: [{
      type: 'radar',
      data: [{
        value: [
          d.completion_rate,
          d.velocity,
          d.quality,
          d.estimation_accuracy,
          d.responsiveness
        ],
        name: '团队效率',
        areaStyle: { opacity: 0.3 },
        itemStyle: { color: chartTheme.primary },
        lineStyle: { width: 2 }
      }]
    }]
  }
  radarChart.setOption(option, true)
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await refreshAll()
  initCharts()
  updateAllCharts()
})

onUnmounted(() => {
  taskTrendChart?.dispose()
  agentProductivityChart?.dispose()
  sprintBurndownChart?.dispose()
  radarChart?.dispose()
})

// watch daysRange to refresh
import { watch } from 'vue'
watch(daysRange, async () => {
  loading.value = true
  try {
    await Promise.all([
      fetchTaskTrend(),
      fetchTeamEfficiency()
    ])
    updateTaskTrendChart()
    updateRadarChart()
  } catch {
    ElMessage.error('获取数据失败')
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.analytics-page {
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

/* ─── Stats Row ───────────────────────────────────────────────── */
.stats-row {
  margin-bottom: 24px;
}

.stat-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 16px 12px;
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

.stat-rate .stat-value,
.stat-good .stat-value { color: #3fb950; }
.stat-cycle .stat-value { color: var(--view-color); }
.stat-warn .stat-value { color: #d29922; }

/* ─── Section Header ──────────────────────────────────────────── */
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  margin-top: 16px;
}

.section-header h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

.refresh-hint {
  font-size: 12px;
  color: var(--text-secondary);
}

/* ─── Chart Cards ─────────────────────────────────────────────── */
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
  height: 320px;
}

.radar-card {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.radar-chart {
  height: 380px;
  max-width: 500px;
}

.charts-row {
  margin-bottom: 16px;
}

/* ─── Responsive ──────────────────────────────────────────────── */
@media (max-width: 768px) {
  .analytics-page {
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
    height: 240px;
  }

  .radar-chart {
    height: 280px;
  }
}

@media (max-width: 480px) {
  .page-title h1 {
    font-size: 20px;
  }

  .stat-value {
    font-size: 18px;
  }

  .chart-container {
    height: 200px;
  }

  .radar-chart {
    height: 240px;
  }
}
</style>
