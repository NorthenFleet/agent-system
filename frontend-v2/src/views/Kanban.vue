<template>
  <div class="kanban-page">
    <div class="kanban-header">
      <h2>看板视图</h2>
      <div class="kanban-controls">
        <el-button type="primary" @click="openCreate">
          <el-icon><Plus /></el-icon> 新建任务
        </el-button>
      </div>
    </div>

    <div class="kanban-board">
      <div
        v-for="column in columns"
        :key="column.key"
        class="kanban-column"
        :class="{ 'drag-over': dragOverColumn === column.key }"
        @dragover.prevent="dragOverColumn = column.key"
        @dragleave="dragOverColumn = null"
        @drop="handleDrop(column.key)"
      >
        <div class="column-header">
          <span class="column-title">{{ column.title }}</span>
          <span class="column-count">{{ getTasksByStatus(column.key).length }}</span>
        </div>
        <div class="column-body">
          <div
            v-for="task in getTasksByStatus(column.key)"
            :key="task.task_id"
            class="kanban-card"
            draggable="true"
            @dragstart="handleDragStart(task)"
          >
            <div class="card-top">
              <el-tag :type="getPriorityType(task.priority)" size="small">
                {{ getPriorityLabel(task.priority) }}
              </el-tag>
              <span class="card-id">{{ task.task_id }}</span>
            </div>
            <div class="card-title">{{ task.title }}</div>
            <div class="card-footer">
              <span class="card-assignee">
                {{ getAgentEmoji(task.assignee) }} {{ task.assignee || '未分配' }}
              </span>
              <el-progress
                v-if="task.progress > 0"
                :percentage="task.progress"
                :stroke-width="4"
                style="width: 60px"
              />
            </div>
            <div class="card-actions">
              <el-button link size="small" @click.stop="openDetail(task)">详情</el-button>
            </div>
          </div>
          <div v-if="!getTasksByStatus(column.key).length" class="column-empty">
            暂无任务
          </div>
        </div>
      </div>
    </div>

    <!-- 创建/编辑对话框 -->
    <TaskDialog v-model="showDialog" :task="editingTask" />

    <!-- 任务详情面板 -->
    <TaskDetail
      v-model="showDetail"
      :task="selectedTask"
      @edit="openEdit"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { useTasksStore, type Task } from '@/stores/tasks'
import TaskDialog from '@/components/TaskDialog.vue'
import TaskDetail from '@/components/TaskDetail.vue'

const tasksStore = useTasksStore()
const showDialog = ref(false)
const showDetail = ref(false)
const editingTask = ref<Task | null>(null)
const selectedTask = ref<Task | null>(null)
const draggingTask = ref<Task | null>(null)
const dragOverColumn = ref<string | null>(null)

const columns = [
  { key: 'pending', title: '待处理', color: '#909399' },
  { key: 'assigned', title: '已分配', color: '#c0c4cc' },
  { key: 'in_progress', title: '进行中', color: '#e6a23c' },
  { key: 'review', title: '审查中', color: '#409eff' },
  { key: 'done', title: '已完成', color: '#67c23a' }
]

function getTasksByStatus(status: string) {
  return tasksStore.tasks.filter(t => t.status === status)
}

function getPriorityType(priority: string): '' | 'success' | 'warning' | 'info' | 'danger' {
  const map: Record<string, '' | 'success' | 'warning' | 'info' | 'danger'> = {
    low: 'info', medium: '', high: 'warning', critical: 'danger'
  }
  return map[priority] || ''
}

function getPriorityLabel(priority: string): string {
  const map: Record<string, string> = { low: '低', medium: '中', high: '高', critical: '紧急' }
  return map[priority] || priority
}

function getAgentEmoji(assignee: string | null): string {
  if (!assignee) return '👤'
  const map: Record<string, string> = {
    leonardo: '🟦', raphael: '🟥', donatello: '🟪',
    michelangelo: '🟧', wheeljack: '🔧', optimus: '🤖'
  }
  return map[assignee] || '👤'
}

function handleDragStart(task: Task) {
  draggingTask.value = task
}

async function handleDrop(newStatus: string) {
  if (!draggingTask.value) return
  const task = draggingTask.value
  if (task.status === newStatus) return

  dragOverColumn.value = null
  try {
    await tasksStore.updateTaskAction(task.task_id, { status: newStatus })
  } catch {
    // 回滚
  }
  draggingTask.value = null
}

function openCreate() {
  editingTask.value = null
  showDialog.value = true
}

function openEdit(task: Task) {
  editingTask.value = task
  showDialog.value = true
}

function openDetail(task: Task) {
  selectedTask.value = task
  tasksStore.selectedTask = task
  showDetail.value = true
}

onMounted(() => {
  tasksStore.fetchTasks()
})
</script>

<style scoped>
.kanban-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: calc(100vh - 140px);
}

.kanban-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}

.kanban-header h2 {
  margin: 0;
  font-size: 18px;
}

.kanban-board {
  display: flex;
  gap: 12px;
  flex: 1;
  overflow-x: auto;
  padding-bottom: 8px;
}

.kanban-column {
  flex: 0 0 220px;
  display: flex;
  flex-direction: column;
  background: #f0f2f5;
  border-radius: 8px;
  overflow: hidden;
  transition: background 0.15s;
}

.kanban-column.drag-over {
  background: #e8f4ff;
  box-shadow: inset 0 0 0 2px #409eff;
}

.column-header {
  padding: 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #e4e7ed;
}

.column-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.column-count {
  font-size: 12px;
  color: #909399;
  background: #e4e7ed;
  padding: 2px 8px;
  border-radius: 10px;
}

.column-body {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.kanban-card {
  background: #fff;
  border-radius: 6px;
  padding: 10px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
  cursor: grab;
  transition: box-shadow 0.15s;
}

.kanban-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
}

.kanban-card:active {
  cursor: grabbing;
}

.card-top {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}

.card-id {
  font-size: 11px;
  color: #909399;
}

.card-title {
  font-size: 13px;
  color: #303133;
  margin-bottom: 8px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: #909399;
}

.card-assignee {
  display: flex;
  align-items: center;
  gap: 4px;
}

.card-actions {
  display: flex;
  justify-content: flex-end;
  padding-top: 6px;
  border-top: 1px solid #f0f0f0;
  margin-top: 6px;
}

.column-empty {
  text-align: center;
  padding: 20px;
  font-size: 12px;
  color: #c0c4cc;
}
</style>
