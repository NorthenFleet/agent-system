import apiClient from './client'
import type { AgentListResponse, AgentHistoryResponse } from '@/stores/agents'

export interface AgentTaskResponse {
  agent_id: string
  tasks: unknown[]
  total: number
}

// Agent 实时状态
export function getAgentsLive() {
  return apiClient.get<AgentListResponse>('/api/v2/agents/live').then(r => r.data)
}

// Agent 心跳上报
export function sendHeartbeat(agentId: string, data: {
  agent_name?: string
  status: string
  current_task?: string
  cpu_usage?: number
  memory_usage?: number
  task_queue_len?: number
  metadata?: Record<string, unknown>
}) {
  const agentName =
    data.agent_name ||
    (typeof data.metadata?.agent_name === 'string' ? data.metadata.agent_name : undefined) ||
    (typeof data.metadata?.name === 'string' ? data.metadata.name : undefined) ||
    agentId

  return apiClient.post(`/api/v2/agents/${agentId}/heartbeat`, {
    ...data,
    agent_id: agentId,
    agent_name: agentName
  }).then(r => r.data)
}

// Agent 状态历史
export function getAgentHistory(agentId: string, params?: { limit?: number; hours?: number }) {
  return apiClient.get<AgentHistoryResponse>(`/api/v2/agents/${agentId}/history`, { params }).then(r => r.data)
}

// Agent 关联任务
export function getAgentTasks(agentId: string) {
  return apiClient.get<AgentTaskResponse>(`/api/v2/agents/${agentId}/tasks`).then(r => r.data)
}

// WebSocket 连接
export function createWsAgent(token: string): WebSocket {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  const ws = new WebSocket(`${protocol}//${host}/ws/status?token=${encodeURIComponent(token)}`)
  return ws
}
