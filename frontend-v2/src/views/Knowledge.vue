<template>
  <div class="knowledge-page">
    <el-row :gutter="12" class="stats-row">
      <el-col :xs="12" :sm="6">
        <el-card class="stat-card" shadow="hover"><span>节点</span><strong>{{ stats?.nodes || 0 }}</strong></el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card class="stat-card" shadow="hover"><span>关系</span><strong>{{ stats?.edges || 0 }}</strong></el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card class="stat-card" shadow="hover"><span>类型</span><strong>{{ typeCount }}</strong></el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card class="stat-card" shadow="hover"><span>索引</span><strong>{{ stats?.available ? '可用' : '异常' }}</strong></el-card>
      </el-col>
    </el-row>

    <el-alert
      v-if="error"
      :title="error"
      type="error"
      show-icon
      :closable="false"
    />

    <div class="workspace-grid">
      <section class="main-column">
        <el-card class="panel workspace-panel" shadow="hover">
          <template #header>
            <div class="panel-header">
              <div>
                <strong>知识工作区</strong>
                <span class="muted"> {{ graphMeta || `当前显示 ${filteredNodes.length} 个节点` }}</span>
              </div>
              <div class="toolbar">
                <el-segmented v-model="graphMode" :options="graphModeOptions" size="small" @change="refreshGraph" />
                <el-select v-model="typeFilter" size="small" clearable placeholder="全部类型" style="width: 128px" @change="refreshGraph">
                  <el-option v-for="[name] in typeEntries" :key="name" :label="name" :value="name" />
                </el-select>
                <el-button size="small" :loading="graphLoading" @click="refreshGraph">重绘</el-button>
              </div>
            </div>
          </template>

          <el-tabs v-model="mainTab" class="workspace-tabs" @tab-change="handleMainTabChange">
            <el-tab-pane label="知识图谱" name="graph">
              <div ref="graphRef" class="graph-canvas" />
            </el-tab-pane>
            <el-tab-pane :label="`节点表 ${filteredNodes.length}`" name="nodes">
              <div class="table-toolbar">
                <el-input
                  v-model="keyword"
                  size="small"
                  clearable
                  placeholder="搜索标题、类型或路径"
                  @keyup.enter="searchNodes"
                />
                <el-button size="small" :loading="loading" @click="searchNodes">搜索</el-button>
              </div>
              <el-table
                v-if="filteredNodes.length"
                :data="filteredNodes"
                size="small"
                height="680"
                highlight-current-row
                @row-click="selectNode"
              >
                <el-table-column label="标题" min-width="260" show-overflow-tooltip>
                  <template #default="{ row }">
                    <div class="node-title">{{ row.title || row.id }}</div>
                    <div class="muted path-text">{{ compactPath(row.path || row.id) }}</div>
                  </template>
                </el-table-column>
                <el-table-column prop="type" label="类型" width="108">
                  <template #default="{ row }">
                    <el-tag size="small" :type="typeTag(row.type)">{{ row.type || '知识' }}</el-tag>
                  </template>
                </el-table-column>
              </el-table>
              <el-empty v-else description="暂无匹配知识节点" />
            </el-tab-pane>

            <el-tab-pane label="知识域" name="domains">
              <div class="domain-grid">
                <button type="button" class="domain-card" :class="{ active: !typeFilter }" @click="setTypeFilter('')">
                  <span>全部知识</span><strong>{{ stats?.nodes || 0 }}</strong>
                </button>
                <button
                  v-for="[name, count] in typeEntries"
                  :key="name"
                  type="button"
                  class="domain-card"
                  :class="{ active: typeFilter === name }"
                  @click="setTypeFilter(name)"
                >
                  <span>{{ name }}</span><strong>{{ count }}</strong>
                  <el-progress :percentage="typePercent(count)" :show-text="false" />
                </button>
              </div>
            </el-tab-pane>

            <el-tab-pane label="节点详情" name="detail">
              <div v-if="selectedNode" class="detail-box detail-box--large">
                <el-tag size="small" :type="typeTag(selectedNode.type)">{{ selectedNode.type || '知识' }}</el-tag>
                <h3>{{ selectedNode.title || selectedNode.id }}</h3>
                <p class="muted">{{ compactPath(selectedNode.path || selectedNode.id) }}</p>
                <el-skeleton v-if="detailLoading" :rows="6" animated />
                <p v-else class="excerpt">{{ selectedContent?.excerpt || '暂无摘要。' }}</p>
              </div>
              <el-empty v-else description="选择一个知识节点查看详情" />
            </el-tab-pane>

            <el-tab-pane :label="`关联节点 ${neighbors.length}`" name="neighbors">
              <div v-if="neighbors.length" class="neighbor-list neighbor-list--grid">
                <button v-for="node in neighbors.slice(0, 36)" :key="node.id" type="button" class="neighbor-item" @click="selectNode(node)">
                  <span>{{ node.title || node.id }}</span>
                  <el-tag size="small">{{ node.type || '知识' }}</el-tag>
                </button>
              </div>
              <el-empty v-else description="暂无局部关系" />
            </el-tab-pane>
          </el-tabs>
        </el-card>
      </section>

      <aside class="side-column">
        <el-card class="panel directory-panel" shadow="hover">
          <template #header>
            <div class="panel-header">
              <div>
                <strong>知识库目录</strong>
                <span class="muted"> 后端 Vault</span>
              </div>
              <div class="toolbar">
                <el-tag size="small" type="info">{{ treeSummary }}</el-tag>
                <el-button size="small" text :loading="treeLoading" @click="loadKnowledgeTree">刷新</el-button>
              </div>
            </div>
          </template>
          <el-skeleton v-if="treeLoading" :rows="4" animated />
          <div v-else-if="knowledgeTree?.available" class="tree-box">
            <button
              v-for="row in directoryRows"
              :key="row.node.id"
              type="button"
              class="directory-row"
              :class="{ 'directory-row--file': row.node.type === 'file' }"
              :style="{ paddingLeft: `${8 + row.depth * 16}px` }"
              @click="selectTreeNode(row.node)"
            >
              <button
                v-if="row.node.type === 'directory'"
                type="button"
                class="directory-row__toggle"
                @click.stop="toggleDirectoryNode(row.node)"
              >
                {{ isDirectoryExpanded(row.node) ? '▾' : '▸' }}
              </button>
              <span v-else class="directory-row__toggle directory-row__toggle--blank" />
              <span class="directory-row__icon">{{ row.node.type === 'directory' ? '目录' : '文件' }}</span>
              <span class="directory-row__name">{{ row.node.name }}</span>
              <el-tag v-if="row.node.type === 'directory'" size="small" type="info">
                {{ row.node.file_count || 0 }}
              </el-tag>
              <el-tag v-else-if="row.node.node_type" size="small">
                {{ row.node.node_type }}
              </el-tag>
            </button>
          </div>
          <el-empty v-else description="暂无知识库目录" />
        </el-card>
      </aside>
    </div>

    <div class="bottom-grid">
      <el-card class="panel" shadow="hover">
        <template #header>
          <div class="panel-header">
            <strong>智能检索</strong>
            <el-segmented v-model="smartMode" :options="smartModeOptions" size="small" />
          </div>
        </template>
        <div class="smart-search">
          <el-input v-model="smartQuery" placeholder="输入问题或关键词" clearable @keyup.enter="runSmartQuery" />
          <el-button type="primary" :loading="smartLoading" @click="runSmartQuery">检索</el-button>
        </div>
        <div v-if="smartError" class="error-text">{{ smartError }}</div>
        <div v-if="smartNodes.length" class="smart-results">
          <button v-for="node in smartNodes" :key="node.id" type="button" class="neighbor-item" @click="selectNode(node)">
            <span>{{ node.title || node.id }}</span>
            <el-tag size="small">{{ node.type || '知识' }}</el-tag>
          </button>
        </div>
      </el-card>

      <el-card class="panel" shadow="hover">
        <template #header>
          <div class="panel-header">
            <strong>知识服务状态</strong>
            <el-button size="small" text @click="loadStackStatus">刷新</el-button>
          </div>
        </template>
        <div class="stack-grid compact-stack">
          <div class="stack-item">
            <strong>Obsidian 图谱</strong>
            <el-tag size="small" :type="stackStatus?.local?.available ? 'success' : 'danger'">
              {{ stackStatus?.local?.available ? '可用' : '异常' }}
            </el-tag>
            <p class="muted">{{ stackStatus?.local?.nodes || 0 }} 节点 · {{ stackStatus?.local?.edges || 0 }} 关系</p>
          </div>
          <div class="stack-item">
            <strong>LightRAG</strong>
            <el-tag size="small" :type="stackStatus?.lightrag?.running ? 'success' : 'info'">
              {{ stackStatus?.lightrag?.running ? '运行中' : '未运行' }}
            </el-tag>
            <p class="muted">{{ stackStatus?.lightrag?.message || stackStatus?.lightrag?.url || '-' }}</p>
          </div>
          <div class="stack-item">
            <strong>OpenSPG KAG</strong>
            <el-tag size="small" :type="stackStatus?.kag?.running ? 'success' : 'info'">
              {{ stackStatus?.kag?.running ? '运行中' : '待配置' }}
            </el-tag>
            <p class="muted">{{ stackStatus?.kag?.message || stackStatus?.kag?.path || '-' }}</p>
          </div>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import * as echarts from 'echarts/core'
import type { EChartsOption } from 'echarts'
import { GraphChart } from 'echarts/charts'
import { LegendComponent, TitleComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { ElMessage } from 'element-plus'
import {
  getKnowledgeGraph,
  getKnowledgeNeighbors,
  getKnowledgeNodeContent,
  getKnowledgeNodes,
  getKnowledgeStackStatus,
  getKnowledgeStats,
  getKnowledgeTree,
  queryKnowledgeStack,
  searchKnowledge,
  type KnowledgeGraph,
  type KnowledgeNeighbors,
  type KnowledgeNode,
  type KnowledgeNodeContent,
  type KnowledgeStackStatus,
  type KnowledgeStats,
  type KnowledgeTree,
  type KnowledgeTreeNode
} from '@/api/openclaw'

echarts.use([CanvasRenderer, GraphChart, LegendComponent, TitleComponent, TooltipComponent])

const stats = ref<KnowledgeStats | null>(null)
const nodes = ref<KnowledgeNode[]>([])
const graph = ref<KnowledgeGraph | null>(null)
const stackStatus = ref<KnowledgeStackStatus | null>(null)
const knowledgeTree = ref<KnowledgeTree | null>(null)
const selectedNode = ref<KnowledgeNode | null>(null)
const selectedContent = ref<KnowledgeNodeContent | null>(null)
const neighbors = ref<KnowledgeNode[]>([])
const keyword = ref('')
const typeFilter = ref('')
const loading = ref(false)
const graphLoading = ref(false)
const treeLoading = ref(false)
const detailLoading = ref(false)
const error = ref('')
const graphRef = ref<HTMLElement>()
const mainTab = ref('graph')
const expandedDirectoryIds = ref<Set<string>>(new Set())
const smartQuery = ref('')
const smartMode = ref('mix')
const graphMode = ref<'concept_backbone' | 'full'>('concept_backbone')
const smartLoading = ref(false)
const smartError = ref('')
const smartNodes = ref<KnowledgeNode[]>([])
const smartModeOptions = ['mix', 'local', 'global']
const graphModeOptions = [
  { label: '概念骨干', value: 'concept_backbone' },
  { label: '全量图谱', value: 'full' }
]

let chart: echarts.EChartsType | null = null

const typeCount = computed(() => Object.keys(stats.value?.entity_types || {}).length)
const typeEntries = computed(() => Object.entries(stats.value?.entity_types || {}).sort((a, b) => b[1] - a[1]))
const treeSummary = computed(() => {
  if (!knowledgeTree.value?.available) return '未加载'
  return `${knowledgeTree.value.total_directories} 目录 · ${knowledgeTree.value.total_files} 文件`
})
const directoryRows = computed(() => {
  const rows: Array<{ node: KnowledgeTreeNode; depth: number }> = []
  const walk = (items: KnowledgeTreeNode[] = [], depth = 0) => {
    for (const node of items) {
      rows.push({ node, depth })
      if (node.type === 'directory' && expandedDirectoryIds.value.has(node.id)) {
        walk(node.children || [], depth + 1)
      }
      if (rows.length >= 260) return
    }
  }
  walk(knowledgeTree.value?.root?.children || [])
  return rows
})
const filteredNodes = computed(() => {
  const key = keyword.value.trim().toLowerCase()
  let list = nodes.value
  if (typeFilter.value) list = list.filter(node => node.type === typeFilter.value)
  if (key) {
    list = list.filter(node => `${node.title} ${node.type} ${node.path} ${node.id}`.toLowerCase().includes(key))
  }
  return list.slice(0, 320)
})
const graphMeta = computed(() => {
  if (!graph.value) return ''
  const prefix = graph.value.mode === 'full' ? '全量' : '概念骨干'
  const conceptCount = graph.value.stats?.concept_count ? ` · ${graph.value.stats.concept_count} 概念` : ''
  return `${prefix} · ${graph.value.nodes.length} 节点 · ${graph.value.total_relations} 关系${conceptCount}`
})

function typePercent(value: number) {
  const total = stats.value?.nodes || 1
  return Math.max(2, Math.round(value / total * 100))
}

function typeTag(type?: string) {
  const tags: Record<string, 'success' | 'warning' | 'info' | 'primary' | 'danger'> = {
    项目: 'primary',
    成果: 'success',
    文献: 'warning',
    论文: 'warning',
    概念: 'info',
    规范: 'danger'
  }
  return tags[type || ''] || 'info'
}

function compactPath(path: string) {
  return path.replace('/Users/apple/工作桌面/knowledge/', '').replace('/Users/apple/WorkSpace/knowledge/', '')
}

async function loadKnowledge() {
  loading.value = true
  error.value = ''
  try {
    const [statsData, nodesData] = await Promise.all([getKnowledgeStats(), getKnowledgeNodes()])
    stats.value = statsData
    nodes.value = nodesData.nodes || []
    if (!selectedNode.value && nodes.value.length) {
      await selectNode(nodes.value[0])
    }
  } catch {
    error.value = '知识库数据加载失败，请确认 Obsidian 图谱索引和后端知识 API 是否正常'
    ElMessage.error(error.value)
  } finally {
    loading.value = false
  }
}

async function loadKnowledgeTree() {
  treeLoading.value = true
  try {
    knowledgeTree.value = await getKnowledgeTree(4, true, 1600)
    expandedDirectoryIds.value = new Set()
  } catch {
    ElMessage.error('知识库目录加载失败')
  } finally {
    treeLoading.value = false
  }
}

async function refreshGraph() {
  graphLoading.value = true
  try {
    graph.value = await getKnowledgeGraph(520, typeFilter.value || undefined, graphMode.value)
    await nextTick()
    renderGraph()
  } catch {
    ElMessage.error('知识图谱加载失败')
  } finally {
    graphLoading.value = false
  }
}

function renderGraph() {
  if (!graphRef.value || !graph.value) return
  if (!chart) {
    chart = echarts.init(graphRef.value)
    chart.on('click', params => {
      const data = params.data as { id?: string } | undefined
      if (params.dataType === 'node' && data?.id) {
        const node = nodes.value.find(item => item.id === data.id) || graph.value?.nodes.find(item => item.id === data.id)
        if (node) selectNode(node)
      }
    })
  }

  const relationIds = new Set<string>()
  for (const relation of graph.value.relations) {
    relationIds.add(relation.source)
    relationIds.add(relation.target)
  }
  const visibleNodes = graph.value.mode === 'concept_backbone'
    ? graph.value.nodes.filter(node => node.backbone || relationIds.has(node.id)).slice(0, 420)
    : graph.value.nodes.filter(node => relationIds.has(node.id) || typeFilter.value).slice(0, 360)
  const categories = Array.from(new Set(visibleNodes.map(node => node.type || '知识'))).map(name => ({ name }))
  const categoryIndex = new Map(categories.map((item, index) => [item.name, index]))
  const allowed = new Set(visibleNodes.map(node => node.id))
  const option: EChartsOption = {
    tooltip: {
      formatter(value) {
        const data = (Array.isArray(value) ? value[0]?.data : value.data) as KnowledgeNode
        const domain = data.domain ? `<br/>${data.domain}` : ''
        return `${data.title || data.id}<br/>${data.type || '知识'}${domain}`
      }
    },
    legend: { top: 0, type: 'scroll' },
    series: [
      {
        type: 'graph',
        layout: 'force',
        roam: true,
        draggable: true,
        categories,
        data: visibleNodes.map(node => ({
          id: node.id,
          name: node.title || node.id,
          title: node.title,
          type: node.type,
          path: node.path,
          category: categoryIndex.get(node.type || '知识') || 0,
          symbolSize: node.backbone
            ? Math.max(22, Math.min(42, 24 + (node.domain ? 4 : 0)))
            : Math.max(10, Math.min(26, 10 + (stats.value?.entity_types?.[node.type] || 1) / 36))
        })),
        links: graph.value.relations
          .filter(relation => allowed.has(relation.source) && allowed.has(relation.target))
          .slice(0, 520)
          .map(relation => ({
            source: relation.source,
            target: relation.target,
            name: relation.type || relation.relation || '关联',
            value: relation.weight || 1
          })),
        force: {
          repulsion: graph.value.mode === 'concept_backbone' ? 260 : 180,
          edgeLength: graph.value.mode === 'concept_backbone' ? 128 : 104,
          gravity: 0.08
        },
        label: { show: true, fontSize: 10, overflow: 'truncate', width: 90 },
        lineStyle: { color: 'source', opacity: 0.34, curveness: 0.12 },
        emphasis: { focus: 'adjacency' }
      }
    ]
  }
  chart.resize()
  chart.setOption(option, true)
}

async function searchNodes() {
  const q = keyword.value.trim()
  if (!q) {
    await loadKnowledge()
    return
  }
  loading.value = true
  try {
    const result = await searchKnowledge(q, 160, typeFilter.value || undefined)
    nodes.value = result.nodes || []
    if (nodes.value.length) await selectNode(nodes.value[0])
  } catch {
    ElMessage.error('知识节点搜索失败')
  } finally {
    loading.value = false
  }
}

async function setTypeFilter(type: string) {
  typeFilter.value = type
  await refreshGraph()
}

async function handleMainTabChange() {
  await nextTick()
  resizeGraph()
}

function isDirectoryExpanded(node: KnowledgeTreeNode) {
  return expandedDirectoryIds.value.has(node.id)
}

function toggleDirectoryNode(node: KnowledgeTreeNode) {
  if (node.type !== 'directory') return
  const next = new Set(expandedDirectoryIds.value)
  if (next.has(node.id)) next.delete(node.id)
  else next.add(node.id)
  expandedDirectoryIds.value = next
}

async function selectTreeNode(item: KnowledgeTreeNode) {
  if (item.type === 'directory') {
    keyword.value = item.relative_path || ''
    if (keyword.value) await searchNodes()
    else await loadKnowledge()
    return
  }
  const matched = findNodeForTreeItem(item)
  await selectNode(matched)
}

function findNodeForTreeItem(item: KnowledgeTreeNode): KnowledgeNode {
  const relative = item.relative_path || ''
  const stem = relative.replace(/\.[^.]+$/, '')
  const candidates = new Set([item.node_id, relative, stem].filter(Boolean) as string[])
  const matched = nodes.value.find(node => {
    const nodePath = compactPath(node.path || node.id)
    return candidates.has(node.id) || candidates.has(node.title) || nodePath === relative || nodePath === stem
  })
  if (matched) return matched
  return {
    id: item.node_id || relative,
    title: item.name.replace(/\.[^.]+$/, ''),
    type: item.node_type || '文档',
    path: item.path
  }
}

async function selectNode(node: KnowledgeNode) {
  selectedNode.value = node
  selectedContent.value = null
  neighbors.value = []
  detailLoading.value = true
  try {
    const [content, neighborData] = await Promise.allSettled([
      getKnowledgeNodeContent(node.id),
      getKnowledgeNeighbors(node.id)
    ])
    if (content.status === 'fulfilled') selectedContent.value = content.value
    if (neighborData.status === 'fulfilled') {
      const data = neighborData.value as KnowledgeNeighbors
      neighbors.value = data.neighbors || []
    }
  } finally {
    detailLoading.value = false
  }
}

async function loadStackStatus() {
  try {
    stackStatus.value = await getKnowledgeStackStatus()
  } catch {
    stackStatus.value = null
  }
}

async function runSmartQuery() {
  const query = smartQuery.value.trim()
  if (!query) {
    smartError.value = '请输入要检索的问题'
    return
  }
  smartLoading.value = true
  smartError.value = ''
  smartNodes.value = []
  try {
    const result = await queryKnowledgeStack(query, smartMode.value, 8)
    const localNodes = result.local?.nodes || []
    const data = result.data || {}
    const entities = Array.isArray(data.entities) ? data.entities : []
    smartNodes.value = localNodes.length
      ? localNodes
      : entities.slice(0, 8).map((item: Record<string, unknown>) => ({
          id: String(item.entity_name || item.id || item.name || ''),
          title: String(item.entity_name || item.name || item.id || ''),
          type: String(item.entity_type || item.type || '知识'),
          path: ''
        }))
  } catch {
    smartError.value = '智能检索失败，请确认 LightRAG 与 Ollama 是否可用'
  } finally {
    smartLoading.value = false
  }
}

function resizeGraph() {
  chart?.resize()
}

onMounted(async () => {
  await Promise.all([loadKnowledge(), loadKnowledgeTree(), refreshGraph(), loadStackStatus()])
  window.addEventListener('resize', resizeGraph)
})

onUnmounted(() => {
  window.removeEventListener('resize', resizeGraph)
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
.knowledge-page {
  display: grid;
  gap: 12px;
}

.stats-row {
  row-gap: 12px;
}

.stat-card,
.panel {
  border-radius: 8px;
}

.stat-card :deep(.el-card__body) {
  display: grid;
  gap: 4px;
  min-height: 58px;
  padding: 12px 16px;
}

.stat-card span,
.muted {
  color: #909399;
  font-size: 13px;
}

.stat-card strong {
  color: #303133;
  font-size: 22px;
}

.workspace-grid {
  display: grid;
  grid-template-columns: minmax(720px, 1fr) minmax(460px, 520px);
  gap: 16px;
  align-items: start;
}

.main-column,
.side-column,
.bottom-grid {
  display: grid;
  gap: 14px;
}

.bottom-grid {
  grid-template-columns: minmax(0, 1fr) minmax(360px, 0.8fr);
  align-items: start;
}

.panel-header,
.toolbar,
.stack-grid,
.smart-search {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.toolbar {
  justify-content: flex-end;
  flex-wrap: wrap;
}

.workspace-panel,
.directory-panel {
  min-height: 760px;
}

.workspace-tabs :deep(.el-tabs__header) {
  margin-bottom: 10px;
}

.workspace-tabs :deep(.el-tabs__content) {
  min-height: 678px;
}

.table-toolbar,
.tab-header-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.table-toolbar :deep(.el-input) {
  max-width: 360px;
}

.graph-canvas {
  height: 678px;
  min-height: 678px;
  width: 100%;
}

.workspace-panel :deep(.el-card__body),
.directory-panel :deep(.el-card__body) {
  padding: 10px 14px 14px;
}

.domain-card,
.neighbor-item {
  width: 100%;
  border: 1px solid #e4e7ed;
  background: #fff;
  border-radius: 8px;
  padding: 9px 10px;
  display: grid;
  gap: 6px;
  text-align: left;
  cursor: pointer;
}

.domain-card + .domain-card,
.neighbor-item + .neighbor-item {
  margin-top: 8px;
}

.domain-card {
  grid-template-columns: 1fr auto;
  align-items: center;
}

.domain-card :deep(.el-progress) {
  grid-column: 1 / -1;
}

.domain-card.active,
.neighbor-item:hover {
  border-color: #409eff;
  background: #ecf5ff;
}

.tree-box {
  max-height: 674px;
  overflow: auto;
}

.tree-box :deep(.el-tree) {
  background: transparent;
}

.tree-box :deep(.el-tree-node__content) {
  min-height: 30px;
  border-radius: 6px;
}

.tree-box :deep(.el-tree-node__content:hover) {
  background: #ecf5ff;
}

.directory-row {
  width: 100%;
  min-height: 30px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  display: flex;
  align-items: center;
  gap: 8px;
  text-align: left;
  cursor: pointer;
}

.directory-row:hover {
  background: #ecf5ff;
}

.directory-row__toggle {
  width: 18px;
  height: 22px;
  border: 0;
  padding: 0;
  border-radius: 4px;
  background: transparent;
  color: #909399;
  cursor: pointer;
  line-height: 20px;
}

.directory-row__toggle:hover {
  background: #d9ecff;
  color: #409eff;
}

.directory-row__toggle--blank {
  flex: 0 0 18px;
}

.directory-row--file {
  color: #606266;
}

.directory-row__icon {
  flex: 0 0 auto;
  color: #909399;
  font-size: 12px;
  width: 26px;
}

.directory-row__name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tree-node {
  width: 100%;
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 13px;
}

.tree-node::before {
  flex: 0 0 auto;
  color: #909399;
  font-size: 12px;
}

.tree-node--directory::before {
  content: '目录';
}

.tree-node--file::before {
  content: '文件';
}

.tree-node__name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.domain-grid,
.neighbor-list--grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 10px;
}

.domain-grid .domain-card + .domain-card,
.neighbor-list--grid .neighbor-item + .neighbor-item {
  margin-top: 0;
}

.node-title {
  font-weight: 700;
  overflow-wrap: anywhere;
}

.path-text {
  overflow-wrap: anywhere;
}

.detail-box h3 {
  margin: 10px 0 6px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.detail-box--large {
  max-width: 860px;
}

.excerpt {
  margin: 12px 0 0;
  line-height: 1.65;
  color: #303133;
  white-space: pre-wrap;
}

.neighbor-list,
.smart-results {
  display: grid;
  gap: 8px;
  max-height: 180px;
  overflow: auto;
}

.neighbor-item {
  grid-template-columns: 1fr auto;
  align-items: center;
}

.neighbor-item span {
  overflow-wrap: anywhere;
}

.stack-grid {
  align-items: stretch;
}

.compact-stack {
  flex-direction: column;
}

.stack-item {
  flex: 1;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 10px;
  display: grid;
  gap: 6px;
}

.smart-search {
  align-items: stretch;
}

.smart-search :deep(.el-input) {
  flex: 1;
}

.error-text {
  color: #f56c6c;
  margin-top: 10px;
  font-size: 13px;
}

@media (max-width: 1120px) {
  .workspace-grid,
  .bottom-grid {
    grid-template-columns: 1fr;
  }

  .side-column {
    grid-template-columns: 1fr;
  }

  .workspace-panel,
  .directory-panel {
    min-height: auto;
  }
}

@media (max-width: 720px) {
  .panel-header,
  .toolbar,
  .smart-search,
  .stack-grid,
  .table-toolbar,
  .tab-header-line {
    align-items: stretch;
    flex-direction: column;
  }

  .toolbar :deep(.el-input),
  .toolbar :deep(.el-select),
  .table-toolbar :deep(.el-input) {
    width: 100% !important;
    max-width: none;
  }

  .graph-canvas,
  .workspace-tabs :deep(.el-tabs__content) {
    min-height: 420px;
    height: 420px;
  }
}
</style>
