<template>
  <section class="linked-workspace">
    <header class="linked-toolbar">
      <div class="workbench-title">
        <span class="eyebrow">HUMAN × AI WORKBENCH</span>
        <h3>协同工作台</h3>
        <p>左右窗口可以独立显示文档、PPT 或 AI，对同一资源执行单写多读。</p>
      </div>

      <div class="workbench-controls">
        <el-segmented
          :model-value="preset"
          :options="presetOptions"
          size="small"
          @change="applyPreset(String($event) as WorkbenchPreset)"
        />
        <div class="icon-actions">
          <el-tooltip content="交换左右窗口" placement="bottom">
            <el-button :icon="Refresh" circle @click="swapPanes" />
          </el-tooltip>
          <el-tooltip content="恢复默认布局" placement="bottom">
            <el-button :icon="FullScreen" circle @click="resetLayout" />
          </el-tooltip>
        </div>
        <span class="sync-state" :class="`is-${preferenceState}`">{{ preferenceStateLabel }}</span>
      </div>
    </header>

    <nav class="mobile-pane-switch" aria-label="协同窗口">
      <el-segmented v-model="mobilePane" :options="mobilePaneOptions" size="small" />
    </nav>

    <div
      ref="panesElement"
      class="linked-panes"
      :class="[`mobile-${mobilePane}`, maximizedPane ? `maximized-${maximizedPane}` : '']"
      :style="paneGridStyle"
    >
      <article
        v-show="maximizedPane !== 'right'"
        class="linked-pane pane-left"
        @pointerdown.capture="lastFocusedPane = 'left'"
      >
        <header class="pane-head">
          <div class="pane-identity">
            <small>左窗口</small>
            <strong>{{ paneTitle(leftPane) }}</strong>
          </div>
          <div class="pane-controls">
            <el-segmented
              :model-value="leftPane.module"
              :options="paneModeOptions"
              size="small"
              @change="changePaneModule('left', String($event) as WritingPaneMode)"
            />
            <el-tooltip :content="maximizedPane === 'left' ? '恢复双窗' : '最大化左窗口'">
              <el-button :icon="FullScreen" circle size="small" @click="toggleMaximize('left')" />
            </el-tooltip>
          </div>
        </header>
        <div class="pane-resource-bar">
          <el-select
            v-if="leftPane.module === 'document'"
            :model-value="leftPane.resource_id"
            size="small"
            placeholder="选择文档"
            @change="changeResource('left', String($event || ''))"
          >
            <el-option v-for="document in sourceOptions" :key="document.id" :label="document.title" :value="document.id" />
          </el-select>
          <el-select
            v-else-if="leftPane.module === 'presentation'"
            :model-value="leftPane.resource_id"
            size="small"
            placeholder="选择 PPT"
            @change="changeResource('left', String($event || ''))"
          >
            <el-option v-for="document in presentationOptions" :key="document.id" :label="document.title" :value="document.id" />
          </el-select>
          <el-select
            v-if="leftPane.module === 'document'"
            v-model="leftPane.section_id"
            size="small"
            placeholder="当前章节"
            @change="markCustomAndPersist"
          >
            <el-option v-for="section in sectionOptions" :key="section.id" :label="section.title" :value="section.id" />
          </el-select>
          <el-input-number
            v-else-if="leftPane.module === 'presentation'"
            v-model="leftPane.slide"
            :min="1"
            :max="leftPresentation?.stats?.slide_count || 999"
            size="small"
            controls-position="right"
            @change="markCustomAndPersist"
          />
          <span class="pane-status" :class="{ readonly: leftReadOnly }">{{ paneStatusLabel('left') }}</span>
          <el-button :icon="Refresh" circle size="small" @click="refreshPane('left')" />
        </div>
        <WritingWorkspacePane
          ref="leftPaneComponent"
          :mode="leftPane.module"
          :project-id="projectId"
          :source-document="leftSource"
          :presentation-document="leftPresentation"
          :section-id="leftPane.section_id || sectionId"
          :outline="outline"
          :selected-node-id="leftPane.section_id || selectedNodeId"
          :presentation-slide="leftPane.slide || 1"
          :refresh-token="leftRefreshToken"
          :read-only="leftReadOnly"
          :ai-target="aiTargetFor('left')"
          :ai-target-locked="Boolean(leftPane.ai_target_locked)"
          :ai-conversation-id="leftPane.ai_conversation_id"
          @changed="handleChanged"
          @context-changed="leftContext = $event"
          @ai-lock-changed="setAiLock('left', $event)"
          @conversation-changed="setConversation('left', $event)"
          @select-outline="handleOutlineSelection('left', $event)"
          @navigate-to-thesis="emit('navigate-to-thesis', $event)"
          @slide-changed="handleSlideChanged('left', $event)"
        />
      </article>

      <button
        v-if="!maximizedPane"
        class="pane-divider"
        type="button"
        aria-label="拖动调整左右窗口宽度"
        @pointerdown.prevent="startResize"
      ><span /></button>

      <article
        v-show="maximizedPane !== 'left'"
        class="linked-pane pane-right"
        @pointerdown.capture="lastFocusedPane = 'right'"
      >
        <header class="pane-head">
          <div class="pane-identity">
            <small>右窗口</small>
            <strong>{{ paneTitle(rightPane) }}</strong>
          </div>
          <div class="pane-controls">
            <el-segmented
              :model-value="rightPane.module"
              :options="paneModeOptions"
              size="small"
              @change="changePaneModule('right', String($event) as WritingPaneMode)"
            />
            <el-tooltip :content="maximizedPane === 'right' ? '恢复双窗' : '最大化右窗口'">
              <el-button :icon="FullScreen" circle size="small" @click="toggleMaximize('right')" />
            </el-tooltip>
          </div>
        </header>
        <div class="pane-resource-bar">
          <el-select
            v-if="rightPane.module === 'document'"
            :model-value="rightPane.resource_id"
            size="small"
            placeholder="选择文档"
            @change="changeResource('right', String($event || ''))"
          >
            <el-option v-for="document in sourceOptions" :key="document.id" :label="document.title" :value="document.id" />
          </el-select>
          <el-select
            v-else-if="rightPane.module === 'presentation'"
            :model-value="rightPane.resource_id"
            size="small"
            placeholder="选择 PPT"
            @change="changeResource('right', String($event || ''))"
          >
            <el-option v-for="document in presentationOptions" :key="document.id" :label="document.title" :value="document.id" />
          </el-select>
          <el-select
            v-if="rightPane.module === 'document'"
            v-model="rightPane.section_id"
            size="small"
            placeholder="当前章节"
            @change="markCustomAndPersist"
          >
            <el-option v-for="section in sectionOptions" :key="section.id" :label="section.title" :value="section.id" />
          </el-select>
          <el-input-number
            v-else-if="rightPane.module === 'presentation'"
            v-model="rightPane.slide"
            :min="1"
            :max="rightPresentation?.stats?.slide_count || 999"
            size="small"
            controls-position="right"
            @change="markCustomAndPersist"
          />
          <span class="pane-status" :class="{ readonly: rightReadOnly }">{{ paneStatusLabel('right') }}</span>
          <el-button :icon="Refresh" circle size="small" @click="refreshPane('right')" />
        </div>
        <WritingWorkspacePane
          ref="rightPaneComponent"
          :mode="rightPane.module"
          :project-id="projectId"
          :source-document="rightSource"
          :presentation-document="rightPresentation"
          :section-id="rightPane.section_id || sectionId"
          :outline="outline"
          :selected-node-id="rightPane.section_id || selectedNodeId"
          :presentation-slide="rightPane.slide || 1"
          :refresh-token="rightRefreshToken"
          :read-only="rightReadOnly"
          :ai-target="aiTargetFor('right')"
          :ai-target-locked="Boolean(rightPane.ai_target_locked)"
          :ai-conversation-id="rightPane.ai_conversation_id"
          @changed="handleChanged"
          @context-changed="rightContext = $event"
          @ai-lock-changed="setAiLock('right', $event)"
          @conversation-changed="setConversation('right', $event)"
          @select-outline="handleOutlineSelection('right', $event)"
          @navigate-to-thesis="emit('navigate-to-thesis', $event)"
          @slide-changed="handleSlideChanged('right', $event)"
        />
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { FullScreen, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import WritingWorkspacePane, {
  type WritingPaneContext,
  type WritingPaneMode
} from './WritingWorkspacePane.vue'
import {
  getWritingWorkbenchPreference,
  updateWritingWorkbenchPreference,
  type WritingWorkbenchPaneState,
  type WritingAiTarget,
  type WritingDirectoryNode,
  type WritingProjectDocument
} from '@/api/writing'

type PaneSide = 'left' | 'right'
type WorkbenchPreset = 'writing' | 'presentation' | 'comparison' | 'custom'

const props = defineProps<{
  projectId: string
  sourceDocument?: WritingProjectDocument
  presentationDocument?: WritingProjectDocument
  sourceDocuments?: WritingProjectDocument[]
  presentationDocuments?: WritingProjectDocument[]
  sectionId: string
  outline: WritingDirectoryNode[]
  selectedNodeId?: string
  presentationSlide?: number
  initialPreset?: WorkbenchPreset
}>()

const emit = defineEmits<{
  changed: [kind: 'document' | 'presentation']
  'select-outline': [node: WritingDirectoryNode]
  'navigate-to-thesis': [payload: { sourceDocumentId: string; section: string }]
  'slide-changed': [slide: number]
}>()

const sourceOptions = computed(() => props.sourceDocuments?.length ? props.sourceDocuments : props.sourceDocument ? [props.sourceDocument] : [])
const presentationOptions = computed(() => props.presentationDocuments?.length ? props.presentationDocuments : props.presentationDocument ? [props.presentationDocument] : [])
const preset = ref<WorkbenchPreset>(props.initialPreset || 'writing')
const splitPercent = ref(42)
const maximizedPane = ref<PaneSide>()
const mobilePane = ref<PaneSide>('left')
const lastFocusedPane = ref<PaneSide>('right')
const preferenceRevision = ref(0)
const preferenceState = ref<'saved' | 'saving' | 'error'>('saved')
const panesElement = ref<HTMLElement>()
const leftPaneComponent = ref<InstanceType<typeof WritingWorkspacePane>>()
const rightPaneComponent = ref<InstanceType<typeof WritingWorkspacePane>>()
const leftRefreshToken = ref(0)
const rightRefreshToken = ref(0)
const leftContext = ref<WritingPaneContext>()
const rightContext = ref<WritingPaneContext>()
const lockedTargets = ref<Partial<Record<PaneSide, WritingAiTarget>>>({})
let persistTimer: ReturnType<typeof setTimeout> | undefined

function defaultPane(module: WritingPaneMode, _side: PaneSide): WritingWorkbenchPaneState {
  return {
    module,
    resource_id: module === 'document'
      ? (props.sourceDocument?.id || sourceOptions.value[0]?.id)
      : module === 'presentation'
        ? (props.presentationDocument?.id || presentationOptions.value[0]?.id)
        : undefined,
    section_id: props.sectionId || undefined,
    slide: Math.max(1, Number(props.presentationSlide || 1)),
    ai_target_locked: false,
    ai_conversation_id: undefined
  }
}

const leftPane = ref<WritingWorkbenchPaneState>(defaultPane('ai', 'left'))
const rightPane = ref<WritingWorkbenchPaneState>(defaultPane('document', 'right'))

const presetOptions = [
  { label: '文档写作', value: 'writing' },
  { label: 'PPT 制作', value: 'presentation' },
  { label: '文档校验', value: 'comparison' },
  { label: '自定义', value: 'custom' }
]
const paneModeOptions = [
  { label: '文档', value: 'document' },
  { label: 'PPT', value: 'presentation' },
  { label: 'AI', value: 'ai' }
]
const mobilePaneOptions = [
  { label: '左窗口', value: 'left' },
  { label: '右窗口', value: 'right' }
]

const sectionOptions = computed(() => {
  const rows: Array<{ id: string; title: string }> = []
  const visit = (nodes: WritingDirectoryNode[]) => nodes.forEach(node => {
    if (node.section_id || node.target_id) rows.push({ id: node.section_id || node.target_id, title: node.title })
    if (node.children?.length) visit(node.children)
  })
  visit(props.outline || [])
  return rows
})
const leftSource = computed(() => sourceOptions.value.find(row => row.id === leftPane.value.resource_id) || props.sourceDocument || sourceOptions.value[0])
const rightSource = computed(() => sourceOptions.value.find(row => row.id === rightPane.value.resource_id) || props.sourceDocument || sourceOptions.value[0])
const leftPresentation = computed(() => presentationOptions.value.find(row => row.id === leftPane.value.resource_id) || props.presentationDocument || presentationOptions.value[0])
const rightPresentation = computed(() => presentationOptions.value.find(row => row.id === rightPane.value.resource_id) || props.presentationDocument || presentationOptions.value[0])
const sameWritableResource = computed(() => (
  leftPane.value.module === rightPane.value.module
  && leftPane.value.module !== 'ai'
  && Boolean(leftPane.value.resource_id)
  && leftPane.value.resource_id === rightPane.value.resource_id
))
const leftReadOnly = computed(() => false)
const rightReadOnly = computed(() => sameWritableResource.value)
const paneGridStyle = computed(() => maximizedPane.value
  ? { gridTemplateColumns: 'minmax(0, 1fr)' }
  : { gridTemplateColumns: `minmax(0, ${splitPercent.value}fr) 8px minmax(0, ${100 - splitPercent.value}fr)` })
const preferenceStateLabel = computed(() => ({ saved: '布局已保存', saving: '保存布局…', error: '布局保存失败' })[preferenceState.value])

function pane(side: PaneSide) {
  return side === 'left' ? leftPane : rightPane
}

function paneComponent(side: PaneSide) {
  return side === 'left' ? leftPaneComponent.value : rightPaneComponent.value
}

function paneTitle(state: WritingWorkbenchPaneState) {
  if (state.module === 'document') return sourceOptions.value.find(row => row.id === state.resource_id)?.title || '文档'
  if (state.module === 'presentation') return presentationOptions.value.find(row => row.id === state.resource_id)?.title || 'PPT'
  return state.ai_target_locked ? 'AI 协作 · 已锁定目标' : 'AI 协作 · 跟随焦点'
}

function paneStatusLabel(side: PaneSide) {
  const state = pane(side).value
  if (state.module === 'ai') return state.ai_target_locked ? '目标已锁定' : '跟随另一窗口'
  if ((side === 'left' ? leftReadOnly : rightReadOnly).value) return '只读对照'
  return '可编辑'
}

async function flushPane(side: PaneSide) {
  try {
    return (await paneComponent(side)?.flush?.()) !== false
  } catch {
    return false
  }
}

async function changePaneModule(side: PaneSide, module: WritingPaneMode) {
  const target = pane(side)
  if (target.value.module === module) return
  if (!(await flushPane(side))) {
    ElMessage.error('当前草稿保存失败，已保留窗口现场')
    return
  }
  target.value = defaultPane(module, side)
  preset.value = 'custom'
  schedulePersist()
}

async function changeResource(side: PaneSide, resourceId: string) {
  const target = pane(side)
  if (target.value.resource_id === resourceId) return
  if (!(await flushPane(side))) {
    ElMessage.error('当前草稿保存失败，不能切换资源')
    return
  }
  target.value.resource_id = resourceId
  preset.value = 'custom'
  schedulePersist()
}

async function applyPreset(nextPreset: WorkbenchPreset) {
  if (nextPreset === 'custom') {
    preset.value = 'custom'
    schedulePersist()
    return
  }
  const results = await Promise.all([flushPane('left'), flushPane('right')])
  if (results.some(result => !result)) {
    ElMessage.error('草稿尚未保存，不能切换工作台预设')
    return
  }
  preset.value = nextPreset
  maximizedPane.value = undefined
  if (nextPreset === 'writing') {
    leftPane.value = defaultPane('ai', 'left')
    rightPane.value = defaultPane('document', 'right')
    splitPercent.value = 42
  } else if (nextPreset === 'presentation') {
    leftPane.value = defaultPane('ai', 'left')
    rightPane.value = defaultPane('presentation', 'right')
    splitPercent.value = 38
  } else {
    leftPane.value = defaultPane('document', 'left')
    rightPane.value = defaultPane('presentation', 'right')
    splitPercent.value = 50
  }
  schedulePersist()
}

async function swapPanes() {
  const results = await Promise.all([flushPane('left'), flushPane('right')])
  if (results.some(result => !result)) {
    ElMessage.error('草稿尚未保存，不能交换窗口')
    return
  }
  const previousLeft = leftPane.value
  leftPane.value = rightPane.value
  rightPane.value = previousLeft
  const previousContext = leftContext.value
  leftContext.value = rightContext.value
  rightContext.value = previousContext
  preset.value = 'custom'
  schedulePersist()
}

function toggleMaximize(side: PaneSide) {
  maximizedPane.value = maximizedPane.value === side ? undefined : side
  schedulePersist()
}

function resetLayout() {
  void applyPreset(props.initialPreset || 'writing')
}

function startResize() {
  const bounds = panesElement.value?.getBoundingClientRect()
  if (!bounds) return
  const move = (moveEvent: PointerEvent) => {
    splitPercent.value = Math.max(28, Math.min(72, Math.round(((moveEvent.clientX - bounds.left) / bounds.width) * 100)))
    preset.value = 'custom'
  }
  const stop = () => {
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', stop)
    schedulePersist()
  }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', stop)
}

function aiTargetFor(side: PaneSide): WritingAiTarget | undefined {
  if (pane(side).value.ai_target_locked && lockedTargets.value[side]) return lockedTargets.value[side]
  const opposite = side === 'left' ? rightContext.value : leftContext.value
  if (opposite) return opposite
  const source = props.sourceDocument || sourceOptions.value[0]
  if (source) return {
    kind: 'document',
    document_id: source.id,
    document_title: source.title,
    section_id: props.sectionId,
    revision: source.revision,
    selection: { from: 0, to: 0, text: '' }
  }
  return undefined
}

function setAiLock(side: PaneSide, locked: boolean) {
  if (locked) lockedTargets.value[side] = aiTargetFor(side)
  else delete lockedTargets.value[side]
  pane(side).value.ai_target_locked = locked
  schedulePersist()
}

function setConversation(side: PaneSide, conversationId: string) {
  pane(side).value.ai_conversation_id = conversationId
  schedulePersist()
}

function handleOutlineSelection(side: PaneSide, node: WritingDirectoryNode) {
  pane(side).value.section_id = node.section_id || node.target_id || node.id
  emit('select-outline', node)
  schedulePersist()
}

function handleSlideChanged(side: PaneSide, slide: number) {
  pane(side).value.slide = slide
  emit('slide-changed', slide)
  schedulePersist()
}

function handleChanged(kind: 'document' | 'presentation') {
  emit('changed', kind)
}

function refreshPane(side: PaneSide) {
  if (side === 'left') leftRefreshToken.value += 1
  else rightRefreshToken.value += 1
}

function markCustomAndPersist() {
  preset.value = 'custom'
  schedulePersist()
}

function preferencePayload() {
  return {
    expected_revision: preferenceRevision.value,
    schema_version: 1,
    preset: preset.value,
    split_percent: splitPercent.value,
    maximized_pane: maximizedPane.value,
    panes: {
      left: { ...leftPane.value },
      right: { ...rightPane.value }
    }
  }
}

function applyStoredPreference(value: any) {
  preferenceRevision.value = Number(value.revision || 0)
  preset.value = value.preset || props.initialPreset || 'writing'
  splitPercent.value = Math.max(28, Math.min(72, Number(value.split_percent || 42)))
  maximizedPane.value = value.maximized_pane || undefined
  leftPane.value = { ...defaultPane('ai', 'left'), ...(value.panes?.left || {}) }
  rightPane.value = { ...defaultPane('document', 'right'), ...(value.panes?.right || {}) }
}

async function loadPreference() {
  try {
    const value = await getWritingWorkbenchPreference(props.projectId)
    if (Number(value.revision || 0) > 0) applyStoredPreference(value)
    else await applyPreset(props.initialPreset || 'writing')
  } catch {
    preferenceState.value = 'error'
    await applyPreset(props.initialPreset || 'writing')
  }
}

function schedulePersist() {
  if (persistTimer) clearTimeout(persistTimer)
  preferenceState.value = 'saving'
  persistTimer = setTimeout(() => void persistPreference(), 500)
}

async function persistPreference() {
  try {
    const saved = await updateWritingWorkbenchPreference(props.projectId, preferencePayload())
    applyStoredPreference(saved)
    preferenceState.value = 'saved'
  } catch (error: any) {
    preferenceState.value = 'error'
    if (error?.response?.status === 409) {
      const current = await getWritingWorkbenchPreference(props.projectId)
      applyStoredPreference(current)
      ElMessage.warning('布局已由另一设备更新，已载入最新版本')
    }
  }
}

onMounted(loadPreference)
onBeforeUnmount(() => {
  if (persistTimer) clearTimeout(persistTimer)
})
</script>

<style scoped>
.linked-workspace { display: grid; gap: 10px; min-width: 0; }
.linked-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 18px; padding: 11px 13px; border: 1px solid var(--line-color); border-radius: 6px; background: var(--card-bg); box-shadow: 0 8px 24px rgb(0 0 0 / 12%); }
.workbench-title { min-width: 220px; }
.linked-toolbar h3 { margin: 3px 0 0; color: var(--text-primary); font-size: 15px; }
.linked-toolbar p { margin: 4px 0 0; color: var(--text-secondary); font-size: 10px; }
.eyebrow { color: var(--view-color-primary); font-size: 9px; }
.workbench-controls, .icon-actions, .pane-controls, .pane-resource-bar { display: flex; align-items: center; gap: 7px; }
.workbench-controls { justify-content: flex-end; min-width: 0; }
.sync-state { min-width: 62px; color: var(--text-secondary); font-size: 9px; text-align: right; }
.sync-state.is-error { color: var(--el-color-danger); }
.mobile-pane-switch { display: none; }
.linked-panes { display: grid; min-width: 0; align-items: stretch; }
.linked-pane { display: grid; grid-template-rows: auto auto minmax(0, 1fr); min-width: 0; overflow: hidden; border: 1px solid var(--line-color); border-radius: 7px; background: var(--card-bg); box-shadow: 0 12px 30px rgb(0 0 0 / 18%); }
.pane-divider { display: flex; align-items: center; justify-content: center; width: 8px; padding: 0; border: 0; background: transparent; cursor: col-resize; touch-action: none; }
.pane-divider span { width: 2px; height: 54px; border-radius: 2px; background: var(--line-color); transition: background .15s, width .15s; }
.pane-divider:hover span, .pane-divider:focus-visible span { width: 4px; background: var(--view-color-primary); }
.pane-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; min-width: 0; padding: 8px 10px; border-bottom: 1px solid var(--line-color); background: var(--panel-bg); }
.pane-identity { display: grid; gap: 2px; min-width: 0; }
.pane-identity small { color: var(--text-secondary); font-size: 9px; }
.pane-identity strong { overflow: hidden; color: var(--text-primary); font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.pane-controls :deep(.el-segmented__item) { min-width: 48px; }
.pane-resource-bar { min-width: 0; padding: 7px 10px; border-bottom: 1px solid var(--line-color); background: var(--content-bg); }
.pane-resource-bar .el-select:first-child { flex: 1; min-width: 120px; }
.pane-resource-bar .el-select:nth-child(2) { width: min(210px, 36%); }
.pane-resource-bar .el-input-number { width: 92px; }
.pane-status { margin-left: auto; padding: 2px 6px; border: 1px solid color-mix(in srgb, var(--el-color-success) 45%, var(--line-color)); border-radius: 4px; color: var(--el-color-success); font-size: 9px; white-space: nowrap; }
.pane-status.readonly { border-color: var(--line-color); color: var(--text-secondary); }
@media (max-width: 1180px) {
  .linked-toolbar { align-items: flex-start; flex-direction: column; }
  .workbench-controls { width: 100%; justify-content: space-between; }
  .mobile-pane-switch { display: flex; justify-content: center; padding: 7px; border: 1px solid var(--line-color); border-radius: 6px; background: var(--panel-bg); }
  .linked-panes { display: block; }
  .linked-pane { display: none !important; }
  .linked-panes.mobile-left .pane-left, .linked-panes.mobile-right .pane-right { display: grid !important; }
  .pane-divider { display: none; }
}
@media (max-width: 720px) {
  .workbench-controls { align-items: stretch; flex-wrap: wrap; }
  .workbench-controls :deep(.el-segmented), .workbench-controls :deep(.el-segmented__group) { width: 100%; }
  .workbench-controls :deep(.el-segmented__item) { flex: 1; min-width: 0; }
  .pane-head { align-items: stretch; flex-direction: column; }
  .pane-controls { justify-content: space-between; }
  .pane-controls :deep(.el-segmented), .pane-controls :deep(.el-segmented__group) { flex: 1; }
  .pane-controls :deep(.el-segmented__item) { flex: 1; min-width: 0; }
  .pane-resource-bar { flex-wrap: wrap; }
  .pane-resource-bar .el-select, .pane-resource-bar .el-select:nth-child(2) { width: calc(50% - 4px); flex: auto; }
}
</style>
