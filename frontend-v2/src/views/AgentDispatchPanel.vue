<template>
  <div class="dispatch-panel">
    <!-- 页面标题 -->
    <div class="page-header">
      <div class="page-title">
        <h1>📋 任务派发</h1>
        <p class="page-desc">选择任务 → 选择 Agent → 一键派发</p>
      </div>
    </div>

    <el-row :gutter="24">
      <!-- 左侧：派发表单 -->
      <el-col :xs="24" :md="16">
        <el-card class="dispatch-form-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>🚀 派发任务</span>
              <el-tag v-if="lastDispatch" type="success" size="small">
                最近派发: {{ lastDispatch }}
              </el-tag>
            </div>
          </template>

          <el-form
            ref="formRef"
            :model="form"
            :rules="rules"
            label-position="top"
            label-width="auto"
            class="dispatch-form"
            @submit.prevent="handleSubmit"
          >
            <!-- 选择 Agent -->
            <el-form-item label="🤖 选择 Agent" prop="agentId">
              <el-select
                v-model="form.agentId"
                placeholder="请选择要派发的智能体"
                filterable
                class="full-width"
                :loading="agentsStore.loading"
                @change="onAgentChange"
              >
                <el-option
                  v-for="agent in availableAgents"
                  :key="agent.agent_id"
                  :label="agent.agent_name || agent.agent_id"
                  :value="agent.agent_id"
                  :disabled="agent.status === 'offline'"
                >
                  <div class="agent-option">
                    <span class="agent-option-emoji">{{ agentEmoji(agent.agent_id) }}</span>
                    <span class="agent-option-name">{{ agent.agent_name || agent.agent_id }}</span>
                    <el-tag
                      :type="statusType(agent.status)"
                      size="small"
                      class="agent-option-status"
                    >
                      {{ statusLabel(agent.status) }}
                    </el-tag>
                  </div>
                </el-option>
              </el-select>
            </el-form-item>

            <!-- Agent 当前状态预览 -->
            <el-alert
              v-if="selectedAgentInfo"
              :title="`${agentEmoji(selectedAgentInfo.agent_id)} ${selectedAgentInfo.agent_name || selectedAgentInfo.agent_id}`"
              :type="selectedAgentInfo.status === 'offline' ? 'error' : 'info'"
              :closable="false"
              show-icon
              class="agent-preview"
            >
              <template #default>
                <div class="agent-preview-detail">
                  <span>当前任务: <strong>{{ selectedAgentInfo.current_task || '待分配' }}</strong></span>
                  <span>状态: <strong>{{ statusLabel(selectedAgentInfo.status) }}</strong></span>
                  <span v-if="selectedAgentInfo.last_heartbeat">最后心跳: <strong>{{ selectedAgentInfo.last_heartbeat }}</strong></span>
                </div>
              </template>
            </el-alert>

            <!-- 选择任务 -->
            <el-form-item label="📝 选择任务" prop="taskId">
              <el-select
                v-model="form.taskId"
                placeholder="请选择要派发的任务"
                filterable
                class="full-width"
                :loading="tasksLoading"
                @change="onTaskChange"
              >
                <el-option
                  v-for="task in availableTasks"
                  :key="task.id"
                  :label="task.title"
                  :value="task.id"
                >
                  <div class="task-option">
                    <span class="task-option-id">{{ task.id }}</span>
                    <span class="task-option-title">{{ task.title }}</span>
                    <el-tag
                      :type="taskPriorityType(task.priority)"
                      size="small"
                    >
                      {{ task.priority || 'normal' }}
                    </el-tag>
                  </div>
                </el-option>
              </el-select>
            </el-form-item>

            <!-- 任务详情预览 -->
            <el-alert
              v-if="selectedTaskInfo"
              :title="`任务: ${selectedTaskInfo.title}`"
              type="info"
              :closable="false"
              show-icon
              class="task-preview"
            >
              <template #default>
                <div class="task-preview-detail">
                  <span>类型: <strong>{{ selectedTaskInfo.type || '-' }}</strong></span>
                  <span>优先级: <strong>{{ selectedTaskInfo.priority || 'normal' }}</strong></span>
                  <span v-if="selectedTaskInfo.assignee">当前负责人: <strong>{{ selectedTaskInfo.assignee }}</strong></span>
                </div>
              </template>
            </el-alert>

            <!-- 派发备注 -->
            <el-form-item label="📌 派发备注" prop="notes">
              <el-input
                v-model="form.notes"
                type="textarea"
                :rows="3"
                placeholder="可选：添加派发说明..."
                maxlength="200"
                show-word-limit
              />
            </el-form-item>

            <!-- 提交按钮 -->
            <el-form-item class="submit-row">
              <el-button
                type="primary"
                :icon="Promotion"
                :loading="submitting"
                :disabled="!canSubmit"
                size="large"
                @click="handleSubmit"
              >
                {{ submitting ? '派发中...' : '确认派发' }}
              </el-button>
              <el-button
                :icon="Refresh"
                @click="resetForm"
              >
                重置
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <!-- 右侧：派发历史 -->
      <el-col :xs="24" :md="8">
        <el-card class="dispatch-history-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>📜 派发历史</span>
              <el-button
                :icon="Refresh"
                size="small"
                text
                @click="fetchHistory"
              >
                刷新
              </el-button>
            </div>
          </template>

          <el-empty
            v-if="historyList.length === 0 && !historyLoading"
            description="暂无派发记录"
            :image-size="80"
          />

          <div v-else class="history-list">
            <div
              v-for="item in historyList"
              :key="item.id"
              class="history-item"
              :class="'history-' + item.status"
            >
              <div class="history-item-header">
                <span class="history-agent">
                  {{ agentEmoji(item.agent_id) }} {{ item.agent_name || item.agent_id }}
                </span>
                <el-tag :type="dispatchStatusType(item.status)" size="small">
                  {{ dispatchStatusLabel(item.status) }}
                </el-tag>
              </div>
              <div class="history-item-body">
                <span class="history-task">📝 {{ item.task_id }}</span>
                <span class="history-dispatcher">👤 {{ item.dispatcher_id || '-' }}</span>
                <span class="history-time">🕐 {{ formatTime(item.dispatched_at) }}</span>
              </div>
              <div v-if="item.notes" class="history-notes">{{ item.notes }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Promotion, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { useAgentsStore, type Agent } from '@/stores/agents'
import { dispatchAgent } from '@/api/agents'

// ===================== 类型 =====================

interface TaskOption {
  id: string
  title: string
  type?: string
  priority?: string
  assignee?: string
  status?: string
}

interface DispatchHistoryItem {
  id: number
  agent_id: string
  agent_name?: string
  task_id: string
  dispatcher_id: string
  dispatched_at: string
  status: string
  notes?: string
}

// ===================== Store =====================
const agentsStore = useAgentsStore()

// ===================== 表单 =====================
const formRef = ref<FormInstance>()
const submitting = ref(false)

const form = ref({
  agentId: '',
  taskId: '',
  notes: ''
})

const rules: FormRules = {
  agentId: [{ required: true, message: '请选择要派发的智能体', trigger: 'change' }],
  taskId: [{ required: true, message: '请选择要派发的任务', trigger: 'change' }]
}

// ===================== Agent 列表 =====================
const availableAgents = computed<Agent[]>(() => agentsStore.agents)

function agentEmoji(id: string): string {
  const map: Record<string, string> = {
    optimus: '🤖',
    leonardo: '🟦',
    raphael: '🟥',
    donatello: '🟪',
    michelangelo: '🟧',
    ironhide: '🛡️',
    perceptor: '🚗',
    ratchet: '🚑',
    wheeljack: '🔧',
    soundwave: '🔷',
    jazz: '🎷',
    bumblebee: '🐝',
    shockwave: '🟣',
    'ultra-magnus': '🔵',
    'wheeljack-leonardo': '🟦',
    'wheeljack-raphael': '🟥',
    'wheeljack-donatello': '🟪',
    'wheeljack-michelangelo': '🟧'
  }
  return map[id] || '🤖'
}

function statusType(status: string): '' | 'success' | 'warning' | 'info' | 'danger' {
  const map: Record<string, '' | 'success' | 'warning' | 'info' | 'danger'> = {
    online: 'success',
    busy: 'warning',
    idle: 'info',
    offline: 'danger'
  }
  return map[status] || 'info'
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    online: '在线',
    busy: '忙碌',
    idle: '空闲',
    pending: '待命',
    offline: '离线'
  }
  return map[status] || status || '未知'
}

const selectedAgentInfo = computed<Agent | null>(() => {
  if (!form.value.agentId) return null
  return availableAgents.value.find(a => a.agent_id === form.value.agentId) || null
})

function onAgentChange() {
  // Agent 切换时可做额外逻辑
}

// ===================== 任务列表 =====================
const availableTasks = ref<TaskOption[]>([])
const tasksLoading = ref(false)
const selectedTaskInfo = ref<TaskOption | null>(null)

async function fetchTasks() {
  tasksLoading.value = true
  try {
    // 调用后端任务列表 API 获取待派发任务
    const token = localStorage.getItem('jwt_token')
    const res = await fetch('/api/v2/tasks?status=pending&status=in_progress&status=assigned&page_size=100', {
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    })
    if (res.ok) {
      const data = await res.json()
      const items = data.tasks || data.items || []
      availableTasks.value = items.map((t: any) => ({
        id: t.id,
        title: t.title || t.name || t.id,
        type: t.type,
        priority: t.priority,
        assignee: t.assignee,
        status: t.status
      }))
    }
  } catch {
    // 降级：使用空列表，不阻断表单
    availableTasks.value = []
  } finally {
    tasksLoading.value = false
  }
}

function onTaskChange() {
  selectedTaskInfo.value = availableTasks.value.find(t => t.id === form.value.taskId) || null
}

function taskPriorityType(priority?: string): '' | 'danger' | 'warning' | 'info' | 'success' {
  const map: Record<string, '' | 'danger' | 'warning' | 'info' | 'success'> = {
    critical: 'danger',
    high: 'warning',
    medium: 'info',
    normal: 'success',
    low: 'info'
  }
  return map[priority || ''] || 'info'
}

// ===================== 派发提交 =====================
const canSubmit = computed(() => {
  return !!form.value.agentId && !!form.value.taskId && !submitting.value
})

const lastDispatch = ref('')

async function handleSubmit() {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }

  submitting.value = true
  try {
    const result = await dispatchAgent(form.value.agentId, {
      task_id: form.value.taskId,
      notes: form.value.notes || undefined
    })

    lastDispatch.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
    ElMessage.success(`✅ 任务 ${form.value.taskId} 已派发给智能体 ${form.value.agentId}`)

    // 刷新 Agent 数据
    await agentsStore.fetchAgents()

    // 重置表单
    resetForm()

    // 刷新历史记录
    await fetchHistory()

    console.log('[派发成功]', result)
  } catch (error: any) {
    const msg = error?.response?.data?.detail || '派发失败，请检查网络后重试'
    ElMessage.error(msg)
  } finally {
    submitting.value = false
  }
}

function resetForm() {
  form.value = {
    agentId: '',
    taskId: '',
    notes: ''
  }
  selectedTaskInfo.value = null
  formRef.value?.clearValidate()
}

// ===================== 派发历史 =====================
const historyList = ref<DispatchHistoryItem[]>([])
const historyLoading = ref(false)

async function fetchHistory() {
  historyLoading.value = true
  try {
    const token = localStorage.getItem('jwt_token')
    const res = await fetch('/api/v2/agents/dispatches?page_size=50', {
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    })
    if (res.ok) {
      const data = await res.json()
      historyList.value = (data.dispatches || data.items || []).map((item: any) => ({
        id: item.id,
        agent_id: item.agent_id,
        agent_name: item.agent_name,
        task_id: item.task_id,
        dispatcher_id: item.dispatcher_id,
        dispatched_at: item.dispatched_at,
        status: item.status,
        notes: item.notes
      }))
    }
  } catch {
    historyList.value = []
  } finally {
    historyLoading.value = false
  }
}

function dispatchStatusType(status: string): '' | 'success' | 'warning' | 'info' | 'danger' {
  const map: Record<string, '' | 'success' | 'warning' | 'info' | 'danger'> = {
    dispatched: 'success',
    accepted: 'success',
    running: 'warning',
    completed: 'info',
    failed: 'danger',
    rejected: 'danger'
  }
  return map[status] || 'info'
}

function dispatchStatusLabel(status: string): string {
  const map: Record<string, string> = {
    dispatched: '已派发',
    accepted: '已接受',
    running: '执行中',
    completed: '已完成',
    failed: '失败',
    rejected: '已拒绝'
  }
  return map[status] || status || '未知'
}

function formatTime(iso: string): string {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    return d.toLocaleString('zh-CN', { hour12: false, month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  } catch {
    return iso
  }
}

// ===================== 生命周期 =====================
onMounted(async () => {
  await Promise.allSettled([
    agentsStore.fetchAgents(),
    fetchTasks(),
    fetchHistory()
  ])
})
</script>

<style scoped>
.dispatch-panel {
  padding: 16px;
  min-height: 100%;
}

/* ===================== 页面头部 ===================== */
.page-header {
  margin-bottom: 20px;
}

.page-title h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 800;
  color: #e0e0e0;
}

.page-desc {
  margin: 4px 0 0;
  color: #888;
  font-size: 13px;
}

/* ===================== 卡片 ===================== */
.dispatch-form-card,
.dispatch-history-card {
  border-radius: 10px;
  border: 1px solid #333;
  background: #1a1a1a;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 15px;
  font-weight: 700;
  color: #e0e0e0;
}

:deep(.el-card__header) {
  border-bottom: 1px solid #2a2a2a;
}

:deep(.el-card__body) {
  padding: 20px;
}

/* ===================== 表单 ===================== */
.dispatch-form {
  max-width: 600px;
}

.full-width {
  width: 100%;
}

:deep(.el-form-item__label) {
  color: #b0b0b0;
  font-weight: 600;
}

/* ===================== 下拉选项 ===================== */
.agent-option {
  display: flex;
  align-items: center;
  gap: 8px;
}

.agent-option-emoji {
  font-size: 16px;
}

.agent-option-name {
  flex: 1;
  font-weight: 500;
}

.agent-option-status {
  margin-left: auto;
}

.task-option {
  display: flex;
  align-items: center;
  gap: 8px;
}

.task-option-id {
  color: #888;
  font-size: 12px;
  font-family: monospace;
}

.task-option-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ===================== 预览 ===================== */
.agent-preview,
.task-preview {
  margin-bottom: 16px;
}

:deep(.el-alert__content) {
  flex: 1;
}

.agent-preview-detail,
.task-preview-detail {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  font-size: 13px;
  color: #b0b0b0;
}

.agent-preview-detail span,
.task-preview-detail span {
  display: inline-flex;
  gap: 4px;
}

/* ===================== 提交行 ===================== */
.submit-row {
  margin-top: 8px;
}

.submit-row :deep(.el-form-item__content) {
  display: flex;
  gap: 12px;
}

/* ===================== 历史记录 ===================== */
.history-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 600px;
  overflow-y: auto;
}

.history-item {
  padding: 12px;
  border-radius: 8px;
  border: 1px solid #2a2a2a;
  background: #1e1e1e;
  transition: border-color 0.15s;
}

.history-item:hover {
  border-color: #409eff;
}

.history-item-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.history-agent {
  font-size: 14px;
  font-weight: 600;
  color: #e0e0e0;
}

.history-item-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: #888;
}

.history-task {
  font-family: monospace;
  color: #b0b0b0;
}

.history-dispatcher {
  color: #666;
}

.history-time {
  color: #666;
}

.history-notes {
  margin-top: 8px;
  padding: 6px 8px;
  border-radius: 4px;
  background: #2a2a2a;
  font-size: 12px;
  color: #b0b0b0;
}

/* ===================== 响应式 ===================== */
@media (max-width: 768px) {
  .dispatch-panel {
    padding: 12px;
  }

  .dispatch-form {
    max-width: 100%;
  }

  .page-title h1 {
    font-size: 18px;
  }
}
</style>
