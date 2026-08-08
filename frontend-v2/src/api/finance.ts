import apiClient from './client'

export interface Envelope<T> { status: string; data: T; meta: Record<string, unknown> }
export interface PageState { loading: boolean; error: string }

export interface FinanceProject {
  id: string; project_key: string; name: string; currency: string; status: string
  owner_user_id?: number; version: number; created_at: string
}

export interface FundAllocation {
  id: string; project_id: string; reference_no: string; amount: number; allocated_at: string; source: string; note: string
}

export interface BudgetLine {
  id: string; budget_version_id: string; category: string; amount: number
  reserved_amount: number; spent_amount: number; lock_version: number; note?: string
}

export interface BudgetVersion {
  id: string; project_id: string; version_no: number; name: string; status: string
  approved_amount: number; lock_version: number; lines: BudgetLine[]
}

export interface ApprovalTask {
  id: string; approval_instance_id: string; step_order: number; assignee_role?: string
  assignee_user_id?: number; status: string; comment?: string; created_at: string
  reimbursement?: {
    id: string; reimbursement_no: string; title: string; total_amount: number; status: string
    applicant_user_id: number; project_id: string; project_name: string
  }
}

export interface ApprovalWorkflowStep {
  id?: string; step_order?: number; name: string; assignee_role?: string | null; assignee_user_id?: number | null
}

export interface ApprovalWorkflow {
  id: string; name: string; project_id?: string | null; category?: string | null
  min_amount: number; max_amount?: number | null; is_active: boolean; priority: number
  steps: ApprovalWorkflowStep[]
}

export interface FinanceRoleAssignment {
  id: string; user_id: number; role: string; username: string; display_name: string; is_active: boolean
  projects: { project_id: string; role: string; project_name: string }[]
}

export interface ReimbursementItem {
  id: string; reimbursement_id: string; budget_line_id: string; description: string
  vendor?: string; expense_date: string; amount: number; invoice_id?: string
}

export interface Reimbursement {
  id: string; reimbursement_no: string; project_id: string; applicant_user_id: number
  title: string; description?: string; total_amount: number; currency: string; status: string
  lock_version: number; created_at: string; items: ReimbursementItem[]
  approval?: { tasks: ApprovalTask[]; events: Record<string, unknown>[] }
}

export interface InvoiceAttachment {
  id: string; invoice_id: string; original_name: string; content_type: string; size_bytes: number; scan_status: string
}

export interface Invoice {
  id: string; project_id: string; invoice_code?: string; invoice_number?: string; invoice_date?: string
  amount?: number; tax_amount?: number; seller_name?: string; buyer_name?: string
  status: string; verification_status: string; attachments: InvoiceAttachment[]
}

export interface Payment {
  id: string; payment_no: string; reimbursement_id: string; amount: number; payee_name: string
  payee_account_masked?: string; status: string; bank_reference?: string; paid_at?: string; lock_version: number
  confirmed_by_user_id?: number; confirmation_note?: string
}

export interface ReconciliationMatch {
  id: string; bank_transaction_id: string; payment_id: string; matched_amount: number
  confidence: number; status: string; created_at: string; confirmation_note?: string
  bank_transaction?: { transaction_ref: string; transaction_date: string; amount: number; counterparty?: string; account_masked?: string; memo?: string }
  payment?: Payment
}

export interface Dashboard {
  status: string; generated_at: string
  summary: {
    projects: number; budget_amount: number; reserved_amount: number; spent_amount: number
    available_amount: number; reimbursements: number; pending_approvals: number
    invoices: number; pending_payments: number; unmatched_transactions: number
  }
  recent_reimbursements: Reimbursement[]
}

export interface FinanceIntakeEvent {
  id: string; event_type: string; actor_type: 'user' | 'agent' | 'system'; actor_id: string
  payload: Record<string, unknown>; created_at: string
}

export interface FinanceIntakeIssue {
  code: string; field: string; message: string
}

export interface FinanceIntakeJob {
  id: string; command_message_id: string; source_channel: string; source_account_id: string
  requested_by_user_id: number; target_agent_id: string; operation_type: string
  mode: 'shadow' | 'controlled_write'; status: string; lock_version: number
  created_at: string; updated_at: string
}

export interface FinanceIntakeDetail extends FinanceIntakeJob {
  external_message_id?: string; external_conversation_id: string; request_text: string
  request_metadata: Record<string, unknown>; normalized_payload: Record<string, unknown>
  shadow_snapshot: { captured_at?: string; authority?: string; write_capability?: string; record_counts?: Record<string, number> }
  validation_report: { validator?: string; validated_at?: string; valid?: boolean; errors?: FinanceIntakeIssue[]; warnings?: FinanceIntakeIssue[] }
  reviewer_report: { decision?: string; summary?: string; findings?: Record<string, unknown>[]; confidence?: number; reviewer_agent_id?: string; reviewed_at?: string }
  last_error?: string; events: FinanceIntakeEvent[]
}

export interface FinanceControlReadiness {
  status: 'blocked' | 'awaiting_authorization'
  mode: 'shadow'
  formal_write_enabled: false
  prerequisites_ready: boolean
  counts: { active_users: number; active_workflows: number; reviewers: number; cashiers: number }
  checks: { key: string; label: string; passed: boolean; detail: string }[]
  blockers: string[]
  evaluated_at: string
}

const key = () => crypto.randomUUID()
const unwrap = async <T>(promise: Promise<{ data: Envelope<T> }>): Promise<T> => (await promise).data.data
const writeHeaders = () => ({ 'Idempotency-Key': key() })

export const financeApi = {
  dashboard: () => unwrap<Dashboard>(apiClient.get('/api/finance/dashboard')),
  controlReadiness: () => unwrap<FinanceControlReadiness>(apiClient.get('/api/finance/control-readiness')),
  intakeJobs: (params?: { status?: string; operation_type?: string; limit?: number }) =>
    unwrap<FinanceIntakeJob[]>(apiClient.get('/api/finance/intake-jobs', { params })),
  intakeJob: (id: string) => unwrap<FinanceIntakeDetail>(apiClient.get(`/api/finance/intake-jobs/${id}`)),
  projects: () => unwrap<FinanceProject[]>(apiClient.get('/api/finance/projects')),
  createProject: (payload: { project_key: string; name: string; owner_user_id?: number }) =>
    unwrap<FinanceProject>(apiClient.post('/api/finance/projects', payload, { headers: writeHeaders() })),
  updateProject: (id: string, payload: Record<string, unknown>) =>
    unwrap<FinanceProject>(apiClient.patch(`/api/finance/projects/${id}`, payload)),
  allocations: (projectId?: string) => unwrap<FundAllocation[]>(apiClient.get('/api/finance/fund-allocations', { params: { project_id: projectId } })),
  createAllocation: (payload: Record<string, unknown>) =>
    unwrap<FundAllocation>(apiClient.post('/api/finance/fund-allocations', payload, { headers: writeHeaders() })),
  budgets: (projectId?: string) => unwrap<BudgetVersion[]>(apiClient.get('/api/finance/budgets', { params: { project_id: projectId } })),
  createBudget: (payload: Record<string, unknown>) =>
    unwrap<BudgetVersion>(apiClient.post('/api/finance/budgets', payload, { headers: writeHeaders() })),
  replaceBudgetLines: (id: string, payload: Record<string, unknown>) =>
    unwrap<BudgetVersion>(apiClient.put(`/api/finance/budgets/${id}/lines`, payload)),
  approveBudget: (id: string, version: number) =>
    unwrap<BudgetVersion>(apiClient.post(`/api/finance/budgets/${id}/approve`, { version }, { headers: writeHeaders() })),
  reimbursements: (status?: string) => unwrap<Reimbursement[]>(apiClient.get('/api/finance/reimbursements', { params: { status } })),
  createReimbursement: (payload: Record<string, unknown>) =>
    unwrap<Reimbursement>(apiClient.post('/api/finance/reimbursements', payload, { headers: writeHeaders() })),
  addReimbursementItem: (id: string, payload: Record<string, unknown>) =>
    unwrap<Reimbursement>(apiClient.post(`/api/finance/reimbursements/${id}/items`, payload)),
  submitReimbursement: (id: string, version: number) =>
    unwrap<Reimbursement>(apiClient.post(`/api/finance/reimbursements/${id}/submit`, { version }, { headers: writeHeaders() })),
  redraftReimbursement: (id: string, version: number) =>
    unwrap<Reimbursement>(apiClient.post(`/api/finance/reimbursements/${id}/redraft`, { version })),
  archiveReimbursement: (id: string, version: number) =>
    unwrap<Reimbursement>(apiClient.post(`/api/finance/reimbursements/${id}/archive`, { version }, { headers: writeHeaders() })),
  approvalTasks: () => unwrap<ApprovalTask[]>(apiClient.get('/api/finance/approval-tasks/me')),
  actApproval: (id: string, action: 'approve' | 'return' | 'reject', comment: string) =>
    unwrap<Reimbursement>(apiClient.post(`/api/finance/approval-tasks/${id}/${action}`, { comment }, { headers: writeHeaders() })),
  invoices: () => unwrap<Invoice[]>(apiClient.get('/api/finance/invoices')),
  createInvoice: (payload: Record<string, unknown>) =>
    unwrap<Invoice>(apiClient.post('/api/finance/invoices', payload, { headers: writeHeaders() })),
  uploadInvoice: (invoiceId: string, file: File) =>
    unwrap<InvoiceAttachment>(apiClient.post(`/api/finance/invoices/${invoiceId}/attachments`, file, {
      headers: { ...writeHeaders(), 'Content-Type': file.type || 'application/octet-stream', 'X-Filename': file.name },
    })),
  runOcr: (invoiceId: string) => unwrap<Invoice>(apiClient.post(`/api/finance/invoices/${invoiceId}/ocr`, null, { headers: writeHeaders() })),
  verifyInvoice: (invoiceId: string) => unwrap<Invoice>(apiClient.post(`/api/finance/invoices/${invoiceId}/verify`, null, { headers: writeHeaders() })),
  payments: () => unwrap<Payment[]>(apiClient.get('/api/finance/payments')),
  createPayment: (payload: Record<string, unknown>) =>
    unwrap<Payment>(apiClient.post('/api/finance/payments', payload, { headers: writeHeaders() })),
  confirmPayment: (id: string, payload: Record<string, unknown>) =>
    unwrap<Payment>(apiClient.post(`/api/finance/payments/${id}/confirm`, payload, { headers: writeHeaders() })),
  importStatement: (file: File) => unwrap<Record<string, unknown>>(apiClient.post('/api/finance/bank-statements/import', file, {
    headers: { ...writeHeaders(), 'Content-Type': file.type || 'text/csv', 'X-Filename': file.name },
  })),
  reconciliations: () => unwrap<ReconciliationMatch[]>(apiClient.get('/api/finance/reconciliations')),
  confirmReconciliations: (matches: string[], confirmation_note: string) => unwrap<{ records: ReconciliationMatch[] }>(apiClient.post(
    '/api/finance/reconciliations/confirm', { matches, human_confirmed: true, confirmation_note }, { headers: writeHeaders() },
  )),
  workflows: () => unwrap<ApprovalWorkflow[]>(apiClient.get('/api/finance/approval-workflows')),
  createWorkflow: (payload: Record<string, unknown>) => unwrap<ApprovalWorkflow>(apiClient.post(
    '/api/finance/approval-workflows', payload, { headers: writeHeaders() },
  )),
  roles: () => unwrap<FinanceRoleAssignment[]>(apiClient.get('/api/finance/roles')),
  grantRole: (payload: Record<string, unknown>) => unwrap<Record<string, unknown>>(apiClient.post(
    '/api/finance/roles', payload, { headers: writeHeaders() },
  )),
  report: <T>(name: 'budget-execution' | 'expenses' | 'payments' | 'audit') =>
    unwrap<T>(apiClient.get(`/api/finance/reports/${name}`)),
  createImport: (payload: { source_type: string; dry_run: boolean }) => unwrap<Record<string, unknown>>(apiClient.post(
    '/api/finance/imports', payload, { headers: writeHeaders() },
  )),
}

export const formatMoney = (value: number | string | undefined) => new Intl.NumberFormat(
  'zh-CN', { style: 'currency', currency: 'CNY' },
).format(Number(value || 0))
