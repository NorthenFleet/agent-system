import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  approveCommandCenterMission: vi.fn(), approveCommandCenterCompensation: vi.fn(),
  approveCommandCenterStep: vi.fn(), approveCommandCenterMemoryCandidate: vi.fn(),
  cancelCommandCenterMission: vi.fn(), createCommandCenterMission: vi.fn(),
  getCommandCenterAgentSpace: vi.fn(), getCommandCenterMission: vi.fn(),
  getCommandCenterProductionHealth: vi.fn(), getCommandCenterSummary: vi.fn(), listCommandCenterMessages: vi.fn(),
  listCommandCenterMemoryCandidates: vi.fn(), listCommandCenterMissions: vi.fn(),
  listCommandCenterTaskWorkbench: vi.fn(), rejectCommandCenterMemoryCandidate: vi.fn(),
  rejectCommandCenterMission: vi.fn(), rejectCommandCenterCompensation: vi.fn(),
  rejectCommandCenterStep: vi.fn(), sendCommandCenterFeedback: vi.fn()
}))

vi.mock('@/api/commandCenter', () => api)
vi.mock('@/api/projects', () => ({
  getProjects: vi.fn().mockResolvedValue({ projects: [{ id: 'project-1', name: '生产系统', project_type: 'software', status: 'active' }] })
}))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ isAdmin: true }) }))

import CommandCenter from '@/views/CommandCenter.vue'

const mission = {
  id: 'mission-12345678', title: '生产配置发布', objective: '受控发布并验证健康状态',
  status: 'waiting_feedback', priority: 'high', project_id: 'project-1', mission_type: 'software',
  plan_version: 3, approval_status: 'approved', created_at: '2026-09-16T00:00:00Z', updated_at: '2026-09-16T00:10:00Z',
  mission_run: { id: 'mrun-1234567890', mission_id: 'mission-12345678', correlation_id: 'mission-trace-123456', status: 'waiting_feedback', active_plan_version: 3, created_at: '2026-09-16T00:00:00Z', updated_at: '2026-09-16T00:10:00Z' },
  planning_context: { id: 'binding-1', mission_id: 'mission-12345678', plan_version: 3, step_id: '', purpose: 'planning', agent_id: 'optimus', context_pack_version: 1, status: 'ready', item_count: 3, citation_count: 2, source_types: ['project'], citations: [], created_at: '2026-09-16T00:00:00Z', updated_at: '2026-09-16T00:00:00Z' },
  plan: { summary: '先备份再发布', risk_level: 'high', plan_quality: { status: 'pass', score: 96, blockers: [], warnings: [], suggestions: [], checked_rules: ['dependencies'] } },
  approval: { decision: 'approved' },
  steps: [{
    id: 'step-1', mission_id: 'mission-12345678', order_index: 1, phase: 'release', title: '更新生产配置', description: '使用受控配置进行发布',
    task_type: 'operations', agent_id: 'optimus', executor: 'openclaw', status: 'failed', dependencies: [],
    risk_class: 'L3', side_effect: true, resources: ['production-config'], idempotency_key: 'mission:step:1', rollback_plan: '恢复上一版配置',
    required_tools: ['deployment'], deliverables: ['发布回执'], acceptance_criteria: ['健康检查通过'], evidence_required: ['healthcheck'],
    artifacts: [{ id: 'artifact-1', step_id: 'step-1', artifact_type: 'log', title: '发布日志', uri: 'artifact://release', created_at: '2026-09-16T00:08:00Z' }],
    evidence: [{ id: 'evidence-1', step_id: 'step-1', evidence_type: 'healthcheck', source_ref: 'health://failed', summary: '健康检查失败', collected_by: 'optimus', collected_at: '2026-09-16T00:09:00Z', confidence: 1 }],
    acceptance_gate: { id: 'gate-step', step_id: 'step-1', gate_type: 'execution_evidence', mode: 'strict', enforced: true, status: 'blocked', accepted: false, score: 45, blockers: ['健康检查未通过'], warnings: [], evaluated_by: 'command-center', evaluated_at: '2026-09-16T00:09:00Z' },
    effects: [{ id: 'effect-1', step_id: 'step-1', effect_key: 'config-update', resource: 'production-config', action: '更新配置', status: 'applied', idempotency_key: 'mission:step:1', receipt_ref: 'ops:1', evidence_refs: ['health://failed'] }],
    compensations: [{ id: 'comp-1', mission_id: 'mission-12345678', plan_version: 3, step_id: 'step-1', effect_id: 'effect-1', compensation_type: 'restore', instructions: '恢复上一版配置', resource: 'production-config', contract_hash: 'abcdef1234567890', idempotency_key: 'compensate:mission:step:1', status: 'pending_approval', attempts: 0 }],
    result: { error: '健康检查失败' }
  }],
  artifacts: [{ id: 'artifact-1', step_id: 'step-1', artifact_type: 'log', title: '发布日志', uri: 'artifact://release', created_at: '2026-09-16T00:08:00Z' }],
  evidence: [{ id: 'evidence-1', step_id: 'step-1', evidence_type: 'healthcheck', source_ref: 'health://failed', summary: '健康检查失败', collected_by: 'optimus', collected_at: '2026-09-16T00:09:00Z', confidence: 1 }],
  acceptance_gates: [{ id: 'gate-step', step_id: 'step-1', gate_type: 'execution_evidence', mode: 'strict', enforced: true, status: 'blocked', accepted: false, score: 45, blockers: ['健康检查未通过'], warnings: [], evaluated_by: 'command-center', evaluated_at: '2026-09-16T00:09:00Z' }],
  effects: [{ id: 'effect-1', step_id: 'step-1', effect_key: 'config-update', resource: 'production-config', action: '更新配置', status: 'applied', idempotency_key: 'mission:step:1', receipt_ref: 'ops:1', evidence_refs: ['health://failed'] }],
  compensations: [{ id: 'comp-1', mission_id: 'mission-12345678', plan_version: 3, step_id: 'step-1', effect_id: 'effect-1', compensation_type: 'restore', instructions: '恢复上一版配置', resource: 'production-config', contract_hash: 'abcdef1234567890', idempotency_key: 'compensate:mission:step:1', status: 'pending_approval', attempts: 0 }],
  delivery_gate: { id: 'gate-delivery', step_id: '', gate_type: 'delivery_evidence', mode: 'strict', enforced: true, status: 'blocked', accepted: false, score: 40, blockers: ['存在未解决补偿'], warnings: [], evaluated_by: 'command-center', evaluated_at: '2026-09-16T00:10:00Z' },
  events: []
}

describe('Command Center governance presentation', () => {
  afterEach(() => vi.clearAllMocks())

  it('renders lifecycle, control point, evidence gate, effect journal and compensation', async () => {
    api.getCommandCenterSummary.mockResolvedValue({ total: 1, active: 1, pending_approvals: 0, pending_step_approvals: 0, pending_compensations: 1, outbox_pending: 0, context_ready: 1, context_degraded: 0, context_by_status: {}, discussion_count: 0, clarification_pending: 0, routed_by_intent: {}, memory_candidates: { total: 0, pending_review: 0, published: 0, rejected: 0, by_status: {} }, by_status: {} })
    api.getCommandCenterProductionHealth.mockResolvedValue({ status: 'ready', storage: { backend: 'postgresql', source_of_truth: 'postgresql:///team_dashboard', capabilities: { multi_instance: true } }, storage_runtime: { backend: 'postgresql', connection_mode: 'threaded_pool', pool: { min_size: 1, max_size: 10, in_use: 1, peak_in_use: 4, acquire_timeouts_total: 0, connection_failures_total: 0, acquire_wait_ms_average: 2, acquire_wait_ms_max: 8 } }, work_runs: { backend: 'postgresql', total: 24, active: 1, expired_active_leases: 0, retry_attempts: 2, failed: 0, lease_reclaims: 1 }, workflow_runtime: { checkpoint_storage: { status: 'ready', backend: 'postgresql', installed_version: 9, required_version: 9, runtime_ddl: false } }, workers: { status: 'ready', required: 2, live: 2, stale: 0, stale_after_seconds: 20, workers: [] } })
    api.listCommandCenterTaskWorkbench.mockResolvedValue({ items: [{ mission_id: mission.id, mission_title: mission.title, mission_status: mission.status, mission_type: 'software', project_id: 'project-1', project_name: '生产系统', objective: mission.objective, approval_status: 'approved', current_agent_id: 'optimus', current_agent_name: '擎天柱', active_step: mission.steps[0], steps_summary: { total: 1, completed: 0, running: 0, failed: 1, pending: 0 }, linked_tasks: [], progress: 40, updated_at: mission.updated_at, waiting_reason: '等待补偿' }], total: 1 })
    api.listCommandCenterMissions.mockResolvedValue({ missions: [mission], total: 1 })
    api.getCommandCenterMission.mockResolvedValue(mission)
    api.listCommandCenterMemoryCandidates.mockResolvedValue({ candidates: [], total: 0, can_review: true, summary: { total: 0, pending_review: 0, published: 0, rejected: 0, by_status: {} } })
    api.listCommandCenterMessages.mockResolvedValue({ messages: [], total: 0 })
    api.getCommandCenterAgentSpace.mockResolvedValue({ commander: 'optimus', single_entry: true, mission: { id: mission.id, title: mission.title, status: mission.status, progress: 40, active_step: mission.steps[0] }, nodes: [], edges: [], lanes: [], updated_at: mission.updated_at })

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/command-center', component: { template: '<div />' } }]
    })
    await router.push('/command-center')
    await router.isReady()
    const wrapper = mount(CommandCenter, { global: { plugins: [ElementPlus, router] } })
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('规范执行链')
    expect(text).toContain('存在未解决副作用')
    expect(text).toContain('任务接收')
    expect(text).toContain('交付闭环')
    expect(text).toContain('Effect Journal')
    expect(text).toContain('执行证据门禁')
    expect(text).toContain('最终交付门禁')
    expect(text).toContain('批准补偿')
    expect(text).toContain('生产运行门禁')
    expect(text).toContain('POSTGRESQL')
    expect(text).toContain('0 个过期')
    expect(wrapper.findAll('.lifecycle-stage')).toHaveLength(8)

    wrapper.unmount()
  })
})
