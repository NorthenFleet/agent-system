<template>
  <section ref="workspaceElement" class="presentation-workspace" :class="[`display-${displayMode}`, { 'is-read-only': readOnly }]" v-loading="loading">
    <header class="presentation-head">
      <div>
        <span class="eyebrow">PPT 演示工作区</span>
        <h3>{{ document.title }}</h3>
        <p>{{ presentationSummary }}</p>
      </div>
      <div v-if="displayMode === 'full'" class="actions">
        <input ref="fileInput" type="file" accept=".pptx" hidden @change="handleFile" />
        <el-button :icon="Upload" @click="fileInput?.click()">替换 PPTX</el-button>
        <el-button :icon="Download" @click="downloadSource">下载原稿</el-button>
        <el-button :icon="FullScreen" @click="openFullscreen">全屏</el-button>
        <el-button :icon="Refresh" circle @click="loadAll" />
      </div>
    </header>

    <el-alert
      v-if="displayMode === 'full'"
      :title="bindingMessage"
      :type="bindingAlertType"
      :closable="false"
      show-icon
    />

    <div v-if="displayMode === 'full'" class="presentation-metrics">
      <div><span>主答辩</span><strong>{{ presentationOutput.main_slide_count || 0 }} 页</strong></div>
      <div><span>附录</span><strong>{{ presentationOutput.appendix_slide_count || 0 }} 页</strong></div>
      <div><span>讲解稿</span><strong>{{ presentationOutput.notes_count || 0 }} 页</strong></div>
      <div><span>结构</span><strong>{{ structureVersionLabel }}</strong></div>
    </div>

    <div v-if="previewUrl || displayMode === 'ai'" class="presentation-stage" :class="`stage-${displayMode}`">
      <aside v-if="displayMode !== 'ai'" class="slide-rail">
        <button
          v-for="slide in slideCount"
          :key="slide"
          type="button"
          :class="{ active: selectedSlide === slide }"
          @click="setSelectedSlide(slide)"
        >
          <span>{{ slide }}</span>
          <em v-if="slide > mainSlideCount">附</em>
          <iframe
            :src="`${previewUrl}#page=${slide}&toolbar=0&navpanes=0&scrollbar=0&view=FitH`"
            :title="`第 ${slide} 页缩略图`"
            tabindex="-1"
          />
        </button>
      </aside>
      <main v-if="displayMode !== 'ai'" class="slide-viewer">
        <iframe
          :key="`${previewUrl}-${selectedSlide}`"
          :src="`${previewUrl}#page=${selectedSlide}&toolbar=1&navpanes=0&view=FitH`"
          :title="`${document.title} 第 ${selectedSlide} 页`"
        />
      </main>
      <aside v-if="displayMode !== 'slides'" class="presentation-inspector">
        <el-tabs v-model="inspectorTab" stretch>
          <el-tab-pane v-if="displayMode === 'full'" label="本页联动" name="binding">
            <div class="inspector-content">
              <span class="eyebrow">第 {{ selectedSlide }} 页</span>
              <h4>{{ currentSlide?.title || '未登记页面标题' }}</h4>
              <p class="claim">{{ currentSlide?.claim || '本页尚未建立论文主张映射。' }}</p>
              <section>
                <strong>对应论文章节</strong>
                <div v-if="currentSlide?.thesis_sections?.length" class="section-links">
                  <el-button
                    v-for="section in currentSlide.thesis_sections"
                    :key="section"
                    text
                    type="primary"
                    @click="navigateToThesis(section)"
                  >
                    {{ section }}
                  </el-button>
                </div>
                <small v-else>未映射</small>
              </section>
              <section>
                <strong>页面属性</strong>
                <dl>
                  <div><dt>位置</dt><dd>{{ currentSlide?.appendix ? '附录' : '主答辩' }}</dd></div>
                  <div><dt>源页</dt><dd>{{ currentSlide?.source_slide || selectedSlide }}</dd></div>
                  <div><dt>同步</dt><dd>{{ bindingStatusLabel }}</dd></div>
                </dl>
              </section>
            </div>
          </el-tab-pane>
          <el-tab-pane v-if="displayMode === 'full'" label="讲解稿" name="notes">
            <div class="inspector-content">
              <pre>{{ currentSlide?.notes || '本页尚未登记讲解稿。' }}</pre>
            </div>
          </el-tab-pane>
          <el-tab-pane v-if="displayMode === 'full'" label="证据" name="evidence">
            <div class="inspector-content">
              <el-tag :type="evidenceTagType" effect="plain">
                {{ currentSlide?.evidence_level || '未分级' }}
              </el-tag>
              <p>{{ evidenceDescription }}</p>
              <section>
                <strong>证据编号</strong>
                <div v-if="currentSlide?.evidence_ids?.length" class="evidence-list">
                  <code v-for="evidence in currentSlide.evidence_ids" :key="evidence">{{ evidence }}</code>
                </div>
                <small v-else>无独立实验编号</small>
              </section>
              <el-alert
                v-if="currentSlide?.evidence_level !== 'A级'"
                title="A级实验完成前，不据此宣称统计显著优于基线。"
                type="warning"
                :closable="false"
                show-icon
              />
            </div>
          </el-tab-pane>
          <el-tab-pane label="人机双写" name="collaboration">
            <div class="inspector-content slide-collaboration">
              <span class="eyebrow">当前页结构化编辑</span>
              <label>
                <small>页面标题</small>
                <el-input v-model="slideDraft.title" placeholder="输入当前页标题" />
              </label>
              <label>
                <small>核心主张</small>
                <el-input v-model="slideDraft.claim" type="textarea" :rows="3" resize="none" placeholder="本页要向观众证明什么" />
              </label>
              <label>
                <small>讲解稿</small>
                <el-input v-model="slideDraft.notes" type="textarea" :rows="5" resize="vertical" placeholder="答辩或授课时的讲解稿" />
              </label>
              <div class="slide-meta-grid">
                <label>
                  <small>证据等级</small>
                  <el-select v-model="slideDraft.evidence_level" placeholder="选择等级">
                    <el-option label="A级" value="A级" />
                    <el-option label="B级" value="B级" />
                    <el-option label="C级" value="C级" />
                    <el-option label="D级" value="D级" />
                  </el-select>
                </label>
                <label>
                  <small>页面位置</small>
                  <el-select v-model="slideDraft.appendix">
                    <el-option label="主答辩" :value="false" />
                    <el-option label="附录" :value="true" />
                  </el-select>
                </label>
              </div>
              <label>
                <small>证据编号</small>
                <el-input v-model="slideDraft.evidence_ids_text" placeholder="多个编号用逗号分隔，如 MODEL-2.1, RUN-M0" />
              </label>
              <label>
                <small>AI 微调指令</small>
                <el-input
                  v-model="aiInstruction"
                  type="textarea"
                  :rows="3"
                  resize="none"
                  placeholder="例如：压缩标题、强化答辩表达、补充证据边界"
                />
              </label>
              <div class="slide-collaboration-actions">
                <el-button :loading="aiBusy" :icon="Refresh" @click="generateSlideProposal">生成建议</el-button>
                <el-button type="primary" :loading="savingManifest" @click="saveSlideDraft">保存本页</el-button>
              </div>
              <article v-if="slideProposal" class="slide-proposal">
                <header>
                  <strong>{{ slideProposal.title }}</strong>
                  <el-tag size="small" effect="plain">待确认</el-tag>
                </header>
                <p>{{ slideProposal.summary }}</p>
                <dl>
                  <div><dt>标题</dt><dd>{{ slideProposal.patch.title }}</dd></div>
                  <div><dt>主张</dt><dd>{{ slideProposal.patch.claim }}</dd></div>
                  <div><dt>证据</dt><dd>{{ slideProposal.patch.evidence_level }} · {{ slideProposal.patch.evidence_ids_text || '无编号' }}</dd></div>
                </dl>
                <pre>{{ slideProposal.patch.notes }}</pre>
                <div>
                  <el-button size="small" @click="slideProposal = undefined">拒绝</el-button>
                  <el-button size="small" type="primary" @click="acceptSlideProposal">接受到草稿</el-button>
                </div>
              </article>
            </div>
          </el-tab-pane>
          <el-tab-pane v-if="displayMode === 'full'" label="版本记录" name="versions">
            <div class="presentation-history inspector-content">
              <div v-for="version in versions" :key="version.name">
                <strong>{{ version.name }}</strong>
                <small>{{ formatDate(version.created_at) }} · {{ formatFileSize(version.size_bytes) }}</small>
                <el-button
                  v-if="!version.current"
                  text
                  type="primary"
                  size="small"
                  @click="restoreVersion(version.name)"
                >恢复此版本</el-button>
              </div>
            </div>
          </el-tab-pane>
        </el-tabs>
      </aside>
    </div>
    <el-empty v-else-if="!loading" description="尚未生成 PPT 预览，可上传或重新替换 PPTX" />

    <DocumentEvaluationPanel
      v-if="displayMode === 'full'"
      compact
      :profile="evaluation.profile.value"
      :report="evaluation.report.value"
      :linked-summary="evaluation.linkedSummary.value"
      :profiles="evaluation.profiles.value"
      :busy="evaluation.busy.value"
      @run="evaluation.run"
      @confirm="evaluation.confirm"
      @save-profile="evaluation.saveProfile"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Download, FullScreen, Refresh, Upload } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import DocumentEvaluationPanel from './DocumentEvaluationPanel.vue'
import { useDocumentEvaluation } from './useDocumentEvaluation'
import {
  createPresentationSlideJob,
  getDocumentWritingVersions,
  getPresentationManifest,
  getPresentationPreview,
  getPresentationSlideJob,
  getWritingDocumentSource,
  replaceWritingDocumentContent,
  restoreWritingDocumentVersion,
  updateDocumentStructureBinding,
  type PresentationManifest,
  type PresentationSlideProposal,
  type WritingProjectDocument
} from '@/api/writing'

const props = defineProps<{
  projectId: string
  document: WritingProjectDocument
  initialSlide?: number
  displayMode?: 'full' | 'slides' | 'ai'
  readOnly?: boolean
}>()
const emit = defineEmits<{
  changed: []
  'navigate-to-thesis': [payload: { sourceDocumentId: string; section: string }]
  'slide-changed': [slide: number]
  'context-changed': [context: {
    kind: 'presentation'
    document_id: string
    document_title: string
    slide: number
    structure_revision: number
    draft: Record<string, unknown>
  }]
}>()
const displayMode = computed(() => props.displayMode || 'full')
const loading = ref(false)
const previewUrl = ref('')
const selectedSlide = ref(1)
const inspectorTab = ref('binding')
const fileInput = ref<HTMLInputElement>()
const workspaceElement = ref<HTMLElement>()
const versions = ref<Array<{ name: string; size_bytes: number; created_at: string; current?: boolean }>>([])
const manifest = ref<PresentationManifest>()
const savingManifest = ref(false)
const aiBusy = ref(false)
const activeSlideJobId = ref('')
const aiInstruction = ref('强化本页答辩表达，保持证据边界，不新增无法核验的结论。')
const slideDraft = ref({
  title: '',
  claim: '',
  notes: '',
  evidence_level: '',
  evidence_ids_text: '',
  appendix: false
})
const slideProposal = ref<{
  title: string
  summary: string
  rationale?: string
  patch: typeof slideDraft.value
}>()
const evaluation = useDocumentEvaluation(
  () => props.projectId,
  () => props.document.id
)
const slideCount = computed(() => Math.max(1, Number(props.document.stats?.slide_count || 1)))
const presentationOutput = computed(() => manifest.value?.authority?.presentation_output || {})
const mainSlideCount = computed(() => Number(
  presentationOutput.value.main_slide_count
    || props.document.stats?.main_slide_count
    || slideCount.value
))
const currentSlide = computed(() => (
  manifest.value?.slides.find(row => Number(row.slide) === selectedSlide.value)
))
const binding = computed(() => manifest.value?.structure_binding || props.document.structure_binding)
const documentVersionLabel = computed(() => {
  const value = String(presentationOutput.value.document_version || props.document.data_version || `v${props.document.revision}`)
  return value.startsWith('文档') ? value : `文档${value}`
})
const structureVersionLabel = computed(() => {
  const value = String(presentationOutput.value.structure_version || props.document.rules_version || '')
  if (!value) return '未绑定'
  return value.startsWith('结构') ? value : `结构${value}`
})
const presentationSummary = computed(() => {
  return `PPT · ${documentVersionLabel.value} · ${slideCount.value}页 · ${structureVersionLabel.value} · ${publicationLabel(props.document.publication_status)}`
})
const bindingStatusLabel = computed(() => ({
  aligned: '一致',
  diverged: '有差异',
  stale: '已过期',
  missing: '未绑定'
} as Record<string, string>)[binding.value?.status || 'missing'])
const bindingMessage = computed(() => {
  if (binding.value?.status === 'aligned') {
    return `当前PPT与源文档 ${binding.value.source_version || ''} 结构一致；浏览器使用静态PDF预览，动画保留在PPTX原稿中。`
  }
  if (binding.value?.status === 'stale') return 'PPT文件或源正文已变化，逐页映射已过期，请重新校验后再用于答辩。'
  if (binding.value?.status === 'diverged') return 'PPT存在未映射页面或变更章节，请完成差异核校。'
  return '当前PPT尚未建立正文结构绑定。'
})
const bindingAlertType = computed(() => (
  binding.value?.status === 'aligned'
    ? 'success'
    : binding.value?.status === 'missing'
      ? 'info'
      : 'warning'
))
const evidenceTagType = computed(() => (
  currentSlide.value?.evidence_level === 'A级'
    ? 'success'
    : currentSlide.value?.evidence_level === 'B级'
      ? 'primary'
      : currentSlide.value?.evidence_level === 'C级'
        ? 'warning'
        : 'info'
))
const evidenceDescription = computed(() => {
  const level = currentSlide.value?.evidence_level
  return ({
    'A级': '多随机种子、基线对比、置信区间和显著性检验。',
    'B级': '可复核系统输出或单次运行证据。',
    'C级': '模型、算法或形式化推导证据。',
    'D级': '研究动机、结构性判断或答辩组织信息。'
  } as Record<string, string>)[level || ''] || '本页尚未登记证据等级。'
})

async function loadPreview() {
  loading.value = true
  revokePreview()
  try {
    const [blob, history, presentationManifest] = await Promise.all([
      getPresentationPreview(props.projectId, props.document.id),
      getDocumentWritingVersions(props.projectId, props.document.id),
      getPresentationManifest(props.projectId, props.document.id)
    ])
    previewUrl.value = URL.createObjectURL(blob)
    versions.value = history.versions
    manifest.value = presentationManifest
    const requestedSlide = Number(props.initialSlide || selectedSlide.value || 1)
    setSelectedSlide(Math.min(Math.max(requestedSlide, 1), slideCount.value))
  } catch (error) {
    ElMessage.error(errorMessage(error, 'PPT 预览加载失败'))
  } finally {
    loading.value = false
  }
}

async function loadEvaluation() {
  try {
    await evaluation.load()
  } catch (error) {
    ElMessage.error(errorMessage(error, 'PPT评价加载失败'))
  }
}

async function loadAll() {
  await Promise.all([loadPreview(), loadEvaluation()])
}

function setSelectedSlide(slide: number) {
  selectedSlide.value = Math.min(Math.max(Number(slide || 1), 1), slideCount.value)
  syncSlideDraft()
  emit('slide-changed', selectedSlide.value)
}

function navigateToThesis(section: string) {
  const sourceDocumentId = String(binding.value?.source_document_id || '')
  if (!sourceDocumentId) {
    ElMessage.warning('本页尚未绑定源正文')
    return
  }
  emit('navigate-to-thesis', { sourceDocumentId, section })
}

async function handleFile(event: Event) {
  if (props.readOnly) return
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  loading.value = true
  try {
    await replaceWritingDocumentContent(props.projectId, props.document.id, file)
    ElMessage.success('PPTX 已替换并生成新版本')
    emit('changed')
    await loadAll()
  } catch (error) {
    ElMessage.error(errorMessage(error, 'PPTX 替换失败'))
  } finally {
    target.value = ''
    loading.value = false
  }
}

async function downloadSource() {
  try {
    const blob = await getWritingDocumentSource(props.projectId, props.document.id)
    downloadBlob(blob, `${props.document.title}.pptx`)
  } catch (error) {
    ElMessage.error(errorMessage(error, 'PPTX 下载失败'))
  }
}

async function openFullscreen() {
  try {
    await workspaceElement.value?.requestFullscreen()
  } catch {
    ElMessage.warning('当前浏览器未允许全屏显示')
  }
}

async function restoreVersion(versionName: string) {
  try {
    await ElMessageBox.confirm(
      `恢复“${versionName}”作为当前 PPT？现有版本会先自动备份。`,
      '恢复 PPT 版本',
      { type: 'warning', confirmButtonText: '恢复', cancelButtonText: '取消' }
    )
    loading.value = true
    await restoreWritingDocumentVersion(props.projectId, props.document.id, versionName)
    ElMessage.success('PPT 历史版本已恢复')
    emit('changed')
    await loadAll()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(errorMessage(error, 'PPT 版本恢复失败'))
  } finally {
    loading.value = false
  }
}

function syncSlideDraft() {
  const slide = currentSlide.value
  slideDraft.value = {
    title: String(slide?.title || ''),
    claim: String(slide?.claim || ''),
    notes: String(slide?.notes || ''),
    evidence_level: String(slide?.evidence_level || ''),
    evidence_ids_text: (slide?.evidence_ids || []).join(', '),
    appendix: Boolean(slide?.appendix)
  }
  slideProposal.value = undefined
}

function evidenceIdsFromDraft(value: string) {
  return value.split(/[,，\n]/).map(item => item.trim()).filter(Boolean)
}

function manifestWithCurrentSlideDraft(patch = slideDraft.value) {
  if (!manifest.value) return undefined
  const next = JSON.parse(JSON.stringify(manifest.value)) as PresentationManifest
  const slides = next.slides || []
  const index = slides.findIndex(row => Number(row.slide) === selectedSlide.value)
  const current = index >= 0
    ? slides[index]
    : {
        slide: selectedSlide.value,
        source_slide: selectedSlide.value,
        thesis_sections: [],
        appendix: selectedSlide.value > mainSlideCount.value
      }
  const updated = {
    ...current,
    title: patch.title.trim(),
    claim: patch.claim.trim(),
    notes: patch.notes.trim(),
    evidence_level: patch.evidence_level.trim(),
    evidence_ids: evidenceIdsFromDraft(patch.evidence_ids_text),
    appendix: Boolean(patch.appendix)
  }
  if (index >= 0) slides[index] = updated
  else slides.push(updated)
  next.slides = slides.sort((left, right) => Number(left.slide) - Number(right.slide))
  next.authority = next.authority || {}
  next.authority.presentation_output = {
    ...(next.authority.presentation_output || {}),
    slide_count: next.slides.length,
    main_slide_count: next.slides.filter(slide => !slide.appendix).length,
    appendix_slide_count: next.slides.filter(slide => slide.appendix).length,
    notes_count: next.slides.filter(slide => String(slide.notes || '').trim()).length
  }
  return next
}

async function saveSlideDraft() {
  if (props.readOnly) return
  const nextManifest = manifestWithCurrentSlideDraft()
  const currentBinding = binding.value
  if (!nextManifest || !currentBinding?.source_document_id) {
    ElMessage.warning('当前 PPT 尚未绑定源正文，不能保存逐页人机双写结果')
    return
  }
  savingManifest.value = true
  try {
    const nextBinding = await updateDocumentStructureBinding(props.projectId, props.document.id, {
      mode: currentBinding.mode || 'mapped',
      source_document_id: currentBinding.source_document_id,
      source_version: currentBinding.source_version || '',
      source_sha256: currentBinding.source_sha256 || '',
      status: currentBinding.status || 'aligned',
      mapped_items: currentBinding.mapped_items || 0,
      unmapped_items: currentBinding.unmapped_items || [],
      changed_sections: currentBinding.changed_sections || [],
      manifest: nextManifest
    })
    nextManifest.structure_binding = nextBinding
    manifest.value = nextManifest
    syncSlideDraft()
    emit('changed')
    ElMessage.success('当前页人机双写结果已保存到 PPT 联动清单')
  } catch (error) {
    ElMessage.error(errorMessage(error, '当前页保存失败'))
  } finally {
    savingManifest.value = false
  }
}

async function generateSlideProposal() {
  if (props.readOnly) return
  if (!manifest.value) {
    ElMessage.warning('PPT 联动清单尚未加载')
    return
  }
  aiBusy.value = true
  try {
    const job = await createPresentationSlideJob(props.projectId, props.document.id, {
      slide: selectedSlide.value,
      instruction: aiInstruction.value.trim() || '强化本页答辩表达，保持证据边界。',
      agent_id: 'presentation-editor',
      client_request_id: globalThis.crypto?.randomUUID?.() || `ppt-${Date.now()}`,
      draft: {
        title: slideDraft.value.title,
        claim: slideDraft.value.claim,
        notes: slideDraft.value.notes,
        evidence_level: slideDraft.value.evidence_level,
        evidence_ids: evidenceIdsFromDraft(slideDraft.value.evidence_ids_text),
        appendix: slideDraft.value.appendix
      }
    })
    activeSlideJobId.value = job.id
    await handleSlideJob(job)
  } catch (error) {
    activeSlideJobId.value = ''
    ElMessage.error(errorMessage(error, 'PPT 页面建议生成失败'))
  } finally {
    if (!activeSlideJobId.value) aiBusy.value = false
  }
}

async function handleSlideJob(job: { id: string; status: string; proposal?: PresentationSlideProposal | null; error?: string }) {
  if (job.status === 'succeeded' && job.proposal) {
    slideProposal.value = proposalToDraft(job.proposal)
    activeSlideJobId.value = ''
    aiBusy.value = false
    return
  }
  if (job.status === 'failed') {
    throw new Error(job.error || 'PPT 页面建议生成失败')
  }
  window.setTimeout(() => {
    void pollSlideJob(job.id)
  }, 1000)
}

async function pollSlideJob(jobId: string) {
  if (!jobId || activeSlideJobId.value !== jobId) return
  try {
    const job = await getPresentationSlideJob(props.projectId, props.document.id, jobId)
    await handleSlideJob(job)
  } catch (error) {
    activeSlideJobId.value = ''
    aiBusy.value = false
    ElMessage.error(errorMessage(error, 'PPT 页面建议任务查询失败'))
  }
}

function proposalToDraft(proposal: PresentationSlideProposal) {
  return {
    title: proposal.title || 'AI 页面微调建议',
    summary: proposal.summary || '已生成结构化修改建议。',
    rationale: proposal.rationale,
    patch: {
      title: proposal.patch.title || '',
      claim: proposal.patch.claim || '',
      notes: proposal.patch.notes || '',
      evidence_level: proposal.patch.evidence_level || '',
      evidence_ids_text: (proposal.patch.evidence_ids || []).join(', '),
      appendix: Boolean(proposal.patch.appendix)
    }
  }
}

function acceptSlideProposal() {
  if (!slideProposal.value || props.readOnly) return
  slideDraft.value = { ...slideProposal.value.patch }
  slideProposal.value = undefined
}

function revokePreview() {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
}

function downloadBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = name
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

function formatDate(value: string) {
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

function formatFileSize(value: number) {
  return value > 1024 * 1024 ? `${(value / 1024 / 1024).toFixed(1)} MB` : `${Math.round(value / 1024)} KB`
}

function publicationLabel(status: WritingProjectDocument['publication_status']) {
  return ({
    draft: '草稿',
    review: '核校',
    approved: '已批准',
    published: '已发布',
    internal: '内部'
  } as Record<string, string>)[status] || status
}

function errorMessage(error: unknown, fallback: string) {
  return (error as any)?.response?.data?.detail || fallback
}

watch(() => props.document.id, loadAll)
watch(displayMode, value => {
  if (value === 'ai') inspectorTab.value = 'collaboration'
}, { immediate: true })
watch(() => props.initialSlide, value => {
  if (value) setSelectedSlide(value)
})
watch(currentSlide, syncSlideDraft)
watch(
  () => [props.document.id, props.document.revision, selectedSlide.value, JSON.stringify(slideDraft.value)],
  () => emit('context-changed', {
    kind: 'presentation',
    document_id: props.document.id,
    document_title: props.document.title,
    slide: selectedSlide.value,
    structure_revision: Number(props.document.revision || 0),
    draft: { ...slideDraft.value }
  }),
  { immediate: true }
)
onMounted(loadAll)
onBeforeUnmount(() => {
  revokePreview()
  evaluation.dispose()
})
</script>

<style scoped>
.presentation-workspace { display: grid; gap: 12px; min-width: 0; min-height: 620px; background: var(--content-bg); }
.presentation-workspace.is-read-only :deep(.presentation-inspector input),
.presentation-workspace.is-read-only :deep(.presentation-inspector textarea),
.presentation-workspace.is-read-only :deep(.presentation-inspector button) { pointer-events: none; opacity: .56; }
.presentation-workspace.display-slides, .presentation-workspace.display-ai { min-height: 100%; }
.presentation-workspace.display-slides .presentation-head, .presentation-workspace.display-ai .presentation-head { padding: 10px 12px; border-bottom: 1px solid var(--line-color); background: var(--panel-bg); }
.presentation-workspace.display-slides .presentation-head h3, .presentation-workspace.display-ai .presentation-head h3 { font-size: 14px; }
.presentation-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.presentation-head h3 { margin: 4px 0 0; color: var(--text-primary); font-size: 18px; }
.presentation-head p { margin: 6px 0 0; color: var(--text-secondary); font-size: 11px; }
.eyebrow { color: var(--view-color-primary); font-size: 11px; }
.actions { display: flex; gap: 8px; }
.presentation-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); border: 1px solid var(--line-color); background: var(--card-bg); }
.presentation-metrics > div { display: grid; gap: 3px; padding: 9px 12px; border-right: 1px solid var(--line-color); }
.presentation-metrics > div:last-child { border-right: 0; }
.presentation-metrics span { color: var(--text-secondary); font-size: 9px; }
.presentation-metrics strong { color: var(--text-primary); font-size: 12px; }
.presentation-stage { display: grid; grid-template-columns: 190px minmax(0, 1fr) 320px; gap: 12px; min-height: calc(100vh - 340px); }
.presentation-stage.stage-slides { grid-template-columns: 150px minmax(0, 1fr); min-height: 100%; }
.presentation-stage.stage-ai { display: block; min-height: 100%; }
.presentation-workspace.display-ai .presentation-inspector { max-height: none; border: 0; }
.presentation-workspace.display-ai :deep(.el-tabs__header) { display: none; }
.slide-rail, .presentation-inspector { max-height: calc(100vh - 340px); overflow-y: auto; border: 1px solid var(--line-color); background: var(--card-bg); }
.slide-rail { display: grid; align-content: start; gap: 8px; padding: 8px; }
.slide-rail button { position: relative; height: 112px; overflow: hidden; padding: 0; border: 2px solid transparent; background: #fff; cursor: pointer; }
.slide-rail button.active { border-color: var(--view-color-primary); }
.slide-rail button > span { position: absolute; z-index: 2; left: 4px; bottom: 3px; padding: 1px 4px; color: #fff; font-size: 9px; background: rgba(0,0,0,.72); }
.slide-rail button > em { position: absolute; z-index: 2; right: 4px; top: 3px; padding: 1px 4px; color: #fff; font-style: normal; font-size: 9px; background: rgba(230,126,34,.88); }
.slide-rail iframe { width: 400%; height: 400%; border: 0; pointer-events: none; transform: scale(.25); transform-origin: 0 0; }
.slide-viewer { min-width: 0; overflow: hidden; border: 1px solid var(--line-color); background: #111; }
.slide-viewer iframe { width: 100%; height: 100%; min-height: 650px; border: 0; background: #fff; }
.presentation-inspector { min-width: 0; padding: 0 12px 12px; }
.inspector-content { display: grid; gap: 12px; min-width: 0; color: var(--text-primary); }
.inspector-content h4 { margin: 0; font-size: 14px; line-height: 1.5; }
.inspector-content .claim { margin: 0; color: var(--text-secondary); font-size: 11px; line-height: 1.7; }
.inspector-content section { display: grid; gap: 7px; padding-top: 10px; border-top: 1px solid var(--line-color); }
.inspector-content section > strong { font-size: 11px; }
.inspector-content pre { margin: 0; color: var(--text-primary); font-family: inherit; font-size: 11px; line-height: 1.8; white-space: pre-wrap; overflow-wrap: anywhere; }
.inspector-content dl { display: grid; margin: 0; }
.inspector-content dl > div { display: flex; justify-content: space-between; gap: 8px; padding: 5px 0; border-bottom: 1px solid var(--line-color); font-size: 10px; }
.inspector-content dt { color: var(--text-secondary); }
.inspector-content dd { margin: 0; text-align: right; }
.section-links { display: flex; flex-wrap: wrap; gap: 4px; }
.section-links .el-button { height: auto; margin: 0; padding: 2px 0; font-size: 10px; white-space: normal; text-align: left; }
.evidence-list { display: grid; gap: 5px; }
.evidence-list code { padding: 5px 7px; color: var(--view-color-primary); font-size: 10px; background: var(--view-color-faint); overflow-wrap: anywhere; }
.presentation-history { padding: 0; }
.presentation-history > div { display: grid; gap: 4px; padding: 9px 0; border-bottom: 1px solid var(--line-color); }
.presentation-history strong { color: var(--text-primary); font-size: 11px; }
.presentation-history small { color: var(--text-secondary); font-size: 9px; line-height: 1.5; }
.presentation-workspace:fullscreen { padding: 14px; overflow: auto; }
.presentation-workspace:fullscreen .presentation-stage { min-height: calc(100vh - 120px); }
@media (max-width: 1100px) {
  .presentation-stage { grid-template-columns: 150px minmax(0, 1fr); }
  .presentation-stage.stage-ai { display: block; }
  .presentation-inspector { grid-column: 1 / -1; max-height: 320px; }
}
@media (max-width: 760px) {
  .presentation-head { flex-direction: column; }
  .presentation-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .presentation-stage { grid-template-columns: 1fr; }
  .slide-rail { grid-auto-flow: column; grid-auto-columns: 130px; overflow-x: auto; }
  .slide-viewer iframe { min-height: 480px; }
}
</style>
