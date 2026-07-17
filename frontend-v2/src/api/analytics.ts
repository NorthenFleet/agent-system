import apiClient from './client'

// ─── Types ────────────────────────────────────────────────────────────────────

export interface TaskTrendPoint {
  date: string
  created: number
  completed: number
  blocked: number
}

export interface AgentProductivity {
  agent_id: string
  agent_name: string
  completed_count: number
  total_count: number
  completion_rate: number
  avg_duration_hours: number
}

export interface SprintBurndownPoint {
  date: string
  ideal_remaining: number
  actual_remaining: number
}

export interface TeamEfficiency {
  completion_rate: number
  avg_cycle_days: number
  estimated_vs_actual_ratio: number
  dimensions: {
    completion_rate: number
    velocity: number
    quality: number
    estimation_accuracy: number
    responsiveness: number
  }
}

// ─── API Functions ────────────────────────────────────────────────────────────

export function getTaskTrend(granularity = 'daily', days = 30) {
  return apiClient
    .get<TaskTrendPoint[]>('/api/v2/analytics/task-trend', { params: { granularity, days } })
    .then(r => r.data)
}

export function getAgentProductivity() {
  return apiClient
    .get<AgentProductivity[]>('/api/v2/analytics/agent-productivity')
    .then(r => r.data)
}

export function getSprintBurndown(sprintId: string | null = null) {
  return apiClient
    .get<SprintBurndownPoint[]>('/api/v2/analytics/sprint-burndown', { params: { sprint_id: sprintId } })
    .then(r => r.data)
}

export function getTeamEfficiency(days = 30) {
  return apiClient
    .get<TeamEfficiency>('/api/v2/analytics/team-efficiency', { params: { days } })
    .then(r => r.data)
}
