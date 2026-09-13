<template>
  <section class="workspace-pane-body" :class="{ 'is-read-only': readOnly, 'has-document-toolbar': mode === 'document' && sourceDocument }">
    <header v-if="mode === 'document' && sourceDocument" class="document-view-toolbar">
      <el-segmented
        :model-value="documentViewMode"
        :options="documentViewOptions"
        size="small"
        @change="changeDocumentView(String($event) as DocumentViewMode)"
      />
      <span>{{ documentViewMode === 'edit' ? '语义完整、可编辑' : '最终 DOCX 同源分页、只读' }}</span>
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
import { getDocumentFidelityPreview } from '@/api/writing'
import type {
  WritingAiTarget,
  WritingDirectoryNode,
  WritingProjectDocument
} from '@/api/writing'

export type WritingPaneMode = 'document' | 'presentation' | 'diagram' | 'ai'
export type WritingPaneContext = WritingAiTarget
type DocumentViewMode = 'edit' | 'preview'
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
  { label: '编辑视图', value: 'edit' },
  { label: 'WPS预览', value: 'preview' }
]
const previewLoading = ref(false)
const previewUrl = ref('')
const previewError = ref('')
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
  if (mode === 'preview' && !(await flush())) return
  documentViewMode.value = mode
  if (mode === 'preview') await loadPreview()
}

watch(() => props.sourceDocument?.id, () => {
  clearPreview()
  if (documentViewMode.value === 'preview') void loadPreview()
})

onBeforeUnmount(clearPreview)

defineExpose({ flush })
</script>

<style scoped>
.workspace-pane-body { display: grid; grid-template-rows: minmax(0, 1fr); min-width: 0; min-height: 700px; overflow: hidden; background: var(--content-bg); }
.workspace-pane-body.has-document-toolbar { grid-template-rows: auto minmax(0, 1fr); }
.document-view-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; min-height: 42px; padding: 6px 12px; border-bottom: 1px solid var(--line-color); background: var(--panel-bg); }
.document-view-toolbar span { color: var(--text-secondary); font-size: 11px; }
.wps-preview { min-height: 0; overflow: auto; padding: 10px; background: #111821; }
.wps-preview iframe { display: block; width: 100%; min-height: 720px; height: calc(100vh - 315px); border: 1px solid var(--line-color); background: #fff; }
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
