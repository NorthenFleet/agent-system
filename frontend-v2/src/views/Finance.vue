<template>
  <div class="finance-page">
    <div class="page-head">
      <div>
        <h2>财务中心</h2>
        <p>项目经费、预算编制、报销单据和发票归档状态。</p>
      </div>
      <div class="head-actions">
        <el-tag :type="data?.status === 'ready' ? 'success' : 'warning'">{{ data?.status || 'loading' }}</el-tag>
        <el-button type="primary" :loading="loading" @click="loadFinance">刷新</el-button>
      </div>
    </div>

    <section class="flow-strip">
      <article v-for="step in financeFlow" :key="step.title" :class="['flow-step', step.state]">
        <span>{{ step.index }}</span>
        <div>
          <strong>{{ step.title }}</strong>
          <small>{{ step.detail }}</small>
        </div>
      </article>
    </section>

    <el-row :gutter="16" class="metric-row">
      <el-col :xs="24" :sm="12" :lg="6">
        <el-card class="metric-card" shadow="hover">
          <span>项目总预算</span>
          <strong>{{ money(budgetSummary.budget_amount) }}</strong>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :lg="6">
        <el-card class="metric-card" shadow="hover">
          <span>已确认报销</span>
          <strong>{{ money(budgetSummary.spent_amount || activeTotal) }}</strong>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :lg="6">
        <el-card class="metric-card" shadow="hover">
          <span>预算余额</span>
          <strong>{{ money(budgetSummary.remaining_amount) }}</strong>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :lg="6">
        <el-card class="metric-card warning" shadow="hover">
          <span>待补全记录</span>
          <strong>{{ quality?.summary.needs_review || data?.summary.data_quality?.needs_review || 0 }}</strong>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <el-col :xs="24" :xl="10">
        <el-card class="panel-card" shadow="hover">
          <template #header>
            <div class="panel-header">
              <span>项目经费状态</span>
              <small>{{ data?.generated_at ? `更新于 ${data.generated_at}` : '等待数据' }}</small>
            </div>
          </template>
          <div class="project-ledger">
            <article
              v-for="project in budgetProjects"
              :key="project.project_key"
              :class="{ active: activeBudgetProjectKey === project.project_key }"
              @click="activeBudgetProjectKey = project.project_key"
            >
              <div>
                <strong>{{ project.name }}</strong>
                <small>预算 {{ money(project.budget_amount) }} · 执行率 {{ percent(projectExecution(project)) }}</small>
              </div>
              <b>{{ money(project.remaining_amount) }}</b>
            </article>
            <el-empty v-if="!budgetProjects.length" description="暂无项目经费记录" />
          </div>
        </el-card>
      </el-col>

      <el-col :xs="24" :xl="14">
        <el-card class="panel-card" shadow="hover">
          <template #header>
            <div class="panel-header">
              <span>预算编制</span>
              <div class="panel-actions">
                <small>{{ selectedBudgetProjectName }}</small>
                <el-select v-model="activeBudgetProjectKey" size="small" class="project-select">
                  <el-option label="全部项目" value="all" />
                  <el-option
                    v-for="project in budgetProjects"
                    :key="project.project_key"
                    :label="project.name"
                    :value="project.project_key"
                  />
                </el-select>
              </div>
            </div>
          </template>
          <el-table :data="budgetRows" size="small" class="budget-table">
            <el-table-column prop="category" label="经费类别" min-width="130" />
            <el-table-column prop="budget" label="预算额度" min-width="120">
              <template #default="{ row }">
                <el-input-number
                  v-if="row.editable"
                  v-model="budgetDrafts[row.category]"
                  :min="0"
                  :step="1000"
                  :precision="2"
                  size="small"
                  controls-position="right"
                />
                <span v-else>{{ row.budgetLabel }}</span>
              </template>
            </el-table-column>
            <el-table-column label="已报销" min-width="120" align="right">
              <template #default="{ row }">{{ money(row.spent) }}</template>
            </el-table-column>
            <el-table-column label="执行率" min-width="180">
              <template #default="{ row }">
                <el-progress :percentage="row.percent" :show-text="false" />
              </template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="110">
              <template #default="{ row }">
                <el-tag :type="row.spent > 0 ? 'warning' : 'info'" effect="plain">{{ row.status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="110" fixed="right">
              <template #default="{ row }">
                <el-button
                  v-if="row.editable"
                  size="small"
                  type="primary"
                  :loading="budgetSaving === row.category"
                  @click="saveBudgetCategory(row.category)"
                >
                  保存
                </el-button>
                <span v-else>-</span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <el-card class="panel-card reimbursement-card" shadow="hover">
      <template #header>
        <div class="panel-header">
          <span>报销单据</span>
          <small>{{ reimbursementSummary.reimbursements }} 张报销单 · {{ reimbursementSummary.items }} 条明细</small>
        </div>
      </template>
      <div class="reimbursement-workspace">
        <div class="reimbursement-list">
          <article
            v-for="record in reimbursementRecords"
            :key="record.reimbursement_key"
            :class="{ active: selectedReimbursementKey === record.reimbursement_key }"
            @click="selectedReimbursementKey = record.reimbursement_key"
          >
            <div>
              <strong>{{ record.title }}</strong>
              <small>{{ record.reimbursement_key }} · {{ record.project_name || record.project_key }}</small>
            </div>
            <b>{{ money(record.total_amount) }}</b>
            <el-tag size="small" :type="record.status === 'confirmed' ? 'success' : 'warning'" effect="plain">
              {{ record.status }}
            </el-tag>
          </article>
          <el-empty v-if="!reimbursementRecords.length" description="暂无报销单" />
        </div>
        <div class="reimbursement-detail" v-if="selectedReimbursement">
          <div class="reimbursement-total">
            <div>
              <span>选中报销单</span>
              <strong>{{ money(selectedReimbursement.total_amount) }}</strong>
              <small>{{ selectedReimbursement.source_path }}</small>
            </div>
            <div class="status-actions">
              <el-button
                v-for="action in reimbursementActions"
                :key="action.status"
                size="small"
                :type="action.type"
                :loading="statusSaving === action.status"
                @click="transitionReimbursement(action.status)"
              >
                {{ action.label }}
              </el-button>
            </div>
          </div>
          <el-table :data="selectedReimbursementItems" size="small">
            <el-table-column prop="item_key" label="票据" width="100" />
            <el-table-column prop="vendor" label="开票方/平台" min-width="220" show-overflow-tooltip />
            <el-table-column prop="budget_category" label="经费类别" width="120" />
            <el-table-column label="金额" width="130" align="right">
              <template #default="{ row }">{{ money(row.amount) }}</template>
            </el-table-column>
            <el-table-column prop="note" label="摘要" min-width="180" show-overflow-tooltip />
          </el-table>
          <div class="reimbursement-meta">
            <article>
              <span>发票来源</span>
              <strong>{{ selectedInvoiceSources.length }}</strong>
              <small>{{ selectedInvoiceSources[0]?.source_type || '待关联' }}</small>
            </article>
            <article>
              <span>审批事件</span>
              <strong>{{ selectedApprovalEvents.length }}</strong>
              <small>{{ selectedApprovalEvents[0]?.comment || '暂无审批记录' }}</small>
            </article>
          </div>
        </div>
      </div>
    </el-card>

    <el-row :gutter="16">
      <el-col :xs="24" :lg="12">
        <el-card class="panel-card" shadow="hover">
          <template #header>
            <div class="panel-header">
              <span>发票入库</span>
              <small>邮件/扫描归档</small>
            </div>
          </template>
          <div class="invoice-board">
            <article>
              <span>已入库支出记录</span>
              <strong>{{ data?.summary.records || 0 }}</strong>
            </article>
            <article>
              <span>Obsidian 归档金额</span>
              <strong>{{ money(data?.summary.obsidian_total_amount || 0) }}</strong>
            </article>
            <article>
              <span>需复核</span>
              <strong>{{ quality?.summary.needs_review || 0 }}</strong>
            </article>
          </div>
          <div class="latest-list">
            <article v-for="item in latest" :key="item.id" class="expense-card">
              <div>
                <h3>{{ item.project_name }}</h3>
                <p>{{ item.id }} · {{ item.category }} · {{ item.date || '未注明日期' }}</p>
                <small>{{ item.path }}</small>
              </div>
              <strong>{{ money(item.amount) }}</strong>
            </article>
          </div>
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="12">
        <el-card class="panel-card" shadow="hover">
          <template #header>月度支出</template>
          <div class="month-list">
            <div v-for="item in topMonths" :key="item.name" class="month-row">
              <span>{{ item.name }}</span>
              <el-progress :percentage="monthPercent(item.amount)" :show-text="false" />
              <strong>{{ money(item.amount) }}</strong>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-tabs v-model="activeSection" class="finance-tabs">
      <el-tab-pane label="单据质量" name="quality">
        <el-card class="panel-card" shadow="hover">
          <template #header>
            <div class="panel-header">
              <span>单据质量</span>
              <small>缺日期、零金额和泛化分类</small>
            </div>
          </template>
          <div class="quality-layout">
            <div class="quality-summary">
              <article>
                <span>完整记录</span>
                <strong>{{ quality?.summary.complete || 0 }}</strong>
              </article>
              <article>
                <span>需复核</span>
                <strong>{{ quality?.summary.needs_review || 0 }}</strong>
              </article>
              <article>
                <span>缺金额</span>
                <strong>{{ quality?.summary.missing_amount || 0 }}</strong>
              </article>
              <article>
                <span>缺日期</span>
                <strong>{{ quality?.summary.missing_date || 0 }}</strong>
              </article>
            </div>
            <div class="issue-list">
              <el-tag v-for="item in quality?.issues || []" :key="item.issue" type="warning" effect="plain">
                {{ issueLabel(item.issue) }} · {{ item.count }}
              </el-tag>
            </div>
          </div>
          <el-table :data="qualityRecords" size="small" height="260">
            <el-table-column prop="expense_key" label="单号" width="150" />
            <el-table-column prop="project_name" label="项目" min-width="180" show-overflow-tooltip />
            <el-table-column prop="expense_date" label="日期" width="120">
              <template #default="{ row }">{{ formatCell(row.expense_date) }}</template>
            </el-table-column>
            <el-table-column label="金额" width="120" align="right">
              <template #default="{ row }">{{ money(Number(row.amount || 0)) }}</template>
            </el-table-column>
            <el-table-column label="问题" min-width="220" show-overflow-tooltip>
              <template #default="{ row }">{{ formatIssues(row.quality_issues) }}</template>
            </el-table-column>
            <el-table-column prop="source_path" label="归档文件" min-width="260" show-overflow-tooltip />
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="智能补全" name="enrichment">
        <el-card class="panel-card" shadow="hover">
          <template #header>
            <div class="panel-header">
              <span>智能补全建议</span>
              <div class="panel-actions">
                <small>{{ enrichment?.generated_at ? `更新于 ${enrichment.generated_at}` : '等待生成' }}</small>
                <el-button size="small" type="primary" :loading="enrichmentLoading" @click="runEnrichment">
                  生成建议
                </el-button>
              </div>
            </div>
          </template>
          <div class="enrichment-summary">
            <article>
              <span>建议总数</span>
              <strong>{{ enrichment?.summary.suggestions || 0 }}</strong>
            </article>
            <article>
              <span>待处理</span>
              <strong>{{ enrichment?.summary.pending || 0 }}</strong>
            </article>
            <article>
              <span>高置信度</span>
              <strong>{{ enrichment?.summary.high_confidence || 0 }}</strong>
            </article>
          </div>
          <div class="issue-list enrichment-fields">
            <el-tag v-for="item in enrichment?.fields || []" :key="item.field" effect="plain">
              {{ fieldLabel(item.field) }} · {{ item.count }} · {{ percent(item.avg_confidence) }}
            </el-tag>
          </div>
          <el-table :data="enrichmentSuggestions" size="small" height="300" v-loading="enrichmentLoading">
            <el-table-column prop="expense_key" label="单号" width="150" />
            <el-table-column label="字段" width="110">
              <template #default="{ row }">{{ fieldLabel(row.field_name) }}</template>
            </el-table-column>
            <el-table-column prop="current_value" label="当前值" min-width="150" show-overflow-tooltip>
              <template #default="{ row }">{{ formatCell(row.current_value) }}</template>
            </el-table-column>
            <el-table-column prop="suggested_value" label="建议值" min-width="160" show-overflow-tooltip />
            <el-table-column label="置信度" width="110">
              <template #default="{ row }">
                <el-tag :type="confidenceType(row.confidence)" effect="plain">{{ percent(row.confidence) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="reason" label="依据" min-width="260" show-overflow-tooltip />
            <el-table-column prop="source_path" label="归档文件" min-width="240" show-overflow-tooltip />
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="支出明细" name="records">
        <el-card class="panel-card" shadow="hover">
          <template #header>
            <div class="panel-header">
              <span>支出明细</span>
              <el-input v-model="query" class="record-search" clearable placeholder="搜索项目、单号、类型" />
            </div>
          </template>
          <el-table :data="filteredRecords" size="small" height="420" v-loading="loading">
            <el-table-column prop="id" label="单号" width="150" fixed />
            <el-table-column prop="project_name" label="项目" min-width="190" show-overflow-tooltip />
            <el-table-column prop="category" label="类型" width="130" />
            <el-table-column prop="date" label="日期" width="120" />
            <el-table-column label="金额" width="120" align="right">
              <template #default="{ row }">{{ money(row.amount) }}</template>
            </el-table-column>
            <el-table-column prop="handler" label="经办人" width="150" show-overflow-tooltip />
            <el-table-column prop="path" label="归档文件" min-width="260" show-overflow-tooltip />
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="数据库" name="database">
        <el-card class="panel-card" shadow="hover">
          <template #header>
            <div class="panel-header">
              <span>数据库管表</span>
              <small>{{ schema?.source || '等待数据库状态' }}</small>
            </div>
          </template>
          <div class="table-overview">
            <article
              v-for="table in schema?.tables || []"
              :key="table.name"
              :class="{ active: table.name === activeTable }"
              @click="selectTable(table.name)"
            >
              <span>{{ table.name }}</span>
              <strong>{{ table.rows }}</strong>
              <small>{{ table.table }} · {{ table.columns.length }} 列</small>
            </article>
          </div>
          <el-tabs v-model="activeTable" class="database-tabs" @tab-change="loadActiveTable">
            <el-tab-pane
              v-for="table in schema?.tables || []"
              :key="table.name"
              :label="table.name"
              :name="table.name"
            />
          </el-tabs>
          <el-table :data="databaseRows" size="small" height="320" v-loading="tableLoading">
            <el-table-column
              v-for="column in activeColumns"
              :key="column.name"
              :prop="column.name"
              :label="column.name"
              min-width="140"
              show-overflow-tooltip
            >
              <template #default="{ row }">{{ formatCell(row[column.name]) }}</template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getFinanceDashboard,
  getFinanceEnrichment,
  getFinanceQuality,
  getFinanceSchema,
  getFinanceTable,
  runFinanceEnrichment,
  transitionFinanceReimbursementStatus,
  updateFinanceBudgetCategory,
  type FinanceDashboard,
  type FinanceEnrichmentReport,
  type FinanceQualityReport,
  type FinanceSchema,
  type FinanceTableData,
} from '@/api/finance'

const data = ref<FinanceDashboard | null>(null)
const schema = ref<FinanceSchema | null>(null)
const tableData = ref<FinanceTableData | null>(null)
const quality = ref<FinanceQualityReport | null>(null)
const enrichment = ref<FinanceEnrichmentReport | null>(null)
const loading = ref(false)
const tableLoading = ref(false)
const enrichmentLoading = ref(false)
const budgetSaving = ref('')
const statusSaving = ref('')
const query = ref('')
const activeTable = ref('')
const activeSection = ref('quality')
const activeBudgetProjectKey = ref('all')
const selectedReimbursementKey = ref('')
const budgetDrafts = ref<Record<string, number>>({})

const budgetCategories = ['差旅费', '设备费', '会议费', '外协费', '管理费', '材料费', '劳务费', '其他']

const latest = computed(() => data.value?.latest_reimbursements || [])
const topMonths = computed(() => (data.value?.monthly || []).slice(0, 8))
const maxMonthAmount = computed(() => Math.max(...topMonths.value.map(item => item.amount), 1))
const activeTotal = computed(() => data.value?.openclaw?.total_amount || data.value?.summary.total_amount || 0)
const budgetSummary = computed(() => data.value?.budget?.summary || {
  projects: 0,
  budget_amount: 0,
  spent_amount: 0,
  remaining_amount: 0,
  execution_percent: 0,
})
const budgetProjects = computed(() => data.value?.budget?.projects || [])
const budgetProjectCount = computed(() => budgetSummary.value.projects || budgetProjects.value.length)
const selectedBudgetProject = computed(() => budgetProjects.value.find(project => project.project_key === activeBudgetProjectKey.value))
const selectedBudgetProjectName = computed(() => selectedBudgetProject.value?.name || '全部项目')
const reimbursementSummary = computed(() => data.value?.reimbursements?.summary || {
  reimbursements: 0,
  items: 0,
  total_amount: 0,
  confirmed: 0,
})
const reimbursementRecords = computed(() => data.value?.reimbursements?.records || [])
const selectedReimbursement = computed(() => {
  if (!reimbursementRecords.value.length) return null
  return reimbursementRecords.value.find(item => item.reimbursement_key === selectedReimbursementKey.value) || reimbursementRecords.value[0]
})
const selectedReimbursementItems = computed(() => (data.value?.reimbursements?.items || [])
  .filter(item => item.reimbursement_key === selectedReimbursement.value?.reimbursement_key))
const selectedInvoiceSources = computed(() => (data.value?.reimbursements?.sources || [])
  .filter(item => item.reimbursement_key === selectedReimbursement.value?.reimbursement_key))
const selectedApprovalEvents = computed(() => (data.value?.reimbursements?.events || [])
  .filter(item => item.reimbursement_key === selectedReimbursement.value?.reimbursement_key))
const reimbursementActions = computed(() => {
  const status = selectedReimbursement.value?.status || ''
  const actions: Record<string, Array<{ status: string; label: string; type: 'primary' | 'success' | 'warning' | 'info' }>> = {
    draft: [{ status: 'submitted', label: '提交审核', type: 'primary' }],
    submitted: [{ status: 'reviewed', label: '复核通过', type: 'primary' }],
    reviewed: [{ status: 'confirmed', label: '确认报销', type: 'success' }],
    confirmed: [{ status: 'paid', label: '登记支付', type: 'success' }, { status: 'reviewed', label: '退回复核', type: 'warning' }],
    paid: [{ status: 'archived', label: '归档', type: 'primary' }],
  }
  return actions[status] || []
})
const activeSchema = computed(() => schema.value?.tables.find(item => item.name === activeTable.value))
const activeColumns = computed(() => activeSchema.value?.columns || [])
const databaseRows = computed(() => tableData.value?.rows || [])
const qualityRecords = computed(() => quality.value?.records || [])
const enrichmentSuggestions = computed(() => enrichment.value?.suggestions || [])

const financeFlow = computed(() => [
  {
    index: '01',
    title: '经费拨付',
    detail: budgetProjectCount.value ? `${budgetProjectCount.value} 个项目` : '待录入',
    state: budgetProjectCount.value ? 'done' : 'pending',
  },
  {
    index: '02',
    title: '预算编制',
    detail: budgetRows.value.some(row => row.spent > 0) ? '按类别归集' : '待编制',
    state: budgetRows.value.some(row => row.spent > 0) ? 'active' : 'pending',
  },
  {
    index: '03',
    title: '报销申请',
    detail: data.value?.openclaw ? money(data.value.openclaw.total_amount) : '待生成',
    state: data.value?.openclaw ? 'done' : 'pending',
  },
  {
    index: '04',
    title: '发票归档',
    detail: `${data.value?.summary.records || 0} 条记录`,
    state: data.value?.summary.records ? 'done' : 'pending',
  },
  {
    index: '05',
    title: '审核补全',
    detail: `${quality.value?.summary.needs_review || 0} 条待复核`,
    state: quality.value?.summary.needs_review ? 'warning' : 'done',
  },
])

const budgetRows = computed(() => {
  const sourceCategories = data.value?.budget?.categories || []
  const categories = activeBudgetProjectKey.value === 'all'
    ? sourceCategories
    : sourceCategories.filter(item => item.project_key === activeBudgetProjectKey.value)
  const spent = new Map<string, number>()
  const budget = new Map<string, number>()
  for (const item of categories) {
    spent.set(item.category, (spent.get(item.category) || 0) + Number(item.spent_amount || 0))
    budget.set(item.category, (budget.get(item.category) || 0) + Number(item.budget_amount || 0))
  }
  return budgetCategories.map(category => {
    const value = spent.get(category) || 0
    const budgetValue = budget.get(category) || 0
    return {
      category,
      budget: budgetValue,
      budgetLabel: budgetValue > 0 ? money(budgetValue) : '待编制',
      spent: value,
      percent: budgetValue > 0 ? Math.min(100, Math.round((value / budgetValue) * 100)) : 0,
      status: budgetValue > 0 ? '已编制' : value > 0 ? '待匹配预算' : '待编制',
      editable: activeBudgetProjectKey.value !== 'all',
    }
  })
})

const filteredRecords = computed(() => {
  const q = query.value.trim().toLowerCase()
  const records = data.value?.records || []
  if (!q) return records
  return records.filter(item => [item.id, item.project_name, item.category, item.project_code, item.path]
    .some(value => String(value || '').toLowerCase().includes(q)))
})

function money(value: number): string {
  return new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' }).format(value || 0)
}

function monthPercent(value: number): number {
  return Math.round(((value || 0) / maxMonthAmount.value) * 100)
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function issueLabel(value: string): string {
  const labels: Record<string, string> = {
    missing_date: '缺日期',
    missing_amount: '缺金额',
    missing_amount_source: '源金额缺失',
    generic_project: '泛化项目',
    generic_category: '泛化类型',
  }
  return labels[value] || value
}

function fieldLabel(value: string): string {
  const labels: Record<string, string> = {
    expense_date: '日期',
    amount: '金额',
    category: '类型',
    project_name: '项目',
  }
  return labels[value] || value
}

function percent(value: number): string {
  return `${Math.round((value || 0) * 100)}%`
}

function projectExecution(project: { budget_amount: number; spent_amount: number }): number {
  return project.budget_amount ? Number(project.spent_amount || 0) / Number(project.budget_amount || 1) : 0
}

function confidenceType(value: number): 'success' | 'warning' | 'info' {
  if (value >= 0.7) return 'success'
  if (value >= 0.5) return 'warning'
  return 'info'
}

function formatIssues(value: unknown): string {
  if (!value) return '-'
  try {
    const parsed = typeof value === 'string' ? JSON.parse(value) : value
    if (Array.isArray(parsed)) return parsed.map(item => issueLabel(String(item))).join('、')
  } catch {
    return String(value)
  }
  return String(value)
}

async function loadEnrichment() {
  enrichment.value = await getFinanceEnrichment()
}

function syncBudgetDrafts() {
  if (activeBudgetProjectKey.value === 'all') {
    budgetDrafts.value = {}
    return
  }
  const drafts: Record<string, number> = {}
  for (const item of data.value?.budget?.categories || []) {
    if (item.project_key === activeBudgetProjectKey.value) {
      drafts[item.category] = Number(item.budget_amount || 0)
    }
  }
  budgetDrafts.value = drafts
}

async function saveBudgetCategory(category: string) {
  if (activeBudgetProjectKey.value === 'all') return
  budgetSaving.value = category
  try {
    await updateFinanceBudgetCategory(activeBudgetProjectKey.value, category, {
      budget_amount: Number(budgetDrafts.value[category] || 0),
      actor: 'user',
      reason: '前端预算编制',
    })
    ElMessage.success('预算科目已保存')
    await loadFinance()
  } catch {
    ElMessage.error('预算科目保存失败')
  } finally {
    budgetSaving.value = ''
  }
}

async function transitionReimbursement(status: string) {
  if (!selectedReimbursement.value) return
  statusSaving.value = status
  try {
    await transitionFinanceReimbursementStatus(selectedReimbursement.value.reimbursement_key, {
      status,
      actor: 'user',
      comment: '前端状态流转',
    })
    ElMessage.success('报销单状态已更新')
    await loadFinance()
  } catch {
    ElMessage.error('报销单状态更新失败')
  } finally {
    statusSaving.value = ''
  }
}

async function runEnrichment() {
  enrichmentLoading.value = true
  try {
    const result = await runFinanceEnrichment()
    ElMessage.success(`已扫描 ${result.scanned} 条，生成/更新 ${result.suggestions_upserted} 条建议`)
    await Promise.all([
      loadEnrichment(),
      loadDatabaseSchema(),
    ])
  } catch {
    ElMessage.error('智能补全建议生成失败')
  } finally {
    enrichmentLoading.value = false
  }
}

async function loadDatabaseSchema() {
  schema.value = await getFinanceSchema()
  if (!activeTable.value && schema.value.tables.length) {
    activeTable.value = schema.value.tables[0].name
  }
  await loadActiveTable()
}

async function loadActiveTable() {
  if (!activeTable.value) return
  tableLoading.value = true
  try {
    tableData.value = await getFinanceTable(activeTable.value)
  } finally {
    tableLoading.value = false
  }
}

async function selectTable(tableName: string) {
  activeTable.value = tableName
  await loadActiveTable()
}

async function loadFinance() {
  loading.value = true
  try {
    const [dashboard, qualityReport] = await Promise.all([
      getFinanceDashboard(),
      getFinanceQuality(),
      loadEnrichment(),
    ])
    data.value = dashboard
    quality.value = qualityReport
    if (!selectedReimbursementKey.value && dashboard.reimbursements?.records?.length) {
      selectedReimbursementKey.value = dashboard.reimbursements.records[0].reimbursement_key
    }
    syncBudgetDrafts()
    await loadDatabaseSchema()
  } catch {
    ElMessage.error('财务数据加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(loadFinance)

watch(activeBudgetProjectKey, syncBudgetDrafts)
</script>

<style scoped>
.finance-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-head,
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.page-head h2 {
  margin: 0 0 6px;
  font-size: 22px;
}

.page-head p,
.panel-header small,
.expense-card p,
.expense-card small,
.project-ledger small,
.flow-step small {
  color: var(--el-text-color-secondary);
}

.head-actions,
.panel-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.flow-strip {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
}

.flow-step {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-lighter);
}

.flow-step span {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  color: var(--el-text-color-regular);
  background: var(--el-fill-color);
  font-weight: 700;
}

.flow-step div {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.flow-step.done span {
  color: var(--el-color-success);
  background: var(--el-color-success-light-9);
}

.flow-step.active span {
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.flow-step.warning span {
  color: var(--el-color-warning);
  background: var(--el-color-warning-light-9);
}

.metric-row {
  margin-bottom: -16px;
}

.metric-card {
  margin-bottom: 16px;
  border-radius: 8px;
}

.metric-card :deep(.el-card__body) {
  display: grid;
  gap: 8px;
}

.metric-card span,
.invoice-board span,
.quality-summary span,
.enrichment-summary span,
.table-overview span,
.table-overview small,
.reimbursement-total span,
.reimbursement-total small,
.reimbursement-list small,
.reimbursement-meta span,
.reimbursement-meta small {
  color: var(--el-text-color-secondary);
}

.metric-card strong {
  font-size: 26px;
  color: var(--el-text-color-primary);
}

.metric-card.warning strong {
  color: var(--el-color-warning);
}

.panel-card {
  border-radius: 8px;
  margin-bottom: 16px;
}

.project-ledger,
.latest-list,
.month-list {
  display: grid;
  gap: 10px;
}

.project-ledger article,
.expense-card,
.month-row,
.invoice-board article,
.quality-summary article,
.enrichment-summary article,
.table-overview article,
.reimbursement-total,
.reimbursement-list article,
.reimbursement-meta article {
  display: grid;
  gap: 6px;
  padding: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-lighter);
}

.project-ledger article {
  cursor: pointer;
}

.project-ledger article.active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.project-select {
  width: 280px;
}

.project-ledger article,
.expense-card,
.month-row {
  align-items: center;
  grid-template-columns: minmax(0, 1fr) auto;
}

.project-ledger b,
.expense-card strong,
.month-row strong,
.invoice-board strong,
.quality-summary strong,
.enrichment-summary strong,
.table-overview strong,
.reimbursement-total strong,
.reimbursement-list b,
.reimbursement-meta strong {
  color: var(--el-color-primary);
}

.budget-table {
  width: 100%;
}

.reimbursement-card {
  border-color: rgba(64, 158, 255, 0.35);
}

.reimbursement-workspace {
  display: grid;
  grid-template-columns: minmax(280px, 0.45fr) minmax(0, 1fr);
  gap: 12px;
}

.reimbursement-list {
  display: grid;
  align-content: start;
  gap: 10px;
}

.reimbursement-list article {
  grid-template-columns: minmax(0, 1fr) auto auto;
  align-items: center;
  cursor: pointer;
}

.reimbursement-list article.active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.reimbursement-detail {
  display: grid;
  gap: 12px;
}

.reimbursement-total strong {
  font-size: 24px;
}

.status-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.reimbursement-total small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.reimbursement-meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.invoice-board,
.quality-summary,
.enrichment-summary,
.table-overview {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}

.month-row {
  grid-template-columns: 86px minmax(0, 1fr) 110px;
}

.finance-tabs :deep(.el-tabs__header) {
  margin-bottom: 12px;
}

.quality-layout {
  display: grid;
  grid-template-columns: minmax(280px, 0.9fr) minmax(0, 1fr);
  gap: 12px;
  margin-bottom: 12px;
}

.issue-list {
  display: flex;
  align-content: flex-start;
  flex-wrap: wrap;
  gap: 8px;
}

.enrichment-fields {
  margin-bottom: 12px;
}

.table-overview article {
  cursor: pointer;
}

.table-overview article.active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.database-tabs {
  margin-bottom: 8px;
}

.record-search {
  width: 260px;
}

@media (max-width: 1100px) {
  .flow-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .page-head,
  .panel-header,
  .project-ledger article,
  .expense-card,
  .month-row,
  .reimbursement-workspace,
  .quality-layout,
  .flow-strip {
    grid-template-columns: 1fr;
    align-items: stretch;
  }

  .page-head,
  .panel-header {
    display: grid;
  }

  .record-search {
    width: 100%;
  }

  .project-select {
    width: 100%;
  }
}
</style>
