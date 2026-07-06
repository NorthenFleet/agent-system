<template>
  <div class="task-recommendation">
    <div class="rec-header">
      <span class="rec-icon">🤖</span>
      <span class="rec-title">智能推荐</span>
      <el-button
        size="small"
        type="primary"
        :loading="loading"
        :disabled="!canRecommend"
        @click="fetchRecommendations"
      >
        获取推荐
      </el-button>
    </div>

    <el-empty v-if="!loading && !agents.length && fetched" description="暂无推荐结果" :image-size="40" />

    <div v-if="loading" class="rec-loading">
      <el-skeleton :rows="3" animated />
    </div>

    <div v-else-if="agents.length" class="rec-list">
      <div
        v-for="(agent, idx) in agents"
        :key="agent.agent_id"
        class="rec-item"
        :class="{ 'rec-item-top': idx === 0 }"
        @click="selectAgent(agent)"
      >
        <div class="rec-rank">
          <span v-if="idx === 0" class="rec-crown">★</span>
          <span v-else class="rec-rank-num">{{ idx + 1 }}</span>
        </div>
        <div class="rec-avatar">
          {{ agentEmoji(agent.agent_id) }}
        </div>
        <div class="rec-info">
          <div class="rec-name">
            {{ agent.agent_name }}
            <el-tag v-if="idx === 0" size="small" type="warning" effect="dark">最佳</el-tag>
          </div>
          <div class="rec-meta">
            <span class="rec-score">
              推荐评分 <strong>{{ Math.round(agent.score * 100) }}%</strong>
            </span>
            <span class="rec-success">
              历史成功率 <strong :style="{ color: successColor(agent.success_rate) }">
                {{ Math.round(agent.success_rate * 100) }}%
              </strong>
            </span>
          </div>
        </div>
        <div class="rec-bar">
          <el-progress
            :percentage="Math.round(agent.score * 100)"
            :stroke-width="6"
            :show-text="false"
            :color="scoreColor(agent.score)"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { recommendAgent, type RecommendAgent } from '@/api/recommendation'

const props = defineProps<{
  taskType: string
  priority: string
  tags: string[]
}>()

const emit = defineEmits<{
  select: [agentId: string]
}>()

const loading = ref(false)
const fetched = ref(false)
const agents = ref<RecommendAgent[]>([])

const canRecommend = computed(() => {
  return !!props.taskType
})

async function fetchRecommendations() {
  if (!canRecommend.value) return
  loading.value = true
  fetched.value = true
  try {
    const res = await recommendAgent({
      task_type: props.taskType,
      priority: props.priority,
      tags: props.tags
    })
    agents.value = (res.agents || []).sort((a, b) => b.score - a.score)
  } catch {
    agents.value = []
  } finally {
    loading.value = false
  }
}

function selectAgent(agent: RecommendAgent) {
  emit('select', agent.agent_id)
}

function agentEmoji(id: string): string {
  const map: Record<string, string> = {
    leonardo: '🟦', raphael: '🟥', donatello: '🟪',
    michelangelo: '🟧', wheeljack: '🔧', optimus: '🤖'
  }
  return map[id] || '👤'
}

function scoreColor(score: number): string {
  if (score >= 0.8) return '#22c55e'
  if (score >= 0.5) return '#eab308'
  return '#ef4444'
}

function successColor(rate: number): string {
  if (rate >= 0.8) return '#22c55e'
  if (rate >= 0.5) return '#eab308'
  return '#ef4444'
}

defineExpose({ fetchRecommendations })
</script>

<style scoped>
.task-recommendation {
  margin-top: 12px;
  padding: 12px;
  border: 1px solid var(--line-color, #e4e7ed);
  border-radius: 8px;
  background: var(--card-bg, #fafafa);
}

.rec-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.rec-icon {
  font-size: 18px;
}

.rec-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary, #303133);
  flex: 1;
}

.rec-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.rec-item {
  display: grid;
  grid-template-columns: 24px 36px 1fr;
  align-items: center;
  gap: 10px;
  padding: 10px;
  border: 1px solid var(--line-color, #e4e7ed);
  border-radius: 8px;
  background: var(--panel-bg, #fff);
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.rec-item:hover {
  border-color: #409eff;
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.12);
}

.rec-item-top {
  border-color: #eab308;
  background: linear-gradient(90deg, rgba(234, 179, 8, 0.06), transparent);
}

.rec-rank {
  display: grid;
  place-items: center;
}

.rec-crown {
  color: #eab308;
  font-size: 18px;
  filter: drop-shadow(0 1px 2px rgba(234, 179, 8, 0.4));
}

.rec-rank-num {
  font-size: 12px;
  color: #909399;
  font-weight: 700;
}

.rec-avatar {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: #383838;
  display: grid;
  place-items: center;
  font-size: 18px;
}

.rec-info {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.rec-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #303133);
  display: flex;
  align-items: center;
  gap: 6px;
}

.rec-meta {
  display: flex;
  gap: 12px;
  font-size: 11px;
  color: var(--text-secondary, #909399);
}

.rec-meta strong {
  font-weight: 700;
}

.rec-bar {
  grid-column: 1 / -1;
  margin-top: 4px;
}

.rec-loading {
  padding: 8px 0;
}
</style>
