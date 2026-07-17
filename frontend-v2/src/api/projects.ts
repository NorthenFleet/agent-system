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
  assigned_agent_id?: string
  key_points?: string[]
  outline_items?: Array<string | DocumentOutlineItem>
  subsections?: Array<string | DocumentOutlineItem>
  required_assets?: Array<string | DocumentAsset>
  images?: Array<string | DocumentAsset>
}

export interface DocumentOutlineItem {
  id?: string
  title: string
  summary?: string
  description?: string
  status?: string
}

export interface DocumentAsset {
  id?: string
  title: string
  type?: string
  description?: string
  status?: string
  chapter_title?: string
  section_id?: string
  file_path?: string
  order_index?: number
}

export interface DocumentReference {
  id?: string
  title: string
  source_type?: 'knowledge_base' | 'paper_citation' | string
  citation_type?: 'candidate' | 'formal' | string
  authors?: string
  year?: string | number
  venue?: string
  doi?: string
  url?: string
  citation_key?: string
  chapter_title?: string
  section_id?: string
  status?: string
  note?: string
  node_id?: string
  relation?: string
}

export interface DocumentSpec {
  document_type?: string
  writing_goal?: string
  target_audience?: string
  output_format?: string
  edition?: string
  expected_chapters?: number
  outline?: string[]
  chapters?: DocumentSection[]
  target_structure?: DocumentTargetStructure
  assets?: DocumentAsset[]
  references?: Array<DocumentReference | string>
  source_word?: DocumentSourceWord
  working_markdown?: DocumentWorkingMarkdown
  section_links?: DocumentSectionLink[]
  sync_status?: DocumentSyncStatus
}

export interface DocumentTargetOutlineItem {
  title: string
  level: number
}

export interface DocumentTargetChapter {
  number: number
  title: string
  outline: DocumentTargetOutlineItem[]
}

export interface DocumentTargetStructure {
  title?: string
  version?: string
  source_path?: string
  source_sha256?: string
  generated_at?: string
  chapter_count: number
  heading_count?: number
  chapters: DocumentTargetChapter[]
}

export interface DocumentSourceWord {
  path?: string
  relative_path?: string
  title?: string
  file_name?: string
  size_bytes?: number
  mtime?: string
  knowledge_node_id?: string
}

export interface DocumentWorkingMarkdown {
  path?: string
  relative_path?: string
  status?: string
  synced_at?: string
  generated_from?: string
  generated_from_relative?: string
  size_chars?: number
  heading_count?: number
  paragraph_count?: number
  table_count?: number
}

export interface DocumentSectionLink {
  id?: string
  heading: string
  level?: number
  anchor?: string
  line?: number
  section_id?: string
  section_title?: string
  source?: string
}

export interface DocumentSyncStatus {
  status?: string
  message?: string
  agent_id?: string
  synced_at?: string
  heading_count?: number
  section_link_count?: number
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
  enabled_modules?: string[]
  product_bindings?: import('./products').ProjectProductBinding[]
  context?: {
    project_type?: string
    mission_planning?: import('./missionPlanning').MissionPlanningIntegration
    [key: string]: unknown
  }
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

export function getProjects(params?: { project_type?: 'software' | 'document'; enabled_module?: string }) {
  return apiClient.get<{ projects: Project[]; total: number }>('/api/v3/projects', { params }).then(r => r.data)
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

export function updateProject(projectId: string, payload: Partial<Project>) {
  return apiClient.put<Project>(`/api/v3/projects/${encodeURIComponent(projectId)}`, payload).then(r => r.data)
}

export function deleteProject(projectId: string) {
  return apiClient.delete<{ project_id: string; deleted: boolean }>(
    `/api/v3/projects/${encodeURIComponent(projectId)}`
  ).then(r => r.data)
}

export function getProjectDocumentWorkdraft(projectId: string) {
  return apiClient.get<{
    project_id: string
    source_word: DocumentSourceWord
    working_markdown: DocumentWorkingMarkdown
    section_links: DocumentSectionLink[]
    sync_status: DocumentSyncStatus
  }>(`/api/v3/projects/${encodeURIComponent(projectId)}/document-workdraft`).then(r => r.data)
}

export function syncProjectDocumentWorkdraft(projectId: string, payload: { source_word_path?: string; force?: boolean; agent_id?: string } = {}) {
  return apiClient.post<{
    project: Project
    source_word: DocumentSourceWord
    working_markdown: DocumentWorkingMarkdown
    section_links: DocumentSectionLink[]
    markdown_preview: string
  }>(`/api/v3/projects/${encodeURIComponent(projectId)}/document-workdraft/sync`, payload).then(r => r.data)
}

export function deleteProjectTask(projectId: string, taskId: string) {
  return apiClient.delete(`/api/v3/projects/${encodeURIComponent(projectId)}/tasks/${encodeURIComponent(taskId)}`).then(r => r.data)
}
