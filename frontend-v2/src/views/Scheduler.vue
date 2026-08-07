<template>
  <div class="scheduler-page">
    <div class="page-header">
      <h2>任务调度中心</h2>
      <div class="header-actions">
        <el-button type="primary" @click="triggerRun" :loading="triggering">触发运行</el-button>
        <el-button @click="refreshAll">刷新</el-button>
      </div>
    </div>

    <!-- 系统状态卡片 -->
    <el-row :gutter="16" class="status-row">
      <el-col :span="6">
        <el-card shadow="hover">
          <div class="stat-card">
            <div class="stat-icon" :class="status?.healthy ? 'healthy' : 'unhealthy'">
              <el-icon><Connection v-if="status?.healthy" /><CircleClose v-else /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-label">调度系统</div>
              <div class="stat-value">{{ status?.healthy ? '运行中' : '离线' }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <div class="stat-card">
            <div class="stat-icon tasks">
              <el-icon><List /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-label">任务总数</div>
              <div class="stat-value">{{ queueSummary?.total_tasks || 0 }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <div class="stat-card">
            <div class="stat-icon sprint">
              <el-icon><AlarmClock /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-label">当前 Sprint</div>
              <div class="stat-value">S{{ queueSummary?.sprint || 0 }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <div class="stat-card">
            <div class="stat-icon clock">
              <el-icon><Clock /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-label">最近运行</div>
              <div class="stat-value">{{ formatTime(queueSummary?.latest_airflow_run?.end_date) }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- DAG 列表 -->
    <el-card class="dag-section">
      <template #header>
        <div class="card-header">
          <span>DAG 调度任务</span>
        </div>
      </template>

      <el-table :data="dags" stripe style="width: 100%">
        <el-table-column prop="dag_id" label="DAG ID" min-width="180" />
        <el-table-column prop="dag_display_name" label="显示名称" min-width="150" />
        <el-table-column prop="schedule_interval" label="调度周期" min-width="120" />
        <el-table-column label="最近运行" min-width="100">
          <template #default="{ row }">
            <el-tag :type="row.last_run_state === 'success' ? 'success' : row.last_run_state === 'running' ? 'warning' : 'info'">
              {{ row.last_run_state || '未运行' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" min-width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_paused ? 'danger' : 'success'">
              {{ row.is_paused ? '已暂停' : '运行中' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150">
          <template #default="{ row }">
            <el-button size="small" @click="togglePause(row)">
              {{ row.is_paused ? '恢复' : '暂停' }}
            </el-button>
            <el-button size="small" type="primary" @click="showRunHistory(row.dag_id)">
              历史
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 任务状态分布 -->
    <el-card v-if="queueSummary?.status_breakdown" class="status-breakdown">
      <template #header>
        <span>任务状态分布</span>
      </template>
      <div class="breakdown-grid">
        <div v-for="(count, status) in queueSummary.status_breakdown" :key="status" class="breakdown-item">
          <div class="breakdown-count">{{ count }}</div>
          <div class="breakdown-status">{{ statusLabel(String(status)) }}</div>
        </div>
      </div>
    </el-card>

    <!-- 运行历史对话框 -->
    <el-dialog v-model="showHistoryDialog" :title="`${currentDagId} 运行历史`" width="800px">
      <el-table :data="dagRuns" stripe>
        <el-table-column prop="dag_run_id" label="运行ID" min-width="200" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.state === 'success' ? 'success' : row.state === 'failed' ? 'danger' : 'warning'">
              {{ row.state }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="start_date" label="开始时间" min-width="180" />
        <el-table-column prop="end_date" label="结束时间" min-width="180" />
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button size="small" @click="showTaskInstances(currentDagId, row.dag_run_id)">
              查看任务
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 任务实例对话框 -->
    <el-dialog v-model="showTaskDialog" title="任务实例详情" width="700px">
      <el-table :data="taskInstances" stripe>
        <el-table-column prop="task_id" label="任务" min-width="150" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.state === 'success' ? 'success' : row.state === 'failed' ? 'danger' : 'warning'">
              {{ row.state }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="start_date" label="开始" min-width="160" />
        <el-table-column prop="end_date" label="结束" min-width="160" />
        <el-table-column label="耗时" min-width="80">
          <template #default="{ row }">
            {{ calcDuration(row.start_date, row.end_date) }}
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Connection, List, Clock, AlarmClock, CircleClose } from '@element-plus/icons-vue'
import apiClient from '@/api/client'

// Data
const status = ref<any>(null)
const dags = ref<any[]>([])
const queueSummary = ref<any>(null)
const dagRuns = ref<any[]>([])
const taskInstances = ref<any[]>([])

// Dialog state
const showHistoryDialog = ref(false)
const showTaskDialog = ref(false)
const currentDagId = ref('')
const triggering = ref(false)

// API calls
const fetchStatus = async () => {
  try {
    const res = await apiClient.get('/api/v2/scheduler/status')
    status.value = res.data
    dags.value = res.data.dags || []
  } catch (e: any) {
    console.error('Failed to fetch scheduler status:', e)
  }
}

const fetchQueueSummary = async () => {
  try {
    const res = await apiClient.get('/api/v2/scheduler/queue-summary')
    queueSummary.value = res.data
  } catch (e: any) {
    console.error('Failed to fetch queue summary:', e)
  }
}

const triggerRun = async () => {
  try {
    triggering.value = true
    await apiClient.post('/api/v2/scheduler/dags/dev_loop_task_pipeline/dagRuns')
    ElMessage.success('触发成功，请等待调度系统响应')
    await refreshAll()
  } catch (e: any) {
    ElMessage.error('触发失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    triggering.value = false
  }
}

const refreshAll = async () => {
  await Promise.all([fetchStatus(), fetchQueueSummary()])
}

const togglePause = async (dag: any) => {
  try {
    await apiClient.patch(`/api/v2/scheduler/dags/${dag.dag_id}`, {
      is_paused: !dag.is_paused
    })
    ElMessage.success(`${dag.is_paused ? '已恢复' : '已暂停'}调度`)
    await refreshAll()
  } catch (e: any) {
    ElMessage.error('操作失败')
  }
}

const showRunHistory = async (dagId: string) => {
  try {
    currentDagId.value = dagId
    const res = await apiClient.get(`/api/v2/scheduler/dags/${dagId}/dagRuns?limit=20`)
    dagRuns.value = res.data.dag_runs || []
    showHistoryDialog.value = true
  } catch (e: any) {
    ElMessage.error('获取历史失败')
  }
}

const showTaskInstances = async (dagId: string, dagRunId: string) => {
  try {
    const res = await apiClient.get(`/api/v2/scheduler/dags/${dagId}/dagRuns/${dagRunId}/taskInstances`)
    taskInstances.value = res.data.task_instances || []
    showTaskDialog.value = true
  } catch (e: any) {
    ElMessage.error('获取任务实例失败')
  }
}

// Helpers
const formatTime = (dateStr: string) => {
  if (!dateStr) return '无'
  const d = new Date(dateStr)
  return d.toLocaleString('zh-CN', { hour: '2-digit', minute: '2-digit', month: '2-digit', day: '2-digit' })
}

const calcDuration = (start: string, end: string) => {
  if (!start || !end) return '-'
  const ms = new Date(end).getTime() - new Date(start).getTime()
  const sec = Math.floor(ms / 1000)
  if (sec < 60) return `${sec}s`
  return `${Math.floor(sec / 60)}m ${sec % 60}s`
}

const statusLabel = (status: string | number) => {
  const labels: Record<string, string> = {
    assigned: '已分配',
    in_progress: '执行中',
    review: '待审核',
    done: '已完成',
    blocked: '阻塞',
    archived: '已归档'
  }
  return labels[status] || status
}

onMounted(() => {
  refreshAll()
})
</script>

<style scoped>
.scheduler-page {
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}

.status-row {
  margin-bottom: 20px;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 12px;
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  color: white;
}

.stat-icon.healthy {
  background: #67c23a;
}

.stat-icon.unhealthy {
  background: #f56c6c;
}

.stat-icon.tasks {
  background: #409eff;
}

.stat-icon.sprint {
  background: #e6a23c;
}

.stat-icon.last-run {
  background: #909399;
}

.stat-info {
  flex: 1;
}

.stat-label {
  font-size: 12px;
  color: #909399;
}

.stat-value {
  font-size: 18px;
  font-weight: 600;
  margin-top: 4px;
}

.dag-section {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.status-breakdown {
  margin-bottom: 20px;
}

.breakdown-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 12px;
}

.breakdown-item {
  text-align: center;
  padding: 16px;
  background: #f5f7fa;
  border-radius: 8px;
}

.breakdown-count {
  font-size: 28px;
  font-weight: 700;
  color: #409eff;
}

.breakdown-status {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
</style>
