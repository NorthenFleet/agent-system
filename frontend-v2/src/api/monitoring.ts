import apiClient from './client'

// ─── Types ────────────────────────────────────────────────────────────────────

export interface MonitoringAgent {
  agent_id: string
  agent_name: string
  status: 'online' | 'busy' | 'idle' | 'timeout' | 'offline'
  cpu_usage: number | null
  memory_usage: number | null
  last_heartbeat: string | null
  heartbeat_age_seconds: number | null
  seconds_ago?: number | null
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

export interface MemoryReleaseDecision {
  decision_id: string
  release_id: string
  candidate_digest: string
  version: string
  status: 'completed' | 'ready' | 'awaiting_approval' | 'blocked' | 'execution_failed'
  technical_ready: boolean
  promotion_ready: boolean
  release_completed: boolean
  execution_required: boolean
  execution_status: string | null
  completed_at: string | null
  risk: MemoryReleaseRisk
  approval: {
    status: 'pending' | 'approved'
    approved_by: string
    approved_at: string | null
    revoked_by: string
    revoked_at: string | null
  }
  blocking_failures: string[]
  checks: Array<{
    name: string
    passed: boolean
    blocking: boolean
    expected: unknown
    actual: unknown
  }>
  rollout_plan: {
    strategy: string
    steps: string[]
    automatic_rollback_on: string[]
  }
}

export interface MemoryReleaseRisk {
  level?: 'low' | 'medium' | 'high' | 'critical'
  label?: string
  approval_mode?: string
  requires_creator_separation?: boolean
  required_validations?: string[]
}

export interface MemoryReleaseHistoryItem {
  release_id: string
  version: string
  change_type: string
  candidate_digest: string
  status: 'completed' | 'rolled_back' | 'rollback_failed' | 'failed' | 'ready' | 'awaiting_approval' | 'blocked' | 'unknown'
  execution_status: string | null
  risk: MemoryReleaseRisk
  approved_by: string
  started_at: string | null
  updated_at: string | null
  completed_at: string | null
  event_count: number
  events: Array<{ stage?: string; status?: string; at?: string; detail?: unknown }>
}

export interface MemorySystemHealth {
  schema_version: string
  status: 'healthy' | 'unhealthy' | 'stale' | 'missing' | 'invalid'
  healthy: boolean
  reported_healthy?: boolean
  checked_at: string | null
  age_seconds: number | null
  stale_after_seconds: number
  case_id?: string
  attempt?: number
  attempts_configured?: number
  summary: {
    status?: string
    authority?: string
    identity_bound?: boolean
    identity_channel?: string
    remembered_items?: number
    retrieval_citations?: number
    degraded_channels?: number
    counts?: Record<string, number>
    channels?: Record<string, string>
    bridge_deployment?: {
      ready?: boolean
      plugin_version?: string | null
      bridge_schema?: string | null
      failed_checks?: string[]
    }
    notification_delivery?: {
      status?: string
      notifications_created?: number
      state?: string
    }
  }
  failures: Array<{
    check?: string
    expected?: unknown
    actual?: unknown
  }>
  matrix?: {
    status: 'healthy' | 'unhealthy' | 'stale' | 'missing' | 'invalid'
    healthy: boolean
    checked_at: string | null
    age_seconds: number | null
    summary: {
      total_cases?: number
      passed_cases?: number
      failed_cases?: string[]
      agents?: string[]
    }
    failures: Array<{ check?: string; expected?: unknown; actual?: unknown }>
  }
  slo?: {
    status: 'healthy' | 'at_risk' | 'breached' | 'insufficient_data'
    window_days: number
    sample_count: number
    monitors: Record<string, {
      status: 'healthy' | 'at_risk' | 'breached' | 'insufficient_data'
      target_percent: number
      sample_count: number
      success_rate_percent: number | null
      error_budget_remaining_percent: number | null
      p95_duration_ms: number | null
      incident_count: number
      open_incident: boolean
      mean_recovery_seconds: number | null
    }>
    excluded_sample_count?: number
    data_quality: {
      valid: boolean
      errors: string[]
      excluded_samples?: number
      exclusion_reasons?: Record<string, number>
    }
  }
  drill?: {
    status: 'healthy' | 'unhealthy' | 'stale' | 'missing' | 'invalid'
    healthy: boolean
    checked_at: string | null
    age_seconds: number | null
    summary: {
      mode?: string
      total_scenarios?: number
      passed_scenarios?: number
      failed_scenarios?: string[]
    }
    failures: Array<{ check?: string; expected?: unknown; actual?: unknown }>
  }
  release?: MemoryReleaseDecision
  release_history?: MemoryReleaseHistoryItem[]
}

// ─── API Functions ────────────────────────────────────────────────────────────

export function getMonitoringLive() {
  return apiClient
    .get<MonitoringAgent[] | { agents: MonitoringAgent[] }>('/api/v2/agents/live')
    .then(r => {
      const agents = Array.isArray(r.data) ? r.data : r.data.agents || []
      return agents.map(agent => ({
        ...agent,
        heartbeat_age_seconds: agent.heartbeat_age_seconds ?? agent.seconds_ago ?? null,
      }))
    })
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

export function getMemorySystemHealth() {
  return apiClient
    .get<MemorySystemHealth>('/api/v2/monitoring/memory-system', {
      suppressErrorToast: true
    })
    .then(r => r.data)
}

export function approveMemoryRelease(expectedDigest: string) {
  return apiClient
    .post<MemoryReleaseDecision>('/api/v2/monitoring/memory-system/release/approve', {
      expected_digest: expectedDigest
    })
    .then(r => r.data)
}

export function revokeMemoryRelease(expectedDigest: string) {
  return apiClient
    .post<MemoryReleaseDecision>('/api/v2/monitoring/memory-system/release/revoke', {
      expected_digest: expectedDigest
    })
    .then(r => r.data)
}

// ─── WebSocket ────────────────────────────────────────────────────────────────

export function createMonitoringWs(token: string): WebSocket {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  return new WebSocket(`${protocol}//${host}/ws/status?token=${encodeURIComponent(token)}`)
}
