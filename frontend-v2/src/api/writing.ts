import apiClient from './client'
import type { CourseProfile, DocumentSpec, DocumentTargetStructure } from './projects'

export interface WritingSectionOutline {
  id: string
  title: string
  level: number
  line: number
  local_line: number
  anchor: string
  target_id: string
}

export interface WritingDirectoryNode {
  id: string
  title: string
  node_type: 'document' | 'section' | 'heading'
  source_level: number
  level: 0 | 1 | 2 | 3
  line: number
  anchor: string
  target_id: string
  section_id: string
  kind?: string
  word_count?: number | null
  metadata?: {
    labels?: string[]
  }
  children: WritingDirectoryNode[]
}

export interface WritingSection {
  id: string
  title: string
  kind: 'chapter' | 'frontmatter' | 'references' | 'appendix' | string
  order_index: number
  start_line: number
  end_line: number
  target_id: string
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

export type WritingEditorJson = Record<string, any>

export interface WritingCollaborationAgent {
  id: string
  name: string
  description?: string
  model?: string
  available?: boolean
}

export interface WritingProposal {
  id: string
  job_id?: string
  agent_id?: string
  block_id?: string
  status: 'pending' | 'accepted' | 'rejected' | 'stale' | string
  scope?: 'selection' | 'block' | 'section' | 'document' | string
  title?: string
  summary?: string
  rationale?: string
  instruction?: string
  requires_rebase?: boolean
  diff?: string
  replacement_markdown?: string
  original_content?: WritingEditorJson | string
  proposed_content?: WritingEditorJson | string
  created_at?: string
  risk_level?: 'low' | 'medium' | 'high'
  approval_required?: boolean
  evidence_ref_ids?: string[]
  concurrency_status?: 'unchanged' | 'conflicted' | string
}

export interface WritingCollaborationState {
  project_id?: string
  document_id?: string
  section_id?: string
  content?: WritingEditorJson
  document?: WritingEditorJson
  draft?: {
    content?: WritingEditorJson
    document?: WritingEditorJson
    revision?: number
  }
  revision: number
  document_revision?: number
  approved_revision?: number
  published_revision?: number
  block_revision?: number
  section?: {
    id: string
    legacy_id?: string
    title?: string
    kind?: string
    order_index?: number
    block_ids?: string[]
  }
  projection?: {
    revision: number
    status: 'current' | 'stale' | string
    error?: string
  }
  conflicts?: Array<{
    block_id?: string
    reason: string
    expected_block_revision?: number
    current_block_revision?: number
  }>
  agents: WritingCollaborationAgent[]
  proposals: WritingProposal[]
}

export interface WritingAiJob {
  id: string
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled' | string
  proposal?: WritingProposal
  proposals?: WritingProposal[]
  error?: string
  created_at?: string
  updated_at?: string
}

export type WritingPaneModule = 'document' | 'presentation' | 'diagram' | 'ai'
export type WritingWorkbenchPreset =
  | 'writing'
  | 'presentation'
  | 'document_compare'
  | 'document_presentation'
  | 'diagramming'
  | 'document_diagram'
  | 'presentation_diagram'
  | 'diagram_compare'
  | 'custom'

export interface WritingWorkbenchPaneState {
  module: WritingPaneModule
  resource_id?: string
  section_id?: string
  slide?: number
  ai_conversation_id?: string
  ai_target_locked?: boolean
}

// Short alias retained for workbench components; the prefixed name remains the public API form.
export type WorkbenchPaneState = WritingWorkbenchPaneState

export interface WritingWorkbenchPreference {
  schema_version: 1 | 2 | 3
  revision: number
  preset: WritingWorkbenchPreset
  split_percent: number
  maximized_pane?: 'left' | 'right' | null
  panes: {
    left: WritingWorkbenchPaneState
    right: WritingWorkbenchPaneState
  }
  updated_at?: string
}

export interface WritingWorkbenchPreferenceUpdate {
  expected_revision: number
  preset: WritingWorkbenchPreset
  split_percent: number
  maximized_pane?: 'left' | 'right' | null
  panes: WritingWorkbenchPreference['panes']
}

export interface WritingAiSelectionSnapshot {
  from: number
  to: number
  text: string
  block_id?: string
  block_revision?: number
}

export interface WritingAiTarget {
  kind: 'document' | 'presentation' | 'diagram'
  document_id: string
  document_title?: string
  scope?: 'selection' | 'block' | 'section' | 'document' | 'cells' | 'diagram'
  section_id?: string
  section_title?: string
  block_id?: string
  block_revision?: number
  revision?: number
  selection?: WritingAiSelectionSnapshot
  slide?: number
  diagram_revision?: number
  cell_ids?: string[]
  draft?: Record<string, any>
}

export interface WritingAiConversation {
  id: string
  project_id: string
  agent_id: string
  title: string
  status: 'active' | 'archived' | string
  created_at?: string
  updated_at?: string
}

export interface WritingAiMessage {
  id: string
  conversation_id: string
  role: 'user' | 'assistant' | string
  content: string
  target_context: WritingAiTarget | Record<string, never>
  job_kind?: 'document' | 'presentation' | 'diagram' | string
  job_id?: string
  proposal_ids: string[]
  status:
    | 'queued'
    | 'running'
    | 'partially_applied'
    | 'applied'
    | 'conflicted'
    | 'succeeded'
    | 'completed'
    | 'failed'
    | 'cancelled'
    | string
  error?: string
  created_at?: string
  updated_at?: string
}

export interface WritingAiConversationMessageCreate {
  client_message_id: string
  agent_id: string
  content: string
  target: WritingAiTarget
}

export interface WritingAiConversationMessageResult {
  request_message_id?: string
  response_message_id?: string
  idempotent_replay?: boolean
  job?: WritingAiJob | PresentationSlideJob | DiagramAiJob
}

export interface WritingAssetUploadResult {
  path: string
  filename: string
  content_type: string
  size_bytes: number
  sha256: string
  url: string
}

export interface WritingDraftPatch {
  content?: WritingEditorJson
  expected_revision?: number
  base_document_revision?: number
  client_change_id?: string
  section_id?: string
  changes?: Array<{
    op: 'upsert' | 'insert_after' | 'move_after' | 'delete'
    block_id: string
    expected_block_revision?: number
    after_block_id?: string
    before_block_id?: string
    node?: WritingEditorJson
  }>
}

export interface WritingAiJobCreate {
  client_request_id?: string
  agent_id: string
  scope: 'selection' | 'block' | 'section' | 'document'
  instruction: string
  section_id?: string
  selection?: { from: number; to: number; text: string; block_id?: string; block_revision?: number }
  block_id?: string
  block_revision?: number
  evidence_ref_ids?: string[]
  risk_policy?: { allow_auto_draft?: boolean }
}

export interface WritingClaim {
  id: string
  document_revision: number
  section_id: string
  block_id: string
  claim_text: string
  claim_type: string
  minimum_evidence_level: 'diagnostic' | 'G1' | 'G2' | 'A'
  evidence_status: 'missing' | 'insufficient' | 'sufficient' | string
  status: string
}

export interface WritingEvidenceRef {
  id: string
  source_system: string
  source_record_id: string
  artifact_path: string
  artifact_sha256: string
  perspective_scope: string
  evidence_level: 'diagnostic' | 'G1' | 'G2' | 'A'
  evidence_kind?: 'literature' | 'simulation' | 'dataset' | 'policy' | 'system_record'
  source_quality?: 'peer_reviewed' | 'official' | 'standard' | 'preprint' | 'secondary' | 'internal'
  support_role?: 'supports' | 'contradicts' | 'contextualizes' | 'method_basis'
  directness?: 'direct' | 'indirect' | 'metadata_only'
  allowed_claim_scope: string
  immutable: boolean
}

export interface WritingEvidenceGap {
  id: string
  claim_id: string
  required_level: 'diagnostic' | 'G1' | 'G2' | 'A'
  gap_type: 'literature' | 'experiment' | 'mixed'
  reason: string
  research_matrix: Record<string, any>
  status: string
  dispatched_run_id: string
}

export interface WritingChangeSet {
  id: string
  base_revision: number
  result_revision: number
  proposal_id: string
  operations: Record<string, any>[]
  evidence_ref_ids: string[]
  risk_level: 'low' | 'medium' | 'high'
  approval_policy: string
  status: string
  summary: string
}

export interface WritingJarvisRun {
  id: string
  run_type: string
  status: string
  approval_reason: string
  error: string
  input_payload?: Record<string, any>
  result_payload?: Record<string, any>
  recovery_cursor: Record<string, any>
  steps: Array<{
    id: string
    step_key: string
    status: string
    attempt_count: number
    error: string
    result_payload?: Record<string, any>
  }>
}

export interface WritingRetrievalRef {
  id: string
  provider: string
  provider_record_id: string
  query_id: string
  rank: number
  retrieval_score: number
  title: string
  authors: string[]
  year?: number | null
  venue: string
  doi: string
  url: string
  access_status: string
  screening_status: 'pending' | 'include' | 'exclude' | 'uncertain' | 'duplicate'
  screening_reason: string
}

export interface WritingResearchIteration {
  id: string
  run_id: string
  iteration_no: number
  base_revision: number
  base_section_sha256: string
  candidate_sha256: string
  candidate_payload: Record<string, any>
  candidate_artifact_path: string
  status: string
  change_set_id: string
  evaluation?: {
    id: string
    evaluator_version: string
    hard_gates: Record<string, boolean | number>
    dimension_scores: Record<string, number>
    total_score: number
    baseline_delta: number
    decision: string
    reasons: string[]
  }
}

export interface WritingResearchWorkflow {
  revision: number
  approved_revision: number
  published_revision: number
  claims: WritingClaim[]
  evidence_refs: WritingEvidenceRef[]
  gaps: WritingEvidenceGap[]
  change_sets: WritingChangeSet[]
  runs: WritingJarvisRun[]
}

export interface WritingQualitySummary {
  score: number
  blockers: number
  warnings: number
  missing_assets: number
  missing_references: number
  uncited_references: number
}

export type DocumentEvaluationStatus =
  | 'pending'
  | 'evaluating'
  | 'provisional'
  | 'confirmed'
  | 'stale'
  | 'failed'

export type DocumentEvaluationCriterionStatus =
  | 'pass'
  | 'partial'
  | 'fail'
  | 'pending'
  | 'not_applicable'

export interface DocumentEvaluationDimension {
  id: string
  name: string
  weight: number
  min_score: number
  source: string
  description?: string
  status?: DocumentEvaluationCriterionStatus
  score?: number | null
  confirmed_score?: number | null
  summary?: string
  evidence?: Array<Record<string, any>>
  recommendations?: string[]
}

export interface DocumentEvaluationGate {
  id: string
  name: string
  source: string
  required: boolean
  critical: boolean
  description?: string
  status?: DocumentEvaluationCriterionStatus
  reason?: string
  evidence?: Array<Record<string, any>>
  confirmed_by?: string
  confirmed_at?: string
}

export interface DocumentEvaluationProfile {
  id: string
  system_profile_id: string
  name: string
  version: string
  kind: WritingDocumentKind
  document_types: string[]
  pass_threshold: number
  dimensions: DocumentEvaluationDimension[]
  gates: DocumentEvaluationGate[]
  maturity_labels: string[]
  profile_sha256: string
  policy_revision: number
}

export interface DocumentEvaluationReport {
  id: string
  project_id: string
  document_id: string
  document_title: string
  document_kind: WritingDocumentKind
  document_type: string
  source_sha256: string
  profile_id: string
  profile_name: string
  profile_version: string
  profile_sha256: string
  model: string
  status: DocumentEvaluationStatus
  decision: 'pending' | 'blocked' | 'qualified'
  maturity_level: 'L0' | 'L1' | 'L2' | 'L3' | 'L4' | 'L5'
  maturity_label: string
  technical_score: number | null
  provisional_score: number | null
  confirmed_score: number | null
  coverage: number
  dimensions: DocumentEvaluationDimension[]
  gates: DocumentEvaluationGate[]
  priority_actions: string[]
  linked_documents: Array<Record<string, any>>
  audit: Array<Record<string, any>>
  created_at: string
  updated_at: string
  evaluated_at: string
}

export interface DocumentEvaluationJob {
  id: string
  status: 'queued' | 'running' | 'succeeded' | 'failed'
  report_id: string
  created_at: string
  started_at: string
  finished_at: string
  error: string
}

export interface LinkedDocumentEvaluation {
  document_id: string
  title: string
  kind: WritingDocumentKind
  structure_status?: DocumentStructureBindingStatus
  evaluation_status: DocumentEvaluationStatus
  decision: 'pending' | 'blocked' | 'qualified'
  maturity_level: string
  technical_score: number | null
  score: number | null
}

export interface LinkedDocumentEvaluationSummary {
  documents: LinkedDocumentEvaluation[]
  defense_ready: boolean
  maturity_level: string
  blockers?: string[]
}

export interface WritingStructureSync {
  status: 'aligned' | 'diverged' | 'missing'
  message: string
  current_version: string
  target_version: string
  current_sha256: string
  target_sha256: string
  source_matches: boolean
  chapter_count_delta: number
  heading_count_delta: number
  changed_chapters: number[]
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
  current_structure: DocumentTargetStructure
  structure_sync: WritingStructureSync
  sections: WritingSection[]
  directory: WritingDirectoryNode[]
  quality: WritingQualitySummary
  reference_summary: {
    formal: number
    cited: number
    uncited: number
    knowledge: number
    in_text_citations: number
    sections_with_citations: number
  }
  document?: WritingProjectDocument
}

export type WritingDocumentKind = 'rich_text' | 'workbook' | 'presentation' | 'diagram'

export type DiagramCellType = 'node' | 'edge' | 'group' | 'text' | 'image'

export interface DiagramCell {
  id: string
  cell_revision: number
  type: DiagramCellType
  shape?: string
  x?: number
  y?: number
  width?: number
  height?: number
  label?: string
  source?: string | { cell: string }
  target?: string | { cell: string }
  parent?: string
  attrs?: Record<string, any>
  data?: Record<string, any>
  [key: string]: any
}

export interface DiagramDocumentState {
  schema_version: number
  project_id: string
  document_id: string
  revision: number
  title: string
  diagram_type: string
  theme_id: string
  page_settings: Record<string, any>
  cells: DiagramCell[]
  content_sha256: string
  updated_at: string
}

export interface DiagramResource {
  document: WritingProjectDocument
  diagram: DiagramDocumentState
}

export interface DiagramReference {
  id: string
  diagram_document_id: string
  diagram_revision: number
  target_document_id: string
  target_kind: 'rich_text' | 'presentation'
  target_section_id?: string
  target_slide?: number
  export_format: 'svg' | 'png'
  crop_or_viewbox: Record<string, any>
  caption: string
  status: 'current' | 'update_available' | string
}

export interface DiagramDocumentPublishResult {
  idempotent_replay: boolean
  diagram_revision: number
  document_revision: number
  inserted_block_ids: string[]
  asset: { path: string; url: string; sha256: string }
  reference: DiagramReference
  document: WritingCollaborationState
}

export interface DiagramAiProposal {
  id: string
  job_id: string
  status: string
  base_revision: number
  operations: Record<string, any>[]
  summary: string
  rationale: string
  risk_level: 'low' | 'medium' | 'high'
  conflicts: Array<{ cell_id?: string; reason: string }>
}

export interface DiagramAiJob {
  id: string
  document_id: string
  status: string
  base_revision: number
  target_cell_ids: string[]
  error?: string
  proposal?: DiagramAiProposal
}
export type WritingPublicationStatus = 'draft' | 'review' | 'approved' | 'published' | 'internal'
export type DocumentStructureBindingMode = 'canonical' | 'derived' | 'mapped'
export type DocumentStructureBindingStatus = 'aligned' | 'diverged' | 'stale' | 'missing'

export interface DocumentStructureBinding {
  mode: DocumentStructureBindingMode
  source_document_id: string
  source_version: string
  source_sha256: string
  status: DocumentStructureBindingStatus
  /** Structural integrity of the PPT mapping; retained separately from source freshness. */
  integrity_status?: DocumentStructureBindingStatus
  /** A document edit does not recreate the PPT; it only makes its content reference pending. */
  reference_status?: 'current' | 'document_updated'
  referenced_document_revision?: string
  referenced_document_sha256?: string
  ppt_sha256?: string
  mapped_items: number
  unmapped_items: Array<string | number | Record<string, any>>
  changed_sections: Array<string | number | Record<string, any>>
}

export interface PresentationSlideManifest {
  slide: number
  source_slide?: number
  title: string
  thesis_sections: string[]
  claim: string
  evidence_level: string
  evidence_ids: string[]
  notes: string
  appendix: boolean
}

export interface PresentationManifest {
  schema: string
  contract_version: string
  authority?: {
    thesis?: {
      version?: string
      chapter_count?: number
      heading_count?: number
      sha256?: string
      role?: string
    }
    presentation_source?: {
      filename?: string
      slide_count?: number
      notes_count?: number
      sha256?: string
      role?: string
    }
    presentation_output?: {
      filename?: string
      document_version?: string
      structure_version?: string
      slide_count?: number
      main_slide_count?: number
      appendix_slide_count?: number
      notes_count?: number
      sha256?: string
      status?: string
    }
  }
  structure_binding: DocumentStructureBinding
  narrative_sections: Array<{
    id: string
    title: string
    start_slide: number
    end_slide: number
  }>
  slides: PresentationSlideManifest[]
  systems?: Record<string, any>
  evidence_policy?: Record<string, any>
  document?: WritingProjectDocument
}

export interface PresentationSlideProposal {
  schema: string
  id: string
  status: 'succeeded' | 'failed' | string
  agent_id: string
  slide: number
  title: string
  summary: string
  rationale?: string
  patch: {
    title: string
    claim: string
    notes: string
    evidence_level: string
    evidence_ids: string[]
    appendix: boolean
  }
}

export interface PresentationSlideJob {
  id: string
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled' | string
  project_id: string
  document_id: string
  slide: number
  agent_id: string
  instruction: string
  proposal?: PresentationSlideProposal | null
  error?: string
  created_at?: string
  updated_at?: string
}

export interface DocumentLayoutProfile {
  id: string
  name: string
  version: string
  applies_to: { kind: string; document_types: string[] }
  authority_source: { path?: string; sha256: string; filename?: string; role?: string; document_id?: string; document_title?: string }
  template_path: string
  template_sha256: string
  status: 'draft' | 'validated' | 'published'
  page: Record<string, string | number | boolean>
  styles: Record<string, Record<string, string | number | boolean>>
  rules: Record<string, any>
  sample_docx_path?: string
  sample_pdf_path?: string
  preview?: { pdf_path?: string; page_count: number; showcase_pages: Array<{ kind: string; label: string; page: number }> }
}

export interface DocumentLayoutBinding {
  profile_id?: string
  profile_name?: string
  profile_version?: string
  template_sha256?: string
  content_version?: number
  content_sha256?: string
  current_content_sha256?: string
  layout_revision?: string
  delivery_basename?: string
  status: 'aligned' | 'stale' | 'missing'
  changed_reasons?: string[]
  cover?: Record<string, string>
  frontmatter?: Record<string, string>
  latest_delivery?: Record<string, any>
  delivery_history?: Array<Record<string, any>>
}

export interface DocumentLayoutAuditReport {
  generated_at: string
  compliance_score: number
  status: 'passed' | 'blocked'
  checks: Array<{ key: string; label: string; passed: boolean; detail: string; severity: string }>
  blockers: string[]
  warnings: string[]
  page_anomalies: Array<Record<string, any>>
}

export interface DocumentLayoutState {
  profiles: DocumentLayoutProfile[]
  profile?: DocumentLayoutProfile
  binding: DocumentLayoutBinding
  cover: Record<string, string>
  frontmatter: Record<string, string>
  audit?: DocumentLayoutAuditReport
  sample: { docx_path?: string; pdf_path?: string }
  display: { content: string; template: string; delivery: string; publication_status: string }
  template_catalog?: { document_type: string; same_type_count: number; total_count: number }
}

export interface DocumentContentFidelityReport {
  schema: 'openclaw.document-content-fidelity.v1'
  project_id: string
  document_id: string
  document_title: string
  source_kind: 'markdown' | 'docx'
  source_sha256: string
  structured_revision: number
  structured_sha256: string
  status: 'passed' | 'degraded' | 'blocked' | 'stale'
  migration_safe: boolean
  source_metrics: Record<string, number | string>
  structured_metrics: Record<string, number | string>
  differences: Record<string, { source: number; structured: number }>
  unresolved_assets: string[]
  empty_formulas: string[]
  warnings: string[]
  audited_at: string
  collaboration_revision?: number
}

export interface WritingProjectDocument {
  id: string
  title: string
  kind: WritingDocumentKind
  status: 'active' | 'archived'
  sort_order: number
  is_primary: boolean
  is_output_product: boolean
  output_format: 'docx' | 'pdf' | 'pptx' | ''
  data_source_ids: string[]
  print_profile: string
  publication_status: WritingPublicationStatus
  rules_version: string
  data_version: string
  product_type: string
  course_unit_ids: string[]
  quality_profile: string
  required_for_release: boolean
  source_refs: Array<{
    ref_type: 'project_document' | 'project_product' | string
    project_id: string
    document_id: string
    product_id: string
    relation: string
    required: boolean
    version: string
  }>
  expected_chapters: number
  legacy_primary?: boolean
  revision: number
  source_path?: string
  source_checksum?: string
  edit_policy?: 'editable' | 'read_only'
  delivery_role?: 'deliverable' | 'historical_reference' | 'candidate'
  lineage?: {
    series_id: string
    edition_label: string
    sequence: number
    source_type: 'markdown' | 'chapter_bundle' | 'docx' | 'structured_authority'
    parent_document_id?: string
    source_checksum: string
    generated_at?: string
    source_paths?: string[]
  } | null
  created_at: string
  updated_at: string
  health?: string
  metadata?: Record<string, any>
  structure_binding?: DocumentStructureBinding
  stats?: {
    word_count?: number
    chapter_count?: number
    sheet_count?: number
    formula_count?: number
    cell_count?: number
    slide_count?: number
    preview_ready?: boolean
    main_slide_count?: number
    appendix_slide_count?: number
    notes_count?: number
  }
}

export interface WritingDocumentComparisonChange {
  operation: 'added' | 'deleted' | 'modified' | 'unchanged'
  left_index?: number | null
  right_index?: number | null
  left_text: string
  right_text: string
  similarity: number
}

export interface WritingDocumentComparison {
  cache_key: string
  cached: boolean
  left: { document_id: string; title: string; revision: number; checksum: string }
  right: { document_id: string; title: string; revision: number; checksum: string }
  summary: { added: number; deleted: number; modified: number; unchanged: number }
  sections: Array<{
    key: string
    left_title: string
    right_title: string
    matched: boolean
    summary: WritingDocumentComparison['summary']
    changes: WritingDocumentComparisonChange[]
  }>
}

export interface WritingProjectDocuments {
  project: { id: string; name: string; description?: string; status?: string; progress?: number }
  documents: WritingProjectDocument[]
  summary: {
    total: number
    active: number
    archived: number
    rich_text: number
    workbook: number
    presentation: number
    diagram: number
    output_products: number
    internal_sources: number
  }
}

export interface CourseProductionBlocker {
  code: string
  message: string
  scope?: string
  source_ref?: Record<string, any>
}

export interface CourseProductionProduct {
  key: string
  title: string
  document_id: string
  product_type?: string
  publication_status?: WritingPublicationStatus
  ready: boolean
  blockers: CourseProductionBlocker[]
}

export interface CourseWorkPoint {
  id: string
  title: string
  description: string
  task_id: string
  task_title: string
  workstream_key: string
  status: string
  assigned_agent: string
  document_ids: string[]
  course_unit_ids: string[]
  acceptance_criteria: string[]
  checklist: string[]
  context: Record<string, any>
  iteration: number
  work_run_id: string
  work_run_status: string
  eligible: boolean
}

export interface CourseWorkPlan {
  workstreams: Array<{
    key: string
    title: string
    task_id: string
    assignee_agent: string
    status: string
    progress: number
    document_ids: string[]
    points: number
    completed_points: number
    dependency_ready: boolean
    blocked_by: string[]
    point_items: CourseWorkPoint[]
    ready: boolean
  }>
  summary: {
    required: number
    tracked: number
    completed: number
    active: number
    points: number
    completed_points: number
    ready: boolean
  }
  execution: {
    current_iteration: number
    eligible_points: number
    queued_points: number
    active_points: number
    review_points: number
    blocked_points: number
    completed_points: number
    missions: Array<{
      id: string
      title: string
      status: string
      approval_status: string
      iteration_start: number
      iteration_end: number
      updated_at: string
    }>
  }
}

export interface CourseProductionStatus {
  course_profile: CourseProfile
  products: CourseProductionProduct[]
  blockers: CourseProductionBlocker[]
  work_plan: CourseWorkPlan
  summary: {
    required: number
    ready: number
    blocked: number
    can_export: boolean
  }
}

export interface WorkbookSheetSummary {
  name: string
  max_row: number
  max_column: number
  formula_count: number
  cell_count: number
}

export interface WorkbookMetadata {
  document: WritingProjectDocument
  sheet_count: number
  formula_count: number
  cell_count: number
  sheets: WorkbookSheetSummary[]
}

export interface WorkbookCell {
  coordinate: string
  row: number
  column: number
  value: string | number | boolean | null
  display: string | number | boolean | null
  formula: string
  data_type: string
  number_format: string
  style: {
    bold: boolean
    italic: boolean
    horizontal: string
    vertical: string
    fill: string
  }
}

export interface WorkbookSheet {
  document_id: string
  sheet: string
  revision: number
  max_row: number
  max_column: number
  columns: Array<{ index: number; letter: string; width: number }>
  rows: Array<{ index: number; height: number }>
  cells: WorkbookCell[]
  merges: string[]
  validations: Array<{ ranges: string; type: string; formula1: string; allow_blank: boolean }>
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

export function getWritingDocuments(projectId: string, includeArchived = true) {
  return apiClient.get<WritingProjectDocuments>(
    `/api/v3/writing/projects/${encodeURIComponent(projectId)}/documents`,
    { params: { include_archived: includeArchived } }
  ).then(r => r.data)
}

export function createWritingDocument(
  projectId: string,
  payload: {
    title: string
    kind: WritingDocumentKind
    outline?: string[]
    is_primary?: boolean
    is_output_product?: boolean
    output_format?: 'docx' | 'pdf' | 'pptx' | ''
    data_source_ids?: string[]
    print_profile?: string
    publication_status?: WritingPublicationStatus
    rules_version?: string
    data_version?: string
  }
) {
  return apiClient.post<WritingProjectDocument>(
    `/api/v3/writing/projects/${encodeURIComponent(projectId)}/documents`,
    payload
  ).then(r => r.data)
}

export function updateWritingDocument(
  projectId: string,
  documentId: string,
  payload: Partial<Pick<
    WritingProjectDocument,
    | 'title'
    | 'status'
    | 'sort_order'
    | 'is_primary'
    | 'is_output_product'
    | 'output_format'
    | 'data_source_ids'
    | 'print_profile'
    | 'publication_status'
    | 'rules_version'
    | 'data_version'
  >>
) {
  return apiClient.patch<WritingProjectDocument>(
    `/api/v3/writing/projects/${encodeURIComponent(projectId)}/documents/${encodeURIComponent(documentId)}`,
    payload
  ).then(r => r.data)
}

export function deleteWritingDocument(projectId: string, documentId: string) {
  return apiClient.delete(
    `/api/v3/writing/projects/${encodeURIComponent(projectId)}/documents/${encodeURIComponent(documentId)}`
  )
}

export function reorderWritingDocuments(projectId: string, documentIds: string[]) {
  return apiClient.patch<{ documents: WritingProjectDocument[] }>(
    `/api/v3/writing/projects/${encodeURIComponent(projectId)}/documents-order`,
    { document_ids: documentIds }
  ).then(r => r.data)
}

export function replaceWritingDocumentContent(projectId: string, documentId: string, file: File) {
  const form = new FormData()
  form.append('file', file)
  return apiClient.post<WritingProjectDocument>(
    `/api/v3/writing/projects/${encodeURIComponent(projectId)}/documents/${encodeURIComponent(documentId)}/content`,
    form,
    { params: { actor: 'admin' }, timeout: 240000 }
  ).then(r => r.data)
}

function documentBase(projectId: string, documentId: string) {
  return `/api/v3/writing/projects/${encodeURIComponent(projectId)}/documents/${encodeURIComponent(documentId)}`
}

function collaborationBase(projectId: string, documentId: string) {
  return `${documentBase(projectId, documentId)}/collaboration`
}

function writingProjectBase(projectId: string) {
  return `/api/v3/writing/projects/${encodeURIComponent(projectId)}`
}

function aiConversationBase(projectId: string, conversationId = '') {
  const base = `${writingProjectBase(projectId)}/ai-conversations`
  return conversationId ? `${base}/${encodeURIComponent(conversationId)}` : base
}

export function getWritingWorkbenchPreference(projectId: string) {
  return apiClient.get<WritingWorkbenchPreference>(
    `${writingProjectBase(projectId)}/workbench-preference`
  ).then(r => r.data)
}

export function updateWritingWorkbenchPreference(
  projectId: string,
  payload: WritingWorkbenchPreferenceUpdate
) {
  return apiClient.patch<WritingWorkbenchPreference>(
    `${writingProjectBase(projectId)}/workbench-preference`,
    payload
  ).then(r => r.data)
}

function diagramBase(projectId: string, diagramId = '') {
  const base = `${writingProjectBase(projectId)}/diagrams`
  return diagramId ? `${base}/${encodeURIComponent(diagramId)}` : base
}

export function getWritingDiagrams(projectId: string) {
  return apiClient.get<{ diagrams: Array<WritingProjectDocument & { diagram?: DiagramDocumentState }> }>(
    diagramBase(projectId)
  ).then(r => r.data)
}

export function createWritingDiagram(
  projectId: string,
  payload: {
    title: string
    template_id?: string
    diagram_type?: string
    theme_id?: string
    page_settings?: Record<string, any>
    cells?: DiagramCell[]
  }
) {
  return apiClient.post<DiagramResource>(diagramBase(projectId), payload).then(r => r.data)
}

export function getWritingDiagram(projectId: string, diagramId: string) {
  return apiClient.get<DiagramResource>(diagramBase(projectId, diagramId)).then(r => r.data)
}

export function updateWritingDiagramDraft(
  projectId: string,
  diagramId: string,
  payload: Partial<DiagramDocumentState> & { expected_revision: number; cells: DiagramCell[] }
) {
  return apiClient.patch<DiagramDocumentState>(`${diagramBase(projectId, diagramId)}/draft`, payload).then(r => r.data)
}

export function createWritingDiagramVersion(
  projectId: string,
  diagramId: string,
  payload: { label?: string; reason?: string } = {}
) {
  return apiClient.post(`${diagramBase(projectId, diagramId)}/versions`, payload).then(r => r.data)
}

export function exportWritingDiagram(
  projectId: string,
  diagramId: string,
  format: 'svg' | 'png' | 'pdf' | 'json'
) {
  return apiClient.post<Blob>(`${diagramBase(projectId, diagramId)}/exports`, { format }, {
    responseType: 'blob',
    timeout: 120000
  }).then(r => r.data)
}

export function createWritingDiagramAiJob(
  projectId: string,
  diagramId: string,
  payload: { client_request_id?: string; agent_id?: string; instruction: string; target_cell_ids?: string[] }
) {
  return apiClient.post<DiagramAiJob>(`${diagramBase(projectId, diagramId)}/ai-jobs`, payload, {
    timeout: 120000
  }).then(r => r.data)
}

export function acceptWritingDiagramProposal(projectId: string, diagramId: string, proposalId: string) {
  return apiClient.post<{ proposal: DiagramAiProposal; diagram: DiagramDocumentState }>(
    `${diagramBase(projectId, diagramId)}/proposals/${encodeURIComponent(proposalId)}/accept`
  ).then(r => r.data)
}

export function rejectWritingDiagramProposal(projectId: string, diagramId: string, proposalId: string) {
  return apiClient.post<DiagramAiProposal>(
    `${diagramBase(projectId, diagramId)}/proposals/${encodeURIComponent(proposalId)}/reject`
  ).then(r => r.data)
}

export function getWritingDiagramReferences(projectId: string, diagramId: string) {
  return apiClient.get<{ references: DiagramReference[] }>(
    `${diagramBase(projectId, diagramId)}/references`
  ).then(r => r.data)
}

export function createWritingDiagramReference(
  projectId: string,
  diagramId: string,
  payload: {
    target_kind: 'rich_text' | 'presentation'
    target_document_id: string
    target_section_id?: string
    target_slide?: number
    export_format?: 'svg' | 'png'
    caption?: string
  }
) {
  return apiClient.post<DiagramReference>(`${diagramBase(projectId, diagramId)}/references`, payload).then(r => r.data)
}

export function publishWritingDiagramToDocument(
  projectId: string,
  diagramId: string,
  payload: {
    target_document_id: string
    target_section_id?: string
    expected_document_revision: number
    expected_diagram_revision: number
    anchor_block_id: string
    replace_block_ids?: string[]
    figure_label?: string
    caption?: string
    width?: string
    export_format?: 'svg' | 'png'
    client_change_id?: string
  }
) {
  return apiClient.post<DiagramDocumentPublishResult>(
    `${diagramBase(projectId, diagramId)}/publish-to-document`,
    payload
  ).then(r => r.data)
}

export function compareWritingDocuments(
  projectId: string,
  payload: {
    left_document_id: string
    right_document_id: string
    left_revision?: number
    right_revision?: number
    section_key?: string
  }
) {
  return apiClient.post<WritingDocumentComparison>(
    `${writingProjectBase(projectId)}/document-comparisons`,
    payload
  ).then(r => r.data)
}

export function getWritingAiConversations(projectId: string) {
  return apiClient.get<WritingAiConversation[]>(aiConversationBase(projectId)).then(r => r.data)
}

export function createWritingAiConversation(
  projectId: string,
  payload: { title?: string; agent_id?: string } = {}
) {
  return apiClient.post<WritingAiConversation>(aiConversationBase(projectId), payload).then(r => r.data)
}

export function getWritingAiConversationMessages(projectId: string, conversationId: string) {
  return apiClient.get<WritingAiMessage[]>(
    `${aiConversationBase(projectId, conversationId)}/messages`
  ).then(r => r.data)
}

export function createWritingAiConversationMessage(
  projectId: string,
  conversationId: string,
  payload: WritingAiConversationMessageCreate
) {
  return apiClient.post<WritingAiConversationMessageResult>(
    `${aiConversationBase(projectId, conversationId)}/messages`,
    payload,
    { timeout: 120000 }
  ).then(r => r.data)
}

export function cancelWritingAiConversationMessage(
  projectId: string,
  conversationId: string,
  messageId: string
) {
  return apiClient.post<WritingAiMessage>(
    `${aiConversationBase(projectId, conversationId)}/messages/${encodeURIComponent(messageId)}/cancel`
  ).then(r => r.data)
}

export function getWritingCollaboration(projectId: string, documentId: string, sectionId = '') {
  return apiClient.get<WritingCollaborationState>(collaborationBase(projectId, documentId), {
    params: sectionId ? { section_id: sectionId } : undefined
  }).then(r => r.data)
}

export function initializeWritingCollaboration(projectId: string, documentId: string) {
  return apiClient.post<WritingCollaborationState>(
    `${collaborationBase(projectId, documentId)}/initialize`
  ).then(r => r.data)
}

export function patchWritingCollaborationDraft(
  projectId: string,
  documentId: string,
  payload: WritingDraftPatch
) {
  return apiClient.patch<WritingCollaborationState>(
    `${collaborationBase(projectId, documentId)}/draft`,
    payload
  ).then(r => r.data)
}

export function createWritingAiJob(projectId: string, documentId: string, payload: WritingAiJobCreate) {
  return apiClient.post<WritingAiJob>(`${documentBase(projectId, documentId)}/ai-jobs`, payload).then(r => r.data)
}

export function getWritingAiJob(projectId: string, documentId: string, jobId: string) {
  return apiClient.get<WritingAiJob>(
    `${documentBase(projectId, documentId)}/ai-jobs/${encodeURIComponent(jobId)}`
  ).then(r => r.data)
}

export function acceptWritingProposal(projectId: string, documentId: string, proposalId: string) {
  return apiClient.post<WritingCollaborationState>(
    `${documentBase(projectId, documentId)}/proposals/${encodeURIComponent(proposalId)}/accept`
  ).then(r => r.data)
}

export function rejectWritingProposal(projectId: string, documentId: string, proposalId: string) {
  return apiClient.post<WritingCollaborationState>(
    `${documentBase(projectId, documentId)}/proposals/${encodeURIComponent(proposalId)}/reject`
  ).then(r => r.data)
}

export function getWritingResearchWorkflow(projectId: string, documentId: string) {
  return apiClient.get<WritingResearchWorkflow>(
    `${documentBase(projectId, documentId)}/research-workflow`
  ).then(r => r.data)
}

export function getWritingLiteratureRuns(projectId: string, documentId: string) {
  return apiClient.get<WritingJarvisRun[]>(
    `${documentBase(projectId, documentId)}/literature-runs`
  ).then(r => r.data)
}

export function getWritingResearchIterations(projectId: string, documentId: string, runId = '') {
  return apiClient.get<WritingResearchIteration[]>(
    `${documentBase(projectId, documentId)}/research-iterations`,
    { params: runId ? { run_id: runId } : {} }
  ).then(r => r.data)
}

export function getWritingRetrievalRefs(projectId: string, documentId: string) {
  return apiClient.get<WritingRetrievalRef[]>(
    `${documentBase(projectId, documentId)}/retrieval-refs`,
    { params: { limit: 500 } }
  ).then(r => r.data)
}

export function createWritingLiteratureRun(
  projectId: string,
  documentId: string,
  payload: {
    base_revision: number
    idempotency_key: string
    scope_section_ids: string[]
    evaluator_version?: string
    max_results_per_query?: number
    source_whitelist?: string[]
    external_request_budget?: number
  }
) {
  return apiClient.post<WritingJarvisRun>(
    `${documentBase(projectId, documentId)}/literature-runs`,
    payload
  ).then(r => r.data)
}

export function createWritingClaim(
  projectId: string,
  documentId: string,
  payload: Pick<WritingClaim, 'claim_text' | 'claim_type' | 'minimum_evidence_level' | 'section_id' | 'block_id'> & {
    document_revision?: number
    research_matrix?: Record<string, any>
  }
) {
  return apiClient.post<WritingClaim>(`${documentBase(projectId, documentId)}/claims`, payload).then(r => r.data)
}

export function createWritingEvidenceRef(
  projectId: string,
  documentId: string,
  payload: Omit<WritingEvidenceRef, 'id' | 'immutable'> & { provenance?: Record<string, any> }
) {
  return apiClient.post<WritingEvidenceRef>(
    `${documentBase(projectId, documentId)}/evidence-refs`,
    payload
  ).then(r => r.data)
}

export function bindWritingEvidence(
  projectId: string,
  documentId: string,
  payload: { claim_id: string; evidence_ref_id: string; support_scope?: string }
) {
  return apiClient.post(
    `${documentBase(projectId, documentId)}/evidence-bindings`,
    payload
  ).then(r => r.data)
}

export function dispatchWritingEvidenceGap(
  projectId: string,
  documentId: string,
  gapId: string,
  payload: {
    research_matrix?: Record<string, any>
    execution_policy?: Record<string, any>
    idempotency_key?: string
    retry?: boolean
    retry_request_id?: string
  } = {}
) {
  return apiClient.post<WritingJarvisRun>(
    `${documentBase(projectId, documentId)}/evidence-gaps/${encodeURIComponent(gapId)}/dispatch`,
    payload
  ).then(r => r.data)
}

export function decideWritingChangeSet(
  projectId: string,
  documentId: string,
  changeSetId: string,
  decision: 'approve' | 'reject',
  comment = ''
) {
  return apiClient.post<WritingChangeSet>(
    `${documentBase(projectId, documentId)}/change-sets/${encodeURIComponent(changeSetId)}/decision`,
    { decision, comment }
  ).then(r => r.data)
}

export function decideWritingJarvisRun(
  projectId: string,
  documentId: string,
  runId: string,
  decision: 'approve' | 'reject',
  comment = ''
) {
  return apiClient.post<WritingJarvisRun>(
    `${documentBase(projectId, documentId)}/jarvis-runs/${encodeURIComponent(runId)}/decision`,
    { decision, comment }
  ).then(r => r.data)
}

export function approveWritingRevision(projectId: string, documentId: string, revision: number) {
  return apiClient.post<{ document_revision: number; approved_revision: number }>(
    `${documentBase(projectId, documentId)}/revisions/${revision}/approval`
  ).then(r => r.data)
}

export function createWritingVersion(
  projectId: string,
  documentId: string,
  payload: { name?: string; message?: string; revision?: number } = {}
) {
  return apiClient.post<{ name?: string; revision?: number; created_at?: string }>(
    `${documentBase(projectId, documentId)}/versions`,
    payload
  ).then(r => r.data)
}

export function getDocumentWritingWorkspace(projectId: string, documentId: string) {
  return apiClient.get<WritingWorkspace>(`${documentBase(projectId, documentId)}/workspace`).then(r => r.data)
}

export function getDocumentWritingSection(projectId: string, documentId: string, sectionId: string) {
  return apiClient.get<WritingSection>(
    `${documentBase(projectId, documentId)}/sections/${encodeURIComponent(sectionId)}`
  ).then(r => r.data)
}

export function getDocumentWritingFulltext(projectId: string, documentId: string) {
  return apiClient.get<{ content: string; version: number; asset_paths: string[] }>(
    `${documentBase(projectId, documentId)}/fulltext`
  ).then(r => r.data)
}

export function updateDocumentWritingSection(
  projectId: string,
  documentId: string,
  sectionId: string,
  payload: { content: string; expected_version: number; actor?: string }
) {
  return apiClient.put<WritingSection>(
    `${documentBase(projectId, documentId)}/sections/${encodeURIComponent(sectionId)}`,
    payload
  ).then(r => r.data)
}

export function getDocumentWritingReferences(projectId: string, documentId: string) {
  return apiClient.get<{
    formal: WritingReference[]
    knowledge: WritingReference[]
    section_coverage: WritingReferenceCoverage[]
    summary: WritingWorkspace['reference_summary']
  }>(`${documentBase(projectId, documentId)}/references`).then(r => r.data)
}

export function getDocumentWritingGraph(projectId: string, documentId: string) {
  return apiClient.get<{
    nodes: WritingGraphNode[]
    edges: WritingGraphEdge[]
    summary: { sections: number; concepts: number; claims: number; relations: number }
  }>(`${documentBase(projectId, documentId)}/graph`).then(r => r.data)
}

export function getDocumentWritingQuality(projectId: string, documentId: string) {
  return apiClient.get<{
    summary: WritingQualitySummary
    issues: Array<{ severity: string; type: string; message: string }>
  }>(`${documentBase(projectId, documentId)}/quality`).then(r => r.data)
}

export function getDocumentContentFidelity(projectId: string, documentId: string) {
  return apiClient.get<DocumentContentFidelityReport>(
    `${documentBase(projectId, documentId)}/fidelity`
  ).then(r => r.data)
}

export function auditDocumentContentFidelity(projectId: string, documentId: string) {
  return apiClient.post<DocumentContentFidelityReport>(
    `${documentBase(projectId, documentId)}/fidelity/audit`
  ).then(r => r.data)
}

export function migrateDocumentContentFidelity(projectId: string, documentId: string) {
  return apiClient.post<DocumentContentFidelityReport>(
    `${documentBase(projectId, documentId)}/fidelity/migrate`
  ).then(r => r.data)
}

export function getDocumentFidelityPreview(projectId: string, documentId: string) {
  return apiClient.get<Blob>(
    `${documentBase(projectId, documentId)}/fidelity/preview.pdf`,
    { responseType: 'blob', timeout: 240000 }
  ).then(r => r.data)
}

export function getEvaluationProfiles() {
  return apiClient.get<{
    schema: string
    profiles: Array<{
      id: string
      name: string
      version: string
      kind: WritingDocumentKind
      document_types: string[]
      pass_threshold: number
      dimension_count: number
      gate_count: number
    }>
  }>('/api/v3/writing/evaluation/profiles').then(r => r.data)
}

export function getDocumentEvaluationProfile(projectId: string, documentId: string) {
  return apiClient.get<DocumentEvaluationProfile>(
    `${documentBase(projectId, documentId)}/evaluation/profile`
  ).then(r => r.data)
}

export function updateDocumentEvaluationProfile(
  projectId: string,
  documentId: string,
  payload: {
    profile_id: string
    overrides: {
      pass_threshold?: number
      dimension_weights?: Record<string, number>
      dimension_min_scores?: Record<string, number>
      gate_required?: Record<string, boolean>
      custom_gates?: Array<Record<string, any>>
    }
    actor?: string
  }
) {
  return apiClient.put<DocumentEvaluationProfile>(
    `${documentBase(projectId, documentId)}/evaluation/profile`,
    payload
  ).then(r => r.data)
}

export function getDocumentEvaluation(projectId: string, documentId: string) {
  return apiClient.get<DocumentEvaluationReport>(
    `${documentBase(projectId, documentId)}/evaluation`
  ).then(r => r.data)
}

export function getDocumentEvaluationHistory(projectId: string, documentId: string) {
  return apiClient.get<{ reports: Array<Partial<DocumentEvaluationReport>> }>(
    `${documentBase(projectId, documentId)}/evaluation/history`
  ).then(r => r.data)
}

export function runDocumentEvaluation(
  projectId: string,
  documentId: string,
  mode: 'technical' | 'full'
) {
  return apiClient.post<{
    mode?: 'technical'
    report: DocumentEvaluationReport
    job?: DocumentEvaluationJob
  }>(
    `${documentBase(projectId, documentId)}/evaluation/run`,
    { mode },
    { timeout: 120000 }
  ).then(r => r.data)
}

export function getDocumentEvaluationJob(
  projectId: string,
  documentId: string,
  jobId: string
) {
  return apiClient.get<DocumentEvaluationJob | null>(
    `${documentBase(projectId, documentId)}/evaluation/jobs/${encodeURIComponent(jobId)}`
  ).then(r => r.data)
}

export function confirmDocumentEvaluation(
  projectId: string,
  documentId: string,
  payload: {
    dimension_scores: Record<string, number>
    gate_statuses: Record<string, 'pass' | 'fail' | 'not_applicable'>
    comment: string
    actor?: string
  }
) {
  return apiClient.post<DocumentEvaluationReport>(
    `${documentBase(projectId, documentId)}/evaluation/confirm`,
    payload
  ).then(r => r.data)
}

export function getLinkedDocumentEvaluationSummary(projectId: string) {
  return apiClient.get<LinkedDocumentEvaluationSummary>(
    `/api/v3/writing/projects/${encodeURIComponent(projectId)}/evaluation/linked-summary`
  ).then(r => r.data)
}

export function getDocumentWritingVersions(projectId: string, documentId: string) {
  return apiClient.get<{ versions: Array<{ name: string; size_bytes: number; created_at: string; current?: boolean }> }>(
    `${documentBase(projectId, documentId)}/versions`
  ).then(r => r.data)
}

export function restoreWritingDocumentVersion(projectId: string, documentId: string, versionName: string) {
  return apiClient.post<WritingProjectDocument>(
    `${documentBase(projectId, documentId)}/versions/${encodeURIComponent(versionName)}/restore`,
    { actor: 'admin' },
    { timeout: 240000 }
  ).then(r => r.data)
}

export function getDocumentWritingAsset(projectId: string, documentId: string, path: string) {
  return apiClient.get<Blob>(`${documentBase(projectId, documentId)}/assets`, {
    params: { path },
    responseType: 'blob',
    suppressErrorToast: true
  }).then(r => r.data)
}

export function uploadDocumentWritingAsset(projectId: string, documentId: string, file: File) {
  const form = new FormData()
  form.append('file', file)
  return apiClient.post<WritingAssetUploadResult>(
    `${documentBase(projectId, documentId)}/assets`,
    form,
    {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000
    }
  ).then(r => r.data)
}

export function getDocumentWritingSourceWord(projectId: string, documentId: string) {
  return apiClient.get<Blob>(`${documentBase(projectId, documentId)}/source-word`, {
    responseType: 'blob'
  }).then(r => r.data)
}

export function exportProjectWritingDocument(
  projectId: string,
  documentId: string,
  format: 'docx' | 'pdf',
  releaseMode: 'candidate' | 'formal' = 'candidate'
) {
  return apiClient.post<Blob>(`${documentBase(projectId, documentId)}/export`, {
    format,
    release_mode: releaseMode
  }, {
    responseType: 'blob',
    timeout: 240000
  }).then(r => r.data)
}

export function getDocumentLayout(projectId: string, documentId: string) {
  return apiClient.get<DocumentLayoutState>(`${documentBase(projectId, documentId)}/layout`).then(r => r.data)
}

export function updateDocumentLayout(
  projectId: string,
  documentId: string,
  payload: { profile_id?: string; layout_revision?: string; cover?: Record<string, string> }
) {
  return apiClient.patch<DocumentLayoutState>(`${documentBase(projectId, documentId)}/layout`, payload).then(r => r.data)
}

export function uploadDocumentLayoutReference(
  projectId: string,
  documentId: string,
  file: File,
  profileName = ''
) {
  const form = new FormData()
  form.append('file', file)
  return apiClient.post<DocumentLayoutState>(
    `${documentBase(projectId, documentId)}/layout/reference-docx`,
    form,
    {
      params: profileName ? { profile_name: profileName } : undefined,
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000
    }
  ).then(r => r.data)
}

export function getDocumentLayoutSample(projectId: string, documentId: string, format: 'docx' | 'pdf') {
  return apiClient.get<Blob>(`${documentBase(projectId, documentId)}/layout/sample/${format}`, {
    responseType: 'blob'
  }).then(r => r.data)
}

export function getDocumentLayoutTemplatePreview(
  projectId: string,
  documentId: string,
  profileId: string,
  format: 'docx' | 'pdf' | 'png',
  page?: number
) {
  return apiClient.get<Blob>(`${documentBase(projectId, documentId)}/layout/templates/${encodeURIComponent(profileId)}/preview/${format}`, {
    params: page ? { page } : undefined,
    responseType: 'blob'
  }).then(r => r.data)
}

export function getDocumentLayoutDelivery(projectId: string, documentId: string, format: 'docx' | 'pdf') {
  return apiClient.get<Blob>(`${documentBase(projectId, documentId)}/layout/delivery/${format}`, {
    responseType: 'blob'
  }).then(r => r.data)
}

export function exportWritingProjectPackage(projectId: string) {
  return apiClient.post<Blob>(
    `/api/v3/writing/projects/${encodeURIComponent(projectId)}/export-package`,
    {},
    {
      responseType: 'blob',
      timeout: 300000
    }
  ).then(r => r.data)
}

export function getCourseProductionStatus(projectId: string) {
  return apiClient.get<CourseProductionStatus>(
    `/api/v3/writing/projects/${encodeURIComponent(projectId)}/production-status`
  ).then(r => r.data)
}

export function applyCourseProductTemplate(projectId: string, dryRun = false) {
  return apiClient.post<{
    dry_run: boolean
    summary: { total: number; create: number; update: number }
    course_profile?: CourseProfile
  }>(
    `/api/v3/writing/projects/${encodeURIComponent(projectId)}/course-template/apply`,
    { dry_run: dryRun }
  ).then(r => r.data)
}

export function applyCourseWorkPlan(projectId: string, dryRun = false) {
  return apiClient.post<{
    dry_run: boolean
    summary: {
      total: number
      create: number
      update: number
      points_added: number
    }
    work_plan?: CourseProductionStatus['work_plan']
  }>(
    `/api/v3/writing/projects/${encodeURIComponent(projectId)}/course-work-plan/apply`,
    { dry_run: dryRun }
  ).then(r => r.data)
}

export function runCourseIteration(
  projectId: string,
  options: {
    rounds: number
    parallelism: number
    dry_run?: boolean
  }
) {
  return apiClient.post<{
    dry_run: boolean
    iteration: {
      iteration_start: number
      iteration_end: number
      requested_rounds: number
      actual_rounds: number
      parallelism: number
      point_count: number
    }
    selected_points: Array<{
      id: string
      title: string
      task_id: string
      task_title: string
      assigned_agent: string
      iteration: number
    }>
    mission?: {
      id: string
      status: string
      approval_status: string
    }
    work_plan?: CourseWorkPlan
  }>(
    `/api/v3/writing/projects/${encodeURIComponent(projectId)}/course-iterations/run`,
    options
  ).then(r => r.data)
}

export function reviewCoursePoint(
  projectId: string,
  pointId: string,
  decision: 'approve' | 'reject' | 'retry',
  comment = ''
) {
  return apiClient.post<{
    decision: string
    point: CourseWorkPoint
    work_plan: CourseWorkPlan
  }>(
    `/api/v3/writing/projects/${encodeURIComponent(projectId)}/course-points/${encodeURIComponent(pointId)}/review`,
    { decision, comment }
  ).then(r => r.data)
}

export function updateCourseBaseline(projectId: string, profile: CourseProfile) {
  return apiClient.put<CourseProfile>(
    `/api/v3/writing/projects/${encodeURIComponent(projectId)}/course-baseline`,
    profile
  ).then(r => r.data)
}

export function importWritingDocx(
  projectId: string,
  file: File,
  options: {
    title: string
    product_type?: string
    course_unit_ids?: string[]
    quality_profile?: string
    required_for_release?: boolean
  }
) {
  const form = new FormData()
  form.append('file', file)
  return apiClient.post<WritingProjectDocument>(
    `/api/v3/writing/projects/${encodeURIComponent(projectId)}/documents/import-docx`,
    form,
    {
      params: {
        title: options.title,
        product_type: options.product_type || '',
        course_unit_ids: (options.course_unit_ids || []).join(','),
        quality_profile: options.quality_profile || '',
        required_for_release: Boolean(options.required_for_release)
      },
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 240000
    }
  ).then(r => r.data)
}

export function getWorkbookMetadata(projectId: string, documentId: string) {
  return apiClient.get<WorkbookMetadata>(`${documentBase(projectId, documentId)}/workbook`).then(r => r.data)
}

export function getWorkbookSheet(projectId: string, documentId: string, sheetName: string) {
  return apiClient.get<WorkbookSheet>(
    `${documentBase(projectId, documentId)}/workbook/sheets/${encodeURIComponent(sheetName)}`
  ).then(r => r.data)
}

export function updateWorkbookCells(
  projectId: string,
  documentId: string,
  sheetName: string,
  payload: { cells: Array<{ coordinate: string; value: any }>; expected_revision: number; actor?: string }
) {
  return apiClient.patch(
    `${documentBase(projectId, documentId)}/workbook/sheets/${encodeURIComponent(sheetName)}/cells`,
    payload,
    { timeout: 120000 }
  ).then(r => r.data)
}

export function getWritingDocumentSource(projectId: string, documentId: string) {
  return apiClient.get<Blob>(`${documentBase(projectId, documentId)}/source`, {
    responseType: 'blob'
  }).then(r => r.data)
}

export function getPresentationPreview(projectId: string, documentId: string) {
  return apiClient.get<Blob>(`${documentBase(projectId, documentId)}/presentation/preview`, {
    responseType: 'blob',
    timeout: 240000
  }).then(r => r.data)
}

export function getPresentationManifest(projectId: string, documentId: string) {
  return apiClient.get<PresentationManifest>(
    `${documentBase(projectId, documentId)}/presentation/manifest`
  ).then(r => r.data)
}

export function createPresentationSlideProposal(
  projectId: string,
  documentId: string,
  payload: {
    slide: number
    instruction: string
    agent_id?: string
    client_request_id?: string
    draft: Record<string, any>
  }
) {
  return apiClient.post<PresentationSlideProposal>(
    `${documentBase(projectId, documentId)}/presentation/slide-proposals`,
    payload,
    { timeout: 120000 }
  ).then(r => r.data)
}

export function createPresentationSlideJob(
  projectId: string,
  documentId: string,
  payload: {
    slide: number
    instruction: string
    agent_id?: string
    client_request_id?: string
    draft: Record<string, any>
  }
) {
  return apiClient.post<PresentationSlideJob>(
    `${documentBase(projectId, documentId)}/presentation/slide-jobs`,
    payload,
    { timeout: 120000 }
  ).then(r => r.data)
}

export function getPresentationSlideJob(projectId: string, documentId: string, jobId: string) {
  return apiClient.get<PresentationSlideJob>(
    `${documentBase(projectId, documentId)}/presentation/slide-jobs/${encodeURIComponent(jobId)}`
  ).then(r => r.data)
}

export function getDocumentStructureBinding(projectId: string, documentId: string) {
  return apiClient.get<DocumentStructureBinding>(
    `${documentBase(projectId, documentId)}/structure-binding`
  ).then(r => r.data)
}

export function updateDocumentStructureBinding(
  projectId: string,
  documentId: string,
  payload: DocumentStructureBinding & { manifest?: Record<string, any> }
) {
  return apiClient.put<DocumentStructureBinding>(
    `${documentBase(projectId, documentId)}/structure-binding`,
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

export function exportWritingDocument(
  projectId: string,
  format: 'docx' | 'pdf',
  releaseMode: 'candidate' | 'formal' = 'candidate'
) {
  return apiClient.post<Blob>(`/api/v3/writing/projects/${encodeURIComponent(projectId)}/export`, {
    format,
    release_mode: releaseMode
  }, {
    responseType: 'blob',
    timeout: 240000
  }).then(r => r.data)
}
