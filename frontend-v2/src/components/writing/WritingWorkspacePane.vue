<template>
  <section class="workspace-pane-body" :class="{ 'is-read-only': readOnly, 'has-document-toolbar': mode === 'document' && sourceDocument }">
    <header v-if="mode === 'document' && sourceDocument" class="document-view-toolbar">
      <el-segmented
        :model-value="documentViewMode"
        :options="documentViewOptions"
        size="small"
        @change="changeDocumentView(String($event) as DocumentViewMode)"
      />
      <span>{{ documentViewHint }}</span>
    </header>

    <WritingAiPane
      v-if="mode === 'ai'"
      :project-id="projectId"
      :target="aiTarget"
      :locked="aiTargetLocked"
      :conversation-id="aiConversationId"
      @lock-changed="emit('ai-lock-changed', $event)"
      @conversation-changed="emit('conversation-changed', $event)"
      @document-changed="emit('document-changed', $event)"
    />

    <div v-else-if="mode === 'document' && sourceDocument && documentViewMode === 'preview'" class="wps-preview">
      <el-skeleton v-if="previewLoading" animated :rows="12" />
      <iframe v-else-if="previewUrl" :src="previewUrl" :title="`${sourceDocument.title} WPS 预览`" />
      <el-empty v-else :description="previewError || '当前没有可用的格式校样'" :image-size="64">
        <el-button size="small" @click="loadPreview">重新加载</el-button>
      </el-empty>
    </div>

    <div v-else-if="mode === 'document' && sourceDocument && documentViewMode === 'office'" class="office-proof">
      <div class="office-proof-toolbar">
        <div>
          <el-tag size="small" :type="officeReady ? (officePilotLimited ? 'warning' : 'success') : 'info'">{{ officeReady ? (officePilotLimited ? 'G1 限制试点' : 'GenOffice 只读') : '引擎不可用' }}</el-tag>
          <span>{{ officeStatusText }}</span>
        </div>
        <div class="office-proof-actions">
          <el-button size="small" :loading="officeProofLoading" :disabled="!officeReady" @click="loadOfficeProof(true)">重新生成校样</el-button>
          <el-button size="small" :loading="officeCheckLoading" :disabled="!officeCheckReady" @click="runOfficeCheck">运行结构检查</el-button>
        </div>
      </div>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="只读取已导入的 Word 原件；不会写回正文、源文件或创建候选版本。"
      />
      <el-skeleton v-if="officeProofLoading" animated :rows="12" />
      <img v-else-if="officeProofUrl" :src="officeProofUrl" :alt="`${sourceDocument.title} Office 校样第 1 页`" />
      <el-empty v-else :description="officeProofError || '当前没有可用的 Office 校样'" :image-size="64">
        <el-button size="small" @click="loadOfficeProof(true)">重新加载</el-button>
      </el-empty>
      <section v-if="officeCheck" class="office-check-result">
        <div class="office-check-heading">
          <strong>结构检查</strong>
          <span>{{ officeCheck.check.summary }}</span>
        </div>
        <p>{{ officeCheck.source.notice }}</p>
        <ul v-if="officeCheck.check.issues.length">
          <li v-for="issue in officeCheck.check.issues" :key="issue.id || `${issue.code}-${issue.message}`">
            <span>{{ issue.level || 'info' }}</span>
            {{ issue.message || issue.code || '未命名检查项' }}
          </li>
        </ul>
        <p v-else>未发现 GenOffice 结构检查项。</p>
      </section>
    </div>

    <CollaborativeWritingEditor
      v-else-if="mode === 'document' && sourceDocument && sectionId"
      ref="documentEditor"
      :key="`document-${sourceDocument.id}-${sectionId}-${refreshToken}`"
      :project-id="projectId"
      :document-id="sourceDocument.id"
      :document-title="sourceDocument.title"
      :section-id="sectionId"
      :outline="outline"
      :selected-node-id="selectedNodeId"
      display-mode="document"
      :read-only="readOnly"
      @select-outline="emit('select-outline', $event)"
      @proposal-applied="emit('changed', 'document')"
      @context-changed="emit('context-changed', $event)"
    />

    <PresentationWorkspace
      v-else-if="mode === 'presentation' && presentationDocument"
      :key="`presentation-${presentationDocument.id}-${presentationSlide}-${refreshToken}`"
      :project-id="projectId"
      :document="presentationDocument"
      :initial-slide="presentationSlide"
      display-mode="slides"
      :read-only="readOnly"
      @changed="emit('changed', 'presentation')"
      @navigate-to-thesis="emit('navigate-to-thesis', $event)"
      @slide-changed="emit('slide-changed', $event)"
      @context-changed="emit('context-changed', $event)"
    />

    <DiagramWorkspace
      v-else-if="mode === 'diagram' && diagramId"
      ref="diagramEditor"
      :key="`diagram-${diagramId}-${refreshToken}`"
      :project-id="projectId"
      :diagram-id="diagramId"
      :read-only="readOnly"
      :document-target-id="documentTargetId"
      :document-section-id="documentTargetSectionId"
      :presentation-target-id="presentationTargetId"
      :presentation-slide="presentationTargetSlide"
      @changed="emit('changed', 'diagram')"
      @context-changed="emit('context-changed', $event)"
    />

    <el-empty v-else :description="emptyDescription" :image-size="64" />
  </section>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, ref, watch } from 'vue'
import CollaborativeWritingEditor from './CollaborativeWritingEditor.vue'
import PresentationWorkspace from './PresentationWorkspace.vue'
import WritingAiPane from './WritingAiPane.vue'
import {
  checkDocumentGenOfficeProof,
  getDocumentFidelityPreview,
  getDocumentGenOfficeProof,
  getGenOfficeStatus
} from '@/api/writing'
import type {
  GenOfficeReadOnlyCheck,
  GenOfficeReadOnlyStatus,
  WritingAiTarget,
  WritingDirectoryNode,
  WritingProjectDocument
} from '@/api/writing'

export type WritingPaneMode = 'document' | 'presentation' | 'diagram' | 'ai'
export type WritingPaneContext = WritingAiTarget
type DocumentViewMode = 'edit' | 'preview' | 'office'
const DiagramWorkspace = defineAsyncComponent(() => import('./DiagramWorkspace.vue'))

const props = defineProps<{
  mode: WritingPaneMode
  projectId: string
  sourceDocument?: WritingProjectDocument
  presentationDocument?: WritingProjectDocument
  diagramId?: string
  documentTargetId?: string
  documentTargetSectionId?: string
  presentationTargetId?: string
  presentationTargetSlide?: number
  sectionId: string
  outline: WritingDirectoryNode[]
  selectedNodeId?: string
  presentationSlide?: number
  refreshToken?: number
  readOnly?: boolean
  aiTarget?: WritingAiTarget
  aiTargetLocked?: boolean
  aiConversationId?: string
}>()

const emit = defineEmits<{
  changed: [kind: 'document' | 'presentation' | 'diagram']
  'select-outline': [node: WritingDirectoryNode]
  'navigate-to-thesis': [payload: { sourceDocumentId: string; section: string }]
  'slide-changed': [slide: number]
  'context-changed': [context: WritingPaneContext]
  'ai-lock-changed': [locked: boolean]
  'conversation-changed': [conversationId: string]
  'document-changed': [documentId: string]
}>()

const documentEditor = ref<InstanceType<typeof CollaborativeWritingEditor>>()
const diagramEditor = ref<{ flush?: () => Promise<boolean> }>()
const documentViewMode = ref<DocumentViewMode>('edit')
const documentViewOptions = [
  { label: '结构化编辑', value: 'edit' },
  { label: 'Office校样', value: 'office' },
  { label: 'WPS预览', value: 'preview' }
]
const previewLoading = ref(false)
const previewUrl = ref('')
const previewError = ref('')
const officeStatus = ref<GenOfficeReadOnlyStatus>()
const officeStatusLoading = ref(false)
const officeProofLoading = ref(false)
const officeProofUrl = ref('')
const officeProofError = ref('')
const officeCheckLoading = ref(false)
const officeCheck = ref<GenOfficeReadOnlyCheck>()
let officeRequestGeneration = 0
let officePaneUnmounted = false

interface OfficeRequestContext {
  generation: number
  projectId: string
  documentId: string
}
const officeReady = computed(() => (
  officeStatus.value?.mode === 'read_only' && officeStatus.value.capabilities.render
))
const officeCheckReady = computed(() => (
  officeStatus.value?.mode === 'read_only' && officeStatus.value.capabilities.docs_check
))
const officePilotLimited = computed(() => officeStatus.value?.pilot_gate !== 'accepted')
const documentViewHint = computed(() => {
  if (documentViewMode.value === 'edit') return '语义完整、可编辑'
  if (documentViewMode.value === 'preview') return '最终 DOCX 同源分页、只读'
  return '已导入 Word 原件的 GenOffice 第 1 页校样、只读'
})
const officeStatusText = computed(() => {
  if (officeStatusLoading.value) return '正在检测 GenOffice 引擎…'
  if (!officeStatus.value) return '等待 GenOffice 状态检测'
  if (officeReady.value) {
    const release = officeStatus.value.version || '已连接'
    const mcp = officeStatus.value.mcp_version ? ` · MCP ${officeStatus.value.mcp_version}` : ''
    const pilot = officePilotLimited.value ? ' · G1 限制试点' : ''
    return `GenOffice ${release}${mcp} · 只读模式${pilot}`
  }
  return officeStatus.value.reason || 'GenOffice 只读引擎不可用'
})
const emptyDescription = computed(() => {
  if (props.mode === 'document') return '当前项目没有可编辑的正文文档'
  if (props.mode === 'presentation') return '当前项目没有可用的 PPT'
  if (props.mode === 'diagram') return '当前项目没有可用的图表，请先新建图表'
  return '请先在另一窗口打开文档、PPT 或图表，建立 AI 目标上下文'
})

async function flush(): Promise<boolean> {
  if (props.mode === 'document') return (await documentEditor.value?.flushDraft?.()) !== false
  if (props.mode === 'diagram') return (await diagramEditor.value?.flush?.()) !== false
  return true
}

function clearPreview() {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
  previewError.value = ''
}

function clearOfficeProof() {
  if (officeProofUrl.value) URL.revokeObjectURL(officeProofUrl.value)
  officeProofUrl.value = ''
  officeProofError.value = ''
}

function currentOfficeRequestContext(): OfficeRequestContext | undefined {
  const documentId = props.sourceDocument?.id
  if (!documentId) return undefined
  return {
    generation: officeRequestGeneration,
    projectId: props.projectId,
    documentId
  }
}

function isCurrentOfficeRequest(context: OfficeRequestContext) {
  return !officePaneUnmounted
    && context.generation === officeRequestGeneration
    && context.projectId === props.projectId
    && context.documentId === props.sourceDocument?.id
}

function invalidateOfficeRequests() {
  officeRequestGeneration += 1
  officeStatus.value = undefined
  officeStatusLoading.value = false
  officeProofLoading.value = false
  officeCheckLoading.value = false
}

function errorMessage(error: any, fallback: string) {
  const detail = error?.response?.data?.detail
  return typeof detail === 'string' ? detail : error?.message || fallback
}

async function loadOfficeStatus(
  force = false,
  context = currentOfficeRequestContext()
): Promise<GenOfficeReadOnlyStatus | undefined> {
  if (!context) return undefined
  if (officeStatus.value && !force) return officeStatus.value
  if (officeStatusLoading.value) return officeStatus.value
  officeStatusLoading.value = true
  let status: GenOfficeReadOnlyStatus
  try {
    status = await getGenOfficeStatus()
  } catch (error: any) {
    status = {
      installed: false,
      reachable: false,
      version: '',
      channel: 'stable',
      mode: 'unavailable',
      capabilities: {
        docs_read: false,
        docs_check: false,
        render: false,
        docs_apply: false,
        visible_editor: false
      },
      reason: errorMessage(error, '无法获取 GenOffice 引擎状态')
    }
  } finally {
    if (isCurrentOfficeRequest(context)) officeStatusLoading.value = false
  }
  if (!isCurrentOfficeRequest(context)) return undefined
  officeStatus.value = status
  return status
}

async function loadOfficeProof(refreshStatus = false) {
  const context = currentOfficeRequestContext()
  if (!context || officeProofLoading.value) return
  const status = await loadOfficeStatus(refreshStatus, context)
  if (!isCurrentOfficeRequest(context)) return
  if (status?.mode !== 'read_only' || !status.capabilities.render) {
    clearOfficeProof()
    officeProofError.value = status?.reason || 'GenOffice Office 校样暂不可用'
    return
  }
  clearOfficeProof()
  officeProofLoading.value = true
  try {
    const blob = await getDocumentGenOfficeProof(context.projectId, context.documentId)
    if (!isCurrentOfficeRequest(context)) return
    officeProofUrl.value = URL.createObjectURL(blob)
  } catch (error: any) {
    if (!isCurrentOfficeRequest(context)) return
    officeProofError.value = errorMessage(error, 'Office 校样加载失败')
  } finally {
    if (isCurrentOfficeRequest(context)) officeProofLoading.value = false
  }
}

async function runOfficeCheck() {
  const context = currentOfficeRequestContext()
  if (!context || officeCheckLoading.value) return
  const status = await loadOfficeStatus(false, context)
  if (!isCurrentOfficeRequest(context)) return
  if (status?.mode !== 'read_only' || !status.capabilities.docs_check) {
    officeProofError.value = status?.reason || 'GenOffice 结构检查暂不可用'
    return
  }
  officeCheckLoading.value = true
  try {
    const result = await checkDocumentGenOfficeProof(context.projectId, context.documentId)
    if (!isCurrentOfficeRequest(context)) return
    officeCheck.value = result
  } catch (error: any) {
    if (!isCurrentOfficeRequest(context)) return
    officeProofError.value = errorMessage(error, 'Office 结构检查失败')
  } finally {
    if (isCurrentOfficeRequest(context)) officeCheckLoading.value = false
  }
}

async function loadPreview() {
  if (!props.sourceDocument?.id || previewLoading.value) return
  clearPreview()
  previewLoading.value = true
  try {
    const blob = await getDocumentFidelityPreview(props.projectId, props.sourceDocument.id)
    previewUrl.value = URL.createObjectURL(blob)
  } catch (error: any) {
    previewError.value = error?.response?.data?.detail || error?.message || 'WPS 预览加载失败'
  } finally {
    previewLoading.value = false
  }
}

async function changeDocumentView(mode: DocumentViewMode) {
  if (mode === documentViewMode.value) return
  if ((mode === 'preview' || mode === 'office') && !(await flush())) return
  documentViewMode.value = mode
  if (mode === 'preview') await loadPreview()
  if (mode === 'office') await loadOfficeProof()
}

watch(() => [props.projectId, props.sourceDocument?.id] as const, () => {
  invalidateOfficeRequests()
  clearPreview()
  clearOfficeProof()
  officeCheck.value = undefined
  if (documentViewMode.value === 'preview') void loadPreview()
  if (documentViewMode.value === 'office') void loadOfficeProof()
}, { flush: 'sync' })

onBeforeUnmount(() => {
  officePaneUnmounted = true
  invalidateOfficeRequests()
  clearPreview()
  clearOfficeProof()
})

defineExpose({ flush })
</script>

<style scoped>
.workspace-pane-body { display: grid; grid-template-rows: minmax(0, 1fr); min-width: 0; min-height: 700px; overflow: hidden; background: var(--content-bg); }
.workspace-pane-body.has-document-toolbar { grid-template-rows: auto minmax(0, 1fr); }
.document-view-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; min-height: 42px; padding: 6px 12px; border-bottom: 1px solid var(--line-color); background: var(--panel-bg); }
.document-view-toolbar span { color: var(--text-secondary); font-size: 11px; }
.wps-preview { min-height: 0; overflow: auto; padding: 10px; background: #111821; }
.wps-preview iframe { display: block; width: 100%; min-height: 720px; height: calc(100vh - 315px); border: 1px solid var(--line-color); background: #fff; }
.office-proof { min-height: 0; overflow: auto; padding: 10px; background: #111821; }
.office-proof-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 0 0 8px; color: var(--text-secondary); font-size: 12px; }
.office-proof-toolbar > div:first-child { display: flex; align-items: center; gap: 8px; min-width: 0; }
.office-proof-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 6px; }
.office-proof > :deep(.el-alert) { margin-bottom: 10px; }
.office-proof > img { display: block; max-width: 100%; margin: 0 auto; border: 1px solid var(--line-color); background: #fff; }
.office-check-result { margin-top: 10px; padding: 10px 12px; border: 1px solid var(--line-color); border-radius: 6px; background: var(--panel-bg); color: var(--text-primary); }
.office-check-heading { display: flex; justify-content: space-between; gap: 12px; }
.office-check-result p { margin: 8px 0 0; color: var(--text-secondary); font-size: 12px; }
.office-check-result ul { margin: 8px 0 0; padding-left: 18px; }
.office-check-result li { margin: 5px 0; }
.office-check-result li span { display: inline-block; min-width: 52px; color: var(--text-secondary); font-size: 11px; text-transform: uppercase; }
.workspace-pane-body.is-read-only::before { content: '只读对照'; position: absolute; z-index: 6; right: 12px; top: 12px; padding: 3px 7px; border: 1px solid var(--line-color); border-radius: 4px; color: var(--text-secondary); font-size: 10px; background: var(--panel-bg); }
.workspace-pane-body.is-read-only { position: relative; }
.workspace-pane-body :deep(.co-writing), .workspace-pane-body :deep(.presentation-workspace), .workspace-pane-body :deep(.diagram-workspace), .workspace-pane-body :deep(.writing-ai-pane) { min-height: 100%; border: 0; border-radius: 0; }
.workspace-pane-body :deep(.paper-scroll) { padding-inline: 18px; }
.workspace-pane-body :deep(.paper-page) { min-width: 720px; }
.workspace-pane-body :deep(.slide-viewer iframe) { min-height: 620px; }
@media (max-width: 1180px) {
  .workspace-pane-body { min-height: calc(100vh - 285px); }
  .workspace-pane-body :deep(.paper-page) { min-width: 0; }
}
</style>
