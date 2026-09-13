<template>
  <section class="diagram-workspace" aria-label="结构化画图工作台">
    <header class="diagram-toolbar">
      <div class="tool-group">
        <el-tooltip content="选择并移动元素"><el-button :icon="Pointer" circle :type="tool === 'select' ? 'primary' : ''" @click="tool = 'select'" /></el-tooltip>
        <el-tooltip content="添加文字节点"><el-button :icon="EditPen" circle @click="addNode('text')" /></el-tooltip>
        <el-tooltip content="撤销"><el-button :icon="Back" circle :disabled="!canUndo" @click="undo" /></el-tooltip>
        <el-tooltip content="重做"><el-button :icon="Right" circle :disabled="!canRedo" @click="redo" /></el-tooltip>
      </div>
      <div class="tool-group">
        <el-tooltip content="自动排版"><el-button :icon="Operation" circle @click="autoLayout" /></el-tooltip>
        <el-tooltip content="适合窗口"><el-button :icon="FullScreen" circle @click="fitContent" /></el-tooltip>
        <el-tooltip content="缩小"><el-button :icon="ZoomOut" circle @click="zoom(-0.1)" /></el-tooltip>
        <span class="zoom-value">{{ zoomLabel }}</span>
        <el-tooltip content="放大"><el-button :icon="ZoomIn" circle @click="zoom(0.1)" /></el-tooltip>
      </div>
      <div class="tool-group toolbar-tail">
        <span class="save-state" :class="`is-${saveState}`">{{ saveStateLabel }}</span>
        <el-dropdown trigger="click" @command="downloadExport">
          <el-button :icon="Download">导出<el-icon class="el-icon--right"><ArrowDown /></el-icon></el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="svg">SVG 矢量图</el-dropdown-item>
              <el-dropdown-item command="png">PNG 2倍图</el-dropdown-item>
              <el-dropdown-item command="pdf">PDF</el-dropdown-item>
              <el-dropdown-item command="json">结构化 JSON</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </header>

    <div v-if="loading" class="diagram-loading"><el-skeleton animated :rows="10" /></div>
    <el-result v-else-if="loadError" icon="error" title="图表加载失败" :sub-title="loadError">
      <template #extra><el-button type="primary" @click="loadDiagram">重试</el-button></template>
    </el-result>
    <div v-else class="diagram-shell" :class="{ 'library-open': libraryOpen, 'inspector-open': inspectorOpen }">
      <aside class="shape-library">
        <header><strong>图形库</strong><el-button :icon="Close" text circle @click="libraryOpen = false" /></header>
        <div class="shape-group">
          <small>流程与架构</small>
          <button v-for="shape in shapes" :key="shape.key" type="button" @click="addNode(shape.key)">
            <span :class="['shape-preview', `is-${shape.key}`]"></span>
            {{ shape.label }}
          </button>
        </div>
        <div class="template-group">
          <small>快速模板</small>
          <el-button v-for="template in templates" :key="template.id" text @click="applyTemplate(template.id)">
            {{ template.label }}
          </el-button>
        </div>
      </aside>

      <main class="diagram-stage">
        <div class="stage-float-actions">
          <el-button v-if="!libraryOpen" :icon="Grid" circle aria-label="打开图形库" @click="libraryOpen = true" />
          <el-button v-if="!inspectorOpen" :icon="Setting" circle aria-label="打开属性面板" @click="inspectorOpen = true" />
        </div>
        <div ref="canvasElement" class="diagram-canvas"></div>
        <div ref="miniMapElement" class="diagram-minimap"></div>
      </main>

      <aside class="property-panel">
        <header><strong>属性</strong><el-button :icon="Close" text circle @click="inspectorOpen = false" /></header>
        <template v-if="selectedCell">
          <el-form label-position="top" size="small">
            <el-form-item label="文字">
              <el-input v-model="selectedLabel" maxlength="120" @change="applySelectedLabel" />
            </el-form-item>
            <div class="property-grid">
              <el-form-item label="X"><el-input-number v-model="selectedGeometry.x" controls-position="right" @change="applyGeometry" /></el-form-item>
              <el-form-item label="Y"><el-input-number v-model="selectedGeometry.y" controls-position="right" @change="applyGeometry" /></el-form-item>
              <el-form-item label="宽"><el-input-number v-model="selectedGeometry.width" :min="48" controls-position="right" @change="applyGeometry" /></el-form-item>
              <el-form-item label="高"><el-input-number v-model="selectedGeometry.height" :min="32" controls-position="right" @change="applyGeometry" /></el-form-item>
            </div>
            <el-form-item label="填充色"><el-color-picker v-model="selectedFill" show-alpha @change="applyStyle" /></el-form-item>
            <el-form-item label="边框色"><el-color-picker v-model="selectedStroke" @change="applyStyle" /></el-form-item>
            <el-form-item label="文字色"><el-color-picker v-model="selectedTextColor" @change="applyStyle" /></el-form-item>
            <div class="property-actions">
              <el-button :icon="Lock" @click="toggleLock">{{ selectedLocked ? '解锁' : '锁定' }}</el-button>
              <el-button :icon="Delete" type="danger" plain @click="deleteSelection">删除</el-button>
            </div>
          </el-form>
        </template>
        <el-empty v-else description="选择节点或连线后编辑属性" :image-size="48" />
        <section class="reference-panel">
          <header><strong>引用</strong><el-tag size="small" effect="plain">{{ references.length }}</el-tag></header>
          <p>插入后固定当前图表版本，新版本不会静默覆盖。</p>
          <div class="reference-actions">
            <el-button size="small" :disabled="!documentTargetId" @click="insertReference('rich_text')">插入文档</el-button>
            <el-button size="small" :disabled="!presentationTargetId" @click="insertReference('presentation')">插入 PPT</el-button>
          </div>
          <el-tag v-if="references.some(row => row.status === 'update_available')" type="warning" size="small">已有引用可更新</el-tag>
        </section>
      </aside>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import {
  ArrowDown, Back, Close, Delete, Download, EditPen, FullScreen, Grid, Lock,
  Operation, Pointer, Right, Setting, ZoomIn, ZoomOut
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { Clipboard, Graph, History, Keyboard, MiniMap, Selection, Snapline } from '@antv/x6'
import * as dagre from '@dagrejs/dagre'
import {
  createWritingDiagramReference,
  createWritingDiagramVersion,
  exportWritingDiagram,
  getWritingCollaboration,
  getWritingDiagram,
  getWritingDiagramReferences,
  publishWritingDiagramToDocument,
  updateWritingDiagramDraft,
  type DiagramCell,
  type DiagramDocumentState,
  type DiagramReference,
  type WritingAiTarget
} from '@/api/writing'

const props = withDefaults(defineProps<{
  projectId: string
  diagramId: string
  readOnly?: boolean
  documentTargetId?: string
  documentSectionId?: string
  presentationTargetId?: string
  presentationSlide?: number
}>(), { readOnly: false, documentSectionId: '', presentationSlide: 1 })

const emit = defineEmits<{
  changed: []
  'context-changed': [context: WritingAiTarget]
}>()

const canvasElement = ref<HTMLElement>()
const miniMapElement = ref<HTMLElement>()
const loading = ref(true)
const loadError = ref('')
const saveState = ref<'saved' | 'saving' | 'error'>('saved')
const diagram = ref<DiagramDocumentState>()
const references = ref<DiagramReference[]>([])
const libraryOpen = ref(false)
const inspectorOpen = ref(false)
const tool = ref('select')
const zoomLevel = ref(1)
const selectedCell = ref<any>()
const selectedLabel = ref('')
const selectedFill = ref('#f8fafc')
const selectedStroke = ref('#64748b')
const selectedTextColor = ref('#172033')
const selectedLocked = ref(false)
const selectedGeometry = reactive({ x: 0, y: 0, width: 180, height: 64 })
let graph: Graph | undefined
let canvasResizeObserver: ResizeObserver | undefined
let resizeFrame: number | undefined
let saveTimer: ReturnType<typeof setTimeout> | undefined
let maxSaveTimer: ReturnType<typeof setTimeout> | undefined
let loadingGraph = false

const shapes = [
  { key: 'process', label: '过程' },
  { key: 'decision', label: '决策' },
  { key: 'data', label: '数据' },
  { key: 'agent', label: '智能体' },
  { key: 'group', label: '分组' },
  { key: 'text', label: '文字' }
]
const templates = [
  { id: 'thesis-roadmap', label: '论文技术路线图' },
  { id: 'system-architecture', label: '系统总体架构图' },
  { id: 'ooda', label: 'OODA 任务流程图' }
]
const saveStateLabel = computed(() => ({ saved: '已保存', saving: '保存中…', error: '保存失败' })[saveState.value])
const zoomLabel = computed(() => `${Math.round(zoomLevel.value * 100)}%`)

function setupGraph() {
  if (!canvasElement.value || !miniMapElement.value) return
  canvasResizeObserver?.disconnect()
  if (resizeFrame) cancelAnimationFrame(resizeFrame)
  graph?.dispose()
  graph = new Graph({
    container: canvasElement.value,
    autoResize: false,
    background: { color: '#f6f8fb' },
    grid: { visible: true, size: 8, type: 'doubleMesh', args: [{ color: '#dfe5ec', thickness: 1 }, { color: '#c8d1dc', thickness: 1, factor: 4 }] },
    panning: { enabled: true, eventTypes: ['rightMouseDown', 'mouseWheel'] },
    mousewheel: { enabled: true, modifiers: ['ctrl', 'meta'], minScale: 0.3, maxScale: 2 },
    connecting: {
      router: 'orth', connector: 'rounded', snap: true, allowBlank: false,
      createEdge: () => graph!.createEdge({ shape: 'edge', attrs: { line: { stroke: '#64748b', strokeWidth: 1.5, targetMarker: { name: 'block', width: 10, height: 8 } } } })
    },
    interacting: {
      nodeMovable: cellView => !props.readOnly && !Boolean(cellView.cell.getProp('locked')),
      edgeMovable: !props.readOnly,
      arrowheadMovable: !props.readOnly,
      vertexMovable: !props.readOnly
    }
  })
  graph.use(new Selection({ enabled: true, multiple: true, rubberband: true, movable: !props.readOnly }))
  graph.use(new Snapline({ enabled: true, resizing: true }))
  graph.use(new History({ enabled: true }))
  graph.use(new Clipboard({ enabled: true }))
  graph.use(new Keyboard({ enabled: true, global: false }))
  graph.use(new MiniMap({ container: miniMapElement.value, width: 148, height: 92, padding: 8 }))
  canvasResizeObserver = new ResizeObserver(() => {
    if (resizeFrame) cancelAnimationFrame(resizeFrame)
    resizeFrame = requestAnimationFrame(resizeCanvas)
  })
  canvasResizeObserver.observe(canvasElement.value)
  resizeCanvas()
  bindGraphEvents()
  if (diagram.value) loadCells(diagram.value.cells)
}

function resizeCanvas() {
  if (!graph || !canvasElement.value) return false
  const { width, height } = canvasElement.value.getBoundingClientRect()
  if (!Number.isFinite(width) || !Number.isFinite(height) || width < 80 || height < 80) return false
  graph.resize(Math.floor(width), Math.floor(height))
  return true
}

function bindGraphEvents() {
  if (!graph) return
  graph.on('cell:selected', ({ cell }) => selectCell(cell))
  graph.on('cell:unselected', () => {
    selectedCell.value = graph?.getSelectedCells()[0]
    if (selectedCell.value) selectCell(selectedCell.value)
  })
  graph.on('blank:click', () => { selectedCell.value = undefined; emitContext() })
  graph.on('scale', ({ sx }) => { zoomLevel.value = sx })
  graph.on('cell:change:*', scheduleSave)
  graph.on('cell:added', scheduleSave)
  graph.on('cell:removed', scheduleSave)
  graph.bindKey(['meta+z', 'ctrl+z'], () => { undo(); return false })
  graph.bindKey(['meta+shift+z', 'ctrl+shift+z'], () => { redo(); return false })
  graph.bindKey(['backspace', 'delete'], () => { deleteSelection(); return false })
}

function loadCells(cells: DiagramCell[]) {
  if (!graph) return
  loadingGraph = true
  const json = cells.map(cell => {
    const { type: _type, cell_revision: _revision, ...metadata } = cell
    if (cell.type === 'edge') return { ...metadata, shape: 'edge' }
    return {
      width: 190,
      height: 64,
      ...metadata,
      ports: metadata.ports || {
        groups: {
          top: { position: 'top', attrs: { circle: { r: 4, magnet: true, stroke: '#4b88d8', fill: '#fff' } } },
          right: { position: 'right', attrs: { circle: { r: 4, magnet: true, stroke: '#4b88d8', fill: '#fff' } } },
          bottom: { position: 'bottom', attrs: { circle: { r: 4, magnet: true, stroke: '#4b88d8', fill: '#fff' } } },
          left: { position: 'left', attrs: { circle: { r: 4, magnet: true, stroke: '#4b88d8', fill: '#fff' } } }
        },
        items: ['top', 'right', 'bottom', 'left'].map(group => ({ id: group, group }))
      },
      data: { ...(metadata.data || {}), cell_revision: cell.cell_revision, semantic_type: cell.type }
    }
  })
  graph.fromJSON(json)
  loadingGraph = false
  nextTick(fitContent)
}

function serializedCells(): DiagramCell[] {
  return (graph?.toJSON().cells || []).map((raw: any) => {
    const data = raw.data || {}
    return {
      ...raw,
      type: raw.shape === 'edge' || raw.source ? 'edge' : (data.semantic_type || 'node'),
      cell_revision: Number(data.cell_revision || 1)
    } as DiagramCell
  })
}

function scheduleSave() {
  if (loadingGraph || props.readOnly || !diagram.value) return
  saveState.value = 'saving'
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => void flush(), 1000)
  if (!maxSaveTimer) maxSaveTimer = setTimeout(() => void flush(), 5000)
}

async function flush(): Promise<boolean> {
  if (props.readOnly || !diagram.value || !graph) return true
  if (saveTimer) clearTimeout(saveTimer)
  if (maxSaveTimer) clearTimeout(maxSaveTimer)
  saveTimer = undefined
  maxSaveTimer = undefined
  try {
    saveState.value = 'saving'
    const saved = await updateWritingDiagramDraft(props.projectId, props.diagramId, {
      expected_revision: diagram.value.revision,
      title: diagram.value.title,
      diagram_type: diagram.value.diagram_type,
      theme_id: diagram.value.theme_id,
      page_settings: diagram.value.page_settings,
      cells: serializedCells()
    })
    diagram.value = saved
    saveState.value = 'saved'
    emit('changed')
    emitContext()
    return true
  } catch (error: any) {
    saveState.value = 'error'
    ElMessage.error(error?.response?.data?.detail || '图表保存失败，当前画布已保留')
    return false
  }
}

async function loadDiagram() {
  if (!props.diagramId) return
  loading.value = true
  loadError.value = ''
  try {
    const [resource, referenceResult] = await Promise.all([
      getWritingDiagram(props.projectId, props.diagramId),
      getWritingDiagramReferences(props.projectId, props.diagramId)
    ])
    diagram.value = resource.diagram
    references.value = referenceResult.references
    loading.value = false
    await nextTick()
    setupGraph()
    emitContext()
  } catch (error: any) {
    loadError.value = error?.response?.data?.detail || error?.message || '无法读取图表'
  } finally {
    loading.value = false
  }
}

function nodeStyle(shape: string) {
  const styles: Record<string, any> = {
    decision: { shape: 'polygon', attrs: { body: { refPoints: '0,10 10,0 20,10 10,20', fill: '#fff7ed', stroke: '#d97706' } } },
    data: { shape: 'rect', attrs: { body: { fill: '#eefbf3', stroke: '#15803d' } } },
    agent: { shape: 'ellipse', attrs: { body: { fill: '#eff6ff', stroke: '#2563eb' } } },
    group: { shape: 'rect', width: 320, height: 180, attrs: { body: { fill: '#f8fafc', fillOpacity: .35, stroke: '#94a3b8', strokeDasharray: '6 4' } } },
    text: { shape: 'rect', attrs: { body: { fill: 'transparent', stroke: 'transparent' } } },
    process: { shape: 'rect', attrs: { body: { fill: '#f8fafc', stroke: '#64748b' } } }
  }
  return styles[shape] || styles.process
}

function addNode(kind: string) {
  if (!graph || props.readOnly) return
  const center = graph.clientToLocal(canvasElement.value!.clientWidth / 2, canvasElement.value!.clientHeight / 2)
  const style = nodeStyle(kind)
  graph.addNode({
    id: `cell-${crypto.randomUUID()}`,
    x: center.x - Number(style.width || 190) / 2,
    y: center.y - Number(style.height || 64) / 2,
    width: style.width || 190,
    height: style.height || 64,
    label: kind === 'text' ? '说明文字' : '新建节点',
    ...style,
    attrs: {
      body: { rx: 6, ry: 6, strokeWidth: 1.5, ...(style.attrs?.body || {}) },
      label: { fill: '#172033', fontSize: 15, fontWeight: 600 }
    },
    ports: {
      groups: Object.fromEntries(['top', 'right', 'bottom', 'left'].map(position => [position, { position, attrs: { circle: { r: 4, magnet: true, stroke: '#4b88d8', fill: '#fff' } } }])),
      items: ['top', 'right', 'bottom', 'left'].map(group => ({ id: group, group }))
    },
    data: { cell_revision: 1, semantic_type: kind === 'group' ? 'group' : kind === 'text' ? 'text' : 'node' }
  })
}

function selectCell(cell: any) {
  selectedCell.value = cell
  selectedLabel.value = String(cell.attr('label/text') || cell.getLabel?.() || '')
  const position = cell.getPosition?.() || { x: 0, y: 0 }
  const size = cell.getSize?.() || { width: 0, height: 0 }
  Object.assign(selectedGeometry, { ...position, ...size })
  selectedFill.value = String(cell.attr('body/fill') || '#f8fafc')
  selectedStroke.value = String(cell.attr('body/stroke') || '#64748b')
  selectedTextColor.value = String(cell.attr('label/fill') || '#172033')
  selectedLocked.value = Boolean(cell.getProp('locked'))
  emitContext()
}

function emitContext() {
  if (!diagram.value) return
  emit('context-changed', {
    kind: 'diagram',
    document_id: props.diagramId,
    document_title: diagram.value.title,
    scope: selectedCell.value ? 'cells' : 'diagram',
    revision: diagram.value.revision,
    diagram_revision: diagram.value.revision,
    cell_ids: graph?.getSelectedCells().map(cell => cell.id) || []
  })
}

function applySelectedLabel() { selectedCell.value?.setLabel?.(selectedLabel.value); scheduleSave() }
function applyGeometry() {
  selectedCell.value?.position?.(selectedGeometry.x, selectedGeometry.y)
  selectedCell.value?.resize?.(selectedGeometry.width, selectedGeometry.height)
  scheduleSave()
}
function applyStyle() {
  selectedCell.value?.attr?.({
    body: { fill: selectedFill.value, stroke: selectedStroke.value },
    label: { fill: selectedTextColor.value }
  })
  scheduleSave()
}
function toggleLock() {
  const cell = selectedCell.value
  if (!cell) return
  selectedLocked.value = !selectedLocked.value
  cell.setProp('locked', selectedLocked.value)
  scheduleSave()
}
function deleteSelection() {
  if (!graph || props.readOnly) return
  graph.removeCells(graph.getSelectedCells())
  selectedCell.value = undefined
}
function undo() { graph?.undo(); canUndo.value = Boolean(graph?.canUndo()) }
function redo() { graph?.redo(); canRedo.value = Boolean(graph?.canRedo()) }
const canUndo = ref(false)
const canRedo = ref(false)

function zoom(delta: number) { graph?.zoom(delta); zoomLevel.value = graph?.zoom() || 1 }
function fitContent() {
  if (!graph || !resizeCanvas()) return
  graph.zoomToFit({ padding: 48, maxScale: 1 })
  graph.centerContent()
  zoomLevel.value = graph.zoom() || 1
}

function autoLayout() {
  if (!graph || props.readOnly) return
  const layoutGraph = new dagre.graphlib.Graph().setGraph({ rankdir: 'LR', nodesep: 48, ranksep: 90, marginx: 40, marginy: 40 }).setDefaultEdgeLabel(() => ({}))
  graph.getNodes().forEach(node => { const size = node.getSize(); layoutGraph.setNode(node.id, { width: size.width, height: size.height }) })
  graph.getEdges().forEach(edge => { const source = edge.getSourceCellId(); const target = edge.getTargetCellId(); if (source && target) layoutGraph.setEdge(source, target) })
  dagre.layout(layoutGraph)
  graph.getNodes().forEach(node => { const position = layoutGraph.node(node.id); const size = node.getSize(); node.position(position.x - size.width / 2, position.y - size.height / 2) })
  fitContent()
  scheduleSave()
}

async function applyTemplate(templateId: string) {
  if (!diagram.value || !graph || props.readOnly) return
  if (graph.getCells().length && !window.confirm('应用模板会替换当前画布，是否继续？')) return
  try {
    const created = await getWritingDiagram(props.projectId, props.diagramId)
    if (created.diagram.cells.length) {
      ElMessage.info('当前资源已有结构，请新建图表后选择模板')
      return
    }
    ElMessage.info(`请在新建图表时选择“${templates.find(row => row.id === templateId)?.label}”模板`)
  } catch {
    ElMessage.error('模板检查失败')
  }
}

async function downloadExport(format: 'svg' | 'png' | 'pdf' | 'json') {
  if (!(await flush())) return
  try {
    await createWritingDiagramVersion(props.projectId, props.diagramId, { label: `导出 ${format.toUpperCase()}`, reason: 'export' })
    const blob = await exportWritingDiagram(props.projectId, props.diagramId, format)
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${diagram.value?.title || 'diagram'}.${format}`
    anchor.click()
    URL.revokeObjectURL(url)
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '图表导出失败')
  }
}

async function insertReference(kind: 'rich_text' | 'presentation') {
  if (!(await flush()) || !diagram.value) return
  const targetId = kind === 'rich_text' ? props.documentTargetId : props.presentationTargetId
  if (!targetId) return
  try {
    let reference: DiagramReference
    if (kind === 'rich_text') {
      const collaboration = await getWritingCollaboration(
        props.projectId,
        targetId,
        props.documentSectionId
      )
      const blocks = collaboration.document?.content || []
      const anchorBlockId = String(blocks.at(-1)?.attrs?.blockId || '')
      if (!anchorBlockId) throw new Error('当前章节没有可用的插图位置')
      const published = await publishWritingDiagramToDocument(
        props.projectId,
        props.diagramId,
        {
          target_document_id: targetId,
          target_section_id: props.documentSectionId,
          expected_document_revision: collaboration.revision,
          expected_diagram_revision: diagram.value.revision,
          anchor_block_id: anchorBlockId,
          caption: diagram.value.title,
          export_format: 'svg',
          client_change_id: `diagram-${props.diagramId}-r${diagram.value.revision}-${targetId}-${props.documentSectionId || 'document'}`
        }
      )
      reference = published.reference
    } else {
      reference = await createWritingDiagramReference(props.projectId, props.diagramId, {
        target_kind: kind,
        target_document_id: targetId,
        target_slide: props.presentationSlide,
        export_format: 'svg',
        caption: diagram.value.title
      })
    }
    references.value = [reference, ...references.value]
    ElMessage.success(kind === 'rich_text' ? '图表已插入文档' : '已建立 PPT 配图引用')
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '建立图表引用失败')
  }
}

watch(() => props.diagramId, async (next, previous) => {
  if (next === previous) return
  if (previous && !(await flush())) return
  await loadDiagram()
})

onMounted(loadDiagram)
onBeforeUnmount(() => {
  if (saveTimer) clearTimeout(saveTimer)
  if (maxSaveTimer) clearTimeout(maxSaveTimer)
  canvasResizeObserver?.disconnect()
  if (resizeFrame) cancelAnimationFrame(resizeFrame)
  graph?.dispose()
})

defineExpose({ flush })
</script>

<style scoped>
.diagram-workspace { container-type: inline-size; display: grid; grid-template-rows: auto minmax(0, 1fr); min-height: 700px; height: 100%; background: var(--content-bg); overflow: hidden; }
.diagram-toolbar { display: flex; align-items: center; gap: 8px; min-height: 46px; padding: 6px 10px; border-bottom: 1px solid var(--line-color); background: var(--panel-bg); }
.tool-group { display: flex; align-items: center; gap: 5px; padding-right: 8px; border-right: 1px solid var(--line-color); }
.toolbar-tail { margin-left: auto; padding-right: 0; border-right: 0; }
.zoom-value, .save-state { min-width: 44px; color: var(--text-secondary); font-size: 11px; text-align: center; }
.save-state.is-error { color: var(--el-color-danger); }
.save-state.is-saving { color: var(--el-color-warning); }
.diagram-loading { padding: 24px; }
.diagram-shell { position: relative; display: grid; grid-template-columns: 184px minmax(0, 1fr) 220px; min-height: 0; overflow: hidden; }
.diagram-shell.library-open:not(.inspector-open) { grid-template-columns: 184px minmax(0, 1fr); }
.diagram-shell:not(.library-open).inspector-open { grid-template-columns: minmax(0, 1fr) 220px; }
.diagram-shell:not(.library-open):not(.inspector-open) { grid-template-columns: minmax(0, 1fr); }
.diagram-shell:not(.library-open) .shape-library, .diagram-shell:not(.inspector-open) .property-panel { display: none; }
.shape-library, .property-panel { min-width: 0; overflow: auto; padding: 10px; background: var(--panel-bg); }
.shape-library { border-right: 1px solid var(--line-color); }
.property-panel { border-left: 1px solid var(--line-color); }
.shape-library > header, .property-panel > header, .reference-panel header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.shape-group, .template-group { display: grid; gap: 6px; margin-bottom: 18px; }
.shape-group small, .template-group small { color: var(--text-secondary); }
.shape-group button { display: flex; align-items: center; gap: 9px; min-height: 38px; padding: 6px 8px; border: 1px solid var(--line-color); border-radius: 6px; color: var(--text-primary); background: var(--content-bg); cursor: pointer; }
.shape-group button:hover { border-color: var(--view-color-primary); background: color-mix(in srgb, var(--view-color-primary) 8%, var(--content-bg)); }
.shape-preview { width: 30px; height: 20px; border: 1.5px solid #64748b; border-radius: 4px; background: #f8fafc; }
.shape-preview.is-decision { transform: rotate(45deg) scale(.72); border-radius: 2px; background: #fff7ed; border-color: #d97706; }
.shape-preview.is-agent { border-radius: 50%; background: #eff6ff; border-color: #2563eb; }
.shape-preview.is-data { background: #eefbf3; border-color: #15803d; }
.shape-preview.is-group { border-style: dashed; background: transparent; }
.shape-preview.is-text { border: 0; background: linear-gradient(#64748b,#64748b) 50% 50%/24px 2px no-repeat; }
.diagram-stage { position: relative; min-width: 0; min-height: 0; overflow: hidden; }
.diagram-canvas { position: absolute; inset: 0; min-height: 560px; }
.diagram-minimap { position: absolute; z-index: 4; right: 12px; bottom: 12px; width: 148px; height: 92px; overflow: hidden; border: 1px solid var(--line-color); border-radius: 6px; background: rgba(255,255,255,.94); box-shadow: 0 8px 22px rgba(15,23,42,.14); }
.stage-float-actions { position: absolute; z-index: 5; top: 10px; left: 10px; display: flex; gap: 6px; }
.property-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 7px; }
.property-actions, .reference-actions { display: flex; gap: 7px; }
.reference-panel { margin-top: 18px; padding-top: 14px; border-top: 1px solid var(--line-color); }
.reference-panel p { color: var(--text-secondary); font-size: 11px; line-height: 1.6; }
@container (max-width: 760px) {
  .diagram-shell { grid-template-columns: minmax(0, 1fr); }
  .shape-library, .property-panel { position: absolute; z-index: 12; top: 46px; bottom: 0; width: min(280px, 82vw); box-shadow: 0 12px 30px rgba(15,23,42,.22); }
  .shape-library { left: 0; }
  .property-panel { right: 0; }
}
@media (max-width: 720px) {
  .diagram-toolbar { flex-wrap: wrap; }
  .toolbar-tail { width: 100%; margin-left: 0; justify-content: flex-end; }
  .diagram-workspace { min-height: calc(100vh - 290px); }
}
</style>
