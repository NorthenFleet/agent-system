<template>
  <div class="writing-page" v-loading="loading">
    <header class="writing-head">
      <div>
        <span class="eyebrow">文档撰写</span>
        <div class="title-line">
          <h2>{{ workspace?.project.name || '文档工作台' }}</h2>
          <el-tag v-if="workspace?.manifest.edition" effect="plain" size="small">{{ workspace.manifest.edition }}</el-tag>
        </div>
        <p>{{ workspace?.project.description || '研究组织、全文写作、证据管理与最终交付' }}</p>
      </div>
      <div class="head-actions">
        <el-button type="primary" :icon="Plus" @click="openProjectDialog()">新建文档</el-button>
        <el-tooltip content="刷新文档工作台" placement="bottom">
          <el-button :icon="Refresh" circle @click="refreshAll" />
        </el-tooltip>
      </div>
    </header>

    <section class="document-manager">
      <header class="manager-head">
        <div>
          <span class="eyebrow">文档项目</span>
          <h3>{{ projects.length }} 个独立文档工作区</h3>
        </div>
        <el-input v-model="projectSearch" :prefix-icon="Search" clearable placeholder="搜索文档名称、类型或负责人" />
      </header>
      <div v-if="filteredProjects.length" class="document-project-list">
        <article
          v-for="project in filteredProjects"
          :key="project.id"
          class="document-project-card"
          :class="{ active: selectedProjectId === project.id, archived: project.status === 'archived' }"
          @click="selectProject(project.id)"
        >
          <div class="project-card-main">
            <span class="document-icon"><el-icon><Document /></el-icon></span>
            <div>
              <div class="project-name-line">
                <strong>{{ project.name }}</strong>
                <el-tag size="small" :type="projectStatusType(project.status)" effect="plain">
                  {{ projectStatusLabel(project.status) }}
                </el-tag>
              </div>
              <p>{{ project.description || '暂无文档说明' }}</p>
            </div>
          </div>
          <div class="project-card-meta">
            <span>{{ project.document_spec?.document_type || '文档' }}</span>
            <span>{{ project.document_spec?.chapters?.length || 0 }} 个计划章节</span>
            <span>{{ project.owner_agent || '未分配' }}</span>
          </div>
          <el-progress :percentage="Math.round(project.progress || 0)" :stroke-width="4" :show-text="false" />
          <div class="project-card-actions">
            <el-tooltip content="编辑文档信息">
              <el-button circle text :icon="EditPen" aria-label="编辑文档信息" @click.stop="openProjectDialog(project)" />
            </el-tooltip>
            <el-tooltip :content="project.status === 'archived' ? '恢复文档' : '归档文档'">
              <el-button circle text :icon="FolderOpened" :aria-label="project.status === 'archived' ? '恢复文档' : '归档文档'" @click.stop="toggleProjectArchive(project)" />
            </el-tooltip>
            <el-tooltip v-if="project.status === 'archived'" content="永久删除文档项目">
              <el-button circle text type="danger" :icon="Delete" aria-label="永久删除文档项目" @click.stop="removeProject(project)" />
            </el-tooltip>
          </div>
        </article>
      </div>
      <el-empty v-else description="暂无匹配的文档项目" :image-size="68" />
    </section>

    <section v-if="workspace" class="status-strip">
      <div><span>论文版本</span><strong class="edition-value">{{ workspace.manifest.edition || '工作稿' }} · v{{ workspace.manifest.version }}</strong></div>
      <div><span>章节</span><strong>{{ workspace.stats.chapter_count }}</strong></div>
      <div><span>正文规模</span><strong>{{ formatNumber(workspace.stats.word_count) }}</strong></div>
      <div><span>图表</span><strong>{{ workspace.stats.image_count }}</strong></div>
      <div><span>正式文献</span><strong>{{ workspace.reference_summary.formal }}</strong></div>
      <div><span>质量</span><strong :class="qualityClass">{{ workspace.quality.score }}</strong></div>
    </section>

    <el-tabs v-model="activeView" class="workspace-tabs" @tab-change="handleViewChange">
      <el-tab-pane label="研究总览" name="overview" />
      <el-tab-pane label="目录与正文" name="reader" />
      <el-tab-pane label="概念与论证" name="graph" />
      <el-tab-pane label="参考文献" name="references" />
      <el-tab-pane label="排版与交付" name="delivery" />
    </el-tabs>

    <template v-if="workspace">
      <main v-if="activeView === 'overview'" class="overview-view">
        <section class="research-brief">
          <header class="section-title">
            <div><span>研究主线</span><h3>论文研究画像</h3></div>
            <el-tag effect="plain">{{ workspace.project.document_spec?.document_type || '博士论文' }}</el-tag>
          </header>
          <div class="brief-grid">
            <div>
              <span>写作目标</span>
              <p>{{ workspace.project.document_spec?.writing_goal || '围绕海上无人集群智能协同任务规划形成完整理论、模型、方法与验证体系。' }}</p>
            </div>
            <div>
              <span>目标读者</span>
              <p>{{ workspace.project.document_spec?.target_audience || '导师、评审专家和相关研究人员' }}</p>
            </div>
            <div>
              <span>工作正文</span>
              <p>{{ workspace.manifest.working_markdown }}</p>
            </div>
            <div>
              <span>最终输出</span>
              <p>{{ workspace.project.document_spec?.output_format || 'Markdown / Word / PDF' }}</p>
            </div>
          </div>
        </section>

        <section v-if="targetStructure" class="target-structure">
          <header class="section-title target-structure__head">
            <div>
              <span>目录基线</span>
              <h3>{{ targetStructure.title || '论文目标结构' }}</h3>
            </div>
            <div class="target-structure__badges">
              <el-tag type="warning" effect="plain">当前稿 {{ workspace.stats.chapter_count }} 章</el-tag>
              <el-tag type="success" effect="plain">目标稿 {{ targetStructure.chapter_count }} 章</el-tag>
            </div>
          </header>
          <div class="target-structure__meta">
            <span>{{ targetStructure.version || '目标版' }}</span>
            <span>{{ targetStructure.heading_count || 0 }} 个目录项</span>
            <span>{{ targetStructure.source_path || workspace.manifest.source_word }}</span>
          </div>
          <div class="target-chapter-list">
            <details
              v-for="chapter in targetStructure.chapters"
              :key="chapter.number"
              :open="chapter.number === 3"
              class="target-chapter"
            >
              <summary>
                <strong>{{ chapter.title }}</strong>
                <small>{{ chapter.outline.length }} 个节项</small>
              </summary>
              <ol>
                <li
                  v-for="item in chapter.outline"
                  :key="`${chapter.number}-${item.title}`"
                  :class="`outline-level-${item.level}`"
                >{{ item.title }}</li>
              </ol>
            </details>
          </div>
        </section>

        <section class="overview-columns">
          <div class="chapter-progress">
            <header class="section-title"><div><span>写作结构</span><h3>章节进展</h3></div></header>
            <button
              v-for="section in chapterSections"
              :key="section.id"
              type="button"
              class="chapter-row"
              @click="openSection(section)"
            >
              <div><strong>{{ section.title }}</strong><small>{{ section.outline.length }} 节 · {{ formatNumber(section.word_count) }} 字符</small></div>
              <el-tag size="small" :type="section.status === 'writing' ? 'success' : 'warning'" effect="plain">
                {{ section.status === 'writing' ? '有正文' : '待充实' }}
              </el-tag>
            </button>
          </div>

          <aside class="quality-panel">
            <header class="section-title">
              <div><span>质量门禁</span><h3>交付准备度</h3></div>
              <strong class="quality-score" :class="qualityClass">{{ workspace.quality.score }}</strong>
            </header>
            <div class="quality-facts">
              <div><span>阻断问题</span><strong>{{ workspace.quality.blockers }}</strong></div>
              <div><span>警告</span><strong>{{ workspace.quality.warnings }}</strong></div>
              <div><span>缺失图片</span><strong>{{ workspace.quality.missing_assets }}</strong></div>
              <div><span>未引用文献</span><strong>{{ workspace.quality.uncited_references }}</strong></div>
            </div>
            <el-button text type="primary" @click="activeView = 'delivery'; loadDelivery()">查看完整质量报告</el-button>
          </aside>
        </section>
      </main>

      <main v-else-if="activeView === 'reader'" class="reader-view">
        <aside class="directory-pane">
          <el-input v-model="directorySearch" :prefix-icon="Search" placeholder="搜索目录" clearable />
          <div class="section-tree">
            <button
              v-for="section in filteredSections"
              :key="section.id"
              type="button"
              :class="{ active: selectedSectionId === section.id && readerMode === 'section' }"
              @click="selectSection(section.id)"
            >
              <strong>{{ section.title }}</strong>
              <small>{{ section.outline.length }} 节 · {{ formatNumber(section.word_count) }}</small>
            </button>
          </div>
        </aside>

        <section class="document-pane">
          <header class="document-toolbar">
            <el-segmented v-model="readerMode" :options="readerModes" size="small" @change="changeReaderMode" />
            <div>
              <el-tooltip v-if="readerMode === 'section'" :content="editing ? '取消编辑' : '编辑当前章节'">
                <el-button :icon="editing ? Close : EditPen" circle text @click="toggleEditing" />
              </el-tooltip>
              <el-button v-if="editing" type="primary" :icon="Check" :loading="saving" @click="saveSection">保存</el-button>
            </div>
          </header>
          <el-skeleton v-if="sectionLoading" :rows="12" animated />
          <el-input
            v-else-if="editing"
            v-model="editorContent"
            type="textarea"
            :autosize="{ minRows: 24 }"
            class="markdown-editor"
          />
          <article v-else class="markdown-body" v-html="renderedDocument" />
        </section>

        <aside class="inspector-pane">
          <template v-if="readerMode === 'section' && activeSectionMeta">
            <span class="eyebrow">章节检查器</span>
            <h3>{{ activeSectionMeta.title }}</h3>
            <p>{{ activeSectionMeta.summary || '暂无章节摘要' }}</p>
            <dl>
              <div><dt>正文规模</dt><dd>{{ formatNumber(activeSectionMeta.word_count) }}</dd></div>
              <div><dt>目录项</dt><dd>{{ activeSectionMeta.outline.length }}</dd></div>
              <div><dt>图表</dt><dd>{{ activeSectionMeta.image_count }}</dd></div>
              <div><dt>引用</dt><dd>{{ activeSectionMeta.citation_count }}</dd></div>
            </dl>
            <section>
              <h4>本章完整目录</h4>
              <div class="outline-list">
                <div v-for="item in activeSectionMeta.outline" :key="item.id" :style="{ paddingLeft: `${(item.level - 2) * 12}px` }">
                  {{ item.title }}
                </div>
              </div>
            </section>
            <section>
              <h4>必要图片</h4>
              <span v-if="!activeSectionMeta.image_count" class="muted">本章未检出图片</span>
              <span v-else>{{ activeSectionMeta.image_count }} 张图片已纳入正文资源检查</span>
            </section>
          </template>
          <template v-else>
            <span class="eyebrow">全文阅读</span>
            <h3>完整工作正文</h3>
            <p>全文仅在需要连续审阅时加载。日常写作建议按章节进行，以保持目录、引用和版本边界清晰。</p>
          </template>
        </aside>
      </main>

      <main v-else-if="activeView === 'graph'" class="graph-view">
        <header class="graph-toolbar">
          <div><span class="eyebrow">知识库概念骨架</span><h3>概念、章节与论证关系</h3></div>
          <el-segmented v-model="graphMode" :options="graphModes" size="small" @change="renderGraph" />
        </header>
        <section class="graph-metrics">
          <div><span>章节</span><strong>{{ graphData?.summary.sections || 0 }}</strong></div>
          <div><span>匹配概念</span><strong>{{ graphData?.summary.concepts || 0 }}</strong></div>
          <div><span>论点</span><strong>{{ graphData?.summary.claims || 0 }}</strong></div>
          <div><span>关系</span><strong>{{ graphData?.summary.relations || 0 }}</strong></div>
        </section>
        <div ref="graphElement" class="graph-canvas" />
        <aside v-if="selectedGraphNode" class="graph-selection">
          <span>{{ graphNodeTypeLabel(selectedGraphNode.type) }}</span>
          <strong>{{ selectedGraphNode.name }}</strong>
          <p v-if="selectedGraphNode.detail">{{ selectedGraphNode.detail }}</p>
        </aside>
      </main>

      <main v-else-if="activeView === 'references'" class="references-view">
        <header class="reference-toolbar">
          <div><span class="eyebrow">证据链</span><h3>知识资料与正式论文引用</h3></div>
          <div class="reference-controls">
            <el-segmented v-model="referenceStatus" :options="referenceStatusOptions" size="small" />
            <el-input v-model="referenceSearch" :prefix-icon="Search" placeholder="检索文献" clearable />
          </div>
        </header>
        <section class="reference-audit-strip">
          <div><span>正式文献</span><strong>{{ references?.summary.formal || 0 }}</strong></div>
          <div><span>已引用</span><strong>{{ references?.summary.cited || 0 }}</strong></div>
          <div><span>未检出</span><strong class="quality-warning">{{ references?.summary.uncited || 0 }}</strong></div>
          <div><span>正文引用</span><strong>{{ references?.summary.in_text_citations || 0 }}</strong></div>
          <div><span>覆盖章节</span><strong>{{ references?.summary.sections_with_citations || 0 }}</strong></div>
        </section>
        <section class="citation-coverage">
          <header><div><span>章节审计</span><h3>引用覆盖</h3></div><small>点击章节可返回正文核验</small></header>
          <div class="coverage-list">
            <button v-for="section in references?.section_coverage || []" :key="section.section_id" type="button" @click="openReferenceLocation(section)">
              <strong>{{ section.title }}</strong>
              <span>{{ section.unique_references }} 篇 · {{ section.citation_occurrences }} 次</span>
            </button>
          </div>
        </section>
        <div class="reference-columns">
          <section>
            <header><div><span>研究资料</span><h3>知识库资料</h3></div><el-tag effect="plain">{{ references?.knowledge.length || 0 }}</el-tag></header>
            <div v-if="filteredKnowledgeReferences.length" class="knowledge-reference-list">
              <article v-for="reference in filteredKnowledgeReferences" :key="reference.id">
                <strong>{{ reference.title || reference.text }}</strong>
                <small>{{ reference.note || reference.source_type || '知识库上下文' }}</small>
              </article>
            </div>
            <el-empty v-else description="暂无匹配的知识库资料" :image-size="64" />
          </section>
          <section>
            <header><div><span>文末书目</span><h3>正式参考文献</h3></div><el-tag type="success" effect="plain">{{ references?.formal.length || 0 }}</el-tag></header>
            <div class="formal-reference-list">
              <article v-for="reference in filteredFormalReferences" :key="reference.id">
                <span>[{{ reference.number }}]</span>
                <div>
                  <strong>{{ reference.text }}</strong>
                  <small>{{ reference.year || '年份待核验' }} · 正文出现 {{ reference.usage_count || 0 }} 次 · 覆盖 {{ reference.section_count || 0 }} 个章节</small>
                  <div v-if="reference.locations?.length" class="reference-locations">
                    <button v-for="location in reference.locations" :key="`${reference.id}-${location.section_id}`" type="button" @click="openReferenceLocation(location)">
                      {{ location.title }} · {{ location.count }} 次
                    </button>
                  </div>
                  <small v-else class="uncited-note">需人工核验：确认保留、删除或在适当论述处补引</small>
                </div>
                <el-tag size="small" :type="reference.usage_count ? 'success' : 'warning'" effect="plain">
                  {{ reference.usage_count ? '已引用' : '未检出' }}
                </el-tag>
              </article>
            </div>
          </section>
        </div>
      </main>

      <main v-else class="delivery-view">
        <section class="delivery-main">
          <header class="section-title"><div><span>格式权威</span><h3>Word 与 PDF 交付</h3></div></header>
          <div class="source-grid">
            <div><span>原始 Word</span><strong>{{ workspace.manifest.source_word || '未登记' }}</strong><el-button text :disabled="!workspace.manifest.source_word" @click="downloadSourceWord">下载原文</el-button></div>
            <div><span>Markdown 工作稿</span><strong>{{ workspace.manifest.working_markdown }}</strong><el-tag effect="plain">v{{ workspace.manifest.version }}</el-tag></div>
          </div>
          <div class="export-actions">
            <el-button type="primary" :icon="Document" :loading="exporting === 'docx'" @click="exportDocument('docx')">生成 Word</el-button>
            <el-button :icon="View" :loading="exporting === 'pdf'" @click="exportDocument('pdf')">预览 PDF</el-button>
          </div>
          <el-alert title="工作稿是内容权威，Word/PDF 是排版与交付权威；外部修改的 Word 应作为新版本重新导入，不进行无提示双向覆盖。" type="info" :closable="false" show-icon />
        </section>

        <aside class="delivery-side">
          <section>
            <header class="section-title"><div><span>版本</span><h3>修改历史</h3></div></header>
            <div class="version-list">
              <div v-for="version in versions" :key="version.name">
                <strong>{{ version.name }}</strong><small>{{ formatDate(version.created_at) }} · {{ formatFileSize(version.size_bytes) }}</small>
              </div>
            </div>
          </section>
          <section>
            <header class="section-title"><div><span>检查</span><h3>质量报告</h3></div></header>
            <div class="issue-list">
              <div v-for="issue in qualityReport?.issues || []" :key="`${issue.type}-${issue.message}`">
                <el-tag size="small" :type="issue.severity === 'blocker' ? 'danger' : 'warning'" effect="plain">
                  {{ issue.severity === 'blocker' ? '阻断' : '警告' }}
                </el-tag>
                <span>{{ issue.message }}</span>
              </div>
              <span v-if="!qualityReport?.issues.length" class="muted">暂无质量问题</span>
            </div>
          </section>
        </aside>
      </main>
    </template>

    <el-empty v-else-if="!loading" description="暂无启用文档撰写模块的项目" />

    <el-dialog v-model="projectDialogVisible" :title="editingProjectId ? '编辑文档项目' : '新建文档项目'" width="720px">
      <div class="project-form">
        <div class="project-form-row title">
          <el-input v-model="projectForm.name" placeholder="文档名称" />
          <el-select v-model="projectForm.document_type" placeholder="文档类型">
            <el-option label="研究报告" value="研究报告" />
            <el-option label="学术论文" value="学术论文" />
            <el-option label="博士论文" value="博士论文" />
            <el-option label="技术报告" value="技术报告" />
            <el-option label="专利文档" value="专利文档" />
            <el-option label="项目方案" value="项目方案" />
          </el-select>
        </div>
        <el-input v-model="projectForm.description" type="textarea" :rows="2" placeholder="文档简介与使用需求" />
        <el-input v-model="projectForm.writing_goal" type="textarea" :rows="2" placeholder="写作目标" />
        <div class="project-form-row">
          <el-input v-model="projectForm.target_audience" placeholder="目标读者" />
          <el-input v-model="projectForm.output_format" placeholder="输出格式" />
        </div>
        <div class="project-form-row">
          <el-input v-model="projectForm.owner_agent" placeholder="负责智能体 ID" />
          <el-select v-model="projectForm.priority" placeholder="优先级">
            <el-option label="高" value="high" />
            <el-option label="中" value="medium" />
            <el-option label="低" value="low" />
          </el-select>
        </div>
        <el-input
          v-model="projectOutlineText"
          type="textarea"
          :rows="7"
          placeholder="初始目录，每行一个章节，例如：&#10;第一章 项目背景&#10;第二章 方案设计&#10;第三章 实施计划"
        />
        <small v-if="editingProjectId" class="form-tip">修改目录计划不会覆盖已经存在的正文和版本记录。</small>
      </div>
      <template #footer>
        <el-button @click="projectDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="projectSaving" @click="saveProject">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="pdfPreviewVisible"
      title="PDF 预览"
      width="94vw"
      class="pdf-preview-dialog"
      destroy-on-close
    >
      <iframe v-if="pdfPreviewUrl" :src="pdfPreviewUrl" title="论文 PDF 预览" class="pdf-preview-frame" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import MarkdownIt from 'markdown-it'
import * as echarts from 'echarts/core'
import { GraphChart } from 'echarts/charts'
import { LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { Check, Close, Delete, Document, EditPen, FolderOpened, Plus, Refresh, Search, View } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { deleteProject, getProjects, updateProject, type Project } from '@/api/projects'
import {
  createWritingProject,
  exportWritingDocument,
  getWritingAsset,
  getWritingFulltext,
  getWritingGraph,
  getWritingQuality,
  getWritingReferences,
  getWritingSection,
  getWritingSourceWord,
  getWritingVersions,
  getWritingWorkspace,
  updateWritingSection,
  type WritingGraphNode,
  type WritingReference,
  type WritingReferenceCoverage,
  type WritingSection,
  type WritingWorkspace
} from '@/api/writing'

echarts.use([GraphChart, LegendComponent, TooltipComponent, CanvasRenderer])

const route = useRoute()
const router = useRouter()
const md = new MarkdownIt({ html: false, linkify: true, breaks: false })
const projects = ref<Project[]>([])
const projectSearch = ref('')
const selectedProjectId = ref('')
const projectDialogVisible = ref(false)
const projectSaving = ref(false)
const editingProjectId = ref('')
const projectOutlineText = ref('')
const projectForm = ref({
  name: '',
  description: '',
  document_type: '研究报告',
  writing_goal: '',
  target_audience: '',
  output_format: 'Markdown / Word / PDF',
  owner_agent: 'ultra-magnus',
  priority: 'medium'
})
const workspace = ref<WritingWorkspace>()
const targetStructure = computed(() => workspace.value?.project.document_spec?.target_structure)
const activeView = ref('overview')
const loading = ref(false)
const sectionLoading = ref(false)
const selectedSectionId = ref('')
const currentSection = ref<WritingSection>()
const readerMode = ref<'section' | 'full'>('section')
const directorySearch = ref('')
const displayMarkdown = ref('')
const editing = ref(false)
const editorContent = ref('')
const saving = ref(false)
const references = ref<Awaited<ReturnType<typeof getWritingReferences>>>()
const referenceSearch = ref('')
const referenceStatus = ref<'all' | 'cited' | 'uncited'>('all')
const graphData = ref<Awaited<ReturnType<typeof getWritingGraph>>>()
const graphMode = ref('concept')
const graphElement = ref<HTMLElement>()
const selectedGraphNode = ref<WritingGraphNode>()
const qualityReport = ref<Awaited<ReturnType<typeof getWritingQuality>>>()
const versions = ref<Array<{ name: string; size_bytes: number; created_at: string; current?: boolean }>>([])
const exporting = ref('')
const objectUrls = ref<string[]>([])
const pdfPreviewVisible = ref(false)
const pdfPreviewUrl = ref('')
let graphChart: echarts.ECharts | undefined

const readerModes = [{ label: '章节阅读', value: 'section' }, { label: '全文阅读', value: 'full' }]
const graphModes = [{ label: '概念骨架', value: 'concept' }, { label: '论证关系', value: 'argument' }]
const referenceStatusOptions = [{ label: '全部', value: 'all' }, { label: '已引用', value: 'cited' }, { label: '未检出', value: 'uncited' }]
const filteredProjects = computed(() => {
  const keyword = projectSearch.value.trim().toLowerCase()
  const rows = [...projects.value].sort((a, b) => {
    if (a.status === 'archived' && b.status !== 'archived') return 1
    if (a.status !== 'archived' && b.status === 'archived') return -1
    return a.name.localeCompare(b.name, 'zh-CN')
  })
  if (!keyword) return rows
  return rows.filter(project => [
    project.name,
    project.description || '',
    project.document_spec?.document_type || '',
    project.owner_agent || ''
  ].some(value => value.toLowerCase().includes(keyword)))
})
const chapterSections = computed(() => workspace.value?.sections.filter(row => row.kind === 'chapter') || [])
const filteredSections = computed(() => {
  const keyword = directorySearch.value.trim().toLowerCase()
  const rows = workspace.value?.sections || []
  if (!keyword) return rows
  return rows.filter(row => row.title.toLowerCase().includes(keyword) || row.outline.some(item => item.title.toLowerCase().includes(keyword)))
})
const activeSectionMeta = computed(() => workspace.value?.sections.find(row => row.id === selectedSectionId.value))
const renderedDocument = computed(() => md.render(displayMarkdown.value || '*暂无正文*'))
const qualityClass = computed(() => {
  const score = workspace.value?.quality.score || 0
  if (score >= 85) return 'quality-good'
  if (score >= 60) return 'quality-warning'
  return 'quality-danger'
})
const filteredFormalReferences = computed(() => filterReferences(references.value?.formal || []).filter(row => {
  if (referenceStatus.value === 'cited') return Boolean(row.usage_count)
  if (referenceStatus.value === 'uncited') return !row.usage_count
  return true
}))
const filteredKnowledgeReferences = computed(() => filterReferences(references.value?.knowledge || []))

async function loadProjects() {
  const result = await getProjects({ project_type: 'document', enabled_module: 'writing' })
  projects.value = result.projects || []
}

async function loadWorkspace() {
  loading.value = true
  try {
    if (!projects.value.length) await loadProjects()
    const routeProjectId = String(route.query.project_id || '')
    selectedProjectId.value = projects.value.some(row => row.id === routeProjectId)
      ? routeProjectId
      : projects.value.some(row => row.id === selectedProjectId.value)
        ? selectedProjectId.value
        : projects.value.find(row => row.status !== 'archived')?.id || projects.value[0]?.id || ''
    if (!selectedProjectId.value) {
      workspace.value = undefined
      return
    }
    workspace.value = await getWritingWorkspace(selectedProjectId.value)
    selectedSectionId.value = workspace.value.sections.find(row => row.kind === 'chapter')?.id || workspace.value.sections[0]?.id || ''
    if (selectedSectionId.value) await loadSection(selectedSectionId.value)
  } catch (error) {
    ElMessage.error(errorMessage(error, '文档工作台加载失败'))
  } finally {
    loading.value = false
  }
}

async function refreshAll() {
  try {
    await loadProjects()
    await loadWorkspace()
    ElMessage.success('文档项目已刷新')
  } catch (error) {
    ElMessage.error(errorMessage(error, '文档项目刷新失败'))
  }
}

async function selectProject(projectId: string) {
  if (selectedProjectId.value === projectId && workspace.value) return
  selectedProjectId.value = projectId
  await changeProject()
}

async function changeProject() {
  await router.replace({ path: '/writing', query: { project_id: selectedProjectId.value } })
  workspace.value = undefined
  references.value = undefined
  graphData.value = undefined
  await loadWorkspace()
}

function splitOutline(value: string) {
  return value.split(/\r?\n/).map(row => row.trim()).filter(Boolean)
}

function openProjectDialog(project?: Project) {
  editingProjectId.value = project?.id || ''
  projectForm.value = {
    name: project?.name || '',
    description: project?.description || '',
    document_type: project?.document_spec?.document_type || '研究报告',
    writing_goal: project?.document_spec?.writing_goal || '',
    target_audience: project?.document_spec?.target_audience || '',
    output_format: project?.document_spec?.output_format || 'Markdown / Word / PDF',
    owner_agent: project?.owner_agent || 'ultra-magnus',
    priority: project?.priority || 'medium'
  }
  projectOutlineText.value = (project?.document_spec?.outline || []).join('\n')
  projectDialogVisible.value = true
}

async function saveProject() {
  if (!projectForm.value.name.trim()) {
    ElMessage.warning('请填写文档名称')
    return
  }
  projectSaving.value = true
  try {
    const outline = splitOutline(projectOutlineText.value)
    if (editingProjectId.value) {
      const existing = projects.value.find(row => row.id === editingProjectId.value)
      await updateProject(editingProjectId.value, {
        name: projectForm.value.name.trim(),
        description: projectForm.value.description.trim(),
        priority: projectForm.value.priority,
        owner_agent: projectForm.value.owner_agent.trim() || 'ultra-magnus',
        document_spec: {
          ...(existing?.document_spec || {}),
          document_type: projectForm.value.document_type,
          writing_goal: projectForm.value.writing_goal.trim(),
          target_audience: projectForm.value.target_audience.trim(),
          output_format: projectForm.value.output_format.trim() || 'Markdown / Word / PDF',
          outline
        }
      })
      selectedProjectId.value = editingProjectId.value
      ElMessage.success('文档项目信息已更新')
    } else {
      const result = await createWritingProject({
        ...projectForm.value,
        outline
      })
      selectedProjectId.value = result.project.id
      ElMessage.success('新文档及独立工作区已创建')
    }
    projectDialogVisible.value = false
    await loadProjects()
    await changeProject()
  } catch (error) {
    ElMessage.error(errorMessage(error, '文档项目保存失败'))
  } finally {
    projectSaving.value = false
  }
}

async function toggleProjectArchive(project: Project) {
  const restoring = project.status === 'archived'
  try {
    await updateProject(project.id, { status: restoring ? 'planning' : 'archived' })
    await loadProjects()
    if (!restoring && selectedProjectId.value === project.id) {
      const next = projects.value.find(row => row.status !== 'archived' && row.id !== project.id)
      if (next) {
        selectedProjectId.value = next.id
        await changeProject()
      }
    }
    ElMessage.success(restoring ? '文档已恢复' : '文档已归档')
  } catch (error) {
    ElMessage.error(errorMessage(error, restoring ? '恢复失败' : '归档失败'))
  }
}

async function removeProject(project: Project) {
  try {
    await ElMessageBox.confirm(
      `永久删除“${project.name}”的项目记录？已生成的正文文件将保留在知识库中。`,
      '删除文档项目',
      { type: 'warning', confirmButtonText: '永久删除', cancelButtonText: '取消' }
    )
    await deleteProject(project.id)
    if (selectedProjectId.value === project.id) {
      selectedProjectId.value = ''
      workspace.value = undefined
    }
    await loadProjects()
    await loadWorkspace()
    ElMessage.success('文档项目记录已删除')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(errorMessage(error, '删除失败'))
  }
}

function projectStatusLabel(status: string) {
  return ({ active: '进行中', planning: '规划中', completed: '已完成', archived: '已归档' } as Record<string, string>)[status] || status
}

function projectStatusType(status: string) {
  if (status === 'active') return 'success'
  if (status === 'planning') return 'warning'
  if (status === 'archived') return 'info'
  return 'primary'
}

async function loadSection(sectionId: string) {
  if (!selectedProjectId.value) return
  sectionLoading.value = true
  editing.value = false
  try {
    revokeObjectUrls()
    currentSection.value = await getWritingSection(selectedProjectId.value, sectionId)
    editorContent.value = currentSection.value.content || ''
    displayMarkdown.value = await hydrateAssets(currentSection.value.content || '', currentSection.value.asset_paths || [])
  } catch (error) {
    ElMessage.error(errorMessage(error, '章节加载失败'))
  } finally {
    sectionLoading.value = false
  }
}

async function selectSection(sectionId: string) {
  readerMode.value = 'section'
  selectedSectionId.value = sectionId
  await loadSection(sectionId)
}

async function openSection(section: WritingSection) {
  activeView.value = 'reader'
  selectedSectionId.value = section.id
  await loadSection(section.id)
}

async function changeReaderMode() {
  editing.value = false
  if (readerMode.value === 'full') {
    sectionLoading.value = true
    try {
      revokeObjectUrls()
      const fulltext = await getWritingFulltext(selectedProjectId.value)
      displayMarkdown.value = await hydrateAssets(fulltext.content, fulltext.asset_paths)
    } catch (error) {
      ElMessage.error(errorMessage(error, '全文加载失败'))
    } finally {
      sectionLoading.value = false
    }
  } else if (selectedSectionId.value) {
    await loadSection(selectedSectionId.value)
  }
}

function toggleEditing() {
  editing.value = !editing.value
  if (editing.value) editorContent.value = currentSection.value?.content || ''
}

async function saveSection() {
  if (!currentSection.value?.version || !selectedSectionId.value) return
  const editedTitle = currentSection.value.title
  saving.value = true
  try {
    await updateWritingSection(selectedProjectId.value, selectedSectionId.value, {
      content: editorContent.value,
      expected_version: currentSection.value.version,
      actor: 'admin'
    })
    ElMessage.success('章节已保存为新版本')
    await loadWorkspace()
    selectedSectionId.value = workspace.value?.sections.find(row => row.title === editedTitle)?.id || selectedSectionId.value
    await loadSection(selectedSectionId.value)
  } catch (error) {
    ElMessage.error(errorMessage(error, '章节保存失败'))
  } finally {
    saving.value = false
  }
}

async function hydrateAssets(markdown: string, paths: string[]) {
  let hydrated = markdown
  await Promise.all(paths.map(async path => {
    try {
      const blob = await getWritingAsset(selectedProjectId.value, path)
      const url = URL.createObjectURL(blob)
      objectUrls.value.push(url)
      hydrated = hydrated.split(`](${path})`).join(`](${url})`)
    } catch {
      // The quality report exposes missing resources; keep the original path visible in the reader.
    }
  }))
  return hydrated
}

function revokeObjectUrls() {
  objectUrls.value.forEach(url => URL.revokeObjectURL(url))
  objectUrls.value = []
}

async function handleViewChange(name: string | number) {
  if (name === 'graph') await loadGraph()
  if (name === 'references') await loadReferences()
  if (name === 'delivery') await loadDelivery()
}

async function loadGraph() {
  if (!graphData.value) graphData.value = await getWritingGraph(selectedProjectId.value)
  await nextTick()
  renderGraph()
}

function renderGraph() {
  if (!graphElement.value || !graphData.value) return
  graphChart ||= echarts.init(graphElement.value)
  const allowedTypes = graphMode.value === 'concept' ? new Set(['section', 'concept']) : new Set(['section', 'claim'])
  const nodes = graphData.value.nodes.filter(node => allowedTypes.has(node.type))
  const allowedIds = new Set(nodes.map(node => node.id))
  const categories = graphMode.value === 'concept'
    ? [{ name: '章节' }, { name: '概念' }]
    : [{ name: '章节' }, { name: '论点' }]
  graphChart.setOption({
    tooltip: { formatter: (params: any) => params.data.detail || `${params.data.name}<br/>${params.data.type}` },
    legend: { data: categories.map(row => row.name), top: 0, textStyle: { color: '#aeb8c6' } },
    series: [{
      type: 'graph', layout: 'force', roam: true, draggable: true, categories,
      data: nodes.map(node => ({
        ...node,
        category: node.type === 'section' ? 0 : 1,
        symbolSize: node.type === 'section' ? 28 : Math.max(10, Math.min(24, 10 + Math.log2((node.value || 1) + 1) * 3))
      })),
      links: graphData.value.edges.filter(edge => allowedIds.has(edge.source) && allowedIds.has(edge.target)).map(edge => ({ ...edge, name: edge.relation })),
      force: { repulsion: 240, edgeLength: [70, 150], gravity: 0.08 },
      label: { show: true, color: '#d8dee8', fontSize: 10, width: 110, overflow: 'truncate' },
      lineStyle: { opacity: 0.4, color: 'source', curveness: 0.08 },
      emphasis: { focus: 'adjacency' }
    }]
  }, true)
  graphChart.off('click')
  graphChart.on('click', event => {
    if (event.dataType === 'node') selectedGraphNode.value = graphData.value?.nodes.find(node => node.id === (event.data as any).id)
  })
  graphChart.resize()
}

async function loadReferences() {
  if (!references.value) references.value = await getWritingReferences(selectedProjectId.value)
}

async function openReferenceLocation(location: Pick<WritingReferenceCoverage, 'section_id'>) {
  const section = workspace.value?.sections.find(row => row.id === location.section_id)
  if (section) await openSection(section)
}

async function loadDelivery() {
  const [quality, history] = await Promise.all([
    getWritingQuality(selectedProjectId.value),
    getWritingVersions(selectedProjectId.value)
  ])
  qualityReport.value = quality
  versions.value = history.versions
}

async function downloadSourceWord() {
  try {
    const blob = await getWritingSourceWord(selectedProjectId.value)
    downloadBlob(blob, `${workspace.value?.project.name || '文档'}-原文.docx`)
  } catch (error) {
    ElMessage.error(errorMessage(error, 'Word 原文下载失败'))
  }
}

async function exportDocument(format: 'docx' | 'pdf') {
  exporting.value = format
  try {
    const blob = await exportWritingDocument(selectedProjectId.value, format)
    if (format === 'pdf') {
      const url = URL.createObjectURL(blob)
      objectUrls.value.push(url)
      pdfPreviewUrl.value = url
      pdfPreviewVisible.value = true
    } else {
      downloadBlob(blob, `${workspace.value?.project.name || '文档'}-v${workspace.value?.manifest.version}.${format}`)
    }
    ElMessage.success(`${format.toUpperCase()} 已生成`)
    await loadDelivery()
  } catch (error) {
    ElMessage.error(errorMessage(error, `${format.toUpperCase()} 生成失败`))
  } finally {
    exporting.value = ''
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

function filterReferences(rows: WritingReference[]) {
  const keyword = referenceSearch.value.trim().toLowerCase()
  if (!keyword) return rows
  return rows.filter(row => `${row.number || ''} ${row.title || ''} ${row.text || ''} ${row.year || ''}`.toLowerCase().includes(keyword))
}

function graphNodeTypeLabel(type: string) {
  return ({ section: '论文章节', concept: '知识库概念', claim: '论文论点' } as Record<string, string>)[type] || type
}

function formatNumber(value?: number) {
  return new Intl.NumberFormat('zh-CN').format(value || 0)
}

function formatDate(value: string) {
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

function formatFileSize(value: number) {
  return value > 1024 * 1024 ? `${(value / 1024 / 1024).toFixed(1)} MB` : `${Math.round(value / 1024)} KB`
}

function errorMessage(error: unknown, fallback: string) {
  return (error as any)?.response?.data?.detail || fallback
}

function handleResize() {
  graphChart?.resize()
}

onMounted(() => {
  window.addEventListener('resize', handleResize)
  loadWorkspace()
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  revokeObjectUrls()
  graphChart?.dispose()
})
</script>

<style scoped>
.writing-page { display: grid; gap: 14px; width: 100%; max-width: 100%; min-width: 0; overflow: hidden; }
.writing-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; }
.writing-head h2, .writing-head p, .section-title h3, .graph-toolbar h3, .reference-toolbar h3 { margin: 0; }
.writing-head h2 { margin-top: 3px; color: var(--text-primary); font-size: 20px; }
.writing-head p { margin-top: 5px; color: var(--text-secondary); font-size: 12px; }
.title-line { display: flex; align-items: center; gap: 8px; }
.eyebrow, .section-title span, .graph-toolbar span, .reference-toolbar span { color: var(--view-color-primary); font-size: 11px; }
.head-actions { display: flex; gap: 8px; }
.document-manager { display: grid; gap: 11px; padding-block: 12px; border-block: 1px solid var(--line-color); }
.manager-head { display: flex; align-items: center; justify-content: space-between; gap: 14px; }
.manager-head h3 { margin: 3px 0 0; color: var(--text-primary); font-size: 14px; letter-spacing: 0; }
.manager-head .el-input { width: min(340px, 42vw); }
.document-project-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(270px, 1fr)); gap: 10px; }
.document-project-card { position: relative; display: grid; gap: 10px; min-width: 0; padding: 12px; border: 1px solid var(--line-color); border-radius: 6px; background: var(--card-bg); cursor: pointer; }
.document-project-card:hover, .document-project-card.active { border-color: var(--view-color-primary); background: var(--view-color-faint); }
.document-project-card.archived { opacity: .68; }
.project-card-main { display: grid; grid-template-columns: 34px minmax(0, 1fr); gap: 9px; padding-right: 62px; }
.document-icon { display: inline-flex; align-items: center; justify-content: center; width: 34px; height: 34px; border-radius: 5px; color: var(--view-color-primary); background: var(--view-color-faint); }
.project-name-line { display: flex; align-items: center; gap: 7px; min-width: 0; }
.project-name-line strong { overflow: hidden; color: var(--text-primary); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.project-card-main p { display: -webkit-box; margin: 4px 0 0; overflow: hidden; color: var(--text-secondary); font-size: 10px; line-height: 1.45; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.project-card-meta { display: flex; flex-wrap: wrap; gap: 5px 10px; color: var(--text-secondary); font-size: 9px; }
.project-card-actions { position: absolute; top: 7px; right: 7px; display: flex; align-items: center; }
.project-card-actions .el-button { width: 26px; height: 26px; margin: 0; }
.project-form { display: grid; gap: 12px; }
.project-form-row { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.project-form-row.title { grid-template-columns: minmax(0, 1.5fr) minmax(150px, .7fr); }
.form-tip { color: var(--text-secondary); font-size: 10px; }
.status-strip { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); border-block: 1px solid var(--line-color); }
.status-strip > div { display: grid; gap: 3px; padding: 9px 12px; border-right: 1px solid var(--line-color); }
.status-strip > div:last-child { border-right: 0; }
.status-strip span, .brief-grid span, .quality-facts span, .graph-metrics span, .source-grid span { color: var(--text-secondary); font-size: 11px; }
.status-strip strong { color: var(--text-primary); font-size: 17px; }
.status-strip .edition-value { font-size: 14px; }
.workspace-tabs { min-width: 0; max-width: 100%; margin-top: -4px; }
.workspace-tabs :deep(.el-tabs__header) { margin: 0; }
.section-title, .graph-toolbar, .reference-toolbar, .reference-columns > section > header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.section-title h3, .graph-toolbar h3, .reference-toolbar h3, .reference-columns h3 { margin-top: 3px; color: var(--text-primary); font-size: 14px; }
.research-brief, .target-structure, .chapter-progress, .quality-panel, .directory-pane, .document-pane, .inspector-pane, .graph-view, .references-view, .delivery-main, .delivery-side > section { border: 1px solid var(--line-color); border-radius: 6px; background: var(--card-bg); }
.research-brief, .target-structure, .chapter-progress, .quality-panel, .graph-view, .references-view, .delivery-main, .delivery-side > section { padding: 15px; }
.overview-view { display: grid; gap: 14px; }
.brief-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 14px; }
.brief-grid > div { min-width: 0; padding: 11px; background: var(--view-color-faint); }
.brief-grid p { margin: 5px 0 0; overflow-wrap: anywhere; color: var(--text-primary); font-size: 12px; line-height: 1.6; }
.target-structure__head { align-items: center; }
.target-structure__badges { display: flex; gap: 8px; flex-wrap: wrap; }
.target-structure__meta { display: flex; gap: 16px; margin: 8px 0 12px; color: var(--text-secondary); font-size: 11px; flex-wrap: wrap; }
.target-structure__meta span:last-child { min-width: 0; overflow-wrap: anywhere; }
.target-chapter-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); border-top: 1px solid var(--line-color); }
.target-chapter { min-width: 0; padding: 10px 12px; border-bottom: 1px solid var(--line-color); }
.target-chapter:nth-child(odd) { border-right: 1px solid var(--line-color); }
.target-chapter summary { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; cursor: pointer; color: var(--text-primary); }
.target-chapter summary strong { min-width: 0; font-size: 12px; }
.target-chapter summary small { color: var(--text-secondary); white-space: nowrap; font-size: 10px; }
.target-chapter ol { display: grid; gap: 4px; margin: 9px 0 0; padding: 9px 0 0; border-top: 1px solid var(--line-color); list-style: none; color: var(--text-secondary); font-size: 10px; }
.target-chapter li { line-height: 1.45; }
.target-chapter li.outline-level-3 { padding-left: 14px; opacity: .78; }
.overview-columns { display: grid; grid-template-columns: minmax(0, 1.65fr) minmax(260px, .7fr); gap: 14px; align-items: start; }
.chapter-progress { display: grid; gap: 0; }
.chapter-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 11px 0; border: 0; border-bottom: 1px solid var(--line-color); color: inherit; text-align: left; background: transparent; cursor: pointer; }
.chapter-row:last-child { border-bottom: 0; }
.chapter-row > div { display: grid; gap: 3px; }
.chapter-row strong { color: var(--text-primary); font-size: 12px; }
.chapter-row small { color: var(--text-secondary); }
.quality-panel { display: grid; gap: 14px; }
.quality-score { font-size: 28px; }
.quality-facts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.quality-facts > div { display: grid; gap: 3px; padding: 9px; background: var(--view-color-faint); }
.quality-good { color: #67c23a !important; }
.quality-warning { color: #e6a23c !important; }
.quality-danger { color: #f56c6c !important; }
.reader-view { display: grid; grid-template-columns: minmax(190px, 250px) minmax(0, 1fr) minmax(230px, 290px); gap: 12px; min-height: calc(100vh - 245px); align-items: stretch; }
.directory-pane, .inspector-pane { padding: 12px; }
.section-tree { display: grid; gap: 2px; max-height: calc(100vh - 310px); margin-top: 10px; overflow-y: auto; }
.section-tree button { display: grid; gap: 3px; padding: 8px; border: 0; border-left: 2px solid transparent; color: inherit; text-align: left; background: transparent; cursor: pointer; }
.section-tree button:hover, .section-tree button.active { border-left-color: var(--view-color-primary); background: var(--view-color-faint); }
.section-tree strong { color: var(--text-primary); font-size: 11px; line-height: 1.4; }
.section-tree small { color: var(--text-secondary); font-size: 10px; }
.document-pane { min-width: 0; overflow: hidden; }
.document-toolbar { display: flex; align-items: center; justify-content: space-between; padding: 9px 12px; border-bottom: 1px solid var(--line-color); }
.markdown-body { max-height: calc(100vh - 300px); padding: 24px clamp(18px, 4vw, 56px) 56px; overflow: auto; color: var(--text-primary); font-size: 14px; line-height: 1.85; }
.markdown-body :deep(h1) { margin: 1.5em 0 .8em; font-size: 25px; letter-spacing: 0; }
.markdown-body :deep(h2) { margin: 1.45em 0 .65em; padding-bottom: 6px; border-bottom: 1px solid var(--line-color); font-size: 19px; letter-spacing: 0; }
.markdown-body :deep(h3) { margin: 1.3em 0 .55em; font-size: 16px; letter-spacing: 0; }
.markdown-body :deep(h4) { font-size: 14px; letter-spacing: 0; }
.markdown-body :deep(p) { margin: .8em 0; }
.markdown-body :deep(img) { display: block; max-width: 100%; max-height: 620px; margin: 18px auto; object-fit: contain; }
.markdown-body :deep(table) { width: 100%; border-collapse: collapse; font-size: 12px; }
.markdown-body :deep(th), .markdown-body :deep(td) { padding: 7px 9px; border: 1px solid var(--line-color); }
.markdown-body :deep(blockquote) { margin: 14px 0; padding: 6px 14px; border-left: 3px solid var(--view-color-primary); color: var(--text-secondary); }
.markdown-editor { padding: 12px; }
.markdown-editor :deep(textarea) { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; line-height: 1.65; }
.inspector-pane { min-width: 0; overflow-y: auto; }
.inspector-pane h3 { margin: 4px 0 8px; color: var(--text-primary); font-size: 14px; }
.inspector-pane p { margin: 0 0 12px; color: var(--text-secondary); font-size: 11px; line-height: 1.6; }
.inspector-pane dl { display: grid; margin: 0; }
.inspector-pane dl > div { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--line-color); font-size: 11px; }
.inspector-pane dt { color: var(--text-secondary); }
.inspector-pane dd { margin: 0; color: var(--text-primary); }
.inspector-pane section { margin-top: 15px; padding-top: 12px; border-top: 1px solid var(--line-color); }
.inspector-pane h4 { margin: 0 0 8px; color: var(--text-primary); font-size: 11px; }
.outline-list { display: grid; gap: 5px; color: var(--text-secondary); font-size: 10px; }
.muted { color: var(--text-secondary); font-size: 11px; }
.graph-view { position: relative; display: grid; gap: 12px; }
.graph-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); border-block: 1px solid var(--line-color); }
.graph-metrics > div { display: grid; gap: 3px; padding: 8px 10px; border-right: 1px solid var(--line-color); }
.graph-metrics strong { color: var(--text-primary); }
.graph-canvas { width: 100%; height: min(680px, calc(100vh - 330px)); min-height: 480px; }
.graph-selection { position: absolute; right: 24px; bottom: 22px; display: grid; gap: 4px; width: min(330px, 34vw); padding: 12px; border: 1px solid var(--view-color-border); background: var(--panel-bg); }
.graph-selection span { color: var(--view-color-primary); font-size: 10px; }
.graph-selection strong { color: var(--text-primary); font-size: 12px; }
.graph-selection p { margin: 0; color: var(--text-secondary); font-size: 11px; line-height: 1.5; }
.references-view { display: grid; gap: 14px; }
.reference-controls { display: flex; align-items: center; justify-content: flex-end; gap: 8px; min-width: 0; }
.reference-controls .el-input { width: min(300px, 32vw); }
.reference-audit-strip { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); border-block: 1px solid var(--line-color); }
.reference-audit-strip > div { display: grid; gap: 3px; padding: 8px 10px; border-right: 1px solid var(--line-color); }
.reference-audit-strip > div:last-child { border-right: 0; }
.reference-audit-strip span { color: var(--text-secondary); font-size: 10px; }
.reference-audit-strip strong { color: var(--text-primary); font-size: 16px; }
.citation-coverage { display: grid; gap: 9px; padding-bottom: 12px; border-bottom: 1px solid var(--line-color); }
.citation-coverage > header { display: flex; align-items: end; justify-content: space-between; gap: 10px; }
.citation-coverage h3 { margin: 3px 0 0; color: var(--text-primary); font-size: 13px; }
.citation-coverage header span, .citation-coverage header small { color: var(--text-secondary); font-size: 10px; }
.coverage-list { display: flex; gap: 6px; overflow-x: auto; padding-bottom: 3px; }
.coverage-list button, .reference-locations button { border: 1px solid var(--view-color-border); border-radius: 4px; color: var(--text-primary); background: var(--view-color-faint); cursor: pointer; }
.coverage-list button { display: grid; flex: 0 0 180px; gap: 3px; padding: 7px 8px; text-align: left; }
.coverage-list button:hover, .reference-locations button:hover { border-color: var(--view-color-primary); }
.coverage-list strong { overflow: hidden; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.coverage-list span { color: var(--text-secondary); font-size: 9px; }
.reference-columns { display: grid; grid-template-columns: minmax(260px, .7fr) minmax(0, 1.5fr); gap: 14px; }
.reference-columns > section { min-width: 0; padding: 13px; border: 1px solid var(--line-color); }
.knowledge-reference-list, .formal-reference-list { max-height: calc(100vh - 330px); margin-top: 12px; overflow-y: auto; }
.knowledge-reference-list article { display: grid; gap: 4px; padding: 10px 0; border-bottom: 1px solid var(--line-color); }
.knowledge-reference-list strong, .formal-reference-list strong { color: var(--text-primary); font-size: 11px; line-height: 1.5; }
.knowledge-reference-list small, .formal-reference-list small { color: var(--text-secondary); font-size: 10px; }
.formal-reference-list article { display: grid; grid-template-columns: 38px minmax(0, 1fr) auto; gap: 8px; align-items: start; padding: 9px 0; border-bottom: 1px solid var(--line-color); }
.formal-reference-list article > span { color: var(--view-color-primary); font-size: 11px; }
.formal-reference-list article > div { display: grid; gap: 3px; }
.reference-locations { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 3px; }
.reference-locations button { padding: 3px 5px; font-size: 9px; }
.uncited-note { color: #e6a23c !important; }
.delivery-view { display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(300px, .75fr); gap: 14px; align-items: start; }
.delivery-main { display: grid; gap: 16px; }
.source-grid { display: grid; gap: 10px; }
.source-grid > div { display: grid; grid-template-columns: 100px minmax(0, 1fr) auto; gap: 10px; align-items: center; padding: 10px 0; border-bottom: 1px solid var(--line-color); }
.source-grid strong { overflow-wrap: anywhere; color: var(--text-primary); font-size: 11px; }
.export-actions { display: flex; gap: 8px; }
.delivery-side { display: grid; gap: 14px; }
.version-list, .issue-list { display: grid; max-height: 280px; margin-top: 10px; overflow-y: auto; }
.version-list > div { display: grid; gap: 3px; padding: 8px 0; border-bottom: 1px solid var(--line-color); }
.version-list strong { color: var(--text-primary); font-size: 11px; }
.version-list small { color: var(--text-secondary); font-size: 10px; }
.issue-list > div { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 8px; align-items: start; padding: 7px 0; border-bottom: 1px solid var(--line-color); color: var(--text-primary); font-size: 10px; line-height: 1.5; }
.pdf-preview-frame { display: block; width: 100%; height: 78vh; border: 1px solid var(--line-color); background: #fff; }
:deep(.pdf-preview-dialog .el-dialog__body) { padding: 0 14px 14px; }
@media (max-width: 1180px) { .reader-view { grid-template-columns: 210px minmax(0, 1fr); } .inspector-pane { grid-column: 1 / -1; } }
@media (max-width: 900px) { .status-strip { grid-template-columns: repeat(3, minmax(0, 1fr)); } .overview-columns, .reference-columns, .delivery-view { grid-template-columns: 1fr; } .reader-view { grid-template-columns: 1fr; } .section-tree, .markdown-body { max-height: none; } .reference-toolbar { align-items: flex-start; flex-direction: column; } .reference-controls { width: 100%; justify-content: space-between; } .reference-controls .el-input { flex: 1; width: auto; } }
@media (max-width: 640px) { .writing-head, .manager-head { align-items: stretch; flex-direction: column; } .head-actions, .manager-head .el-input { width: 100%; } .document-project-list, .project-form-row, .project-form-row.title { grid-template-columns: 1fr; } .status-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); } .brief-grid, .target-chapter-list { grid-template-columns: 1fr; } .target-chapter:nth-child(odd) { border-right: 0; } .graph-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); } .reference-controls { align-items: stretch; flex-direction: column; } .reference-controls .el-input { width: 100%; } .reference-audit-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); } .reference-audit-strip > div { border-bottom: 1px solid var(--line-color); } .formal-reference-list article { grid-template-columns: 34px minmax(0, 1fr); } .formal-reference-list .el-tag { grid-column: 2; justify-self: start; } .source-grid > div { grid-template-columns: 1fr; } }
</style>
