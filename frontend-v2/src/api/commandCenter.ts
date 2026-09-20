import apiClient from './client'

export interface ContextCitation {
  rank: number
  source_id?: string
  source_ref: string
  title: string
}

export interface CommandCenterContextBinding {
  id: string
  mission_id: string
  plan_version: number
  step_id: string
  purpose: 'planning' | 'execution' | string
  agent_id: string
  context_pack_id?: string
  context_pack_version: number
  status: string
  summary?: string
  item_count: number
  citation_count: number
  source_types: string[]
  citations: ContextCitation[]
  error?: string
  created_at: string
  updated_at: string
}

export interface CommandCenterToolRequirement {
  id: string
  name: string
  category: string
  status: string
  description?: string
  evidence_types?: string[]
}

export interface CommandCenterExecutionQuality {
  status: 'pass' | 'warning' | 'blocked' | string
  score: number
  blockers: string[]
  warnings: string[]
  evidence_refs: string[]
  required_evidence: string[]
  required_tools: string[]
  checked_rules: string[]
}

export interface CommandCenterStepApproval {
  id: string
  mission_id: string
  plan_version: number
  step_id: string
  request_version: number
  risk_class: string
  action_summary: string
  contract_hash: string
  status: 'pending' | 'approved' | 'rejected' | 'expired' | 'cancelled' | 'consumed' | string
  requested_at: string
  expires_at: string
  decided_at?: string
  decided_by?: string
  comment?: string
  consumed_at?: string
  consumed: boolean
  single_use: boolean
}

export interface CommandCenterEffect {
  id: string
  step_id: string
  effect_key: string
  resource: string
  action: string
  status: 'applied' | 'not_applied' | 'unknown' | 'reverted' | string
  idempotency_key: string
  receipt_ref?: string
  evidence_refs: string[]
}

export interface CommandCenterCompensation {
  id: string
  mission_id: string
  plan_version: number
  step_id: string
  effect_id: string
  compensation_type: string
  instructions: string
  resource: string
  contract_hash: string
  idempotency_key: string
  status: 'pending_approval' | 'ready' | 'running' | 'completed' | 'failed' | 'rejected' | 'cancelled' | string
  attempts: number
  approved_by?: string
  approval_comment?: string
  authorization_expires_at?: string
  result?: Record<string, unknown>
  last_error?: string
}

export interface CommandCenterArtifact {
  id: string
  step_id: string
  artifact_type: string
  title: string
  uri: string
  content_hash?: string
  created_at: string
}

export interface CommandCenterEvidence {
  id: string
  step_id: string
  artifact_id?: string
  evidence_type: string
  source_ref: string
  summary: string
  collected_by: string
  collected_at: string
  confidence: number
}

export interface CommandCenterAcceptanceGate {
  id: string
  step_id: string
  gate_type: string
  mode: string
  enforced: boolean
  status: string
  accepted: boolean
  score: number
  blockers: string[]
  warnings: string[]
  details?: Record<string, unknown>
  evaluated_by: string
  evaluated_at: string
}

export interface CommandCenterMissionRun {
  id: string
  mission_id: string
  correlation_id: string
  status: string
  active_plan_version: number
  workflow_run_id?: string
  outcome?: string
  created_at: string
  updated_at: string
  ended_at?: string
}

export interface CommandCenterStep {
  id: string
  mission_id: string
  order_index: number
  phase?: string
  title: string
  description?: string
  task_type: string
  agent_id: string
  executor: string
  status: string
  dependencies: string[]
  required_tools?: string[]
  tool_requirements?: CommandCenterToolRequirement[]
  deliverables?: string[]
  acceptance_criteria?: string[]
  evidence_required?: string[]
  risk_level?: string
  risk_class?: string
  approval_required?: boolean
  side_effect?: boolean
  resources?: string[]
  idempotency_key?: string
  rollback_plan?: string
  capability_match?: boolean
  result?: {
    success?: boolean
    output?: string
    error?: string
    duration_ms?: number
    execution_quality?: CommandCenterExecutionQuality
    context?: {
      binding_id?: string
      context_pack_id?: string
      context_pack_version?: number
      status?: string
      citation_count?: number
      citations?: ContextCitation[]
    }
  }
  context_binding?: CommandCenterContextBinding
  artifacts?: CommandCenterArtifact[]
  evidence?: CommandCenterEvidence[]
  acceptance_gate?: CommandCenterAcceptanceGate
  step_approval?: CommandCenterStepApproval
  effects?: CommandCenterEffect[]
  compensations?: CommandCenterCompensation[]
  work_run_id?: string
  started_at?: string
  completed_at?: string
}

export interface CommandCenterEvent {
  id: string
  event_type: string
  from_status?: string
  to_status?: string
  actor?: string
  detail?: string
  run_sequence?: number
  created_at: string
}

export interface CommandCenterPlanQuality {
  status: 'pass' | 'warning' | 'blocked' | string
  score: number
  blockers: string[]
  warnings: string[]
  suggestions: string[]
  checked_rules: string[]
  tool_summary?: {
    total: number
    unknown: number
    unavailable: number
  }
}

export interface CommandCenterCapabilityAgent {
  id: string
  name: string
  role: string
  task_types: string[]
}

export interface CommandCenterCapabilityCatalog {
  agents: CommandCenterCapabilityAgent[]
  tools: CommandCenterToolRequirement[]
  task_agent_defaults: Record<string, string>
  task_type_defaults: Record<string, {
    required_tools: string[]
    deliverables: string[]
    acceptance_criteria: string[]
    evidence_required: string[]
  }>
}

export interface CommandCenterMission {
  id: string
  title: string
  objective: string
  status: string
  priority: string
  project_id?: string
  mission_type?: 'software' | 'document' | string
  requested_by?: string
  plan_version: number
  approval_status: string
  last_error?: string
  context?: {
    source?: string
    profile_user_id?: string
    user_context?: Record<string, unknown>
  }
  created_at: string
  updated_at: string
  completed_at?: string
  mission_run?: CommandCenterMissionRun
  plan?: {
    summary?: string
    rationale?: string
    risk_level?: string
    status?: string
    plan_quality?: CommandCenterPlanQuality
    raw_plan?: Record<string, unknown>
  }
  approval?: {
    decision?: string
    decided_by?: string
    comment?: string
    requested_at?: string
    decided_at?: string
  }
  steps: CommandCenterStep[]
  artifacts?: CommandCenterArtifact[]
  evidence?: CommandCenterEvidence[]
  acceptance_gates?: CommandCenterAcceptanceGate[]
  delivery_gate?: CommandCenterAcceptanceGate
  step_approvals?: CommandCenterStepApproval[]
  effects?: CommandCenterEffect[]
  compensations?: CommandCenterCompensation[]
  context_bindings?: CommandCenterContextBinding[]
  planning_context?: CommandCenterContextBinding
  events?: CommandCenterEvent[]
  messages?: Array<{
    id: string
    direction: string
    sender_id?: string
    content: string
    created_at: string
  }>
}

export interface CommandCenterLinkedTask {
  task_id: string
  title: string
  description?: string
  type?: string
  status: string
  priority?: string
  assignee?: string
  assignee_name?: string
  progress?: number
  source: string
  parent_task_id?: string | null
  project_id?: string
  project_name?: string
  mission_id?: string
  mission_type?: string
  work_item_type?: string
  updated_at?: string
}

export interface CommandCenterWorkbenchItem {
  mission_id: string
  mission_title: string
  mission_status: string
  mission_type: 'software' | 'document' | string
  project_id?: string
  project_name?: string
  objective: string
  approval_status: string
  current_agent_id: string
  current_agent_name: string
  active_step?: CommandCenterStep
  steps_summary: {
    total: number
    completed: number
    running: number
    failed: number
    pending: number
  }
  linked_tasks: CommandCenterLinkedTask[]
  progress: number
  updated_at?: string
  waiting_reason?: string
}

export interface CommandCenterSummary {
  total: number
  active: number
  pending_approvals: number
  pending_step_approvals: number
  pending_compensations: number
  outbox_pending: number
  context_ready: number
  context_degraded: number
  context_by_status: Record<string, number>
  discussion_count: number
  clarification_pending: number
  routed_by_intent: Record<string, number>
  memory_candidates: {
    total: number
    pending_review: number
    published: number
    rejected: number
    by_status: Record<string, number>
  }
  by_status: Record<string, number>
}

export interface CommandCenterProductionHealth {
  status: 'ready' | 'degraded' | string
  storage: {
    backend: string
    source_of_truth: string
    capabilities: Record<string, boolean>
  }
  storage_runtime: {
    backend: string
    connection_mode: string
    pre_ping?: boolean
    pool?: {
      min_size: number
      max_size: number
      in_use: number
      peak_in_use: number
      acquire_timeouts_total: number
      connection_failures_total: number
      stale_connections_discarded_total?: number
      reconnects_total?: number
      acquire_wait_ms_average: number
      acquire_wait_ms_max: number
    }
  }
  work_runs: {
    backend: string
    total: number
    active: number
    expired_active_leases: number
    retry_attempts: number
    failed: number
    lease_reclaims: number
  }
  workflow_runtime: {
    checkpoint_storage: {
      status: string
      backend: string
      installed_version?: number
      required_version?: number
      missing_tables?: string[]
      runtime_ddl?: boolean
    }
  }
  workers: {
    status: string
    required: number
    live: number
    stale: number
    stale_after_seconds: number
    workers: Array<{
      id: string
      role: string
      state: string
      started_at: string
      last_seen_at: string
      stopped_at?: string
      live: boolean
      metadata: Record<string, unknown>
    }>
  }
}

export interface CommandCenterSpaceNode {
  id: string
  agent_id: string
  name: string
  role?: string
  emoji?: string
  node_type: string
  parent_id?: string
  lane: string
  x: number
  y: number
  status: string
  progress: number
  current_task?: string
  active_mission_count: number
  is_commander: boolean
  can_direct_command: boolean
}

export interface CommandCenterSpaceEdge {
  id: string
  from: string
  to: string
  type: string
  label: string
  step_id?: string
  active: boolean
}

export interface CommandCenterAgentSpace {
  commander: string
  single_entry: boolean
  mission: {
    id?: string
    title?: string
    status?: string
    progress: number
    active_step?: CommandCenterStep
  }
  nodes: CommandCenterSpaceNode[]
  edges: CommandCenterSpaceEdge[]
  lanes: Array<{ id: string; label: string }>
  updated_at: string
}

export interface CommandCenterRoutedMessage {
  id: string
  conversation_id: string
  mission_id?: string
  direction: 'inbound' | 'outbound' | string
  sender_id?: string
  content: string
  intent_type:
    | 'discussion'
    | 'software_project'
    | 'document_project'
    | 'mission_control'
    | 'clarification_required'
    | string
  intent_confidence: number
  intent_reason: string
  execution_requested: number | boolean
  routing_status: string
  resolved_project_id?: string
  created_at: string
  response?: CommandCenterRoutedMessage
}

export interface CommandCenterMemoryCandidate {
  id: string
  user_id: string
  profile_id?: string
  mission_id: string
  plan_version: number
  project_id?: string
  step_id?: string
  agent_id?: string
  target_scope: 'profile' | 'project' | 'agent' | string
  memory_type: string
  memory_key: string
  title: string
  content: string
  rationale?: string
  importance: 'critical' | 'high' | 'normal' | 'low' | string
  confidence: number
  evidence_refs: string[]
  source_ref: string
  source_snapshot?: Record<string, unknown>
  status: 'pending_review' | 'published' | 'rejected' | string
  proposed_by: string
  reviewed_by?: string
  review_comment?: string
  reviewed_at?: string
  published_ref?: string
  published_at?: string
  created_at: string
  updated_at: string
}

export interface CommandCenterMemoryCandidatesResponse {
  candidates: CommandCenterMemoryCandidate[]
  total: number
  summary: CommandCenterSummary['memory_candidates']
  can_review: boolean
}

export interface MemoryCandidateReviewPayload {
  comment?: string
  title?: string
  content?: string
  memory_key?: string
  importance?: string
}

export function getCommandCenterSummary() {
  return apiClient
    .get<CommandCenterSummary>('/api/v3/command-center/summary')
    .then(response => response.data)
}

export function getCommandCenterProductionHealth() {
  return apiClient
    .get<CommandCenterProductionHealth>('/api/v3/command-center/production-health')
    .then(response => response.data)
}

export function listCommandCenterTaskWorkbench(params: {
  status?: string
  mission_type?: string
  project_id?: string
  agent_id?: string
  source?: string
  search?: string
  limit?: number
  offset?: number
} = {}) {
  return apiClient
    .get<{ items: CommandCenterWorkbenchItem[]; total: number }>(
      '/api/v3/command-center/task-workbench',
      { params }
    )
    .then(response => response.data)
}

export function getCommandCenterAgentSpace(params: { mission_id?: string } = {}) {
  return apiClient
    .get<CommandCenterAgentSpace>('/api/v3/command-center/space', { params })
    .then(response => response.data)
}

export function listCommandCenterMissions(params: { status?: string; limit?: number } = {}) {
  return apiClient
    .get<{ missions: CommandCenterMission[]; total: number }>(
      '/api/v3/command-center/missions',
      { params }
    )
    .then(response => response.data)
}

export function getCommandCenterMission(missionId: string) {
  return apiClient
    .get<CommandCenterMission>(`/api/v3/command-center/missions/${missionId}`)
    .then(response => response.data)
}

export function createCommandCenterMission(payload: {
  title?: string
  objective: string
  project_id: string
  mission_type: 'software' | 'document'
  context?: Record<string, unknown>
}) {
  return apiClient
    .post<{ success: boolean; mission: CommandCenterMission }>(
      '/api/v3/command-center/missions',
      payload
    )
    .then(response => response.data)
}

export function listCommandCenterMessages(
  params: { intent_type?: string; limit?: number } = {}
) {
  return apiClient
    .get<{ messages: CommandCenterRoutedMessage[]; total: number }>(
      '/api/v3/command-center/messages',
      { params }
    )
    .then(response => response.data)
}

export function getCommandCenterCapabilities() {
  return apiClient
    .get<CommandCenterCapabilityCatalog>('/api/v3/command-center/capabilities')
    .then(response => response.data)
}

export function routeCommandCenterMessage(payload: {
  content: string
  intent_type?: string
  intent_confidence?: number
  intent_reason?: string
  execution_requested?: boolean
  project_id?: string
}) {
  return apiClient
    .post('/api/v3/command-center/messages', payload)
    .then(response => response.data)
}

export function approveCommandCenterMission(missionId: string, comment = '') {
  return apiClient
    .post<CommandCenterMission>(
      `/api/v3/command-center/missions/${missionId}/approve`,
      { comment }
    )
    .then(response => response.data)
}

export function rejectCommandCenterMission(missionId: string, comment = '') {
  return apiClient
    .post<CommandCenterMission>(
      `/api/v3/command-center/missions/${missionId}/reject`,
      { comment }
    )
    .then(response => response.data)
}

export function approveCommandCenterStep(
  missionId: string,
  stepId: string,
  approval: Pick<CommandCenterStepApproval, 'id' | 'contract_hash'>,
  comment = ''
) {
  return apiClient
    .post<{ success: boolean; approval: CommandCenterStepApproval; mission: CommandCenterMission }>(
      `/api/v3/command-center/missions/${missionId}/steps/${stepId}/approve`,
      { approval_id: approval.id, contract_hash: approval.contract_hash, comment }
    )
    .then(response => response.data)
}

export function rejectCommandCenterStep(
  missionId: string,
  stepId: string,
  approval: Pick<CommandCenterStepApproval, 'id' | 'contract_hash'>,
  comment: string
) {
  return apiClient
    .post<{ success: boolean; approval: CommandCenterStepApproval; mission: CommandCenterMission }>(
      `/api/v3/command-center/missions/${missionId}/steps/${stepId}/reject`,
      { approval_id: approval.id, contract_hash: approval.contract_hash, comment }
    )
    .then(response => response.data)
}

export function approveCommandCenterCompensation(
  missionId: string,
  compensation: Pick<CommandCenterCompensation, 'id' | 'contract_hash'>,
  comment = ''
) {
  return apiClient
    .post<{ success: boolean; compensation: CommandCenterCompensation; mission: CommandCenterMission }>(
      `/api/v3/command-center/missions/${missionId}/compensations/${compensation.id}/approve`,
      { contract_hash: compensation.contract_hash, comment }
    )
    .then(response => response.data)
}

export function rejectCommandCenterCompensation(
  missionId: string,
  compensation: Pick<CommandCenterCompensation, 'id' | 'contract_hash'>,
  comment: string
) {
  return apiClient
    .post<{ success: boolean; compensation: CommandCenterCompensation; mission: CommandCenterMission }>(
      `/api/v3/command-center/missions/${missionId}/compensations/${compensation.id}/reject`,
      { contract_hash: compensation.contract_hash, comment }
    )
    .then(response => response.data)
}

export function cancelCommandCenterMission(missionId: string, comment = '') {
  return apiClient
    .post<CommandCenterMission>(
      `/api/v3/command-center/missions/${missionId}/cancel`,
      { comment }
    )
    .then(response => response.data)
}

export function sendCommandCenterFeedback(missionId: string, content: string) {
  return apiClient
    .post<CommandCenterMission>(
      `/api/v3/command-center/missions/${missionId}/feedback`,
      { content }
    )
    .then(response => response.data)
}

export function listCommandCenterMemoryCandidates(
  params: { status?: string; mission_id?: string; limit?: number } = {}
) {
  return apiClient
    .get<CommandCenterMemoryCandidatesResponse>(
      '/api/v3/command-center/memory-candidates',
      { params }
    )
    .then(response => response.data)
}

export function approveCommandCenterMemoryCandidate(
  candidateId: string,
  payload: MemoryCandidateReviewPayload = {}
) {
  return apiClient
    .post<{ success: boolean; candidate: CommandCenterMemoryCandidate }>(
      `/api/v3/command-center/memory-candidates/${candidateId}/approve`,
      payload
    )
    .then(response => response.data)
}

export function rejectCommandCenterMemoryCandidate(
  candidateId: string,
  payload: MemoryCandidateReviewPayload
) {
  return apiClient
    .post<{ success: boolean; candidate: CommandCenterMemoryCandidate }>(
      `/api/v3/command-center/memory-candidates/${candidateId}/reject`,
      payload
    )
    .then(response => response.data)
}
