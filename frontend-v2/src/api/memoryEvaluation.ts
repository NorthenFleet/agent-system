import apiClient from './client'

export type EvaluationCaseStatus = 'draft' | 'active' | 'archived'

export interface MemoryEvaluationCase {
  id: string
  owner_user_id: string
  subject_user_id: string
  origin: string
  source_memory_ref: string
  variant_key: string
  query: string
  project_id: string
  agent_id: string
  limit: number
  expected_source_refs: string[]
  forbidden_source_refs: string[]
  tags: string[]
  notes: string
  review_checks: Record<string, boolean>
  reviewer_confidence: 'unreviewed' | 'medium' | 'high'
  source_snapshot_hash: string
  status: EvaluationCaseStatus
  version: number
  reviewed_by?: string | null
  reviewed_at?: string | null
  created_at: string
  updated_at: string
}

export interface MemoryEvaluationCasePayload {
  id?: string
  subject_user_id?: string
  origin?: string
  source_memory_ref?: string
  variant_key?: string
  query: string
  project_id?: string
  agent_id?: string
  limit?: number
  expected_source_refs: string[]
  forbidden_source_refs: string[]
  tags?: string[]
  notes?: string
  review_checks?: Record<string, boolean>
  reviewer_confidence?: 'unreviewed' | 'medium' | 'high'
  status: EvaluationCaseStatus
}

export interface ShadowMetrics {
  status: string
  samples: { queries: number; distinct_query_fingerprints: number; minimum_required: number; remaining: number }
  availability: { vector_ready_rate: number; target: number; by_status: Record<string, number> }
  latency_ms: { total: { p95: number; target_p95: number }; vector: { p95: number; target_p95: number } }
  ranking_change: { top1_change_rate: number; mean_topk_overlap_ratio: number; mean_rank_displacement: number }
  rollout_gate: { online_observation_passed: boolean; promotion_ready: boolean; blockers: string[] }
  privacy: { raw_query_stored: boolean; ranked_references_stored: boolean; retention_days: number }
}

export interface EvaluationRun {
  id: string
  case_count: number
  dataset_hash: string
  status: 'passed' | 'blocked' | string
  baseline: Record<string, any>
  candidate: Record<string, any>
  assessment: { passed: boolean; checks: Record<string, boolean>; degraded_cases: number }
  strategy_metadata: Record<string, any>
  created_at: string
}

export interface RolloutGate {
  promotion_ready: boolean
  recommended_action: string
  fusion_mode: string
  online: ShadowMetrics
  offline: {
    active_cases: number
    minimum_required: number
    dataset_hash: string
    checks: Record<string, boolean>
    stale_case_ids?: string[]
    approved_sources?: number
    covered_approved_sources?: number
    active_safety_negative_cases?: number
    latest_run?: EvaluationRun | null
  }
  blockers: string[]
  automatic_switch_performed: boolean
}

export interface EvaluationCoverage {
  approved_sources: number
  sources_with_cases: number
  sources_with_active_cases: number
  uncovered_source_refs: string[]
  cases_total: number
  by_status: Record<EvaluationCaseStatus, number>
  by_variant: Record<string, number>
  by_confidence: Record<string, number>
  review_ready_drafts: number
  safety_negative_cases: number
  active_safety_negative_cases: number
  source_drift_cases: number
  missing_source_cases: number
  audit_events: number
  minimum_active_cases: number
  remaining_active_cases: number
  automatic_activation: boolean
}

export interface EvaluationReviewSource {
  source_ref: string
  source_type: string
  title: string
  content: string
  user_id: string
  project_id: string
  agent_id: string
  content_hash: string
  updated_at: string
  case_count: number
  draft_count: number
  active_count: number
  safety_case_count: number
  stale_case_ids: string[]
}

export interface EvaluationReviewQueue {
  sources: EvaluationReviewSource[]
  source_count: number
  cases_total: number
  stale_case_ids: string[]
  missing_case_ids: string[]
  automatic_activation: boolean
}

export interface EvaluationCaseEvent {
  id: string
  case_id: string
  event_type: string
  from_status: string
  to_status: string
  case_version: number
  actor: string
  source_snapshot_hash: string
  case_hash: string
  created_at: string
}

export interface EvaluationReviewPlanItem {
  order: number
  case_id: string
  source_memory_ref: string
  variant_key: string
  suggested_forbidden_source_refs: string[]
  suggestion_requires_human_verification: boolean
  proposal?: {
    suggested_query: string
    suggested_forbidden_source_refs: string[]
    rationale: string
    proposed_by: string
    proposed_at: string
    proposal_hash: string
    status: 'pending_human_review'
  }
}

export interface EvaluationReviewBatch {
  id: string
  name: string
  target_case_count: number
  case_ids: string[]
  review_plan: EvaluationReviewPlanItem[]
  proposal_count: number
  status: 'in_review' | 'completed'
  selected_cases: number
  active_cases: number
  archived_cases: number
  remaining_cases: number
  covered_approved_sources: number
  approved_sources: number
  active_safety_negative_cases: number
  checks: Record<string, boolean>
  blockers: string[]
  by_variant: Record<string, number>
  by_source: Record<string, number>
  next_case: MemoryEvaluationCase | null
  next_plan: EvaluationReviewPlanItem | null
  requested_by: string
  created_at: string
  updated_at: string
  automatic_review: boolean
  automatic_activation: boolean
}

const base = '/api/v3/context/evaluations/retrieval'

export function listMemoryEvaluationCases(status = '') {
  return apiClient.get<{ cases: MemoryEvaluationCase[]; total: number }>(`${base}/cases`, { params: { status } }).then(response => response.data)
}

export function createMemoryEvaluationCase(payload: MemoryEvaluationCasePayload) {
  return apiClient.post<MemoryEvaluationCase>(`${base}/cases`, payload).then(response => response.data)
}

export function updateMemoryEvaluationCase(id: string, payload: MemoryEvaluationCasePayload) {
  return apiClient.put<MemoryEvaluationCase>(`${base}/cases/${encodeURIComponent(id)}`, payload).then(response => response.data)
}

export function generateMemoryEvaluationDrafts() {
  return apiClient.post<{
    approved_memories_scanned: number
    drafts_created: number
    drafts_skipped: number
    automatic_activation: boolean
  }>(`${base}/cases/generate-drafts`).then(response => response.data)
}

export function generateMemoryEvaluationVariants() {
  return apiClient.post<{
    approved_memories_scanned: number
    variants_per_memory: number
    drafts_created: number
    drafts_skipped: number
    automatic_activation: boolean
  }>(`${base}/cases/generate-variants`).then(response => response.data)
}

export function getMemoryEvaluationCoverage() {
  return apiClient.get<EvaluationCoverage>(`${base}/coverage`).then(response => response.data)
}

export function getMemoryEvaluationReviewQueue() {
  return apiClient.get<EvaluationReviewQueue>(`${base}/review-queue`).then(response => response.data)
}

export function getMemoryEvaluationCaseEvents(id: string) {
  return apiClient.get<{ events: EvaluationCaseEvent[]; total: number }>(`${base}/cases/${encodeURIComponent(id)}/events`).then(response => response.data)
}

export function createMemoryEvaluationReviewBatch(targetCount = 30, name = '') {
  return apiClient.post<EvaluationReviewBatch>(`${base}/batches`, { target_count: targetCount, name }).then(response => response.data)
}

export function getLatestMemoryEvaluationReviewBatch() {
  return apiClient.get<{ batch: EvaluationReviewBatch | null }>(`${base}/batches/latest`).then(response => response.data)
}

export function setMemoryEvaluationReviewProposals(
  batchId: string,
  proposals: Array<{
    case_id: string
    suggested_query: string
    suggested_forbidden_source_refs: string[]
    rationale: string
  }>
) {
  return apiClient.put<EvaluationReviewBatch>(`${base}/batches/${encodeURIComponent(batchId)}/proposals`, { proposals }).then(response => response.data)
}

export function runMemoryRetrievalEvaluation(caseIds: string[] = []) {
  return apiClient.post<EvaluationRun>(`${base}/run`, { case_ids: caseIds }).then(response => response.data)
}

export function getLatestMemoryRetrievalEvaluation() {
  return apiClient.get<{ run: EvaluationRun | null }>(`${base}/latest`).then(response => response.data)
}

export function getMemoryShadowMetrics(windowHours = 168) {
  return apiClient.get<ShadowMetrics>('/api/v3/context/vector-memory/shadow-metrics', { params: { window_hours: windowHours } }).then(response => response.data)
}

export function getMemoryRolloutGate(windowHours = 168) {
  return apiClient.get<RolloutGate>('/api/v3/context/vector-memory/rollout-gate', { params: { window_hours: windowHours } }).then(response => response.data)
}
