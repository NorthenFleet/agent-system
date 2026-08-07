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

export interface CommandCenterStep {
  id: string
  mission_id: string
  order_index: number
  title: string
  description?: string
  task_type: string
  agent_id: string
  executor: string
  status: string
  dependencies: string[]
  result?: {
    success?: boolean
    output?: string
    error?: string
    duration_ms?: number
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
  created_at: string
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
  plan?: {
    summary?: string
    rationale?: string
    risk_level?: string
    status?: string
  }
  approval?: {
    decision?: string
    decided_by?: string
    comment?: string
    requested_at?: string
    decided_at?: string
  }
  steps: CommandCenterStep[]
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
