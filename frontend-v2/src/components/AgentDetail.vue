<template>
  <el-drawer
    v-model="visible"
    title="智能体详情"
    size="480px"
    direction="rtl"
    @close="handleClose"
  >
    <template #header="{ titleId, titleClass }">
      <div class="drawer-header">
        <span :id="titleId" :class="titleClass">
          {{ agentEmoji }} {{ agent?.agent_name || '智能体' }} 详情
        </span>
      </div>
    </template>

    <div v-if="agent" class="detail-content">
      <!-- 基本信息 -->
      <el-descriptions :column="1" border>
        <el-descriptions-item label="ID">{{ agent.agent_id }}</el-descriptions-item>
        <el-descriptions-item label="名称">{{ agent.agent_name }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="getAgentStatusType(agent.status)" size="small">
            {{ getAgentStatusLabel(agent.status) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="健康度">
          <HeartbeatIndicator :agent="agent" />
          <span class="health-text">{{ getHealthLabel(agent.health) }}</span>
          <span v-if="agentsStore.getHealthScore(agent.agent_id) != null" class="health-score-inline">
            <HealthBar :score="agentsStore.getHealthScore(agent.agent_id)" :agent-id="agent.agent_id" />
          </span>
        </el-descriptions-item>
        <el-descriptions-item label="当前任务">
          {{ agent.current_task || '—' }}
        </el-descriptions-item>
        <el-descriptions-item label="最近心跳">
          {{ formatHeartbeatAge(agent.heartbeat_age_seconds) }}
        </el-descriptions-item>
        <el-descriptions-item label="CPU">
          {{ agent.cpu_usage != null ? agent.cpu_usage.toFixed(1) + '%' : '—' }}
        </el-descriptions-item>
        <el-descriptions-item label="内存">
          {{ agent.memory_usage != null ? agent.memory_usage.toFixed(1) + '%' : '—' }}
        </el-descriptions-item>
      </el-descriptions>

      <el-divider />

      <!-- 健康度趋势 -->
      <h4>📈 健康度趋势 (24h)</h4>
      <div v-if="agentsStore.healthLoading" class="health-chart-loading">
        <el-skeleton :rows="4" animated />
      </div>
      <VChart v-else-if="trendOption" :option="trendOption" autoresize class="health-trend-chart" />
      <el-empty v-else description="暂无趋势数据" :image-size="40" />

      <el-divider />

      <!-- 状态变更历史 -->
      <h4>📜 状态变更历史</h4>
      <el-timeline v-if="agentsStore.selectedAgentHistory.length">
        <el-timeline-item
          v-for="(item, idx) in agentsStore.selectedAgentHistory.slice(0, 10)"
          :key="idx"
          :type="getTimelineType(item.to_status)"
          :timestamp="formatTime(item.changed_at)"
          placement="top"
        >
          <div class="timeline-content">
            <span class="status-from">
              {{ item.from_status ? getStatusLabel(item.from_status) : '—' }}
            </span>
            <span class="arrow">→</span>
            <span class="status-to">{{ getStatusLabel(item.to_status) }}</span>
            <div v-if="item.current_task" class="task-ref">
              任务: {{ item.current_task }}
            </div>
          </div>
        </el-timeline-item>
      </el-timeline>
      <el-empty v-else description="暂无状态变更记录" :image-size="40" />

      <el-divider />

      <!-- 通知列表 -->
      <h4>🔔 实时通知</h4>
      <div v-if="agentsStore.notifications.length" class="notification-list">
        <el-timeline>
          <el-timeline-item
            v-for="(notif, idx) in agentsStore.notifications.slice(0, 10)"
            :key="idx"
            :type="notif.type === 'agent' ? 'success' : 'warning'"
            :timestamp="formatTime(notif.timestamp)"
            placement="top"
          >
            {{ notif.message }}
          </el-timeline-item>
        </el-timeline>
      </div>
      <el-empty v-else description="暂无通知" :image-size="40" />
    </div>

    <div v-else class="detail-empty">
      <el-empty description="请选择一个智能体查看详情" />
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import { useAgentsStore, type Agent } from '@/stores/agents'
import HeartbeatIndicator from './common/HeartbeatIndicator.vue'
import HealthBar from './agent/HealthBar.vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart } from 'echarts/charts'
import { TooltipComponent, GridComponent } from 'echarts/components'

use([CanvasRenderer, LineChart, TooltipComponent, GridComponent])

const props = defineProps<{
  modelValue: boolean
  agent: Agent | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const agentsStore = useAgentsStore()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v)
})

// 健康度趋势图
watch(
  () => props.agent?.agent_id,
  (agentId) => {
    if (agentId) {
      agentsStore.fetchHealthTrend(agentId, 24)
    }
  },
  { immediate: true }
)

const trendOption = computed(() => {
  const data = agentsStore.healthTrend
  if (!data.length) return null

  const times = data.map(p => {
    const d = new Date(p.timestamp)
    return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
  })
  const scores = data.map(p => p.score)

  const lastScore = scores[scores.length - 1]
  const lineColor = lastScore >= 80 ? '#22c55e' : lastScore >= 50 ? '#eab308' : '#ef4444'

  return {
    tooltip: {
      trigger: 'axis',
      formatter: (params: any) => {
        const item = params[0]
        return `${item.axisValue}<br/>健康度: ${item.value}`
      }
    },
    grid: { left: 40, right: 16, top: 12, bottom: 28 },
    xAxis: {
      type: 'category',
      data: times,
      axisLabel: { color: '#909399', fontSize: 10 },
      axisLine: { lineStyle: { color: '#404040' } },
      splitLine: { show: false }
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 100,
      axisLabel: { color: '#909399', fontSize: 10, formatter: '{value}' },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } }
    },
    series: [{
      type: 'line',
      data: scores,
      smooth: true,
      symbol: 'none',
      lineStyle: { color: lineColor, width: 2 },
      areaStyle: {
        color: {
          type: 'linear',
          x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: `${lineColor}44` },
            { offset: 1, color: `${lineColor}08` }
          ]
        }
      }
    }]
  }
})

const agentEmoji = computed(() => {
  if (!props.agent) return '🤖'
  const map: Record<string, string> = {
    leonardo: '🟦', raphael: '🟥', donatello: '🟪',
    michelangelo: '🟧', wheeljack: '🔧', optimus: '🤖'
  }
  return map[props.agent.agent_id] || '🤖'
})

function handleClose() {
  emit('update:modelValue', false)
}

function getAgentStatusType(status: string): '' | 'success' | 'warning' | 'info' | 'danger' {
  const map: Record<string, '' | 'success' | 'warning' | 'info' | 'danger'> = {
    online: 'success', busy: 'warning', idle: 'info', offline: 'danger'
  }
  return map[status] || 'info'
}

function getAgentStatusLabel(status: string): string {
  const map: Record<string, string> = {
    online: '在线', busy: '忙碌', idle: '空闲', offline: '离线'
  }
  return map[status] || status
}

function getStatusLabel(status: string | null): string {
  if (!status) return '—'
  return getAgentStatusLabel(status)
}

function getHealthLabel(health: string): string {
  const map: Record<string, string> = {
    healthy: '健康', warning: '警告', critical: '严重', offline: '离线'
  }
  return map[health] || health
}

function getTimelineType(status: string): 'success' | 'primary' | 'warning' | 'danger' | 'info' {
  if (status === 'online' || status === 'busy') return 'success'
  if (status === 'idle') return 'warning'
  if (status === 'offline') return 'danger'
  return 'info'
}

function formatHeartbeatAge(seconds: number | null): string {
  if (seconds == null) return '无数据'
  if (seconds < 60) return `${Math.round(seconds)}秒前`
  return `${Math.round(seconds / 60)}分钟前`
}

function formatTime(time: string): string {
  if (!time) return '—'
  return new Date(time).toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit'
  })
}
</script>

<style scoped>
.drawer-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.detail-content {
  display: flex;
  flex-direction: column;
}

.health-text {
  margin-left: 8px;
  font-size: 13px;
  color: #606266;
}

.health-score-inline {
  display: block;
  margin-top: 6px;
}

.health-chart-loading {
  padding: 12px 0;
}

.health-trend-chart {
  height: 180px;
  background: var(--card-bg, #1a1a2e);
  border-radius: 8px;
  border: 1px solid var(--line-color, #333);
  padding: 8px;
}

h4 {
  margin: 0 0 12px;
  font-size: 14px;
  color: #606266;
}

.timeline-content {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.status-from {
  color: #909399;
  font-size: 13px;
}

.arrow {
  color: #c0c4cc;
}

.status-to {
  font-weight: 600;
  font-size: 13px;
}

.task-ref {
  font-size: 12px;
  color: #909399;
  margin-top: 2px;
}

.notification-list {
  max-height: 200px;
  overflow-y: auto;
}

.detail-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 400px;
}
</style>
