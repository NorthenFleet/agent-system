<template>
  <section v-loading="loading" class="reimbursement-page">
    <header class="mode-bar">
      <el-segmented v-model="mode" :options="modeOptions" />
      <div class="mode-summary">
        <span>待我审批</span>
        <strong>{{ approvalTasks.length }}</strong>
      </div>
    </header>

    <template v-if="mode === 'records'">
      <div class="toolbar">
        <el-button type="primary" @click="openCreate">新建报销</el-button>
        <el-select v-model="status" clearable placeholder="全部状态" @change="loadRecords">
          <el-option v-for="item in statuses" :key="item" :label="statusLabel(item)" :value="item" />
        </el-select>
      </div>
      <div class="layout">
        <el-card class="list" shadow="never">
          <article v-for="item in records" :key="item.id" :class="{ active: selected?.id === item.id }" @click="selected = item">
            <div>
              <b>{{ item.title }}</b>
              <small>{{ item.reimbursement_no }}</small>
            </div>
            <div class="record-state">
              <strong>{{ formatMoney(item.total_amount) }}</strong>
              <el-tag size="small" :type="statusType(item.status)">{{ statusLabel(item.status) }}</el-tag>
            </div>
          </article>
          <el-empty v-if="!records.length" description="暂无报销单" />
        </el-card>

        <el-card v-if="selected" class="detail" shadow="never">
          <template #header>
            <div class="detail-header">
              <div>
                <b>{{ selected.title }}</b>
                <small>{{ selected.reimbursement_no }}</small>
              </div>
              <div class="detail-actions">
                <el-button v-if="['draft', 'returned'].includes(selected.status)" @click="itemDialog = true">新增明细</el-button>
                <el-button v-if="selected.status === 'draft'" type="primary" @click="submit">提交审批</el-button>
                <el-button v-if="selected.status === 'returned'" @click="redraft">转回草稿</el-button>
                <el-button v-if="selected.status === 'paid'" type="success" @click="archive">归档</el-button>
              </div>
            </div>
          </template>
          <el-descriptions :column="3" border>
            <el-descriptions-item label="状态">{{ statusLabel(selected.status) }}</el-descriptions-item>
            <el-descriptions-item label="金额">{{ formatMoney(selected.total_amount) }}</el-descriptions-item>
            <el-descriptions-item label="版本">{{ selected.lock_version }}</el-descriptions-item>
          </el-descriptions>
          <el-table :data="selected.items" class="items">
            <el-table-column prop="description" label="说明" />
            <el-table-column prop="vendor" label="供应商" />
            <el-table-column prop="expense_date" label="日期" width="110" />
            <el-table-column label="金额" width="130"><template #default="{ row }">{{ formatMoney(row.amount) }}</template></el-table-column>
          </el-table>
          <section v-if="selected.approval" class="approval-flow">
            <div class="section-title">
              <b>审批进度</b>
              <span>{{ selected.approval.tasks.filter(task => task.status === 'approved').length }} / {{ selected.approval.tasks.length }} 步</span>
            </div>
            <div class="approval-steps">
              <div v-for="task in selected.approval.tasks" :key="task.id" class="approval-step">
                <span class="step-order">{{ task.step_order }}</span>
                <div><b>{{ task.assignee_role || `用户 ${task.assignee_user_id}` }}</b><small>{{ taskStatusLabel(task.status) }}</small></div>
              </div>
            </div>
            <el-timeline v-if="selected.approval.events?.length" class="timeline">
              <el-timeline-item v-for="(event, index) in selected.approval.events" :key="index" :timestamp="String(event.created_at || '')">
                {{ eventLabel(String(event.action || '')) }}<span v-if="event.comment"> · {{ event.comment }}</span>
              </el-timeline-item>
            </el-timeline>
          </section>
        </el-card>
      </div>
    </template>

    <template v-else>
      <div class="approval-queue">
        <article v-for="task in approvalTasks" :key="task.id" class="approval-card">
          <div class="approval-card-main">
            <div class="approval-card-heading">
              <div>
                <span class="eyebrow">第 {{ task.step_order }} 级审批</span>
                <h3>{{ task.reimbursement?.title || '报销审批任务' }}</h3>
              </div>
              <strong>{{ formatMoney(task.reimbursement?.total_amount) }}</strong>
            </div>
            <dl>
              <div><dt>项目</dt><dd>{{ task.reimbursement?.project_name || task.reimbursement?.project_id || '-' }}</dd></div>
              <div><dt>单号</dt><dd>{{ task.reimbursement?.reimbursement_no || '-' }}</dd></div>
              <div><dt>申请人</dt><dd>用户 {{ task.reimbursement?.applicant_user_id || '-' }}</dd></div>
              <div><dt>分配方式</dt><dd>{{ task.assignee_role ? `角色：${task.assignee_role}` : `用户：${task.assignee_user_id}` }}</dd></div>
            </dl>
          </div>
          <div class="approval-card-actions">
            <el-button type="success" @click="act(task, 'approve')">通过</el-button>
            <el-button type="warning" @click="act(task, 'return')">退回补充</el-button>
            <el-button type="danger" plain @click="act(task, 'reject')">拒绝</el-button>
          </div>
        </article>
        <el-empty v-if="!approvalTasks.length" description="当前没有待审批任务" />
      </div>
    </template>

    <el-dialog v-model="createDialog" title="新建报销单" width="520px">
      <el-form label-width="90px">
        <el-form-item label="项目"><el-select v-model="createForm.project_id"><el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" /></el-select></el-form-item>
        <el-form-item label="标题"><el-input v-model="createForm.title" /></el-form-item>
        <el-form-item label="说明"><el-input v-model="createForm.description" type="textarea" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="createDialog = false">取消</el-button><el-button type="primary" @click="createRecord">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="itemDialog" title="新增报销明细" width="560px">
      <el-form label-width="90px">
        <el-form-item label="预算科目"><el-select v-model="itemForm.budget_line_id"><el-option v-for="line in availableLines" :key="line.id" :label="`${line.category} · 可用 ${formatMoney(Number(line.amount) - Number(line.reserved_amount) - Number(line.spent_amount))}`" :value="line.id" /></el-select></el-form-item>
        <el-form-item label="支出说明"><el-input v-model="itemForm.description" /></el-form-item>
        <el-form-item label="供应商"><el-input v-model="itemForm.vendor" /></el-form-item>
        <el-form-item label="日期"><el-date-picker v-model="itemForm.expense_date" value-format="YYYY-MM-DD" /></el-form-item>
        <el-form-item label="金额"><el-input-number v-model="itemForm.amount" :min="0.01" :precision="2" /></el-form-item>
        <el-form-item label="发票"><el-select v-model="itemForm.invoice_id" clearable><el-option v-for="invoice in invoices" :key="invoice.id" :label="`${invoice.invoice_number || invoice.id} · ${formatMoney(invoice.amount)}`" :value="invoice.id" /></el-select></el-form-item>
      </el-form>
      <template #footer><el-button @click="itemDialog = false">取消</el-button><el-button type="primary" @click="addItem">保存</el-button></template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  financeApi,
  formatMoney,
  type ApprovalTask,
  type BudgetLine,
  type BudgetVersion,
  type FinanceProject,
  type Invoice,
  type Reimbursement,
} from '@/api/finance'

const loading = ref(false)
const mode = ref<'records' | 'approvals'>('records')
const status = ref('')
const records = ref<Reimbursement[]>([])
const approvalTasks = ref<ApprovalTask[]>([])
const selected = ref<Reimbursement | null>(null)
const projects = ref<FinanceProject[]>([])
const budgets = ref<BudgetVersion[]>([])
const invoices = ref<Invoice[]>([])
const createDialog = ref(false)
const itemDialog = ref(false)
const modeOptions = [
  { label: '报销单', value: 'records' },
  { label: '待我审批', value: 'approvals' },
]
const statuses = ['draft', 'submitted', 'in_review', 'returned', 'approved', 'payment_pending', 'paid', 'archived', 'rejected', 'cancelled']
const createForm = reactive({ project_id: '', title: '', description: '' })
const itemForm = reactive({ budget_line_id: '', description: '', vendor: '', expense_date: '', amount: 0, invoice_id: '' })
const availableLines = computed<BudgetLine[]>(() => budgets.value
  .filter(budget => budget.project_id === selected.value?.project_id && budget.status === 'approved')
  .flatMap(budget => budget.lines))

const statusNames: Record<string, string> = {
  draft: '草稿', submitted: '已提交', in_review: '审批中', returned: '已退回', approved: '审批通过',
  payment_pending: '待付款', paid: '已付款', archived: '已归档', rejected: '已拒绝', cancelled: '已取消',
}

function statusLabel(value: string) { return statusNames[value] || value }
function taskStatusLabel(value: string) { return ({ pending: '待处理', approved: '已通过', returned: '已退回', rejected: '已拒绝' } as Record<string, string>)[value] || value }
function eventLabel(value: string) { return ({ submit: '提交审批', approve: '审批通过', return: '退回补充', reject: '审批拒绝' } as Record<string, string>)[value] || value }
function statusType(value: string): 'success' | 'warning' | 'danger' | 'info' {
  if (['approved', 'paid', 'archived'].includes(value)) return 'success'
  if (['submitted', 'in_review', 'payment_pending'].includes(value)) return 'warning'
  if (['rejected', 'cancelled'].includes(value)) return 'danger'
  return 'info'
}

async function loadRecords() {
  records.value = await financeApi.reimbursements(status.value || undefined)
  selected.value = selected.value
    ? records.value.find(record => record.id === selected.value?.id) || records.value[0] || null
    : records.value[0] || null
}

async function load() {
  loading.value = true
  try {
    [records.value, approvalTasks.value, budgets.value, invoices.value] = await Promise.all([
      financeApi.reimbursements(status.value || undefined),
      financeApi.approvalTasks(),
      financeApi.budgets(),
      financeApi.invoices(),
    ])
    selected.value = records.value.find(record => record.id === selected.value?.id) || records.value[0] || null
  } finally {
    loading.value = false
  }
}

async function openCreate() {
  projects.value = await financeApi.projects()
  createForm.project_id = projects.value[0]?.id || ''
  createDialog.value = true
}

async function createRecord() {
  const item = await financeApi.createReimbursement(createForm)
  createDialog.value = false
  await load()
  selected.value = records.value.find(record => record.id === item.id) || item
  ElMessage.success('报销草稿已创建')
}

async function addItem() {
  if (!selected.value) return
  selected.value = await financeApi.addReimbursementItem(selected.value.id, { ...itemForm, invoice_id: itemForm.invoice_id || null })
  itemDialog.value = false
  await load()
  ElMessage.success('报销明细已添加')
}

async function submit() {
  if (!selected.value) return
  await ElMessageBox.confirm('提交后将锁定当前内容、占用项目预算并进入分级审批，确认继续？', '提交审批', { type: 'warning' })
  selected.value = await financeApi.submitReimbursement(selected.value.id, selected.value.lock_version)
  await load()
  ElMessage.success('报销已提交审批')
}

async function redraft() {
  if (!selected.value) return
  selected.value = await financeApi.redraftReimbursement(selected.value.id, selected.value.lock_version)
  await load()
}

async function archive() {
  if (!selected.value) return
  selected.value = await financeApi.archiveReimbursement(selected.value.id, selected.value.lock_version)
  await load()
  ElMessage.success('已归档')
}

async function act(task: ApprovalTask, action: 'approve' | 'return' | 'reject') {
  const label = action === 'approve' ? '通过' : action === 'return' ? '退回补充' : '拒绝'
  const { value } = await ElMessageBox.prompt(
    action === 'approve' ? '可填写审批意见。' : '请填写处理原因，内容将进入审计记录。',
    `${label}审批`,
    {
      inputPlaceholder: '审批意见',
      inputValidator: input => action === 'approve' || Boolean(String(input || '').trim()) || '退回或拒绝必须填写原因',
      confirmButtonText: label,
      cancelButtonText: '取消',
      type: action === 'approve' ? 'success' : 'warning',
    },
  )
  await financeApi.actApproval(task.id, action, String(value || ''))
  await load()
  ElMessage.success(`审批已${label}`)
}

onMounted(load)
</script>

<style scoped>
.reimbursement-page { display: grid; gap: 16px; }
.mode-bar { display: flex; align-items: center; justify-content: space-between; padding: 12px 14px; border: 1px solid var(--el-border-color); background: var(--el-fill-color-lighter); border-radius: 6px; }
.mode-summary { display: flex; align-items: baseline; gap: 8px; color: var(--el-text-color-secondary); }
.mode-summary strong { color: var(--el-color-warning); font-size: 22px; }
.toolbar { display: flex; gap: 10px; }
.toolbar .el-select { width: 180px; }
.layout { display: grid; grid-template-columns: 360px minmax(0, 1fr); gap: 16px; }
.list article { display: flex; justify-content: space-between; gap: 12px; padding: 12px; border: 1px solid var(--el-border-color); border-radius: 6px; margin-bottom: 8px; cursor: pointer; }
.list article.active { border-color: var(--el-color-primary); background: var(--el-color-primary-light-9); }
.list article > div { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
.list b, .list small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.record-state { align-items: flex-end; flex: 0 0 auto; }
.list small, .detail-header small, .approval-step small { display: block; color: var(--el-text-color-secondary); margin-top: 4px; }
.detail-header { display: flex; justify-content: space-between; align-items: center; gap: 16px; }
.detail-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
.detail-actions .el-button + .el-button { margin-left: 0; }
.items { margin-top: 16px; }
.approval-flow { margin-top: 22px; padding-top: 18px; border-top: 1px solid var(--el-border-color); }
.section-title { display: flex; justify-content: space-between; margin-bottom: 14px; }
.section-title span { color: var(--el-text-color-secondary); }
.approval-steps { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 8px; }
.approval-step { display: flex; align-items: center; gap: 10px; padding: 10px; border: 1px solid var(--el-border-color); border-radius: 6px; }
.step-order { display: grid; place-items: center; width: 28px; height: 28px; border-radius: 50%; background: var(--el-color-primary-light-8); color: var(--el-color-primary); font-weight: 700; }
.timeline { margin-top: 20px; }
.approval-queue { display: grid; gap: 12px; }
.approval-card { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 18px; padding: 18px; border: 1px solid var(--el-border-color); background: var(--el-bg-color-overlay); border-radius: 6px; box-shadow: var(--el-box-shadow-light); }
.approval-card-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.approval-card-heading h3 { margin: 4px 0 0; font-size: 17px; }
.approval-card-heading > strong { color: var(--el-color-primary); font-size: 20px; }
.eyebrow { color: var(--el-text-color-secondary); font-size: 12px; }
.approval-card dl { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin: 16px 0 0; }
.approval-card dl div { min-width: 0; }
.approval-card dt { color: var(--el-text-color-secondary); font-size: 12px; }
.approval-card dd { margin: 5px 0 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.approval-card-actions { display: flex; align-items: center; gap: 8px; }
.approval-card-actions .el-button + .el-button { margin-left: 0; }
@media (max-width: 1180px) {
  .layout { grid-template-columns: 1fr; }
  .approval-card { grid-template-columns: 1fr; }
  .approval-card-actions { justify-content: flex-end; }
}
@media (max-width: 720px) {
  .mode-bar, .detail-header { align-items: flex-start; flex-direction: column; }
  .approval-card dl { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .approval-card-actions { flex-wrap: wrap; justify-content: stretch; }
  .approval-card-actions .el-button { flex: 1; }
}
</style>
