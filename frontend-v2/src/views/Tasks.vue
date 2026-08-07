<template>
  <div class="tasks-page">
    <el-tabs v-model="activeTab" class="tasks-tabs" type="card">
      <!-- ====== Tab 1: 任务总账 ====== -->
      <el-tab-pane label="任务总账" name="list">
        <div class="tasks-header">
          <div class="title-block">
            <span class="task-total">共 {{ tasksStore.total }} 项，汇总程序开发与文档撰写任务</span>
          </div>
          <div class="tasks-actions">
            <el-input
              v-model="tasksStore.filters.search"
              placeholder="搜索任务..."
              clearable
              style="width: 240px; margin-right: 12px"
              @input="handleSearch"
            />
            <el-select
              v-model="tasksStore.filters.status"
              placeholder="状态"
              clearable
              style="width: 120px; margin-right: 8px"
              @change="tasksStore.fetchTasks"
            >
              <el-option label="待处理" value="pending" />
              <el-option label="已分配" value="assigned" />
              <el-option label="进行中" value="in_progress" />
              <el-option label="审查中" value="review" />
              <el-option label="测试中" value="testing" />
              <el-option label="已完成" value="done" />
            </el-select>
            <el-select
              v-model="tasksStore.filters.priority"
              placeholder="优先级"
              clearable
              style="width: 100px; margin-right: 8px"
              @change="tasksStore.fetchTasks"
            >
              <el-option label="低" value="low" />
              <el-option label="中" value="medium" />
              <el-option label="高" value="high" />
              <el-option label="紧急" value="critical" />
            </el-select>
            <el-select
              v-model="tasksStore.filters.source"
              placeholder="来源"
              clearable
              style="width: 120px; margin-right: 8px"
              @change="tasksStore.fetchTasks"
            >
              <el-option label="全部" value="" />
              <el-option label="程序开发" value="project-dev" />
              <el-option label="文档撰写" value="project-doc" />
              <el-option label="指挥中心" value="command-center" />
              <el-option label="手动创建" value="manual" />
              <el-option label="系统" value="system" />
              <el-option label="调度" value="airflow" />
            </el-select>
            <el-button type="primary" @click="openCreate">
              <el-icon><Plus /></el-icon> 新建任务
            </el-button>
          </div>
        </div>

        <el-alert
          v-if="tasksStore.error"
          :title="tasksStore.error"
          type="error"
          show-icon
          :closable="false"
        />

        <el-table
          :data="tasksStore.tasks"
          v-loading="tasksStore.loading"
          stripe
          style="width: 100%"
          @row-click="handleRowClick"
          highlight-current-row
          class="desktop-table"
        >
          <el-table-column prop="title" label="任务标题" min-width="230">
            <template #default="{ row }">
              <div class="task-title" :title="row.title">{{ row.title }}</div>
              <div v-if="row.parent_title" class="parent-title" :title="row.parent_title">
                上级：{{ row.parent_title }}
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="work_item_type" label="层级" width="92">
            <template #default="{ row }">
              <el-tag :type="row.work_item_type === 'point' ? 'info' : ''" size="small">
                {{ getWorkItemLabel(row) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="project_name" label="所属项目" min-width="130" show-overflow-tooltip>
            <template #default="{ row }">{{ row.project_name || '独立任务' }}</template>
          </el-table-column>
          <el-table-column prop="source" label="来源" width="92">
            <template #default="{ row }">
              <el-tag size="small" effect="plain">{{ getSourceLabel(row.source) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="mission_id" label="关联任务" min-width="120" show-overflow-tooltip>
            <template #default="{ row }">{{ row.mission_id || '—' }}</template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="86">
            <template #default="{ row }">
              <el-tag :type="getStatusType(row.status)" size="small">
                {{ getStatusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="priority" label="优先级" width="70">
            <template #default="{ row }">
              <el-tag :type="getPriorityType(row.priority)" size="small">
                {{ getPriorityLabel(row.priority) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="assignee" label="智能体" width="110">
            <template #default="{ row }">
              <div class="assignee-cell">
                <strong>{{ row.assignee_name || row.assignee || '—' }}</strong>
                <span v-if="row.assignee_name && row.assignee_name !== row.assignee">{{ row.assignee }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="progress" label="进度" width="86">
            <template #default="{ row }">
              <el-tooltip :content="`${row.progress}%`" placement="top">
                <el-progress :percentage="row.progress" :stroke-width="8" :show-text="false" />
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="88" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click.stop="openEdit(row)">编辑</el-button>
              <el-popconfirm
                title="确定删除？"
                confirm-button-text="删除"
                cancel-button-text="取消"
                @confirm="handleDelete(row.task_id)"
              >
                <template #reference>
                  <el-button link type="danger" size="small">删除</el-button>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>

        <!-- 移动端卡片视图（≤768px 显示） -->
        <div class="mobile-cards" v-if="tasksStore.tasks.length">
          <SwipeTaskCard
            v-for="task in tasksStore.tasks"
            :key="task.task_id"
            @edit="openEdit(task)"
            @done="handleComplete(task.task_id)"
            @delete="handleDelete(task.task_id)"
          >
            <div class="mobile-task-card" @click="handleRowClick(task)">
              <div class="card-header">
                <span class="task-id">{{ task.task_id }}</span>
                <el-tag :type="getStatusType(task.status)" size="small">
                  {{ getStatusLabel(task.status) }}
                </el-tag>
                <el-tag :type="getPriorityType(task.priority)" size="small">
                  {{ getPriorityLabel(task.priority) }}
                </el-tag>
              </div>
              <div class="card-title">{{ task.title }}</div>
              <div class="card-meta">
                <span class="meta-item">👤 {{ task.assignee || '未分配' }}</span>
                <span class="meta-item">📂 {{ getSourceLabel(task.source) }}</span>
              </div>
              <div class="card-progress">
                <el-progress :percentage="task.progress" :stroke-width="6" />
              </div>
            </div>
          </SwipeTaskCard>
        </div>

        <el-empty v-if="!tasksStore.tasks.length && !tasksStore.loading && !tasksStore.error" description="暂无符合条件的任务" />

        <div class="pagination-wrapper">
          <el-pagination
            v-model:current-page="tasksStore.pagination.page"
            v-model:page-size="tasksStore.pagination.pageSize"
            :total="tasksStore.total"
            :page-sizes="[10, 20, 50, 100]"
            layout="total, sizes, prev, pager, next"
            @current-change="tasksStore.fetchTasks"
            @size-change="tasksStore.fetchTasks"
          />
        </div>

        <!-- 创建/编辑对话框 -->
        <TaskDialog v-model="showDialog" :task="editingTask" />

        <!-- 任务详情面板 -->
        <TaskDetail
          v-model="showDetail"
          :task="selectedTask"
          @edit="openEdit"
        />
      </el-tab-pane>

      <!-- ====== Tab 2: 调度中心 ====== -->
      <el-tab-pane label="调度中心" name="scheduler">
        <div class="scheduler-header">
          <div class="title-block">
            <span class="task-total">Airflow 调度引擎 · 自动化任务分发与监控</span>
          </div>
          <div class="tasks-actions">
            <el-button type="primary" @click="triggerRun" :loading="triggering">触发运行</el-button>
            <el-button @click="refreshScheduler">刷新</el-button>
          </div>
        </div>

        <!-- 系统状态卡片 -->
        <el-row :gutter="16" class="status-row">
          <el-col :xs="24" :sm="12" :md="6">
            <el-card shadow="hover">
              <div class="stat-card">
                <div class="stat-icon" :class="schedulerStatus?.healthy ? 'healthy' : 'unhealthy'">
                  <el-icon><Connection v-if="schedulerStatus?.healthy" /><CircleClose v-else /></el-icon>
                </div>
                <div class="stat-info">
                  <div class="stat-label">调度系统</div>
                  <div class="stat-value">{{ schedulerStatus?.healthy ? '运行中' : '离线' }}</div>
                </div>
              </div>
            </el-card>
          </el-col>
          <el-col :xs="24" :sm="12" :md="6">
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
          <el-col :xs="24" :sm="12" :md="6">
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
          <el-col :xs="24" :sm="12" :md="6">
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
            <span>DAG 调度任务</span>
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
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { Plus, Connection, List, Clock, AlarmClock, CircleClose } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useTasksStore, type Task } from '@/stores/tasks'
import TaskDialog from '@/components/TaskDialog.vue'
import TaskDetail from '@/components/TaskDetail.vue'
import SwipeTaskCard from '@/components/SwipeTaskCard.vue'
import apiClient from '@/api/client'

const route = useRoute()
const tasksStore = useTasksStore()

// ── Tab control ──
const activeTab = ref((route.query.tab as string) || 'list')

// ── Task list state ──
const showDialog = ref(false)
const showDetail = ref(false)
const editingTask = ref<Task | null>(null)
const selectedTask = ref<Task | null>(null)

// ── Scheduler state ──
const schedulerStatus = ref<any>(null)
const dags = ref<any[]>([])
const queueSummary = ref<any>(null)
const dagRuns = ref<any[]>([])
const taskInstances = ref<any[]>([])
const showHistoryDialog = ref(false)
const showTaskDialog = ref(false)
const currentDagId = ref('')
const triggering = ref(false)

onMounted(() => {
  tasksStore.fetchTasks()
  refreshScheduler()
})

// ── Task list handlers ──
function handleSearch() {
  tasksStore.pagination.page = 1
  tasksStore.fetchTasks()
}

function openCreate() {
  editingTask.value = null
  showDialog.value = true
}

function openEdit(task: Task) {
  editingTask.value = task
  showDialog.value = true
}

function handleRowClick(row: Task) {
  selectedTask.value = row
  tasksStore.selectedTask = row
  showDetail.value = true
}

async function handleDelete(taskId: string) {
  await tasksStore.deleteTaskAction(taskId)
}

async function handleComplete(taskId: string) {
  try {
    await tasksStore.updateTaskAction(taskId, { status: 'done' })
  } catch {
    // 静默处理
  }
}

function getStatusType(status: string): '' | 'success' | 'warning' | 'info' | 'danger' {
  const map: Record<string, '' | 'success' | 'warning' | 'info' | 'danger'> = {
    pending: 'info', assigned: '', in_progress: 'warning',
    review: '', testing: 'warning', done: 'success'
  }
  return map[status] || ''
}

function getStatusLabel(status: string): string {
  const map: Record<string, string> = {
    pending: '待处理', assigned: '已分配', in_progress: '进行中',
    review: '审查中', testing: '测试中', done: '已完成', archived: '已归档'
  }
  return map[status] || status
}

function getPriorityType(priority: string): '' | 'success' | 'warning' | 'info' | 'danger' {
  const map: Record<string, '' | 'success' | 'warning' | 'info' | 'danger'> = {
    low: 'info', medium: '', high: 'warning', critical: 'danger'
  }
  return map[priority] || ''
}

function getPriorityLabel(priority: string): string {
  const map: Record<string, string> = {
    low: '低', medium: '中', high: '高', critical: '紧急'
  }
  return map[priority] || priority
}

function getSourceLabel(source: string): string {
  const map: Record<string, string> = {
    'project-dev': '程序开发',
    'project-doc': '文档撰写',
    'command-center': '指挥中心',
    'manual': '手动',
    'system': '系统',
    'airflow': '调度'
  }
  return map[source] || source || '—'
}

function getWorkItemLabel(task: Task): string {
  if (task.source === 'command-center' && task.work_item_type === 'mission') return '指挥任务'
  if (task.source === 'command-center' && task.work_item_type === 'step') return '执行步骤'
  if (task.work_item_type !== 'point') return '主任务'
  return task.source === 'project-doc' ? '写作子项' : '开发子项'
}

// ── Scheduler handlers ──
const fetchSchedulerStatus = async () => {
  try {
    const res = await apiClient.get('/api/v2/scheduler/status')
    schedulerStatus.value = res.data
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
    await refreshScheduler()
  } catch (e: any) {
    ElMessage.error('触发失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    triggering.value = false
  }
}

const refreshScheduler = async () => {
  await Promise.all([fetchSchedulerStatus(), fetchQueueSummary()])
}

const togglePause = async (dag: any) => {
  try {
    await apiClient.patch(`/api/v2/scheduler/dags/${dag.dag_id}`, {
      is_paused: !dag.is_paused
    })
    ElMessage.success(`${dag.is_paused ? '已恢复' : '已暂停'}调度`)
    await refreshScheduler()
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
</script>

<style scoped>
.tasks-page {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.tasks-tabs {
  width: 100%;
}

/* ── Shared header ── */
.tasks-header,
.scheduler-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
}

.title-block {
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.task-total {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.tasks-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.task-title,
.parent-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.parent-title {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-top: 3px;
}

.assignee-cell {
  display: grid;
  gap: 2px;
}

.assignee-cell strong {
  font-size: 12px;
  line-height: 1.2;
}

.assignee-cell span {
  color: var(--el-text-color-secondary);
  font-size: 11px;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  padding-top: 12px;
}

/* ── Mobile cards ── */
.mobile-cards {
  display: none;
  flex-direction: column;
  gap: 8px;
}

.mobile-task-card {
  padding: 12px;
}

.mobile-task-card .card-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}

.mobile-task-card .task-id {
  font-size: 11px;
  color: #909399;
  font-family: monospace;
}

.mobile-task-card .card-title {
  font-size: 14px;
  font-weight: 600;
  color: #1d2b3a;
  margin-bottom: 8px;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.mobile-task-card .card-meta {
  display: flex;
  gap: 12px;
  margin-bottom: 8px;
}

.mobile-task-card .meta-item {
  font-size: 12px;
  color: #606266;
}

.mobile-task-card .card-progress {
  margin-top: 8px;
}

/* ── Scheduler ── */
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

.stat-icon.clock {
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

/* ── Responsive ── */
@media (max-width: 768px) {
  .desktop-table {
    display: none;
  }

  .mobile-cards {
    display: flex;
  }

  .tasks-header,
  .scheduler-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .tasks-actions {
    width: 100%;
    flex-direction: column;
  }

  .tasks-actions .el-input {
    width: 100% !important;
    margin-right: 0 !important;
  }

  .tasks-actions .el-select {
    width: 100% !important;
    margin-right: 0 !important;
  }

  .tasks-actions .el-button {
    width: 100%;
  }

  .pagination-wrapper {
    justify-content: center;
    overflow-x: auto;
  }
}

@media (max-width: 480px) {
  .mobile-task-card .card-title {
    font-size: 13px;
  }

  .mobile-task-card .card-header {
    flex-wrap: wrap;
  }
}
</style>
