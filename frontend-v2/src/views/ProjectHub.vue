<template>
  <div class="project-hub-page">
    <section class="hub-summary">
      <div class="hub-summary-main">
        <h2>项目中枢</h2>
        <p>统一组织程序开发、文档、财务、知识和专业产品，让智能体团队围绕项目完成工作闭环。</p>
      </div>
      <div class="hub-metrics">
        <div class="metric">
          <span>项目</span>
          <strong>{{ projects.length }}</strong>
        </div>
        <div class="metric">
          <span>复合项目</span>
          <strong>{{ compositeProjects }}</strong>
        </div>
        <div class="metric">
          <span>产品绑定</span>
          <strong>{{ productBindingCount }}</strong>
        </div>
      </div>
    </section>

    <el-skeleton v-if="loading" :rows="8" animated />
    <section v-else class="project-grid">
      <article v-for="project in projects" :key="project.id" class="project-panel">
        <header class="project-panel-head">
          <div>
            <h3>{{ project.name }}</h3>
            <p>{{ project.description || projectTypeLabel(project) }}</p>
          </div>
          <div class="project-head-actions">
            <el-tag effect="plain">{{ enabledModules(project).length }} 个模块</el-tag>
            <el-tooltip content="配置项目模块" placement="top">
              <el-button :icon="Setting" circle text @click="openModuleSettings(project)" />
            </el-tooltip>
          </div>
        </header>

        <div class="project-progress">
          <div class="progress-head">
            <span>{{ phaseLabel(project.current_phase || project.status) }}</span>
            <strong>{{ Math.round(project.progress || 0) }}%</strong>
          </div>
          <el-progress :percentage="Math.round(project.progress || 0)" :show-text="false" />
        </div>

        <div class="module-grid">
          <button
            v-for="module in modulesForProject(project)"
            :key="module.key"
            class="module-tile"
            :class="{ active: module.active }"
            :disabled="!module.active"
            @click="openModule(project, module)"
          >
            <span>{{ module.name }}</span>
            <strong>{{ module.value }}</strong>
          </button>
        </div>
      </article>
    </section>

    <el-dialog
      v-model="missionDialogVisible"
      class="mission-dialog"
      :title="`${selectedProject?.name || ''} · 无人集群任务规划`"
      width="min(920px, 92vw)"
      destroy-on-close
      @closed="stopMissionPolling"
    >
      <div class="mission-workspace" v-loading="missionLoading">
        <header class="product-status-band">
          <div>
            <span class="section-label">专业产品</span>
            <strong>无人集群任务规划系统</strong>
            <small>{{ missionHealth?.base_url || missionIntegration.product_url || '192.168.31.144:5130' }}</small>
          </div>
          <el-tag :type="missionHealth?.online ? 'success' : 'danger'" effect="plain">
            {{ missionHealth?.online ? '在线' : '离线' }}
          </el-tag>
        </header>

        <el-alert
          v-if="missionHealth && !missionHealth.online"
          :title="missionHealth.error || '5130 暂时不可用'"
          type="error"
          :closable="false"
          show-icon
        />

        <section class="system-chain" aria-label="项目产品运行链">
          <div class="chain-node chain-owner">
            <span>项目中枢</span>
            <strong>OpenClaw 3021</strong>
            <small>{{ selectedProject?.name }}</small>
          </div>
          <span class="chain-arrow">→</span>
          <div class="chain-node">
            <span>任务规划</span>
            <strong>AI Planning 5130</strong>
            <small>{{ missionIntegration.mission?.bindings?.planning?.scenario_id || '待绑定想定' }}</small>
          </div>
          <span class="chain-arrow">→</span>
          <div class="chain-node">
            <span>仿真执行</span>
            <strong>one-sim</strong>
            <small>5130 内嵌态势会话</small>
          </div>
        </section>

        <section class="binding-section">
          <div class="section-heading">
            <div>
              <h4>项目绑定</h4>
              <p>3021保存项目关系，想定和规划数据仍由5130管理。</p>
            </div>
            <el-tag v-if="missionIntegration.scenario_id" effect="plain">已绑定</el-tag>
          </div>
          <div class="binding-controls">
            <el-select
              v-model="selectedScenarioId"
              filterable
              placeholder="选择5130想定"
              class="scenario-select"
              :disabled="missionBusy || Boolean(missionStatus?.running)"
            >
              <el-option
                v-for="scenario in missionScenarios"
                :key="scenario.id"
                :label="scenario.name"
                :value="scenario.id"
              >
                <span>{{ scenario.name }}</span>
                <small class="scenario-type">{{ scenario.type }}</small>
              </el-option>
            </el-select>
            <el-segmented
              v-model="selectedSide"
              :options="sideOptions"
              :disabled="missionBusy || Boolean(missionStatus?.running)"
            />
            <el-button
              type="primary"
              :loading="bindingMission"
              :disabled="!selectedScenarioId || !missionHealth?.online || Boolean(missionStatus?.running)"
              @click="bindMission"
            >
              保存绑定
            </el-button>
          </div>
          <p v-if="selectedScenarioDescription" class="scenario-description">{{ selectedScenarioDescription }}</p>
        </section>

        <section v-if="missionIntegration.scenario_id" class="runtime-section">
          <div class="section-heading">
            <div>
              <h4>规划运行</h4>
              <p>{{ missionIntegration.scenario_name }} · {{ sideLabel(missionIntegration.side) }}</p>
            </div>
            <el-tag :type="missionStatusTagType(missionIntegration.status)" effect="plain">
              {{ missionStatusLabel(missionIntegration.status) }}
            </el-tag>
          </div>

          <div class="runtime-metrics">
            <div>
              <span>进度</span>
              <strong>{{ Math.round(missionStatus?.progress || 0) }}%</strong>
            </div>
            <div>
              <span>任务</span>
              <strong>{{ missionStatus?.plan_summary?.done || 0 }}/{{ missionStatus?.plan_summary?.total || 0 }}</strong>
            </div>
            <div>
              <span>推演步</span>
              <strong>{{ missionStatus?.tick_count || 0 }}</strong>
            </div>
            <div>
              <span>重规划</span>
              <strong>{{ missionStatus?.total_replans || 0 }}</strong>
            </div>
            <div>
              <span>仿真帧</span>
              <strong>{{ missionIntegration.simulation_status?.frame || 0 }}</strong>
            </div>
          </div>
          <el-progress
            :percentage="Math.round(missionStatus?.progress || 0)"
            :status="missionIntegration.status === 'completed' ? 'success' : undefined"
          />

          <el-alert
            v-if="missionIntegration.last_error"
            :title="missionIntegration.last_error"
            type="error"
            :closable="false"
            show-icon
          />
          <p v-else-if="missionIntegration.result_summary" class="result-summary">
            {{ missionIntegration.result_summary }}
          </p>

          <div class="run-identity">
            <div>
              <span>Mission</span>
              <strong>{{ missionIntegration.mission?.id || '绑定后生成' }}</strong>
            </div>
            <div>
              <span>Run</span>
              <strong>{{ currentMissionRun?.id || '尚未启动' }}</strong>
            </div>
            <div>
              <span>Correlation</span>
              <strong>{{ currentMissionRun?.correlation_id || '尚未生成' }}</strong>
            </div>
          </div>

          <section v-if="runTimeline.length" class="run-timeline">
            <div class="section-heading compact-heading">
              <div>
                <h4>统一运行时间线</h4>
                <p>规划命令、仿真事件和成果使用同一个关联标识。</p>
              </div>
              <el-tag effect="plain">{{ runTimeline.length }} 条最近记录</el-tag>
            </div>
            <div v-for="item in runTimeline" :key="item.key" class="timeline-row">
              <el-tag size="small" effect="plain" :type="timelineTagType(item.kind)">
                {{ timelineKindLabel(item.kind) }}
              </el-tag>
              <div>
                <strong>{{ item.title }}</strong>
                <small>{{ item.source }} · {{ formatMissionTime(item.createdAt) }}</small>
              </div>
            </div>
          </section>

          <div v-if="missionStatus?.tasks?.length" class="mission-task-list">
            <div v-for="task in missionStatus.tasks" :key="task.id" class="mission-task-row">
              <span>{{ task.name }}</span>
              <small :title="task.assigned_units?.join('、')">{{ assignedUnitsLabel(task.assigned_units) }}</small>
              <el-tag size="small" effect="plain">{{ taskStatusLabel(task.status) }}</el-tag>
            </div>
          </div>

          <section class="agent-approval-section">
            <div class="section-heading">
              <div>
                <h4>智能体行动审批</h4>
                <p>{{ pendingApprovalCount ? `${pendingApprovalCount} 项待审批` : '暂无待审批行动' }}</p>
              </div>
              <div class="automation-heading-actions">
                <el-switch
                  v-model="automationEnabled"
                  :loading="updatingAutomation"
                  inline-prompt
                  active-text="监控"
                  inactive-text="关闭"
                />
                <el-button
                  size="small"
                  :loading="evaluatingAutomation"
                  :disabled="!automationEnabled || !missionIntegration.scenario_id"
                  @click="evaluateMissionAutomationNow"
                >立即评估</el-button>
                <el-tag :type="pendingApprovalCount ? 'warning' : 'info'" effect="plain">
                  {{ pendingApprovalCount }} 待审批
                </el-tag>
              </div>
            </div>

            <div class="automation-status-strip">
              <strong>态势监控</strong>
              <el-tag :type="automationHealthTagType(missionIntegration.automation?.health)" effect="plain" size="small">
                {{ automationHealthLabel(missionIntegration.automation?.health) }}
              </el-tag>
              <span>{{ missionMonitor?.task_active ? `${missionMonitor.interval_seconds} 秒周期` : '后台监控未运行' }}</span>
              <span v-if="missionIntegration.automation?.last_checked_at">
                最近评估 {{ formatMissionTime(missionIntegration.automation.last_checked_at) }}
              </span>
              <span v-if="missionIntegration.automation?.monitor_state?.stagnant_checks">
                连续静止 {{ missionIntegration.automation.monitor_state.stagnant_checks }} 次
              </span>
            </div>

            <div class="agent-tool-controls">
              <el-input v-model="missionAgentId" placeholder="智能体 ID" maxlength="64" />
              <el-select v-model="selectedMissionTool" placeholder="选择行动">
                <el-option
                  v-for="tool in missionTools"
                  :key="tool.id"
                  :label="`${tool.name}${tool.approval_required ? ' · 需审批' : ' · 自动执行'}`"
                  :value="tool.id"
                />
              </el-select>
              <el-input v-model="missionAgentReason" placeholder="行动原因或目标" maxlength="500" />
              <el-button
                type="primary"
                :loading="submittingAgentTool"
                :disabled="!canSubmitAgentTool"
                @click="submitAgentTool"
              >
                提交行动
              </el-button>
            </div>
            <p v-if="selectedTool" class="tool-description">{{ selectedTool.description }}</p>

            <div v-if="missionApprovals.length" class="approval-list">
              <div v-for="request in missionApprovals.slice(0, 10)" :key="request.id" class="approval-row">
                <div class="approval-main">
                  <strong>{{ request.tool_label }}</strong>
                  <small>{{ requestSourceLabel(request) }} · {{ request.agent_id }} · {{ formatMissionTime(request.requested_at) }}</small>
                  <span v-if="request.reason">{{ request.reason }}</span>
                  <span v-if="request.source === 'automation' && request.evidence">
                    触发证据：{{ evidenceLabel(request.evidence) }}
                  </span>
                  <span v-if="request.error" class="approval-error">{{ request.error }}</span>
                </div>
                <div class="approval-tags">
                  <el-tag v-if="request.severity" :type="severityTagType(request.severity)" effect="plain" size="small">
                    {{ severityLabel(request.severity) }}
                  </el-tag>
                  <el-tag :type="approvalTagType(request.status)" effect="plain" size="small">
                    {{ approvalStatusLabel(request.status) }}
                  </el-tag>
                </div>
                <div v-if="request.status === 'pending'" class="approval-actions">
                  <el-button
                    size="small"
                    type="primary"
                    :loading="decidingApprovalId === request.id"
                    @click="decideApproval(request, true)"
                  >批准</el-button>
                  <el-button
                    size="small"
                    :disabled="Boolean(decidingApprovalId)"
                    @click="decideApproval(request, false)"
                  >驳回</el-button>
                </div>
              </div>
            </div>
            <el-empty v-else :image-size="44" description="暂无智能体行动记录" />
          </section>

          <div class="section-heading direct-control-heading">
            <div>
              <h4>人工直接控制</h4>
              <p>管理员在当前工作台直接操作5130。</p>
            </div>
          </div>
          <footer class="mission-actions">
            <el-button
              type="primary"
              :loading="startingMission"
              :disabled="!missionHealth?.online || Boolean(missionStatus?.running)"
              @click="startMission"
            >
              启动规划与推演
            </el-button>
            <el-button
              :loading="refreshingMission"
              :disabled="!missionHealth?.online"
              @click="refreshMissionStatus(false)"
            >
              刷新状态
            </el-button>
            <el-button
              type="danger"
              plain
              :loading="stoppingMission"
              :disabled="!missionStatus?.running"
              @click="stopMission"
            >
              停止运行
            </el-button>
            <el-button @click="openMissionProduct">打开5130工作区</el-button>
          </footer>
        </section>
      </div>
    </el-dialog>

    <el-dialog
      v-model="moduleDialogVisible"
      :title="`${moduleProject?.name || ''} · 项目模块`"
      width="min(620px, 92vw)"
      destroy-on-close
    >
      <p class="module-dialog-copy">按项目需要组合业务能力。关闭模块不会删除已有数据，重新启用后仍可继续使用。</p>
      <el-checkbox-group v-model="moduleSelection" class="module-selector">
        <el-checkbox
          v-for="option in projectModuleOptions"
          :key="option.value"
          :value="option.value"
          border
        >
          <strong>{{ option.label }}</strong>
          <small>{{ option.description }}</small>
        </el-checkbox>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="moduleDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingModules" @click="saveProjectModules">保存模块</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Setting } from '@element-plus/icons-vue'
import { getProjects, updateProject, type Project } from '@/api/projects'
import {
  bindProjectMissionPlanning,
  decideMissionPlanningApproval,
  evaluateMissionPlanningAutomation,
  getMissionPlanningApprovals,
  getMissionPlanningAutomationStatus,
  getMissionPlanningHealth,
  getMissionPlanningScenarios,
  getMissionPlanningTools,
  getProjectMissionPlanning,
  invokeMissionPlanningAgentTool,
  refreshProjectMissionPlanning,
  startProjectMissionPlanning,
  stopProjectMissionPlanning,
  updateMissionPlanningAutomation,
  type MissionPlanningApprovalRequest,
  type MissionPlanningIntegration,
  type MissionPlanningScenario,
  type MissionPlanningStatus,
  type MissionPlanningTool
} from '@/api/missionPlanning'

interface ProjectModuleTile {
  key: string
  name: string
  value: string
  route?: string
  action?: 'mission-planning'
  active: boolean
}

const router = useRouter()
const loading = ref(false)
const projects = ref<Project[]>([])
const moduleDialogVisible = ref(false)
const savingModules = ref(false)
const moduleProject = ref<Project>()
const moduleSelection = ref<string[]>([])
const missionDialogVisible = ref(false)
const missionLoading = ref(false)
const bindingMission = ref(false)
const startingMission = ref(false)
const refreshingMission = ref(false)
const stoppingMission = ref(false)
const submittingAgentTool = ref(false)
const decidingApprovalId = ref('')
const updatingAutomation = ref(false)
const evaluatingAutomation = ref(false)
const selectedProject = ref<Project>()
const missionHealth = ref<Awaited<ReturnType<typeof getMissionPlanningHealth>>>()
const missionScenarios = ref<MissionPlanningScenario[]>([])
const missionIntegration = ref<MissionPlanningIntegration>({})
const missionStatus = ref<MissionPlanningStatus>()
const selectedScenarioId = ref('')
const selectedSide = ref('red')
const missionTools = ref<MissionPlanningTool[]>([])
const missionApprovals = ref<MissionPlanningApprovalRequest[]>([])
const selectedMissionTool = ref('inspect_status')
const missionAgentId = ref('optimus')
const missionAgentReason = ref('')
const missionMonitor = ref<Awaited<ReturnType<typeof getMissionPlanningAutomationStatus>>>()
const sideOptions = [
  { label: '红方', value: 'red' },
  { label: '蓝方', value: 'blue' }
]
let missionPollTimer: number | undefined

const projectModuleOptions = [
  { value: 'development', label: '程序开发', description: '软件任务、开发要点和 Codex 执行反馈' },
  { value: 'writing', label: '文档撰写', description: '章节目录、图表、知识引用和论文参考文献' },
  { value: 'finance', label: '财务管理', description: '预算、报销和项目财务归集' },
  { value: 'knowledge', label: '知识引用', description: '关联知识库、概念骨架和项目资料' },
  { value: 'products', label: '产品矩阵', description: '绑定规划、仿真或其他专业产品' },
  { value: 'mission-planning', label: '无人集群任务规划', description: '接入 AI Planning 5130 与 one-sim 仿真' }
]

const missionBusy = computed(() => (
  bindingMission.value || startingMission.value || refreshingMission.value || stoppingMission.value
))
const selectedScenarioDescription = computed(() => (
  missionScenarios.value.find(item => item.id === selectedScenarioId.value)?.description || ''
))
const selectedTool = computed(() => missionTools.value.find(item => item.id === selectedMissionTool.value))
const pendingApprovalCount = computed(() => missionApprovals.value.filter(item => item.status === 'pending').length)
const automationEnabled = computed({
  get: () => missionIntegration.value.automation?.enabled !== false,
  set: value => toggleMissionAutomation(value)
})
const canSubmitAgentTool = computed(() => {
  if (!missionAgentId.value.trim() || !selectedMissionTool.value || !missionHealth.value?.online) return false
  if (selectedMissionTool.value === 'bind_scenario') return Boolean(selectedScenarioId.value)
  return Boolean(missionIntegration.value.scenario_id)
})
const currentMissionRun = computed(() => {
  const runs = missionIntegration.value.runs || []
  const runId = missionIntegration.value.current_run_id || missionIntegration.value.run_id
  return [...runs].reverse().find(run => run.id === runId) || runs[runs.length - 1]
})
const runTimeline = computed(() => {
  const run = currentMissionRun.value
  if (!run) return []
  return [
    ...(run.commands || []).map(item => ({
      key: item.id || `command-${item.created_at}`,
      kind: 'command',
      title: item.detail || item.name || '产品命令',
      source: item.target || 'ai-planning',
      createdAt: item.created_at
    })),
    ...(run.events || []).map(item => ({
      key: item.id || `event-${item.created_at}`,
      kind: 'event',
      title: item.summary || item.type || '运行事件',
      source: item.source || 'product',
      createdAt: item.created_at
    })),
    ...(run.artifacts || []).map(item => ({
      key: item.id || `artifact-${item.created_at}`,
      kind: 'artifact',
      title: item.title || item.type || '运行成果',
      source: item.source || 'product',
      createdAt: item.created_at
    }))
  ].sort((a, b) => String(b.createdAt || '').localeCompare(String(a.createdAt || ''))).slice(0, 8)
})

const compositeProjects = computed(() => projects.value.filter(project => {
  const modules = enabledModules(project)
  return modules.includes('development') && modules.includes('writing')
}).length)
const productBindingCount = computed(() => projects.value.reduce(
  (total, project) => total + (project.product_bindings?.length || 0),
  0
))

function projectTypeValue(project?: Project): 'software' | 'document' {
  const value = String(project?.project_type || project?.type || 'software').toLowerCase()
  return value === 'document' ? 'document' : 'software'
}

function projectTypeLabel(project?: Project) {
  return projectTypeValue(project) === 'document' ? '文档模板' : '开发模板'
}

function enabledModules(project?: Project) {
  if (project?.enabled_modules?.length) return project.enabled_modules
  return projectTypeValue(project) === 'document'
    ? ['writing', 'finance', 'knowledge', 'products']
    : ['development', 'finance', 'knowledge', 'products']
}

function phaseLabel(phase?: string) {
  const map: Record<string, string> = {
    planning: '规划中',
    active: '进行中',
    completed: '已完成',
    done: '已完成',
    draft: '草稿',
    outline: '大纲阶段'
  }
  return map[phase || ''] || phase || '未设置'
}

function modulesForProject(project: Project): ProjectModuleTile[] {
  const modules = new Set(enabledModules(project))
  const taskCount = project.tasks?.length || 0
  const chapterCount = project.document_spec?.chapters?.length || 0
  const assetCount = project.document_spec?.assets?.length || 0
  const mission = project.context?.mission_planning
  const missionProgress = Math.round(mission?.product_status?.progress || 0)
  return [
    {
      key: 'mission-planning',
      name: '无人集群任务规划',
      value: mission?.status === 'running'
        ? `运行中 ${missionProgress}%`
        : mission?.status === 'error'
          ? '连接错误'
          : mission?.scenario_name || '未绑定',
      action: 'mission-planning',
      active: modules.has('mission-planning')
    },
    {
      key: 'development',
      name: '程序开发',
      value: modules.has('development') ? `${taskCount} 任务` : '未启用',
      route: '/development',
      active: modules.has('development')
    },
    {
      key: 'writing',
      name: '文档撰写',
      value: modules.has('writing') ? `${chapterCount} 章` : '未启用',
      route: '/writing',
      active: modules.has('writing')
    },
    {
      key: 'finance',
      name: '财务管理',
      value: '预算/报销',
      route: '/finance',
      active: modules.has('finance')
    },
    {
      key: 'knowledge',
      name: '知识引用',
      value: modules.has('writing') ? `${assetCount} 图表` : '知识库',
      route: '/knowledge',
      active: modules.has('knowledge')
    },
    {
      key: 'products',
      name: '产品矩阵',
      value: `${project.product_bindings?.length || 0} 个产品`,
      route: '/products',
      active: modules.has('products')
    }
  ]
}

function openModuleSettings(project: Project) {
  moduleProject.value = project
  moduleSelection.value = [...enabledModules(project)]
  moduleDialogVisible.value = true
}

async function saveProjectModules() {
  if (!moduleProject.value) return
  if (!moduleSelection.value.length) {
    ElMessage.warning('项目至少需要启用一个模块')
    return
  }
  savingModules.value = true
  try {
    const response = await updateProject(moduleProject.value.id, { enabled_modules: moduleSelection.value })
    const updated = (response as any).project || response
    updateProjectInList(updated)
    moduleDialogVisible.value = false
    ElMessage.success('项目模块已更新')
  } catch (error) {
    ElMessage.error(errorDetail(error, '项目模块保存失败'))
  } finally {
    savingModules.value = false
  }
}

function openModule(project: Project, module: ProjectModuleTile) {
  if (module.action === 'mission-planning') {
    openMissionPlanning(project)
    return
  }
  if (module.route) router.push({ path: module.route, query: { project_id: project.id } })
}

function errorDetail(error: unknown, fallback: string) {
  const detail = (error as any)?.response?.data?.detail
  return typeof detail === 'string' ? detail : fallback
}

function updateProjectInList(project?: Project) {
  if (!project) return
  const index = projects.value.findIndex(item => item.id === project.id)
  if (index >= 0) projects.value[index] = project
  selectedProject.value = project
}

async function openMissionPlanning(project: Project) {
  stopMissionPolling()
  selectedProject.value = project
  missionDialogVisible.value = true
  missionLoading.value = true
  missionHealth.value = undefined
  missionScenarios.value = []
  missionTools.value = []
  missionApprovals.value = []
  missionMonitor.value = undefined
  missionIntegration.value = project.context?.mission_planning || {}
  missionStatus.value = project.context?.mission_planning?.product_status
  missionAgentId.value = project.owner_agent || 'optimus'
  missionAgentReason.value = ''
  selectedMissionTool.value = 'inspect_status'
  try {
    const [healthResult, scenariosResult, projectResult, toolsResult, approvalsResult, monitorResult] = await Promise.allSettled([
      getMissionPlanningHealth(),
      getMissionPlanningScenarios(),
      getProjectMissionPlanning(project.id),
      getMissionPlanningTools(),
      getMissionPlanningApprovals(project.id),
      getMissionPlanningAutomationStatus()
    ])
    if (healthResult.status === 'fulfilled') {
      missionHealth.value = healthResult.value
    } else {
      missionHealth.value = {
        online: false,
        base_url: missionIntegration.value.product_url || 'http://192.168.31.144:5130',
        product: '无人集群任务规划系统',
        error: errorDetail(healthResult.reason, '5130健康检查失败')
      }
    }
    if (scenariosResult.status === 'fulfilled') {
      missionScenarios.value = scenariosResult.value.scenarios || []
    } else {
      missionScenarios.value = []
      ElMessage.error(errorDetail(scenariosResult.reason, '5130想定目录加载失败'))
    }
    if (projectResult.status === 'fulfilled') {
      missionIntegration.value = projectResult.value.integration || {}
    } else {
      throw projectResult.reason
    }
    missionTools.value = toolsResult.status === 'fulfilled' ? toolsResult.value.tools || [] : []
    missionApprovals.value = approvalsResult.status === 'fulfilled' ? approvalsResult.value.requests || [] : []
    missionMonitor.value = monitorResult.status === 'fulfilled' ? monitorResult.value : undefined
    missionStatus.value = missionIntegration.value.product_status
    selectedScenarioId.value = missionIntegration.value.scenario_id || ''
    selectedSide.value = missionIntegration.value.side || 'red'
    if (missionStatus.value?.running) startMissionPolling()
  } catch (error) {
    ElMessage.error(errorDetail(error, '任务规划产品信息加载失败'))
  } finally {
    missionLoading.value = false
  }
}

async function bindMission() {
  if (!selectedProject.value || !selectedScenarioId.value) return
  bindingMission.value = true
  try {
    const data = await bindProjectMissionPlanning(selectedProject.value.id, {
      scenario_id: selectedScenarioId.value,
      side: selectedSide.value
    })
    missionIntegration.value = data.integration
    missionStatus.value = data.integration.product_status
    updateProjectInList(data.project)
    ElMessage.success('5130想定已绑定到项目')
  } catch (error) {
    ElMessage.error(errorDetail(error, '绑定失败'))
  } finally {
    bindingMission.value = false
  }
}

async function startMission() {
  if (!selectedProject.value) return
  startingMission.value = true
  try {
    const data = await startProjectMissionPlanning(selectedProject.value.id)
    missionIntegration.value = data.integration
    updateProjectInList(data.project)
    await refreshMissionStatus(true)
    startMissionPolling()
    ElMessage.success('5130规划与闭环推演已启动')
  } catch (error) {
    ElMessage.error(errorDetail(error, '启动失败'))
  } finally {
    startingMission.value = false
  }
}

async function refreshMissionStatus(silent = false) {
  if (!selectedProject.value || refreshingMission.value) return
  refreshingMission.value = true
  try {
    const data = await refreshProjectMissionPlanning(selectedProject.value.id)
    missionIntegration.value = data.integration
    missionStatus.value = data.status
    updateProjectInList(data.project)
    await loadMissionApprovals().catch(() => undefined)
    if (!data.status.running) stopMissionPolling()
    if (!silent) ElMessage.success('5130状态已同步')
  } catch (error) {
    stopMissionPolling()
    if (!silent) ElMessage.error(errorDetail(error, '状态同步失败'))
  } finally {
    refreshingMission.value = false
  }
}

async function stopMission() {
  if (!selectedProject.value) return
  stoppingMission.value = true
  try {
    const data = await stopProjectMissionPlanning(selectedProject.value.id)
    missionIntegration.value = data.integration
    missionStatus.value = { ...(missionStatus.value || {}), running: false, state: 'stopped' }
    updateProjectInList(data.project)
    stopMissionPolling()
    ElMessage.success('5130运行已停止')
  } catch (error) {
    ElMessage.error(errorDetail(error, '停止失败'))
  } finally {
    stoppingMission.value = false
  }
}

async function loadMissionApprovals() {
  if (!selectedProject.value) return
  const data = await getMissionPlanningApprovals(selectedProject.value.id)
  missionApprovals.value = data.requests || []
}

async function reloadMissionIntegration() {
  if (!selectedProject.value) return
  const data = await getProjectMissionPlanning(selectedProject.value.id)
  missionIntegration.value = data.integration || {}
  missionStatus.value = missionIntegration.value.product_status
}

async function toggleMissionAutomation(enabled: boolean) {
  if (!selectedProject.value || updatingAutomation.value) return
  updatingAutomation.value = true
  try {
    const data = await updateMissionPlanningAutomation(selectedProject.value.id, enabled)
    missionIntegration.value = data.integration
    updateProjectInList(data.project)
    ElMessage.success(enabled ? '态势自动监控已开启' : '态势自动监控已关闭')
  } catch (error) {
    ElMessage.error(errorDetail(error, '态势监控设置失败'))
  } finally {
    updatingAutomation.value = false
  }
}

async function evaluateMissionAutomationNow() {
  if (!selectedProject.value) return
  evaluatingAutomation.value = true
  try {
    const data = await evaluateMissionPlanningAutomation(selectedProject.value.id)
    await Promise.all([reloadMissionIntegration(), loadMissionApprovals()])
    if (data.suggestions?.length) ElMessage.warning(`检测到 ${data.suggestions.length} 项需审批行动`)
    else ElMessage.success(data.status === 'waiting' ? '5130未运行，当前无需行动' : '态势评估完成，未发现需审批行动')
  } catch (error) {
    await reloadMissionIntegration().catch(() => undefined)
    ElMessage.error(errorDetail(error, '态势评估失败'))
  } finally {
    evaluatingAutomation.value = false
  }
}

function applyAgentExecution(execution?: {
  project?: Project
  integration?: MissionPlanningIntegration
  status?: MissionPlanningStatus
}) {
  if (!execution) return
  if (execution.integration) missionIntegration.value = execution.integration
  if (execution.status) missionStatus.value = execution.status
  else if (execution.integration?.product_status) missionStatus.value = execution.integration.product_status
  updateProjectInList(execution.project)
}

async function submitAgentTool() {
  if (!selectedProject.value || !canSubmitAgentTool.value) return
  const payload: Record<string, unknown> = {}
  if (selectedMissionTool.value === 'bind_scenario') {
    payload.scenario_id = selectedScenarioId.value
    payload.side = selectedSide.value
  } else if (selectedMissionTool.value === 'replan') {
    payload.reason = missionAgentReason.value || '智能体请求重新规划'
  }
  submittingAgentTool.value = true
  try {
    const data = await invokeMissionPlanningAgentTool(selectedProject.value.id, {
      agent_id: missionAgentId.value.trim(),
      tool_name: selectedMissionTool.value,
      reason: missionAgentReason.value,
      payload
    })
    applyAgentExecution(data.execution)
    await loadMissionApprovals()
    missionAgentReason.value = ''
    ElMessage.success(data.dispatch_status === 'pending_approval' ? '智能体行动已提交审批' : '只读行动已自动执行')
  } catch (error) {
    await loadMissionApprovals().catch(() => undefined)
    ElMessage.error(errorDetail(error, '智能体行动提交失败'))
  } finally {
    submittingAgentTool.value = false
  }
}

async function decideApproval(request: MissionPlanningApprovalRequest, approved: boolean) {
  if (!selectedProject.value) return
  decidingApprovalId.value = request.id
  try {
    const data = await decideMissionPlanningApproval(selectedProject.value.id, request.id, {
      approved,
      comment: approved ? '管理员批准执行' : '管理员驳回'
    })
    applyAgentExecution(data.execution)
    await loadMissionApprovals()
    ElMessage.success(approved ? '行动已批准并执行' : '行动已驳回')
  } catch (error) {
    await loadMissionApprovals().catch(() => undefined)
    ElMessage.error(errorDetail(error, approved ? '批准或执行失败' : '驳回失败'))
  } finally {
    decidingApprovalId.value = ''
  }
}

function startMissionPolling() {
  stopMissionPolling()
  missionPollTimer = window.setInterval(() => refreshMissionStatus(true), 5000)
}

function stopMissionPolling() {
  if (missionPollTimer) window.clearInterval(missionPollTimer)
  missionPollTimer = undefined
}

function openMissionProduct() {
  const url = missionHealth.value?.base_url || missionIntegration.value.product_url
  if (url) window.open(url, '_blank', 'noopener,noreferrer')
}

function missionStatusLabel(status?: string) {
  return ({ bound: '已绑定', running: '运行中', completed: '已完成', stopped: '已停止', error: '错误' } as Record<string, string>)[status || ''] || '未启动'
}

function missionStatusTagType(status?: string): 'success' | 'warning' | 'danger' | 'info' | 'primary' {
  if (status === 'completed') return 'success'
  if (status === 'running') return 'primary'
  if (status === 'error') return 'danger'
  if (status === 'stopped') return 'warning'
  return 'info'
}

function taskStatusLabel(status?: string) {
  return ({ active: '执行中', done: '已完成', pending: '待执行', failed: '失败' } as Record<string, string>)[status || ''] || status || '未知'
}

function assignedUnitsLabel(units?: string[]) {
  if (!units?.length) return '未分配平台'
  if (units.length <= 3) return units.join('、')
  return `${units.slice(0, 3).join('、')} 等 ${units.length} 个平台`
}

function sideLabel(side?: string) {
  return side === 'blue' ? '蓝方规划' : '红方规划'
}

function timelineKindLabel(kind: string) {
  return ({ command: '命令', event: '事件', artifact: '成果' } as Record<string, string>)[kind] || kind
}

function timelineTagType(kind: string): 'primary' | 'success' | 'warning' | 'info' {
  if (kind === 'command') return 'primary'
  if (kind === 'artifact') return 'success'
  return 'info'
}

function approvalStatusLabel(status?: string) {
  return ({
    queued: '排队中',
    pending: '待审批',
    approved: '已批准',
    executing: '执行中',
    executed: '已执行',
    rejected: '已驳回',
    failed: '失败'
  } as Record<string, string>)[status || ''] || status || '未知'
}

function approvalTagType(status?: string): 'success' | 'warning' | 'danger' | 'info' | 'primary' {
  if (status === 'executed') return 'success'
  if (status === 'pending') return 'warning'
  if (status === 'failed' || status === 'rejected') return 'danger'
  if (status === 'executing' || status === 'approved') return 'primary'
  return 'info'
}

function automationHealthLabel(health?: string) {
  return ({
    waiting: '等待运行',
    healthy: '正常',
    attention: '需关注',
    error: '检查失败',
    disabled: '已关闭'
  } as Record<string, string>)[health || ''] || (automationEnabled.value ? '等待采样' : '已关闭')
}

function automationHealthTagType(health?: string): 'success' | 'warning' | 'danger' | 'info' | 'primary' {
  if (health === 'healthy') return 'success'
  if (health === 'attention') return 'warning'
  if (health === 'error') return 'danger'
  return 'info'
}

function requestSourceLabel(request: MissionPlanningApprovalRequest) {
  return request.source === 'automation' ? '态势监控器' : '人工提交'
}

function severityLabel(severity?: string) {
  return ({ critical: '严重', high: '高', medium: '中' } as Record<string, string>)[severity || ''] || severity || ''
}

function severityTagType(severity?: string): 'danger' | 'warning' | 'info' {
  if (severity === 'critical') return 'danger'
  if (severity === 'high') return 'warning'
  return 'info'
}

function evidenceLabel(evidence?: Record<string, unknown>) {
  if (!evidence) return ''
  const labels: Record<string, string> = {
    event: '事件',
    event_type: '类型',
    replan_delta: '新增重规划',
    total_replans: '累计重规划',
    consecutive_urgent: '连续紧急',
    eval_score: '评估分',
    diagnosis: '诊断',
    tick_count: '推演步',
    done: '完成任务',
    stagnant_checks: '静止采样'
  }
  return Object.entries(evidence)
    .filter(([, value]) => value !== undefined && value !== null && value !== '')
    .map(([key, value]) => `${labels[key] || key} ${String(value)}`)
    .join(' · ')
}

function formatMissionTime(value?: string) {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}

async function loadProjects() {
  loading.value = true
  try {
    const data = await getProjects()
    projects.value = data.projects || []
  } catch {
    ElMessage.error('项目数据加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(loadProjects)
onBeforeUnmount(stopMissionPolling)
</script>

<style scoped>
.project-hub-page {
  min-height: 100%;
}

.hub-summary {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 18px;
  align-items: stretch;
  margin-bottom: 18px;
  padding: 18px;
  border: 1px solid var(--view-color-border);
  border-radius: 8px;
  background: var(--panel-bg);
}

.hub-summary-main h2 {
  margin: 0 0 6px;
  color: var(--text-primary);
  font-size: 20px;
}

.hub-summary-main p {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.6;
}

.hub-metrics {
  display: grid;
  grid-template-columns: repeat(3, 96px);
  gap: 10px;
}

.metric {
  display: grid;
  gap: 6px;
  align-content: center;
  padding: 12px;
  border: 1px solid var(--line-color);
  border-radius: 6px;
  background: var(--card-bg);
}

.metric span {
  color: var(--text-secondary);
  font-size: 12px;
}

.metric strong {
  color: var(--text-primary);
  font-size: 22px;
}

.project-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
  gap: 16px;
}

.project-panel {
  display: grid;
  gap: 14px;
  padding: 16px;
  border: 1px solid var(--view-color-border);
  border-radius: 8px;
  background: var(--panel-bg);
}

.project-panel-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.project-head-actions {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  flex: none;
}

.module-dialog-copy {
  margin: 0 0 16px;
  color: var(--text-secondary);
  line-height: 1.6;
}

.module-selector {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.module-selector :deep(.el-checkbox) {
  width: 100%;
  height: auto;
  min-height: 72px;
  margin: 0;
  padding: 12px;
  align-items: flex-start;
}

.module-selector :deep(.el-checkbox__label) {
  display: grid;
  gap: 5px;
  white-space: normal;
}

.module-selector small {
  color: var(--text-secondary);
  line-height: 1.4;
}

.project-panel-head h3 {
  margin: 0 0 6px;
  color: var(--text-primary);
  font-size: 16px;
}

.project-panel-head p {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.5;
}

.project-progress {
  display: grid;
  gap: 8px;
}

.progress-head {
  display: flex;
  justify-content: space-between;
  color: var(--text-secondary);
  font-size: 12px;
}

.module-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(128px, 1fr));
  gap: 10px;
}

@media (max-width: 720px) {
  .module-selector {
    grid-template-columns: 1fr;
  }
}

.module-tile {
  min-height: 72px;
  display: grid;
  gap: 6px;
  align-content: center;
  text-align: left;
  padding: 10px 12px;
  border: 1px solid var(--line-color);
  border-radius: 6px;
  color: var(--text-secondary);
  background: var(--card-bg);
  cursor: default;
}

.module-tile.active {
  color: var(--text-primary);
  border-color: var(--view-color-border);
  background: var(--view-color-faint);
  cursor: pointer;
}

.module-tile.active:hover {
  border-color: var(--view-color-strong-border);
  background: var(--view-color-soft);
}

.module-tile span {
  font-size: 12px;
}

.module-tile strong {
  font-size: 14px;
  font-weight: 700;
}

.mission-workspace {
  display: grid;
  gap: 18px;
}

:deep(.mission-dialog) {
  display: flex;
  flex-direction: column;
  max-height: 92vh;
  margin-top: 4vh;
  margin-bottom: 4vh;
}

:deep(.mission-dialog .el-dialog__body) {
  min-height: 0;
  overflow-y: auto;
}

.product-status-band,
.section-heading,
.mission-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.product-status-band {
  padding-bottom: 14px;
  border-bottom: 1px solid var(--line-color);
}

.product-status-band > div {
  display: grid;
  gap: 3px;
}

.product-status-band strong {
  color: var(--text-primary);
  font-size: 16px;
}

.product-status-band small,
.section-label,
.section-heading p,
.scenario-description,
.mission-task-row small {
  color: var(--text-secondary);
}

.system-chain {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr) auto minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  padding: 10px 0;
  border-top: 1px solid var(--line-color);
  border-bottom: 1px solid var(--line-color);
}

.chain-node {
  display: grid;
  gap: 3px;
  min-width: 0;
  padding: 8px 10px;
  border-left: 2px solid var(--view-color-border);
}

.chain-owner {
  border-left-color: var(--el-color-success);
}

.chain-node span,
.chain-node small,
.chain-arrow {
  color: var(--text-secondary);
  font-size: 11px;
}

.chain-node strong,
.chain-node small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chain-node strong {
  color: var(--text-primary);
  font-size: 13px;
}

.section-label {
  font-size: 11px;
}

.binding-section,
.runtime-section {
  display: grid;
  gap: 14px;
}

.section-heading h4,
.section-heading p {
  margin: 0;
}

.section-heading h4 {
  margin-bottom: 4px;
  color: var(--text-primary);
  font-size: 15px;
}

.section-heading p,
.scenario-description,
.result-summary {
  font-size: 12px;
}

.binding-controls {
  display: grid;
  grid-template-columns: minmax(260px, 1fr) auto auto;
  gap: 10px;
  align-items: center;
}

.scenario-type {
  float: right;
  margin-left: 18px;
  color: var(--text-secondary);
}

.scenario-description,
.result-summary {
  margin: 0;
  line-height: 1.6;
}

.runtime-metrics {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  border-top: 1px solid var(--line-color);
  border-bottom: 1px solid var(--line-color);
}

.runtime-metrics > div {
  display: grid;
  gap: 5px;
  padding: 12px;
  border-right: 1px solid var(--line-color);
}

.runtime-metrics > div:last-child {
  border-right: 0;
}

.runtime-metrics span {
  color: var(--text-secondary);
  font-size: 11px;
}

.runtime-metrics strong {
  color: var(--text-primary);
  font-size: 18px;
}

.run-identity {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1px;
  background: var(--line-color);
  border: 1px solid var(--line-color);
  border-radius: 6px;
  overflow: hidden;
}

.run-identity > div {
  display: grid;
  gap: 4px;
  min-width: 0;
  padding: 9px 10px;
  background: var(--card-bg);
}

.run-identity span,
.run-identity strong,
.timeline-row small {
  font-size: 11px;
}

.run-identity span,
.timeline-row small {
  color: var(--text-secondary);
}

.run-identity strong {
  overflow: hidden;
  color: var(--text-primary);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.run-timeline {
  display: grid;
  gap: 0;
  padding-top: 4px;
}

.compact-heading {
  margin-bottom: 6px;
}

.timeline-row {
  display: grid;
  grid-template-columns: 54px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  min-height: 42px;
  border-bottom: 1px solid var(--line-color);
}

.timeline-row > div {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.timeline-row strong,
.timeline-row small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mission-task-list {
  display: grid;
  border-top: 1px solid var(--line-color);
}

.mission-task-row {
  display: grid;
  grid-template-columns: minmax(180px, 1fr) minmax(160px, 1fr) auto;
  gap: 12px;
  align-items: center;
  min-height: 42px;
  border-bottom: 1px solid var(--line-color);
}

.mission-task-row > span {
  color: var(--text-primary);
}

.mission-actions {
  justify-content: flex-start;
  flex-wrap: wrap;
  padding-top: 4px;
}

.agent-approval-section {
  display: grid;
  gap: 12px;
  padding-top: 14px;
  border-top: 1px solid var(--line-color);
}

.agent-tool-controls {
  display: grid;
  grid-template-columns: minmax(120px, 0.7fr) minmax(190px, 1fr) minmax(220px, 1.5fr) auto;
  gap: 8px;
  align-items: center;
}

.automation-heading-actions,
.approval-tags {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.automation-status-strip {
  display: flex;
  gap: 10px;
  align-items: center;
  min-height: 36px;
  padding: 7px 10px;
  border-top: 1px solid var(--line-color);
  border-bottom: 1px solid var(--line-color);
  color: var(--text-secondary);
  font-size: 11px;
}

.automation-status-strip strong {
  color: var(--text-primary);
  font-size: 12px;
}

.tool-description {
  margin: 0;
  color: var(--text-secondary);
  font-size: 12px;
}

.approval-list {
  display: grid;
  border-top: 1px solid var(--line-color);
}

.approval-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  gap: 12px;
  align-items: center;
  min-height: 58px;
  padding: 8px 0;
  border-bottom: 1px solid var(--line-color);
}

.approval-main {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.approval-main strong,
.approval-main span,
.approval-main small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.approval-main strong {
  color: var(--text-primary);
  font-size: 13px;
}

.approval-main small,
.approval-main span {
  color: var(--text-secondary);
  font-size: 11px;
}

.approval-main .approval-error {
  color: var(--el-color-danger);
}

.approval-actions {
  display: flex;
  gap: 4px;
}

.direct-control-heading {
  padding-top: 14px;
  border-top: 1px solid var(--line-color);
}

@media (max-width: 900px) {
  .hub-summary {
    grid-template-columns: 1fr;
  }

  .hub-metrics {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .binding-controls {
    grid-template-columns: 1fr;
  }

  .system-chain {
    grid-template-columns: 1fr;
  }

  .chain-arrow {
    display: none;
  }

  .agent-tool-controls {
    grid-template-columns: 1fr;
  }

  .automation-heading-actions,
  .automation-status-strip {
    align-items: flex-start;
  }

  .agent-approval-section > .section-heading {
    align-items: stretch;
    flex-direction: column;
  }

  .automation-heading-actions {
    justify-content: space-between;
    width: 100%;
  }

  .automation-status-strip {
    flex-wrap: wrap;
  }

  .runtime-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .runtime-metrics > div:nth-child(2) {
    border-right: 0;
  }

  .runtime-metrics > div:nth-child(4) {
    border-right: 0;
  }

  .run-identity {
    grid-template-columns: 1fr;
  }

  .mission-task-row {
    grid-template-columns: 1fr auto;
  }

  .mission-task-row small {
    grid-column: 1 / -1;
    grid-row: 2;
  }

  .approval-row {
    grid-template-columns: minmax(0, 1fr) auto;
  }

  .approval-actions {
    grid-column: 1 / -1;
  }
}
</style>
