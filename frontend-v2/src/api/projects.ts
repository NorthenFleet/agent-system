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
  current_edition_label?: string
  obsidian_edition_label?: string
  publication_edition_label?: string
  version_role_note?: string
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
  course_profile?: CourseProfile
}

export interface CourseUnit {
  id: string
  order: number
  title: string
  delivery_mode: 'theory' | 'practice' | 'assessment'
  hours: number
}

export interface CourseProfile {
  template_key: string
  version: string
  canonical_title: string
  course_code: string
  target_audience: string
  course_nature: string
  total_hours: number
  unit_hours: number
  theory_hours: number
  practice_hours: number
  assessment_hours: number
  theory_sessions: number
  practice_sessions: number
  assessment_sessions: number
  units: CourseUnit[]
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
  project_relations?: ProjectRelation[]
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

export interface ProjectRelationSummary {
  id: string
  name: string
  project_type: 'software' | 'document' | string
  description?: string
  goal?: string
  status?: string
  progress?: number
  current_phase?: string
  task_summary?: {
    total: number
    open: number
    recent: Array<{ id?: string; title?: string; status?: string; progress?: number }>
  }
  work_object?: Record<string, unknown>
}

export interface ProjectRelation {
  id: string
  source_project_id: string
  target_project_id: string
  relation_type: string
  status: string
  purpose?: string
  source_role?: string
  target_role?: string
  current_role?: string
  counterpart_role?: string
  direction?: 'inbound' | 'outbound'
  context_contract?: Record<string, unknown>
  counterpart?: ProjectRelationSummary
}

export interface ProjectRelationshipContext {
  project_id: string
  operating_model?: string
  current_project_role?: string
  current_project_responsibility?: string
  shared_goal?: string
  relations: ProjectRelation[]
  implementation_project?: ProjectRelationSummary | null
  source_documents?: ProjectRelationSummary[]
  boundaries?: string[]
}

export interface ProjectChatContext {
  suggested_next_actions?: Array<{ action?: string; reason?: string } | string>
  open_points?: Array<{ id?: string; title?: string; task_title?: string }>
  project?: Project
  relationship_context?: ProjectRelationshipContext
  background_context?: ProjectRelationshipContext
}

export interface ProjectChatMessage {
  id?: string
  agent_id?: string
  role?: string
  message?: string
  content?: string
  created_at?: string
}

export interface SoftwareDocumentNode {
  id: string
  label: string
  path: string
  kind: 'folder' | 'file'
  category?: string
  extension?: string
  children: SoftwareDocumentNode[]
}

export interface SoftwareDocumentEntry {
  path: string
  name: string
  extension: string
  category: string
  size_bytes: number
  modified_at?: string
}

export interface SoftwareWorkspace {
  project_id: string
  machine: { name: string; host: string; user?: string | null; status: string }
  repository: { path: string; branch: string; commit: string; dirty_count: number }
  documents: SoftwareDocumentEntry[]
  tree: SoftwareDocumentNode[]
  coverage: Array<{ key: string; label: string; count: number; status: 'available' | 'missing' | string }>
  total_documents: number
  generated_at: string
}

export interface SoftwareDocumentContent {
  project_id: string
  path: string
  name: string
  extension: string
  category: string
  content: string
  truncated: boolean
  size_bytes: number
}

export interface SoftwareGitChange {
  path: string
  original_path?: string
  index_status: string
  worktree_status: string
  index_code: string
  worktree_code: string
  staged: boolean
  unstaged: boolean
}

export interface SoftwareGitCommit {
  hash: string
  author: string
  date: string
  subject: string
}

export interface SoftwareGitStatus {
  project_id: string
  repository_id: string
  repository_name: string
  repository: string
  branch: string
  commit: string
  upstream: string
  ahead: number
  behind: number
  staged_count: number
  unstaged_count: number
  total_changes: number
  truncated: boolean
  changes: SoftwareGitChange[]
  commits: SoftwareGitCommit[]
  operation?: string
  output?: string
  error?: string
}

export interface SoftwareGitDiff {
  project_id: string
  repository_id: string
  path: string
  staged: boolean
  content: string
  truncated: boolean
  binary: boolean
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

export function getProjectSoftwareWorkspace(projectId: string) {
  return apiClient.get<SoftwareWorkspace>(
    `/api/v3/projects/${encodeURIComponent(projectId)}/software-workspace`,
    { timeout: 30000 }
  ).then(r => r.data)
}

export function getProjectSoftwareDocument(projectId: string, path: string) {
  return apiClient.get<SoftwareDocumentContent>(
    `/api/v3/projects/${encodeURIComponent(projectId)}/software-workspace/document`,
    { params: { path }, timeout: 30000 }
  ).then(r => r.data)
}

export function getProjectSoftwareGitRepositories(projectId: string) {
  return apiClient.get<{ project_id: string; repositories: SoftwareGitStatus[] }>(
    `/api/v3/projects/${encodeURIComponent(projectId)}/software-workspace/git/repositories`,
    { timeout: 45000 }
  ).then(r => r.data)
}

export function getProjectSoftwareGitStatus(projectId: string, repositoryId: string) {
  return apiClient.get<SoftwareGitStatus>(
    `/api/v3/projects/${encodeURIComponent(projectId)}/software-workspace/git/status`,
    { params: { repository_id: repositoryId }, timeout: 30000 }
  ).then(r => r.data)
}

export function getProjectSoftwareGitDiff(projectId: string, repositoryId: string, path: string, staged: boolean) {
  return apiClient.get<SoftwareGitDiff>(
    `/api/v3/projects/${encodeURIComponent(projectId)}/software-workspace/git/diff`,
    { params: { repository_id: repositoryId, path, staged }, timeout: 30000 }
  ).then(r => r.data)
}

export function stageProjectSoftwareFiles(projectId: string, repositoryId: string, paths: string[]) {
  return apiClient.post<SoftwareGitStatus>(
    `/api/v3/projects/${encodeURIComponent(projectId)}/software-workspace/git/stage`,
    { repository_id: repositoryId, paths }, { timeout: 30000 }
  ).then(r => r.data)
}

export function unstageProjectSoftwareFiles(projectId: string, repositoryId: string, paths: string[]) {
  return apiClient.post<SoftwareGitStatus>(
    `/api/v3/projects/${encodeURIComponent(projectId)}/software-workspace/git/unstage`,
    { repository_id: repositoryId, paths }, { timeout: 30000 }
  ).then(r => r.data)
}

export function commitProjectSoftwareFiles(projectId: string, repositoryId: string, message: string) {
  return apiClient.post<SoftwareGitStatus>(
    `/api/v3/projects/${encodeURIComponent(projectId)}/software-workspace/git/commit`,
    { repository_id: repositoryId, message }, { timeout: 45000 }
  ).then(r => r.data)
}
