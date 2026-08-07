import apiClient from './client'

export type CodexJobStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'

export interface CodexJob {
  id: string
  agent_id: string
  agent_role: string
  task_id?: string
  instruction: string
  repo: string
  status: CodexJobStatus
  created_at: string
  updated_at: string
  started_at?: string | null
  finished_at?: string | null
  exit_code?: number | null
  error?: string | null
  log_file: string
  final_file: string
  summary: string
  running: boolean
  runner_mode?: 'local' | 'ssh' | string
  loop_id?: string
  loop_round?: number
  loop_stage?: 'plan' | 'develop' | 'evaluate'
  parent_task_id?: string
}

export interface CodexStatus {
  codex_bin: string
  available: boolean
  runner: string
  runner_mode: 'local' | 'ssh' | string
  remote_host?: string | null
  remote_user?: string | null
  remote_repo?: string | null
  sandbox?: string
  approval?: string
  health?: {
    configured: boolean
    available: boolean
    reachable: boolean
    codex_executable: boolean
    codex_version?: string
    repo?: string
    repo_exists: boolean
    repo_writable: boolean
    git_root?: string
    repo_relative_path?: string
    repo_is_git_root?: boolean
    checked_at?: string
    error?: string
  }
}

export interface CodexLoopRound {
  round: number
  stage: string
  jobs: string[]
  checkpoint?: DevelopmentRoundCheckpoint
  evaluation?: DevelopmentRoundEvaluation
}

export interface CodexLoop {
  id: string
  task_id: string
  title: string
  instruction: string
  repo: string
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled' | 'needs_attention'
  current_round: number
  current_stage: string
  max_rounds: number
  planner_agent_id: string
  developer_agent_id: string
  evaluator_agent_id: string
  rounds: CodexLoopRound[]
  created_at: string
  updated_at: string
  finished_at?: string | null
  summary?: string
  error?: string | null
  source_repo?: string | null
  source_working_directory?: string | null
  repo_relative_path?: string | null
  execution_worktree_root?: string | null
  execution_repo?: string | null
  execution_branch?: string | null
  integration_branch?: string | null
  base_commit?: string | null
  result_commit?: string | null
  merge_commit?: string | null
  workspace_status?: string | null
  handoff_reason?: string | null
}

export interface DevelopmentRoundCheckpoint {
  round: number
  commit_sha?: string
  created_commit: boolean
  changed_files: string[]
  diff_stat?: string
  clean: boolean
}

export interface DevelopmentRoundEvaluation {
  job_id?: string
  status?: string
  passed?: boolean
  summary?: string
}

export interface DevelopmentLoopRound {
  id: string
  round_index: number
  status: string
  job_ids: string[]
  commit_sha?: string | null
  evidence_json: {
    checkpoint?: DevelopmentRoundCheckpoint
    evaluation?: DevelopmentRoundEvaluation
  }
}

export type DevelopmentPlanStatus =
  | 'pending_approval'
  | 'revision_requested'
  | 'rejected'
  | 'approved'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'manual_takeover'

export interface DevelopmentPlan {
  id: string
  project_id: string
  target_kind: 'task' | 'development_point'
  target_id: string
  task_type: string
  title: string
  instruction: string
  plan_markdown: string
  acceptance_criteria: string[]
  risk_level: string
  status: DevelopmentPlanStatus
  version: number
  planner_agent_id: string
  reviewer_agent_id: string
  developer_agent_id: string
  evaluator_agent_id: string
  max_rounds: number
  review_score: number
  review_summary?: string
  review_details?: { warnings?: string[]; risk_level?: string }
  loop_id?: string | null
  execution_error?: string | null
  approved_by?: string | null
  approved_at?: string | null
  created_at: string
  updated_at: string
  source_repo?: string | null
  workspace_path?: string | null
  source_branch?: string | null
  execution_branch?: string | null
  integration_branch?: string | null
  base_commit?: string | null
  result_commit?: string | null
  merge_commit?: string | null
  workspace_status?: string | null
  handoff_reason?: string | null
  evidence_json?: { rounds?: CodexLoopRound[] }
  loop_rounds?: DevelopmentLoopRound[]
}

export function getCodexStatus(force = false) {
  return apiClient.get<CodexStatus>('/api/v2/codex/status', { params: { force: force || undefined } }).then(r => r.data)
}

export function listCodexJobs(agentId?: string) {
  return apiClient
    .get<{ jobs: CodexJob[] }>('/api/v2/codex/jobs', { params: { agent_id: agentId || undefined } })
    .then(r => r.data)
}

export function createCodexJob(payload: {
  agent_id: string
  instruction: string
  repo?: string
  task_id?: string
}) {
  return apiClient.post<{ job: CodexJob }>('/api/v2/codex/jobs', payload, { timeout: 30000 }).then(r => r.data)
}

export function listCodexLoops(taskId?: string) {
  return apiClient
    .get<{ loops: CodexLoop[] }>('/api/v2/codex/loops', { params: { task_id: taskId || undefined } })
    .then(r => r.data)
}

export function createCodexLoop(payload: {
  task_id: string
  instruction: string
  title?: string
  repo?: string
  developer_agent_id?: string
  planner_agent_id?: string
  evaluator_agent_id?: string
  max_rounds?: number
}) {
  return apiClient.post<{ loop: CodexLoop }>('/api/v2/codex/loops', payload, { timeout: 30000 }).then(r => r.data)
}

export function listDevelopmentPlans(projectId?: string) {
  return apiClient
    .get<{ plans: DevelopmentPlan[] }>('/api/v3/development/plans', { params: { project_id: projectId || undefined } })
    .then(r => r.data)
}

export function createDevelopmentPlan(payload: {
  project_id: string
  target_kind: 'task' | 'development_point'
  target_id: string
  instruction: string
  task_type?: string
  developer_agent_id?: string
  planner_agent_id?: string
  evaluator_agent_id?: string
  max_rounds?: number
  repo?: string
}) {
  return apiClient.post<{ plan: DevelopmentPlan }>('/api/v3/development/plans', payload, { timeout: 30000 }).then(r => r.data)
}

export function decideDevelopmentPlan(planId: string, payload: {
  action: 'approve' | 'revise' | 'reject'
  comment?: string
  auto_execute?: boolean
}) {
  return apiClient
    .post<{ plan: DevelopmentPlan }>(`/api/v3/development/plans/${planId}/decision`, payload, { timeout: 30000 })
    .then(r => r.data)
}

export function retryDevelopmentPlanIntegration(planId: string) {
  return apiClient
    .post<{ plan: DevelopmentPlan }>(`/api/v3/development/plans/${planId}/retry-integration`, {}, { timeout: 30000 })
    .then(r => r.data)
}

export function redispatchDevelopmentPlan(planId: string) {
  return apiClient
    .post<{ plan: DevelopmentPlan }>(`/api/v3/development/plans/${planId}/redispatch`, {}, { timeout: 30000 })
    .then(r => r.data)
}

export function getCodexLoop(loopId: string) {
  return apiClient.get<{ loop: CodexLoop }>(`/api/v2/codex/loops/${loopId}`).then(r => r.data)
}

export function getCodexJob(jobId: string) {
  return apiClient.get<{ job: CodexJob }>(`/api/v2/codex/jobs/${jobId}`).then(r => r.data)
}

export function getCodexJobLogs(jobId: string, tail = 400) {
  return apiClient.get<{ job: CodexJob; logs: string[] }>(`/api/v2/codex/jobs/${jobId}/logs`, { params: { tail } }).then(r => r.data)
}

export function cancelCodexJob(jobId: string) {
  return apiClient.post<{ job: CodexJob }>(`/api/v2/codex/jobs/${jobId}/cancel`).then(r => r.data)
}
