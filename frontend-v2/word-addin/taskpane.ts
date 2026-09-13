import './taskpane.css'
import {
  ApiClient,
  buildSelectionJob,
  pollJob,
  randomId,
  resolveCandidate,
  type AddinConfig,
  type CandidateProposal,
  type CapturedParagraph
} from './core'
import { captureCurrentParagraph, replaceCurrentParagraph } from './wordAdapter'

declare const Office: any

const byId = <T extends HTMLElement>(id: string): T => document.getElementById(id) as T
const fields = {
  apiOrigin: byId<HTMLInputElement>('apiOrigin'),
  projectId: byId<HTMLInputElement>('projectId'),
  documentId: byId<HTMLInputElement>('documentId'),
  token: byId<HTMLInputElement>('token')
}
const authority = byId<HTMLSpanElement>('authority')
const sourceText = byId<HTMLPreElement>('sourceText')
const instruction = byId<HTMLTextAreaElement>('instruction')
const replacementText = byId<HTMLPreElement>('replacementText')
const risk = byId<HTMLSpanElement>('risk')
const message = byId<HTMLOutputElement>('message')
const generateButton = byId<HTMLButtonElement>('generate')
const applyButton = byId<HTMLButtonElement>('apply')

let client: ApiClient | null = null
let baseRevision = 0
let captured: CapturedParagraph | null = null
let resolvedBlockId = ''
let candidate: CandidateProposal | null = null
const officeSessionId = randomId('office-')

function config(): AddinConfig {
  return {
    apiOrigin: fields.apiOrigin.value,
    projectId: fields.projectId.value.trim(),
    documentId: fields.documentId.value.trim(),
    token: fields.token.value.trim()
  }
}

function setMessage(value: string, error = false): void {
  message.textContent = value
  message.className = error ? 'error' : ''
}

function busy(button: HTMLButtonElement, active: boolean): void {
  button.disabled = active
  document.body.classList.toggle('busy', active)
}

function resetCandidate(): void {
  candidate = null
  applyButton.disabled = true
  replacementText.textContent = '尚无候选'
  replacementText.classList.add('empty')
  risk.textContent = '待生成'
}

function restoreSettings(): void {
  const params = new URLSearchParams(location.search)
  fields.apiOrigin.value = params.get('api_origin') || localStorage.getItem('word-addin-api-origin') || location.origin
  fields.projectId.value = params.get('project_id') || localStorage.getItem('word-addin-project-id') || ''
  fields.documentId.value = params.get('document_id') || localStorage.getItem('word-addin-document-id') || ''
  fields.token.value = localStorage.getItem('token') || localStorage.getItem('access_token') || ''
}

byId<HTMLButtonElement>('connect').addEventListener('click', async event => {
  const button = event.currentTarget as HTMLButtonElement
  try {
    const current = config()
    if (!current.projectId || !current.documentId || !current.token) throw new Error('项目、文档和访问令牌不能为空')
    busy(button, true)
    client = new ApiClient(current)
    const context = await client.context()
    baseRevision = Number(context.revision || 0)
    if (!baseRevision) throw new Error('未取得结构化正文修订')
    authority.textContent = `候选模式 · 修订 ${baseRevision}`
    localStorage.setItem('word-addin-api-origin', current.apiOrigin)
    localStorage.setItem('word-addin-project-id', current.projectId)
    localStorage.setItem('word-addin-document-id', current.documentId)
    setMessage('已连接。正文权威不会由Word任务窗格直接推进。')
  } catch (error) {
    client = null
    setMessage(error instanceof Error ? error.message : String(error), true)
  } finally {
    busy(button, false)
  }
})

byId<HTMLButtonElement>('capture').addEventListener('click', async event => {
  const button = event.currentTarget as HTMLButtonElement
  try {
    busy(button, true)
    captured = await captureCurrentParagraph()
    if (!client) throw new Error('请先连接3021权威状态')
    const resolved = await client.resolveParagraph(captured)
    if (Number(resolved.revision || 0) !== baseRevision) throw new Error('3021正文修订已变化，请重新连接')
    resolvedBlockId = String(resolved.block_id || '')
    if (!resolvedBlockId) throw new Error('未取得Word段落对应的稳定块ID')
    sourceText.textContent = captured.text
    sourceText.classList.remove('empty')
    generateButton.disabled = false
    resetCandidate()
    setMessage('已读取光标所在段落及其样式指纹。')
  } catch (error) {
    setMessage(error instanceof Error ? error.message : String(error), true)
  } finally {
    busy(button, false)
  }
})

generateButton.addEventListener('click', async () => {
  if (!client || !captured) return
  try {
    if (!instruction.value.trim()) throw new Error('请填写修改要求')
    busy(generateButton, true)
    resetCandidate()
    setMessage('AI正在生成待审建议…')
    const created = await client.createJob(buildSelectionJob(captured, instruction.value, baseRevision, resolvedBlockId))
    const jobId = String(created.id || created.job_id || '')
    if (!jobId) throw new Error('AI任务未返回任务ID')
    const job = await pollJob(client, jobId)
    const workflow = await client.workflow()
    candidate = resolveCandidate({ ...job, id: jobId }, workflow, baseRevision)
    const validation = await client.validateApply(candidate.changeSetId, {
      base_revision: candidate.baseRevision,
      current_paragraph_sha256: captured.sha256,
      office_session_id: officeSessionId,
      document_session_fingerprint: captured.documentFingerprint
    })
    candidate.replacementText = String(validation.replacement_text || '')
    replacementText.textContent = candidate.replacementText
    replacementText.classList.remove('empty')
    risk.textContent = '待人工确认'
    applyButton.dataset.applyToken = String(validation.apply_token || '')
    applyButton.disabled = false
    setMessage('建议已通过修订与段落指纹校验。')
  } catch (error) {
    setMessage(error instanceof Error ? error.message : String(error), true)
  } finally {
    generateButton.disabled = false
    document.body.classList.remove('busy')
  }
})

applyButton.addEventListener('click', async () => {
  if (!client || !captured || !candidate) return
  try {
    busy(applyButton, true)
    const validation = await client.validateApply(candidate.changeSetId, {
      base_revision: candidate.baseRevision,
      current_paragraph_sha256: captured.sha256,
      office_session_id: officeSessionId,
      document_session_fingerprint: captured.documentFingerprint
    })
    const replacement = String(validation.replacement_text || '')
    if (replacement !== candidate.replacementText) throw new Error('候选内容在确认后发生变化')
    const result = await replaceCurrentParagraph(captured, replacement)
    await client.recordReceipt(candidate.changeSetId, {
      apply_token: validation.apply_token,
      before_sha256: result.beforeSha256,
      after_sha256: result.afterSha256,
      office_session_id: officeSessionId,
      document_session_fingerprint: captured.documentFingerprint
    })
    authority.textContent = `Word候选已应用 · 正文仍为修订 ${baseRevision}`
    risk.textContent = '等待Word回流'
    setMessage('Word候选已写入并登记回执；3021结构化正文未改变。')
  } catch (error) {
    setMessage(error instanceof Error ? error.message : String(error), true)
    applyButton.disabled = false
  } finally {
    document.body.classList.remove('busy')
  }
})

restoreSettings()
if (typeof Office !== 'undefined') Office.onReady(() => setMessage('Word任务窗格已就绪。'))
