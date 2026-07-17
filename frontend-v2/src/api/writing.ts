import apiClient from './client'
import type { DocumentSpec } from './projects'

export interface WritingSectionOutline {
  id: string
  title: string
  level: number
  line: number
  anchor: string
}

export interface WritingSection {
  id: string
  title: string
  kind: 'chapter' | 'frontmatter' | 'references' | 'appendix' | string
  order_index: number
  start_line: number
  end_line: number
  summary: string
  outline: WritingSectionOutline[]
  word_count: number
  heading_count: number
  image_count: number
  citation_count: number
  status: string
  content?: string
  version?: number
  asset_paths?: string[]
}

export interface WritingQualitySummary {
  score: number
  blockers: number
  warnings: number
  missing_assets: number
  missing_references: number
  uncited_references: number
}

export interface WritingWorkspace {
  project: {
    id: string
    name: string
    description?: string
    status?: string
    progress?: number
    owner_agent?: string
    document_spec?: DocumentSpec
  }
  manifest: {
    version: number
    edition?: string
    expected_chapters?: number
    source_markdown: string
    source_word?: string
    working_markdown: string
    updated_at: string
  }
  stats: {
    size_chars: number
    word_count: number
    section_count: number
    chapter_count: number
    heading_count: number
    image_count: number
    formal_reference_count: number
  }
  sections: WritingSection[]
  quality: WritingQualitySummary
  reference_summary: {
    formal: number
    cited: number
    uncited: number
    knowledge: number
    in_text_citations: number
    sections_with_citations: number
  }
}

export interface WritingReferenceLocation {
  section_id: string
  title: string
  kind: string
  count: number
}

export interface WritingReferenceCoverage {
  section_id: string
  title: string
  kind: string
  unique_references: number
  citation_occurrences: number
  reference_numbers: number[]
}

export interface WritingReference {
  id: string
  number?: number
  text?: string
  title?: string
  year?: string
  document_type?: string
  usage_count?: number
  section_count?: number
  locations?: WritingReferenceLocation[]
  status?: string
  source_type?: string
  note?: string
}

export interface WritingGraphNode {
  id: string
  name: string
  type: 'section' | 'concept' | 'claim' | string
  category?: string
  value?: number
  detail?: string
}

export interface WritingGraphEdge {
  source: string
  target: string
  relation: string
  weight?: number
}

export interface WritingProjectCreate {
  name: string
  description?: string
  document_type?: string
  writing_goal?: string
  target_audience?: string
  output_format?: string
  outline?: string[]
  owner_agent?: string
  priority?: string
}

export function createWritingProject(payload: WritingProjectCreate) {
  return apiClient.post<{ project: { id: string }; workspace: WritingWorkspace }>(
    '/api/v3/writing/projects',
    payload
  ).then(r => r.data)
}

export function getWritingWorkspace(projectId: string) {
  return apiClient.get<WritingWorkspace>(`/api/v3/writing/projects/${encodeURIComponent(projectId)}/workspace`).then(r => r.data)
}

export function getWritingSection(projectId: string, sectionId: string) {
  return apiClient.get<WritingSection>(`/api/v3/writing/projects/${encodeURIComponent(projectId)}/sections/${encodeURIComponent(sectionId)}`).then(r => r.data)
}

export function getWritingFulltext(projectId: string) {
  return apiClient.get<{ content: string; version: number; asset_paths: string[] }>(
    `/api/v3/writing/projects/${encodeURIComponent(projectId)}/fulltext`
  ).then(r => r.data)
}

export function updateWritingSection(projectId: string, sectionId: string, payload: { content: string; expected_version: number; actor?: string }) {
  return apiClient.put<WritingSection>(`/api/v3/writing/projects/${encodeURIComponent(projectId)}/sections/${encodeURIComponent(sectionId)}`, payload).then(r => r.data)
}

export function getWritingReferences(projectId: string) {
  return apiClient.get<{
    formal: WritingReference[]
    knowledge: WritingReference[]
    section_coverage: WritingReferenceCoverage[]
    summary: WritingWorkspace['reference_summary']
  }>(`/api/v3/writing/projects/${encodeURIComponent(projectId)}/references`).then(r => r.data)
}

export function getWritingGraph(projectId: string) {
  return apiClient.get<{
    nodes: WritingGraphNode[]
    edges: WritingGraphEdge[]
    summary: { sections: number; concepts: number; claims: number; relations: number }
  }>(`/api/v3/writing/projects/${encodeURIComponent(projectId)}/graph`).then(r => r.data)
}

export function getWritingQuality(projectId: string) {
  return apiClient.get<{
    summary: WritingQualitySummary
    issues: Array<{ severity: string; type: string; message: string }>
  }>(`/api/v3/writing/projects/${encodeURIComponent(projectId)}/quality`).then(r => r.data)
}

export function getWritingVersions(projectId: string) {
  return apiClient.get<{ versions: Array<{ name: string; size_bytes: number; created_at: string; current?: boolean }> }>(
    `/api/v3/writing/projects/${encodeURIComponent(projectId)}/versions`
  ).then(r => r.data)
}

export function getWritingAsset(projectId: string, path: string) {
  return apiClient.get<Blob>(`/api/v3/writing/projects/${encodeURIComponent(projectId)}/assets`, {
    params: { path },
    responseType: 'blob'
  }).then(r => r.data)
}

export function getWritingSourceWord(projectId: string) {
  return apiClient.get<Blob>(`/api/v3/writing/projects/${encodeURIComponent(projectId)}/source-word`, {
    responseType: 'blob'
  }).then(r => r.data)
}

export function exportWritingDocument(projectId: string, format: 'docx' | 'pdf') {
  return apiClient.post<Blob>(`/api/v3/writing/projects/${encodeURIComponent(projectId)}/export`, { format }, {
    responseType: 'blob',
    timeout: 240000
  }).then(r => r.data)
}
