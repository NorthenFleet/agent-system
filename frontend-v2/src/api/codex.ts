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
  loop_id?: string
  loop_round?: number
  loop_stage?: 'plan' | 'develop' | 'evaluate'
  parent_task_id?: string
}

export interface CodexLoopRound {
  round: number
  stage: string
  jobs: string[]
}

export interface CodexLoop {
  id: string
  task_id: string
  title: string
  instruction: string
  repo: string
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'
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
}

export function getCodexStatus() {
  return apiClient.get('/api/v2/codex/status').then(r => r.data)
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
