<template>
  <div class="tasks-page">
    <div class="tasks-header">
      <h2>任务管理</h2>
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
        <el-button type="primary" @click="openCreate">
          <el-icon><Plus /></el-icon> 新建任务
        </el-button>
      </div>
    </div>

    <el-table
      :data="tasksStore.tasks"
      v-loading="tasksStore.loading"
      stripe
      style="width: 100%"
      @row-click="handleRowClick"
      highlight-current-row
    >
      <el-table-column prop="task_id" label="ID" width="110" />
      <el-table-column prop="title" label="任务标题" min-width="220" show-overflow-tooltip />
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="getStatusType(row.status)" size="small">
            {{ getStatusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="priority" label="优先级" width="80">
        <template #default="{ row }">
          <el-tag :type="getPriorityType(row.priority)" size="small">
            {{ getPriorityLabel(row.priority) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="assignee" label="负责人" width="100">
        <template #default="{ row }">
          {{ row.assignee || '—' }}
        </template>
      </el-table-column>
      <el-table-column prop="progress" label="进度" width="120">
        <template #default="{ row }">
          <el-progress :percentage="row.progress" :stroke-width="8" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120" fixed="right">
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

    <el-empty v-if="!tasksStore.tasks.length && !tasksStore.loading" description="暂无任务数据（API 待对接）" />

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

onMounted(() => {
  tasksStore.fetchTasks()
})

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
</script>

<style scoped>
.tasks-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.tasks-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}

.tasks-header h2 {
  margin: 0;
  font-size: 18px;
}

.tasks-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  padding-top: 12px;
}
</style>
