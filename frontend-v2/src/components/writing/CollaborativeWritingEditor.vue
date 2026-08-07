<template>
  <section class="co-writing" :class="[`mobile-${mobilePanel}`, `display-${displayMode}`]">
    <nav v-if="displayMode === 'full'" class="mobile-panels" aria-label="协同写作面板">
      <el-segmented v-model="mobilePanel" :options="mobilePanels" size="small" />
    </nav>

    <aside v-if="displayMode !== 'document'" class="ai-panel" aria-label="AI 协作面板">
      <header class="panel-heading">
        <div>
          <span>HUMAN × AI</span>
          <h3>协作写作</h3>
        </div>
        <el-tag size="small" effect="plain" :type="jobStatus === 'failed' ? 'danger' : 'info'">
          {{ jobStatusLabel }}
        </el-tag>
      </header>

      <div class="ai-config">
        <label>
          <span>协作智能体</span>
          <el-select v-model="agentId" placeholder="选择智能体" :disabled="jobBusy">
            <el-option v-for="agent in agents" :key="agent.id" :label="agent.name" :value="agent.id">
              <span>{{ agent.name }}</span>
              <small v-if="agent.model">{{ agent.model }}</small>
            </el-option>
          </el-select>
        </label>

        <label>
          <span>作用范围</span>
          <el-segmented v-model="scope" :options="scopeOptions" size="small" />
        </label>

        <div class="selection-context">
          <span>{{ scopeContextLabel }}</span>
          <small>{{ scopeContextDetail }}</small>
        </div>
      </div>

      <div class="quick-actions" aria-label="AI 快捷操作">
        <button v-for="action in quickActions" :key="action.label" type="button" @click="applyQuickAction(action.instruction)">
          <el-icon><MagicStick /></el-icon>
          <span>{{ action.label }}</span>
        </button>
      </div>

      <section class="artifact-list" aria-label="图表公式清单">
        <header>
          <span>图表公式</span>
          <button type="button" @click="renumberArtifacts()">重排编号</button>
        </header>
        <div class="artifact-counts">
          <small>图 {{ artifactCounts.figure }}</small>
          <small>表 {{ artifactCounts.table }}</small>
          <small>式 {{ artifactCounts.equation }}</small>
        </div>
        <ul v-if="artifactRows.length">
          <li v-for="artifact in artifactRows" :key="`${artifact.kind}-${artifact.index}`">
            <div>
              <strong>{{ artifact.label }}</strong>
              <span>{{ artifact.title || artifact.fallback }}</span>
              <small v-if="artifact.sourceLabel">{{ artifact.sourceLabel }}</small>
            </div>
            <button type="button" @click="insertArtifactReference(artifact)">引用</button>
          </li>
        </ul>
        <el-empty v-else description="暂无图表公式" :image-size="40" />
      </section>

      <label class="instruction-box">
        <span>写作指令</span>
        <el-input
          v-model="instruction"
          type="textarea"
          :rows="5"
          resize="none"
          placeholder="说明目标、语气、证据边界和必须保留的内容……"
          @keydown.meta.enter.prevent="runAiJob"
          @keydown.ctrl.enter.prevent="runAiJob"
        />
      </label>
      <el-button
        class="run-ai"
        type="primary"
        :icon="MagicStick"
        :loading="jobBusy"
        :disabled="!canRunAi"
        @click="runAiJob"
      >
        生成修改建议
      </el-button>

      <section class="proposal-list" aria-live="polite">
        <header>
          <span>待审建议</span>
          <small>{{ pendingProposals.length }} 条</small>
        </header>
        <article v-for="proposal in pendingProposals" :key="proposal.id" class="proposal-card">
          <div class="proposal-meta">
            <el-tag size="small" effect="plain">{{ scopeLabel(proposal.scope) }}</el-tag>
            <small>{{ proposal.created_at ? formatTime(proposal.created_at) : '刚刚' }}</small>
          </div>
          <strong>{{ proposal.title || proposal.summary || 'AI 修改建议' }}</strong>
          <p v-if="proposal.rationale">{{ proposal.rationale }}</p>
          <div class="proposal-actions">
            <el-button size="small" :icon="Close" @click="rejectProposal(proposal.id)">拒绝</el-button>
            <el-button
              v-if="proposal.requires_rebase"
              size="small"
              type="primary"
              :icon="MagicStick"
              @click="rebaseProposal(proposal)"
            >基于当前重写</el-button>
            <el-button v-else size="small" type="primary" :icon="Check" @click="acceptProposal(proposal.id)">接受</el-button>
          </div>
        </article>
        <el-empty v-if="!pendingProposals.length" description="同段冲突会在这里等待人工处理" :image-size="48" />
      </section>
    </aside>

    <section v-if="displayMode !== 'ai'" class="document-workbench">
      <header class="editor-toolbar" aria-label="富文本工具栏">
        <div class="toolbar-group">
          <el-tooltip content="撤销" placement="bottom"><button type="button" aria-label="撤销" :disabled="!editor?.can().undo()" @click="editor?.chain().focus().undo().run()"><el-icon><Back /></el-icon></button></el-tooltip>
          <el-tooltip content="重做" placement="bottom"><button type="button" aria-label="重做" :disabled="!editor?.can().redo()" @click="editor?.chain().focus().redo().run()"><el-icon><Right /></el-icon></button></el-tooltip>
        </div>
        <div class="toolbar-group">
          <el-tooltip content="正文" placement="bottom"><button type="button" aria-label="正文" :class="{ active: editor?.isActive('paragraph') }" @click="editor?.chain().focus().setParagraph().run()"><el-icon><Document /></el-icon></button></el-tooltip>
          <el-tooltip content="一级标题" placement="bottom"><button type="button" aria-label="一级标题" :class="{ active: editor?.isActive('heading', { level: 1 }) }" @click="editor?.chain().focus().toggleHeading({ level: 1 }).run()"><span>H1</span></button></el-tooltip>
          <el-tooltip content="二级标题" placement="bottom"><button type="button" aria-label="二级标题" :class="{ active: editor?.isActive('heading', { level: 2 }) }" @click="editor?.chain().focus().toggleHeading({ level: 2 }).run()"><span>H2</span></button></el-tooltip>
        </div>
        <div class="toolbar-group">
          <el-tooltip content="加粗" placement="bottom"><button type="button" aria-label="加粗" :class="{ active: editor?.isActive('bold') }" @click="editor?.chain().focus().toggleBold().run()"><strong>B</strong></button></el-tooltip>
          <el-tooltip content="斜体" placement="bottom"><button type="button" aria-label="斜体" :class="{ active: editor?.isActive('italic') }" @click="editor?.chain().focus().toggleItalic().run()"><em>I</em></button></el-tooltip>
          <el-tooltip content="下划线" placement="bottom"><button type="button" aria-label="下划线" :class="{ active: editor?.isActive('underline') }" @click="editor?.chain().focus().toggleUnderline().run()"><u>U</u></button></el-tooltip>
          <el-tooltip content="删除线" placement="bottom"><button type="button" aria-label="删除线" :class="{ active: editor?.isActive('strike') }" @click="editor?.chain().focus().toggleStrike().run()"><s>S</s></button></el-tooltip>
        </div>
        <div class="toolbar-group">
          <el-tooltip content="项目符号" placement="bottom"><button type="button" aria-label="项目符号" :class="{ active: editor?.isActive('bulletList') }" @click="editor?.chain().focus().toggleBulletList().run()"><el-icon><List /></el-icon></button></el-tooltip>
          <el-tooltip content="编号列表" placement="bottom"><button type="button" aria-label="编号列表" :class="{ active: editor?.isActive('orderedList') }" @click="editor?.chain().focus().toggleOrderedList().run()"><el-icon><Sort /></el-icon></button></el-tooltip>
          <el-tooltip content="引用" placement="bottom"><button type="button" aria-label="引用" :class="{ active: editor?.isActive('blockquote') }" @click="editor?.chain().focus().toggleBlockquote().run()"><el-icon><ChatLineSquare /></el-icon></button></el-tooltip>
          <el-tooltip content="插入表格" placement="bottom"><button type="button" aria-label="插入表格" @click="insertTable"><el-icon><Grid /></el-icon></button></el-tooltip>
          <el-tooltip content="插入图片" placement="bottom"><button type="button" aria-label="插入图片" @click="insertImage"><el-icon><Picture /></el-icon></button></el-tooltip>
          <el-tooltip content="上传图片" placement="bottom"><button type="button" aria-label="上传图片" :disabled="assetUploading" @click="assetInput?.click()"><el-icon><Upload /></el-icon></button></el-tooltip>
          <el-tooltip content="插入公式" placement="bottom"><button type="button" aria-label="插入公式" @click="insertFormula"><span>Σ</span></button></el-tooltip>
          <el-tooltip content="重排图表公式编号" placement="bottom"><button type="button" aria-label="重排图表公式编号" @click="renumberArtifacts()"><el-icon><Refresh /></el-icon></button></el-tooltip>
        </div>
        <div v-if="editor?.isActive('table')" class="toolbar-group table-tools">
          <el-tooltip content="左侧插入列" placement="bottom"><button type="button" aria-label="左侧插入列" @click="editor?.chain().focus().addColumnBefore().run()"><span>+列</span></button></el-tooltip>
          <el-tooltip content="下方插入行" placement="bottom"><button type="button" aria-label="下方插入行" @click="editor?.chain().focus().addRowAfter().run()"><span>+行</span></button></el-tooltip>
          <el-tooltip content="删除列" placement="bottom"><button type="button" aria-label="删除列" @click="editor?.chain().focus().deleteColumn().run()"><span>-列</span></button></el-tooltip>
          <el-tooltip content="删除行" placement="bottom"><button type="button" aria-label="删除行" @click="editor?.chain().focus().deleteRow().run()"><span>-行</span></button></el-tooltip>
          <el-tooltip content="删除表格" placement="bottom"><button type="button" aria-label="删除表格" @click="editor?.chain().focus().deleteTable().run()"><span>×</span></button></el-tooltip>
        </div>
        <div class="toolbar-group align-tools">
          <el-tooltip content="左对齐" placement="bottom"><button type="button" aria-label="左对齐" :class="{ active: editor?.isActive({ textAlign: 'left' }) }" @click="editor?.chain().focus().setTextAlign('left').run()"><el-icon><DArrowLeft /></el-icon></button></el-tooltip>
          <el-tooltip content="居中" placement="bottom"><button type="button" aria-label="居中" :class="{ active: editor?.isActive({ textAlign: 'center' }) }" @click="editor?.chain().focus().setTextAlign('center').run()"><el-icon><Rank /></el-icon></button></el-tooltip>
        </div>
        <div class="save-tools">
          <span class="save-state" :class="`is-${saveState}`"><i />{{ saveStateLabel }}</span>
          <el-tooltip content="保存版本快照" placement="bottom">
            <button type="button" aria-label="保存版本快照" :disabled="saveState === 'saving'" @click="saveVersion"><el-icon><Clock /></el-icon></button>
          </el-tooltip>
        </div>
      </header>
      <input
        ref="assetInput"
        class="asset-input"
        type="file"
        accept="image/png,image/jpeg,image/webp,image/gif,image/svg+xml"
        @change="uploadImageAsset"
      />

      <div class="document-stage">
        <aside class="embedded-outline" :class="{ collapsed: outlineCollapsed }">
          <button class="outline-collapse" type="button" :aria-label="outlineCollapsed ? '展开目录' : '收起目录'" @click="outlineCollapsed = !outlineCollapsed">
            <el-icon><component :is="outlineCollapsed ? Expand : Fold" /></el-icon>
          </button>
          <DocumentOutlineTree
            v-if="!outlineCollapsed"
            :nodes="outline"
            :project-id="projectId"
            :document-id="documentId"
            :selected-node-id="selectedNodeId"
            @select="emit('select-outline', $event)"
          />
        </aside>

        <main class="paper-scroll" :aria-busy="loading">
          <el-skeleton v-if="loading" :rows="14" animated />
          <el-empty v-else-if="initializationRequired" class="initialization-empty" description="该文档尚未切换到结构化正文">
            <el-button type="primary" :loading="initializing" @click="initializeCollaboration">启用人机双写</el-button>
          </el-empty>
          <div v-else class="paper-page">
            <header class="paper-header">
              <span>{{ documentTitle || '工作文档' }}</span>
              <small>修订 {{ revision }}</small>
            </header>
            <EditorContent :editor="editor" class="rich-editor" />
          </div>
        </main>
      </div>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Extension, Node, type JSONContent } from '@tiptap/core'
import Image from '@tiptap/extension-image'
import Placeholder from '@tiptap/extension-placeholder'
import { TableKit } from '@tiptap/extension-table'
import TextAlign from '@tiptap/extension-text-align'
import StarterKit from '@tiptap/starter-kit'
import { EditorContent, useEditor } from '@tiptap/vue-3'
import {
    Back, Check, ChatLineSquare, Clock, Close, DArrowLeft, Document, Expand, Fold,
  Grid, List, MagicStick, Picture, Rank, Refresh, Right, Sort, Upload
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import DocumentOutlineTree from '@/components/writing/DocumentOutlineTree.vue'
import {
  acceptWritingProposal,
  createWritingAiJob,
  createWritingVersion,
  getDocumentWritingAsset,
  getWritingAiJob,
  getWritingCollaboration,
  initializeWritingCollaboration,
  patchWritingCollaborationDraft,
  rejectWritingProposal,
  uploadDocumentWritingAsset,
  type WritingAiJob,
  type WritingCollaborationAgent,
  type WritingCollaborationState,
  type WritingDirectoryNode,
  type WritingProposal
} from '@/api/writing'

const props = defineProps<{
  projectId: string
  documentId: string
  documentTitle?: string
  sectionId: string
  outline: WritingDirectoryNode[]
  selectedNodeId?: string
  displayMode?: 'full' | 'document' | 'ai'
}>()

const emit = defineEmits<{
  saved: []
  'proposal-applied': []
  'select-outline': [node: WritingDirectoryNode]
}>()

const displayMode = computed(() => props.displayMode || 'full')

const StableBlockAttrs = Extension.create({
  name: 'stableBlockAttrs',
  addGlobalAttributes() {
    return [{
      types: [
        'paragraph', 'heading', 'blockquote', 'bulletList', 'orderedList',
        'codeBlock', 'horizontalRule', 'image', 'table', 'rawMarkdown'
      ],
      attributes: {
        blockId: {
          default: null,
          parseHTML: element => element.getAttribute('data-block-id'),
          renderHTML: attributes => attributes.blockId ? { 'data-block-id': attributes.blockId } : {}
        },
        blockRevision: {
          default: null,
          parseHTML: element => {
            const value = element.getAttribute('data-block-revision')
            return value == null ? null : Number(value)
          },
          renderHTML: attributes => attributes.blockRevision == null
            ? {}
            : { 'data-block-revision': String(attributes.blockRevision) }
        },
        artifactKind: {
          default: null,
          parseHTML: element => element.getAttribute('data-artifact-kind'),
          renderHTML: attributes => attributes.artifactKind
            ? {
                'data-artifact-kind': attributes.artifactKind,
                class: `artifact-${attributes.artifactKind}`
              }
            : {}
        },
        artifactLabel: {
          default: null,
          parseHTML: element => element.getAttribute('data-artifact-label'),
          renderHTML: attributes => attributes.artifactLabel
            ? { 'data-artifact-label': attributes.artifactLabel }
            : {}
        },
        artifactTitle: {
          default: null,
          parseHTML: element => element.getAttribute('data-artifact-title'),
          renderHTML: attributes => attributes.artifactTitle
            ? { 'data-artifact-title': attributes.artifactTitle }
            : {}
        }
      }
    }]
  }
})

const RawMarkdown = Node.create({
  name: 'rawMarkdown',
  group: 'block',
  atom: true,
  selectable: true,
  addAttributes() {
    return {
      markdown: { default: '' },
      blockId: { default: null },
      blockRevision: { default: 1 }
    }
  },
  parseHTML() {
    return [{ tag: 'pre[data-raw-markdown]' }]
  },
  renderHTML({ node, HTMLAttributes }) {
    const markdown = String(node.attrs.markdown || '')
    const isMath = markdown.trimStart().startsWith('$$')
    const formula = isMath
      ? markdown.replace(/^\s*\$\$\s*/, '').replace(/\s*\$\$\s*$/, '').trim()
      : markdown
    return [
      'pre',
      {
        ...HTMLAttributes,
        'data-raw-markdown': '',
        class: isMath ? 'raw-markdown-block math-block' : 'raw-markdown-block'
      },
      isMath
        ? ['span', { class: 'math-preview' }, formula]
        : ['code', {}, markdown]
    ]
  }
})

function isProjectAssetPath(src: string) {
  const value = src.trim()
  return Boolean(value && !/^https?:\/\//i.test(value) && !/^blob:|^data:/i.test(value) && !value.startsWith('/'))
}

const AssetImage = Image.extend({
  renderHTML({ HTMLAttributes }) {
    const src = String(HTMLAttributes.src || '')
    return [
      'img',
      {
        ...HTMLAttributes,
        ...(isProjectAssetPath(src) ? { 'data-asset-src': src } : {})
      }
    ]
  }
})

const loading = ref(true)
const revision = ref(0)
const canonicalSectionId = ref('')
const agents = ref<WritingCollaborationAgent[]>([])
const proposals = ref<WritingProposal[]>([])
const agentId = ref('')
const scope = ref<'selection' | 'block' | 'section' | 'document'>('section')
const instruction = ref('')
const saveState = ref<'saved' | 'dirty' | 'saving' | 'error'>('saved')
const jobStatus = ref('idle')
const activeJobId = ref('')
const outlineCollapsed = ref(false)
const mobilePanel = ref('document')
const suppressUpdate = ref(false)
const initializationRequired = ref(false)
const initializing = ref(false)
const selectionRevision = ref(0)
const artifactRevision = ref(0)
const assetInput = ref<HTMLInputElement>()
const assetUploading = ref(false)
const assetPreviewMissing = ref(new Set<string>())
const assetPreviewUrls = new Map<string, string>()
let assetPreviewRefresh: Promise<void> | undefined
let lastSavedJson = ''
let saveTimer: ReturnType<typeof setTimeout> | undefined
let hardFlushTimer: ReturnType<typeof setInterval> | undefined
let jobPollTimer: ReturnType<typeof setTimeout> | undefined
let saveQueued = false
let saveInFlight = false
let savePromise: Promise<void> | undefined
let lastSavedDocument: JSONContent = { type: 'doc', content: [] }
let latestDocument: JSONContent = { type: 'doc', content: [{ type: 'paragraph' }] }
let isUnmounting = false

const editor = useEditor({
  extensions: [
    StarterKit,
    AssetImage.configure({ inline: false, allowBase64: false }),
    TableKit,
    RawMarkdown,
    TextAlign.configure({ types: ['heading', 'paragraph'] }),
    Placeholder.configure({ placeholder: '从这里开始写作，或在左侧邀请 AI 提出修改建议……' }),
    StableBlockAttrs
  ],
  content: { type: 'doc', content: [{ type: 'paragraph' }] },
  editorProps: { attributes: { 'aria-label': '协同富文本编辑器', spellcheck: 'true' } },
  onUpdate: ({ editor: activeEditor }) => {
    if (suppressUpdate.value) return
    artifactRevision.value += 1
    latestDocument = normaliseDocument(activeEditor.getJSON())
    void refreshAssetPreviews()
    const serialized = JSON.stringify(latestDocument)
    if (serialized === lastSavedJson) return
    saveState.value = 'dirty'
    if (saveInFlight) saveQueued = true
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => flushDraft(), 1000)
  },
  onSelectionUpdate: () => { selectionRevision.value += 1 }
})

const mobilePanels = [
  { label: 'AI 协作', value: 'ai' },
  { label: '文档', value: 'document' },
  { label: '大纲', value: 'outline' }
]
const scopeOptions = [
  { label: '选区', value: 'selection' },
  { label: '段落', value: 'block' },
  { label: '章节', value: 'section' },
  { label: '全文', value: 'document' }
]
const quickActions = [
  { label: '续写', instruction: '延续当前论述续写，保持术语、语气和证据边界一致。' },
  { label: '学术润色', instruction: '润色为严谨、简洁的学术表达，不新增无法核验的事实。' },
  { label: '压缩', instruction: '压缩冗余表达，保留论点、证据与限定条件。' },
  { label: '扩写论证', instruction: '补强论证链条，明确前提、推理和结论，不虚构证据。' }
]

const pendingProposals = computed(() => proposals.value.filter(item => item.status === 'pending' || !item.status))
const activeSectionId = computed(() => canonicalSectionId.value || props.sectionId)
const jobBusy = computed(() => ['queued', 'running'].includes(jobStatus.value))
const canRunAi = computed(() => Boolean(agentId.value && instruction.value.trim() && !jobBusy.value))
const saveStateLabel = computed(() => ({ saved: '已保存', dirty: '待保存', saving: '保存中', error: '保存失败' })[saveState.value])
const jobStatusLabel = computed(() => ({
  idle: '就绪', queued: '已排队', running: '生成中', applied: '已自动合并',
  partially_applied: '部分合并', conflicted: '待审阅', failed: '任务失败', cancelled: '已取消'
} as Record<string, string>)[jobStatus.value] || jobStatus.value)
const currentSelection = computed(() => {
  void selectionRevision.value
  if (!editor.value) return { from: 0, to: 0, text: '' }
  const { from, to } = editor.value.state.selection
  return { from, to, text: editor.value.state.doc.textBetween(from, to, ' ') }
})
const currentBlock = computed(() => {
  void selectionRevision.value
  const position = editor.value?.state.selection.$from
  if (!position) return { id: undefined, revision: undefined }
  for (let depth = position.depth; depth >= 0; depth -= 1) {
    const attrs = position.node(depth).attrs || {}
    if (attrs.blockId) {
      return { id: attrs.blockId as string, revision: attrs.blockRevision as number | undefined }
    }
  }
  return { id: undefined, revision: undefined }
})
const scopeContextLabel = computed(() => ({ selection: '当前选区', block: '当前段落', section: '当前章节', document: '整篇文档' })[scope.value])
const scopeContextDetail = computed(() => {
  if (scope.value === 'selection') return currentSelection.value.text || '请先在正文中选择文字'
  if (scope.value === 'block') return currentBlock.value.id ? `块 ${currentBlock.value.id}` : '当前光标所在段落'
  if (scope.value === 'section') return props.sectionId || '当前章节'
  return props.documentTitle || '当前文档'
})
const artifactRows = computed(() => {
  void artifactRevision.value
  return collectArtifacts(editor.value ? normaliseDocument(editor.value.getJSON()) : latestDocument)
})
const artifactCounts = computed(() => artifactRows.value.reduce((counts, item) => {
  counts[item.kind] += 1
  return counts
}, { figure: 0, table: 0, equation: 0 } as Record<'figure' | 'table' | 'equation', number>))

interface CollaborativeWritingExportPreflightIssue {
  severity: 'blocker' | 'warning'
  message: string
}

interface CollaborativeWritingExportPreflightResult {
  ok: boolean
  issues: CollaborativeWritingExportPreflightIssue[]
  revision: number
}

function stateContent(state: WritingCollaborationState): JSONContent {
  return (state.document || state.draft?.document || state.draft?.content || state.content || {
    type: 'doc', content: [{ type: 'paragraph' }]
  }) as JSONContent
}

function cloneDocument(document: JSONContent): JSONContent {
  return JSON.parse(JSON.stringify(document)) as JSONContent
}

function blockId(node: JSONContent) {
  return String(node.attrs?.blockId || '')
}

function blockRevision(node: JSONContent) {
  return Number(node.attrs?.blockRevision || 1)
}

function newBlockId() {
  return `block-${globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`}`
}

function artifactLabel(kind: 'figure' | 'table' | 'equation') {
  const labels: Record<typeof kind, string> = { figure: '图', table: '表', equation: '式' }
  const count = (latestDocument.content || [])
    .filter(node => node.attrs?.artifactKind === kind)
    .length + 1
  return `${labels[kind]} ${count}`
}

function captionParagraph(kind: 'figure' | 'table', label: string, title: string): JSONContent {
  return {
    type: 'paragraph',
    attrs: { artifactKind: `${kind}-caption`, artifactLabel: label, artifactTitle: title },
    content: [{ type: 'text', text: title ? `${label} ${title}` : label }]
  }
}

function collectArtifacts(document: JSONContent) {
  const rows: Array<{
    kind: 'figure' | 'table' | 'equation'
    index: number
    label: string
    title: string
    fallback: string
    sourceLabel?: string
  }> = []
  ;(document.content || []).forEach((node, index) => {
    const kind = node.attrs?.artifactKind
    if (kind === 'figure' || kind === 'table' || kind === 'equation') {
      rows.push({
        kind,
        index,
        label: String(node.attrs?.artifactLabel || ''),
        title: String(node.attrs?.artifactTitle || ''),
        fallback: kind === 'figure' ? '图片' : kind === 'table' ? '表格' : '公式',
        sourceLabel: kind === 'figure' ? figureSourceLabel(String(node.attrs?.src || '')) : undefined
      })
    }
  })
  return rows
}

function figureSourceLabel(src: string) {
  if (!src.trim()) return '缺少图片地址'
  if (/^https?:\/\//i.test(src)) return '网络图片'
  if (/^blob:|^data:/i.test(src)) return '临时图片'
  if (assetPreviewMissing.value.has(src)) return '缺失资产'
  return '项目资产'
}

function collectProjectAssetPaths(document: JSONContent) {
  return Array.from(new Set((document.content || [])
    .filter(node => node.type === 'image')
    .map(node => String(node.attrs?.src || '').trim())
    .filter(isProjectAssetPath)))
}

async function refreshAssetPreviews() {
  if (assetPreviewRefresh) return assetPreviewRefresh
  assetPreviewRefresh = (async () => {
    const paths = collectProjectAssetPaths(latestDocument)
    const missing = new Set(assetPreviewMissing.value)
    await Promise.all(paths.map(async path => {
      if (assetPreviewUrls.has(path) || missing.has(path)) return
      try {
        const blob = await getDocumentWritingAsset(props.projectId, props.documentId, path)
        assetPreviewUrls.set(path, URL.createObjectURL(blob))
      } catch {
        missing.add(path)
      }
    }))
    assetPreviewMissing.value = missing
    await nextTick()
    const root = editor.value?.view.dom
    if (!root) return
    root.querySelectorAll<HTMLImageElement>('img[data-asset-src]').forEach(image => {
      const path = image.dataset.assetSrc || ''
      const preview = assetPreviewUrls.get(path)
      if (preview && image.src !== preview) image.src = preview
      if (missing.has(path)) image.classList.add('asset-missing')
      else image.classList.remove('asset-missing')
    })
    artifactRevision.value += 1
  })().finally(() => { assetPreviewRefresh = undefined })
  return assetPreviewRefresh
}

function resetAssetPreviews() {
  assetPreviewUrls.forEach(url => URL.revokeObjectURL(url))
  assetPreviewUrls.clear()
  assetPreviewMissing.value = new Set()
}

function titleFromCaption(node: JSONContent | undefined, fallback = '') {
  const text = node?.content?.map(item => item.text || '').join('') || ''
  return text.replace(/^(图|表)\s*\d+\s*/, '').trim() || fallback
}

function renumberedArtifacts(document: JSONContent) {
  const value = cloneDocument(document)
  const counters = { figure: 0, table: 0, equation: 0 }
  const content = value.content || []
  content.forEach((node, index) => {
    const kind = node.attrs?.artifactKind as 'figure' | 'table' | 'equation' | string | undefined
    if (kind === 'figure' || kind === 'table' || kind === 'equation') {
      counters[kind] += 1
      const prefix = kind === 'figure' ? '图' : kind === 'table' ? '表' : '式'
      const label = `${prefix} ${counters[kind]}`
      const next = content[index + 1]
      const title = kind === 'figure'
        ? titleFromCaption(next, node.attrs?.artifactTitle || node.attrs?.title || node.attrs?.alt || '')
        : kind === 'table'
          ? titleFromCaption(content[index - 1], node.attrs?.artifactTitle || '')
          : String(node.attrs?.artifactTitle || '')
      node.attrs = { ...(node.attrs || {}), artifactLabel: label, artifactTitle: title }
      if (kind === 'figure' && next?.attrs?.artifactKind === 'figure-caption') {
        next.attrs = { ...(next.attrs || {}), artifactLabel: label, artifactTitle: title }
        next.content = [{ type: 'text', text: title ? `${label} ${title}` : label }]
      }
      if (kind === 'table') {
        const previous = content[index - 1]
        if (previous?.attrs?.artifactKind === 'table-caption') {
          previous.attrs = { ...(previous.attrs || {}), artifactLabel: label, artifactTitle: title }
          previous.content = [{ type: 'text', text: title ? `${label} ${title}` : label }]
        }
      }
    }
  })
  return value
}

function normaliseDocument(document: JSONContent): JSONContent {
  const value = cloneDocument(document)
  value.type = 'doc'
  value.content = (value.content || []).map(node => ({
    ...node,
    attrs: {
      ...(node.attrs || {}),
      blockId: blockId(node) || newBlockId(),
      blockRevision: blockRevision(node)
    }
  }))
  return value
}

function semanticNode(node: JSONContent | undefined) {
  if (!node) return ''
  const value = cloneDocument(node)
  const stripDefaults = (item: JSONContent) => {
    const attrs = item.attrs
    if (attrs) {
      delete attrs.blockRevision
      Object.keys(attrs).forEach(key => {
        if (attrs[key] == null) delete attrs[key]
      })
    }
    ;(item.content || []).forEach(stripDefaults)
  }
  stripDefaults(value)
  return JSON.stringify(value)
}

function draftChanges(base: JSONContent, current: JSONContent) {
  const baseRows = base.content || []
  const currentRows = current.content || []
  const baseById = new Map(baseRows.map(node => [blockId(node), node]))
  const currentIds = new Set(currentRows.map(blockId))
  const changes: Array<{
    op: 'upsert' | 'insert_after' | 'move_after' | 'delete'
    block_id: string
    expected_block_revision?: number
    after_block_id?: string
    before_block_id?: string
    node?: JSONContent
  }> = []
  currentRows.forEach((node, index) => {
    const id = blockId(node)
    const saved = baseById.get(id)
    if (saved && semanticNode(saved) !== semanticNode(node)) {
      changes.push({ op: 'upsert', block_id: id, expected_block_revision: blockRevision(saved), node })
    } else if (!saved) {
      const previous = currentRows[index - 1]
      const next = currentRows.slice(index + 1).find(row => baseById.has(blockId(row)))
      changes.push({
        op: 'insert_after',
        block_id: id,
        after_block_id: previous ? blockId(previous) : '',
        before_block_id: !previous && next ? blockId(next) : '',
        node
      })
    }
  })
  baseRows.forEach(node => {
    const id = blockId(node)
    if (!currentIds.has(id)) {
      changes.push({ op: 'delete', block_id: id, expected_block_revision: blockRevision(node) })
    }
  })
  const baseExistingOrder = baseRows.map(blockId).filter(id => currentIds.has(id))
  const desiredExistingOrder = currentRows.map(blockId).filter(id => baseById.has(id))
  if (JSON.stringify(baseExistingOrder) !== JSON.stringify(desiredExistingOrder)) {
    let previousId = ''
    currentRows.forEach(node => {
      const id = blockId(node)
      const saved = baseById.get(id)
      const changedInRequest = Boolean(saved && semanticNode(saved) !== semanticNode(node))
      changes.push({
        op: 'move_after',
        block_id: id,
        expected_block_revision: saved
          ? blockRevision(saved) + (changedInRequest ? 1 : 0)
          : 1,
        after_block_id: previousId
      })
      previousId = id
    })
  }
  return changes
}

function reconcileDocuments(local: JSONContent, sent: JSONContent, server: JSONContent) {
  const sentById = new Map((sent.content || []).map(node => [blockId(node), node]))
  const serverById = new Map((server.content || []).map(node => [blockId(node), node]))
  const localIds = new Set((local.content || []).map(blockId))
  const merged: JSONContent[] = []
  const included = new Set<string>()
  ;(local.content || []).forEach(localNode => {
    const id = blockId(localNode)
    const sentNode = sentById.get(id)
    const serverNode = serverById.get(id)
    if (!serverNode) {
      if (!sentNode || semanticNode(localNode) !== semanticNode(sentNode)) merged.push(localNode)
      return
    }
    if (!sentNode || semanticNode(localNode) === semanticNode(sentNode)) {
      merged.push(serverNode)
    } else if (semanticNode(serverNode) === semanticNode(sentNode)) {
      merged.push({
        ...localNode,
        attrs: { ...(localNode.attrs || {}), blockRevision: blockRevision(serverNode) }
      })
    } else {
      merged.push(localNode)
    }
    included.add(id)
  })
  ;(server.content || []).forEach(node => {
    const id = blockId(node)
    const pendingLocalDeletion = sentById.has(id) && !localIds.has(id)
    if (!included.has(id) && !pendingLocalDeletion) merged.push(node)
  })
  return { type: 'doc', attrs: cloneDocument(server).attrs, content: merged } as JSONContent
}

function applyState(state: WritingCollaborationState, replaceContent = true) {
  revision.value = state.revision ?? state.draft?.revision ?? revision.value
  canonicalSectionId.value = state.section?.id || canonicalSectionId.value || props.sectionId
  agents.value = state.agents || agents.value
  proposals.value = state.proposals || proposals.value
  if (!agentId.value || !agents.value.some(agent => agent.id === agentId.value)) {
    agentId.value = agents.value.find(agent => agent.available !== false)?.id || ''
  }
  if (replaceContent && editor.value) {
    const content = normaliseDocument(stateContent(state))
    try {
      editor.value.schema.nodeFromJSON(content)
      suppressUpdate.value = true
      editor.value.commands.setContent(content, { emitUpdate: false, errorOnInvalidContent: true })
      latestDocument = normaliseDocument(editor.value.getJSON())
      lastSavedDocument = cloneDocument(content)
      lastSavedJson = JSON.stringify(latestDocument)
      saveState.value = 'saved'
      artifactRevision.value += 1
      void refreshAssetPreviews()
      initializationRequired.value = false
    } catch {
      saveState.value = 'error'
      ElMessage.error('服务器正文不符合编辑器结构，已保留当前有效内容且未写回')
    } finally {
      suppressUpdate.value = false
    }
  }
}

function mergeRemoteState(state: WritingCollaborationState, sent = lastSavedDocument) {
  if (!editor.value && !isUnmounting) return
  revision.value = state.revision ?? state.draft?.revision ?? revision.value
  canonicalSectionId.value = state.section?.id || canonicalSectionId.value || props.sectionId
  proposals.value = state.proposals || proposals.value
  const server = normaliseDocument(stateContent(state))
  const local = editor.value && !isUnmounting
    ? normaliseDocument(editor.value.getJSON())
    : normaliseDocument(latestDocument)
  const merged = reconcileDocuments(local, sent, server)
  latestDocument = cloneDocument(merged)
  if (editor.value && !isUnmounting) {
    editor.value.schema.nodeFromJSON(server)
    editor.value.schema.nodeFromJSON(merged)
    const selection = {
      from: editor.value.state.selection.from,
      to: editor.value.state.selection.to
    }
    suppressUpdate.value = true
    editor.value.commands.setContent(merged, { emitUpdate: false, errorOnInvalidContent: true })
    latestDocument = normaliseDocument(editor.value.getJSON())
    artifactRevision.value += 1
    void refreshAssetPreviews()
    const maxPosition = editor.value.state.doc.content.size
    editor.value.commands.setTextSelection({
      from: Math.min(selection.from, maxPosition),
      to: Math.min(selection.to, maxPosition)
    })
    suppressUpdate.value = false
  }
  lastSavedDocument = cloneDocument(server)
  lastSavedJson = JSON.stringify(server)
  saveState.value = JSON.stringify(merged) === JSON.stringify(server) ? 'saved' : 'dirty'
}

async function loadCollaboration() {
  loading.value = true
  canonicalSectionId.value = ''
  resetAssetPreviews()
  try {
    const state = await getWritingCollaboration(props.projectId, props.documentId, props.sectionId)
    applyState(state)
  } catch (error) {
    const message = errorMessage(error, '协同写作内容加载失败')
    initializationRequired.value = message.includes('尚未启用人机双写')
    if (!initializationRequired.value) ElMessage.error(message)
  } finally {
    loading.value = false
  }
}

async function initializeCollaboration() {
  initializing.value = true
  try {
    await initializeWritingCollaboration(props.projectId, props.documentId)
    await loadCollaboration()
    ElMessage.success('结构化正文校验通过，已启用人机双写')
  } catch (error) {
    ElMessage.error(errorMessage(error, '人机双写初始化失败'))
  } finally {
    initializing.value = false
  }
}

async function flushDraft() {
  if ((!editor.value && !isUnmounting) || saveState.value === 'saved') return
  if (saveInFlight) {
    saveQueued = true
    await savePromise
    return
  }
  if (saveTimer) clearTimeout(saveTimer)
  const editorJson = editor.value && !isUnmounting ? editor.value.getJSON() : latestDocument
  const content = normaliseDocument(editorJson)
  latestDocument = cloneDocument(content)
  if (editor.value && !isUnmounting && JSON.stringify(content) !== JSON.stringify(editorJson)) {
    suppressUpdate.value = true
    editor.value.schema.nodeFromJSON(content)
    editor.value.commands.setContent(content, { emitUpdate: false, errorOnInvalidContent: true })
    suppressUpdate.value = false
  }
  const serialized = JSON.stringify(content)
  if (serialized === lastSavedJson) {
    saveState.value = 'saved'
    return
  }
  saveInFlight = true
  saveState.value = 'saving'
  let saveFailed = false
  const sentDocument = cloneDocument(content)
  const changes = draftChanges(lastSavedDocument, sentDocument)
  if (!changes.length) {
    saveState.value = 'saved'
    saveInFlight = false
    return
  }
  savePromise = (async () => {
    try {
      const state = await patchWritingCollaborationDraft(props.projectId, props.documentId, {
        base_document_revision: revision.value,
        client_change_id: globalThis.crypto?.randomUUID?.() || `change-${Date.now()}`,
        changes,
        section_id: activeSectionId.value
      })
      mergeRemoteState(state, sentDocument)
      if (state.conflicts?.length) ElMessage.warning('部分段落已变化，未覆盖这些段落')
      emit('saved')
    } catch (error) {
      saveFailed = true
      saveState.value = 'error'
      ElMessage.error(errorMessage(error, '草稿保存失败'))
    }
  })()
  try {
    await savePromise
  } finally {
    savePromise = undefined
    saveInFlight = false
  }
  const needsAnotherSave = saveQueued
  saveQueued = false
  if (needsAnotherSave && !saveFailed) {
    saveState.value = 'dirty'
    await flushDraft()
  }
}

function applyQuickAction(value: string) {
  instruction.value = value
}

async function runAiJob() {
  if (!canRunAi.value) return
  await flushDraft()
  if (saveState.value === 'error') return
  try {
    const selection = currentSelection.value
    const block = currentBlock.value
    const job = await createWritingAiJob(props.projectId, props.documentId, {
      client_request_id: globalThis.crypto?.randomUUID?.() || `ai-${Date.now()}`,
      agent_id: agentId.value,
      scope: scope.value,
      instruction: instruction.value.trim(),
      section_id: activeSectionId.value,
      selection: scope.value === 'selection'
        ? { ...selection, block_id: block.id, block_revision: block.revision }
        : undefined,
      block_id: scope.value === 'block' ? block.id : undefined,
      block_revision: scope.value === 'block' ? block.revision : undefined
    })
    activeJobId.value = job.id
    jobStatus.value = job.status
    mergeJobProposals(job)
    if (jobBusy.value) scheduleJobPoll()
  } catch (error) {
    jobStatus.value = 'failed'
    ElMessage.error(errorMessage(error, 'AI 写作任务创建失败'))
  }
}

function mergeJobProposals(job: WritingAiJob) {
  const incoming = [...(job.proposals || []), ...(job.proposal ? [job.proposal] : [])]
  incoming.forEach(proposal => {
    const index = proposals.value.findIndex(item => item.id === proposal.id)
    if (index >= 0) proposals.value[index] = proposal
    else proposals.value.unshift(proposal)
  })
}

function scheduleJobPoll() {
  if (jobPollTimer) clearTimeout(jobPollTimer)
  jobPollTimer = setTimeout(() => pollJob(), 1200)
}

async function pollJob() {
  if (!activeJobId.value) return
  try {
    const job = await getWritingAiJob(props.projectId, props.documentId, activeJobId.value)
    jobStatus.value = job.status
    mergeJobProposals(job)
    if (['queued', 'running'].includes(job.status)) scheduleJobPoll()
    else if (job.status === 'failed') ElMessage.error(job.error || 'AI 写作任务失败')
    else if (['applied', 'partially_applied', 'conflicted'].includes(job.status)) {
      const state = await getWritingCollaboration(props.projectId, props.documentId, activeSectionId.value)
      mergeRemoteState(state)
    }
  } catch (error) {
    jobStatus.value = 'failed'
    ElMessage.error(errorMessage(error, 'AI 写作任务状态获取失败'))
  }
}

async function acceptProposal(proposalId: string) {
  await flushDraft()
  if (saveState.value === 'error') return
  try {
    const state = await acceptWritingProposal(props.projectId, props.documentId, proposalId)
    applyState(state)
    emit('saved')
    emit('proposal-applied')
    ElMessage.success('建议已接受并写入草稿')
  } catch (error) {
    ElMessage.error(errorMessage(error, '接受建议失败'))
  }
}

async function rebaseProposal(proposal: WritingProposal) {
  await flushDraft()
  if (saveState.value === 'error' || !proposal.block_id) return
  try {
    const job = await createWritingAiJob(props.projectId, props.documentId, {
      client_request_id: globalThis.crypto?.randomUUID?.() || `rebase-${Date.now()}`,
      agent_id: proposal.agent_id || agentId.value,
      scope: 'block',
      instruction: proposal.instruction || proposal.rationale || '基于当前正文重新生成该段修改建议。',
      section_id: activeSectionId.value,
      block_id: proposal.block_id
    })
    await rejectWritingProposal(props.projectId, props.documentId, proposal.id)
    proposals.value = proposals.value.filter(item => item.id !== proposal.id)
    activeJobId.value = job.id
    jobStatus.value = job.status
    if (jobBusy.value) scheduleJobPoll()
  } catch (error) {
    ElMessage.error(errorMessage(error, '重新生成建议失败'))
  }
}

async function insertTable() {
  try {
    const result = await ElMessageBox.prompt('表题（可留空自动编号）', '插入表格', {
      confirmButtonText: '插入',
      cancelButtonText: '取消',
      inputPlaceholder: '实验参数对比'
    })
    const title = result.value.trim()
    const label = artifactLabel('table')
    editor.value?.chain().focus().insertContent([
      captionParagraph('table', label, title),
      {
        type: 'table',
        attrs: { artifactKind: 'table', artifactLabel: label, artifactTitle: title },
        content: [
          {
            type: 'tableRow',
            content: [
              { type: 'tableHeader', content: [{ type: 'paragraph', content: [{ type: 'text', text: '指标' }] }] },
              { type: 'tableHeader', content: [{ type: 'paragraph', content: [{ type: 'text', text: '内容' }] }] },
              { type: 'tableHeader', content: [{ type: 'paragraph', content: [{ type: 'text', text: '说明' }] }] }
            ]
          },
          {
            type: 'tableRow',
            content: [
              { type: 'tableCell', content: [{ type: 'paragraph' }] },
              { type: 'tableCell', content: [{ type: 'paragraph' }] },
              { type: 'tableCell', content: [{ type: 'paragraph' }] }
            ]
          },
          {
            type: 'tableRow',
            content: [
              { type: 'tableCell', content: [{ type: 'paragraph' }] },
              { type: 'tableCell', content: [{ type: 'paragraph' }] },
              { type: 'tableCell', content: [{ type: 'paragraph' }] }
            ]
          }
        ]
      },
      { type: 'paragraph' }
    ]).run()
  } catch {
    // Cancelling the prompt is not an editing error.
  }
}

async function insertImage() {
  try {
    const result = await ElMessageBox.prompt('图片地址｜说明文字｜标题（后两项可省略）', '插入图片', {
      confirmButtonText: '插入',
      cancelButtonText: '取消',
      inputPlaceholder: 'assets/figure.png｜图1 系统结构｜系统结构示意图',
      inputPattern: /\S+/,
      inputErrorMessage: '图片地址不能为空'
    })
    const [src, alt = '', title = ''] = result.value.split('｜').map(row => row.trim())
    const label = artifactLabel('figure')
    editor.value?.chain().focus().insertContent([
      { type: 'image', attrs: { src, alt, title, artifactKind: 'figure', artifactLabel: label, artifactTitle: title || alt } },
      captionParagraph('figure', label, title || alt),
      { type: 'paragraph' }
    ]).run()
  } catch {
    // Cancelling the prompt is not an editing error.
  }
}

async function uploadImageAsset(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (!file.type.startsWith('image/')) {
    ElMessage.error('只能上传图片文件')
    return
  }
  assetUploading.value = true
  try {
    const uploaded = await uploadDocumentWritingAsset(props.projectId, props.documentId, file)
    const title = file.name.replace(/\.[^.]+$/, '')
    const label = artifactLabel('figure')
    editor.value?.chain().focus().insertContent([
      {
        type: 'image',
        attrs: {
          src: uploaded.path,
          alt: title,
          title,
          artifactKind: 'figure',
          artifactLabel: label,
          artifactTitle: title
        }
      },
      captionParagraph('figure', label, title),
      { type: 'paragraph' }
    ]).run()
    void refreshAssetPreviews()
    ElMessage.success('图片已上传并插入文档')
  } catch (error) {
    ElMessage.error(errorMessage(error, '图片上传失败'))
  } finally {
    assetUploading.value = false
  }
}

async function insertFormula() {
  try {
    const result = await ElMessageBox.prompt('输入 LaTeX 公式内容，不需要外层 $$', '插入公式', {
      confirmButtonText: '插入',
      cancelButtonText: '取消',
      inputType: 'textarea',
      inputPlaceholder: '\\Phi_A^{rob}(t)=\\mathbb{E}[\\widehat\\Phi_A(t)]-\\kappa\\sigma[\\widehat\\Phi_A(t)]',
      inputPattern: /\S+/,
      inputErrorMessage: '公式内容不能为空'
    })
    const formula = result.value.trim()
    const label = artifactLabel('equation')
    editor.value?.chain().focus().insertContent({
      type: 'rawMarkdown',
      attrs: { markdown: `$$\n${formula}\n$$`, artifactKind: 'equation', artifactLabel: label, artifactTitle: formula }
    }).run()
  } catch {
    // Cancelling the prompt is not an editing error.
  }
}

function renumberArtifacts(showMessage = true) {
  if (!editor.value) return
  const current = normaliseDocument(editor.value.getJSON())
  const next = normaliseDocument(renumberedArtifacts(current))
  if (JSON.stringify(current) === JSON.stringify(next)) {
    if (showMessage) ElMessage.info('图表公式编号已是最新')
    return
  }
  suppressUpdate.value = true
  editor.value.commands.setContent(next, { emitUpdate: false, errorOnInvalidContent: true })
  suppressUpdate.value = false
  latestDocument = normaliseDocument(editor.value.getJSON())
  artifactRevision.value += 1
  saveState.value = 'dirty'
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => flushDraft(), 1000)
  if (showMessage) ElMessage.success('图表公式编号已重排')
}

function insertArtifactReference(artifact: { kind: 'figure' | 'table' | 'equation'; label: string }) {
  const label = artifact.label || (artifact.kind === 'figure' ? '图' : artifact.kind === 'table' ? '表' : '式')
  editor.value?.chain().focus().insertContent(`见${label}`).run()
}

function artifactNumberingIsStale() {
  const current = normaliseDocument(editor.value ? editor.value.getJSON() : latestDocument)
  const next = normaliseDocument(renumberedArtifacts(current))
  return JSON.stringify(current) !== JSON.stringify(next)
}

async function prepareExportPreflight(): Promise<CollaborativeWritingExportPreflightResult> {
  const issues: CollaborativeWritingExportPreflightIssue[] = []
  await flushDraft()
  if (saveState.value === 'error') {
    issues.push({ severity: 'blocker', message: '当前草稿保存失败，请先处理保存错误后再导出。' })
  }

  if (artifactNumberingIsStale()) {
    renumberArtifacts(false)
    await flushDraft()
    issues.push({ severity: 'warning', message: '已自动重排图、表、公式编号并保存到结构化正文。' })
  }

  await refreshAssetPreviews()
  const missingAssets = Array.from(assetPreviewMissing.value)
  if (missingAssets.length) {
    const preview = missingAssets.slice(0, 3).join('、')
    const suffix = missingAssets.length > 3 ? ` 等 ${missingAssets.length} 个资源` : ''
    issues.push({ severity: 'blocker', message: `缺失图片资源：${preview}${suffix}。请重新上传或修正图片路径后再导出。` })
  }

  return {
    ok: !issues.some(issue => issue.severity === 'blocker'),
    issues,
    revision: revision.value
  }
}

async function rejectProposal(proposalId: string) {
  try {
    const state = await rejectWritingProposal(props.projectId, props.documentId, proposalId)
    if (state?.proposals) proposals.value = state.proposals
    else proposals.value = proposals.value.filter(item => item.id !== proposalId)
  } catch (error) {
    ElMessage.error(errorMessage(error, '拒绝建议失败'))
  }
}

async function saveVersion() {
  await flushDraft()
  try {
    await createWritingVersion(props.projectId, props.documentId, {
      name: `协同写作修订 ${revision.value}`,
      revision: revision.value
    })
    ElMessage.success('版本快照已保存')
  } catch (error) {
    ElMessage.error(errorMessage(error, '版本保存失败'))
  }
}

function scopeLabel(value?: string) {
  return ({ selection: '选区', block: '段落', section: '章节', document: '全文' } as Record<string, string>)[value || ''] || '建议'
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit' }).format(new Date(value))
}

function errorMessage(error: unknown, fallback: string) {
  const detail = (error as any)?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail?.message) return detail.message
  return fallback
}

defineExpose({ editor, flushDraft, runAiJob, renumberArtifacts, prepareExportPreflight })

watch(() => [props.projectId, props.documentId, props.sectionId], loadCollaboration)

onMounted(() => {
  loadCollaboration()
  hardFlushTimer = setInterval(() => {
    if (['dirty', 'error'].includes(saveState.value)) void flushDraft()
  }, 5000)
})

onBeforeUnmount(() => {
  if (editor.value) latestDocument = normaliseDocument(editor.value.getJSON())
  isUnmounting = true
  resetAssetPreviews()
  if (saveTimer) clearTimeout(saveTimer)
  if (hardFlushTimer) clearInterval(hardFlushTimer)
  if (jobPollTimer) clearTimeout(jobPollTimer)
  if (saveState.value === 'dirty' || saveState.value === 'error') void flushDraft()
})
</script>

<style scoped>
.co-writing { display: grid; grid-template-columns: clamp(360px, 29vw, 480px) minmax(0, 1fr); min-height: calc(100vh - 248px); border: 1px solid var(--line-color); border-radius: 7px; overflow: hidden; background: var(--card-bg); }
.co-writing.display-document, .co-writing.display-ai { grid-template-columns: minmax(0, 1fr); min-height: 100%; }
.co-writing.display-ai .ai-panel { max-height: none; border-right: 0; }
.co-writing.display-document .document-workbench { min-height: 100%; }
.mobile-panels { display: none; }
.ai-panel { display: flex; min-width: 0; max-height: calc(100vh - 248px); flex-direction: column; gap: 14px; padding: 16px; overflow-y: auto; border-right: 1px solid var(--line-color); background: color-mix(in srgb, var(--panel-bg) 92%, #101929); }
.panel-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.panel-heading span, .ai-config label > span, .instruction-box > span, .proposal-list > header span { color: var(--view-color-primary); font-size: 10px; letter-spacing: .08em; }
.panel-heading h3 { margin: 4px 0 0; color: var(--text-primary); font-size: 17px; }
.ai-config { display: grid; gap: 12px; padding: 12px; border: 1px solid var(--line-color); border-radius: 6px; background: var(--view-color-faint); }
.ai-config label, .instruction-box { display: grid; gap: 7px; }
.ai-config :deep(.el-segmented) { width: 100%; }
.ai-config :deep(.el-segmented__group) { width: 100%; }
.ai-config :deep(.el-segmented__item) { flex: 1; min-width: 0; }
.ai-config :deep(.el-select-dropdown__item) { display: flex; justify-content: space-between; }
.ai-config small { color: var(--text-secondary); }
.selection-context { display: grid; gap: 3px; padding-top: 9px; border-top: 1px solid var(--line-color); }
.selection-context span { color: var(--text-primary); font-size: 11px; }
.selection-context small { overflow: hidden; color: var(--text-secondary); font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.quick-actions { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 7px; }
.quick-actions button { display: flex; align-items: center; gap: 6px; padding: 8px 9px; border: 1px solid var(--line-color); border-radius: 5px; color: var(--text-primary); background: var(--view-color-faint); cursor: pointer; }
.quick-actions button:hover { border-color: var(--view-color-primary); color: var(--view-color-primary); }
.instruction-box :deep(textarea) { font-size: 11px; line-height: 1.6; }
.run-ai { width: 100%; }
.proposal-list { display: grid; gap: 9px; padding-top: 4px; }
.proposal-list > header, .proposal-meta, .proposal-actions { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.proposal-list > header small { color: var(--text-secondary); font-size: 10px; }
.proposal-card { display: grid; gap: 8px; padding: 11px; border: 1px solid var(--view-color-border); border-radius: 6px; background: var(--card-bg); }
.proposal-card strong { color: var(--text-primary); font-size: 12px; line-height: 1.5; }
.proposal-card p { margin: 0; color: var(--text-secondary); font-size: 10px; line-height: 1.55; }
.proposal-meta small { color: var(--text-secondary); font-size: 9px; }
.proposal-actions { justify-content: flex-end; }
.document-workbench { display: grid; grid-template-rows: auto minmax(0, 1fr); min-width: 0; background: #111720; }
.editor-toolbar { display: flex; align-items: center; gap: 5px; min-width: 0; padding: 8px 10px; overflow-x: auto; border-bottom: 1px solid var(--line-color); background: var(--panel-bg); }
.asset-input { display: none; }
.toolbar-group { display: flex; gap: 2px; padding-right: 5px; border-right: 1px solid var(--line-color); }
.toolbar-group button, .save-tools button, .outline-collapse { display: inline-grid; width: 30px; height: 30px; place-items: center; border: 0; border-radius: 4px; color: var(--text-secondary); background: transparent; cursor: pointer; }
.toolbar-group button:hover, .toolbar-group button.active, .save-tools button:hover { color: var(--view-color-primary); background: var(--view-color-faint); }
.toolbar-group button:disabled, .save-tools button:disabled { opacity: .35; cursor: not-allowed; }
.toolbar-group button span, .toolbar-group button strong, .toolbar-group button em, .toolbar-group button u, .toolbar-group button s { font-size: 11px; }
.save-tools { display: flex; align-items: center; gap: 5px; margin-left: auto; white-space: nowrap; }
.save-state { display: inline-flex; align-items: center; gap: 5px; color: var(--text-secondary); font-size: 10px; }
.save-state i { width: 6px; height: 6px; border-radius: 50%; background: #67c23a; }
.save-state.is-dirty i { background: #e6a23c; }
.save-state.is-saving i { background: var(--view-color-primary); animation: pulse 1s infinite; }
.save-state.is-error { color: #f56c6c; }
.save-state.is-error i { background: #f56c6c; }
.document-stage { display: grid; grid-template-columns: auto minmax(0, 1fr); min-height: 0; }
.embedded-outline { position: relative; width: 238px; min-width: 0; border-right: 1px solid var(--line-color); background: var(--panel-bg); transition: width .2s ease; }
.embedded-outline.collapsed { width: 38px; }
.outline-collapse { position: absolute; z-index: 2; top: 8px; right: 4px; color: var(--text-secondary); background: var(--view-color-faint); }
.embedded-outline :deep(.document-outline) { height: 100%; padding-top: 44px; border: 0; border-radius: 0; background: transparent; }
.paper-scroll { min-width: 0; max-height: calc(100vh - 300px); padding: 30px clamp(24px, 5vw, 72px) 80px; overflow: auto; background: #151c26; }
.initialization-empty { width: min(850px, 100%); min-height: 520px; margin: 0 auto; border: 1px dashed var(--line-color); background: var(--panel-bg); }
.paper-page { width: min(850px, 100%); min-height: 1120px; margin: 0 auto; color: #23272d; background: #fff; box-shadow: 0 10px 35px rgb(0 0 0 / 32%); }
.paper-header { display: flex; justify-content: space-between; gap: 12px; margin: 0 64px; padding: 24px 0 12px; border-bottom: 1px solid #e4e7ec; color: #8b929d; font-size: 10px; }
.rich-editor { min-height: 1030px; }
.rich-editor :deep(.tiptap) { min-height: 1000px; padding: 48px clamp(42px, 8vw, 90px) 96px; outline: none; font-family: "Noto Serif SC", "Songti SC", SimSun, serif; font-size: 15px; line-height: 1.95; }
.rich-editor :deep(.tiptap h1) { margin: 1.8em 0 .9em; font-size: 28px; text-align: center; }
.rich-editor :deep(.tiptap h2) { margin: 1.6em 0 .8em; font-size: 22px; }
.rich-editor :deep(.tiptap h3) { margin: 1.4em 0 .65em; font-size: 18px; }
.rich-editor :deep(.tiptap p) { margin: .8em 0; }
.rich-editor :deep(.tiptap blockquote) { margin: 1.2em 0; padding-left: 1.2em; border-left: 3px solid #9aa6b5; color: #4f5865; }
.rich-editor :deep(.tiptap table) { width: 100%; margin: 1.25em 0; border-collapse: collapse; table-layout: fixed; }
.rich-editor :deep(.tiptap th), .rich-editor :deep(.tiptap td) { min-width: 70px; padding: 7px 9px; border: 1px solid #aeb5bf; vertical-align: top; }
.rich-editor :deep(.tiptap th) { background: #f2f4f7; font-weight: 600; }
.rich-editor :deep(.tiptap img) { display: block; max-width: 100%; height: auto; margin: 1.4em auto; }
.rich-editor :deep(.tiptap img.asset-missing) { min-height: 120px; border: 1px dashed #ef4444; background: repeating-linear-gradient(45deg, #fff, #fff 10px, #fee2e2 10px, #fee2e2 20px); }
.rich-editor :deep(.tiptap p.artifact-figure-caption),
.rich-editor :deep(.tiptap p.artifact-table-caption) { margin: .35em 0 1.1em; color: #4f5865; font-size: 13px; line-height: 1.6; text-align: center; }
.rich-editor :deep(.tiptap p.artifact-table-caption) { margin: 1.1em 0 .45em; font-weight: 600; }
.rich-editor :deep(.tiptap img.artifact-figure) { margin-bottom: .35em; }
.rich-editor :deep(.tiptap pre[data-raw-markdown]) { overflow-x: auto; padding: 10px 12px; border-left: 3px solid #9aa6b5; color: #4f5865; background: #f5f6f8; white-space: pre-wrap; }
.rich-editor :deep(.tiptap pre.math-block) { position: relative; border: 1px solid #cfd6df; border-left: 3px solid #3b82f6; border-radius: 5px; color: #1f2937; background: #f8fafc; text-align: center; }
.rich-editor :deep(.tiptap pre.math-block[data-artifact-label]::after) { position: absolute; right: 12px; bottom: 8px; color: #64748b; content: "(" attr(data-artifact-label) ")"; font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace; font-size: 12px; }
.rich-editor :deep(.tiptap pre.math-block code) { font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace; font-size: 13px; line-height: 1.7; }
.rich-editor :deep(.tiptap p.is-editor-empty:first-child::before) { height: 0; float: left; color: #9ba3ae; content: attr(data-placeholder); pointer-events: none; }
.rich-editor :deep(.tiptap [data-block-id]:hover) { outline: 1px solid rgb(64 158 255 / 22%); outline-offset: 4px; }
@keyframes pulse { 50% { opacity: .35; } }
@media (max-width: 1180px) {
  .co-writing { display: block; min-height: calc(100vh - 230px); }
  .mobile-panels { display: flex; justify-content: center; padding: 8px; border-bottom: 1px solid var(--line-color); background: var(--panel-bg); }
  .mobile-panels :deep(.el-segmented) { width: min(420px, 100%); }
  .mobile-panels :deep(.el-segmented__item) { min-width: 100px; }
  .ai-panel, .document-workbench { display: none; }
  .mobile-ai .ai-panel { display: flex; max-height: calc(100vh - 290px); border-right: 0; }
  .mobile-document .document-workbench, .mobile-outline .document-workbench { display: grid; min-height: calc(100vh - 290px); }
  .mobile-outline .paper-scroll { display: none; }
  .mobile-outline .document-stage { grid-template-columns: minmax(0, 1fr); }
  .mobile-outline .embedded-outline { width: 100%; border-right: 0; }
  .mobile-outline .outline-collapse { display: none; }
  .mobile-outline .embedded-outline :deep(.document-outline) { min-height: calc(100vh - 350px); }
  .mobile-document .embedded-outline { display: none; }
  .co-writing.display-ai .ai-panel { display: flex; max-height: none; }
  .co-writing.display-document .document-workbench { display: grid; min-height: 100%; }
  .co-writing.display-document .embedded-outline { display: none; }
  .paper-scroll { max-height: calc(100vh - 340px); padding: 18px 12px 52px; }
  .align-tools { display: none; }
}
@media (max-width: 640px) {
  .editor-toolbar { padding-inline: 6px; }
  .paper-page { min-width: 0; }
  .rich-editor :deep(.tiptap) { padding: 32px 22px 64px; font-size: 14px; }
}
</style>
