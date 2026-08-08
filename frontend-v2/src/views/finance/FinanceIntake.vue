<template>
  <section class="intake-workspace" v-loading="loading">
    <div class="mode-strip">
      <div>
        <div class="mode-title">
          <span>智能财务作业</span>
          <el-tag type="warning" effect="plain">影子模式</el-tag>
        </div>
        <p>正式财务表只读，当前作业仅保存在受审计暂存区。</p>
      </div>
      <el-tooltip content="刷新作业" placement="bottom">
        <el-button :icon="Refresh" circle aria-label="刷新作业" @click="load" />
      </el-tooltip>
    </div>

    <section v-if="readiness" class="readiness-panel">
      <div class="readiness-head">
        <div>
          <strong>正式写入门禁</strong>
          <p>配置齐备后仍需单独人工授权，系统不会自动切换。</p>
        </div>
        <el-tag :type="readiness.prerequisites_ready ? 'warning' : 'danger'" effect="plain">
          {{ readiness.prerequisites_ready ? '等待人工授权' : '尚不具备启用条件' }}
        </el-tag>
      </div>
      <div class="readiness-grid">
        <div><span>运行模式</span><strong>影子锁定</strong></div>
        <div><span>审批流程</span><strong>{{ readiness.counts.active_workflows }}</strong></div>
        <div><span>复核员</span><strong>{{ readiness.counts.reviewers }}</strong></div>
        <div><span>出纳</span><strong>{{ readiness.counts.cashiers }}</strong></div>
      </div>
      <div class="readiness-checks">
        <span v-for="check in readiness.checks" :key="check.key" :class="{ passed: check.passed }">
          {{ check.passed ? '已满足' : '待配置' }} · {{ check.label }}
        </span>
      </div>
      <p class="gate-note">{{ readiness.blockers.join('；') }}</p>
    </section>

    <div class="summary-grid">
      <div v-for="item in summaryCards" :key="item.key" class="summary-item">
        <span>{{ item.label }}</span>
        <strong :class="`tone-${item.tone}`">{{ item.value }}</strong>
      </div>
    </div>

    <div class="workbench-grid">
      <aside class="queue-panel">
        <div class="panel-head">
          <div>
            <strong>作业队列</strong>
            <span>{{ visibleJobs.length }} / {{ jobs.length }}</span>
          </div>
        </div>
        <div class="filters">
          <el-select v-model="statusFilter" placeholder="全部状态" clearable>
            <el-option v-for="item in statusOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-select v-model="operationFilter" placeholder="全部类型" clearable>
            <el-option v-for="item in operationOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </div>

        <div v-if="visibleJobs.length" class="job-list">
          <button
            v-for="job in visibleJobs"
            :key="job.id"
            type="button"
            class="job-row"
            :class="{ active: selectedId === job.id }"
            @click="selectJob(job.id)"
          >
            <span class="job-state" :class="`state-${job.status}`" />
            <span class="job-main">
              <span class="job-title">{{ operationLabel(job.operation_type) }}</span>
              <span class="job-meta">{{ job.target_agent_id === 'soundwave' ? '声波' : job.target_agent_id }} · {{ formatTime(job.created_at) }}</span>
            </span>
            <el-tag :type="statusType(job.status)" size="small" effect="plain">{{ statusLabel(job.status) }}</el-tag>
          </button>
        </div>
        <el-empty v-else description="暂无匹配作业" :image-size="72" />
      </aside>

      <main class="detail-panel">
        <template v-if="detail">
          <header class="detail-head">
            <div>
              <div class="detail-title">
                <strong>{{ operationLabel(detail.operation_type) }}</strong>
                <el-tag :type="statusType(detail.status)" effect="plain">{{ statusLabel(detail.status) }}</el-tag>
              </div>
              <span class="job-id">{{ detail.id }}</span>
            </div>
            <div class="agent-chain">
              <span>声波</span><i>→</i><span>确定性规则</span><i>→</i><span>检查员</span>
            </div>
          </header>

          <el-steps
            class="pipeline"
            :active="pipelineActive"
            :process-status="detail.status === 'rejected' || detail.status === 'failed' ? 'error' : 'process'"
            finish-status="success"
            align-center
          >
            <el-step title="安全接入" :description="formatTime(detail.created_at)" />
            <el-step title="抽取与校验" :description="validationStepText" />
            <el-step title="独立复核" :description="reviewStepText" />
          </el-steps>

          <section class="detail-section">
            <div class="section-title"><strong>原始请求</strong><span>{{ detail.source_channel }} / {{ detail.source_account_id }}</span></div>
            <div class="request-box">{{ detail.request_text }}</div>
          </section>

          <section class="detail-section">
            <div class="section-title"><strong>结构化抽取</strong><span>版本 {{ detail.lock_version }}</span></div>
            <div v-if="normalizedEntries.length" class="field-grid">
              <div v-for="entry in normalizedEntries" :key="entry[0]" class="field-item">
                <span>{{ fieldLabel(entry[0]) }}</span>
                <strong>{{ valueText(entry[1]) }}</strong>
              </div>
            </div>
            <el-empty v-else description="等待声波抽取" :image-size="64" />
          </section>

          <section class="detail-section validation-section">
            <div class="section-title">
              <strong>确定性校验</strong>
              <el-tag v-if="detail.validation_report.valid === true" type="success" effect="plain">通过</el-tag>
              <el-tag v-else-if="detail.validation_report.valid === false" type="danger" effect="plain">未通过</el-tag>
              <el-tag v-else effect="plain">未执行</el-tag>
            </div>
            <div v-if="validationIssues.length" class="issue-list">
              <div v-for="issue in validationIssues" :key="`${issue.kind}-${issue.code}-${issue.field}`" class="issue-row" :class="issue.kind">
                <el-tag :type="issue.kind === 'error' ? 'danger' : 'warning'" size="small" effect="plain">
                  {{ issue.kind === 'error' ? '错误' : '提醒' }}
                </el-tag>
                <span>{{ issue.message }}</span>
                <code>{{ issue.field }}</code>
              </div>
            </div>
            <p v-else class="quiet-line">暂无校验问题</p>
          </section>

          <section class="detail-section">
            <div class="section-title"><strong>检查员复核</strong><span>{{ reviewerConfidence }}</span></div>
            <div v-if="detail.reviewer_report.decision" class="review-box">
              <div>
                <el-tag :type="detail.reviewer_report.decision === 'approve' ? 'success' : 'danger'" effect="dark">
                  {{ detail.reviewer_report.decision === 'approve' ? '复核通过' : '复核驳回' }}
                </el-tag>
                <span>{{ formatTime(detail.reviewer_report.reviewed_at) }}</span>
              </div>
              <p>{{ detail.reviewer_report.summary }}</p>
            </div>
            <p v-else class="quiet-line">等待独立复核</p>
          </section>

          <section class="detail-section timeline-section">
            <div class="section-title"><strong>审计时间线</strong><span>{{ detail.events.length }} 个事件</span></div>
            <el-timeline>
              <el-timeline-item
                v-for="event in detail.events"
                :key="event.id"
                :timestamp="formatTime(event.created_at)"
                :type="eventType(event.event_type)"
                placement="top"
              >
                <div class="timeline-event">
                  <strong>{{ eventLabel(event.event_type) }}</strong>
                  <span>{{ actorLabel(event.actor_id) }}</span>
                </div>
              </el-timeline-item>
            </el-timeline>
          </section>
        </template>
        <el-empty v-else description="选择一个财务作业查看详情" />
      </main>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { financeApi, type FinanceControlReadiness, type FinanceIntakeDetail, type FinanceIntakeJob } from '@/api/finance'

const loading = ref(false)
const jobs = ref<FinanceIntakeJob[]>([])
const readiness = ref<FinanceControlReadiness | null>(null)
const detail = ref<FinanceIntakeDetail | null>(null)
const selectedId = ref('')
const statusFilter = ref('')
const operationFilter = ref('')

const statusOptions = [
  { value: 'shadow_read', label: '等待抽取' },
  { value: 'needs_review', label: '等待复核' },
  { value: 'validated', label: '复核通过' },
  { value: 'rejected', label: '复核驳回' },
  { value: 'failed', label: '处理失败' },
]
const operationOptions = [
  { value: 'reimbursement', label: '报销' },
  { value: 'invoice', label: '发票' },
  { value: 'budget', label: '预算' },
  { value: 'payment', label: '付款' },
  { value: 'reconciliation', label: '对账' },
  { value: 'query', label: '查询' },
]
const statusLabels: Record<string, string> = {
  received: '已接入', shadow_read: '等待抽取', needs_review: '等待复核', validated: '复核通过',
  rejected: '复核驳回', failed: '处理失败', cancelled: '已取消', committed: '已入账',
}
const operationLabels: Record<string, string> = {
  reimbursement: '报销作业', invoice: '发票作业', budget: '预算作业', payment: '付款作业',
  reconciliation: '对账作业', query: '财务查询', unknown: '待识别作业',
}
const fieldLabels: Record<string, string> = {
  project_id: '财务项目', title: '标题', currency: '币种', total_amount: '总金额', items: '费用明细',
  invoice_numbers: '发票号码', invoice_number: '发票号码', invoice_code: '发票代码', invoice_date: '开票日期',
  amount: '金额', seller_name: '销方名称', buyer_name: '购方名称',
}

const visibleJobs = computed(() => jobs.value.filter(job => (
  (!statusFilter.value || job.status === statusFilter.value)
  && (!operationFilter.value || job.operation_type === operationFilter.value)
)))
const summaryCards = computed(() => [
  { key: 'all', label: '全部作业', value: jobs.value.length, tone: 'normal' },
  { key: 'extract', label: '等待抽取', value: jobs.value.filter(job => job.status === 'shadow_read').length, tone: 'warning' },
  { key: 'review', label: '等待复核', value: jobs.value.filter(job => job.status === 'needs_review').length, tone: 'warning' },
  { key: 'valid', label: '复核通过', value: jobs.value.filter(job => job.status === 'validated').length, tone: 'success' },
  { key: 'problem', label: '异常作业', value: jobs.value.filter(job => ['rejected', 'failed'].includes(job.status)).length, tone: 'danger' },
])
const normalizedEntries = computed(() => Object.entries(detail.value?.normalized_payload || {}))
const validationIssues = computed(() => [
  ...(detail.value?.validation_report.errors || []).map(item => ({ ...item, kind: 'error' })),
  ...(detail.value?.validation_report.warnings || []).map(item => ({ ...item, kind: 'warning' })),
])
const pipelineActive = computed(() => {
  if (!detail.value) return 0
  if (['validated', 'rejected', 'failed'].includes(detail.value.status)) return 3
  if (detail.value.status === 'needs_review') return 2
  return 1
})
const validationStepText = computed(() => {
  if (detail.value?.validation_report.valid === true) return '规则通过'
  if (detail.value?.validation_report.valid === false) return '存在阻断项'
  return '等待处理'
})
const reviewStepText = computed(() => {
  if (detail.value?.reviewer_report.decision === 'approve') return '检查员通过'
  if (detail.value?.reviewer_report.decision === 'reject') return '检查员驳回'
  return '等待检查员'
})
const reviewerConfidence = computed(() => {
  const value = detail.value?.reviewer_report.confidence
  return typeof value === 'number' ? `置信度 ${Math.round(value * 100)}%` : ''
})

function statusLabel(value: string) { return statusLabels[value] || value }
function operationLabel(value: string) { return operationLabels[value] || value }
function fieldLabel(value: string) { return fieldLabels[value] || value }
function statusType(value: string) {
  if (value === 'validated') return 'success'
  if (['rejected', 'failed'].includes(value)) return 'danger'
  if (['needs_review', 'shadow_read'].includes(value)) return 'warning'
  return 'info'
}
function eventType(value: string) {
  if (value === 'independent_review_completed') return 'success'
  if (value.endsWith('_failed')) return 'danger'
  if (value === 'extraction_submitted') return 'warning'
  return 'primary'
}
function eventLabel(value: string) {
  return ({
    received: '财务请求已接入', formal_snapshot_captured: '正式财务数据只读快照完成',
    extraction_submitted: '声波提交结构化抽取', independent_review_completed: '检查员完成独立复核',
    independent_review_failed: '独立复核失败',
  } as Record<string, string>)[value] || value
}
function actorLabel(value: string) {
  return ({ soundwave: '声波', inspector: '检查员', 'finance-intake': '财务暂存服务', 'finance-review-orchestrator': '复核调度器' } as Record<string, string>)[value] || value
}
function valueText(value: unknown) {
  if (value === null || value === undefined || value === '') return '-'
  if (Array.isArray(value)) return value.length ? JSON.stringify(value, null, 2) : '[]'
  if (typeof value === 'object') return JSON.stringify(value, null, 2)
  return String(value)
}
function formatTime(value?: string) {
  if (!value) return '-'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}

async function selectJob(id: string) {
  selectedId.value = id
  try {
    detail.value = await financeApi.intakeJob(id)
  } catch {
    detail.value = null
    ElMessage.error('财务作业详情加载失败')
  }
}
async function load() {
  loading.value = true
  try {
    const [nextJobs, nextReadiness] = await Promise.all([
      financeApi.intakeJobs({ limit: 500 }),
      financeApi.controlReadiness(),
    ])
    jobs.value = nextJobs
    readiness.value = nextReadiness
    const nextId = jobs.value.some(job => job.id === selectedId.value) ? selectedId.value : jobs.value[0]?.id || ''
    if (nextId) await selectJob(nextId)
    else { selectedId.value = ''; detail.value = null }
  } catch {
    ElMessage.error('财务作业队列加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.intake-workspace { display: flex; flex-direction: column; gap: 14px; min-width: 0; }
.mode-strip { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 14px 16px; border: 1px solid var(--el-border-color); border-radius: 6px; background: var(--el-bg-color-overlay); box-shadow: 0 8px 24px rgb(0 0 0 / 12%); }
.mode-title { display: flex; align-items: center; gap: 10px; font-size: 16px; font-weight: 700; }
.mode-strip p { margin: 5px 0 0; color: var(--el-text-color-secondary); font-size: 13px; }
.readiness-panel { padding: 14px 16px; border: 1px solid var(--el-border-color); border-radius: 6px; background: var(--el-bg-color-overlay); box-shadow: 0 8px 24px rgb(0 0 0 / 10%); }
.readiness-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.readiness-head p,.gate-note { margin: 5px 0 0; color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.6; }
.readiness-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 1px; margin-top: 12px; overflow: hidden; border: 1px solid var(--el-border-color); border-radius: 5px; background: var(--el-border-color); }
.readiness-grid > div { min-width: 0; padding: 10px 12px; background: var(--el-fill-color-light); }.readiness-grid span { display: block; color: var(--el-text-color-secondary); font-size: 11px; }.readiness-grid strong { display: block; margin-top: 5px; font-size: 16px; }
.readiness-checks { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 10px; }.readiness-checks span { padding: 4px 7px; border: 1px solid var(--el-color-danger-light-5); border-radius: 4px; color: var(--el-color-danger); font-size: 11px; }.readiness-checks span.passed { border-color: var(--el-color-success-light-5); color: var(--el-color-success); }
.summary-grid { display: grid; grid-template-columns: repeat(5, minmax(120px, 1fr)); border: 1px solid var(--el-border-color); border-radius: 6px; overflow: hidden; background: var(--el-bg-color-overlay); }
.summary-item { min-width: 0; padding: 13px 16px; border-right: 1px solid var(--el-border-color); }
.summary-item:last-child { border-right: 0; }
.summary-item span { display: block; color: var(--el-text-color-secondary); font-size: 12px; }
.summary-item strong { display: block; margin-top: 7px; font-size: 24px; line-height: 1; }
.tone-warning { color: var(--el-color-warning); }.tone-success { color: var(--el-color-success); }.tone-danger { color: var(--el-color-danger); }
.workbench-grid { display: grid; grid-template-columns: minmax(320px, 380px) minmax(0, 1fr); min-height: 660px; border: 1px solid var(--el-border-color); border-radius: 6px; overflow: hidden; background: var(--el-bg-color-overlay); box-shadow: 0 12px 30px rgb(0 0 0 / 14%); }
.queue-panel { min-width: 0; border-right: 1px solid var(--el-border-color); background: color-mix(in srgb, var(--el-bg-color) 88%, var(--el-color-primary) 12%); }
.panel-head { display: flex; align-items: center; justify-content: space-between; min-height: 52px; padding: 0 14px; border-bottom: 1px solid var(--el-border-color); }
.panel-head div { display: flex; align-items: baseline; gap: 8px; }.panel-head span { color: var(--el-text-color-secondary); font-size: 12px; }
.filters { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; padding: 12px; border-bottom: 1px solid var(--el-border-color); }
.job-list { display: flex; flex-direction: column; max-height: 738px; overflow: auto; }
.job-row { display: grid; grid-template-columns: 8px minmax(0, 1fr) auto; align-items: center; gap: 10px; width: 100%; min-height: 68px; padding: 10px 12px; border: 0; border-bottom: 1px solid var(--el-border-color-lighter); background: transparent; color: inherit; text-align: left; cursor: pointer; }
.job-row:hover { background: var(--el-fill-color-light); }.job-row.active { background: color-mix(in srgb, var(--el-color-primary) 14%, var(--el-bg-color)); box-shadow: inset 3px 0 var(--el-color-primary); }
.job-state { width: 7px; height: 7px; border-radius: 50%; background: var(--el-color-info); }.state-validated { background: var(--el-color-success); }.state-needs_review,.state-shadow_read { background: var(--el-color-warning); }.state-rejected,.state-failed { background: var(--el-color-danger); }
.job-main { min-width: 0; }.job-title,.job-meta { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.job-title { font-weight: 650; }.job-meta { margin-top: 6px; color: var(--el-text-color-secondary); font-size: 12px; }
.detail-panel { min-width: 0; padding: 18px 20px 26px; overflow: hidden; background: var(--el-bg-color); }
.detail-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; padding-bottom: 16px; border-bottom: 1px solid var(--el-border-color); }
.detail-title { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; font-size: 18px; }.job-id { display: block; margin-top: 7px; color: var(--el-text-color-secondary); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
.agent-chain { display: flex; align-items: center; gap: 7px; flex-wrap: wrap; color: var(--el-text-color-regular); font-size: 12px; }.agent-chain i { color: var(--el-color-primary); font-style: normal; }
.pipeline { padding: 24px 8px 20px; border-bottom: 1px solid var(--el-border-color); }
.detail-section { padding: 18px 0; border-bottom: 1px solid var(--el-border-color-lighter); }.detail-section:last-child { border-bottom: 0; }
.section-title { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; }.section-title span { color: var(--el-text-color-secondary); font-size: 12px; }
.request-box,.review-box { padding: 13px 14px; border: 1px solid var(--el-border-color); border-radius: 5px; background: var(--el-fill-color-light); line-height: 1.7; white-space: pre-wrap; }
.field-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }.field-item { min-width: 0; padding: 10px 12px; border: 1px solid var(--el-border-color-lighter); border-radius: 5px; background: var(--el-fill-color-light); }.field-item span { display: block; color: var(--el-text-color-secondary); font-size: 12px; }.field-item strong { display: block; margin-top: 6px; overflow: auto; color: var(--el-text-color-primary); font-family: inherit; font-size: 13px; font-weight: 500; line-height: 1.55; white-space: pre-wrap; }
.issue-list { display: flex; flex-direction: column; gap: 7px; }.issue-row { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 10px; padding: 9px 10px; border-radius: 5px; background: var(--el-fill-color-light); }.issue-row code { color: var(--el-text-color-secondary); font-size: 11px; }.quiet-line { margin: 0; color: var(--el-text-color-secondary); font-size: 13px; }
.review-box > div { display: flex; align-items: center; gap: 10px; }.review-box > div span { color: var(--el-text-color-secondary); font-size: 12px; }.review-box p { margin: 10px 0 0; }
.timeline-section :deep(.el-timeline) { padding-left: 8px; }.timeline-event { display: flex; align-items: center; justify-content: space-between; gap: 12px; }.timeline-event span { color: var(--el-text-color-secondary); font-size: 12px; }
@media (max-width: 1180px) { .readiness-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }.summary-grid { grid-template-columns: repeat(3, minmax(120px, 1fr)); }.summary-item { border-bottom: 1px solid var(--el-border-color); }.workbench-grid { grid-template-columns: 1fr; }.queue-panel { border-right: 0; border-bottom: 1px solid var(--el-border-color); }.job-list { max-height: 300px; } }
@media (max-width: 720px) { .summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }.mode-strip,.detail-head { align-items: flex-start; }.detail-head { flex-direction: column; }.filters,.field-grid { grid-template-columns: 1fr; }.detail-panel { padding: 14px 12px 20px; }.issue-row { grid-template-columns: auto minmax(0, 1fr); }.issue-row code { grid-column: 2; }.summary-item { border-right: 1px solid var(--el-border-color); } }
</style>
