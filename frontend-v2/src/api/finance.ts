import apiClient from './client'

export interface FinanceRecord {
  id: string
  invoice_id: string
  project_name: string
  project_code: string
  date: string
  month: string
  amount: number
  amount_label: string
  category: string
  handler: string
  archived_at: string
  source: string
  path: string
  data_quality?: string
  quality_issues?: string
  needs_review?: number
}

export interface FinanceGroup {
  name: string
  count: number
  amount: number
}

export interface FinanceSummary {
  records: number
  total_amount: number
  obsidian_total_amount: number
  projects: number
  categories: number
  latest_amount: number
  data_quality?: {
    complete: number
    needs_review: number
    missing_amount: number
    missing_date: number
  }
}

export interface OpenClawFinanceProject {
  name: string
  amount: number
}

export interface OpenClawFinanceItem {
  invoice: string
  vendor: string
  amount: number
  note: string
}

export interface OpenClawFinanceSummary {
  agent: string
  agent_label: string
  source: string
  total_amount: number
  projects: OpenClawFinanceProject[]
  items: OpenClawFinanceItem[]
  updated_at: string
}

export interface FinanceDashboard {
  status: string
  source: string
  openclaw: OpenClawFinanceSummary | null
  generated_at: string
  summary: FinanceSummary
  latest_reimbursements: FinanceRecord[]
  projects: FinanceGroup[]
  categories: FinanceGroup[]
  monthly: FinanceGroup[]
  records: FinanceRecord[]
  budget?: FinanceBudget
  reimbursements?: FinanceReimbursements
}

export interface FinanceReimbursement {
  id: number
  reimbursement_key: string
  batch_key: string
  title: string
  project_key: string
  project_name?: string
  source_agent: string
  source_path: string
  total_amount: number
  item_count: number
  status: string
  submitted_at: string
  confirmed_at: string
  created_at: string
  updated_at: string
}

export interface FinanceReimbursementItem {
  id: number
  reimbursement_key: string
  item_key: string
  project_key: string
  budget_category: string
  vendor: string
  invoice_no: string
  source_type: string
  source_ref: string
  expense_date: string
  amount: number
  note: string
  status: string
}

export interface FinanceInvoiceSource {
  id: number
  source_key: string
  reimbursement_key: string
  item_key: string
  source_type: string
  source_ref: string
  file_path: string
  email_id: string
  scan_path: string
  status: string
}

export interface FinanceApprovalEvent {
  id: number
  reimbursement_key: string
  event_type: string
  actor: string
  from_status: string
  to_status: string
  comment: string
  created_at: string
}

export interface FinanceReimbursements {
  summary: {
    reimbursements: number
    items: number
    total_amount: number
    confirmed: number
  }
  records: FinanceReimbursement[]
  items: FinanceReimbursementItem[]
  sources: FinanceInvoiceSource[]
  events: FinanceApprovalEvent[]
}

export interface FinanceBudgetProject {
  id: number
  project_key: string
  name: string
  budget_amount: number
  allocated_amount: number
  spent_amount: number
  remaining_amount: number
  status: string
  source: string
  created_at: string
  updated_at: string
}

export interface FinanceBudgetCategory {
  id: number
  project_key: string
  category: string
  budget_amount: number
  spent_amount: number
  remaining_amount: number
  note: string
  created_at: string
  updated_at: string
}

export interface FinanceBudget {
  summary: {
    projects: number
    budget_amount: number
    spent_amount: number
    remaining_amount: number
    execution_percent: number
  }
  projects: FinanceBudgetProject[]
  categories: FinanceBudgetCategory[]
}

export interface FinanceTableColumn {
  name: string
  type: string
  required: boolean
  primary_key: boolean
}

export interface FinanceTableSchema {
  name: string
  table: string
  rows: number
  columns: FinanceTableColumn[]
}

export interface FinanceSchema {
  status: string
  source: string
  generated_at: string
  tables: FinanceTableSchema[]
}

export interface FinanceTableData {
  status: string
  source: string
  name: string
  table: string
  limit: number
  offset: number
  total: number
  rows: Record<string, unknown>[]
  generated_at: string
}

export interface FinanceQualityIssue {
  issue: string
  count: number
}

export interface FinanceQualityReport {
  status: string
  source: string
  generated_at: string
  summary: {
    records: number
    complete: number
    needs_review: number
    missing_amount: number
    missing_date: number
  }
  issues: FinanceQualityIssue[]
  records: Record<string, unknown>[]
}

export interface FinanceEnrichmentSuggestion {
  id: number
  expense_key: string
  field_name: string
  current_value: string
  suggested_value: string
  confidence: number
  reason: string
  source: string
  status: string
  project_name?: string
  amount?: number
  expense_date?: string
  category?: string
  source_path?: string
}

export interface FinanceEnrichmentReport {
  status: string
  source: string
  generated_at: string
  summary: {
    suggestions: number
    pending: number
    applied: number
    high_confidence: number
  }
  fields: Array<{
    field: string
    count: number
    avg_confidence: number
  }>
  suggestions: FinanceEnrichmentSuggestion[]
}

export interface FinanceEnrichmentRunResult {
  status: string
  scanned: number
  suggestions_upserted: number
  generated_at: string
}

export interface FinanceBudgetUpdatePayload {
  budget_amount: number
  actor?: string
  reason?: string
}

export interface FinanceReimbursementStatusPayload {
  status: string
  actor?: string
  comment?: string
}

export async function getFinanceDashboard(limit = 120): Promise<FinanceDashboard> {
  const response = await apiClient.get<FinanceDashboard>('/api/finance/summary', { params: { limit } })
  return response.data
}

export async function getFinanceSchema(): Promise<FinanceSchema> {
  const response = await apiClient.get<FinanceSchema>('/api/finance/schema')
  return response.data
}

export async function updateFinanceBudgetCategory(
  projectKey: string,
  category: string,
  payload: FinanceBudgetUpdatePayload,
): Promise<{ budget: FinanceBudget }> {
  const response = await apiClient.put(`/api/finance/budget/categories/${projectKey}/${encodeURIComponent(category)}`, payload)
  return response.data
}

export async function transitionFinanceReimbursementStatus(
  reimbursementKey: string,
  payload: FinanceReimbursementStatusPayload,
): Promise<{ reimbursements: FinanceReimbursements }> {
  const response = await apiClient.post(`/api/finance/reimbursements/${reimbursementKey}/status`, payload)
  return response.data
}

export async function getFinanceTable(tableName: string, limit = 50, offset = 0): Promise<FinanceTableData> {
  const response = await apiClient.get<FinanceTableData>(`/api/finance/tables/${tableName}`, {
    params: { limit, offset },
  })
  return response.data
}

export async function getFinanceQuality(limit = 100): Promise<FinanceQualityReport> {
  const response = await apiClient.get<FinanceQualityReport>('/api/finance/quality', { params: { limit } })
  return response.data
}

export async function getFinanceEnrichment(limit = 100): Promise<FinanceEnrichmentReport> {
  const response = await apiClient.get<FinanceEnrichmentReport>('/api/finance/enrichment', { params: { limit } })
  return response.data
}

export async function runFinanceEnrichment(limit = 100): Promise<FinanceEnrichmentRunResult> {
  const response = await apiClient.post<FinanceEnrichmentRunResult>('/api/finance/enrichment/run', null, {
    params: { limit },
  })
  return response.data
}
