<template>
  <main class="literature-workbench" v-loading="loading || starting">
    <header class="literature-toolbar">
      <div>
        <span class="eyebrow">研究现状</span>
        <h3>文献研究迭代</h3>
      </div>
      <div class="literature-actions">
        <el-input v-model="scopeSection" size="small" aria-label="研究范围" />
        <el-tooltip content="刷新研究状态" placement="bottom">
          <el-button :icon="Refresh" circle @click="refresh" />
        </el-tooltip>
        <el-button type="primary" :icon="VideoPlay" :loading="starting" @click="startRun">
          开始研究
        </el-button>
      </div>
    </header>

    <section class="research-metrics">
      <div><span>正文修订</span><strong>r{{ workflow?.revision || revision }}</strong></div>
      <div><span>主张</span><strong>{{ workflow?.claims.length || 0 }}</strong></div>
      <div><span>证据不足</span><strong class="warning">{{ gapCount }}</strong></div>
      <div><span>候选来源</span><strong>{{ selectedRetrievals.length }}</strong></div>
      <div><span>已纳入</span><strong>{{ includedCount }}</strong></div>
      <div><span>待核验</span><strong class="warning">{{ uncertainCount }}</strong></div>
      <div><span>待审修改</span><strong class="attention">{{ pendingChangeSets.length }}</strong></div>
    </section>

    <section class="research-columns">
      <section class="direction-pane">
        <header>
          <div><span>研究矩阵</span><h4>方向与进度</h4></div>
          <el-tag size="small" effect="plain">{{ directions.length }} 项</el-tag>
        </header>
        <button
          v-for="direction in directions"
          :key="direction.key"
          type="button"
          :class="['direction-row', { active: selectedDirection === direction.key }]"
          @click="selectedDirection = direction.key"
        >
          <span>{{ direction.title }}</span>
          <small>{{ directionSourceCount(direction.key) }} 条来源</small>
        </button>
        <el-empty v-if="!directions.length" description="暂无研究矩阵" :image-size="54" />
      </section>

      <section class="iteration-pane">
        <header>
          <div><span>运行与候选</span><h4>{{ selectedRunTitle }}</h4></div>
          <el-select v-model="selectedRunId" size="small" @change="loadRunDetails">
            <el-option
              v-for="run in runs"
              :key="run.id"
              :label="`${runStatusLabel(run.status)} · ${runSection(run)}`"
              :value="run.id"
            />
          </el-select>
        </header>
        <div v-if="selectedRun" class="step-track">
          <div v-for="step in selectedRun.steps" :key="step.id" :class="['step-node', step.status]">
            <span></span>
            <small>{{ stepLabel(step.step_key) }}</small>
          </div>
        </div>
        <div class="iteration-list">
          <article v-for="iteration in iterations" :key="iteration.id" class="iteration-row">
            <div class="iteration-score">
              <span>第 {{ iteration.iteration_no }} 轮</span>
              <strong>{{ formatScore(iteration.evaluation?.total_score) }}</strong>
              <small v-if="iteration.evaluation?.baseline_delta">
                {{ iteration.evaluation.baseline_delta > 0 ? '+' : '' }}{{ iteration.evaluation.baseline_delta }}
              </small>
            </div>
            <div>
              <strong>{{ iterationStatusLabel(iteration) }}</strong>
              <p>{{ iteration.evaluation?.reasons?.[0] || '基线评价已完成' }}</p>
            </div>
            <el-tag :type="iterationTagType(iteration)" effect="plain" size="small">
              {{ iteration.evaluation?.decision === 'discarded' ? '已丢弃' : iteration.iteration_no === 0 ? '基线' : '待审' }}
            </el-tag>
          </article>
        </div>
        <section v-if="latestCandidateOperation" class="candidate-diff">
          <header><span>候选差异</span><strong>{{ latestCandidate?.candidate_payload?.section_id }}</strong></header>
          <div class="diff-before"><small>当前</small><p>{{ latestCandidateOperation.old_text }}</p></div>
          <div class="diff-after"><small>候选</small><p>{{ latestCandidateOperation.new_text }}</p></div>
        </section>
        <el-empty v-if="!iterations.length" description="暂无研究迭代" :image-size="54" />
      </section>

      <section class="evidence-pane">
        <header>
          <div><span>来源与审批</span><h4>证据审查</h4></div>
          <el-segmented v-model="sourceFilter" :options="sourceFilters" size="small" />
        </header>
        <div class="source-list">
          <article v-for="item in filteredRetrievals" :key="item.id" class="source-row">
            <div>
              <strong>{{ item.title }}</strong>
              <small>{{ providerLabel(item.provider) }} · {{ item.year || '年份待核验' }}</small>
            </div>
            <el-tag :type="screeningTagType(item.screening_status)" effect="plain" size="small">
              {{ screeningLabel(item.screening_status) }}
            </el-tag>
            <p>{{ item.screening_reason }}</p>
          </article>
          <el-empty v-if="!filteredRetrievals.length" description="暂无匹配来源" :image-size="50" />
        </div>
        <section v-if="pendingChangeSets.length" class="review-queue">
          <header><span>待审 ChangeSet</span><strong>{{ pendingChangeSets.length }}</strong></header>
          <article v-for="changeSet in pendingChangeSets" :key="changeSet.id">
            <div>
              <strong>{{ changeSet.summary }}</strong>
              <small>高风险 · 基于 r{{ changeSet.base_revision }}</small>
            </div>
            <div class="review-actions">
              <el-tooltip content="批准后生成新的工作正文修订">
                <el-button size="small" type="primary" @click="decideChangeSet(changeSet, 'approve')">批准</el-button>
              </el-tooltip>
              <el-button size="small" @click="decideChangeSet(changeSet, 'reject')">拒绝</el-button>
            </div>
          </article>
        </section>
      </section>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Refresh, VideoPlay } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createWritingLiteratureRun,
  decideWritingChangeSet,
  getWritingLiteratureRuns,
  getWritingResearchIterations,
  getWritingResearchWorkflow,
  getWritingRetrievalRefs,
  type WritingChangeSet,
  type WritingJarvisRun,
  type WritingResearchIteration,
  type WritingResearchWorkflow,
  type WritingRetrievalRef
} from '@/api/writing'

const props = defineProps<{
  projectId: string
  documentId: string
  revision: number
  sectionId?: string
}>()

const loading = ref(false)
const starting = ref(false)
const workflow = ref<WritingResearchWorkflow>()
const runs = ref<WritingJarvisRun[]>([])
const retrievals = ref<WritingRetrievalRef[]>([])
const iterations = ref<WritingResearchIteration[]>([])
const selectedRunId = ref('')
const selectedDirection = ref('')
const scopeSection = ref('1.3.1')
const sourceFilter = ref('all')
const sourceFilters = [
  { label: '全部', value: 'all' },
  { label: '已纳入', value: 'include' },
  { label: '待核验', value: 'uncertain' }
]

const selectedRun = computed(() => runs.value.find(row => row.id === selectedRunId.value))
const selectedRunIds = computed(() => new Set(
  (selectedRun.value?.result_payload?.retrieval_ref_ids || []) as string[]
))
const selectedRetrievals = computed(() => retrievals.value.filter(row => selectedRunIds.value.has(row.id)))
const filteredRetrievals = computed(() => selectedRetrievals.value
  .filter(row => selectedDirection.value ? row.query_id === selectedDirection.value || row.provider === 'bibliography' : true)
  .filter(row => sourceFilter.value === 'all' || row.screening_status === sourceFilter.value)
  .slice(0, 80))
const directions = computed(() => (
  selectedRun.value?.result_payload?.research_matrix?.directions || []
) as Array<{ key: string; title: string }>)
const latestCandidate = computed(() => iterations.value.find(row => row.iteration_no > 0 && row.evaluation?.decision === 'kept'))
const latestCandidateOperation = computed(() => latestCandidate.value?.candidate_payload?.operations?.[0])
const pendingChangeSets = computed(() => (workflow.value?.change_sets || []).filter(row => row.status === 'review_required'))
const gapCount = computed(() => (workflow.value?.claims || []).filter(row => row.evidence_status !== 'sufficient').length)
const includedCount = computed(() => selectedRetrievals.value.filter(row => row.screening_status === 'include').length)
const uncertainCount = computed(() => selectedRetrievals.value.filter(row => row.screening_status === 'uncertain').length)
const selectedRunTitle = computed(() => selectedRun.value ? `${runSection(selectedRun.value)} · ${runStatusLabel(selectedRun.value.status)}` : '尚未运行')

onMounted(refresh)
watch(() => [props.projectId, props.documentId], refresh)
watch(() => props.sectionId, value => {
  if (value?.startsWith('1.3')) scopeSection.value = value
})

async function refresh() {
  if (!props.projectId || !props.documentId) return
  loading.value = true
  try {
    const [nextWorkflow, nextRuns, nextRetrievals] = await Promise.all([
      getWritingResearchWorkflow(props.projectId, props.documentId),
      getWritingLiteratureRuns(props.projectId, props.documentId),
      getWritingRetrievalRefs(props.projectId, props.documentId)
    ])
    workflow.value = nextWorkflow
    runs.value = nextRuns
    retrievals.value = nextRetrievals
    if (!nextRuns.some(row => row.id === selectedRunId.value)) selectedRunId.value = nextRuns[0]?.id || ''
    await loadRunDetails()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '研究迭代加载失败')
  } finally {
    loading.value = false
  }
}

async function loadRunDetails() {
  iterations.value = selectedRunId.value
    ? await getWritingResearchIterations(props.projectId, props.documentId, selectedRunId.value)
    : []
  selectedDirection.value = directions.value[0]?.key || ''
}

async function startRun() {
  starting.value = true
  try {
    const run = await createWritingLiteratureRun(props.projectId, props.documentId, {
      base_revision: workflow.value?.revision || props.revision,
      idempotency_key: `literature-ui-${scopeSection.value}-${Date.now()}`,
      scope_section_ids: [scopeSection.value],
      evaluator_version: 'literature-baseline-v1',
      max_results_per_query: 12,
      source_whitelist: ['local_knowledge', 'bibliography', 'semantic_scholar', 'crossref'],
      external_request_budget: 2
    })
    selectedRunId.value = run.id
    ElMessage.success('研究基线已完成')
    await refresh()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '研究运行失败')
  } finally {
    starting.value = false
  }
}

async function decideChangeSet(changeSet: WritingChangeSet, decision: 'approve' | 'reject') {
  const action = decision === 'approve' ? '批准并生成新工作修订' : '拒绝该候选'
  try {
    await ElMessageBox.confirm(action, '研究候选审批', {
      type: decision === 'approve' ? 'warning' : 'info',
      confirmButtonText: decision === 'approve' ? '批准' : '拒绝',
      cancelButtonText: '取消'
    })
  } catch {
    return
  }
  try {
    await decideWritingChangeSet(props.projectId, props.documentId, changeSet.id, decision)
    ElMessage.success(decision === 'approve' ? '已生成新的工作正文修订' : '候选已拒绝')
    await refresh()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '审批失败')
  }
}

function directionSourceCount(key: string) {
  return selectedRetrievals.value.filter(row => row.query_id === key && row.screening_status === 'include').length
}
function runSection(run: WritingJarvisRun) { return String(run.result_payload?.section_id || run.input_payload?.scope_section_ids?.[0] || '-') }
function runStatusLabel(status: string) { return ({ completed: '已完成', running: '运行中', failed: '失败' } as Record<string, string>)[status] || status }
function iterationStatusLabel(row: WritingResearchIteration) {
  if (row.iteration_no === 0) return '当前正文基线'
  return row.evaluation?.decision === 'discarded' ? '本轮未保留' : '候选等待审查'
}
function iterationTagType(row: WritingResearchIteration) { return row.evaluation?.decision === 'discarded' ? 'info' : row.iteration_no === 0 ? 'primary' : 'warning' }
function formatScore(value?: number) { return typeof value === 'number' ? value.toFixed(2) : '--' }
function providerLabel(provider: string) { return ({ bibliography: '现有书目', local_knowledge: '团队资料', semantic_scholar: 'Semantic Scholar', crossref: 'Crossref' } as Record<string, string>)[provider] || provider }
function screeningLabel(status: string) { return ({ include: '已纳入', uncertain: '待核验', exclude: '已排除', duplicate: '重复', pending: '待筛选' } as Record<string, string>)[status] || status }
function screeningTagType(status: string) { return ({ include: 'success', uncertain: 'warning', exclude: 'info', duplicate: 'info' } as Record<string, any>)[status] || 'primary' }
function stepLabel(key: string) { return ({ freeze_baseline: '冻结', extract_claims: '主张', build_matrix: '矩阵', retrieve_local: '团队资料', retrieve_external: '外部检索', deduplicate: '去重', screen: '筛选', snapshot_sources: '快照', promote_evidence: '证据', bind_claims: '绑定', score_baseline: '评价' } as Record<string, string>)[key] || key }
</script>

<style scoped>
.literature-workbench { min-width: 0; border: 1px solid var(--line-color); border-radius: 6px; background: var(--card-bg); overflow: hidden; }
.literature-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 14px 16px; border-bottom: 1px solid var(--line-color); }
.literature-toolbar h3, .research-columns h4 { margin: 3px 0 0; font-size: 15px; letter-spacing: 0; }
.literature-actions { display: flex; align-items: center; gap: 8px; }
.literature-actions .el-input { width: 110px; }
.research-metrics { display: grid; grid-template-columns: repeat(7, minmax(90px, 1fr)); border-bottom: 1px solid var(--line-color); }
.research-metrics > div { min-width: 0; padding: 11px 14px; border-right: 1px solid var(--line-color); }
.research-metrics > div:last-child { border-right: 0; }
.research-metrics span, .research-metrics strong { display: block; }
.research-metrics span { color: var(--text-muted); font-size: 11px; }
.research-metrics strong { margin-top: 4px; font-size: 18px; letter-spacing: 0; }
.research-metrics .warning { color: var(--el-color-warning); }
.research-metrics .attention { color: var(--el-color-danger); }
.research-columns { display: grid; grid-template-columns: minmax(220px, .75fr) minmax(420px, 1.5fr) minmax(300px, 1fr); min-height: 560px; }
.research-columns > section { min-width: 0; padding: 14px; border-right: 1px solid var(--line-color); }
.research-columns > section:last-child { border-right: 0; }
.research-columns > section > header, .candidate-diff > header, .review-queue > header { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 12px; }
.research-columns header span { color: var(--text-muted); font-size: 11px; }
.direction-row { display: grid; gap: 5px; width: 100%; min-height: 58px; padding: 10px; text-align: left; color: var(--text-color); border: 0; border-bottom: 1px solid var(--line-color); background: transparent; cursor: pointer; }
.direction-row:hover, .direction-row.active { background: var(--el-fill-color-light); }
.direction-row span { font-size: 12px; line-height: 1.5; }
.direction-row small { color: var(--text-muted); }
.iteration-pane > header .el-select { width: 190px; }
.step-track { display: grid; grid-template-columns: repeat(11, minmax(24px, 1fr)); gap: 2px; margin-bottom: 14px; overflow-x: auto; }
.step-node { min-width: 42px; text-align: center; }
.step-node > span { display: block; height: 4px; margin-bottom: 5px; background: var(--el-fill-color-dark); }
.step-node.completed > span { background: var(--el-color-success); }
.step-node.failed > span { background: var(--el-color-danger); }
.step-node small { display: block; color: var(--text-muted); font-size: 9px; white-space: nowrap; }
.iteration-list { display: grid; gap: 1px; background: var(--line-color); }
.iteration-row { display: grid; grid-template-columns: 78px minmax(0, 1fr) auto; align-items: center; gap: 12px; min-height: 74px; padding: 10px; background: var(--card-bg); }
.iteration-row p { margin: 4px 0 0; color: var(--text-muted); font-size: 11px; line-height: 1.45; }
.iteration-score span, .iteration-score small { display: block; color: var(--text-muted); font-size: 10px; }
.iteration-score strong { display: inline-block; margin: 3px 5px 0 0; font-size: 18px; }
.candidate-diff { margin-top: 14px; border-top: 1px solid var(--line-color); padding-top: 12px; }
.candidate-diff > div { padding: 9px 10px; border-left: 3px solid var(--line-color); }
.candidate-diff .diff-before { background: color-mix(in srgb, var(--el-color-danger) 8%, transparent); border-left-color: var(--el-color-danger); }
.candidate-diff .diff-after { margin-top: 6px; background: color-mix(in srgb, var(--el-color-success) 8%, transparent); border-left-color: var(--el-color-success); }
.candidate-diff small { color: var(--text-muted); }
.candidate-diff p { margin: 4px 0 0; line-height: 1.65; }
.source-list { max-height: 360px; overflow: auto; border-top: 1px solid var(--line-color); }
.source-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 5px 8px; padding: 10px 2px; border-bottom: 1px solid var(--line-color); }
.source-row strong { display: block; overflow: hidden; font-size: 12px; line-height: 1.45; text-overflow: ellipsis; white-space: nowrap; }
.source-row small { color: var(--text-muted); }
.source-row p { grid-column: 1 / -1; margin: 2px 0 0; color: var(--text-muted); font-size: 10px; line-height: 1.45; }
.review-queue { margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--line-color); }
.review-queue article { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 10px; padding: 10px 0; border-top: 1px solid var(--line-color); }
.review-queue article strong, .review-queue article small { display: block; }
.review-queue article small { margin-top: 4px; color: var(--text-muted); }
.review-actions { display: flex; gap: 6px; }
@media (max-width: 1280px) {
  .research-metrics { grid-template-columns: repeat(4, minmax(90px, 1fr)); }
  .research-columns { grid-template-columns: 220px minmax(380px, 1fr); }
  .evidence-pane { grid-column: 1 / -1; border-top: 1px solid var(--line-color); }
}
@media (max-width: 760px) {
  .literature-toolbar { align-items: flex-start; flex-direction: column; }
  .literature-actions { width: 100%; }
  .literature-actions .el-input { flex: 1; width: auto; }
  .research-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .research-columns { display: block; }
  .research-columns > section { border-right: 0; border-bottom: 1px solid var(--line-color); }
  .step-track { grid-template-columns: repeat(11, 48px); }
  .iteration-row { grid-template-columns: 68px minmax(0, 1fr); }
  .iteration-row > .el-tag { grid-column: 2; justify-self: start; }
}
</style>
