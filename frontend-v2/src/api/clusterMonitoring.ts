import apiClient from './client'

export type CollectionState = 'fresh' | 'stale' | 'missing' | 'error'
export type NetworkState = 'online' | 'offline' | 'unknown'
export type IdentityStatus = 'confirmed' | 'unconfirmed'
export type ServiceState = 'healthy' | 'unhealthy' | 'unknown'

export interface ClusterGpuMetrics {
  name: string | null
  memory_total_bytes: number | null
  memory_used_bytes: number | null
  utilization_percent: number | null
}

export interface ClusterMetrics {
  cpu_percent?: number | null
  cpu_logical_count?: number | null
  memory_total_bytes?: number | null
  memory_available_bytes?: number | null
  memory_percent?: number | null
  disk_total_bytes?: number | null
  disk_free_bytes?: number | null
  gpus?: ClusterGpuMetrics[] | null
  os_version?: string | null
  architecture?: string | null
  hardware_model?: string | null
  hostname?: string | null
  memory_unused_bytes?: number | null
  gpu_probe_state?: 'available' | 'unavailable' | 'error' | string | null
  docker_state?: 'ready' | 'unknown' | 'unavailable' | 'error' | string | null
  docker_version?: string | null
}

export interface ClusterServiceStatus {
  name: string
  state: ServiceState
  observed_at: string | null
  detail?: string | null
}

export interface ClusterNode {
  node_id: string
  tailscale_id: string
  hostname: string
  dns_name: string | null
  addresses: string[]
  os: string | null
  role: string | null
  managed: boolean
  identity_status: IdentityStatus
  legacy_device_id: string | number | null
  domain_refs: Record<string, unknown>
  maintenance: boolean
  network: {
    state: NetworkState
    observed_at: string | null
    expired: boolean
  }
  telemetry: {
    state: CollectionState
    observed_at: string | null
    source: string | null
    error: string | null
    metrics: ClusterMetrics
  }
  services: ClusterServiceStatus[]
  scheduling: {
    eligible: false
    reason: string
  }
}

export interface ClusterMonitoringSnapshot {
  schema_version: 'cluster-monitoring.v1'
  generated_at: string
  mode: 'read_only'
  discovery: {
    state: CollectionState
    observed_at: string | null
    error: string | null
  }
  nodes: ClusterNode[]
  execution?: ClusterExecutionPreparation
}

export interface ClusterExecutionPreparation {
  schema_version: 'cluster-execution-preparation.v1'
  mode: 'preparation_only'
  enabled: false
  ledger: 'work_runs' | string
  approval_authority: 'command_center' | string
  operations: Array<{
    operation: string
    read_only: boolean
    supported_os: string[]
    max_timeout_seconds: number
  }>
  blockers: string[]
  nodes: Array<{
    node_id: string
    ready: false
    blockers: string[]
  }>
}

export function getClusterMonitoring(signal?: AbortSignal) {
  return apiClient
    .get<ClusterMonitoringSnapshot>('/api/v2/monitoring/cluster', {
      suppressErrorToast: true,
      signal
    })
    .then(response => response.data)
}
