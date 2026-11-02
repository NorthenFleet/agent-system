import type {
  CommandCenterAcceptanceGate,
  CommandCenterMission,
  CommandCenterStep
} from '@/api/commandCenter'

export type LifecycleStageState = 'pending' | 'active' | 'completed' | 'warning' | 'blocked'

export interface LifecycleStage {
  id: 'intake' | 'context' | 'planning' | 'approval' | 'execution' | 'evidence' | 'recovery' | 'delivery'
  label: string
  description: string
  state: LifecycleStageState
  detail: string
}

export interface MissionControlPoint {
  tone: 'success' | 'primary' | 'warning' | 'danger' | 'info'
  title: string
  description: string
  action: string
}

const TERMINAL_STATUSES = new Set(['completed', 'failed', 'cancelled'])
const ACTIVE_COMPENSATIONS = new Set(['pending_approval', 'ready', 'running', 'failed', 'rejected'])

function gateState(gate?: CommandCenterAcceptanceGate): LifecycleStageState {
  if (!gate) return 'pending'
  if (gate.enforced && !gate.accepted) return 'blocked'
  if (gate.status === 'warning' || gate.warnings.length) return 'warning'
  return gate.accepted || !gate.enforced ? 'completed' : 'active'
}

function executionDetail(steps: CommandCenterStep[]) {
  const completed = steps.filter(step => step.status === 'completed').length
  const running = steps.filter(step => step.status === 'running').length
  const failed = steps.filter(step => step.status === 'failed').length
  if (!steps.length) return '等待任务拆解'
  if (failed) return `${failed} 个步骤失败，${completed}/${steps.length} 已完成`
  if (running) return `${running} 个步骤执行中，${completed}/${steps.length} 已完成`
  return `${completed}/${steps.length} 个步骤已完成`
}

export function buildMissionLifecycle(mission: CommandCenterMission): LifecycleStage[] {
  const steps = mission.steps || []
  const hasPlan = Boolean(mission.plan)
  const planQuality = mission.plan?.plan_quality
  const pendingStepApprovals = steps.filter(
    step => step.status === 'awaiting_approval' && step.step_approval?.status === 'pending'
  )
  const failedSteps = steps.filter(step => step.status === 'failed')
  const runningSteps = steps.filter(step => step.status === 'running')
  const completedSteps = steps.filter(step => step.status === 'completed')
  const gates = mission.acceptance_gates || []
  const blockedGates = gates.filter(gate => gate.enforced && !gate.accepted)
  const unresolvedCompensations = (mission.compensations || []).filter(
    item => ACTIVE_COMPENSATIONS.has(item.status)
  )
  const unknownEffects = (mission.effects || []).filter(effect => effect.status === 'unknown')
  const context = mission.planning_context

  let contextState: LifecycleStageState = 'pending'
  if (context?.status === 'ready') contextState = 'completed'
  else if (['degraded', 'empty'].includes(context?.status || '')) contextState = 'warning'
  else if (context?.status === 'failed') contextState = 'blocked'
  else if (mission.status === 'received') contextState = 'active'

  let planningState: LifecycleStageState = 'pending'
  if (planQuality?.status === 'blocked') planningState = 'blocked'
  else if (hasPlan && planQuality?.status === 'warning') planningState = 'warning'
  else if (hasPlan) planningState = 'completed'
  else if (mission.status === 'planning') planningState = 'active'

  let approvalState: LifecycleStageState = 'pending'
  if (mission.approval?.decision === 'rejected') approvalState = 'blocked'
  else if (mission.approval_status === 'approved' || mission.approval?.decision === 'approved') {
    approvalState = pendingStepApprovals.length ? 'active' : 'completed'
  } else if (mission.status === 'awaiting_approval') approvalState = 'active'

  let executionState: LifecycleStageState = 'pending'
  if (failedSteps.length) executionState = 'blocked'
  else if (steps.length && completedSteps.length === steps.length) executionState = 'completed'
  else if (runningSteps.length || mission.status === 'running') executionState = 'active'

  let evidenceState = gateState(mission.delivery_gate)
  if (!mission.delivery_gate && gates.length) {
    evidenceState = blockedGates.length
      ? 'blocked'
      : gates.every(gate => gate.accepted && !gate.warnings.length) && executionState === 'completed'
        ? 'completed'
        : 'warning'
  } else if (!gates.length && executionState === 'completed') {
    evidenceState = 'active'
  }

  let recoveryState: LifecycleStageState = 'pending'
  if (unresolvedCompensations.length || unknownEffects.length) recoveryState = 'blocked'
  else if ((mission.compensations || []).some(item => item.status === 'completed')) recoveryState = 'completed'
  else if (executionState === 'completed') recoveryState = 'completed'

  let deliveryState: LifecycleStageState = 'pending'
  if (mission.status === 'completed') deliveryState = 'completed'
  else if (mission.status === 'evaluating') deliveryState = 'active'
  else if (mission.status === 'waiting_feedback' || mission.status === 'failed') deliveryState = 'blocked'
  else if (mission.status === 'cancelled') deliveryState = 'warning'

  return [
    {
      id: 'intake', label: '任务接收', description: '目标与项目绑定', state: 'completed',
      detail: `Mission ${mission.id.slice(0, 8)} 已入库`
    },
    {
      id: 'context', label: '背景冻结', description: '检索与引用快照', state: contextState,
      detail: context ? `${contextStatusLabel(context.status)} · ${context.citation_count} 条引用` : '等待生成上下文快照'
    },
    {
      id: 'planning', label: '规范拆解', description: '合同化步骤与质检', state: planningState,
      detail: hasPlan ? `V${mission.plan_version} · ${planQuality?.score ?? '-'} 分 · ${steps.length} 步` : '等待擎天柱拆解'
    },
    {
      id: 'approval', label: '风险审批', description: '计划与高风险步骤', state: approvalState,
      detail: pendingStepApprovals.length ? `${pendingStepApprovals.length} 个高风险步骤待审批` : approvalState === 'completed' ? '当前计划已授权' : '等待审批节点'
    },
    {
      id: 'execution', label: '受控执行', description: '依赖、租约与幂等', state: executionState,
      detail: executionDetail(steps)
    },
    {
      id: 'evidence', label: '证据验收', description: '产物、证据与门禁', state: evidenceState,
      detail: blockedGates.length ? `${blockedGates.length} 个强制门禁未通过` : `${mission.artifacts?.length || 0} 份产物 · ${mission.evidence?.length || 0} 条证据`
    },
    {
      id: 'recovery', label: '故障恢复', description: '副作用与补偿闭环', state: recoveryState,
      detail: unresolvedCompensations.length ? `${unresolvedCompensations.length} 个未解决补偿` : unknownEffects.length ? `${unknownEffects.length} 个副作用状态未知` : '无未解决恢复项'
    },
    {
      id: 'delivery', label: '交付闭环', description: '总验收与结果回执', state: deliveryState,
      detail: mission.status === 'completed' ? '已通过交付门禁' : `当前：${missionStatusLabel(mission.status)}`
    }
  ]
}

export function deriveMissionControlPoint(mission: CommandCenterMission): MissionControlPoint {
  if (mission.status === 'cancelled') {
    const unresolved = (mission.compensations || []).some(item => ACTIVE_COMPENSATIONS.has(item.status))
    return { tone: unresolved ? 'warning' : 'info', title: '任务已取消', description: '任务已停止调度，历史记录保留', action: unresolved ? '仍有未解决副作用，请查看恢复记录' : '无需继续审批；需要重新执行时创建新任务' }
  }
  if (mission.status === 'planning' || mission.status === 'received') {
    return { tone: 'primary', title: '正在制定执行计划', description: mission.plan_version ? '正在根据反馈制定新计划；尚未批准执行，历史记录保留' : '任务已接收，尚未批准执行', action: '等待计划生成后审阅和批准' }
  }
  const planQuality = mission.plan?.plan_quality
  if (planQuality?.status === 'blocked') {
    return { tone: 'danger', title: '计划质检阻断', description: planQuality.blockers.join('；') || '计划未达到可执行标准', action: '修正任务拆解后重新提交审批' }
  }
  if (mission.status === 'awaiting_approval') {
    return { tone: 'warning', title: '等待计划审批', description: `执行计划 V${mission.plan_version} 已冻结，批准前不会派发步骤`, action: '审查步骤依赖、产物、验收标准和风险后决策' }
  }
  const approvalStep = mission.steps.find(step => step.status === 'awaiting_approval')
  if (approvalStep) {
    return { tone: 'warning', title: '高风险步骤等待授权', description: `${approvalStep.title} 将影响 ${approvalStep.resources?.join('、') || '未声明资源'}`, action: '核对合同指纹、幂等键和回滚方案' }
  }
  const compensation = (mission.compensations || []).find(item => ACTIVE_COMPENSATIONS.has(item.status))
  if (compensation) {
    if (compensation.compensation_type === 'verify_effect') {
      return { tone: 'danger', title: '执行结果待核实', description: `${compensation.resource} · ${compensationStatusLabel(compensation.status)}`, action: compensation.status === 'failed' ? '核实未确认可以继续；保持暂停，需制定新的恢复方案' : '先审批只读核实；不会写入、覆盖或删除文件，也不会自动重试原步骤' }
    }
    return { tone: 'danger', title: '存在未解决副作用', description: `${mission.steps.find(step => step.status === 'failed')?.result?.completion_decision?.effect_quality?.blockers?.join('；') || '需要核实执行结果'} · ${compensation.resource} · ${compensationStatusLabel(compensation.status)}`, action: '完成补偿审批、执行及证据验证后才能继续交付' }
  }
  const blockedGate = (mission.acceptance_gates || []).find(gate => gate.enforced && !gate.accepted)
  if (blockedGate) {
    return { tone: 'danger', title: '验收门禁未通过', description: blockedGate.blockers.join('；') || '执行证据不完整', action: '补齐产物、回执和验证证据后重新评估' }
  }
  const failedStep = mission.steps.find(step => step.status === 'failed')
  if (failedStep) {
    return { tone: 'danger', title: '执行步骤失败', description: mission.last_error || `${failedStep.title}：${failedStep.result?.error || '请查看执行记录'}`, action: '先确认副作用和补偿状态，再决定重试或调整计划' }
  }
  const runningStep = mission.steps.find(step => step.status === 'running')
  if (mission.status === 'failed') {
    return { tone: 'danger', title: '任务失败', description: mission.last_error || '任务未能完成', action: '查看失败原因和执行记录后调整任务' }
  }
  if (runningStep) {
    return { tone: 'primary', title: '规范流程执行中', description: `${runningStep.title} 由 ${runningStep.agent_id} 执行`, action: '等待执行回执和证据门禁评估' }
  }
  if (mission.status === 'completed') {
    const evidenceWarnings = mission.steps.flatMap(step => step.result?.execution_quality?.warnings || [])
    if (evidenceWarnings.length) {
      return { tone: 'warning', title: '任务已完成，证据仍有警告', description: `${evidenceWarnings.length} 条证据警告尚需核对；完成状态不代表严格验收通过`, action: '下载交付物，并查看步骤中的证据警告' }
    }
    return { tone: 'success', title: '交付闭环已完成', description: '计划、执行、证据与恢复状态均已归档', action: '在顶部任务产物中下载文件，并核对审核结论' }
  }
  if (mission.status === 'evaluating') {
    return { tone: 'primary', title: '正在进行最终验收', description: '执行步骤已结束，正在核对最终交付条件', action: '等待验收结论；现有文件可先下载查看' }
  }
  if (mission.status === 'waiting_feedback') return { tone: 'warning', title: '需要补充反馈', description: mission.last_error || '任务已暂停', action: '提交处理意见后重新规划或继续' }
  return { tone: TERMINAL_STATUSES.has(mission.status) ? 'info' : 'primary', title: '任务正在推进', description: '系统将按已批准的规范流程继续执行', action: '关注当前阶段和新产生的控制点' }
}

function contextStatusLabel(status: string) {
  return ({ ready: '已冻结', degraded: '降级', empty: '内容为空', failed: '失败', pending: '处理中' } as Record<string, string>)[status] || status
}

function missionStatusLabel(status: string) {
  return ({ received: '待规划', planning: '规划中', awaiting_approval: '等待批准', running: '执行中', waiting_feedback: '等待反馈', evaluating: '评估中', failed: '失败', cancelled: '已取消' } as Record<string, string>)[status] || status
}

function compensationStatusLabel(status: string) {
  return ({ pending_approval: '等待审批', ready: '等待执行', running: '执行中', failed: '执行失败', rejected: '已拒绝' } as Record<string, string>)[status] || status
}
