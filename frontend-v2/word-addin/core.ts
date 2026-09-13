export interface AddinConfig {
  apiOrigin: string
  projectId: string
  documentId: string
  token: string
}

export interface CapturedParagraph {
  text: string
  sha256: string
  style: string
  documentFingerprint: string
}

export interface CandidateProposal {
  jobId: string
  proposalId: string
  changeSetId: string
  baseRevision: number
  replacementText: string
}

export function normalizeOrigin(value: string): string {
  return value.trim().replace(/\/+$/, '')
}

export function randomId(prefix = ''): string {
  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes)
  const value = Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('')
  return `${prefix}${value}`
}

export async function sha256(value: string): Promise<string> {
  const bytes = new TextEncoder().encode(value)
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('')
}

export function buildSelectionJob(
  paragraph: CapturedParagraph,
  instruction: string,
  baseRevision: number,
  blockId: string
): Record<string, unknown> {
  return {
    client_request_id: randomId('word-'),
    agent_id: 'ultra-magnus',
    scope: 'selection',
    instruction: instruction.trim(),
    selection: {
      text: paragraph.text,
      text_sha256: paragraph.sha256,
      source: 'microsoft-word-addin',
      paragraph_style: paragraph.style,
      base_revision: baseRevision,
      block_id: blockId
    },
    risk_policy: {
      allow_auto_draft: false,
      require_human_review: true,
      word_candidate_only: true
    }
  }
}

export class ApiClient {
  constructor(private readonly config: AddinConfig) {}

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await fetch(`${normalizeOrigin(this.config.apiOrigin)}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${this.config.token}`,
        ...(init.headers || {})
      }
    })
    const body = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw new Error(String(body.detail || body.message || `HTTP ${response.status}`))
    }
    return body as T
  }

  private documentPath(): string {
    return `/api/v3/writing/projects/${encodeURIComponent(this.config.projectId)}/documents/${encodeURIComponent(this.config.documentId)}`
  }

  context(): Promise<Record<string, unknown>> {
    return this.request(`${this.documentPath()}/word-addin/context`)
  }

  resolveParagraph(paragraph: CapturedParagraph): Promise<Record<string, unknown>> {
    return this.request(`${this.documentPath()}/word-addin/resolve-paragraph`, {
      method: 'POST',
      body: JSON.stringify({ text: paragraph.text, text_sha256: paragraph.sha256 })
    })
  }

  createJob(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
    return this.request(`${this.documentPath()}/ai-jobs`, {
      method: 'POST',
      body: JSON.stringify(payload)
    })
  }

  getJob(jobId: string): Promise<Record<string, unknown>> {
    return this.request(`${this.documentPath()}/ai-jobs/${encodeURIComponent(jobId)}`)
  }

  workflow(): Promise<Record<string, unknown>> {
    return this.request(`${this.documentPath()}/research-workflow`)
  }

  validateApply(changeSetId: string, payload: Record<string, unknown>): Promise<Record<string, unknown>> {
    return this.request(`${this.documentPath()}/word-addin/change-sets/${encodeURIComponent(changeSetId)}/validate-apply`, {
      method: 'POST',
      body: JSON.stringify(payload)
    })
  }

  recordReceipt(changeSetId: string, payload: Record<string, unknown>): Promise<Record<string, unknown>> {
    return this.request(`${this.documentPath()}/word-addin/change-sets/${encodeURIComponent(changeSetId)}/receipts`, {
      method: 'POST',
      body: JSON.stringify(payload)
    })
  }
}

function objectArray(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter(item => item && typeof item === 'object') : []
}

export function resolveCandidate(
  job: Record<string, unknown>,
  workflow: Record<string, unknown>,
  baseRevision: number
): CandidateProposal {
  const jobId = String(job.id || job.job_id || '')
  const proposals = objectArray(job.proposals || workflow.proposals)
  const proposal = proposals.find(item => String(item.job_id || '') === jobId) || proposals[0]
  if (!proposal) throw new Error('AI任务已完成，但未返回块级建议')
  const proposalId = String(proposal.id || proposal.proposal_id || '')
  const changeSets = objectArray(workflow.change_sets || workflow.changeSets)
  const changeSet = changeSets.find(item => String(item.proposal_id || '') === proposalId)
  if (!changeSet) throw new Error('AI建议尚未生成待审ChangeSet')
  return {
    jobId,
    proposalId,
    changeSetId: String(changeSet.id || changeSet.change_set_id || ''),
    baseRevision: Number(changeSet.base_revision || baseRevision),
    replacementText: ''
  }
}

export async function pollJob(
  client: ApiClient,
  jobId: string,
  waitMs = 1200,
  maxAttempts = 100
): Promise<Record<string, unknown>> {
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    const job = await client.getJob(jobId)
    const status = String(job.status || '').toLowerCase()
    if (['completed', 'succeeded', 'review_required'].includes(status)) return job
    if (['failed', 'cancelled', 'rejected'].includes(status)) {
      throw new Error(String(job.error || job.error_message || `AI任务${status}`))
    }
    await new Promise(resolve => setTimeout(resolve, waitMs))
  }
  throw new Error('等待AI建议超时')
}
