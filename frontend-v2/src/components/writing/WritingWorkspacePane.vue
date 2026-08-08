<template>
  <section ref="paneRoot" class="workspace-pane-body" :class="{ 'is-read-only': readOnly }" @scroll.capture="handleScroll">
    <WritingAiPane
      v-if="mode === 'ai'"
      :project-id="projectId"
      :target="aiTarget"
      :locked="aiTargetLocked"
      :conversation-id="aiConversationId"
      @lock-changed="emit('ai-lock-changed', $event)"
      @conversation-changed="emit('conversation-changed', $event)"
    />

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

    <el-empty v-else :description="emptyDescription" :image-size="64" />
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import CollaborativeWritingEditor from './CollaborativeWritingEditor.vue'
import PresentationWorkspace from './PresentationWorkspace.vue'
import WritingAiPane from './WritingAiPane.vue'
import type {
  WritingAiTarget,
  WritingDirectoryNode,
  WritingProjectDocument
} from '@/api/writing'

export type WritingPaneMode = 'document' | 'presentation' | 'ai'
export type WritingPaneContext = WritingAiTarget

const props = defineProps<{
  mode: WritingPaneMode
  projectId: string
  sourceDocument?: WritingProjectDocument
  presentationDocument?: WritingProjectDocument
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
  changed: [kind: 'document' | 'presentation']
  'select-outline': [node: WritingDirectoryNode]
  'navigate-to-thesis': [payload: { sourceDocumentId: string; section: string }]
  'slide-changed': [slide: number]
  'context-changed': [context: WritingPaneContext]
  'ai-lock-changed': [locked: boolean]
  'conversation-changed': [conversationId: string]
  'content-scroll': [ratio: number]
}>()

const documentEditor = ref<InstanceType<typeof CollaborativeWritingEditor>>()
const paneRoot = ref<HTMLElement>()
let applyingSyncedScroll = false
const emptyDescription = computed(() => {
  if (props.mode === 'document') return '当前项目没有可编辑的正文文档'
  if (props.mode === 'presentation') return '当前项目没有可用的 PPT'
  return '请先在另一窗口打开文档或 PPT，建立 AI 目标上下文'
})

async function flush(): Promise<boolean> {
  if (props.mode !== 'document') return true
  return (await documentEditor.value?.flushDraft?.()) !== false
}

function handleScroll(event: Event) {
  if (applyingSyncedScroll) return
  const target = event.target
  if (!(target instanceof HTMLElement) || !target.classList.contains('paper-scroll')) return
  const range = target.scrollHeight - target.clientHeight
  emit('content-scroll', range > 0 ? target.scrollTop / range : 0)
}

function setContentScrollRatio(ratio: number) {
  const scroller = paneRoot.value?.querySelector<HTMLElement>('.paper-scroll')
  if (!scroller) return
  const range = scroller.scrollHeight - scroller.clientHeight
  applyingSyncedScroll = true
  scroller.scrollTop = Math.max(0, Math.min(1, ratio)) * Math.max(0, range)
  requestAnimationFrame(() => { applyingSyncedScroll = false })
}

defineExpose({ flush, setContentScrollRatio })
</script>

<style scoped>
.workspace-pane-body { display: grid; grid-template-rows: minmax(0, 1fr); min-width: 0; min-height: 700px; overflow: hidden; background: var(--content-bg); }
.workspace-pane-body.is-read-only::before { content: '只读对照'; position: absolute; z-index: 6; right: 12px; top: 12px; padding: 3px 7px; border: 1px solid var(--line-color); border-radius: 4px; color: var(--text-secondary); font-size: 10px; background: var(--panel-bg); }
.workspace-pane-body.is-read-only { position: relative; }
.workspace-pane-body :deep(.co-writing), .workspace-pane-body :deep(.presentation-workspace), .workspace-pane-body :deep(.writing-ai-pane) { min-height: 100%; border: 0; border-radius: 0; }
.workspace-pane-body :deep(.paper-scroll) { padding-inline: 18px; }
.workspace-pane-body :deep(.paper-page) { min-width: 720px; }
.workspace-pane-body :deep(.slide-viewer iframe) { min-height: 620px; }
@media (max-width: 1180px) {
  .workspace-pane-body { min-height: calc(100vh - 285px); }
  .workspace-pane-body :deep(.paper-page) { min-width: 0; }
}
</style>
