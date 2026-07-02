import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getTasks, getTask, createTask, updateTask, deleteTask, addComment, getComments } from '@/api/tasks'

export interface Task {
  id: number
  task_id: string
  title: string
  description: string
  type: string
  status: string
  priority: string
  assignee: string | null
  progress: number
  source: string
  sprint: number | null
  tags: string[]
  parent_task_id: string | null
  created_at: string
  updated_at: string
  completed_at: string | null
  due_date: string | null
  start_date: string | null
  comment_count?: number
}

export interface TaskCreate {
  title: string
  description?: string
  type?: string
  priority?: string
  assignee?: string
  sprint?: number
  tags?: string[]
  due_date?: string
  start_date?: string
  parent_task_id?: string | null
}

export interface TaskUpdate {
  title?: string
  description?: string
  type?: string
  status?: string
  priority?: string
  assignee?: string
  progress?: number
  sprint?: number
  tags?: string[]
  due_date?: string
  start_date?: string
}

export interface TaskListResponse {
  tasks: Task[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface Comment {
  id: number
  task_id: string
  user?: {
    id: number
    username: string
    display_name: string
  }
  content: string
  created_at: string
  updated_at: string
}

export interface CommentResponse {
  comments: Comment[]
  total: number
}

export interface TaskStats {
  total: number
  by_status: Record<string, number>
  by_priority: Record<string, number>
  by_assignee: Record<string, number>
  completion_rate: number
}

export const useTasksStore = defineStore('tasks', () => {
  const tasks = ref<Task[]>([])
  const total = ref(0)
  const totalPages = ref(0)
  const loading = ref(false)
  const selectedTask = ref<Task | null>(null)
  const comments = ref<Comment[]>([])
  const filters = ref({
    status: '',
    priority: '',
    assignee: '',
    search: ''
  })
  const pagination = ref({
    page: 1,
    pageSize: 20
  })

  async function fetchTasks() {
    loading.value = true
    try {
      const res = await getTasks({
        status: filters.value.status || undefined,
        priority: filters.value.priority || undefined,
        assignee: filters.value.assignee || undefined,
        search: filters.value.search || undefined,
        page: pagination.value.page,
        page_size: pagination.value.pageSize
      })
      tasks.value = res.tasks
      total.value = res.total
      totalPages.value = res.total_pages
    } catch {
      tasks.value = []
      total.value = 0
      totalPages.value = 0
    } finally {
      loading.value = false
    }
  }

  async function fetchTask(taskId: string) {
    loading.value = true
    try {
      const task = await getTask(taskId)
      selectedTask.value = task
      // 同时拉取评论
      const commentRes = await getComments(taskId)
      comments.value = commentRes.comments
    } catch {
      selectedTask.value = null
      comments.value = []
    } finally {
      loading.value = false
    }
  }

  async function createTaskAction(data: TaskCreate) {
    loading.value = true
    try {
      await createTask(data)
      await fetchTasks()
    } finally {
      loading.value = false
    }
  }

  async function updateTaskAction(taskId: string, data: TaskUpdate) {
    loading.value = true
    try {
      await updateTask(taskId, data)
      await fetchTasks()
      // 如果当前正在查看该任务，也刷新详情
      if (selectedTask.value?.task_id === taskId) {
        await fetchTask(taskId)
      }
    } finally {
      loading.value = false
    }
  }

  async function deleteTaskAction(taskId: string) {
    loading.value = true
    try {
      await deleteTask(taskId)
      await fetchTasks()
      if (selectedTask.value?.task_id === taskId) {
        selectedTask.value = null
        comments.value = []
      }
    } finally {
      loading.value = false
    }
  }

  async function addCommentAction(taskId: string, content: string) {
    try {
      await addComment(taskId, content)
      const res = await getComments(taskId)
      comments.value = res.comments
    } catch {
      // 忽略
    }
  }

  function applyFilter(newFilters: Partial<typeof filters.value>) {
    filters.value = { ...filters.value, ...newFilters }
    pagination.value.page = 1
    fetchTasks()
  }

  function clearFilters() {
    filters.value = { status: '', priority: '', assignee: '', search: '' }
    pagination.value.page = 1
    fetchTasks()
  }

  return {
    tasks,
    total,
    totalPages,
    loading,
    selectedTask,
    comments,
    filters,
    pagination,
    fetchTasks,
    fetchTask,
    createTaskAction,
    updateTaskAction,
    deleteTaskAction,
    addCommentAction,
    applyFilter,
    clearFilters
  }
})
