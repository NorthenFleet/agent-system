import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  createMemoryEvaluationReviewBatch: vi.fn(),
  createMemoryEvaluationCase: vi.fn(),
  generateMemoryEvaluationDrafts: vi.fn(),
  generateMemoryEvaluationVariants: vi.fn(),
  getLatestMemoryRetrievalEvaluation: vi.fn(),
  getLatestMemoryEvaluationReviewBatch: vi.fn(),
  getMemoryEvaluationCaseEvents: vi.fn(),
  getMemoryEvaluationCoverage: vi.fn(),
  getMemoryEvaluationReviewQueue: vi.fn(),
  getMemoryRolloutGate: vi.fn(),
  listMemoryEvaluationCases: vi.fn(),
  runMemoryRetrievalEvaluation: vi.fn(),
  updateMemoryEvaluationCase: vi.fn()
}))

vi.mock('@/api/memoryEvaluation', () => api)

import MemoryEvaluation from '@/views/MemoryEvaluation.vue'

const draft = {
  id: 'memory-eval-draft-1', owner_user_id: '1', subject_user_id: '1',
  origin: 'approved_memory_draft', source_memory_ref: 'profile_fact:fact-1',
  variant_key: 'canonical',
  query: '发布前需要遵循什么规则？', project_id: '', agent_id: 'optimus', limit: 10,
  expected_source_refs: ['profile_fact:fact-1'], forbidden_source_refs: [], tags: ['auto-draft'],
  notes: '激活前须人工审核', status: 'draft', version: 1, reviewed_by: null, reviewed_at: null,
  review_checks: { query_rewritten: false, scope_verified: false, labels_verified: false },
  reviewer_confidence: 'unreviewed', source_snapshot_hash: '',
  created_at: '2026-09-17T00:00:00Z', updated_at: '2026-09-17T00:00:00Z'
}

const gate = {
  promotion_ready: false, recommended_action: 'keep_shadow', fusion_mode: 'shadow',
  online: {
    status: 'collecting', samples: { queries: 0, distinct_query_fingerprints: 0, minimum_required: 100, remaining: 100 },
    availability: { vector_ready_rate: 0, target: 0.99, by_status: {} },
    latency_ms: { total: { p95: 0, target_p95: 500 }, vector: { p95: 0, target_p95: 250 } },
    ranking_change: { top1_change_rate: 0, mean_topk_overlap_ratio: 0, mean_rank_displacement: 0 },
    rollout_gate: { online_observation_passed: false, promotion_ready: false, blockers: ['minimum_queries'] },
    privacy: { raw_query_stored: false, ranked_references_stored: false, retention_days: 30 }
  },
  offline: { active_cases: 0, minimum_required: 30, dataset_hash: '', checks: {}, latest_run: null },
  blockers: ['online:minimum_queries', 'offline:evaluation_exists', 'offline:minimum_labeled_cases'],
  automatic_switch_performed: false
}

describe('Memory retrieval evaluation workbench', () => {
  afterEach(() => vi.clearAllMocks())

  it('renders gate blockers and keeps generated cases as review drafts', async () => {
    api.listMemoryEvaluationCases.mockResolvedValue({ cases: [draft], total: 1 })
    api.getMemoryRolloutGate.mockResolvedValue(gate)
    api.getLatestMemoryRetrievalEvaluation.mockResolvedValue({ run: null })
    api.getMemoryEvaluationCoverage.mockResolvedValue({ approved_sources: 1, sources_with_cases: 1, sources_with_active_cases: 0, uncovered_source_refs: [], cases_total: 1, by_status: { draft: 1, active: 0, archived: 0 }, by_variant: { canonical: 1 }, by_confidence: { unreviewed: 1 }, review_ready_drafts: 0, safety_negative_cases: 0, active_safety_negative_cases: 0, source_drift_cases: 0, missing_source_cases: 0, audit_events: 1, minimum_active_cases: 30, remaining_active_cases: 30, automatic_activation: false })
    api.getMemoryEvaluationReviewQueue.mockResolvedValue({ sources: [{ source_ref: 'profile_fact:fact-1', source_type: 'profile_fact', title: '发布门禁', content: '发布前必须完成回归测试。', user_id: '1', project_id: '', agent_id: '', content_hash: 'hash-1', updated_at: '2026-09-17T00:00:00Z', case_count: 1, draft_count: 1, active_count: 0, safety_case_count: 0, stale_case_ids: [] }], source_count: 1, cases_total: 1, stale_case_ids: [], missing_case_ids: [], automatic_activation: false })
    api.getMemoryEvaluationCaseEvents.mockResolvedValue({ events: [{ id: 'event-1', case_id: draft.id, event_type: 'imported', from_status: '', to_status: 'draft', case_version: 1, actor: 'schema-migration', source_snapshot_hash: '', case_hash: 'case-hash', created_at: '2026-09-17T00:00:00Z' }], total: 1 })
    api.getLatestMemoryEvaluationReviewBatch.mockResolvedValue({ batch: { id: 'batch-1', name: '可信标注批次', target_case_count: 30, case_ids: [draft.id], review_plan: [{ order: 1, case_id: draft.id, source_memory_ref: draft.source_memory_ref, variant_key: 'canonical', suggested_forbidden_source_refs: ['project-memory:other'], suggestion_requires_human_verification: true, proposal: { suggested_query: '上线前要完成哪些发布审核？', suggested_forbidden_source_refs: ['project-memory:other'], rationale: '把内部标题改成真实业务问法。', proposed_by: 'assistant', proposed_at: '2026-09-18T01:00:00Z', proposal_hash: 'proposal-hash', status: 'pending_human_review' } }], proposal_count: 1, status: 'in_review', selected_cases: 30, active_cases: 0, archived_cases: 0, remaining_cases: 30, covered_approved_sources: 0, approved_sources: 1, active_safety_negative_cases: 0, checks: {}, blockers: ['target_active_cases'], by_variant: { canonical: 6, natural: 6, terse: 6, contextual: 6, boundary: 6 }, by_source: { [draft.source_memory_ref]: 5 }, next_case: draft, next_plan: null, requested_by: 'admin', created_at: '2026-09-18T00:00:00Z', updated_at: '2026-09-18T00:00:00Z', automatic_review: false, automatic_activation: false } })
    api.generateMemoryEvaluationDrafts.mockResolvedValue({ approved_memories_scanned: 1, drafts_created: 0, drafts_skipped: 1, automatic_activation: false })
    api.generateMemoryEvaluationVariants.mockResolvedValue({ approved_memories_scanned: 1, variants_per_memory: 4, drafts_created: 4, drafts_skipped: 0, automatic_activation: false })

    const wrapper = mount(MemoryEvaluation, { global: { plugins: [ElementPlus] } })
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('记忆检索评测')
    expect(text).toContain('BLOCKED')
    expect(text).toContain('0 / 100')
    expect(text).toContain('0 / 30')
    expect(text).toContain('在线样本不足')
    expect(text).toContain('发布前需要遵循什么规则？')
    expect(text).toContain('profile_fact:fact-1')
    expect(text).toContain('待审核')
    expect(text).toContain('标注覆盖度')
    expect(text).toContain('还需激活 30 条')
    expect(text).toContain('标准问法')
    expect(text).toContain('安全反例')
    expect(text).toContain('审计事件')
    expect(text).toContain('人工审核批次')
    expect(text).toContain('已激活 0 / 30')
    expect(text).toContain('AI提案 1 / 30')

    const generateButton = wrapper.findAll('button').find(button => button.text().includes('从权威记忆生成草稿'))
    expect(generateButton).toBeTruthy()
    await generateButton!.trigger('click')
    await flushPromises()

    expect(api.generateMemoryEvaluationDrafts).toHaveBeenCalledOnce()
    expect(api.listMemoryEvaluationCases).toHaveBeenCalledTimes(2)
    expect(api.runMemoryRetrievalEvaluation).not.toHaveBeenCalled()
    expect(api.updateMemoryEvaluationCase).not.toHaveBeenCalled()

    const variantButton = wrapper.findAll('button').find(button => button.text().includes('生成问法变体'))
    expect(variantButton).toBeTruthy()
    await variantButton!.trigger('click')
    await flushPromises()
    expect(api.generateMemoryEvaluationVariants).toHaveBeenCalledOnce()

    const reviewButton = wrapper.findAll('button').find(button => button.text().includes('审核下一条'))
    await reviewButton!.trigger('click')
    await flushPromises()
    expect(api.getMemoryEvaluationCaseEvents).toHaveBeenCalledWith(draft.id)
    expect(wrapper.text()).toContain('发布前必须完成回归测试。')
    expect(wrapper.text()).toContain('迁移建档')
    expect(wrapper.text()).toContain('安全反例建议')
    expect(wrapper.text()).toContain('project-memory:other')
    expect(wrapper.text()).toContain('AI改写提案')
    expect(wrapper.text()).toContain('上线前要完成哪些发布审核？')
    expect(wrapper.text()).toContain('待人工裁决，不属于正式标签')

    const applyProposalButton = wrapper.findAll('button').find(button => button.text().includes('应用到表单'))
    await applyProposalButton!.trigger('click')
    await flushPromises()
    expect((wrapper.find('textarea').element as HTMLTextAreaElement).value).toBe('上线前要完成哪些发布审核？')
    expect(api.updateMemoryEvaluationCase).not.toHaveBeenCalled()

    wrapper.unmount()
  })
})
