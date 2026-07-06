import apiClient from './client'

export interface AgentDashboardItem {
  id: string
  agent_id?: string
  name: string
  agent_name?: string
  role?: string
  team?: string
  status: string
  memory?: AgentMemoryItem[]
  responsibilities?: string[]
  metadata?: {
    responsibilities?: string[]
    [key: string]: unknown
  }
  profile?: {
    id?: string
    name?: string
    role?: string
    team?: string
    skills?: string[]
    memory?: AgentMemoryItem[]
    responsibilities?: string[]
  }
  current_task?: string
  legacy_current_task?: string
  current_project_id?: string | null
  current_project_name?: string | null
  current_task_id?: string | null
  current_task_title?: string | null
  current_development_point_id?: string | null
  current_development_point_title?: string | null
  task_progress?: number
  project_progress?: number
  updated_at?: string
  last_seen?: string
  stale?: boolean
  stale_reason?: string
  skill_summary?: {
    total: number
    issues?: number
    skills?: SkillItem[]
  }
  skills?: SkillItem[]
  source?: Record<string, string>
}

export type AgentMemoryItem = string | {
  text?: string
  title?: string
  content?: string
  summary?: string
  date?: string
  created_at?: string
  updated_at?: string
  section?: string
  details?: string
}

export interface AgentOrganizationNode {
  id: string
  parent_id?: string
  node_type: 'person' | 'assistant' | 'agent' | 'group' | 'placeholder'
  agent_id?: string
  name: string
  emoji?: string
  title?: string
  registered?: boolean
  planned?: boolean
  order?: number
}

export interface AgentOrganizationRelation {
  from: string
  to: string
  type: string
  label?: string
}

export interface AgentOrganization {
  version: number
  root: AgentOrganizationNode
  nodes: AgentOrganizationNode[]
  relations: AgentOrganizationRelation[]
}

export interface KnowledgeStats {
  nodes: number
  edges: number
  entity_types: Record<string, number>
  build_time?: string
  vault_path?: string
  index_path?: string
  concept_moc_path?: string
  concept_count?: number
  attached_count?: number
  source_stats?: KnowledgeStats
  available: boolean
}

export interface KnowledgeNode {
  id: string
  title: string
  type: string
  path: string
  score?: number
  matched_keyword?: string
  backbone?: boolean
  layer?: string
  domain?: string
}

export interface KnowledgeRelation {
  source: string
  target: string
  type?: string
  relation?: string
  weight?: number
  backbone?: boolean
}

export interface KnowledgeGraph {
  mode?: 'concept_backbone' | 'full'
  stats: KnowledgeStats
  nodes: KnowledgeNode[]
  relations: KnowledgeRelation[]
  total_relations: number
  limit_edges: number
  source?: string
}

export interface KnowledgeNodeContent {
  node: KnowledgeNode
  content: string
  excerpt: string
  path?: string
  available: boolean
}

export interface KnowledgeNeighbors {
  node: KnowledgeNode
  neighbors: KnowledgeNode[]
  relations: KnowledgeRelation[]
  total: number
}

export interface KnowledgeStackStatus {
  local?: {
    name: string
    available: boolean
    nodes: number
    edges: number
    index_path?: string
    vault_path?: string
    build_time?: string
  }
  lightrag?: {
    name: string
    installed: boolean
    running: boolean
    ready: boolean
    url?: string
    message?: string
  }
  kag?: {
    name: string
    installed: boolean
    running: boolean
    ready: boolean
    path?: string
    message?: string
  }
}

export interface KnowledgeStackQueryResult {
  source: string
  query: string
  mode?: string
  data?: Record<string, unknown>
  local?: { nodes?: KnowledgeNode[]; total?: number }
}

export interface SkillItem {
  id: string
  name: string
  description?: string
  category?: string
  source?: string
  path?: string
  enabled?: boolean
  status?: string
  triggers?: string[]
  required_tools?: string[]
  assigned_agents?: string[]
}

export interface ScheduledTask {
  id: string
  name: string
  owner?: string
  schedule?: string
  status: string
  next_run?: string
  last_run?: string
  success_rate?: number
  description?: string
}

export interface DeviceItem {
  id: string
  name: string
  ip: string
  os?: string
  role?: string
  status: string
  location?: string
  description?: string
  specs?: Record<string, string>
  ports?: number[]
  assigned_agents_details?: Array<{ id: string; name: string; role?: string; status?: string }>
}

export interface BarMessage {
  agent_id: string
  agent_name: string
  message?: string
  action?: string
  drink?: string
  timestamp?: number
  time_str?: string
}

export interface ForumTopic {
  id: string
  title: string
  content?: string
  agent_id?: string
  agent_name?: string
  agent_emoji?: string
  created_at?: string
  updated_at?: string
  views?: number
  post_count?: number
  tags?: string[]
  status?: string
}

export interface NewsItem {
  id: string
  title: string
  summary?: string
  category?: string
  location?: string
  source?: string
  url?: string
  published_at?: string
  priority?: string
  fetched_at?: string
}

export interface NewsLocation {
  lat: number
  lng: number
  name: string
  country?: string
}

export interface NewsLocationPoint extends NewsLocation {
  news?: NewsItem
}

export function getAgentDashboard() {
  return apiClient.get<{ agents: AgentDashboardItem[] }>('/api/v3/agents/dashboard').then(r => r.data)
}

export function getAgentOrganization() {
  return apiClient.get<AgentOrganization>('/api/v3/agents/organization').then(r => r.data)
}

export function getAgentMemory(agentId: string) {
  return apiClient.get<{ agent_id: string; memory: AgentMemoryItem[] }>(`/api/agents/${encodeURIComponent(agentId)}/memory`).then(r => r.data)
}

export function getKnowledgeStats() {
  return apiClient.get<KnowledgeStats>('/api/knowledge/stats').then(r => r.data)
}

export function getKnowledgeNodes(limit = 500, offset = 0, type?: string, q?: string) {
  return apiClient.get<{ nodes: KnowledgeNode[]; total: number; limit: number; offset: number }>('/api/knowledge/nodes', {
    params: { limit, offset, type: type || undefined, q: q || undefined }
  }).then(r => r.data)
}

export function getKnowledgeGraph(limitEdges = 260, type?: string, mode: 'concept_backbone' | 'full' = 'concept_backbone') {
  return apiClient.get<KnowledgeGraph>('/api/knowledge/graph', {
    params: { limit_edges: limitEdges, type: type || undefined, mode }
  }).then(r => r.data)
}

export function searchKnowledge(q: string, limit = 40, type?: string) {
  return apiClient.get<{ query: string; nodes: KnowledgeNode[]; total: number }>('/api/knowledge/search', {
    params: { q, limit, type: type || undefined }
  }).then(r => r.data)
}

export function getKnowledgeNodeContent(nodeId: string, maxChars = 5000) {
  return apiClient.get<KnowledgeNodeContent>(`/api/knowledge/nodes/${encodeURIComponent(nodeId)}/content`, {
    params: { max_chars: maxChars }
  }).then(r => r.data)
}

export function getKnowledgeNeighbors(nodeId: string, limit = 60) {
  return apiClient.get<KnowledgeNeighbors>(`/api/knowledge/neighbors/${encodeURIComponent(nodeId)}`, {
    params: { limit }
  }).then(r => r.data)
}

export function getKnowledgeStackStatus() {
  return apiClient.get<KnowledgeStackStatus>('/api/knowledge-stack/status').then(r => r.data)
}

export function queryKnowledgeStack(query: string, mode = 'mix', limit = 8) {
  return apiClient.post<KnowledgeStackQueryResult>('/api/knowledge-stack/query', {
    query,
    mode,
    limit
  }).then(r => r.data)
}

export function getSkills() {
  return apiClient.get<{ skills: SkillItem[] }>('/api/v3/skills').then(r => r.data)
}

export function getScheduledTasks() {
  return apiClient.get<{ tasks: ScheduledTask[]; managed_by?: string; manager_role?: string; last_updated?: string }>('/api/scheduled-tasks').then(r => r.data)
}

export function getDevices() {
  return apiClient.get<{ devices: DeviceItem[] }>('/api/devices').then(r => r.data)
}

export function getBarMessages(limit = 60) {
  return apiClient.get<{ messages: BarMessage[] }>('/api/bar/messages', { params: { limit } }).then(r => r.data)
}

export function getForumTopics() {
  return apiClient.get<{ topics: ForumTopic[]; total: number }>('/api/forum/topics').then(r => r.data)
}

export function getCommunityStats() {
  return apiClient.get('/api/community/stats').then(r => r.data)
}

export function getNews(limit = 80) {
  return apiClient.get<{ news: NewsItem[]; total?: number }>('/api/news', { params: { limit } }).then(r => r.data)
}

export function getNewsLocations() {
  return apiClient.get<{ locations: Record<string, NewsLocation> }>('/api/news/locations').then(r => r.data)
}

export function getLocationNews() {
  return apiClient.get<{ data: NewsLocationPoint[] }>('/api/news/location-news').then(r => r.data)
}
