<template>
  <div class="scheduled-page">
    <el-card class="panel" shadow="hover">
      <template #header>
        <div class="panel-header">
          <div>
            <span>定时任务</span>
            <div class="muted">{{ managerText }}</div>
          </div>
          <el-button size="small" type="primary" @click="loadTasks">刷新</el-button>
        </div>
      </template>
      <el-table :data="tasks" size="small" height="640">
        <el-table-column prop="name" label="任务" min-width="220" show-overflow-tooltip />
        <el-table-column prop="owner" label="负责人" width="110" />
        <el-table-column prop="schedule" label="周期" width="150" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="next_run" label="下次运行" min-width="210" show-overflow-tooltip />
        <el-table-column prop="last_run" label="上次运行" min-width="210" show-overflow-tooltip />
        <el-table-column prop="description" label="说明" min-width="260" show-overflow-tooltip />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getScheduledTasks, type ScheduledTask } from '@/api/openclaw'

const tasks = ref<ScheduledTask[]>([])
const managedBy = ref('')
const managerRole = ref('')

const managerText = computed(() => managedBy.value ? `${managedBy.value} · ${roleLabel(managerRole.value)}` : '调度信息加载中')

async function loadTasks() {
  try {
    const data = await getScheduledTasks()
    tasks.value = data.tasks
    managedBy.value = data.managed_by || ''
    managerRole.value = data.manager_role || ''
  } catch {
    ElMessage.error('定时任务加载失败')
  }
}

onMounted(loadTasks)

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    active: '启用',
    pending: '待启用',
    paused: '已暂停',
    disabled: '已停用',
    failed: '失败'
  }
  return map[status] || status
}

function roleLabel(role: string): string {
  const map: Record<string, string> = {
    scheduler: '调度器',
    manager: '管理器',
    system: '系统'
  }
  return map[role] || role
}
</script>

<style scoped>
.panel {
  border-radius: 8px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.muted {
  color: #909399;
  font-size: 13px;
  margin-top: 4px;
}
</style>
