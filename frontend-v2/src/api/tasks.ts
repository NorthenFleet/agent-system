import apiClient from './client'
import type {
  Task, TaskListResponse, TaskCreate, TaskUpdate,
  Comment, CommentResponse, TaskStats
} from '@/stores/tasks'

// Helper: unwrap response for create/update (backend returns {success: true, task: ...})
function unwrapTask(response: { success?: boolean; task?: Task }) {
  return response.task || (response as unknown as Task)
}

// 任务列表
export function getTasks(params?: {
  status?: string
  priority?: string
  assignee?: string
  search?: string
  page?: number
  page_size?: number
  sort_by?: string
  sort_order?: string
}) {
  return apiClient.get<TaskListResponse>('/api/v2/tasks', { params }).then(r => r.data)
}

// 任务详情
export function getTask(taskId: string) {
  return apiClient.get<Task>(`/api/v2/tasks/${taskId}`).then(r => r.data)
}

// 创建任务 (后端返回 {success: true, task: {...}})
export function createTask(data: TaskCreate) {
  return apiClient.post('/api/v2/tasks', data).then(r => unwrapTask(r.data))
}

// 更新任务 (后端返回 {success: true, task: {...}})
export function updateTask(taskId: string, data: TaskUpdate) {
  return apiClient.put(`/api/v2/tasks/${taskId}`, data).then(r => unwrapTask(r.data))
}

// 删除任务
export function deleteTask(taskId: string) {
  return apiClient.delete(`/api/v2/tasks/${taskId}`).then(r => r.data)
}

// 添加评论 (后端端点: /comments 复数)
export function addComment(taskId: string, content: string) {
  return apiClient.post<Comment>(`/api/v2/tasks/${taskId}/comments`, { content }).then(r => r.data)
}

// 获取评论
export function getComments(taskId: string) {
  return apiClient.get<CommentResponse>(`/api/v2/tasks/${taskId}/comments`).then(r => r.data)
}

// 任务统计
export function getTaskStats() {
  return apiClient.get<TaskStats>('/api/v2/tasks/stats').then(r => r.data)
}
