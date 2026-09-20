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
