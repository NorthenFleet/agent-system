<template>
  <section class="linked-workspace">
    <header class="linked-toolbar">
      <div>
        <span class="eyebrow">文档 × PPT × AI</span>
        <h3>联动工作台</h3>
        <p>两个窗口独立选择工作模块，所有修改仍写回各自的结构化权威。</p>
      </div>
      <div class="layout-controls">
        <label>
          <span>左侧宽度</span>
          <el-slider v-model="splitPercent" :min="35" :max="65" :show-tooltip="false" />
        </label>
        <el-tooltip content="交换左右窗口" placement="bottom">
          <el-button :icon="Refresh" circle @click="swapPanes" />
        </el-tooltip>
      </div>
    </header>

    <nav class="mobile-pane-switch" aria-label="联动窗口">
      <el-segmented v-model="mobilePane" :options="mobilePaneOptions" size="small" />
    </nav>

    <div
      class="linked-panes"
      :class="`mobile-${mobilePane}`"
      :style="{ gridTemplateColumns: `${splitPercent}fr ${100 - splitPercent}fr` }"
    >
      <article class="linked-pane pane-left">
        <header class="pane-head">
          <div><small>左侧窗口</small><strong>{{ paneTitle(leftMode) }}</strong></div>
          <el-segmented v-model="leftMode" :options="paneModeOptions" size="small" />
        </header>
        <WritingWorkspacePane
          :mode="leftMode"
          :project-id="projectId"
          :source-document="sourceDocument"
          :presentation-document="presentationDocument"
          :section-id="sectionId"
          :outline="outline"
          :selected-node-id="selectedNodeId"
          :presentation-slide="activePresentationSlide"
          :refresh-token="refreshToken(leftMode)"
          @changed="handleChanged"
          @select-outline="emit('select-outline', $event)"
          @navigate-to-thesis="emit('navigate-to-thesis', $event)"
          @slide-changed="handleSlideChanged"
        />
      </article>

      <article class="linked-pane pane-right">
        <header class="pane-head">
          <div><small>右侧窗口</small><strong>{{ paneTitle(rightMode) }}</strong></div>
          <el-segmented v-model="rightMode" :options="paneModeOptions" size="small" />
        </header>
        <WritingWorkspacePane
          :mode="rightMode"
          :project-id="projectId"
          :source-document="sourceDocument"
          :presentation-document="presentationDocument"
          :section-id="sectionId"
          :outline="outline"
          :selected-node-id="selectedNodeId"
          :presentation-slide="activePresentationSlide"
          :refresh-token="refreshToken(rightMode)"
          @changed="handleChanged"
          @select-outline="emit('select-outline', $event)"
          @navigate-to-thesis="emit('navigate-to-thesis', $event)"
          @slide-changed="handleSlideChanged"
        />
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import WritingWorkspacePane, { type WritingPaneMode } from './WritingWorkspacePane.vue'
import type { WritingDirectoryNode, WritingProjectDocument } from '@/api/writing'

const props = defineProps<{
  projectId: string
  sourceDocument?: WritingProjectDocument
  presentationDocument?: WritingProjectDocument
  sectionId: string
  outline: WritingDirectoryNode[]
  selectedNodeId?: string
  presentationSlide?: number
}>()

const emit = defineEmits<{
  changed: [kind: 'document' | 'presentation']
  'select-outline': [node: WritingDirectoryNode]
  'navigate-to-thesis': [payload: { sourceDocumentId: string; section: string }]
  'slide-changed': [slide: number]
}>()

const leftMode = ref<WritingPaneMode>('document')
const rightMode = ref<WritingPaneMode>('presentation')
const mobilePane = ref<'left' | 'right'>('left')
const splitPercent = ref(50)
const activePresentationSlide = ref(Math.max(1, Number(props.presentationSlide || 1)))
const documentRefreshToken = ref(0)
const presentationRefreshToken = ref(0)
const paneModeOptions = [
  { label: '文档', value: 'document' },
  { label: 'PPT', value: 'presentation' },
  { label: 'AI', value: 'ai' }
]
const mobilePaneOptions = [
  { label: '左侧窗口', value: 'left' },
  { label: '右侧窗口', value: 'right' }
]

function paneTitle(mode: WritingPaneMode) {
  if (mode === 'document') return props.sourceDocument?.title || '文档撰写'
  if (mode === 'presentation') return props.presentationDocument?.title || 'PPT 制作'
  return 'AI 协作'
}

function refreshToken(mode: WritingPaneMode) {
  if (mode === 'document') return documentRefreshToken.value
  if (mode === 'presentation') return presentationRefreshToken.value
  return documentRefreshToken.value + presentationRefreshToken.value
}

function handleChanged(kind: 'document' | 'presentation') {
  if (kind === 'document') documentRefreshToken.value += 1
  else presentationRefreshToken.value += 1
  emit('changed', kind)
}

function handleSlideChanged(slide: number) {
  activePresentationSlide.value = slide
  emit('slide-changed', slide)
}

function swapPanes() {
  const previousLeft = leftMode.value
  leftMode.value = rightMode.value
  rightMode.value = previousLeft
}
</script>

<style scoped>
.linked-workspace { display: grid; gap: 10px; min-width: 0; }
.linked-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 18px; padding: 12px 14px; border: 1px solid var(--line-color); border-radius: 6px; background: var(--card-bg); }
.linked-toolbar h3 { margin: 3px 0 0; color: var(--text-primary); font-size: 15px; }
.linked-toolbar p { margin: 5px 0 0; color: var(--text-secondary); font-size: 10px; }
.eyebrow { color: var(--view-color-primary); font-size: 10px; }
.layout-controls { display: flex; align-items: center; gap: 10px; }
.layout-controls label { display: grid; grid-template-columns: auto 120px; align-items: center; gap: 10px; color: var(--text-secondary); font-size: 10px; }
.linked-panes { display: grid; gap: 10px; min-width: 0; align-items: stretch; }
.linked-pane { display: grid; grid-template-rows: auto minmax(0, 1fr); min-width: 0; overflow: hidden; border: 1px solid var(--line-color); border-radius: 7px; background: var(--card-bg); box-shadow: 0 8px 24px rgb(0 0 0 / 16%); }
.pane-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; min-width: 0; padding: 9px 11px; border-bottom: 1px solid var(--line-color); background: var(--panel-bg); }
.pane-head > div { display: grid; gap: 2px; min-width: 0; }
.pane-head small { color: var(--text-secondary); font-size: 9px; }
.pane-head strong { overflow: hidden; color: var(--text-primary); font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.pane-head :deep(.el-segmented__item) { min-width: 52px; }
.mobile-pane-switch { display: none; }
@media (max-width: 1180px) {
  .linked-toolbar { align-items: flex-start; flex-direction: column; }
  .layout-controls { width: 100%; justify-content: flex-end; }
  .mobile-pane-switch { display: flex; justify-content: center; padding: 8px; border: 1px solid var(--line-color); background: var(--panel-bg); }
  .linked-panes { display: block; }
  .linked-pane { display: none; }
  .linked-panes.mobile-left .pane-left, .linked-panes.mobile-right .pane-right { display: grid; }
}
@media (max-width: 640px) {
  .layout-controls label { display: none; }
  .pane-head { align-items: stretch; flex-direction: column; }
  .pane-head :deep(.el-segmented), .pane-head :deep(.el-segmented__group) { width: 100%; }
  .pane-head :deep(.el-segmented__item) { flex: 1; }
}
</style>
