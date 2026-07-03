import apiClient from './client'

export interface DevelopmentPoint {
  id: string
  title: string
  status: string
  weight?: number
  assigned_agent?: string
  completion_evidence?: string
}

export interface ProjectTask {
  id: string
  title: string
  description?: string
  assignee_agent?: string
  assignee_agent_id?: string
  type?: string
  status: string
  priority?: string
  progress: number
  development_points: DevelopmentPoint[]
}

export interface DocumentSection {
  id?: string
  title: string
  summary?: string
  main_content?: string
  content_brief?: string
  status?: string
  assigned_agent?: string
  key_points?: string[]
}

export interface DocumentAsset {
  id?: string
  title: string
  type?: string
  description?: string
  status?: string
  chapter_title?: string
  section_id?: string
}

export interface DocumentSpec {
  document_type?: string
  writing_goal?: string
  target_audience?: string
  output_format?: string
  chapters?: DocumentSection[]
  assets?: DocumentAsset[]
}

export interface Project {
  id: string
  name: string
  description?: string
  project_type?: 'software' | 'document' | string
  type?: string
  status: string
  priority?: string
  owner_agent?: string
  project_manager_agent?: string
  progress: number
  current_phase?: string
  document_spec?: DocumentSpec
  design_doc?: {
    summary?: string
    usage_requirements?: unknown[]
    parallel_tasks?: unknown[]
    data_structure?: unknown
    system_architecture?: unknown
    system_functions?: unknown[]
    api_interfaces?: unknown[]
  }
  tasks: ProjectTask[]
}

export interface ProjectChatContext {
  suggested_next_actions?: Array<{ action?: string; reason?: string } | string>
  open_points?: Array<{ id?: string; title?: string; task_title?: string }>
  project?: Project
}

export interface ProjectChatMessage {
  id?: string
  agent_id?: string
  role?: string
  message?: string
  content?: string
  created_at?: string
}

export function getProjects() {
  return apiClient.get<{ projects: Project[]; total: number }>('/api/v3/projects').then(r => r.data)
}

export function getProjectChatContext(projectId: string) {
  return apiClient.get<ProjectChatContext>(`/api/v3/projects/${encodeURIComponent(projectId)}/chat-context`).then(r => r.data)
}

export function getProjectConversation(projectId: string) {
  return apiClient.get<{ messages?: ProjectChatMessage[]; conversation?: ProjectChatMessage[] }>(`/api/v3/projects/${encodeURIComponent(projectId)}/conversation`).then(r => r.data)
}

export function sendProjectChat(projectId: string, payload: { agent_id?: string; message: string; role?: string; intent?: string }) {
  return apiClient.post(`/api/v3/projects/${encodeURIComponent(projectId)}/chat`, payload).then(r => r.data)
}

export function createProjectAgentAction(projectId: string, payload: Record<string, unknown>) {
  return apiClient.post(`/api/v3/projects/${encodeURIComponent(projectId)}/agent-actions`, payload).then(r => r.data)
}
