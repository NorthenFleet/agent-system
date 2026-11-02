import { describe, expect, it } from 'vitest'

import type { CommandCenterMission } from '@/api/commandCenter'
import { buildMissionLifecycle, deriveMissionControlPoint } from '@/utils/commandCenterLifecycle'

function mission(overrides: Partial<CommandCenterMission> = {}): CommandCenterMission {
  return {
    id: 'mission-12345678',
    title: '生产发布',
    objective: '安全发布新版本',
    status: 'running',
    priority: 'high',
    plan_version: 2,
    approval_status: 'approved',
    created_at: '2026-09-16T00:00:00Z',
    updated_at: '2026-09-16T00:10:00Z',
    plan: {
      summary: '受控发布',
      plan_quality: {
        status: 'pass',
        score: 96,
        blockers: [],
        warnings: [],
        suggestions: [],
        checked_rules: ['dependencies']
      }
    },
    approval: { decision: 'approved' },
    planning_context: {
      id: 'binding-1',
      mission_id: 'mission-12345678',
      plan_version: 2,
      step_id: '',
      purpose: 'planning',
      agent_id: 'optimus',
      context_pack_version: 1,
      status: 'ready',
      item_count: 4,
      citation_count: 3,
      source_types: ['project'],
      citations: [],
      created_at: '2026-09-16T00:00:00Z',
      updated_at: '2026-09-16T00:00:00Z'
    },
    steps: [
      {
        id: 'step-1', mission_id: 'mission-12345678', order_index: 1,
        title: '发布', task_type: 'operations', agent_id: 'optimus', executor: 'openclaw',
        status: 'running', dependencies: []
      }
    ],
    artifacts: [],
    evidence: [],
    acceptance_gates: [],
    effects: [],
    compensations: [],
    ...overrides
  }
}

describe('command center normalized lifecycle', () => {
  it('keeps evidence warnings visible on pilot completion', () => {
    const value = mission({ status: 'completed', steps: [{ ...mission().steps[0], status: 'completed', result: {
      execution_quality: { status: 'warning', score: 92,
        blockers: [], warnings: ['引用未闭合'], checked_rules: [], evidence_refs: [],
        required_tools: [], required_evidence: [] }
    } }] })
    const point = deriveMissionControlPoint(value)
    expect(point.tone).toBe('warning')
    expect(point.title).toContain('证据仍有警告')
    expect(point.description).toContain('不代表严格验收通过')
  })
  it('shows replanning instead of the retained failure from the previous plan', () => {
    const value = mission({ status: 'planning', steps: [{ ...mission().steps[0], status: 'failed' }] })
    expect(deriveMissionControlPoint(value).title).toBe('正在制定执行计划')
    expect(deriveMissionControlPoint(value).description).toContain('历史记录保留')
  })
  it('keeps cancellation terminal even when stale execution or approval details remain', () => {
    const point = deriveMissionControlPoint(mission({ status: 'cancelled' }))
    expect(point.title).toBe('任务已取消')
    expect(point.description).toContain('停止调度')
    expect(point.action).not.toContain('等待')
  })

  it('does not describe a failed mission as progressing', () => {
    expect(deriveMissionControlPoint(mission({ status: 'failed', steps: [], last_error: '验收异常' })).title).toBe('任务失败')
  })
  it('maps the backend state into the complete eight-stage lifecycle', () => {
    const stages = buildMissionLifecycle(mission())

    expect(stages).toHaveLength(8)
    expect(stages.map(stage => stage.id)).toEqual([
      'intake', 'context', 'planning', 'approval', 'execution', 'evidence', 'recovery', 'delivery'
    ])
    expect(stages.find(stage => stage.id === 'planning')?.state).toBe('completed')
    expect(stages.find(stage => stage.id === 'execution')?.state).toBe('active')
  })

  it('makes a pending high-risk approval the current control point', () => {
    const value = mission({
      steps: [{
        id: 'step-risk', mission_id: 'mission-12345678', order_index: 1,
        title: '更新生产配置', task_type: 'operations', agent_id: 'optimus', executor: 'openclaw',
        status: 'awaiting_approval', dependencies: [], resources: ['production-config'],
        step_approval: {
          id: 'approval-1', mission_id: 'mission-12345678', plan_version: 2, step_id: 'step-risk',
          request_version: 1, risk_class: 'L3', action_summary: '更新配置', contract_hash: 'hash',
          status: 'pending', requested_at: '2026-09-16T00:00:00Z', expires_at: '2026-09-16T00:30:00Z',
          consumed: false, single_use: true
        }
      }]
    })

    expect(deriveMissionControlPoint(value)).toMatchObject({
      tone: 'warning',
      title: '高风险步骤等待授权'
    })
    expect(buildMissionLifecycle(value).find(stage => stage.id === 'approval')?.state).toBe('active')
  })

  it('hard-blocks recovery and delivery visibility for unresolved compensation', () => {
    const value = mission({
      compensations: [{
        id: 'comp-1', mission_id: 'mission-12345678', plan_version: 2, step_id: 'step-1', effect_id: 'effect-1',
        compensation_type: 'restore', instructions: '恢复配置', resource: 'production-config',
        contract_hash: 'hash', idempotency_key: 'compensate:key', status: 'pending_approval', attempts: 0
      }]
    })

    expect(deriveMissionControlPoint(value)).toMatchObject({
      tone: 'danger',
      title: '存在未解决副作用'
    })
    expect(buildMissionLifecycle(value).find(stage => stage.id === 'recovery')?.state).toBe('blocked')
  })

  it('shows a completed delivery only when the mission is completed', () => {
    const value = mission({
      status: 'completed',
      steps: [{
        id: 'step-1', mission_id: 'mission-12345678', order_index: 1,
        title: '发布', task_type: 'operations', agent_id: 'optimus', executor: 'openclaw',
        status: 'completed', dependencies: []
      }]
    })

    expect(deriveMissionControlPoint(value).tone).toBe('success')
    expect(buildMissionLifecycle(value).find(stage => stage.id === 'delivery')?.state).toBe('completed')
  })
})


it('does not present partial pilot evidence as completed acceptance', () => {
  const value = mission({ status: 'waiting_feedback', acceptance_gates: [{
    id: 'gate', accepted: true, enforced: false, status: 'warning', warnings: ['缺少证据'], blockers: [],
  } as any] })
  expect(buildMissionLifecycle(value).find(stage => stage.id === 'evidence')?.state).toBe('warning')
  expect(deriveMissionControlPoint({ ...value, steps: [], last_error: '规划无法解析' }).description).toBe('规划无法解析')
})

it('distinguishes unapproved planning from final acceptance', () => {
  expect(deriveMissionControlPoint(mission({ status: 'planning', steps: [] })).description).toContain('尚未批准')
  expect(deriveMissionControlPoint(mission({ status: 'evaluating', steps: [] })).title).toBe('正在进行最终验收')
})
