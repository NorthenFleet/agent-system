import apiClient from './client'

// ─── Types ────────────────────────────────────────────────────────────────────

export interface MonitoringAgent {
  agent_id: string
  agent_name: string
  status: 'online' | 'busy' | 'idle' | 'offline'
  cpu_usage: number | null
  memory_usage: number | null
  last_heartbeat: string | null
  heartbeat_age_seconds: number | null
  current_task: string | null
  health: 'healthy' | 'warning' | 'critical' | 'offline'
  health_score?: number
}

export interface MonitoringSummary {
  total: number
  online: number
  busy: number
  idle: number
  offline: number
  avg_cpu: number
  avg_memory: number
  healthy_rate: number
}

export interface MonitoringTrendPoint {
  timestamp: string
  cpu: number
  memory: number
  active_agents: number
}

// ─── API Functions ────────────────────────────────────────────────────────────

export function getMonitoringLive() {
  return apiClient.get<MonitoringAgent[]>('/api/v2/agents/live').then(r => r.data)
}

export function getMonitoringSummary() {
  return apiClient.get<MonitoringSummary>('/api/v2/monitoring/summary')
    .then(r => r.data)
    .catch(() => null)
}

export function getMonitoringTrend(hours = 1) {
  return apiClient.get<MonitoringTrendPoint[]>('/api/v2/monitoring/trend', {
    params: { hours }
  })
    .then(r => r.data)
    .catch(() => [])
}

// ─── WebSocket ────────────────────────────────────────────────────────────────

export function createMonitoringWs(token: string): WebSocket {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  return new WebSocket(`${protocol}//${host}/ws/status?token=${encodeURIComponent(token)}`)
}
