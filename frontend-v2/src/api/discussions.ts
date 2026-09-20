import apiClient from './client'

export type DiscussionStatus = 'captured' | 'exploring' | 'research_candidate' | 'promoted' | 'closed'

export interface DiscussionLink {
  id: string
  target_type: 'project' | 'agent' | 'knowledge' | 'discussion'
  target_id: string
  relation: string
  created_at: string
}

export interface Discussion {
  id: string
  title: string
  status: DiscussionStatus
  summary: string
  question: string
  current_conclusion: string
  hypothesis: string
  open_questions: string[]
  topics: string[]
  agent_ids: string[]
  vault_path: string
  content_hash: string
  promoted_project_id?: string | null
  created_at: string
  updated_at: string
  links: DiscussionLink[]
  content?: string
  body?: string
  content_available?: boolean
  revisions?: Array<{ revision: number; content_hash: string; summary: string; action: string; created_at: string }>
  messages?: DiscussionMessage[]
}

export interface DiscussionMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
  metadata?: Record<string, unknown>
}

export interface DiscussionPayload {
  title: string
  status?: DiscussionStatus
  summary?: string
  question?: string
  body?: string
  current_conclusion?: string
  open_questions?: string[]
  topics?: string[]
  agent_ids?: string[]
}

export function listDiscussions(params: { status?: string; q?: string; topic?: string } = {}) {
  return apiClient.get<{ items: Discussion[]; total: number; topics: string[] }>('/api/v3/discussions', { params }).then(response => response.data)
}

export function getDiscussion(id: string) {
  return apiClient.get<Discussion>(`/api/v3/discussions/${encodeURIComponent(id)}`).then(response => response.data)
}

export function createDiscussion(payload: DiscussionPayload) {
  return apiClient.post<Discussion>('/api/v3/discussions', payload).then(response => response.data)
}

export function createConversation() {
  return apiClient.post<Discussion>('/api/v3/discussions/conversations', { agent_id: 'optimus' }).then(response => response.data)
}

export function sendDiscussionMessage(id: string, content: string) {
  return apiClient.post<Discussion>(`/api/v3/discussions/${encodeURIComponent(id)}/messages`, { content }).then(response => response.data)
}

export function archiveDiscussion(id: string) {
  return apiClient.post<Discussion>(`/api/v3/discussions/${encodeURIComponent(id)}/archive`).then(response => response.data)
}

export function updateDiscussion(id: string, payload: Partial<DiscussionPayload>) {
  return apiClient.put<Discussion>(`/api/v3/discussions/${encodeURIComponent(id)}`, payload).then(response => response.data)
}

export function promoteDiscussion(id: string, payload: { project_name?: string; description?: string; hypothesis?: string; owner_agent?: string }) {
  return apiClient.post<{ discussion: Discussion; project: { id: string; name: string }; reused: boolean }>(`/api/v3/discussions/${encodeURIComponent(id)}/promote`, payload).then(response => response.data)
}
