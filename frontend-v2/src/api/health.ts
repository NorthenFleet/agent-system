import apiClient from './client'

export interface AgentHealthScore {
  agent_id: string
  agent_name: string
  score: number
  trend: 'up' | 'down' | 'flat'
  prev_score: number
  dimensions: {
    online_status: number
    task_success_rate: number
    response_latency: number
    task_backlog: number
    confidence_trend: number
  }
}

export interface HealthTrendPoint {
  timestamp: string
  score: number
}

export interface HealthTrendResponse {
  agent_id: string
  trend: HealthTrendPoint[]
}

export const getAgentHealth = () =>
  apiClient.get<AgentHealthScore[]>('/api/v2/agents/health').then(r => r.data)

export const getAgentHealthById = (agentId: string) =>
  apiClient.get<AgentHealthScore>(`/api/v2/agents/${agentId}/health`).then(r => r.data)

export const getHealthTrend = (agentId: string, hours = 24) =>
  apiClient.get<HealthTrendResponse>(`/api/v2/agents/${agentId}/health/trend`, { params: { hours } }).then(r => r.data)
