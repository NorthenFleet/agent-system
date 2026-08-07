<template>
  <section class="workbook-workspace" v-loading="loading">
    <header class="workbook-head">
      <div>
        <span class="eyebrow">Excel 高保真工作区</span>
        <h3>{{ document.title }}</h3>
        <p v-if="metadata">
          {{ metadata.sheet_count }} 个工作表 · {{ formatNumber(metadata.cell_count) }} 个数据单元格 ·
          {{ formatNumber(metadata.formula_count) }} 个公式
        </p>
      </div>
      <div class="actions">
        <input ref="fileInput" type="file" accept=".xlsx" hidden @change="handleFile" />
        <el-button :icon="Upload" @click="fileInput?.click()">替换 XLSX</el-button>
        <el-button :icon="Download" @click="downloadSource">下载原表</el-button>
        <el-button :icon="Refresh" circle @click="loadAll" />
      </div>
    </header>

    <el-alert
      title="原始 XLSX 是格式与公式权威；网页修改按单元格写入，并由 LibreOffice 重算后保存为新版本。"
      type="info"
      :closable="false"
      show-icon
    />

    <el-tabs v-if="metadata?.sheets.length" v-model="activeSheet" class="sheet-tabs" @tab-change="loadSheet">
      <el-tab-pane
        v-for="sheet in metadata.sheets"
        :key="sheet.name"
        :name="sheet.name"
        :label="sheet.name"
      />
    </el-tabs>

    <div v-if="sheetData" class="cell-editor">
      <strong>{{ selectedCoordinate || '选择单元格' }}</strong>
      <el-input
        v-model="editorValue"
        :disabled="!selectedCoordinate"
        placeholder="选择单元格后编辑；公式以 = 开头"
        @keyup.enter="saveCell"
      />
      <el-button type="primary" :disabled="!selectedCoordinate" :loading="saving" @click="saveCell">保存单元格</el-button>
      <small>v{{ sheetData.revision }} · {{ sheetData.max_row }} 行 × {{ sheetData.max_column }} 列</small>
    </div>

    <div v-if="sheetData" class="grid-scroll">
      <table class="sheet-grid">
        <thead>
          <tr>
            <th class="row-number corner"></th>
            <th
              v-for="column in sheetData.columns"
              :key="column.index"
              :style="{ minWidth: `${Math.max(72, Math.min(column.width * 8, 240))}px` }"
            >{{ column.letter }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in sheetData.rows" :key="row.index" :style="{ height: `${Math.max(row.height, 24)}px` }">
            <th class="row-number">{{ row.index }}</th>
            <template v-for="column in sheetData.columns" :key="`${row.index}-${column.index}`">
              <td
                v-if="!mergeInfo(row.index, column.index).covered"
                :rowspan="mergeInfo(row.index, column.index).rowspan"
                :colspan="mergeInfo(row.index, column.index).colspan"
                :class="{
                  selected: selectedCoordinate === coordinate(row.index, column.index),
                  formula: Boolean(cellAt(row.index, column.index)?.formula)
                }"
                :style="cellStyle(row.index, column.index)"
                @click="selectCell(row.index, column.index)"
              >
                {{ cellDisplay(row.index, column.index) }}
              </td>
            </template>
          </tr>
        </tbody>
      </table>
    </div>
    <el-empty v-else-if="!loading" description="尚未加载工作表" />

    <DocumentEvaluationPanel
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
import { computed, onBeforeUnmount, onMounted, ref, watch, type CSSProperties } from 'vue'
import { Download, Refresh, Upload } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import DocumentEvaluationPanel from './DocumentEvaluationPanel.vue'
import { useDocumentEvaluation } from './useDocumentEvaluation'
import {
  getWorkbookMetadata,
  getWorkbookSheet,
  getWritingDocumentSource,
  replaceWritingDocumentContent,
  updateWorkbookCells,
  type WorkbookCell,
  type WorkbookMetadata,
  type WorkbookSheet,
  type WritingProjectDocument
} from '@/api/writing'

const props = defineProps<{ projectId: string; document: WritingProjectDocument }>()
const emit = defineEmits<{ changed: [] }>()

const loading = ref(false)
const saving = ref(false)
const metadata = ref<WorkbookMetadata>()
const sheetData = ref<WorkbookSheet>()
const activeSheet = ref('')
const selectedCoordinate = ref('')
const editorValue = ref('')
const fileInput = ref<HTMLInputElement>()
const evaluation = useDocumentEvaluation(
  () => props.projectId,
  () => props.document.id
)

const cellMap = computed(() => new Map((sheetData.value?.cells || []).map(cell => [cell.coordinate, cell])))
const mergeMap = computed(() => {
  const result = new Map<string, { covered: boolean; rowspan?: number; colspan?: number }>()
  for (const range of sheetData.value?.merges || []) {
    const [start, end] = range.split(':')
    const a = decodeCoordinate(start)
    const b = decodeCoordinate(end || start)
    for (let row = a.row; row <= b.row; row += 1) {
      for (let column = a.column; column <= b.column; column += 1) {
        const key = coordinate(row, column)
        result.set(key, row === a.row && column === a.column
          ? { covered: false, rowspan: b.row - a.row + 1, colspan: b.column - a.column + 1 }
          : { covered: true })
      }
    }
  }
  return result
})

async function loadMetadata() {
  loading.value = true
  try {
    metadata.value = await getWorkbookMetadata(props.projectId, props.document.id)
    if (!metadata.value.sheets.some(row => row.name === activeSheet.value)) {
      activeSheet.value = metadata.value.sheets[0]?.name || ''
    }
    if (activeSheet.value) await loadSheet()
  } catch (error) {
    ElMessage.error(errorMessage(error, '表格加载失败'))
  } finally {
    loading.value = false
  }
}

async function loadEvaluation() {
  try {
    await evaluation.load()
  } catch (error) {
    ElMessage.error(errorMessage(error, '工作簿评价加载失败'))
  }
}

async function loadAll() {
  await Promise.all([loadMetadata(), loadEvaluation()])
}

async function loadSheet() {
  if (!activeSheet.value) return
  loading.value = true
  try {
    sheetData.value = await getWorkbookSheet(props.projectId, props.document.id, activeSheet.value)
    selectedCoordinate.value = ''
    editorValue.value = ''
  } catch (error) {
    ElMessage.error(errorMessage(error, '工作表加载失败'))
  } finally {
    loading.value = false
  }
}

function coordinate(row: number, column: number) {
  let value = ''
  let index = column
  while (index > 0) {
    index -= 1
    value = String.fromCharCode(65 + (index % 26)) + value
    index = Math.floor(index / 26)
  }
  return `${value}${row}`
}

function decodeCoordinate(value: string) {
  const match = /^([A-Z]+)(\d+)$/.exec(value.toUpperCase())
  if (!match) return { row: 1, column: 1 }
  let column = 0
  for (const character of match[1]) column = column * 26 + character.charCodeAt(0) - 64
  return { row: Number(match[2]), column }
}

function cellAt(row: number, column: number): WorkbookCell | undefined {
  return cellMap.value.get(coordinate(row, column))
}

function cellDisplay(row: number, column: number) {
  const cell = cellAt(row, column)
  const value = cell?.display ?? cell?.value ?? ''
  return typeof value === 'boolean' ? (value ? 'TRUE' : 'FALSE') : String(value)
}

function mergeInfo(row: number, column: number) {
  return mergeMap.value.get(coordinate(row, column)) || { covered: false, rowspan: 1, colspan: 1 }
}

function cellStyle(row: number, column: number): CSSProperties {
  const style = cellAt(row, column)?.style
  if (!style) return {}
  return {
    fontWeight: style.bold ? '700' : '400',
    fontStyle: style.italic ? 'italic' : 'normal',
    textAlign: (style.horizontal || 'left') as CSSProperties['textAlign'],
    verticalAlign: (style.vertical || 'middle') as CSSProperties['verticalAlign'],
    backgroundColor: /^FF[0-9A-F]{6}$/i.test(style.fill || '') ? `#${style.fill.slice(2)}` : undefined
  }
}

function selectCell(row: number, column: number) {
  selectedCoordinate.value = coordinate(row, column)
  const cell = cellAt(row, column)
  editorValue.value = String(cell?.formula || (cell?.value ?? ''))
}

async function saveCell() {
  if (!selectedCoordinate.value || !sheetData.value) return
  saving.value = true
  try {
    await updateWorkbookCells(props.projectId, props.document.id, activeSheet.value, {
      cells: [{ coordinate: selectedCoordinate.value, value: editorValue.value }],
      expected_revision: sheetData.value.revision,
      actor: 'admin'
    })
    ElMessage.success(`${selectedCoordinate.value} 已保存并生成新版本`)
    await loadAll()
    emit('changed')
  } catch (error) {
    ElMessage.error(errorMessage(error, '单元格保存失败'))
  } finally {
    saving.value = false
  }
}

async function handleFile(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  loading.value = true
  try {
    await replaceWritingDocumentContent(props.projectId, props.document.id, file)
    ElMessage.success('XLSX 已替换并生成新版本')
    await loadAll()
    emit('changed')
  } catch (error) {
    ElMessage.error(errorMessage(error, 'XLSX 替换失败'))
  } finally {
    target.value = ''
    loading.value = false
  }
}

async function downloadSource() {
  try {
    const blob = await getWritingDocumentSource(props.projectId, props.document.id)
    downloadBlob(blob, `${props.document.title}.xlsx`)
  } catch (error) {
    ElMessage.error(errorMessage(error, '表格下载失败'))
  }
}

function downloadBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = name
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

function formatNumber(value?: number) {
  return new Intl.NumberFormat('zh-CN').format(value || 0)
}

function errorMessage(error: unknown, fallback: string) {
  return (error as any)?.response?.data?.detail || fallback
}

watch(() => props.document.id, loadAll)
onMounted(loadAll)
onBeforeUnmount(evaluation.dispose)
</script>

<style scoped>
.workbook-workspace { display: grid; gap: 12px; min-width: 0; }
.workbook-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.workbook-head h3 { margin: 4px 0 0; color: var(--text-primary); font-size: 18px; }
.workbook-head p { margin: 6px 0 0; color: var(--text-secondary); font-size: 11px; }
.eyebrow { color: var(--view-color-primary); font-size: 11px; }
.actions { display: flex; gap: 8px; }
.sheet-tabs :deep(.el-tabs__header) { margin-bottom: 0; }
.cell-editor { display: grid; grid-template-columns: 90px minmax(240px, 1fr) auto auto; gap: 8px; align-items: center; }
.cell-editor strong { color: var(--view-color-primary); font-family: ui-monospace, monospace; }
.cell-editor small { color: var(--text-secondary); white-space: nowrap; }
.grid-scroll { max-height: calc(100vh - 340px); overflow: auto; border: 1px solid var(--line-color); background: var(--card-bg); }
.sheet-grid { border-spacing: 0; border-collapse: separate; min-width: 100%; color: var(--text-primary); font-size: 11px; }
.sheet-grid th, .sheet-grid td { box-sizing: border-box; padding: 5px 7px; border-right: 1px solid var(--line-color); border-bottom: 1px solid var(--line-color); white-space: pre-wrap; }
.sheet-grid thead th { position: sticky; z-index: 3; top: 0; color: var(--text-secondary); text-align: center; background: var(--panel-bg); }
.row-number { position: sticky; z-index: 2; left: 0; width: 46px; min-width: 46px !important; color: var(--text-secondary); text-align: center; background: var(--panel-bg); }
.corner { z-index: 4 !important; top: 0; }
.sheet-grid td { cursor: cell; }
.sheet-grid td:hover, .sheet-grid td.selected { outline: 2px solid var(--view-color-primary); outline-offset: -2px; }
.sheet-grid td.formula::after { float: right; color: var(--view-color-primary); content: "ƒ"; opacity: .7; }
@media (max-width: 800px) {
  .workbook-head { flex-direction: column; }
  .cell-editor { grid-template-columns: 70px minmax(0, 1fr); }
  .cell-editor .el-button, .cell-editor small { grid-column: 2; }
}
</style>
