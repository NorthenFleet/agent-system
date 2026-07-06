import apiClient from './client'

export interface RecommendRequest {
  task_type: string
  priority: string
  tags: string[]
}

export interface RecommendAgent {
  agent_id: string
  agent_name: string
  score: number
  success_rate: number
  avatar?: string
}

export interface RecommendResponse {
  agents: RecommendAgent[]
}

export interface QTableEntry {
  agent_id: string
  task_type: string
  success_count: number
  total_count: number
  success_rate: number
}

export interface QTableResponse {
  entries: QTableEntry[]
}

export const recommendAgent = (data: RecommendRequest) =>
  apiClient.post<RecommendResponse>('/api/v2/tasks/recommend', data).then(r => r.data)

export const getQTable = () =>
  apiClient.get<QTableResponse>('/api/v2/tasks/q-table').then(r => r.data)
