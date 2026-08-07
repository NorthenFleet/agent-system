<template>
  <section class="workspace-pane-body">
    <div v-if="mode === 'ai' && aiTargetOptions.length > 1" class="ai-target-switch">
      <span>AI 当前作用于</span>
      <el-segmented v-model="aiTarget" :options="aiTargetOptions" size="small" />
    </div>

    <CollaborativeWritingEditor
      v-if="effectiveMode === 'document' && sourceDocument && sectionId"
      :key="`document-${sourceDocument.id}-${sectionId}-${refreshToken}`"
      :project-id="projectId"
      :document-id="sourceDocument.id"
      :document-title="sourceDocument.title"
      :section-id="sectionId"
      :outline="outline"
      :selected-node-id="selectedNodeId"
      :display-mode="mode === 'ai' ? 'ai' : 'document'"
      @select-outline="emit('select-outline', $event)"
      @proposal-applied="emit('changed', 'document')"
    />

    <PresentationWorkspace
      v-else-if="effectiveMode === 'presentation' && presentationDocument"
      :key="`presentation-${presentationDocument.id}-${presentationSlide}-${refreshToken}`"
      :project-id="projectId"
      :document="presentationDocument"
      :initial-slide="presentationSlide"
      :display-mode="mode === 'ai' ? 'ai' : 'slides'"
      @changed="emit('changed', 'presentation')"
      @navigate-to-thesis="emit('navigate-to-thesis', $event)"
      @slide-changed="emit('slide-changed', $event)"
    />

    <el-empty
      v-else
      :description="emptyDescription"
      :image-size="64"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import CollaborativeWritingEditor from './CollaborativeWritingEditor.vue'
import PresentationWorkspace from './PresentationWorkspace.vue'
import type { WritingDirectoryNode, WritingProjectDocument } from '@/api/writing'

export type WritingPaneMode = 'document' | 'presentation' | 'ai'
type AiTarget = 'document' | 'presentation'

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
}>()

const emit = defineEmits<{
  changed: [kind: AiTarget]
  'select-outline': [node: WritingDirectoryNode]
  'navigate-to-thesis': [payload: { sourceDocumentId: string; section: string }]
  'slide-changed': [slide: number]
}>()

const aiTarget = ref<AiTarget>('document')
const aiTargetOptions = computed(() => [
  ...(props.sourceDocument ? [{ label: '当前文档', value: 'document' as const }] : []),
  ...(props.presentationDocument ? [{ label: '当前 PPT', value: 'presentation' as const }] : [])
])
const effectiveMode = computed<AiTarget>(() => (
  props.mode === 'ai' ? aiTarget.value : props.mode
))
const emptyDescription = computed(() => {
  if (props.mode === 'document') return '当前项目没有可编辑的正文文档'
  if (props.mode === 'presentation') return '当前项目没有可用的 PPT'
  return '当前项目没有可供 AI 协作的文档或 PPT'
})

watch(aiTargetOptions, options => {
  if (!options.some(option => option.value === aiTarget.value)) {
    aiTarget.value = options[0]?.value || 'document'
  }
}, { immediate: true })
</script>

<style scoped>
.workspace-pane-body { display: grid; grid-template-rows: auto minmax(0, 1fr); min-width: 0; min-height: 680px; overflow: hidden; background: var(--content-bg); }
.ai-target-switch { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 9px 12px; border-bottom: 1px solid var(--line-color); background: var(--panel-bg); }
.ai-target-switch > span { color: var(--text-secondary); font-size: 10px; }
.workspace-pane-body :deep(.co-writing), .workspace-pane-body :deep(.presentation-workspace) { min-height: 100%; border: 0; border-radius: 0; }
.workspace-pane-body :deep(.paper-scroll) { padding-inline: 18px; }
.workspace-pane-body :deep(.paper-page) { min-width: 720px; }
.workspace-pane-body :deep(.slide-viewer iframe) { min-height: 600px; }
@media (max-width: 1180px) {
  .workspace-pane-body { min-height: calc(100vh - 290px); }
  .workspace-pane-body :deep(.paper-page) { min-width: 0; }
}
</style>
