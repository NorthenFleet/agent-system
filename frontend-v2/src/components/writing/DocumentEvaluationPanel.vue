<template>
  <section class="evaluation-panel" :class="{ compact }">
    <header class="evaluation-head">
      <div>
        <span class="eyebrow">文档评价</span>
        <div class="evaluation-title">
          <h3>{{ profile?.name || report?.profile_name || '评价标准加载中' }}</h3>
          <el-tag v-if="profile || report" effect="plain" size="small">
            v{{ profile?.version || report?.profile_version }}
          </el-tag>
          <el-tag
            v-if="report"
            :type="statusMeta.type"
            effect="plain"
            size="small"
          >
            {{ statusMeta.label }}
          </el-tag>
        </div>
        <p v-if="report?.updated_at" class="evaluation-time">
          评价时间 {{ formatDate(report.updated_at) }}
          <span v-if="report.status === 'stale'">· 正文或标准已变化，当前结果仅供追溯</span>
        </p>
      </div>
      <div class="evaluation-actions">
        <el-button text @click="detailVisible = true">查看完整报告</el-button>
        <el-dropdown split-button type="primary" :loading="busy" @click="$emit('run', 'full')">
          {{ report?.status === 'evaluating' ? '评价中' : '重新评价' }}
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="$emit('run', 'technical')">仅刷新技术检查</el-dropdown-item>
              <el-dropdown-item @click="$emit('run', 'full')">执行完整学术评价</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button :disabled="!canConfirm" @click="openConfirm">专家确认</el-button>
        <el-button :disabled="!profile" @click="openSettings">标准设置</el-button>
      </div>
    </header>

    <el-alert
      v-if="report?.status === 'failed'"
      type="warning"
      :closable="false"
      title="学术评价未完成，技术完整度结果仍然有效；系统没有生成替代分数。"
      show-icon
    />
    <el-alert
      v-else-if="report?.status === 'stale'"
      type="warning"
      :closable="false"
      title="评价已过期：正文哈希或评价标准版本发生变化，请重新评价。"
      show-icon
    />

    <div class="evaluation-summary">
      <article>
        <span>当前成熟度</span>
        <strong>{{ report?.maturity_level || 'L0' }}</strong>
        <small>{{ report?.maturity_label || '材料汇集' }}</small>
      </article>
      <article>
        <span>AI建议分</span>
        <strong>{{ scoreText(report?.provisional_score) }}</strong>
        <small>仅供修改参考</small>
      </article>
      <article>
        <span>专家确认分</span>
        <strong>{{ scoreText(report?.confirmed_score) }}</strong>
        <small>{{ report?.status === 'confirmed' ? '已形成审计记录' : '尚未确认' }}</small>
      </article>
      <article>
        <span>技术完整度</span>
        <strong>{{ scoreText(report?.technical_score) }}</strong>
        <small>结构、引用与文件检查</small>
      </article>
      <article>
        <span>证据覆盖率</span>
        <strong>{{ scoreText(report?.coverage, '%') }}</strong>
        <small>未评价项目不记0分</small>
      </article>
    </div>

    <div v-if="report" class="evaluation-body">
      <section class="dimension-section">
        <header>
          <div>
            <span class="eyebrow">分类型维度</span>
            <h4>{{ report.dimensions.length }} 项动态评价指标</h4>
          </div>
          <small>总分门槛 {{ profile?.pass_threshold ?? '—' }}</small>
        </header>
        <div class="dimension-grid">
          <article
            v-for="dimension in report.dimensions"
            :key="dimension.id"
            class="dimension-card"
          >
            <div>
              <strong>{{ dimension.name }}</strong>
              <small>权重 {{ dimension.weight }} · 最低 {{ dimension.min_score }}</small>
            </div>
            <span :class="criterionClass(dimension.status)">
              {{ dimensionScore(dimension) }}
            </span>
            <el-progress
              :percentage="dimensionProgress(dimension)"
              :show-text="false"
              :stroke-width="5"
              :status="progressStatus(dimension)"
            />
            <p>{{ dimension.summary || '尚未评价，等待证据分析。' }}</p>
          </article>
        </div>
      </section>

      <section class="gate-section">
        <header>
          <div>
            <span class="eyebrow">硬性门槛</span>
            <h4>{{ report.gates.length }} 项送审前置条件</h4>
          </div>
          <small>高总分不能抵消硬门槛失败</small>
        </header>
        <div class="gate-grid">
          <article v-for="gate in report.gates" :key="gate.id">
            <span :class="['gate-dot', criterionClass(gate.status)]" />
            <div>
              <strong>{{ gate.name }}</strong>
              <small>{{ criterionLabel(gate.status) }} · {{ sourceLabel(gate.source) }}</small>
            </div>
            <el-tag v-if="gate.critical" size="small" type="danger" effect="plain">不可关闭</el-tag>
          </article>
        </div>
      </section>
    </div>

    <div v-if="linkedSummary?.documents.length" class="linked-evaluation">
      <header>
        <div>
          <span class="eyebrow">联动成品评价</span>
          <h4>{{ linkedSummary.defense_ready ? 'L5 答辩就绪' : '尚未达到 L5 答辩就绪' }}</h4>
        </div>
        <el-tag :type="linkedSummary.defense_ready ? 'success' : 'warning'" effect="plain">
          {{ linkedSummary.maturity_level }}
        </el-tag>
      </header>
      <div class="linked-document-list">
        <article v-for="item in linkedSummary.documents" :key="item.document_id">
          <div>
            <strong>{{ item.title }}</strong>
            <small>{{ kindLabel(item.kind) }} · {{ item.maturity_level }}</small>
          </div>
          <div>
            <el-tag :type="decisionType(item.decision)" size="small" effect="plain">
              {{ decisionLabel(item.decision) }}
            </el-tag>
            <el-tag
              v-if="item.kind === 'presentation'"
              :type="item.structure_status === 'aligned' ? 'success' : 'warning'"
              size="small"
              effect="plain"
            >
              结构{{ item.structure_status === 'aligned' ? '一致' : '待同步' }}
            </el-tag>
          </div>
        </article>
      </div>
      <ul v-if="linkedSummary.blockers?.length" class="linked-blockers">
        <li v-for="item in linkedSummary.blockers" :key="item">{{ item }}</li>
      </ul>
    </div>

    <section v-if="report?.priority_actions.length" class="priority-actions">
      <header>
        <span class="eyebrow">优先修改建议</span>
        <h4>下一轮写作应先处理</h4>
      </header>
      <ol>
        <li v-for="item in report.priority_actions" :key="item">{{ item }}</li>
      </ol>
    </section>

    <el-drawer v-model="detailVisible" title="文档评价完整报告" size="min(760px, 92vw)">
      <template v-if="report">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="评价标准">{{ report.profile_name }} v{{ report.profile_version }}</el-descriptions-item>
          <el-descriptions-item label="正文哈希">{{ report.source_sha256.slice(0, 16) }}…</el-descriptions-item>
          <el-descriptions-item label="成熟度">{{ report.maturity_level }} {{ report.maturity_label }}</el-descriptions-item>
          <el-descriptions-item label="判定">{{ decisionLabel(report.decision) }}</el-descriptions-item>
          <el-descriptions-item label="模型">{{ report.model || '尚未调用' }}</el-descriptions-item>
          <el-descriptions-item label="证据覆盖">{{ report.coverage }}%</el-descriptions-item>
        </el-descriptions>
        <section v-for="dimension in report.dimensions" :key="dimension.id" class="report-item">
          <header>
            <strong>{{ dimension.name }}</strong>
            <span>{{ dimensionScore(dimension) }} / 最低{{ dimension.min_score }}</span>
          </header>
          <p>{{ dimension.summary || '尚未评价' }}</p>
          <ul v-if="dimension.recommendations?.length">
            <li v-for="item in dimension.recommendations" :key="item">{{ item }}</li>
          </ul>
        </section>
        <section class="audit-list">
          <h4>审计记录</h4>
          <article v-for="(item, index) in report.audit" :key="index">
            <strong>{{ auditLabel(String(item.action || '')) }}</strong>
            <span>{{ String(item.actor || 'system') }} · {{ formatDate(String(item.at || '')) }}</span>
          </article>
        </section>
      </template>
    </el-drawer>

    <el-dialog v-model="confirmVisible" title="专家逐项确认" width="min(760px, 94vw)">
      <el-alert
        title="专家确认会形成审计记录。硬门槛全部通过且分数达标后，文档才可能判定为送审就绪。"
        type="info"
        :closable="false"
        show-icon
      />
      <div class="confirm-dimensions">
        <label v-for="dimension in report?.dimensions || []" :key="dimension.id">
          <span>{{ dimension.name }}（最低{{ dimension.min_score }}）</span>
          <el-input-number
            v-model="confirmScores[dimension.id]"
            :min="0"
            :max="100"
            :precision="1"
            controls-position="right"
          />
        </label>
      </div>
      <div class="confirm-gates">
        <label v-for="gate in report?.gates || []" :key="gate.id">
          <span>{{ gate.name }}</span>
          <el-select v-model="confirmGates[gate.id]" placeholder="暂不确认">
            <el-option label="通过" value="pass" />
            <el-option label="不通过" value="fail" />
            <el-option v-if="!gate.critical" label="不适用" value="not_applicable" />
          </el-select>
        </label>
      </div>
      <el-input v-model="confirmComment" type="textarea" :rows="3" placeholder="填写专家意见与修改要求" />
      <template #footer>
        <el-button @click="confirmVisible = false">取消</el-button>
        <el-button type="primary" :loading="busy" @click="submitConfirmation">保存确认</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="settingsVisible" title="评价标准设置" width="min(760px, 94vw)">
      <el-alert
        title="当前为通用基线标准，不冒充学校官方规范；项目可调整权重和门槛，学术伦理等关键门槛不可关闭。"
        type="info"
        :closable="false"
        show-icon
      />
      <el-form v-if="profile" label-position="top" class="settings-form">
        <el-form-item label="评价标准">
          <el-select v-model="settingsProfileId">
            <el-option
              v-for="item in compatibleProfiles"
              :key="item.id"
              :label="`${item.name} · v${item.version}`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="总分合格阈值">
          <el-input-number v-model="settingsThreshold" :min="0" :max="100" />
        </el-form-item>
        <div class="settings-dimensions">
          <label v-for="dimension in profile.dimensions" :key="dimension.id">
            <span>{{ dimension.name }}</span>
            <el-input-number v-model="settingsWeights[dimension.id]" :min="0" :max="100" />
            <small>权重</small>
            <el-input-number v-model="settingsMinimums[dimension.id]" :min="0" :max="100" />
            <small>最低分</small>
          </label>
        </div>
        <p :class="['weight-total', { invalid: settingsWeightTotal !== 100 }]">
          当前权重合计：{{ settingsWeightTotal }}
        </p>
        <div class="settings-gates">
          <label v-for="gate in profile.gates" :key="gate.id">
            <span>{{ gate.name }}<small v-if="gate.critical">关键门槛</small></span>
            <el-switch v-model="settingsGateRequired[gate.id]" :disabled="gate.critical" />
          </label>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="settingsVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="busy"
          :disabled="settingsWeightTotal !== 100"
          @click="submitSettings"
        >
          保存标准
        </el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import type {
  DocumentEvaluationCriterionStatus,
  DocumentEvaluationDimension,
  DocumentEvaluationProfile,
  DocumentEvaluationReport,
  LinkedDocumentEvaluationSummary,
  WritingDocumentKind
} from '@/api/writing'

interface CatalogProfile {
  id: string
  name: string
  version: string
  kind: WritingDocumentKind
}

const props = withDefaults(defineProps<{
  profile?: DocumentEvaluationProfile
  report?: DocumentEvaluationReport
  linkedSummary?: LinkedDocumentEvaluationSummary
  profiles?: CatalogProfile[]
  busy?: boolean
  compact?: boolean
}>(), {
  profiles: () => [],
  busy: false,
  compact: false
})

const emit = defineEmits<{
  run: [mode: 'technical' | 'full']
  confirm: [payload: {
    dimension_scores: Record<string, number>
    gate_statuses: Record<string, 'pass' | 'fail' | 'not_applicable'>
    comment: string
  }]
  saveProfile: [payload: {
    profile_id: string
    overrides: {
      pass_threshold: number
      dimension_weights: Record<string, number>
      dimension_min_scores: Record<string, number>
      gate_required: Record<string, boolean>
    }
  }]
}>()

const detailVisible = ref(false)
const confirmVisible = ref(false)
const settingsVisible = ref(false)
const confirmScores = reactive<Record<string, number | undefined>>({})
const confirmGates = reactive<Record<string, '' | 'pass' | 'fail' | 'not_applicable'>>({})
const confirmComment = ref('')
const settingsProfileId = ref('')
const settingsThreshold = ref(80)
const settingsWeights = reactive<Record<string, number>>({})
const settingsMinimums = reactive<Record<string, number>>({})
const settingsGateRequired = reactive<Record<string, boolean>>({})

const statusMeta = computed(() => {
  const map = {
    pending: { label: '待评价', type: 'info' as const },
    evaluating: { label: '评价中', type: 'warning' as const },
    provisional: { label: 'AI建议', type: 'warning' as const },
    confirmed: { label: '专家已确认', type: 'success' as const },
    stale: { label: '需复评', type: 'danger' as const },
    failed: { label: '评价失败', type: 'danger' as const }
  }
  return map[props.report?.status || 'pending']
})

const canConfirm = computed(() => Boolean(
  props.report
  && props.report.status !== 'evaluating'
  && props.report.status !== 'stale'
  && props.report.status !== 'failed'
))
const compatibleProfiles = computed(() => {
  const kind = props.profile?.kind
  const rows = props.profiles.filter(row => !kind || row.kind === kind)
  if (rows.length) return rows
  return props.profile ? [props.profile] : []
})
const settingsWeightTotal = computed(() => Math.round(
  Object.values(settingsWeights).reduce((sum, value) => sum + Number(value || 0), 0) * 10
) / 10)

function scoreText(score: number | null | undefined, suffix = '') {
  return score === null || score === undefined ? '待评价' : `${score}${suffix}`
}

function dimensionScore(dimension: DocumentEvaluationDimension) {
  const score = dimension.confirmed_score ?? dimension.score
  return score === null || score === undefined ? '待评价' : `${score}`
}

function dimensionProgress(dimension: DocumentEvaluationDimension) {
  return Number(dimension.confirmed_score ?? dimension.score ?? 0)
}

function progressStatus(dimension: DocumentEvaluationDimension) {
  const score = dimension.confirmed_score ?? dimension.score
  if (score === null || score === undefined) return undefined
  if (score < dimension.min_score) return 'exception'
  if (score >= 85) return 'success'
  return undefined
}

function criterionClass(status?: DocumentEvaluationCriterionStatus) {
  return `criterion-${status || 'pending'}`
}

function criterionLabel(status?: DocumentEvaluationCriterionStatus) {
  const map: Record<string, string> = {
    pass: '通过',
    partial: '部分满足',
    fail: '不通过',
    pending: '待评价',
    not_applicable: '不适用'
  }
  return map[status || 'pending']
}

function sourceLabel(source: string) {
  const map: Record<string, string> = {
    automatic: '自动检查',
    ai: 'AI建议',
    mixed: '自动＋AI',
    human: '人工确认',
    external: '外部确认'
  }
  return map[source] || source
}

function decisionLabel(value: string) {
  return { pending: '待判定', blocked: '存在阻断', qualified: '合格' }[value] || value
}

function decisionType(value: string) {
  if (value === 'qualified') return 'success'
  if (value === 'blocked') return 'danger'
  return 'info'
}

function kindLabel(kind: WritingDocumentKind) {
  return { rich_text: '正文', presentation: 'PPT', workbook: '工作簿' }[kind]
}

function auditLabel(action: string) {
  return {
    technical_evaluation: '技术检查',
    academic_evaluation: 'AI学术评价',
    academic_evaluation_failed: 'AI评价失败',
    expert_confirmation: '专家确认'
  }[action] || action
}

function formatDate(value: string) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}

function clearRecord(record: Record<string, any>) {
  Object.keys(record).forEach(key => delete record[key])
}

function openConfirm() {
  if (!props.report) return
  clearRecord(confirmScores)
  clearRecord(confirmGates)
  props.report.dimensions.forEach(row => {
    const score = row.confirmed_score ?? row.score
    if (score !== null && score !== undefined) confirmScores[row.id] = score
  })
  props.report.gates.forEach(row => {
    confirmGates[row.id] = ['pass', 'fail', 'not_applicable'].includes(row.status || '')
      ? row.status as 'pass' | 'fail' | 'not_applicable'
      : ''
  })
  confirmComment.value = ''
  confirmVisible.value = true
}

function submitConfirmation() {
  const dimensionScores = Object.fromEntries(
    Object.entries(confirmScores)
      .filter(([, value]) => value !== undefined)
      .map(([key, value]) => [key, Number(value)])
  )
  const gateStatuses = Object.fromEntries(
    Object.entries(confirmGates).filter(([, value]) => Boolean(value))
  ) as Record<string, 'pass' | 'fail' | 'not_applicable'>
  emit('confirm', {
    dimension_scores: dimensionScores,
    gate_statuses: gateStatuses,
    comment: confirmComment.value.trim()
  })
  confirmVisible.value = false
}

function openSettings() {
  if (!props.profile) return
  settingsProfileId.value = props.profile.system_profile_id || props.profile.id
  settingsThreshold.value = props.profile.pass_threshold
  clearRecord(settingsWeights)
  clearRecord(settingsMinimums)
  clearRecord(settingsGateRequired)
  props.profile.dimensions.forEach(row => {
    settingsWeights[row.id] = row.weight
    settingsMinimums[row.id] = row.min_score
  })
  props.profile.gates.forEach(row => {
    settingsGateRequired[row.id] = row.required
  })
  settingsVisible.value = true
}

function submitSettings() {
  emit('saveProfile', {
    profile_id: settingsProfileId.value,
    overrides: {
      pass_threshold: settingsThreshold.value,
      dimension_weights: { ...settingsWeights },
      dimension_min_scores: { ...settingsMinimums },
      gate_required: { ...settingsGateRequired }
    }
  })
  settingsVisible.value = false
}
</script>

<style scoped>
.evaluation-panel {
  display: grid;
  gap: 16px;
  padding: 18px;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  background: var(--el-bg-color-overlay);
}

.evaluation-head,
.evaluation-title,
.evaluation-actions,
.dimension-section > header,
.gate-section > header,
.linked-evaluation > header,
.priority-actions > header {
  display: flex;
  align-items: center;
}

.evaluation-head,
.dimension-section > header,
.gate-section > header,
.linked-evaluation > header {
  justify-content: space-between;
  gap: 16px;
}

.evaluation-title,
.evaluation-actions {
  flex-wrap: wrap;
  gap: 8px;
}

.evaluation-title h3,
.dimension-section h4,
.gate-section h4,
.linked-evaluation h4,
.priority-actions h4 {
  margin: 2px 0 0;
}

.evaluation-time {
  margin: 6px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.eyebrow {
  color: var(--el-color-primary);
  font-size: 11px;
  letter-spacing: .08em;
}

.evaluation-summary {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
}

.evaluation-summary article {
  display: grid;
  gap: 4px;
  padding: 14px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  background: var(--el-fill-color-light);
}

.evaluation-summary span,
.evaluation-summary small,
.dimension-card small,
.dimension-card p,
.gate-grid small,
.linked-document-list small {
  color: var(--el-text-color-secondary);
}

.evaluation-summary strong {
  font-size: 22px;
}

.evaluation-body {
  display: grid;
  grid-template-columns: minmax(0, 1.65fr) minmax(290px, 1fr);
  gap: 16px;
}

.dimension-section,
.gate-section,
.linked-evaluation,
.priority-actions {
  display: grid;
  gap: 12px;
}

.dimension-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.dimension-card {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px 12px;
  padding: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
}

.dimension-card .el-progress,
.dimension-card p {
  grid-column: 1 / -1;
}

.dimension-card p {
  margin: 0;
  font-size: 12px;
  line-height: 1.55;
}

.criterion-pass { color: var(--el-color-success); }
.criterion-partial { color: var(--el-color-warning); }
.criterion-fail { color: var(--el-color-danger); }
.criterion-pending,
.criterion-not_applicable { color: var(--el-text-color-secondary); }

.gate-grid {
  display: grid;
  gap: 8px;
}

.gate-grid article {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 9px;
  min-height: 40px;
  padding: 7px 10px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.gate-grid div {
  display: grid;
  gap: 2px;
}

.gate-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: currentColor;
}

.linked-evaluation,
.priority-actions {
  padding-top: 14px;
  border-top: 1px solid var(--el-border-color);
}

.linked-document-list {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.linked-document-list article {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
}

.linked-document-list article > div {
  display: grid;
  align-content: start;
  gap: 4px;
}

.linked-blockers {
  display: grid;
  gap: 5px;
  margin: 0;
  padding-left: 20px;
  color: var(--el-color-warning);
  font-size: 12px;
}

.priority-actions ol {
  display: grid;
  gap: 7px;
  margin: 0;
  padding-left: 20px;
}

.report-item {
  margin-top: 14px;
  padding: 14px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
}

.report-item header,
.audit-list article {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.report-item p {
  line-height: 1.7;
}

.audit-list {
  margin-top: 18px;
}

.audit-list article {
  padding: 9px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.confirm-dimensions,
.confirm-gates,
.settings-dimensions,
.settings-gates {
  display: grid;
  gap: 8px;
  margin: 14px 0;
}

.confirm-dimensions label,
.confirm-gates label,
.settings-gates label {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.settings-dimensions label {
  display: grid;
  grid-template-columns: minmax(160px, 1fr) auto auto auto auto;
  align-items: center;
  gap: 8px;
}

.settings-gates span {
  display: flex;
  gap: 8px;
}

.weight-total {
  color: var(--el-color-success);
  text-align: right;
}

.weight-total.invalid {
  color: var(--el-color-danger);
}

.compact .evaluation-body {
  grid-template-columns: 1fr;
}

.compact .dimension-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

@media (max-width: 1100px) {
  .evaluation-summary {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .evaluation-body {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 900px) {
  .evaluation-head,
  .dimension-section > header,
  .gate-section > header,
  .linked-evaluation > header {
    align-items: flex-start;
    flex-direction: column;
  }

  .evaluation-summary,
  .dimension-grid,
  .compact .dimension-grid,
  .linked-document-list {
    grid-template-columns: 1fr;
  }

  .evaluation-actions {
    width: 100%;
  }

  .settings-dimensions label {
    grid-template-columns: 1fr auto;
  }
}
</style>
