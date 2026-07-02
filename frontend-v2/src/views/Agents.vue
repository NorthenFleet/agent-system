<template>
  <div class="agents-page">
    <el-row :gutter="16" class="stats-row">
      <el-col :xs="12" :md="6">
        <el-card class="stat-card" shadow="hover"><span>注册智能体</span><strong>{{ registeredAgentCount }}</strong></el-card>
      </el-col>
      <el-col :xs="12" :md="6">
        <el-card class="stat-card" shadow="hover"><span>项目中</span><strong>{{ busyAgentCount }}</strong></el-card>
      </el-col>
      <el-col :xs="12" :md="6">
        <el-card class="stat-card" shadow="hover"><span>组织节点</span><strong>{{ visibleNodeCount }}</strong></el-card>
      </el-col>
      <el-col :xs="12" :md="6">
        <el-card class="stat-card" shadow="hover"><span>规划占位</span><strong>{{ plannedNodeCount }}</strong></el-card>
      </el-col>
    </el-row>

    <el-card class="overview-panel" shadow="hover">
      <div class="overview-head">
        <div>
          <div class="overview-title">智能体组织看板</div>
          <div class="muted">每一行表示一个组织层级；卡片保留角色、状态、职责、当前项目任务和下级关系。</div>
        </div>
        <div class="overview-actions">
          <el-switch v-model="showPlanned" size="small" active-text="显示规划节点" />
          <el-button size="small" type="primary" :loading="loading" @click="loadAll">刷新</el-button>
        </div>
      </div>
    </el-card>

    <div class="agent-board-layout">
      <section>
        <el-skeleton v-if="loading" :rows="12" animated />
        <el-empty v-else-if="!hierarchyRows.length" description="暂无组织数据" />
        <div v-else class="hierarchy-board">
          <section v-for="level in hierarchyRows" :key="level.depth" class="level-row">
            <div class="level-head">
              <span class="level-index">第 {{ level.depth + 1 }} 层</span>
              <strong>{{ levelTitle(level.depth) }}</strong>
              <span>{{ level.cards.length }} 个节点</span>
            </div>
            <div class="agent-card-grid">
              <button
                v-for="card in level.cards"
                :key="card.node.id"
                class="agent-card"
                :class="{
                  active: selectedNodeId === card.node.id,
                  planned: card.node.planned,
                  group: card.node.node_type === 'group'
                }"
                @click="selectNode(card.node)"
              >
                <span class="card-top">
                  <span class="agent-avatar">{{ nodeEmoji(card.node) }}</span>
                  <span class="agent-title">
                    <strong>{{ nodeName(card.node) }}</strong>
                    <small>{{ card.node.agent_id || card.node.id }}</small>
                  </span>
                  <el-tag v-if="card.node.planned" size="small" type="info">规划</el-tag>
                  <el-tag v-else-if="card.agent" size="small" :type="statusType(card.agent.status)">{{ statusLabel(card.agent.status) }}</el-tag>
                  <el-tag v-else size="small" type="info">{{ card.node.node_type === 'group' ? '分组' : '节点' }}</el-tag>
                </span>

                <span class="card-role">{{ nodeSubtitle(card.node, card.agent, card.childCount) }}</span>

                <span v-if="card.agent" class="card-fields">
                  <span>
                    <b>职责</b>
                    <em>{{ responsibilities(card.agent).slice(0, 2).join(' / ') }}</em>
                  </span>
                  <span>
                    <b>当前任务</b>
                    <em>{{ card.agent.current_task_title || card.agent.current_task || '待分配' }}</em>
                  </span>
                  <span>
                    <b>项目</b>
                    <em>{{ card.agent.current_project_name || '暂无项目' }}</em>
                  </span>
                </span>

                <span v-else class="card-fields">
                  <span>
                    <b>类型</b>
                    <em>{{ card.node.node_type === 'group' ? '组织分组' : '组织成员' }}</em>
                  </span>
                  <span>
                    <b>说明</b>
                    <em>{{ card.node.title || '待配置' }}</em>
                  </span>
                </span>

                <span class="card-footer">
                  <span>{{ card.childCount }} 个下级</span>
                  <span v-if="card.agent?.current_project_id" class="project-link" @click.stop="openAgentProjectTask(card.agent)">查看任务</span>
                </span>
              </button>
            </div>
          </section>
        </div>
      </section>

      <aside class="agent-memory-panel">
        <el-card class="memory-card" shadow="hover">
          <div class="selected-head">
            <div>
              <div class="field-title">{{ selectedAgent ? '智能体档案' : '组织节点' }}</div>
              <div class="selected-name">{{ selectedTitle }}</div>
              <div class="muted">{{ selectedSubtitle }}</div>
            </div>
            <el-tag v-if="selectedAgent" :type="statusType(selectedAgent.status)" size="small">{{ statusLabel(selectedAgent.status) }}</el-tag>
            <el-tag v-else-if="selectedNode?.planned" size="small" type="info">规划占位</el-tag>
          </div>

          <div v-if="selectedAgent" class="detail-block">
            <div class="field-title">职责</div>
            <div class="responsibility-list">
              <span v-for="item in responsibilities(selectedAgent)" :key="`selected-${item}`" class="responsibility-chip">{{ item }}</span>
            </div>
          </div>

          <div v-if="selectedAgent?.current_project_id" class="current-work">
            <div class="field-title">当前项目任务</div>
            <div class="work-title">{{ selectedAgent.current_task_title || selectedAgent.current_task || '未命名任务' }}</div>
            <div class="muted">{{ selectedAgent.current_development_point_title || selectedAgent.current_project_name }}</div>
            <el-button size="small" type="primary" class="work-button" @click="openAgentProjectTask(selectedAgent)">跳转到项目任务</el-button>
          </div>

          <div v-if="selectedChildren.length" class="detail-block">
            <div class="field-title">下级节点</div>
            <div class="child-list">
              <button v-for="child in selectedChildren" :key="child.id" class="child-chip" @click="selectNode(child)">
                {{ nodeEmoji(child) }} {{ nodeName(child) }}
              </button>
            </div>
          </div>
        </el-card>

        <el-card class="memory-card" shadow="hover">
          <div class="memory-section-title">
            <span>短期记忆</span>
            <el-button size="small" text :loading="memoryLoading" :disabled="!selectedAgent" @click="loadAgentMemory(selectedAgent)">刷新</el-button>
          </div>
          <div v-if="shortMemory.length" class="memory-list">
            <div v-for="(mem, idx) in shortMemory" :key="`short-${idx}`" class="memory-item">
              <div class="memory-item-title">{{ memoryText(mem) }}</div>
              <div class="muted">{{ memoryDate(mem) }}</div>
            </div>
          </div>
          <div v-else class="muted">{{ selectedAgent ? '暂无短期记忆' : '请选择一个已注册智能体查看记忆' }}</div>
        </el-card>

        <el-card class="memory-card" shadow="hover">
          <div class="memory-section-title">长期记忆 / 历史</div>
          <div v-if="longMemory.length" class="memory-list">
            <div v-for="(mem, idx) in longMemory" :key="`long-${idx}`" class="memory-history-line">
              {{ memoryDate(mem) }} · {{ memoryText(mem) }}
            </div>
          </div>
          <div v-else class="muted">暂无长期记忆</div>
        </el-card>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  getAgentDashboard,
  getAgentMemory,
  getAgentOrganization,
  type AgentDashboardItem,
  type AgentMemoryItem,
  type AgentOrganization,
  type AgentOrganizationNode
} from '@/api/openclaw'

interface HierarchyCard {
  node: AgentOrganizationNode
  agent?: AgentDashboardItem
  childCount: number
}

interface HierarchyRow {
  depth: number
  cards: HierarchyCard[]
}

const router = useRouter()
const loading = ref(false)
const memoryLoading = ref(false)
const showPlanned = ref(true)
const agents = ref<AgentDashboardItem[]>([])
const organization = ref<AgentOrganization | null>(null)
const selectedNodeId = ref('')
const agentMemory = ref<AgentMemoryItem[]>([])

const agentById = computed(() => {
  const map = new Map<string, AgentDashboardItem>()
  agents.value.forEach(agent => map.set(agentId(agent), agent))
  return map
})

const childrenByParent = computed(() => {
  const map = new Map<string, AgentOrganizationNode[]>()
  for (const node of organization.value?.nodes || []) {
    if (!showPlanned.value && node.planned) continue
    const key = node.parent_id || ''
    if (!map.has(key)) map.set(key, [])
    map.get(key)!.push(node)
  }
  for (const list of map.values()) {
    list.sort((a, b) => (a.order || 999) - (b.order || 999) || a.name.localeCompare(b.name, 'zh-CN'))
  }
  return map
})

const hierarchyRows = computed(() => {
  if (!organization.value) return []
  const rows: HierarchyRow[] = []
  const pendingLevels: AgentOrganizationNode[][] = [[organization.value.root]]
  let depth = 0

  while (pendingLevels.length) {
    const currentLevel = expandStructuralGroups(pendingLevels.shift() || [])
    if (!currentLevel.length) continue

    const displayNodes = currentLevel.filter(node => node.node_type !== 'group')
    if (displayNodes.length) {
      rows.push({
        depth,
        cards: displayNodes.map(node => ({
          node,
          agent: node.agent_id ? agentById.value.get(node.agent_id) : undefined,
          childCount: visibleChildren(node).length
        }))
      })
      depth += 1
    }

    const children = currentLevel.flatMap(node => childrenByParent.value.get(node.id) || [])
    if (children.length) pendingLevels.push(children)
  }
  return rows
})

function expandStructuralGroups(nodes: AgentOrganizationNode[]) {
  let expanded = nodes
  while (expanded.length && expanded.every(node => node.node_type === 'group')) {
    expanded = expanded.flatMap(node => childrenByParent.value.get(node.id) || [])
  }
  return expanded
}

function visibleChildren(node: AgentOrganizationNode): AgentOrganizationNode[] {
  const direct = childrenByParent.value.get(node.id) || []
  return direct.flatMap(child => {
    if (child.node_type !== 'group') return [child]
    return (childrenByParent.value.get(child.id) || []).filter(grandchild => grandchild.node_type !== 'group')
  })
}

const visibleNodeCount = computed(() => hierarchyRows.value.reduce((total, row) => total + row.cards.length, 0))
const visibleAgents = computed(() => hierarchyRows.value.flatMap(row => row.cards.map(card => card.agent).filter(Boolean) as AgentDashboardItem[]))
const registeredAgentCount = computed(() => visibleAgents.value.length)
const busyAgentCount = computed(() => visibleAgents.value.filter(hasCurrentWork).length)
const plannedNodeCount = computed(() => (organization.value?.nodes || []).filter(node => node.planned).length)
const selectedNode = computed(() => {
  if (!organization.value) return null
  if (selectedNodeId.value === organization.value.root.id) return organization.value.root
  return organization.value.nodes.find(node => node.id === selectedNodeId.value) || organization.value.root
})
const selectedAgent = computed(() => selectedNode.value?.agent_id ? agentById.value.get(selectedNode.value.agent_id) || null : null)
const selectedChildren = computed(() => selectedNode.value ? visibleChildren(selectedNode.value) : [])
const selectedTitle = computed(() => selectedNode.value ? `${nodeEmoji(selectedNode.value)} ${nodeName(selectedNode.value)}` : '未选择')
const selectedSubtitle = computed(() => {
  if (!selectedNode.value) return ''
  if (selectedAgent.value) return `${selectedNode.value.title || selectedAgent.value.role || '未配置角色'} · ${selectedAgent.value.current_task_title || selectedAgent.value.current_task || '待分配'}`
  return selectedNode.value.title || `${selectedChildren.value.length} 个下级节点`
})


const sortedMemory = computed(() => agentMemory.value.slice().sort((a, b) => {
  const ad = new Date(memoryDate(a) || 0).getTime()
  const bd = new Date(memoryDate(b) || 0).getTime()
  return bd - ad
}))
const shortMemory = computed(() => sortedMemory.value.slice(0, 3))
const longMemory = computed(() => sortedMemory.value.slice(3, 11))

watch(selectedAgent, agent => {
  if (agent) loadAgentMemory(agent)
  else agentMemory.value = []
})

function agentId(agent: AgentDashboardItem) {
  return agent.id || agent.agent_id || agent.name
}

function nodeName(node: AgentOrganizationNode) {
  const agent = node.agent_id ? agentById.value.get(node.agent_id) : null
  return node.name || agent?.name || agent?.agent_name || node.id
}

function nodeEmoji(node: AgentOrganizationNode) {
  if (node.emoji) return node.emoji
  if (node.agent_id) return agentEmoji(node.agent_id)
  return node.node_type === 'group' ? '📂' : '👤'
}

function nodeSubtitle(node: AgentOrganizationNode, agent?: AgentDashboardItem, childCount = 0) {
  if (node.planned) return `${node.title || '规划节点'} · 未注册`
  if (agent) return `${node.title || agent.role || '未配置角色'} · ${agent.current_task_title || agent.current_task || '待分配'}`
  if (node.node_type === 'group') return `${node.title || '组织分组'} · ${childCount} 个节点`
  return node.title || '组织节点'
}

function levelTitle(depth: number) {
  const labels: Record<number, string> = {
    0: '负责人',
    1: '总协调',
    2: '项目经理',
    3: '开发执行',
    4: '保障'
  }
  return labels[depth] || '扩展层级'
}

function agentEmoji(id: string) {
  const map: Record<string, string> = {
    optimus: '🤖',
    main: '🌙',
    bumblebee: '🐝',
    leonardo: '🟦',
    raphael: '🟥',
    donatello: '🟪',
    michelangelo: '🟧',
    ironhide: '🛡️',
    perceptor: '🚗',
    ratchet: '🚑',
    jazz: '🎷',
    soundwave: '🔷',
    wheeljack: '🔧',
    shockwave: '🟣',
    'ultra-magnus': '🔵',
    'wheeljack-leonardo': '🟦',
    'wheeljack-raphael': '🟥',
    'wheeljack-donatello': '🟪',
    'wheeljack-michelangelo': '🟧'
  }
  return map[id] || '👤'
}

function hasCurrentWork(agent: AgentDashboardItem) {
  return Boolean(agent.current_project_id || agent.current_task_id || agent.current_development_point_id)
}

function statusType(status: string): '' | 'success' | 'warning' | 'info' | 'danger' {
  const map: Record<string, '' | 'success' | 'warning' | 'info' | 'danger'> = {
    online: 'success',
    busy: 'warning',
    idle: 'info',
    pending: 'warning',
    offline: 'danger'
  }
  return map[status] || 'info'
}

function statusLabel(status: string) {
  const map: Record<string, string> = {
    online: '在线',
    busy: '忙碌',
    idle: '空闲',
    pending: '待命',
    offline: '离线',
    unknown: '未知'
  }
  return map[status] || status || '未知'
}

function responsibilities(agent: AgentDashboardItem) {
  const direct = agent.responsibilities || agent.profile?.responsibilities || agent.metadata?.responsibilities
  if (Array.isArray(direct) && direct.length) return direct.map(item => String(item).trim()).filter(Boolean)
  if (agent.role && String(agent.role).trim()) return [String(agent.role).trim()]
  return ['待配置职责']
}

function selectNode(node: AgentOrganizationNode) {
  selectedNodeId.value = node.id
}

async function loadAll() {
  loading.value = true
  try {
    const [orgData, agentData] = await Promise.all([getAgentOrganization(), getAgentDashboard()])
    organization.value = orgData
    agents.value = agentData.agents || []
    if (!selectedNodeId.value) selectedNodeId.value = orgData.root.id
  } catch {
    ElMessage.error('智能体组织数据加载失败')
  } finally {
    loading.value = false
  }
}

async function loadAgentMemory(agent: AgentDashboardItem | null) {
  if (!agent) {
    agentMemory.value = []
    return
  }
  memoryLoading.value = true
  try {
    const data = await getAgentMemory(agentId(agent))
    agentMemory.value = Array.isArray(data.memory) ? data.memory : []
  } catch {
    agentMemory.value = Array.isArray(agent.memory) ? agent.memory : []
  } finally {
    memoryLoading.value = false
  }
}

function memoryText(item: AgentMemoryItem) {
  if (!item) return '-'
  if (typeof item === 'string') return item
  return item.text || item.title || item.content || item.summary || JSON.stringify(item)
}

function memoryDate(item: AgentMemoryItem) {
  if (!item || typeof item === 'string') return ''
  return item.date || item.created_at || item.updated_at || item.section || ''
}

function openAgentProjectTask(agent: AgentDashboardItem) {
  if (!agent.current_project_id) {
    ElMessage.warning('该智能体当前没有匹配的项目任务')
    return
  }
  router.push({
    path: '/projects',
    query: {
      project_id: agent.current_project_id,
      task_id: agent.current_task_id || undefined,
      agent_id: agentId(agent)
    }
  })
}

onMounted(loadAll)
</script>

<style scoped>
.agents-page {
  display: grid;
  gap: 16px;
}

.stats-row {
  margin-bottom: 0;
}

.stat-card,
.overview-panel,
.memory-card {
  border-radius: 8px;
}

.stat-card :deep(.el-card__body) {
  display: grid;
  gap: 8px;
}

.stat-card span,
.muted,
.field-title {
  color: #909399;
  font-size: 13px;
}

.stat-card strong {
  color: #303133;
  font-size: 24px;
}

.overview-head,
.selected-head,
.memory-section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.overview-title {
  color: #303133;
  font-weight: 800;
  margin-bottom: 4px;
}

.overview-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  justify-content: flex-end;
  align-items: center;
}

.agent-board-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 16px;
  align-items: start;
}

.hierarchy-board {
  display: grid;
  gap: 14px;
}

.level-row {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  background: #fff;
  padding: 12px;
}

.level-head {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #909399;
  font-size: 13px;
  margin-bottom: 10px;
}

.level-head strong {
  color: #303133;
  font-size: 14px;
}

.level-index {
  color: #409eff;
  font-weight: 800;
}

.agent-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 10px;
}

.agent-card {
  width: 100%;
  min-height: 182px;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  background: #fff;
  padding: 12px;
  display: grid;
  grid-template-rows: auto auto 1fr auto;
  gap: 10px;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s, background 0.15s;
}

.agent-card:hover,
.agent-card.active {
  border-color: #409eff;
  box-shadow: 0 4px 16px rgba(64, 158, 255, 0.12);
}

.agent-card.active {
  background: #f5f9ff;
}

.agent-card.group {
  background: #fafafa;
}

.agent-card.planned {
  opacity: 0.68;
  background: #fbfbfb;
}

.card-top {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
}

.agent-avatar {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  background: #f5f7fa;
  flex: 0 0 auto;
}

.agent-title {
  display: grid;
  gap: 2px;
  min-width: 0;
  flex: 1;
}

.agent-title strong,
.card-role,
.work-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-title strong {
  color: #303133;
  font-size: 15px;
}

.agent-title small,
.card-role,
.card-fields b,
.card-fields em,
.card-footer {
  font-size: 12px;
}

.agent-title small,
.card-fields b,
.card-footer {
  color: #909399;
}

.card-role {
  color: #606266;
}

.card-fields {
  display: grid;
  gap: 6px;
}

.card-fields span {
  min-width: 0;
  display: grid;
  grid-template-columns: 56px minmax(0, 1fr);
  gap: 8px;
  align-items: baseline;
}

.card-fields em {
  color: #606266;
  font-style: normal;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  border-top: 1px dashed #ebeef5;
  padding-top: 8px;
}

.project-link {
  color: #409eff;
  font-weight: 700;
}

.agent-memory-panel {
  position: sticky;
  top: 12px;
  display: grid;
  gap: 14px;
}

.selected-name {
  color: #303133;
  font-weight: 800;
  margin: 3px 0;
}

.detail-block {
  margin-top: 12px;
  display: grid;
  gap: 7px;
}

.responsibility-list,
.child-list {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.responsibility-chip,
.child-chip {
  border: 1px solid #dcdfe6;
  border-radius: 999px;
  padding: 3px 8px;
  color: #606266;
  background: #fafafa;
  font-size: 12px;
}

.child-chip {
  cursor: pointer;
}

.current-work {
  margin-top: 12px;
  padding: 12px;
  border: 1px solid rgba(64, 158, 255, 0.24);
  border-radius: 8px;
  background: rgba(64, 158, 255, 0.08);
}

.work-title {
  color: #303133;
  font-weight: 700;
  margin-top: 4px;
}

.work-button {
  width: 100%;
  margin-top: 10px;
}

.memory-section-title {
  color: #303133;
  font-weight: 800;
  margin-bottom: 10px;
}

.memory-list {
  display: grid;
  gap: 8px;
}

.memory-item {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 10px;
}

.memory-item-title {
  color: #606266;
  font-size: 13px;
  line-height: 1.5;
}

.memory-history-line {
  color: #606266;
  font-size: 13px;
  line-height: 1.6;
  border-bottom: 1px dashed #ebeef5;
  padding-bottom: 6px;
}

@media (max-width: 1100px) {
  .agent-board-layout {
    grid-template-columns: 1fr;
  }

  .agent-memory-panel {
    position: static;
  }
}
</style>
