<template>
  <div class="health-score-card">
    <!-- 总分布 -->
    <div class="score-overview">
      <div class="score-ring">
        <el-progress
          type="dashboard"
          :percentage="healthData?.score ?? 0"
          :color="scoreColor"
          :width="120"
          :stroke-width="10"
        />
        <div class="score-trend">
          <span v-if="trendIcon" :style="{ color: trendColor }">{{ trendIcon }}</span>
          <span v-if="scoreDelta != null" class="score-delta" :style="{ color: trendColor }">
            {{ scoreDelta > 0 ? '+' : '' }}{{ scoreDelta }}
          </span>
        </div>
      </div>
      <div class="score-label">
        <div class="score-value" :style="{ color: scoreColor }">
          {{ healthData?.score ?? 0 }}
        </div>
        <div class="score-desc">健康度评分 (0-100)</div>
      </div>
    </div>

    <!-- 五维度雷达图 -->
    <div class="radar-section">
      <div class="radar-title">五维度分析</div>
      <VChart :option="radarOption" autoresize style="height: 260px" />
    </div>

    <!-- 维度详情 -->
    <div class="dimension-list">
      <div
        v-for="dim in dimensions"
        :key="dim.key"
        class="dimension-item"
      >
        <div class="dim-info">
          <span class="dim-name">{{ dim.name }}</span>
          <span class="dim-weight">权重 {{ dim.weight }}</span>
        </div>
        <div class="dim-bar">
          <el-progress
            :percentage="dimValue(dim.key)"
            :stroke-width="6"
            :show-text="false"
            :color="dimColor(dimValue(dim.key))"
          />
        </div>
        <span class="dim-value" :style="{ color: dimColor(dimValue(dim.key)) }">
          {{ dimValue(dim.key) }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { RadarChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent } from 'echarts/components'
import type { AgentHealthScore } from '@/api/health'

use([CanvasRenderer, RadarChart, TooltipComponent, LegendComponent])

const props = defineProps<{
  healthData: AgentHealthScore | null
}>()

const dimensions = [
  { key: 'online_status', name: '在线状态', weight: '20%' },
  { key: 'task_success_rate', name: '任务成功率', weight: '30%' },
  { key: 'response_latency', name: '响应延迟', weight: '20%' },
  { key: 'task_backlog', name: '任务积压', weight: '15%' },
  { key: 'confidence_trend', name: '置信度趋势', weight: '15%' }
]

const scoreColor = computed(() => {
  const score = props.healthData?.score ?? 0
  if (score >= 80) return '#22c55e'
  if (score >= 50) return '#eab308'
  return '#ef4444'
})

const trendIcon = computed(() => {
  const trend = props.healthData?.trend
  if (trend === 'up') return '↑'
  if (trend === 'down') return '↓'
  if (trend === 'flat') return '→'
  return null
})

const trendColor = computed(() => {
  const trend = props.healthData?.trend
  if (trend === 'up') return '#22c55e'
  if (trend === 'down') return '#ef4444'
  return '#909399'
})

const scoreDelta = computed(() => {
  if (!props.healthData) return null
  return props.healthData.score - props.healthData.prev_score
})

function dimValue(key: string): number {
  if (!props.healthData?.dimensions) return 0
  return props.healthData.dimensions[key as keyof typeof props.healthData.dimensions] ?? 0
}

function dimColor(value: number): string {
  if (value >= 80) return '#22c55e'
  if (value >= 50) return '#eab308'
  return '#ef4444'
}

const radarOption = computed(() => ({
  radar: {
    indicator: dimensions.map(d => ({
      name: d.name,
      max: 100
    })),
    radius: '65%',
    splitNumber: 5,
    axisName: {
      color: '#a0a0a0',
      fontSize: 11
    },
    splitArea: {
      areaStyle: {
        color: ['rgba(255,255,255,0.04)', 'rgba(255,255,255,0.02)', 'rgba(255,255,255,0.01)', 'rgba(255,255,255,0.005)']
      }
    },
    axisLine: {
      lineStyle: { color: 'rgba(255,255,255,0.1)' }
    },
    splitLine: {
      lineStyle: { color: 'rgba(255,255,255,0.1)' }
    }
  },
  series: [{
    type: 'radar',
    data: [{
      value: dimensions.map(d => dimValue(d.key)),
      name: props.healthData?.agent_name || 'Agent',
      areaStyle: {
        color: `rgba(${scoreColor.value === '#22c55e' ? '34, 197, 94' : scoreColor.value === '#eab308' ? '234, 179, 8' : '239, 68, 68'}, 0.25)`
      },
      lineStyle: {
        color: scoreColor.value,
        width: 2
      },
      itemStyle: {
        color: scoreColor.value
      }
    }]
  }],
  tooltip: {
    trigger: 'item',
    formatter: (params: any) => {
      const vals = params.value as number[]
      return dimensions.map((d, i) => `${d.name}: ${vals[i]}`).join('<br/>')
    }
  }
}))
</script>

<style scoped>
.health-score-card {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px;
}

.score-overview {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px;
  background: var(--card-bg, #1a1a2e);
  border-radius: 12px;
  border: 1px solid var(--line-color, #333);
}

.score-ring {
  position: relative;
  flex: 0 0 auto;
}

.score-trend {
  position: absolute;
  bottom: 4px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 700;
}

.score-label {
  display: grid;
  gap: 2px;
}

.score-value {
  font-size: 28px;
  font-weight: 800;
}

.score-desc {
  font-size: 12px;
  color: var(--text-secondary, #909399);
}

.radar-section {
  padding: 12px;
  background: var(--card-bg, #1a1a2e);
  border-radius: 8px;
  border: 1px solid var(--line-color, #333);
}

.radar-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary, #e0e0e0);
  margin-bottom: 8px;
}

.dimension-list {
  display: grid;
  gap: 10px;
}

.dimension-item {
  display: grid;
  grid-template-columns: 80px 1fr 32px;
  align-items: center;
  gap: 10px;
}

.dim-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.dim-name {
  font-size: 12px;
  color: var(--text-primary, #e0e0e0);
  font-weight: 600;
}

.dim-weight {
  font-size: 10px;
  color: var(--text-secondary, #909399);
}

.dim-bar {
  width: 100%;
}

.dim-value {
  font-size: 13px;
  font-weight: 700;
  text-align: right;
}
</style>
