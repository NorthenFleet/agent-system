<template>
  <div class="devices-page">
    <el-row :gutter="14">
      <el-col v-for="device in devices" :key="device.id" :xs="24" :md="8">
        <el-card class="device-card" shadow="hover">
          <div class="device-header">
            <div>
              <div class="device-name">{{ device.name }}</div>
              <div class="muted">{{ device.ip }} · {{ device.location || '未知位置' }}</div>
            </div>
            <el-tag :type="device.status === 'online' ? 'success' : 'info'">{{ statusLabel(device.status) }}</el-tag>
          </div>
          <div class="device-meta">
            <div><span>系统</span><strong>{{ device.os || '未知' }}</strong></div>
            <div><span>角色</span><strong>{{ device.role || '未设置' }}</strong></div>
            <div><span>端口</span><strong>{{ device.ports?.join(', ') || '无' }}</strong></div>
          </div>
          <el-divider />
          <div class="agent-list">
            <el-tag v-for="agent in device.assigned_agents_details || []" :key="agent.id" size="small">{{ agent.name }}</el-tag>
            <span v-if="!device.assigned_agents_details?.length" class="muted">暂无绑定智能体</span>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getDevices, type DeviceItem } from '@/api/openclaw'

const devices = ref<DeviceItem[]>([])
let refreshTimer: ReturnType<typeof window.setInterval> | undefined

async function loadDevices() {
  try {
    const data = await getDevices()
    devices.value = data.devices
  } catch {
    ElMessage.error('设备数据加载失败')
  }
}

onMounted(() => {
  loadDevices()
  refreshTimer = window.setInterval(loadDevices, 15000)
})

onUnmounted(() => {
  if (refreshTimer) {
    window.clearInterval(refreshTimer)
  }
})

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    online: '在线',
    offline: '离线',
    idle: '空闲',
    busy: '忙碌',
    unknown: '未知'
  }
  return map[status] || status
}
</script>

<style scoped>
.device-card {
  border-radius: 8px;
  margin-bottom: 14px;
}

.device-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.device-name {
  color: #303133;
  font-size: 16px;
  font-weight: 700;
}

.muted {
  color: #909399;
  font-size: 13px;
}

.device-meta {
  display: grid;
  gap: 10px;
  margin-top: 16px;
}

.device-meta div {
  display: grid;
  gap: 4px;
}

.device-meta span {
  color: #909399;
  font-size: 12px;
}

.device-meta strong {
  color: #606266;
  font-size: 13px;
}

.agent-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
</style>
