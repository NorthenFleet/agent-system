import apiClient from './client'
import type { Project } from './projects'

export interface MissionPlanningScenario {
  id: string
  name: string
  description?: string
  type: string
  map_size?: Array<number | null>
}

export interface MissionPlanningStatus {
  state?: string
  running?: boolean
  tick_count?: number
  total_replans?: number
  eval_score?: number
  last_eval_status?: string
  consecutive_urgent?: number
  last_tick?: Record<string, unknown>
  progress?: number
  plan_summary?: { total: number; active: number; done: number; pending: number }
  tasks?: Array<{ id?: string; name?: string; status?: string; assigned_units?: string[] }>
  recent_events?: unknown[]
  last_diagnosis?: unknown
}

export interface MissionPlanningIntegration {
  scenario_id?: string
  scenario_name?: string
  scenario_type?: string
  side?: 'red' | 'blue' | string
  status?: 'bound' | 'running' | 'completed' | 'stopped' | 'error' | string
  run_id?: string
  product_url?: string
  bound_at?: string
  started_at?: string
  completed_at?: string
  stopped_at?: string
  last_synced_at?: string
  last_error?: string
  result_summary?: string
  product_status?: MissionPlanningStatus
  simulation_status?: MissionSimulationStatus
  mission?: MissionProtocol
  current_run_id?: string
  runs?: MissionRun[]
  approval_requests?: MissionPlanningApprovalRequest[]
  automation?: MissionPlanningAutomation
}

export interface MissionProductBinding {
  product?: string
  name?: string
  base_url?: string
  mode?: string
  scenario_id?: string
  side?: string
  bound_at?: string
}

export interface MissionProtocol {
  id?: string
  project_id?: string
  title?: string
  objective?: string
  status?: string
  current_run_id?: string
  bindings?: {
    planning?: MissionProductBinding
    simulation?: MissionProductBinding
  }
}

export interface MissionRunRecord {
  id?: string
  name?: string
  type?: string
  target?: string
  source?: string
  status?: string
  summary?: string
  detail?: string
  title?: string
  created_at?: string
}

export interface MissionRun {
  id: string
  mission_id?: string
  correlation_id?: string
  scenario_id?: string
  side?: string
  status?: string
  created_at?: string
  started_at?: string
  ended_at?: string
  commands?: MissionRunRecord[]
  events?: MissionRunRecord[]
  artifacts?: MissionRunRecord[]
}

export interface MissionSimulationStatus {
  provider?: string
  mode?: string
  scenario_name?: string
  frame?: number
  turn?: number
  phase?: string
  unit_count?: number
  destroyed_count?: number
}

export interface MissionPlanningAutomation {
  enabled: boolean
  health?: 'waiting' | 'healthy' | 'attention' | 'error' | 'disabled' | string
  last_checked_at?: string
  last_suggestion_at?: string
  last_error?: string
  last_skip_reason?: string
  monitor_state?: {
    stagnant_checks?: number
    last_tick_count?: number
    last_done?: number
    last_total_replans?: number
    last_eval_status?: string
  }
}

export interface MissionPlanningTool {
  id: 'inspect_status' | 'bind_scenario' | 'start_run' | 'stop_run' | 'replan' | string
  name: string
  description: string
  approval_required: boolean
}

export interface MissionPlanningApprovalRequest {
  id: string
  project_id: string
  agent_id: string
  tool_name: string
  tool_label: string
  payload?: Record<string, unknown>
  reason?: string
  approval_required: boolean
  status: 'queued' | 'pending' | 'approved' | 'executing' | 'executed' | 'rejected' | 'failed' | string
  requested_by?: string
  requested_at: string
  reviewer?: string
  reviewed_at?: string
  review_comment?: string
  executed_at?: string
  failed_at?: string
  error?: string
  result?: Record<string, unknown>
  source?: 'manual' | 'automation' | string
  severity?: 'critical' | 'high' | 'medium' | string
  rule_id?: string
  trigger_key?: string
  evidence?: Record<string, unknown>
}

export function getMissionPlanningHealth() {
  return apiClient.get<{
    online: boolean
    base_url: string
    product: string
    supervisor_state?: string
    running?: boolean
    error?: string
  }>('/api/v3/mission-planning/health').then(r => r.data)
}

export function getMissionPlanningScenarios() {
  return apiClient.get<{ scenarios: MissionPlanningScenario[]; total: number }>(
    '/api/v3/mission-planning/scenarios'
  ).then(r => r.data)
}

export function getProjectMissionPlanning(projectId: string) {
  return apiClient.get<{ project_id: string; integration: MissionPlanningIntegration; product_url: string }>(
    `/api/v3/mission-planning/projects/${encodeURIComponent(projectId)}`
  ).then(r => r.data)
}

export function bindProjectMissionPlanning(projectId: string, payload: { scenario_id: string; side: string }) {
  return apiClient.put<{ project: Project; integration: MissionPlanningIntegration }>(
    `/api/v3/mission-planning/projects/${encodeURIComponent(projectId)}/binding`,
    payload
  ).then(r => r.data)
}

export function startProjectMissionPlanning(projectId: string) {
  return apiClient.post<{ project: Project; integration: MissionPlanningIntegration }>(
    `/api/v3/mission-planning/projects/${encodeURIComponent(projectId)}/start`
  ).then(r => r.data)
}

export function refreshProjectMissionPlanning(projectId: string) {
  return apiClient.get<{ project: Project; integration: MissionPlanningIntegration; status: MissionPlanningStatus }>(
    `/api/v3/mission-planning/projects/${encodeURIComponent(projectId)}/status`
  ).then(r => r.data)
}

export function stopProjectMissionPlanning(projectId: string) {
  return apiClient.post<{ project: Project; integration: MissionPlanningIntegration }>(
    `/api/v3/mission-planning/projects/${encodeURIComponent(projectId)}/stop`
  ).then(r => r.data)
}

export function getMissionPlanningTools() {
  return apiClient.get<{ tools: MissionPlanningTool[]; total: number }>(
    '/api/v3/mission-planning/tools'
  ).then(r => r.data)
}

export function getMissionPlanningApprovals(projectId: string) {
  return apiClient.get<{
    project_id: string
    requests: MissionPlanningApprovalRequest[]
    pending_count: number
  }>(`/api/v3/mission-planning/projects/${encodeURIComponent(projectId)}/approvals`).then(r => r.data)
}

export function invokeMissionPlanningAgentTool(
  projectId: string,
  payload: { agent_id: string; tool_name: string; reason?: string; payload?: Record<string, unknown> }
) {
  return apiClient.post<{
    request: MissionPlanningApprovalRequest
    dispatch_status: string
    execution?: {
      project?: Project
      integration?: MissionPlanningIntegration
      status?: MissionPlanningStatus
    }
  }>(`/api/v3/mission-planning/projects/${encodeURIComponent(projectId)}/agent-tools/invoke`, payload).then(r => r.data)
}

export function decideMissionPlanningApproval(
  projectId: string,
  requestId: string,
  payload: { approved: boolean; comment?: string }
) {
  return apiClient.post<{
    request: MissionPlanningApprovalRequest
    dispatch_status: string
    execution?: {
      project?: Project
      integration?: MissionPlanningIntegration
      status?: MissionPlanningStatus
    }
  }>(
    `/api/v3/mission-planning/projects/${encodeURIComponent(projectId)}/approvals/${encodeURIComponent(requestId)}/decision`,
    payload
  ).then(r => r.data)
}

export function getMissionPlanningAutomationStatus() {
  return apiClient.get<{
    enabled: boolean
    running: boolean
    task_active: boolean
    interval_seconds: number
    last_tick_at?: string
    last_error?: string
    projects_checked?: number
    suggestions_created?: number
  }>('/api/v3/mission-planning/automation/status').then(r => r.data)
}

export function updateMissionPlanningAutomation(projectId: string, enabled: boolean) {
  return apiClient.put<{
    project: Project
    integration: MissionPlanningIntegration
    automation: MissionPlanningAutomation
  }>(`/api/v3/mission-planning/projects/${encodeURIComponent(projectId)}/automation`, { enabled }).then(r => r.data)
}

export function evaluateMissionPlanningAutomation(projectId: string) {
  return apiClient.post<{
    project_id: string
    status: string
    snapshot?: MissionPlanningStatus
    suggestions: MissionPlanningApprovalRequest[]
    automation?: MissionPlanningAutomation
  }>(`/api/v3/mission-planning/projects/${encodeURIComponent(projectId)}/automation/evaluate`).then(r => r.data)
}
