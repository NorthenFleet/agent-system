<template>
  <el-drawer
    v-model="visible"
    title="任务详情"
    size="480px"
    direction="rtl"
    @close="handleClose"
  >
    <template #header="{ titleId, titleClass }">
      <div class="drawer-header">
        <span :id="titleId" :class="titleClass">任务详情</span>
        <el-button v-if="task" size="small" @click="handleEdit">编辑</el-button>
      </div>
    </template>

    <div v-if="task" class="detail-content">
      <!-- 任务基本信息 -->
      <el-descriptions :column="1" border size="default">
        <el-descriptions-item label="ID">{{ task.task_id }}</el-descriptions-item>
        <el-descriptions-item label="标题">{{ task.title }}</el-descriptions-item>
        <el-descriptions-item label="类型">{{ getTypeLabel(task.type) }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="getStatusType(task.status)" size="small">
            {{ getStatusLabel(task.status) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="优先级">
          <el-tag :type="getPriorityType(task.priority)" size="small">
            {{ getPriorityLabel(task.priority) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="负责人">
          {{ task.assignee || '未分配' }}
        </el-descriptions-item>
        <el-descriptions-item label="进度">
          <el-progress :percentage="task.progress" :stroke-width="8" />
        </el-descriptions-item>
        <el-descriptions-item label="描述">
          {{ task.description || '暂无描述' }}
        </el-descriptions-item>
        <el-descriptions-item v-if="task.start_date" label="开始日期">
          {{ task.start_date.split('T')[0] }}
        </el-descriptions-item>
        <el-descriptions-item v-if="task.due_date" label="截止日期">
          {{ task.due_date.split('T')[0] }}
        </el-descriptions-item>
        <el-descriptions-item v-if="task.tags?.length" label="标签">
          <el-tag v-for="tag in task.tags" :key="tag" size="small" style="margin-right: 4px">
            {{ tag }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="创建时间">
          {{ formatTime(task.created_at) }}
        </el-descriptions-item>
        <el-descriptions-item label="更新时间">
          {{ formatTime(task.updated_at) }}
        </el-descriptions-item>
      </el-descriptions>

      <el-divider />

      <!-- 评论区域 -->
      <div class="comments-section">
        <h4>💬 评论 ({{ tasksStore.comments.length }})</h4>
        <div class="comments-list">
          <div v-for="comment in tasksStore.comments" :key="comment.id" class="comment-item">
            <div class="comment-author">
              {{ comment.user?.display_name || '匿名' }}
            </div>
            <div class="comment-content">{{ comment.content }}</div>
            <div class="comment-time">{{ formatTime(comment.created_at) }}</div>
          </div>
          <el-empty
            v-if="!tasksStore.comments.length"
            description="暂无评论"
            :image-size="40"
          />
        </div>
        <div class="comment-input">
          <el-input
            v-model="newComment"
            type="textarea"
            :rows="2"
            placeholder="添加评论..."
            @keydown.ctrl.enter="submitComment"
          />
          <div class="comment-input-actions">
            <span class="comment-hint">Ctrl + Enter 发送</span>
            <el-button
              type="primary"
              size="small"
              :disabled="!newComment.trim()"
              @click="submitComment"
            >
              发送
            </el-button>
          </div>
        </div>
      </div>

      <!-- 操作按钮 -->
      <div class="detail-actions">
        <el-popconfirm
          title="确定要删除此任务吗？"
          confirm-button-text="删除"
          cancel-button-text="取消"
          @confirm="handleDelete"
        >
          <template #reference>
            <el-button type="danger" plain>删除任务</el-button>
          </template>
        </el-popconfirm>
      </div>
    </div>

    <div v-else class="detail-empty">
      <el-empty description="请选择一个任务查看详情" />
    </div>
  </el-drawer>

  <!-- 编辑对话框 -->
  <TaskDialog
    v-model="showEditDialog"
    :task="task"
  />
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useTasksStore } from '@/stores/tasks'
import type { Task } from '@/stores/tasks'
import TaskDialog from './TaskDialog.vue'

const props = defineProps<{
  modelValue: boolean
  task: Task | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  edit: [task: Task]
}>()

const tasksStore = useTasksStore()
const newComment = ref('')
const showEditDialog = ref(false)

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v)
})

const task = computed(() => props.task)

function handleClose() {
  emit('update:modelValue', false)
  newComment.value = ''
}

function handleEdit() {
  if (props.task) {
    emit('edit', props.task)
    handleClose()
  }
}

async function handleDelete() {
  if (props.task) {
    try {
      await tasksStore.deleteTaskAction(props.task.task_id)
      ElMessage.success('任务已删除')
      handleClose()
    } catch {
      ElMessage.error('删除失败')
    }
  }
}

async function submitComment() {
  if (!newComment.value.trim() || !props.task) return
  try {
    await tasksStore.addCommentAction(props.task.task_id, newComment.value.trim())
    newComment.value = ''
    ElMessage.success('评论已发送')
  } catch {
    ElMessage.error('评论发送失败')
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

function getTypeLabel(type: string): string {
  const map: Record<string, string> = {
    fullstack: '全栈', backend: '后端', frontend: '前端',
    testing: '测试', general: '其他'
  }
  return map[type] || type
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
  justify-content: space-between;
  width: 100%;
}

.detail-content {
  display: flex;
  flex-direction: column;
}

.comments-section {
  margin-top: 16px;
}

.comments-section h4 {
  margin: 0 0 12px;
  font-size: 14px;
  color: #606266;
}

.comments-list {
  max-height: 300px;
  overflow-y: auto;
  margin-bottom: 12px;
}

.comment-item {
  padding: 8px 0;
  border-bottom: 1px solid #f0f0f0;
}

.comment-author {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 2px;
}

.comment-content {
  font-size: 13px;
  color: #606266;
  word-break: break-word;
}

.comment-time {
  font-size: 12px;
  color: #c0c4cc;
  margin-top: 2px;
}

.comment-input {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.comment-input-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.comment-hint {
  font-size: 12px;
  color: #c0c4cc;
}

.detail-actions {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.detail-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 400px;
}
</style>
