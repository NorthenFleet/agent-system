<template>
  <main class="agent-space">
    <div class="office-backdrop" aria-hidden="true"></div>
    <div class="backdrop-scrim" aria-hidden="true"></div>

    <header class="space-header">
      <button class="brand" type="button" @click="router.push('/')">
        <span class="brand-mark">✦</span>
        <span>OpenClaw</span>
      </button>
      <div class="header-actions">
        <button type="button" class="text-button" @click="router.push('/command-center')">进入任务工作台</button>
        <button type="button" class="avatar-button" @click="router.push('/agents')" aria-label="查看智能体团队">🤖</button>
      </div>
    </header>

    <section class="hero" aria-labelledby="agent-space-title">
      <p class="eyebrow"><span></span> YOUR AI WORKFORCE</p>
      <h1 id="agent-space-title">智能体 <em>Agent Space</em></h1>
      <p class="hero-copy">研发与办公路上的协作伙伴，把复杂任务交给擎天柱和智能体团队。</p>

      <div class="mode-switch" role="tablist" aria-label="任务模式">
        <button
          v-for="item in modes"
          :key="item.value"
          type="button"
          role="tab"
          :aria-selected="mode === item.value"
          :class="{ active: mode === item.value }"
          @click="selectMode(item.value)"
        >
          {{ item.label }}
        </button>
      </div>

      <section class="mission-composer" aria-label="创建智能体任务">
        <textarea
          v-model="objective"
          :placeholder="mode === 'software' ? '描述你要开发、修改或排查的软件任务…' : '描述你要生成、分析或整理的办公任务…'"
          :disabled="submitting"
          @keydown.meta.enter.prevent="submitMission"
          @keydown.ctrl.enter.prevent="submitMission"
        />
        <div class="composer-footer">
          <div class="composer-controls">
            <label class="project-picker">
              <span class="control-icon">⌘</span>
              <select v-model="projectId" :disabled="loading || !matchingProjects.length">
                <option value="">{{ loading ? '正在加载项目…' : '选择 Workspace' }}</option>
                <option v-for="project in matchingProjects" :key="project.id" :value="project.id">{{ project.name }}</option>
              </select>
            </label>
            <span class="control-divider"></span>
            <span class="agent-control"><span class="control-icon">✦</span>擎天柱编排</span>
          </div>
          <button
            class="submit-button"
            type="button"
            :disabled="!canSubmit"
            :aria-label="submitting ? '正在创建任务' : '交给擎天柱'"
            @click="submitMission"
          >
            <span v-if="submitting" class="loader"></span>
            <span v-else>↑</span>
          </button>
        </div>
      </section>

      <div class="workspace-row">
        <span class="workspace-label"><span class="folder-icon">⌑</span>{{ selectedProject?.name || '选择 Workspace 后启动任务' }}</span>
        <span class="workspace-progress"><i></i>{{ activeMissionCount }} 项任务进行中</span>
      </div>

      <div class="suggestion-area">
        <p>快速开始</p>
        <div class="suggestions">
          <button v-for="item in suggestions" :key="item.title" type="button" @click="applySuggestion(item)">
            <span class="suggestion-icon">{{ item.icon }}</span>{{ item.title }}
          </button>
        </div>
      </div>
    </section>

    <footer class="space-footer">
      <span>任务由 AI 智能体协同处理；高风险步骤将进入审批流程。</span>
      <span>⌘ / Ctrl + Enter 提交</span>
    </footer>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { createCommandCenterMission, getCommandCenterSummary } from '@/api/commandCenter'
import { getProjects, type Project } from '@/api/projects'

type MissionMode = 'software' | 'document'

const router = useRouter()
const objective = ref('')
const mode = ref<MissionMode>('document')
const projectId = ref('')
const projects = ref<Project[]>([])
const loading = ref(true)
const submitting = ref(false)
const activeMissionCount = ref(0)

const modes: Array<{ value: MissionMode; label: string }> = [
  { value: 'software', label: '代码开发' },
  { value: 'document', label: '研发办公' }
]

const suggestions = [
  { icon: '▤', title: '技术文档生成', mode: 'document' as MissionMode, prompt: '根据现有项目资料，生成一份结构完整、可评审的技术方案文档，包含目标、架构、接口、风险和验收标准。' },
  { icon: '◔', title: '数据分析', mode: 'document' as MissionMode, prompt: '分析当前项目数据，提炼关键趋势、异常和可执行建议，并输出图表说明与结论。' },
  { icon: '▣', title: 'PRD 生成', mode: 'document' as MissionMode, prompt: '梳理产品需求并生成 PRD，包含用户故事、功能范围、交互说明、优先级和验收条件。' },
  { icon: '▧', title: 'PPT 生成', mode: 'document' as MissionMode, prompt: '根据项目资料制作汇报型 PPT 大纲，明确每页标题、核心观点、数据建议和视觉呈现方式。' },
  { icon: '</>', title: '开发任务', mode: 'software' as MissionMode, prompt: '请分析需求、拆分开发任务并完成实现；输出变更说明、测试结果与验收证据。' }
]

function projectType(project: Project): MissionMode {
  const value = String(project.project_type || project.type || project.context?.project_type || '').toLowerCase()
  return value === 'document' || value === 'writing' ? 'document' : 'software'
}

const matchingProjects = computed(() => projects.value.filter(project => projectType(project) === mode.value))
const selectedProject = computed(() => projects.value.find(project => project.id === projectId.value))
const canSubmit = computed(() => Boolean(objective.value.trim() && projectId.value && !submitting.value))

function selectMode(nextMode: MissionMode) {
  mode.value = nextMode
}

function applySuggestion(item: typeof suggestions[number]) {
  mode.value = item.mode
  objective.value = item.prompt
}

function selectDefaultProject() {
  if (!matchingProjects.value.some(project => project.id === projectId.value)) {
    projectId.value = matchingProjects.value[0]?.id || ''
  }
}

async function loadSpace() {
  loading.value = true
  try {
    const [projectData, summary] = await Promise.all([getProjects(), getCommandCenterSummary()])
    projects.value = projectData.projects
    activeMissionCount.value = summary.active
    selectDefaultProject()
  } catch {
    ElMessage.error('Agent Space 初始化失败，请检查服务连接')
  } finally {
    loading.value = false
  }
}

async function submitMission() {
  if (!objective.value.trim()) return
  if (!projectId.value) {
    ElMessage.warning(matchingProjects.value.length ? '请选择 Workspace' : `暂无可用于${mode.value === 'software' ? '代码开发' : '研发办公'}的项目`)
    return
  }
  submitting.value = true
  try {
    const { mission } = await createCommandCenterMission({
      title: objective.value.trim().slice(0, 80),
      objective: objective.value.trim(),
      project_id: projectId.value,
      mission_type: mode.value
    })
    ElMessage.success('任务已交给擎天柱，正在生成执行计划')
    await router.push({ path: '/command-center', query: { mission_id: mission.id } })
  } catch {
    ElMessage.error('任务创建失败，请稍后重试')
  } finally {
    submitting.value = false
  }
}

watch(mode, selectDefaultProject)
onMounted(loadSpace)
</script>

<style scoped>
.agent-space { min-height: 100vh; position: relative; isolation: isolate; overflow: auto; color: #f7f7f8; background: #050609; }
.office-backdrop, .backdrop-scrim { position: absolute; inset: 0; pointer-events: none; }
.office-backdrop { z-index: -2; background: #050609 url('/assets/agent-space-office.png') center / cover no-repeat; }
.backdrop-scrim { z-index: -1; background: linear-gradient(180deg, rgba(3, 4, 8, .62) 0%, rgba(3, 4, 8, .83) 45%, rgba(3, 4, 8, .32) 100%), radial-gradient(circle at 50% 36%, rgba(10, 13, 19, .08), rgba(3, 4, 8, .68) 78%); }
.space-header { height: 72px; display: flex; align-items: center; justify-content: space-between; padding: 0 clamp(22px, 4vw, 72px); border-bottom: 1px solid rgba(255,255,255,.08); background: rgba(4,5,8,.18); backdrop-filter: blur(12px); }
.brand, .text-button, .avatar-button, .mode-switch button, .suggestions button, .submit-button { font: inherit; color: inherit; cursor: pointer; border: 0; }
.brand { display: inline-flex; align-items: center; gap: 9px; padding: 0; font-size: 16px; font-weight: 750; letter-spacing: .02em; background: transparent; }
.brand-mark { color: #9f7bff; font-size: 23px; line-height: 1; filter: drop-shadow(0 0 10px rgba(159,123,255,.7)); }
.header-actions { display: flex; gap: 12px; align-items: center; }
.text-button { background: rgba(255,255,255,.07); padding: 9px 14px; border-radius: 10px; color: rgba(255,255,255,.78); font-size: 13px; transition: .2s; }
.text-button:hover { color: #fff; background: rgba(255,255,255,.14); }
.avatar-button { display: grid; place-items: center; width: 38px; height: 38px; border-radius: 50%; background: rgba(255,255,255,.12); font-size: 17px; }
.hero { width: min(940px, calc(100% - 36px)); margin: clamp(58px, 10vh, 120px) auto 0; text-align: center; }
.eyebrow { margin: 0 0 16px; color: rgba(235,228,255,.7); font-size: 11px; font-weight: 700; letter-spacing: .17em; }
.eyebrow span { display: inline-block; width: 25px; height: 1px; margin: 0 9px 4px 0; background: #9f7bff; box-shadow: 0 0 10px #9f7bff; }
h1 { margin: 0; font-size: clamp(43px, 6.25vw, 78px); font-weight: 800; line-height: 1.06; letter-spacing: -.055em; text-wrap: balance; text-shadow: 0 5px 30px rgba(0,0,0,.48); }
h1 em { font-style: normal; font-weight: 800; }
.hero-copy { margin: 20px auto 31px; max-width: 600px; color: rgba(239,239,242,.68); font-size: clamp(14px, 1.5vw, 18px); letter-spacing: .02em; }
.mode-switch { display: inline-flex; padding: 4px; border: 1px solid rgba(255,255,255,.13); border-radius: 999px; background: rgba(8,9,13,.72); backdrop-filter: blur(12px); }
.mode-switch button { min-width: 120px; padding: 10px 18px; border-radius: 999px; background: transparent; color: rgba(255,255,255,.55); font-size: 15px; transition: .2s; }
.mode-switch button.active { background: linear-gradient(135deg, #f8f8fb, #d4d4da); color: #19191d; font-weight: 750; box-shadow: 0 3px 11px rgba(0,0,0,.35); }
.mission-composer { margin: 38px auto 0; overflow: hidden; border: 1px solid rgba(255,255,255,.15); border-radius: 16px; background: rgba(20,21,26,.82); box-shadow: 0 22px 55px rgba(0,0,0,.31), inset 0 1px rgba(255,255,255,.045); text-align: left; backdrop-filter: blur(18px); }
.mission-composer:focus-within { border-color: rgba(167,132,255,.75); box-shadow: 0 22px 55px rgba(0,0,0,.31), 0 0 0 3px rgba(157,117,255,.13); }
textarea { width: 100%; min-height: 136px; display: block; resize: vertical; padding: 25px 27px; border: 0; outline: 0; background: transparent; color: #f9f9fb; font: inherit; font-size: 18px; line-height: 1.55; }
textarea::placeholder { color: rgba(255,255,255,.42); }
.composer-footer { min-height: 64px; padding: 10px 16px 13px 19px; display: flex; align-items: center; justify-content: space-between; gap: 14px; }
.composer-controls { min-width: 0; display: flex; align-items: center; gap: 14px; color: rgba(255,255,255,.72); }
.project-picker { display: flex; align-items: center; max-width: min(310px, 45vw); gap: 8px; }
.project-picker select { min-width: 0; max-width: 100%; appearance: none; overflow: hidden; padding: 6px 20px 6px 0; border: 0; outline: 0; background: transparent; color: inherit; font: inherit; font-size: 14px; text-overflow: ellipsis; cursor: pointer; }
.project-picker select option { color: #16171a; }
.control-icon { color: #bda8ff; font-size: 18px; font-weight: 700; }.control-divider { width: 1px; height: 19px; background: rgba(255,255,255,.15); }.agent-control { white-space: nowrap; font-size: 14px; }
.submit-button { flex: 0 0 auto; display: grid; width: 43px; height: 43px; place-items: center; border-radius: 11px; background: linear-gradient(135deg, #8358ea, #5c32c5); color: white; font-size: 27px; line-height: 1; box-shadow: 0 7px 19px rgba(87,47,195,.36); transition: .2s; }
.submit-button:hover:not(:disabled) { transform: translateY(-1px); filter: brightness(1.15); }.submit-button:disabled { cursor: not-allowed; opacity: .45; }.loader { width: 16px; height: 16px; border: 2px solid rgba(255,255,255,.42); border-top-color: #fff; border-radius: 50%; animation: spin .8s linear infinite; }
.workspace-row { display: flex; justify-content: space-between; gap: 20px; padding: 16px 20px 0; color: rgba(255,255,255,.58); font-size: 13px; text-align: left; }.workspace-label, .workspace-progress { display: inline-flex; align-items: center; gap: 7px; }.folder-icon { color: #a98eff; font-size: 19px; }.workspace-progress i { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #62d7b0; box-shadow: 0 0 10px rgba(98,215,176,.8); }
.suggestion-area { margin-top: clamp(36px, 6vh, 76px); }.suggestion-area p { margin: 0 0 13px; color: rgba(255,255,255,.55); font-size: 13px; }.suggestions { display: flex; flex-wrap: wrap; justify-content: center; gap: 10px; }.suggestions button { display: inline-flex; align-items: center; gap: 8px; border: 1px solid rgba(255,255,255,.13); border-radius: 999px; padding: 10px 16px; background: rgba(12,13,17,.68); color: rgba(255,255,255,.85); font-size: 14px; transition: .2s; backdrop-filter: blur(8px); }.suggestions button:hover { border-color: rgba(183,151,255,.65); background: rgba(121,83,222,.22); transform: translateY(-1px); }.suggestion-icon { color: #cabaff; font-weight: 800; }
.space-footer { width: min(1080px, calc(100% - 44px)); margin: clamp(55px, 10vh, 130px) auto 16px; display: flex; justify-content: space-between; gap: 16px; color: rgba(255,255,255,.42); font-size: 12px; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 650px) { .space-header { height: 60px; padding: 0 16px; }.text-button { display: none; }.hero { width: min(100% - 26px, 940px); margin-top: 54px; }.hero-copy { margin-bottom: 23px; }.mode-switch button { min-width: 105px; }.mission-composer { margin-top: 26px; border-radius: 13px; } textarea { min-height: 120px; padding: 19px; font-size: 16px; }.composer-footer { padding-left: 14px; }.agent-control { display: none; }.control-divider { display: none; }.project-picker { max-width: calc(100vw - 122px); }.workspace-row { padding-left: 4px; padding-right: 4px; }.workspace-progress { display: none; }.suggestion-area { margin-top: 43px; }.space-footer { margin-top: 72px; font-size: 11px; }.space-footer span:last-child { display: none; } }
</style>
