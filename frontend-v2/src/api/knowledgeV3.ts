import client from './client'

const root = '/api/v3/knowledge'
const quiet = { suppressErrorToast: true }
export interface Space { id: string; name: string; project_id: string }
export interface Span { id: string; text: string; locator: Record<string, number> }
export interface KnowledgeBlock { block_id: string; text: string; span_ids: string[]; epistemic_status: string }
export interface PageOperation { page_id: string; base_revision: number; type: string; title: string; blocks: KnowledgeBlock[]; aliases?: string[]; superseded_by?: string }
export interface ChangeSet {
  id: string; status: string; payload_hash: string;
  payload: { pages: PageOperation[]; extraction_mode: string; links: { rationale: string; relation?: string }[] };
  relation_targets?: { page_id: string; revision: number; body_json: PageOperation }[];
  before: { page_id: string; body_json: PageOperation }[];
  sources: { version_id: string; title: string; spans: Span[]; external_references?: { kind: string; version: number; lifecycle: string; independent_evidence: boolean }[] }[];
}
export interface Item { id: string; title?: string; stage?: string; status?: string; revision?: number; type?: string; error_code?: string; change_set_id?: string; source_version_id?: string }
export interface Citation { source_ref: string; page_id: string; revision: number; title: string; excerpt: string; epistemic_status?: string; citations: { source_version_id: string; span_id: string; text: string; locator: Record<string, number> }[] }
export interface Answer { answer_mode: string; answer: string; citations: Citation[]; gaps: string[]; conflicts?: { source_title: string; target_title: string; source_ref: string; target_ref: string; rationale: string; stale: boolean }[] }
export interface KnowledgeStatus { enabled: boolean; write_enabled: boolean; worker_enabled: boolean; compiler: string; projection_enabled?: boolean; context_mode?: string }
export const newRequestKey = () => crypto.randomUUID()
const headers = (key: string) => ({ 'Idempotency-Key': key })

export const knowledgeStatus = async () => (await client.get<KnowledgeStatus>(`${root}/status`, quiet)).data
export const knowledgeSpaces = async () => (await client.get<{ items: Space[] }>(`${root}/spaces`, quiet)).data.items
export const knowledgeProjects = async () => (await client.get<{ items: { id: string; name: string }[] }>(`${root}/projects`, quiet)).data.items
export const createKnowledgeSpace = async (name: string, project_id: string, key: string) => (await client.post<Space>(`${root}/spaces`, { name, project_id }, { ...quiet, headers: headers(key) })).data
export const uploadKnowledge = async (spaceId: string, file: File, key: string) => {
  const form = new FormData(); form.append('space_id', spaceId); form.append('file', file)
  return (await client.post<{ version_id: string; duplicate: boolean }>(`${root}/sources`, form, { ...quiet, headers: { ...headers(key), 'Content-Type': 'multipart/form-data' } })).data
}
export const enqueueKnowledge = async (space_id: string, source_version_id: string, concept_title: string, key: string) => (await client.post(`${root}/ingestions`, { space_id, source_version_id, concept_title }, { ...quiet, headers: headers(key) })).data
export const knowledgeItems = async (spaceId: string, kind: string, offset = 0) => (await client.get<{ items: Item[]; total: number }>(`${root}/spaces/${encodeURIComponent(spaceId)}/items/${kind}`, { ...quiet, params: { limit: 50, offset } })).data
export const knowledgeChange = async (id: string) => (await client.get<ChangeSet>(`${root}/change-sets/${encodeURIComponent(id)}`, quiet)).data
export const reviewKnowledge = async (change: ChangeSet, decision: string, reason: string, key: string) => (await client.post(`${root}/change-sets/${change.id}/review`, { payload_hash: change.payload_hash, decision, reason }, { ...quiet, headers: headers(key) })).data
export const publishKnowledge = async (change: ChangeSet, key: string) => (await client.post<{ release_id: string; projection_status: string }>(`${root}/change-sets/${change.id}/publish`, { payload_hash: change.payload_hash }, { ...quiet, headers: headers(key) })).data
export const queryKnowledge = async (space_id: string, query: string) => (await client.post<Answer>(`${root}/query`, { space_id, query }, quiet)).data
export const knowledgePage = async (id: string, revision?: number) => (await client.get<{ title: string; revision: number; body_json: PageOperation; citations: Citation['citations'] }>(`${root}/pages/${encodeURIComponent(id)}`, { ...quiet, params: { revision } })).data
export const knowledgeSource = async (id: string) => (await client.get<{ title: string; spans: Span[] }>(`${root}/sources/${encodeURIComponent(id)}`, quiet)).data
export const retryKnowledgeJob = async (id: string, key: string) => (await client.post(`${root}/jobs/${encodeURIComponent(id)}/retry`, {}, { ...quiet, headers: headers(key) })).data
export const cancelKnowledgeJob = async (id: string, key: string) => (await client.post(`${root}/jobs/${encodeURIComponent(id)}/cancel`, {}, { ...quiet, headers: headers(key) })).data

export function knowledgeError(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: string | { message?: string } } } })?.response?.data?.detail
  return typeof detail === 'string' ? detail : detail?.message || '操作失败，请检查连接后重试。'
}

export interface MaintenanceRequest {
  action: 'rename' | 'merge' | 'relate' | 'edit'; page_id: string; base_revision: number;
  title?: string; target_page_id?: string; target_revision?: number; relation?: string;
  reason: string; blocks?: KnowledgeBlock[];
}
export interface MaintenanceReport { sequence: number; access_epoch: number; pages_checked: number; pending_changes: number; issues: { kind: string; page_id: string; target_page_id?: string; message: string }[]; automatic_semantic_check: boolean }
export interface ProjectionHealth { status: string; issues: string[]; expected_sequence?: number; expected_epoch?: number; pointer?: { sequence: number; access_epoch: number }; events: { id: string; event_type: string; status: string; attempts: number; error_code?: string }[] }
export const knowledgeMaintenance = async (spaceId: string) => (await client.get<MaintenanceReport>(`${root}/spaces/${encodeURIComponent(spaceId)}/maintenance`, quiet)).data
export const knowledgeProjection = async (spaceId: string) => (await client.get<ProjectionHealth>(`${root}/spaces/${encodeURIComponent(spaceId)}/projection`, quiet)).data
export const proposeKnowledgeMaintenance = async (spaceId: string, body: MaintenanceRequest, key: string) => (await client.post<{ id: string }>(`${root}/spaces/${encodeURIComponent(spaceId)}/maintenance/candidates`, body, { ...quiet, headers: headers(key) })).data
export const replayKnowledgeProjection = async (spaceId: string, eventId: string, regenerate: boolean, key: string) => (await client.post(`${root}/spaces/${encodeURIComponent(spaceId)}/projection/${encodeURIComponent(eventId)}/replay`, { regenerate }, { ...quiet, headers: headers(key) })).data
export const knowledgeHistory = async (id: string) => (await client.get<{ items: { revision: number; title: string }[]; status: string; superseded_by: string }>(`${root}/pages/${encodeURIComponent(id)}/history`, quiet)).data
export const appendKnowledgeSource = async (space_id: string, source_version_id: string, page: Item, key: string) => (await client.post(`${root}/ingestions`, { space_id, source_version_id, concept_title: page.title, target_page_id: page.id, base_revision: page.revision }, { ...quiet, headers: headers(key) })).data

export interface ShadowEntry { title: string; content: string; source_ref: string; authority: string; revision: number; epistemic_status: string; source_version_refs: string[]; evidence: { ref: string; source_version_id: string; locator: Record<string, number> }[] }
export interface ShadowSnapshot { id: string; mode: string; injected: boolean; content_hash: string; access_epoch: number; items: ShadowEntry[]; knowledge_refs: string[]; candidate_count: number; conflict_count: number; gaps: string[]; budget: { total_chars: number; baseline_chars: number; knowledge_chars_limit: number; knowledge_chars_used: number } }
export const previewKnowledgeContext = async (spaceId: string, body: { project_id: string; query: string; total_chars: number; baseline_chars: number }) => (await client.post<ShadowSnapshot>(`${root}/spaces/${encodeURIComponent(spaceId)}/context/preview`, body, quiet)).data
export const captureKnowledgeContext = async (spaceId: string, body: { project_id: string; query: string; total_chars: number; baseline_chars: number }, key: string) => (await client.post<ShadowSnapshot>(`${root}/spaces/${encodeURIComponent(spaceId)}/context/snapshots`, body, { ...quiet, headers: headers(key) })).data
export const readKnowledgeContext = async (id: string, project_id: string) => (await client.get<ShadowSnapshot>(`${root}/context/snapshots/${encodeURIComponent(id)}`, { ...quiet, params: { project_id } })).data

export interface ExternalReference { kind: 'artifact' | 'document'; container_id: string; object_id: string; version: number; expected_hash: string; selected: boolean }
export interface BridgeOverview { memory_mode: string; automatic_memory_bridge: boolean; proposals: { id: string; status: string; reason: string }[]; imports: { id: string; source_version_id: string; reference: ExternalReference & { lifecycle: string } }[] }
export interface MemoryProposalResult { id: string; mode: string; approved: boolean; knowledge_revision_ref: string; proposed_content: string; evidence_refs: string[] }
export interface MaintenanceReceipt { id: string; period_key: string; work_run_id: string; report: { attention_required: boolean; changed: boolean; notification_sent: boolean; structural: MaintenanceReport; failed_jobs: string[]; dead_letters: string[]; memory_needs_review: string[] } }
export const knowledgeBridges = async (sid: string) => (await client.get<BridgeOverview>(`${root}/spaces/${encodeURIComponent(sid)}/bridges`, quiet)).data
export const importKnowledgeReference = async (sid: string, body: ExternalReference, key: string) => (await client.post<{ version_id: string; duplicate: boolean; auto_extract: boolean }>(`${root}/spaces/${encodeURIComponent(sid)}/external-imports`, body, { ...quiet, headers: headers(key) })).data
export const proposeKnowledgeMemory = async (sid: string, body: { page_id: string; revision: number; block_id: string; memory_key: string; proposed_content: string; reason: string }, key: string) => (await client.post<MemoryProposalResult>(`${root}/spaces/${encodeURIComponent(sid)}/memory-proposals`, body, { ...quiet, headers: headers(key) })).data
export const readKnowledgeMemoryProposal = async (id: string) => (await client.get<MemoryProposalResult>(`${root}/memory-proposals/${encodeURIComponent(id)}`, quiet)).data
export const maintainKnowledge = async (sid: string, cadence: string) => (await client.post<MaintenanceReceipt>(`${root}/spaces/${encodeURIComponent(sid)}/maintenance-runs`, { cadence }, quiet)).data
export const knowledgeMaintenanceRuns = async (sid: string) => (await client.get<{ items: MaintenanceReceipt[] }>(`${root}/spaces/${encodeURIComponent(sid)}/maintenance-runs`, quiet)).data.items
