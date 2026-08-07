import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  confirmDocumentEvaluation,
  getDocumentEvaluation,
  getDocumentEvaluationJob,
  getDocumentEvaluationProfile,
  getEvaluationProfiles,
  getLinkedDocumentEvaluationSummary,
  runDocumentEvaluation,
  updateDocumentEvaluationProfile,
  type DocumentEvaluationProfile,
  type DocumentEvaluationReport,
  type LinkedDocumentEvaluationSummary,
  type WritingDocumentKind
} from '@/api/writing'

export function useDocumentEvaluation(
  projectId: () => string,
  documentId: () => string
) {
  const profile = ref<DocumentEvaluationProfile>()
  const report = ref<DocumentEvaluationReport>()
  const linkedSummary = ref<LinkedDocumentEvaluationSummary>()
  const profiles = ref<Array<{
    id: string
    name: string
    version: string
    kind: WritingDocumentKind
  }>>([])
  const busy = ref(false)
  let pollTimer: ReturnType<typeof setTimeout> | undefined

  function clearPolling() {
    if (pollTimer) clearTimeout(pollTimer)
    pollTimer = undefined
  }

  async function load() {
    const currentProjectId = projectId()
    const currentDocumentId = documentId()
    if (!currentProjectId || !currentDocumentId) return
    const [nextProfile, nextReport, nextLinked, catalog] = await Promise.all([
      getDocumentEvaluationProfile(currentProjectId, currentDocumentId),
      getDocumentEvaluation(currentProjectId, currentDocumentId),
      getLinkedDocumentEvaluationSummary(currentProjectId),
      profiles.value.length ? Promise.resolve(undefined) : getEvaluationProfiles()
    ])
    if (currentProjectId !== projectId() || currentDocumentId !== documentId()) return
    profile.value = nextProfile
    report.value = nextReport
    linkedSummary.value = nextLinked
    if (catalog) profiles.value = catalog.profiles
  }

  async function pollJob(jobId: string, attempt = 0) {
    clearPolling()
    const currentProjectId = projectId()
    const currentDocumentId = documentId()
    try {
      const job = await getDocumentEvaluationJob(
        currentProjectId,
        currentDocumentId,
        jobId
      )
      if (currentProjectId !== projectId() || currentDocumentId !== documentId()) return
      if (!job || ['succeeded', 'failed'].includes(job.status)) {
        await load()
        busy.value = false
        if (job?.status === 'succeeded') ElMessage.success('完整文档评价已完成')
        if (job?.status === 'failed') {
          ElMessage.warning(job.error || '学术评价未完成，已保留技术检查结果')
        }
        return
      }
      if (attempt >= 200) {
        busy.value = false
        ElMessage.warning('评价仍在后台执行，可稍后刷新查看')
        return
      }
      pollTimer = setTimeout(() => pollJob(jobId, attempt + 1), 3000)
    } catch (error) {
      busy.value = false
      ElMessage.error(errorMessage(error, '评价任务状态读取失败'))
    }
  }

  async function run(mode: 'technical' | 'full') {
    busy.value = true
    try {
      const result = await runDocumentEvaluation(projectId(), documentId(), mode)
      report.value = result.report
      if (result.job) {
        ElMessage.info('完整评价已进入后台执行')
        await pollJob(result.job.id)
      } else {
        await load()
        busy.value = false
        ElMessage.success('技术完整度已刷新')
      }
    } catch (error) {
      busy.value = false
      ElMessage.error(errorMessage(error, '文档评价启动失败'))
    }
  }

  async function confirm(payload: {
    dimension_scores: Record<string, number>
    gate_statuses: Record<string, 'pass' | 'fail' | 'not_applicable'>
    comment: string
  }) {
    busy.value = true
    try {
      report.value = await confirmDocumentEvaluation(projectId(), documentId(), {
        ...payload,
        actor: 'admin'
      })
      linkedSummary.value = await getLinkedDocumentEvaluationSummary(projectId())
      ElMessage.success('专家确认已保存并写入审计记录')
    } catch (error) {
      ElMessage.error(errorMessage(error, '专家确认保存失败'))
    } finally {
      busy.value = false
    }
  }

  async function saveProfile(payload: {
    profile_id: string
    overrides: {
      pass_threshold: number
      dimension_weights: Record<string, number>
      dimension_min_scores: Record<string, number>
      gate_required: Record<string, boolean>
    }
  }) {
    busy.value = true
    try {
      profile.value = await updateDocumentEvaluationProfile(projectId(), documentId(), {
        ...payload,
        actor: 'admin'
      })
      const result = await runDocumentEvaluation(projectId(), documentId(), 'technical')
      report.value = result.report
      linkedSummary.value = await getLinkedDocumentEvaluationSummary(projectId())
      ElMessage.success('评价标准已更新，旧学术评价已失效')
    } catch (error) {
      ElMessage.error(errorMessage(error, '评价标准保存失败'))
    } finally {
      busy.value = false
    }
  }

  return {
    profile,
    report,
    linkedSummary,
    profiles,
    busy,
    load,
    run,
    confirm,
    saveProfile,
    dispose: clearPolling
  }
}

function errorMessage(error: unknown, fallback: string) {
  return (error as any)?.response?.data?.detail || fallback
}
