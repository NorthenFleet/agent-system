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

export function getCodexJob(jobId: string) {
  return apiClient.get<{ job: CodexJob }>(`/api/v2/codex/jobs/${jobId}`).then(r => r.data)
}

export function getCodexJobLogs(jobId: string, tail = 400) {
  return apiClient.get<{ job: CodexJob; logs: string[] }>(`/api/v2/codex/jobs/${jobId}/logs`, { params: { tail } }).then(r => r.data)
}

export function cancelCodexJob(jobId: string) {
  return apiClient.post<{ job: CodexJob }>(`/api/v2/codex/jobs/${jobId}/cancel`).then(r => r.data)
}
