import apiClient from './client'

export interface DataSource {
  id: string
  name: string
  source_type: string
  path: string
  status: string
  record_count: number
  last_synced_at?: string
}

export interface DatabaseTable {
  name: string
  rows: number
}

export interface DataOverview {
  database: {
    path: string
    status: string
    schema: DatabaseTable[]
  }
  totals: Record<string, number>
  data_sources: DataSource[]
}

export interface AdminAgent {
  id: string
  name: string
  display_name?: string
  agent_type?: string
  role?: string
  emoji?: string
  team?: string
  category?: string
  status?: string
  current_task?: string
  enabled?: boolean
  visible?: boolean
  visible_in_org?: boolean
  is_clone?: boolean
  source?: string
  responsibilities?: string[]
  updated_at?: string
}

export interface AdminAgentOrgNode {
  id: string
  parent_id?: string
  agent_id?: string
  node_type: string
  name: string
  emoji?: string
  title?: string
  order?: number
  visible?: boolean
  registered?: boolean
  planned?: boolean
}

export interface AdminAgentOrg {
  version: number
  root: AdminAgentOrgNode
  nodes: AdminAgentOrgNode[]
  relations?: Array<{ from: string; to: string; type: string; label?: string }>
  source?: string
}

export function getDataOverview() {
  return apiClient.get<DataOverview>('/api/admin/data/overview').then(r => r.data)
}

export function getDataHealth() {
  return apiClient.get('/api/admin/data/health').then(r => r.data)
}

export function getAdminAgents() {
  return apiClient.get<{ agents: AdminAgent[]; total: number }>('/api/admin/data/agents').then(r => r.data)
}

export function updateAdminAgent(agentId: string, payload: Partial<AdminAgent>) {
  return apiClient.put<AdminAgent>(`/api/admin/data/agents/${encodeURIComponent(agentId)}`, payload).then(r => r.data)
}

export function importAdminAgents() {
  return apiClient.post('/api/admin/data/agents/import').then(r => r.data)
}

export function getAdminAgentOrg(includeHidden = false) {
  return apiClient.get<AdminAgentOrg>('/api/admin/data/agent-org', { params: { include_hidden: includeHidden } }).then(r => r.data)
}

export function importAdminAgentOrg() {
  return apiClient.post('/api/admin/data/agent-org/import').then(r => r.data)
}
