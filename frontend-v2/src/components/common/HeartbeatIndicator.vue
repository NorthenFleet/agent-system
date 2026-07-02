<template>
  <span
    class="heartbeat-dot"
    :class="[`status-${agent.health}`]"
    :title="`最近心跳: ${formatHeartbeatAge(agent.heartbeat_age_seconds)}`"
  />
</template>

<script setup lang="ts">
import type { Agent } from '@/stores/agents'

defineProps<{
  agent: Agent
}>()

function formatHeartbeatAge(seconds: number | null): string {
  if (seconds == null) return '无数据'
  if (seconds < 60) return `${Math.round(seconds)}秒前`
  return `${Math.round(seconds / 60)}分钟前`
}
</script>

<style scoped>
.heartbeat-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #909399;
}

.status-healthy {
  background: #67c23a;
  box-shadow: 0 0 6px #67c23a88;
}

.status-warning {
  background: #e6a23c;
  box-shadow: 0 0 6px #e6a23c88;
}

.status-critical {
  background: #f56c6c;
  box-shadow: 0 0 6px #f56c6c88;
  animation: blink 1s ease-in-out infinite;
}

.status-offline {
  background: #909399;
  opacity: 0.5;
  animation: blink 1.5s ease-in-out infinite;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
</style>
