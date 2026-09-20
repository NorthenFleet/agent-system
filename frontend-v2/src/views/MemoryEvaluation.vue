<template>
  <div class="memory-evaluation-page" v-loading="loading">
    <header class="page-header">
      <div>
        <p class="eyebrow">MEMORY RETRIEVAL GOVERNANCE</p>
        <h1>记忆检索评测</h1>
        <p>Shadow 排序不影响当前结果；只有在线指标和人工标注评测同时通过后，系统才会建议切流。</p>
      </div>
      <div class="header-actions">
        <el-button :icon="Refresh" @click="loadAll">刷新</el-button>
        <el-button :icon="MagicStick" :loading="generating" @click="generateDrafts">从权威记忆生成草稿</el-button>
        <el-button :icon="MagicStick" :loading="generatingVariants" @click="generateVariants">生成问法变体</el-button>
        <el-button type="primary" :icon="Plus" @click="openCreate">新建标注</el-button>
      </div>
    </header>

    <section class="gate-card" :class="{ ready: gate?.promotion_ready }">
      <div class="gate-state">
        <span>{{ gate?.promotion_ready ? '已满足切流条件' : '继续 Shadow 观测' }}</span>
        <strong>{{ gate?.promotion_ready ? 'READY' : 'BLOCKED' }}</strong>
        <small>系统不会自动切换排序策略</small>
      </div>
      <div class="metrics-grid">
        <article><span>真实查询</span><strong>{{ gate?.online.samples.queries || 0 }} / {{ gate?.online.samples.minimum_required || 100 }}</strong></article>
        <article><span>激活标注</span><strong>{{ gate?.offline.active_cases || 0 }} / {{ gate?.offline.minimum_required || 30 }}</strong></article>
        <article><span>向量可用率</span><strong>{{ percent(gate?.online.availability.vector_ready_rate) }}</strong></article>
        <article><span>向量 P95</span><strong>{{ number(gate?.online.latency_ms.vector.p95) }} ms</strong></article>
        <article><span>Context P95</span><strong>{{ number(gate?.online.latency_ms.total.p95) }} ms</strong></article>
        <article><span>Top-1 变化率</span><strong>{{ percent(gate?.online.ranking_change.top1_change_rate) }}</strong></article>
      </div>
      <div v-if="gate?.blockers?.length" class="blockers">
        <el-tag v-for="item in gate.blockers" :key="item" type="warning" effect="plain">{{ blockerLabel(item) }}</el-tag>
      </div>
    </section>

    <section v-if="coverage" class="coverage-card">
      <header>
        <div><span class="eyebrow">DATASET COVERAGE</span><h2>标注覆盖度</h2></div>
        <el-tag :type="coverage.remaining_active_cases === 0 ? 'success' : 'warning'">还需激活 {{ coverage.remaining_active_cases }} 条</el-tag>
      </header>
      <div class="coverage-grid">
        <article><span>权威记忆</span><strong>{{ coverage.approved_sources }}</strong><small>{{ coverage.sources_with_cases }} 条已有用例</small></article>
        <article><span>待审草稿</span><strong>{{ coverage.by_status.draft || 0 }}</strong><small>{{ coverage.review_ready_drafts }} 条完成审核清单</small></article>
        <article><span>已激活</span><strong>{{ coverage.by_status.active || 0 }}</strong><small>覆盖 {{ coverage.sources_with_active_cases }} 个记忆源</small></article>
        <article><span>安全反例</span><strong>{{ coverage.active_safety_negative_cases }} / {{ coverage.safety_negative_cases }}</strong><small>已激活 / 全部候选</small></article>
        <article><span>来源漂移</span><strong>{{ coverage.source_drift_cases }}</strong><small>{{ coverage.missing_source_cases }} 条来源缺失</small></article>
        <article><span>审计事件</span><strong>{{ coverage.audit_events }}</strong><small>创建、编辑和状态变更均留痕</small></article>
        <article class="variant-coverage"><span>问法类型</span><div><el-tag v-for="(count, key) in coverage.by_variant" :key="key" size="small" effect="plain">{{ variantLabel(String(key)) }} {{ count }}</el-tag></div></article>
      </div>
    </section>

    <section class="batch-card">
      <header>
        <div><span class="eyebrow">HUMAN REVIEW BATCH</span><h2>人工审核批次</h2></div>
        <el-tag v-if="reviewBatch" :type="reviewBatch.status === 'completed' ? 'success' : 'warning'">{{ reviewBatch.status === 'completed' ? '已完成' : '审核中' }}</el-tag>
      </header>
      <template v-if="reviewBatch">
        <el-progress :percentage="batchProgress" :status="reviewBatch.status === 'completed' ? 'success' : undefined" />
        <div class="batch-metrics">
          <span>已激活 <strong>{{ reviewBatch.active_cases }}</strong> / {{ reviewBatch.target_case_count }}</span>
          <span>来源覆盖 <strong>{{ reviewBatch.covered_approved_sources }}</strong> / {{ reviewBatch.approved_sources }}</span>
          <span>AI提案 <strong>{{ reviewBatch.proposal_count }}</strong> / {{ reviewBatch.target_case_count }}</span>
          <span>安全反例 <strong>{{ reviewBatch.active_safety_negative_cases }}</strong></span>
          <span>剩余 <strong>{{ reviewBatch.remaining_cases }}</strong></span>
        </div>
        <div class="batch-footer">
          <div><el-tag v-for="(count, key) in reviewBatch.by_variant" :key="key" size="small" effect="plain">{{ variantLabel(String(key)) }} {{ count }}</el-tag></div>
          <el-button type="primary" :disabled="!reviewBatch.next_case" @click="openNextBatchCase">审核下一条</el-button>
        </div>
      </template>
      <template v-else>
        <p>创建一个平衡的30条审核清单；系统只安排顺序和提供安全反例建议，不会代替人工审核。</p>
        <el-button type="primary" :loading="creatingBatch" @click="createReviewBatch">创建30条审核批次</el-button>
      </template>
    </section>

    <section class="toolbar-card">
      <el-radio-group v-model="statusFilter" @change="loadCases">
        <el-radio-button value="">全部</el-radio-button>
        <el-radio-button value="draft">待审核</el-radio-button>
        <el-radio-button value="active">已激活</el-radio-button>
        <el-radio-button value="archived">已归档</el-radio-button>
      </el-radio-group>
      <div>
        <span>当前 {{ cases.length }} 条</span>
        <el-button type="success" :icon="VideoPlay" :loading="running" :disabled="activeCount === 0" @click="runEvaluation">运行离线评测</el-button>
      </div>
    </section>

    <section class="cases-card">
      <el-table :data="cases" row-key="id" stripe>
        <el-table-column label="状态" width="100">
          <template #default="{ row }"><el-tag :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag></template>
        </el-table-column>
        <el-table-column label="业务问法" min-width="300">
          <template #default="{ row }"><strong class="query-text">{{ row.query }}</strong><small class="source-line"><el-tag size="small" effect="plain">{{ variantLabel(row.variant_key) }}</el-tag> {{ row.source_memory_ref || '手工标注' }}</small></template>
        </el-table-column>
        <el-table-column label="作用域" width="190">
          <template #default="{ row }"><span>{{ row.subject_user_id || row.owner_user_id }}</span><small class="source-line">{{ row.project_id || '用户级' }} · {{ row.agent_id }}</small></template>
        </el-table-column>
        <el-table-column label="标签" min-width="220">
          <template #default="{ row }"><div class="tag-list"><el-tag v-for="tag in row.tags" :key="tag" size="small" effect="plain">{{ tag }}</el-tag></div><small>期望 {{ row.expected_source_refs.length }} · 禁止 {{ row.forbidden_source_refs.length }}</small></template>
        </el-table-column>
        <el-table-column label="版本" width="88"><template #default="{ row }">V{{ row.version }}</template></el-table-column>
        <el-table-column label="置信度" width="100"><template #default="{ row }"><el-tag size="small" :type="confidenceType(row.reviewer_confidence)">{{ confidenceLabel(row.reviewer_confidence) }}</el-tag></template></el-table-column>
        <el-table-column label="操作" width="190" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" :icon="EditPen" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="row.status !== 'archived'" link type="danger" @click="archiveCase(row)">归档</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!cases.length && !loading" description="尚无标注用例，可从已审核记忆生成草稿" />
    </section>

    <section v-if="latestRun" class="run-card">
      <header><div><span class="eyebrow">LATEST OFFLINE RUN</span><h2>最新离线评测</h2></div><el-tag :type="latestRun.status === 'passed' ? 'success' : 'danger'">{{ latestRun.status === 'passed' ? '通过' : '阻断' }}</el-tag></header>
      <div class="run-metrics"><span>用例 {{ latestRun.case_count }}</span><span>Baseline Recall {{ metric(latestRun.baseline, 'recall_at_k') }}</span><span>RRF Recall {{ metric(latestRun.candidate, 'recall_at_k') }}</span><span>RRF MRR {{ metric(latestRun.candidate, 'mrr_at_k') }}</span><span>Forbidden {{ latestRun.candidate?.forbidden_hits ?? 0 }}</span></div>
    </section>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑评测用例' : '新建评测用例'" width="min(760px, 95vw)" destroy-on-close>
      <el-alert v-if="isGeneratedDraft" title="这是自动生成的草稿；激活前必须完成三项人工核对。" type="warning" show-icon :closable="false" />
      <section v-if="currentEvidence" class="evidence-card" :class="{ stale: currentIsStale }">
        <header><div><span class="eyebrow">SOURCE EVIDENCE</span><h3>{{ currentEvidence.title }}</h3></div><el-tag :type="currentIsStale ? 'danger' : 'success'">{{ currentIsStale ? '来源已变化' : '当前权威版本' }}</el-tag></header>
        <p>{{ currentEvidence.content }}</p>
        <small>{{ currentEvidence.source_ref }} · {{ currentEvidence.project_id || '用户级' }} · {{ currentEvidence.agent_id || '通用智能体' }}</small>
      </section>
      <section v-if="currentPlan?.proposal" class="proposal-card">
        <header><div><strong>AI改写提案</strong><small>待人工裁决，不属于正式标签</small></div><el-tag size="small" type="info">PENDING</el-tag></header>
        <p>{{ currentPlan.proposal.suggested_query }}</p>
        <small>{{ currentPlan.proposal.rationale }}</small>
        <el-button size="small" type="primary" plain @click="applyProposal">应用到表单（不保存）</el-button>
      </section>
      <section v-if="proposalForbiddenRefs.length" class="safety-suggestion">
        <div><strong>安全反例建议</strong><small>仅作为候选，加入后仍需人工核对</small></div>
        <div><el-tag v-for="ref in proposalForbiddenRefs" :key="ref" size="small" type="warning" effect="plain">{{ ref }}</el-tag></div>
        <el-button size="small" @click="applySafetySuggestions">加入禁止来源</el-button>
      </section>
      <el-form label-position="top" class="case-form">
        <el-form-item label="真实业务问法" required><el-input v-model="form.query" type="textarea" :rows="3" placeholder="使用业务人员真实会输入的表达" /></el-form-item>
        <div class="form-grid">
          <el-form-item label="被测用户 ID"><el-input v-model="form.subject_user_id" placeholder="留空使用当前用户" /></el-form-item>
          <el-form-item label="项目 ID"><el-input v-model="form.project_id" placeholder="留空为用户级" /></el-form-item>
          <el-form-item label="智能体"><el-input v-model="form.agent_id" /></el-form-item>
          <el-form-item label="Top-K"><el-input-number v-model="form.limit" :min="1" :max="50" /></el-form-item>
        </div>
        <el-form-item label="期望来源（每行一条）" required><el-input v-model="form.expected" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="禁止来源（每行一条）"><el-input v-model="form.forbidden" type="textarea" :rows="3" placeholder="跨用户、已归档、过期或冲突来源" /></el-form-item>
        <el-form-item label="标签（逗号分隔）"><el-input v-model="form.tags" /></el-form-item>
        <el-form-item label="审核备注"><el-input v-model="form.notes" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="审核置信度" required>
          <el-radio-group v-model="form.reviewer_confidence">
            <el-radio-button value="unreviewed">未审核</el-radio-button>
            <el-radio-button value="medium">中</el-radio-button>
            <el-radio-button value="high">高</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="isGeneratedDraft" label="人工审核清单" required>
          <el-checkbox v-model="form.review_checks.query_rewritten">已改写成真实业务问法</el-checkbox>
          <el-checkbox v-model="form.review_checks.scope_verified">已核对被测用户、项目和智能体</el-checkbox>
          <el-checkbox v-model="form.review_checks.labels_verified">已核对期望与禁止来源</el-checkbox>
        </el-form-item>
        <el-form-item v-if="caseEvents.length" label="审计轨迹">
          <div class="audit-list"><span v-for="event in caseEvents" :key="event.id">V{{ event.case_version }} · {{ eventLabel(event.event_type) }} · {{ event.actor }} · {{ formatTime(event.created_at) }}</span></div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button :loading="saving" @click="saveCase('draft')">保存草稿</el-button>
        <el-button type="primary" :loading="saving" @click="saveCase('active')">确认并激活</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { EditPen, MagicStick, Plus, Refresh, VideoPlay } from '@element-plus/icons-vue'
import {
  createMemoryEvaluationReviewBatch,
  createMemoryEvaluationCase,
  generateMemoryEvaluationDrafts,
  generateMemoryEvaluationVariants,
  getLatestMemoryRetrievalEvaluation,
  getLatestMemoryEvaluationReviewBatch,
  getMemoryEvaluationCaseEvents,
  getMemoryEvaluationCoverage,
  getMemoryEvaluationReviewQueue,
  getMemoryRolloutGate,
  listMemoryEvaluationCases,
  runMemoryRetrievalEvaluation,
  updateMemoryEvaluationCase,
  type EvaluationCaseStatus,
  type EvaluationCoverage,
  type EvaluationCaseEvent,
  type EvaluationReviewQueue,
  type EvaluationReviewBatch,
  type EvaluationRun,
  type MemoryEvaluationCase,
  type MemoryEvaluationCasePayload,
  type RolloutGate
} from '@/api/memoryEvaluation'

const cases = ref<MemoryEvaluationCase[]>([])
const gate = ref<RolloutGate | null>(null)
const coverage = ref<EvaluationCoverage | null>(null)
const reviewQueue = ref<EvaluationReviewQueue | null>(null)
const reviewBatch = ref<EvaluationReviewBatch | null>(null)
const caseEvents = ref<EvaluationCaseEvent[]>([])
const latestRun = ref<EvaluationRun | null>(null)
const loading = ref(false), generating = ref(false), generatingVariants = ref(false), creatingBatch = ref(false), running = ref(false), saving = ref(false)
const statusFilter = ref('')
const dialogVisible = ref(false), editingId = ref('')
const emptyForm = () => ({ subject_user_id: '', origin: 'manual', source_memory_ref: '', variant_key: 'canonical', query: '', project_id: '', agent_id: 'optimus', limit: 10, expected: '', forbidden: '', tags: '', notes: '', reviewer_confidence: 'unreviewed' as 'unreviewed' | 'medium' | 'high', source_snapshot_hash: '', review_checks: { query_rewritten: false, scope_verified: false, labels_verified: false } })
const form = reactive(emptyForm())
const activeCount = computed(() => cases.value.filter(item => item.status === 'active').length || gate.value?.offline.active_cases || 0)
const isGeneratedDraft = computed(() => form.origin.startsWith('approved_memory_'))
const currentEvidence = computed(() => reviewQueue.value?.sources.find(item => item.source_ref === form.source_memory_ref) || null)
const currentIsStale = computed(() => Boolean(editingId.value && reviewQueue.value?.stale_case_ids.includes(editingId.value)))
const currentPlan = computed(() => reviewBatch.value?.review_plan.find(item => item.case_id === editingId.value) || null)
const proposalForbiddenRefs = computed(() => currentPlan.value?.proposal?.suggested_forbidden_source_refs || currentPlan.value?.suggested_forbidden_source_refs || [])
const batchProgress = computed(() => reviewBatch.value ? Math.round((reviewBatch.value.active_cases / reviewBatch.value.target_case_count) * 100) : 0)
const lines = (value: string) => value.split(/\n|,|，/).map(item => item.trim()).filter(Boolean)
const percent = (value?: number) => `${((value || 0) * 100).toFixed(1)}%`
const number = (value?: number) => Number(value || 0).toFixed(1)
const metric = (value: Record<string, any>, key: string) => Number(value?.[key] || 0).toFixed(3)
const statusLabel = (value: string) => ({ draft: '待审核', active: '已激活', archived: '已归档' }[value] || value)
const statusType = (value: string) => ({ draft: 'warning', active: 'success', archived: 'info' } as Record<string, any>)[value] || 'info'
const blockerLabel = (value: string) => ({ 'online:minimum_queries': '在线样本不足', 'online:vector_availability': '向量可用率未达标', 'online:vector_p95_latency': '向量延迟未达标', 'online:total_p95_latency': '总延迟未达标', 'offline:evaluation_exists': '缺少离线评测', 'offline:minimum_labeled_cases': '激活标注不足', 'offline:dataset_current': '评测数据集已变更', 'offline:quality_gate_passed': '离线质量门禁未通过', 'offline:source_evidence_current': '存在来源漂移', 'offline:approved_source_coverage': '权威记忆覆盖不足', 'offline:safety_negative_coverage': '缺少安全反例' } as Record<string, string>)[value] || value
const variantLabel = (value: string) => ({ canonical: '标准问法', natural: '自然问法', terse: '简短问法', contextual: '上下文问法', boundary: '边界问法' } as Record<string, string>)[value] || value
const confidenceLabel = (value: string) => ({ unreviewed: '未审核', medium: '中', high: '高' } as Record<string, string>)[value] || value
const confidenceType = (value: string) => ({ unreviewed: 'info', medium: 'warning', high: 'success' } as Record<string, any>)[value] || 'info'
const eventLabel = (value: string) => value === 'created' ? '创建' : value === 'updated' ? '编辑' : value === 'imported' ? '迁移建档' : value.replace('status:', '状态 ')
const formatTime = (value: string) => value ? new Date(value).toLocaleString('zh-CN') : '-'

async function loadCases() { cases.value = (await listMemoryEvaluationCases(statusFilter.value)).cases }
async function loadAll() {
  loading.value = true
  try {
    const [caseData, gateData, runData, coverageData, queueData, batchData] = await Promise.all([listMemoryEvaluationCases(statusFilter.value), getMemoryRolloutGate(), getLatestMemoryRetrievalEvaluation(), getMemoryEvaluationCoverage(), getMemoryEvaluationReviewQueue(), getLatestMemoryEvaluationReviewBatch()])
    cases.value = caseData.cases; gate.value = gateData; latestRun.value = runData.run; coverage.value = coverageData; reviewQueue.value = queueData; reviewBatch.value = batchData.batch
  } finally { loading.value = false }
}
function assignForm(item?: MemoryEvaluationCase) {
  Object.assign(form, emptyForm(), item ? { subject_user_id: item.subject_user_id, origin: item.origin, source_memory_ref: item.source_memory_ref, variant_key: item.variant_key, query: item.query, project_id: item.project_id, agent_id: item.agent_id, limit: item.limit, expected: item.expected_source_refs.join('\n'), forbidden: item.forbidden_source_refs.join('\n'), tags: item.tags.join(', '), notes: item.notes, reviewer_confidence: item.reviewer_confidence || 'unreviewed', source_snapshot_hash: item.source_snapshot_hash || '', review_checks: { ...emptyForm().review_checks, ...item.review_checks } } : {})
}
function openCreate() { editingId.value = ''; caseEvents.value = []; assignForm(); dialogVisible.value = true }
async function openEdit(item: MemoryEvaluationCase) { editingId.value = item.id; assignForm(item); dialogVisible.value = true; caseEvents.value = (await getMemoryEvaluationCaseEvents(item.id)).events }
async function openNextBatchCase() { if (reviewBatch.value?.next_case) await openEdit(reviewBatch.value.next_case) }
function applySafetySuggestions() { form.forbidden = [...new Set([...lines(form.forbidden), ...proposalForbiddenRefs.value])].join('\n'); ElMessage.info('已加入候选禁止来源，请逐条核对后再确认标签') }
function applyProposal() { if (!currentPlan.value?.proposal) return; form.query = currentPlan.value.proposal.suggested_query; form.forbidden = [...new Set([...lines(form.forbidden), ...proposalForbiddenRefs.value])].join('\n'); ElMessage.info('AI提案已填入表单，尚未保存，也未完成任何审核项') }
function payload(status: EvaluationCaseStatus): MemoryEvaluationCasePayload { return { subject_user_id: form.subject_user_id, origin: form.origin, source_memory_ref: form.source_memory_ref, variant_key: form.variant_key, query: form.query.trim(), project_id: form.project_id, agent_id: form.agent_id, limit: form.limit, expected_source_refs: lines(form.expected), forbidden_source_refs: lines(form.forbidden), tags: lines(form.tags), notes: form.notes, reviewer_confidence: form.reviewer_confidence, review_checks: { ...form.review_checks }, status } }
async function saveCase(status: EvaluationCaseStatus) {
  const data = payload(status)
  if (!data.query || (!data.expected_source_refs.length && !data.forbidden_source_refs.length)) return ElMessage.warning('请填写业务问法，并至少标注一条期望或禁止来源')
  if (status === 'active' && !Object.values(form.review_checks).every(Boolean)) return ElMessage.warning('请先完成三项人工审核清单')
  if (status === 'active' && !['medium', 'high'].includes(form.reviewer_confidence)) return ElMessage.warning('请选择中或高审核置信度')
  if (status === 'active' && currentIsStale.value) return ElMessage.warning('权威记忆内容已变化，请先保存为草稿并重新审核')
  if (status === 'active' && !await confirmAction('激活后该用例将进入切流门禁。请确认问法、被测用户和来源标签已经人工核对。', '确认激活评测用例', '已核对，激活')) return
  saving.value = true
  try { if (editingId.value) await updateMemoryEvaluationCase(editingId.value, data); else await createMemoryEvaluationCase(data); dialogVisible.value = false; await loadAll(); ElMessage.success(status === 'active' ? '评测用例已激活' : '草稿已保存') } finally { saving.value = false }
}
async function confirmAction(message: string, title: string, confirmButtonText: string) {
  try {
    await ElMessageBox.confirm(message, title, { type: 'warning', confirmButtonText, cancelButtonText: '取消' })
    return true
  } catch {
    return false
  }
}
async function archiveCase(item: MemoryEvaluationCase) {
  if (!await confirmAction('归档后该用例不再参与离线评测和切流门禁。', '确认归档评测用例', '确认归档')) return
  await updateMemoryEvaluationCase(item.id, { ...item, status: 'archived' })
  await loadAll()
  ElMessage.success('用例已归档')
}
async function generateDrafts() { generating.value = true; try { const result = await generateMemoryEvaluationDrafts(); await loadAll(); ElMessage.success(`新建 ${result.drafts_created} 条草稿，跳过 ${result.drafts_skipped} 条已存在记忆`) } finally { generating.value = false } }
async function generateVariants() { generatingVariants.value = true; try { const result = await generateMemoryEvaluationVariants(); await loadAll(); ElMessage.success(`新建 ${result.drafts_created} 条问法变体，跳过 ${result.drafts_skipped} 条已存在变体`) } finally { generatingVariants.value = false } }
async function createReviewBatch() {
  if (!await confirmAction('将从候选池中平衡选择30条，创建持久化审核顺序。此操作不会自动修改或激活任何用例。', '创建人工审核批次', '创建批次')) return
  creatingBatch.value = true
  try { reviewBatch.value = await createMemoryEvaluationReviewBatch(30); await loadAll(); ElMessage.success('30条人工审核批次已创建') } finally { creatingBatch.value = false }
}
async function runEvaluation() {
  if (!await confirmAction(`将对 ${activeCount.value} 条已激活用例执行基线/RRF 对比。评测不会写入 Context Pack，是否继续？`, '运行离线评测', '开始评测')) return
  running.value = true
  try { latestRun.value = await runMemoryRetrievalEvaluation(); await loadAll(); ElMessage.success(latestRun.value.status === 'passed' ? '离线评测已通过' : '评测完成，存在阻断项') } finally { running.value = false }
}
onMounted(loadAll)
</script>

<style scoped>
.memory-evaluation-page{max-width:1500px;margin:0 auto;color:var(--text-primary)}.page-header{display:flex;justify-content:space-between;gap:20px;align-items:flex-start;margin-bottom:18px}.page-header h1{margin:2px 0 6px;font-size:26px}.page-header p{margin:0;color:var(--text-secondary);line-height:1.6}.eyebrow{font-size:11px!important;letter-spacing:.12em;color:var(--view-color)!important}.header-actions{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}.gate-card,.coverage-card,.toolbar-card,.cases-card,.run-card{border:1px solid var(--line-color);border-radius:9px;background:var(--panel-bg)}.gate-card{display:grid;grid-template-columns:220px 1fr;gap:18px;padding:18px;margin-bottom:14px;border-left:4px solid #d29922}.gate-card.ready{border-left-color:#3fb950}.gate-state{display:flex;flex-direction:column;justify-content:center}.gate-state span,.metrics-grid span,.source-line,.toolbar-card span,.tag-list+small,.coverage-grid span,.coverage-grid small{color:var(--text-secondary);font-size:12px}.gate-state strong{margin:7px 0;font-size:28px;color:#d29922}.gate-card.ready .gate-state strong{color:#3fb950}.gate-state small{color:var(--text-secondary);line-height:1.4}.metrics-grid{display:grid;grid-template-columns:repeat(3,minmax(130px,1fr));gap:10px}.metrics-grid article{padding:11px 13px;border:1px solid var(--line-color);border-radius:7px;background:var(--card-bg-soft)}.metrics-grid strong{display:block;margin-top:6px;font-size:18px}.blockers{grid-column:1/-1;display:flex;flex-wrap:wrap;gap:7px}.coverage-card{padding:16px 18px;margin-bottom:14px}.coverage-card header{display:flex;align-items:center;justify-content:space-between}.coverage-card h2{margin:3px 0 0;font-size:18px}.coverage-grid{display:grid;grid-template-columns:repeat(3,minmax(130px,1fr)) 2fr;gap:10px;margin-top:13px}.coverage-grid article{padding:11px 13px;border:1px solid var(--line-color);border-radius:7px;background:var(--card-bg-soft)}.coverage-grid strong{display:block;margin:5px 0;font-size:22px}.variant-coverage div{display:flex;flex-wrap:wrap;gap:6px;margin-top:9px}.toolbar-card{display:flex;justify-content:space-between;align-items:center;padding:12px 14px;margin-bottom:12px}.toolbar-card>div{display:flex;align-items:center;gap:12px}.cases-card{overflow:hidden}.query-text{display:block;line-height:1.5}.source-line{display:block;margin-top:5px;word-break:break-all}.tag-list{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:5px}.run-card{margin-top:14px;padding:16px 18px}.run-card header{display:flex;justify-content:space-between;align-items:center}.run-card h2{margin:3px 0 0;font-size:18px}.run-metrics{display:flex;gap:18px;flex-wrap:wrap;margin-top:14px;color:var(--text-secondary)}.evidence-card{margin-top:14px;padding:14px;border:1px solid #3fb950;border-radius:8px;background:var(--card-bg-soft)}.evidence-card.stale{border-color:#f56c6c}.evidence-card header{display:flex;justify-content:space-between;gap:12px}.evidence-card h3{margin:3px 0 0}.evidence-card p{white-space:pre-wrap;line-height:1.65}.evidence-card small{color:var(--text-secondary);word-break:break-all}.case-form{margin-top:14px}.form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 14px}.audit-list{display:flex;flex-direction:column;gap:6px;width:100%;color:var(--text-secondary);font-size:12px}@media(max-width:1100px){.coverage-grid{grid-template-columns:repeat(2,minmax(130px,1fr))}}@media(max-width:900px){.page-header{flex-direction:column}.header-actions{justify-content:flex-start}.gate-card{grid-template-columns:1fr}.metrics-grid{grid-template-columns:repeat(2,minmax(120px,1fr))}.toolbar-card{align-items:flex-start;flex-direction:column;gap:12px}.form-grid{grid-template-columns:1fr}}@media(max-width:560px){.metrics-grid,.coverage-grid{grid-template-columns:1fr}}
.batch-card{margin-bottom:14px;padding:16px 18px;border:1px solid var(--line-color);border-left:4px solid #409eff;border-radius:9px;background:var(--panel-bg)}.batch-card header,.batch-footer{display:flex;align-items:center;justify-content:space-between;gap:12px}.batch-card h2{margin:3px 0 12px;font-size:18px}.batch-card>p{color:var(--text-secondary)}.batch-metrics{display:flex;gap:24px;flex-wrap:wrap;margin:12px 0;color:var(--text-secondary)}.batch-metrics strong{color:var(--text-primary)}.batch-footer>div{display:flex;gap:6px;flex-wrap:wrap}.safety-suggestion{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:12px;padding:12px;border:1px dashed #e6a23c;border-radius:8px;background:var(--card-bg-soft)}.safety-suggestion>div{display:flex;gap:6px;flex-wrap:wrap}.safety-suggestion small{display:block;color:var(--text-secondary)}
.proposal-card{display:grid;gap:9px;margin-top:12px;padding:13px;border:1px solid #409eff;border-radius:8px;background:var(--card-bg-soft)}.proposal-card header{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.proposal-card header div{display:grid;gap:3px}.proposal-card p{margin:0;line-height:1.6}.proposal-card small{color:var(--text-secondary)}.proposal-card .el-button{justify-self:start}
</style>
