import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessageBox } from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  downloadCommandCenterArtifact: vi.fn(), approveCommandCenterMission: vi.fn(), approveCommandCenterCompensation: vi.fn(),
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
    routing_decision: { mode: 'shadow', enforced: false, policy_version: 'dr-shadow-v1', phase: 'dispatch', action: 'delegate', reason_code: 'registered_agent_match', detail: '按已批准计划交给具备对应能力的 Agent', attempt: 2, actual_executor: 'openclaw', actual_agent_id: 'optimus' },
    result: { error: '健康检查失败', decision_shadow: { mode: 'shadow', enforced: false, policy_version: 'dr-shadow-v1', phase: 'completion', action: 'inspect', reason_code: 'effect_requires_inspection', detail: '先核验副作用和回执，再判断恢复方式', attempt: 2, actual_executor: 'openclaw', actual_agent_id: 'optimus', consecutive_failures: 2, repeated_failure: true } }
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
    expect(text).toContain('路由观察 · 仅建议，未接管执行')
    expect(text).toContain('实际执行：optimus / openclaw')
    expect(text).toContain('连续相同失败 2 次')
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

    api.sendCommandCenterFeedback.mockResolvedValue(mission)
    await wrapper.find('textarea[placeholder="补充范围、约束、凭据或处理意见"]').setValue('修订文档后重新复核')
    const replan = wrapper.findAll('button').find(button => button.text() === '反馈并重新规划')!
    await replan.trigger('click')
    await flushPromises()
    expect(api.sendCommandCenterFeedback).toHaveBeenCalledWith(mission.id, '修订文档后重新复核', true)

    const failed = JSON.parse(JSON.stringify(mission))
    failed.steps[0].executor = 'deterministic-v1'
    failed.steps[0].result.tool_control = { enforced: true, calls: 3, receipts: 2, denied: 0, incomplete: 1, unknown: 0, accepted: false }
    failed.steps[0].result.code_workspace = { workspace_status: 'candidate', execution_branch: 'codex/test-candidate', commit_sha: 'abc123', integrated: false }
    failed.steps[0].result.execution_profile = { role: 'worker', requested_model: 'provider/model', actual_model: null, usage: null, cost_usd: null }
    failed.advisor_reviews = [{ checkpoint: 'plan', status: 'completed', verdict: 'concerns', suggested_action: '补齐独立测试', findings: [{ message: '缺少独立测试', evidence_refs: ['step-1'] }] }]
    failed.steps[0].result.recovery_control = { enforced: true, requires_replan: true, reason_code: 'attempt_budget_exhausted' }
    for (const item of [...failed.compensations, ...failed.steps.flatMap((step: any) => step.compensations || [])]) {
      item.status = 'failed'
      item.compensation_type = 'manual_recovery'
    }
    api.getCommandCenterMission.mockResolvedValue(failed)
    await wrapper.findAll('button').find(button => button.text() === '刷新')!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('确定性检查 · 无模型调用')
    expect(wrapper.text()).toContain('隔离代码候选 · 尚未合并')
    expect(wrapper.text()).toContain('工具调用控制 · 未通过')
    expect(wrapper.text()).toContain('3 次调用 · 2 条回执 · 0 次拒绝 · 1 项待核验')
    expect(wrapper.text()).toContain('实际模型 回执未提供')
    expect(wrapper.text()).toContain('检查点顾问 · 仅建议，不代替审批与验收')
    expect(wrapper.text()).toContain('补齐独立测试')
    expect(wrapper.text()).toContain('受控修复 · 已停止原步骤重试')
    const retry = wrapper.findAll('button').find(button => button.text() === '重新审批补偿')!
    expect(retry).toBeTruthy()
    expect(api.approveCommandCenterCompensation).not.toHaveBeenCalled()
    const confirm = vi.spyOn(ElMessageBox, 'confirm').mockRejectedValueOnce('cancel')
    await retry.trigger('click')
    await flushPromises()
    expect(confirm.mock.calls[0][0]).toContain('上次失败不代表没有生效')
    expect(api.approveCommandCenterCompensation).not.toHaveBeenCalled()
    confirm.mockResolvedValueOnce('confirm')
    await retry.trigger('click')
    await flushPromises()
    expect(api.approveCommandCenterCompensation).toHaveBeenCalledWith(mission.id, expect.objectContaining({ contract_hash: 'abcdef1234567890', status: 'failed' }), '已确认当前补偿合同快照')
    for (const item of [...failed.compensations, ...failed.steps.flatMap((step: any) => step.compensations || [])]) {
      item.status = 'pending_approval'
      item.last_error = 'Interrupted compensation requires reapproval'
    }
    api.getCommandCenterMission.mockResolvedValue(JSON.parse(JSON.stringify(failed)))
    await wrapper.findAll('button').find(button => button.text() === '刷新')!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('实际操作可能已生效')
    api.approveCommandCenterCompensation.mockClear()
    confirm.mockRejectedValueOnce('cancel')
    await wrapper.findAll('button').find(button => button.text() === '批准补偿')!.trigger('click')
    await flushPromises()
    expect(confirm.mock.calls.at(-1)![0]).toContain('上次失败不代表没有生效')
    expect(api.approveCommandCenterCompensation).not.toHaveBeenCalled()
    confirm.mockRestore()
    // Download failures remain attached to the artifact; preparing a draft never submits it.
    api.downloadCommandCenterArtifact.mockRejectedValueOnce({ response: { status: 409, data: new Blob([JSON.stringify({ detail: '文件已变化，与该任务登记的版本不一致' })]) } })
    await wrapper.findAll('button').find(button => button.text() === '下载文件')!.trigger('click')
    await flushPromises()
    expect(wrapper.find('.artifact-download-error').text()).toContain('文件已变化')
    const draft = wrapper.findAll('button').find(button => button.text() === '准备重新交付任务')!
    Element.prototype.scrollIntoView = vi.fn()
    await draft.trigger('click')
    await flushPromises()
    expect(api.createCommandCenterMission).not.toHaveBeenCalled()
    const goal = wrapper.find('textarea[placeholder="描述目标、约束、期望结果和完成标准"]')
    expect((goal.element as HTMLTextAreaElement).value).toContain(mission.id)
    expect((goal.element as HTMLTextAreaElement).value).toContain('artifact-1')
    expect((goal.element as HTMLTextAreaElement).value).toContain('独立路径')
    expect(draft.attributes('disabled')).toBeDefined()
    await goal.setValue('用户编辑的草稿')
    await wrapper.findAll('button').find(button => button.text() === '刷新')!.trigger('click')
    await flushPromises()
    expect((goal.element as HTMLTextAreaElement).value).toBe('用户编辑的草稿')
    expect(wrapper.find('.artifact-download-error').exists()).toBe(true)
    URL.createObjectURL = vi.fn(() => 'blob:test')
    URL.revokeObjectURL = vi.fn()
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    api.downloadCommandCenterArtifact.mockResolvedValueOnce(new Blob(['valid']))
    await wrapper.findAll('button').find(button => button.text() === '下载文件')!.trigger('click')
    await flushPromises()
    expect(wrapper.find('.artifact-download-error').exists()).toBe(false)
    expect((goal.element as HTMLTextAreaElement).value).toBe('用户编辑的草稿')
    expect(api.createCommandCenterMission).not.toHaveBeenCalled()
    expect(anchorClick).toHaveBeenCalledOnce()
    anchorClick.mockRestore()
    wrapper.unmount()
  })
})
