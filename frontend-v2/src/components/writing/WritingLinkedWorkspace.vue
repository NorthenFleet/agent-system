<template>
  <section class="linked-workspace">
    <header class="linked-toolbar">
      <div class="workbench-title">
        <span class="eyebrow">HUMAN × AI WORKBENCH</span>
        <h3>协同工作台</h3>
        <p>左右窗口可以独立显示文档、PPT、画图或 AI，对同一资源执行单写多读。</p>
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

    <section v-if="comparison" class="comparison-strip">
      <div class="comparison-summary">
        <strong>版本差异</strong>
        <span class="diff-added">新增 {{ comparison.summary.added }}</span>
        <span class="diff-deleted">删除 {{ comparison.summary.deleted }}</span>
        <span class="diff-modified">修改 {{ comparison.summary.modified }}</span>
        <span>未变化 {{ comparison.summary.unchanged }}</span>
        <el-tooltip content="仅联动章节与差异定位，左右正文始终独立滚动" placement="bottom">
          <el-switch v-model="syncComparisonSections" inline-prompt active-text="章节" inactive-text="独立" />
        </el-tooltip>
      </div>
      <div v-if="activeDifference" class="difference-row" :class="`is-${activeDifference.change.operation}`">
        <div><small>{{ activeDifference.section.left_title || '无对应章节' }}</small><p>{{ activeDifference.change.left_text || '本版本无此段落' }}</p></div>
        <div><small>{{ activeDifference.section.right_title || '无对应章节' }}</small><p>{{ activeDifference.change.right_text || '本版本无此段落' }}</p></div>
        <div class="difference-actions">
          <el-button size="small" :disabled="differenceIndex <= 0" @click="differenceIndex--">上一个</el-button>
          <span>{{ differenceIndex + 1 }} / {{ differences.length }}</span>
          <el-button size="small" :disabled="differenceIndex >= differences.length - 1" @click="differenceIndex++">下一个</el-button>
        </div>
      </div>
      <el-alert v-else title="两个版本当前没有可显示的段落差异" type="success" :closable="false" show-icon />
    </section>

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
            <el-option v-for="document in sourceOptions" :key="document.id" :label="documentOptionLabel(document)" :value="document.id" />
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
            v-else-if="leftPane.module === 'diagram'"
            :model-value="leftPane.resource_id"
            size="small"
            placeholder="选择图表"
            @change="changeResource('left', String($event || ''))"
          >
            <el-option v-for="document in diagramOptions" :key="document.id" :label="document.title" :value="document.id" />
          </el-select>
          <el-button v-if="leftPane.module === 'diagram'" type="primary" plain size="small" @click="openDiagramCreator('left')">新建</el-button>
          <el-select
            v-if="leftPane.module === 'document'"
            v-model="leftPane.section_id"
            size="small"
            placeholder="当前章节"
            @change="markCustomAndPersist"
          >
            <el-option v-for="section in sectionOptionsFor('left')" :key="section.id" :label="section.title" :value="section.id" />
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
          v-if="leftPane.module !== 'document' || paneReady.left"
          ref="leftPaneComponent"
          :mode="leftPane.module"
          :project-id="projectId"
          :source-document="leftSource"
          :presentation-document="leftPresentation"
          :diagram-id="leftPane.module === 'diagram' ? leftPane.resource_id : undefined"
          :document-target-id="oppositeDocumentId('left')"
          :document-target-section-id="oppositeDocumentSectionId('left')"
          :presentation-target-id="oppositePresentationId('left')"
          :presentation-target-slide="oppositePresentationSlide('left')"
          :section-id="leftPane.section_id || ''"
          :outline="outlineFor('left')"
          :selected-node-id="leftPane.section_id || ''"
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
          @document-changed="handleAiDocumentChanged"
          @select-outline="handleOutlineSelection('left', $event)"
          @navigate-to-thesis="emit('navigate-to-thesis', $event)"
          @slide-changed="handleSlideChanged('left', $event)"
        />
        <el-skeleton v-else class="pane-loading" animated :rows="8" />
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
            <el-option v-for="document in sourceOptions" :key="document.id" :label="documentOptionLabel(document)" :value="document.id" />
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
            v-else-if="rightPane.module === 'diagram'"
            :model-value="rightPane.resource_id"
            size="small"
            placeholder="选择图表"
            @change="changeResource('right', String($event || ''))"
          >
            <el-option v-for="document in diagramOptions" :key="document.id" :label="document.title" :value="document.id" />
          </el-select>
          <el-button v-if="rightPane.module === 'diagram'" type="primary" plain size="small" @click="openDiagramCreator('right')">新建</el-button>
          <el-select
            v-if="rightPane.module === 'document'"
            v-model="rightPane.section_id"
            size="small"
            placeholder="当前章节"
            @change="markCustomAndPersist"
          >
            <el-option v-for="section in sectionOptionsFor('right')" :key="section.id" :label="section.title" :value="section.id" />
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
          v-if="rightPane.module !== 'document' || paneReady.right"
          ref="rightPaneComponent"
          :mode="rightPane.module"
          :project-id="projectId"
          :source-document="rightSource"
          :presentation-document="rightPresentation"
          :diagram-id="rightPane.module === 'diagram' ? rightPane.resource_id : undefined"
          :document-target-id="oppositeDocumentId('right')"
          :document-target-section-id="oppositeDocumentSectionId('right')"
          :presentation-target-id="oppositePresentationId('right')"
          :presentation-target-slide="oppositePresentationSlide('right')"
          :section-id="rightPane.section_id || ''"
          :outline="outlineFor('right')"
          :selected-node-id="rightPane.section_id || ''"
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
          @document-changed="handleAiDocumentChanged"
          @select-outline="handleOutlineSelection('right', $event)"
          @navigate-to-thesis="emit('navigate-to-thesis', $event)"
          @slide-changed="handleSlideChanged('right', $event)"
        />
        <el-skeleton v-else class="pane-loading" animated :rows="8" />
      </article>
    </div>

    <el-dialog v-model="diagramCreatorVisible" title="新建结构化图表" width="min(520px, 92vw)" destroy-on-close>
      <el-form label-position="top">
        <el-form-item label="图表名称"><el-input v-model="diagramDraft.title" maxlength="120" /></el-form-item>
        <el-form-item label="起始模板">
          <el-radio-group v-model="diagramDraft.template_id" class="template-radio-group">
            <el-radio-button label="blank">空白画布</el-radio-button>
            <el-radio-button label="thesis-roadmap">论文技术路线</el-radio-button>
            <el-radio-button label="system-architecture">系统架构</el-radio-button>
            <el-radio-button label="ooda">OODA 流程</el-radio-button>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="diagramCreatorVisible = false">取消</el-button>
        <el-button type="primary" :loading="creatingDiagram" :disabled="!diagramDraft.title.trim()" @click="createDiagram">创建并打开</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { FullScreen, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import WritingWorkspacePane, {
  type WritingPaneContext,
  type WritingPaneMode
} from './WritingWorkspacePane.vue'
import {
  createWritingDiagram,
  getWritingDiagrams,
  getWritingWorkbenchPreference,
  getDocumentWritingWorkspace,
  compareWritingDocuments,
  updateWritingWorkbenchPreference,
  type WritingWorkbenchPaneState,
  type WritingAiTarget,
  type WritingDocumentComparison,
  type WritingDirectoryNode,
  type WritingProjectDocument
} from '@/api/writing'

type PaneSide = 'left' | 'right'
type WorkbenchPreset =
  | 'writing'
  | 'presentation'
  | 'document_compare'
  | 'document_presentation'
  | 'diagramming'
  | 'document_diagram'
  | 'presentation_diagram'
  | 'diagram_compare'
  | 'custom'

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
  initialPresetOverride?: boolean
}>()

const emit = defineEmits<{
  changed: [kind: 'document' | 'presentation' | 'diagram']
  'select-outline': [node: WritingDirectoryNode]
  'navigate-to-thesis': [payload: { sourceDocumentId: string; section: string }]
  'slide-changed': [slide: number]
}>()

const sourceOptions = computed(() => props.sourceDocuments?.length ? props.sourceDocuments : props.sourceDocument ? [props.sourceDocument] : [])
const presentationOptions = computed(() => props.presentationDocuments?.length ? props.presentationDocuments : props.presentationDocument ? [props.presentationDocument] : [])
const diagramOptions = ref<WritingProjectDocument[]>([])
const diagramCreatorVisible = ref(false)
const creatingDiagram = ref(false)
const diagramCreatorSide = ref<PaneSide>('right')
const diagramDraft = ref({ title: '新建论文插图', template_id: 'blank' })
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
const documentOutlines = ref<Record<string, WritingDirectoryNode[]>>({})
const comparison = ref<WritingDocumentComparison>()
const comparisonLoading = ref(false)
const differenceIndex = ref(0)
const syncComparisonSections = ref(false)
const paneReady = ref<Record<PaneSide, boolean>>({ left: false, right: false })
const outlineLoads = new Map<string, Promise<void>>()
const paneOutlineGeneration: Record<PaneSide, number> = { left: 0, right: 0 }
let persistTimer: ReturnType<typeof setTimeout> | undefined
let persistInFlight = false
let persistQueued = false

function defaultPane(module: WritingPaneMode, _side: PaneSide): WritingWorkbenchPaneState {
  return {
    module,
    resource_id: module === 'document'
      ? props.sourceDocument?.id
      : module === 'presentation'
        ? props.presentationDocument?.id
        : module === 'diagram'
          ? diagramOptions.value[0]?.id
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
  { label: '版本比对', value: 'document_compare' },
  { label: '文档/PPT校验', value: 'document_presentation' },
  { label: '图表创作', value: 'diagramming' },
  { label: '论文插图', value: 'document_diagram' },
  { label: 'PPT配图', value: 'presentation_diagram' },
  { label: '自定义', value: 'custom' }
]
const paneModeOptions = [
  { label: '文档', value: 'document' },
  { label: 'PPT', value: 'presentation' },
  { label: '画图', value: 'diagram' },
  { label: 'AI', value: 'ai' }
]
const mobilePaneOptions = [
  { label: '左窗口', value: 'left' },
  { label: '右窗口', value: 'right' }
]

type OutlineOption = { id: string; title: string }

function flattenOutline(outline: WritingDirectoryNode[]) {
  const rows: Array<{ id: string; title: string }> = []
  const seen = new Set<string>()
  const visit = (nodes: WritingDirectoryNode[]) => nodes.forEach(node => {
    const id = node.section_id || node.target_id
    if (id && !seen.has(id)) {
      seen.add(id)
      rows.push({ id, title: String(node.title || '') })
    }
    if (node.children?.length) visit(node.children)
  })
  visit(outline || [])
  return rows
}

function sectionOrdinal(id: string | null | undefined = '') {
  const normalizedId = String(id || '')
  const match = normalizedId.match(/(?:^|-)section-(\d+)(?:-|$)/i) || normalizedId.match(/^section-(\d+)(?:-|$)/i)
  return match ? Number(match[1]) : undefined
}

function chineseChapterNumber(value: string) {
  const digits: Record<string, number> = { 零: 0, 一: 1, 二: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9 }
  if (value === '十') return 10
  if (value.includes('十')) {
    const [tens, units] = value.split('十')
    return (tens ? digits[tens] : 1) * 10 + (units ? digits[units] : 0)
  }
  return digits[value]
}

function normalizedSectionTitle(title: string | null | undefined = '') {
  return String(title || '')
    .replace(/第([零一二三四五六七八九十]+)章/g, (_whole, number: string) => `第${chineseChapterNumber(number)}章`)
    .replace(/\s+/g, '')
}

function equivalentSection(options: OutlineOption[], reference: Partial<OutlineOption>) {
  const ordinal = sectionOrdinal(reference.id)
  if (ordinal !== undefined) {
    const byOrdinal = options.find(row => sectionOrdinal(row.id) === ordinal)
    if (byOrdinal) return byOrdinal
  }
  const title = normalizedSectionTitle(reference.title)
  return title ? options.find(row => normalizedSectionTitle(row.title) === title) : undefined
}
function outlineFor(side: PaneSide) {
  const documentId = pane(side).value.resource_id || ''
  return documentOutlines.value[documentId] || (documentId === props.sourceDocument?.id ? props.outline : [])
}
function sectionOptionsFor(side: PaneSide) {
  return flattenOutline(outlineFor(side))
}
const leftSource = computed(() => sourceOptions.value.find(row => row.id === leftPane.value.resource_id) || props.sourceDocument || sourceOptions.value[0])
const rightSource = computed(() => sourceOptions.value.find(row => row.id === rightPane.value.resource_id) || props.sourceDocument || sourceOptions.value[0])
const leftPresentation = computed(() => presentationOptions.value.find(row => row.id === leftPane.value.resource_id) || props.presentationDocument || presentationOptions.value[0])
const rightPresentation = computed(() => presentationOptions.value.find(row => row.id === rightPane.value.resource_id) || props.presentationDocument || presentationOptions.value[0])
const leftDiagram = computed(() => diagramOptions.value.find(row => row.id === leftPane.value.resource_id))
const rightDiagram = computed(() => diagramOptions.value.find(row => row.id === rightPane.value.resource_id))
const sameWritableResource = computed(() => (
  leftPane.value.module === rightPane.value.module
  && leftPane.value.module !== 'ai'
  && Boolean(leftPane.value.resource_id)
  && leftPane.value.resource_id === rightPane.value.resource_id
))
const leftReadOnly = computed(() => (
  leftPane.value.module === 'diagram' ? leftDiagram.value?.edit_policy === 'read_only' : leftSource.value?.edit_policy === 'read_only'
))
const rightReadOnly = computed(() => (
  (rightPane.value.module === 'diagram' ? rightDiagram.value?.edit_policy === 'read_only' : rightSource.value?.edit_policy === 'read_only')
  || sameWritableResource.value
))
const differences = computed(() => (comparison.value?.sections || []).flatMap(section =>
  section.changes.filter(change => change.operation !== 'unchanged').map(change => ({ section, change }))
))
const activeDifference = computed(() => differences.value[differenceIndex.value])
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
  if (state.module === 'diagram') return diagramOptions.value.find(row => row.id === state.resource_id)?.title || '画图'
  return state.ai_target_locked ? 'AI 协作 · 已锁定目标' : 'AI 协作 · 跟随焦点'
}

function oppositeDocumentId(side: PaneSide) {
  const target = side === 'left' ? rightPane.value : leftPane.value
  return target.module === 'document' ? target.resource_id : undefined
}

function oppositeDocumentSectionId(side: PaneSide) {
  const target = side === 'left' ? rightPane.value : leftPane.value
  return target.module === 'document' ? target.section_id : undefined
}

function oppositePresentationId(side: PaneSide) {
  const target = side === 'left' ? rightPane.value : leftPane.value
  return target.module === 'presentation' ? target.resource_id : undefined
}

function oppositePresentationSlide(side: PaneSide) {
  const target = side === 'left' ? rightPane.value : leftPane.value
  return target.module === 'presentation' ? target.slide : undefined
}

function documentOptionLabel(document: WritingProjectDocument) {
  const edition = document.lineage?.edition_label ? `${document.lineage.edition_label} · ` : ''
  const policy = document.edit_policy === 'read_only'
    ? document.delivery_role === 'deliverable'
      ? '（冻结交付基线，只读）'
      : '（只读）'
    : document.is_primary
      ? document.delivery_role === 'candidate'
        ? '（当前正文权威，交付待冻结）'
        : '（当前正文权威）'
      : document.delivery_role === 'candidate'
        ? '（候选，不进入交付包）'
        : ''
  return `${edition}${document.title}${policy}`
}

async function loadDiagrams() {
  try {
    const result = await getWritingDiagrams(props.projectId)
    diagramOptions.value = result.diagrams.map(row => ({
      ...row,
      ...(row.diagram ? { revision: row.diagram.revision } : {})
    }))
  } catch {
    diagramOptions.value = []
  }
}

function openDiagramCreator(side: PaneSide) {
  diagramCreatorSide.value = side
  diagramDraft.value = { title: '新建论文插图', template_id: 'blank' }
  diagramCreatorVisible.value = true
}

async function createDiagram() {
  creatingDiagram.value = true
  try {
    const result = await createWritingDiagram(props.projectId, {
      title: diagramDraft.value.title.trim(),
      template_id: diagramDraft.value.template_id,
      diagram_type: diagramDraft.value.template_id === 'ooda' ? 'flowchart' : 'architecture'
    })
    await loadDiagrams()
    const target = pane(diagramCreatorSide.value)
    target.value = {
      ...defaultPane('diagram', diagramCreatorSide.value),
      resource_id: result.document.id
    }
    diagramCreatorVisible.value = false
    preset.value = 'custom'
    schedulePersist()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '创建图表失败')
  } finally {
    creatingDiagram.value = false
  }
}

async function loadDocumentOutline(documentId?: string) {
  if (!documentId || documentOutlines.value[documentId]) return
  const existing = outlineLoads.get(documentId)
  if (existing) return existing
  const projectId = props.projectId
  let load!: Promise<void>
  load = (async () => {
    try {
      const workspace = await getDocumentWritingWorkspace(projectId, documentId)
      if (projectId === props.projectId) {
        documentOutlines.value = { ...documentOutlines.value, [documentId]: workspace.directory || [] }
      }
    } catch {
      if (projectId === props.projectId) {
        documentOutlines.value = { ...documentOutlines.value, [documentId]: [] }
      }
    } finally {
      if (outlineLoads.get(documentId) === load) outlineLoads.delete(documentId)
    }
  })()
  outlineLoads.set(documentId, load)
  return load
}

async function ensurePaneOutline(side: PaneSide) {
  const generation = ++paneOutlineGeneration[side]
  const state = pane(side).value
  if (state.module !== 'document') {
    paneReady.value[side] = true
    return
  }
  const resourceId = state.resource_id
  paneReady.value[side] = false
  await loadDocumentOutline(resourceId)
  if (generation !== paneOutlineGeneration[side]
    || state.module !== 'document'
    || state.resource_id !== resourceId) return
  const options = sectionOptionsFor(side)
  if (!options.some(row => row.id === state.section_id)) {
    state.section_id = equivalentSection(options, { id: state.section_id })?.id || options[0]?.id
  }
  paneReady.value[side] = true
}

async function refreshComparison() {
  if (leftPane.value.module !== 'document' || rightPane.value.module !== 'document'
    || !leftPane.value.resource_id || !rightPane.value.resource_id
    || leftPane.value.resource_id === rightPane.value.resource_id) {
    comparison.value = undefined
    return
  }
  comparisonLoading.value = true
  try {
    comparison.value = await compareWritingDocuments(props.projectId, {
      left_document_id: leftPane.value.resource_id,
      right_document_id: rightPane.value.resource_id,
      left_revision: leftSource.value?.revision,
      right_revision: rightSource.value?.revision
    })
    differenceIndex.value = 0
  } catch {
    comparison.value = undefined
  } finally {
    comparisonLoading.value = false
  }
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
  paneReady.value[side] = module !== 'document'
  await ensurePaneOutline(side)
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
  target.value.section_id = undefined
  target.value.resource_id = resourceId
  await ensurePaneOutline(side)
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
  } else if (nextPreset === 'document_compare') {
    const candidate = sourceOptions.value.find(row => row.delivery_role === 'candidate')
    const historical = [...sourceOptions.value]
      .filter(row => row.delivery_role === 'historical_reference')
      .sort((a, b) => Number(b.lineage?.sequence || 0) - Number(a.lineage?.sequence || 0))[0]
    const current = sourceOptions.value.find(row => row.edit_policy !== 'read_only' && row.lineage?.sequence === 3)
      || props.sourceDocument || sourceOptions.value.find(row => row.edit_policy !== 'read_only')
    leftPane.value = { ...defaultPane('document', 'left'), resource_id: candidate?.id || historical?.id || sourceOptions.value[0]?.id, section_id: undefined }
    rightPane.value = { ...defaultPane('document', 'right'), resource_id: current?.id || sourceOptions.value[sourceOptions.value.length - 1]?.id, section_id: undefined }
    splitPercent.value = 50
  } else if (nextPreset === 'document_presentation') {
    leftPane.value = defaultPane('document', 'left')
    rightPane.value = defaultPane('presentation', 'right')
    splitPercent.value = 50
  } else if (nextPreset === 'diagramming') {
    leftPane.value = defaultPane('ai', 'left')
    rightPane.value = defaultPane('diagram', 'right')
    splitPercent.value = 36
  } else if (nextPreset === 'document_diagram') {
    leftPane.value = defaultPane('document', 'left')
    rightPane.value = defaultPane('diagram', 'right')
    splitPercent.value = 45
  } else if (nextPreset === 'presentation_diagram') {
    leftPane.value = defaultPane('presentation', 'left')
    rightPane.value = defaultPane('diagram', 'right')
    splitPercent.value = 45
  } else {
    leftPane.value = defaultPane('diagram', 'left')
    rightPane.value = defaultPane('document', 'right')
    splitPercent.value = 50
  }
  await Promise.all([ensurePaneOutline('left'), ensurePaneOutline('right')])
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
  const selectedId = node.section_id || node.target_id || node.id
  pane(side).value.section_id = selectedId
  if (syncComparisonSections.value && comparison.value) {
    const title = normalizedSectionTitle(node.title)
    const mapped = comparison.value.sections.find(row =>
      normalizedSectionTitle(row.left_title) === title || normalizedSectionTitle(row.right_title) === title
    )
    const other: PaneSide = side === 'left' ? 'right' : 'left'
    const options = sectionOptionsFor(other)
    const direct = equivalentSection(options, { id: selectedId, title: node.title })
    if (direct) {
      pane(other).value.section_id = direct.id
    } else if (mapped) {
      const targetTitle = side === 'left' ? mapped.right_title : mapped.left_title
      const target = equivalentSection(options, { title: targetTitle })
      if (target) pane(other).value.section_id = target.id
    }
  }
  if (pane(side).value.resource_id === props.sourceDocument?.id) {
    emit('select-outline', node)
  }
  schedulePersist()
}

function handleSlideChanged(side: PaneSide, slide: number) {
  pane(side).value.slide = slide
  emit('slide-changed', slide)
  schedulePersist()
}

function handleChanged(kind: 'document' | 'presentation' | 'diagram') {
  emit('changed', kind)
  if (kind === 'document') void refreshComparison()
  if (kind === 'diagram') void loadDiagrams()
}

function handleAiDocumentChanged(documentId: string) {
  ;(['left', 'right'] as PaneSide[]).forEach(side => {
    const state = pane(side).value
    if (state.module === 'document' && state.resource_id === documentId) refreshPane(side)
  })
  const remaining = Object.entries(documentOutlines.value)
    .filter(([id]) => id !== documentId)
  documentOutlines.value = Object.fromEntries(remaining)
  emit('changed', 'document')
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
    schema_version: 3,
    preset: preset.value,
    split_percent: splitPercent.value,
    maximized_pane: maximizedPane.value,
    panes: {
      left: { ...leftPane.value },
      right: { ...rightPane.value }
    }
  }
}

function normalizeStoredPane(
  value: WritingWorkbenchPaneState | undefined,
  side: PaneSide,
  oppositeResourceId?: string
) {
  const module = value?.module || (side === 'left' ? 'ai' : 'document')
  const normalized = { ...defaultPane(module, side), ...(value || {}) }
  if (module === 'document' && !sourceOptions.value.some(row => row.id === normalized.resource_id)) {
    const historical = [...sourceOptions.value]
      .filter(row => row.delivery_role === 'historical_reference' && row.id !== oppositeResourceId)
      .sort((a, b) => Number(b.lineage?.sequence || 0) - Number(a.lineage?.sequence || 0))[0]
    const fallback = historical
      || sourceOptions.value.find(row => row.id !== oppositeResourceId)
      || props.sourceDocument
      || sourceOptions.value[0]
    return {
      pane: { ...normalized, resource_id: fallback?.id, section_id: undefined },
      repaired: true
    }
  }
  if (module === 'presentation' && !presentationOptions.value.some(row => row.id === normalized.resource_id)) {
    return {
      pane: { ...normalized, resource_id: props.presentationDocument?.id, slide: 1 },
      repaired: true
    }
  }
  if (module === 'diagram' && !diagramOptions.value.some(row => row.id === normalized.resource_id)) {
    return {
      pane: { ...normalized, resource_id: diagramOptions.value[0]?.id },
      repaired: true
    }
  }
  return { pane: normalized, repaired: false }
}

function applyStoredPreference(value: any, hydratePanes = true) {
  preferenceRevision.value = Number(value.revision || 0)
  if (!hydratePanes) return false
  preset.value = value.preset === 'comparison' ? 'document_presentation' : value.preset || props.initialPreset || 'writing'
  splitPercent.value = Math.max(28, Math.min(72, Number(value.split_percent || 42)))
  maximizedPane.value = value.maximized_pane || undefined
  const storedLeft = value.panes?.left as WritingWorkbenchPaneState | undefined
  const storedRight = value.panes?.right as WritingWorkbenchPaneState | undefined
  const left = normalizeStoredPane(storedLeft, 'left', storedRight?.resource_id)
  const right = normalizeStoredPane(storedRight, 'right', left.pane.resource_id)
  leftPane.value = left.pane
  rightPane.value = right.pane
  paneReady.value.left = leftPane.value.module !== 'document'
  paneReady.value.right = rightPane.value.module !== 'document'
  void Promise.all([ensurePaneOutline('left'), ensurePaneOutline('right')])
  return left.repaired || right.repaired
}

async function loadPreference() {
  try {
    const value = await getWritingWorkbenchPreference(props.projectId)
    if (props.initialPresetOverride) {
      preferenceRevision.value = Number(value.revision || 0)
      await applyPreset(props.initialPreset || 'writing')
    }
    else if (Number(value.revision || 0) > 0) {
      const repaired = applyStoredPreference(value)
      if (repaired) schedulePersist()
    }
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
  persistTimer = undefined
  if (persistInFlight) {
    persistQueued = true
    return
  }
  persistInFlight = true
  try {
    const saved = await updateWritingWorkbenchPreference(props.projectId, preferencePayload())
    applyStoredPreference(saved, false)
    preferenceState.value = 'saved'
  } catch (error: any) {
    preferenceState.value = 'error'
    if (error?.response?.status === 409) {
      const current = await getWritingWorkbenchPreference(props.projectId)
      applyStoredPreference(current)
      ElMessage.warning('布局已由另一设备更新，已载入最新版本')
    }
  } finally {
    persistInFlight = false
    if (persistQueued) {
      persistQueued = false
      preferenceState.value = 'saving'
      await persistPreference()
    }
  }
}

watch(
  () => [leftPane.value.module, leftPane.value.resource_id, rightPane.value.module, rightPane.value.resource_id],
  () => {
    void ensurePaneOutline('left')
    void ensurePaneOutline('right')
    void refreshComparison()
  }
)

watch(differences, rows => {
  if (differenceIndex.value >= rows.length) differenceIndex.value = Math.max(0, rows.length - 1)
})

watch(activeDifference, value => {
  if (!value || !syncComparisonSections.value) return
  const left = equivalentSection(sectionOptionsFor('left'), { title: value.section.left_title })
  const right = equivalentSection(sectionOptionsFor('right'), { title: value.section.right_title })
  if (left) leftPane.value.section_id = left.id
  if (right) rightPane.value.section_id = right.id
})

onMounted(async () => {
  if (props.sourceDocument?.id) documentOutlines.value[props.sourceDocument.id] = props.outline || []
  await loadDiagrams()
  await loadPreference()
  await Promise.all([ensurePaneOutline('left'), ensurePaneOutline('right')])
  await refreshComparison()
})
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
.comparison-strip { display: grid; gap: 8px; padding: 9px 11px; border: 1px solid var(--line-color); border-radius: 6px; background: var(--card-bg); }
.comparison-summary { display: flex; align-items: center; gap: 12px; color: var(--text-secondary); font-size: 10px; }
.comparison-summary strong { color: var(--text-primary); font-size: 11px; }
.comparison-summary .el-switch { margin-left: auto; }
.diff-added { color: var(--el-color-success); }
.diff-deleted { color: var(--el-color-danger); }
.diff-modified { color: var(--el-color-warning); }
.difference-row { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto; gap: 8px; padding: 8px; border-left: 3px solid var(--el-color-warning); background: var(--panel-bg); }
.difference-row.is-added { border-left-color: var(--el-color-success); }
.difference-row.is-deleted { border-left-color: var(--el-color-danger); }
.difference-row > div:not(.difference-actions) { min-width: 0; padding: 7px 9px; background: var(--content-bg); }
.difference-row small { color: var(--text-secondary); font-size: 9px; }
.difference-row p { max-height: 84px; margin: 5px 0 0; overflow: auto; color: var(--text-primary); font-size: 10px; line-height: 1.55; white-space: pre-wrap; }
.difference-actions { display: grid; align-content: center; justify-items: center; gap: 5px; min-width: 74px; color: var(--text-secondary); font-size: 9px; }
.linked-panes { display: grid; min-width: 0; align-items: stretch; }
.linked-pane { display: grid; grid-template-rows: auto auto minmax(0, 1fr); min-width: 0; overflow: hidden; border: 1px solid var(--line-color); border-radius: 7px; background: var(--card-bg); box-shadow: 0 12px 30px rgb(0 0 0 / 18%); }
.pane-loading { min-height: 700px; padding: 22px; background: var(--content-bg); }
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
  .difference-row { grid-template-columns: 1fr 1fr; }
  .difference-actions { grid-column: 1 / -1; display: flex; justify-content: center; }
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
