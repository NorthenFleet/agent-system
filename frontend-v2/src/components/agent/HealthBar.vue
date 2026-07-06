<template>
  <div class="health-bar" :class="{ clickable }" @click="clickable ? $emit('click') : null">
    <div class="health-bar-left">
      <span
        class="health-badge"
        :style="{ backgroundColor: barColor }"
      />
      <span class="health-score-num" :style="{ color: barColor }">
        {{ score != null ? score : '--' }}
      </span>
      <span v-if="trendIcon" class="health-trend" :style="{ color: trendColor }">
        {{ trendIcon }}
      </span>
    </div>
    <div class="health-bar-track">
      <div
        class="health-bar-fill"
        :style="{ width: `${score ?? 0}%`, backgroundColor: barColor }"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useAgentsStore } from '@/stores/agents'

const props = defineProps<{
  score?: number
  agentId?: string
  clickable?: boolean
}>()

defineEmits<{
  click: []
}>()

const agentsStore = useAgentsStore()

const effectiveScore = computed(() => {
  if (props.score != null) return props.score
  if (props.agentId) return agentsStore.getHealthScore(props.agentId)
  return null
})

const barColor = computed(() => {
  const s = effectiveScore.value
  if (s == null) return '#909399'
  if (s >= 80) return '#22c55e'
  if (s >= 50) return '#eab308'
  return '#ef4444'
})

const trendIcon = computed(() => {
  if (!props.agentId) return null
  const data = agentsStore.getHealthScoreData(props.agentId)
  if (!data?.trend) return null
  if (data.trend === 'up') return '↑'
  if (data.trend === 'down') return '↓'
  return '→'
})

const trendColor = computed(() => {
  if (!props.agentId) return '#909399'
  const data = agentsStore.getHealthScoreData(props.agentId)
  if (!data?.trend) return '#909399'
  if (data.trend === 'up') return '#22c55e'
  if (data.trend === 'down') return '#ef4444'
  return '#909399'
})
</script>

<style scoped>
.health-bar {
  display: flex;
  align-items: center;
  gap: 8px;
}

.health-bar.clickable {
  cursor: pointer;
}

.health-bar-left {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: 0 0 auto;
  min-width: 56px;
}

.health-badge {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.health-score-num {
  font-size: 12px;
  font-weight: 700;
}

.health-trend {
  font-size: 11px;
  font-weight: 700;
}

.health-bar-track {
  flex: 1;
  height: 6px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 3px;
  overflow: hidden;
}

.health-bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.3s ease, background-color 0.3s ease;
}
</style>
