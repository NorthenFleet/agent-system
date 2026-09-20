<template>
  <div class="agents-page">
    <!-- 页面标题 + 统计卡片 -->
    <div class="page-header">
      <div class="page-title">
        <h1>🤖 智能体管理</h1>
        <p class="page-desc">Agent 状态监控 · 实时状态 · 任务追踪</p>
      </div>
      <div class="page-actions">
        <el-button
          type="primary"
          size="small"
          :loading="agentsStore.loading"
          :icon="Refresh"
          @click="refresh"
        >
          刷新
        </el-button>
        <span class="ws-indicator" :class="{ connected: agentsStore.wsConnected }">
          <span class="ws-dot"></span>
          {{ agentsStore.wsConnected ? '实时推送' : '轮询模式' }}
        </span>
      </div>
    </div>

    <el-tabs v-model="activeTab" class="agents-tabs">
      <el-tab-pane label="组织架构" name="team">
    <!-- 统计摘要 -->
    <el-row :gutter="16" class="stats-row">
      <el-col :xs="12" :sm="6">
        <div class="stat-card stat-total">
          <span class="stat-label">全部</span>
          <span class="stat-value">{{ total }}</span>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6">
        <div class="stat-card stat-online">
          <span class="stat-label">在线</span>
          <span class="stat-value">{{ onlineCount }}</span>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6">
        <div class="stat-card stat-busy">
          <span class="stat-label">忙碌</span>
          <span class="stat-value">{{ busyCount }}</span>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6">
        <div class="stat-card stat-offline">
          <span class="stat-label">离线</span>
          <span class="stat-value">{{ offlineCount }}</span>
        </div>
      </el-col>
    </el-row>

    <!-- 状态筛选 -->
    <div class="filter-bar">
      <el-button-group>
        <el-button
          v-for="f in filterOptions"
          :key="f.value"
          :type="activeFilter === f.value ? 'primary' : 'default'"
          :plain="activeFilter !== f.value"
          size="small"
          @click="activeFilter = f.value"
        >
          {{ f.icon }} {{ f.label }}
          <span class="filter-badge">{{ filterCount(f.value) }}</span>
        </el-button>
      </el-button-group>
    </div>

    <section v-if="activeFilter === 'all' && organizationGroups.length" class="organization-board">
      <div class="section-head">
        <div>
          <h2>组织架构</h2>
          <p>来自智能体组织配置，运行态心跳会自动合并到对应成员。</p>
        </div>
        <el-tag type="info">{{ organizationAgentCount }} 个成员</el-tag>
      </div>
      <div class="organization-grid">
        <article v-for="group in organizationGroups" :key="group.id" class="organization-group">
          <header>
            <strong>{{ group.name }}</strong>
            <span>{{ group.title || `${group.members.length} 个成员` }}</span>
          </header>
          <div class="organization-members">
            <button
              v-for="member in group.members"
              :key="member.id"
              class="org-member"
              @click="selectAgent(member.agent.agent_id)"
            >
              <span class="org-avatar" :style="{ background: avatarColor(member.agent.agent_id) }">
                {{ member.emoji || agentEmoji(member.agent.agent_id) }}
              </span>
              <span class="org-member-main">
                <strong>{{ member.name }}</strong>
                <small>{{ member.title || member.agent.metadata?.role || member.agent.agent_id }}</small>
              </span>
              <el-tag size="small" :type="statusType(member.agent.status)">
                {{ statusLabel(member.agent.status) }}
              </el-tag>
            </button>
          </div>
        </article>
      </div>
    </section>

    <!-- Loading 状态 -->
    <div v-if="agentsStore.loading && filteredAgents.length === 0" class="loading-wrapper">
      <el-icon class="loading-spinner" :size="40"><Loading /></el-icon>
      <p class="loading-text">加载智能体数据...</p>
    </div>

    <!-- 空状态 -->
    <el-empty
      v-else-if="filteredAgents.length === 0"
      description="暂无匹配的智能体"
      :image-size="100"
    />

    <!-- Agent 卡片列表 -->
    <div v-else class="agent-grid">
      <el-card
        v-for="agent in filteredAgents"
        :key="agent.agent_id"
        class="agent-card"
        shadow="hover"
        @click="selectAgent(agent.agent_id)"
      >
        <!-- 卡片头部：头像 + 名称 + 状态 -->
        <div class="agent-card-header">
          <div class="agent-avatar" :style="{ background: avatarColor(agent.agent_id) }">
            <span>{{ agentEmoji(agent.agent_id) }}</span>
          </div>
          <div class="agent-info">
            <div class="agent-name">
              {{ agent.agent_name || agent.agent_id }}
              <el-tag
                :type="statusType(agent.status)"
                size="small"
                class="status-tag"
              >
                {{ statusLabel(agent.status) }}
              </el-tag>
            </div>
            <div class="agent-id muted">{{ agent.agent_id }}</div>
          </div>
        </div>

        <!-- 当前任务 -->
        <div class="agent-task">
          <span class="task-label">📋 当前任务</span>
          <span class="task-value">{{ agent.current_task || '待分配' }}</span>
        </div>

        <!-- 资源指标 -->
        <div class="agent-metrics">
          <div class="metric-item">
            <span class="metric-label">CPU</span>
            <el-progress
              :percentage="agent.cpu_usage ?? 0"
              :stroke-width="4"
              :show-text="false"
              :status="metricStatus(agent.cpu_usage, 80)"
            />
            <span class="metric-value">{{ agent.cpu_usage != null ? `${agent.cpu_usage}%` : '—' }}</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">内存</span>
            <el-progress
              :percentage="agent.memory_usage ?? 0"
              :stroke-width="4"
              :show-text="false"
              :status="metricStatus(agent.memory_usage, 80)"
            />
            <span class="metric-value">{{ agent.memory_usage != null ? `${agent.memory_usage}%` : '—' }}</span>
          </div>
        </div>

        <!-- 心跳 + 健康度 -->
        <div class="agent-footer">
          <span class="heartbeat" :class="heartbeatClass(agent)">
            <span class="heartbeat-dot"></span>
            {{ heartbeatText(agent) }}
          </span>
          <span v-if="agent.health_score != null" class="health-score">
            健康度 {{ agent.health_score }}
          </span>
        </div>
      </el-card>
    </div>
      </el-tab-pane>
    </el-tabs>

    <!-- Agent 详情 Drawer -->
    <el-drawer
      v-model="drawerVisible"
      :title="drawerTitle"
      size="min(680px, 100vw)"
      direction="rtl"
    >
      <template v-if="selectedAgent">
        <div class="drawer-agent-header">
          <div class="drawer-avatar" :style="{ background: avatarColor(selectedAgent.agent_id) }">
            <span>{{ agentEmoji(selectedAgent.agent_id) }}</span>
          </div>
          <div>
            <div class="drawer-agent-name">{{ selectedAgent.agent_name || selectedAgent.agent_id }}</div>
            <el-tag :type="statusType(selectedAgent.status)" size="small">
              {{ statusLabel(selectedAgent.status) }}
            </el-tag>
          </div>
        </div>

        <el-divider />

        <div class="drawer-section">
          <h3>📋 当前项目工作</h3>
          <el-descriptions :column="1" size="small">
            <el-descriptions-item label="项目">
              {{ selectedAgent.current_project_name || selectedAgent.current_project_id || '未绑定项目' }}
            </el-descriptions-item>
            <el-descriptions-item label="任务">
              {{ selectedAgent.current_task_title || selectedAgent.current_task || '暂无任务' }}
            </el-descriptions-item>
            <el-descriptions-item label="开发要点">
              {{ selectedAgent.current_development_point_title || '暂无开发要点' }}
            </el-descriptions-item>
            <el-descriptions-item label="工作状态">
              <el-tag
                v-if="selectedAgent.current_work_status"
                :type="workStatusType(selectedAgent.current_work_status)"
                size="small"
              >
                {{ workStatusLabel(selectedAgent.current_work_status) }}
              </el-tag>
              <span v-else>待分配</span>
            </el-descriptions-item>
            <el-descriptions-item
              v-if="selectedAgent.task_progress != null"
              label="任务进度"
            >
              {{ selectedAgent.task_progress }}%
            </el-descriptions-item>
          </el-descriptions>
        </div>

        <div class="drawer-section">
          <h3>💓 心跳信息</h3>
          <el-descriptions :column="1" size="small">
            <el-descriptions-item label="最后心跳">
              {{ selectedAgent.last_heartbeat || '无' }}
            </el-descriptions-item>
            <el-descriptions-item label="心跳延迟">
              {{ heartbeatText(selectedAgent) }}
            </el-descriptions-item>
            <el-descriptions-item label="健康状态">
              {{ healthLabel(selectedAgent.health) }}
            </el-descriptions-item>
          </el-descriptions>
        </div>

        <div class="drawer-section">
          <h3>📊 资源使用</h3>
          <el-descriptions :column="1" size="small">
            <el-descriptions-item label="CPU">
              {{ selectedAgent.cpu_usage != null ? `${selectedAgent.cpu_usage}%` : '—' }}
            </el-descriptions-item>
            <el-descriptions-item label="内存">
              {{ selectedAgent.memory_usage != null ? `${selectedAgent.memory_usage}%` : '—' }}
            </el-descriptions-item>
          </el-descriptions>
        </div>

        <div v-if="selectedAgent.metadata && Object.keys(selectedAgent.metadata).length" class="drawer-section">
          <h3>📝 元数据</h3>
          <el-descriptions :column="1" size="small">
            <el-descriptions-item
              v-for="(val, key) in selectedAgent.metadata"
              :key="key"
              :label="key"
            >
              {{ typeof val === 'string' ? val : JSON.stringify(val) }}
            </el-descriptions-item>
          </el-descriptions>
        </div>

        <div class="drawer-section graph-memory-section">
          <div class="memory-heading">
            <h3>🧠 Graph Memory</h3>
            <el-tag v-if="memorySummary" size="small" :type="memoryStateType(memorySummary.state)">
              {{ memoryStateLabel(memorySummary.state) }}
            </el-tag>
          </div>
          <el-alert
            title="私有记忆仅对授权管理员可见；其他智能体只能召回明确批准共享给自己的快照。"
            type="info"
            :closable="false"
            show-icon
            class="memory-boundary"
          />
          <div v-if="memoryLoading" class="memory-loading">
            <el-icon class="loading-spinner"><Loading /></el-icon>
            <span>正在读取记忆结构...</span>
          </div>
          <el-alert v-else-if="memoryError" :title="memoryError" type="error" :closable="false" show-icon />
          <template v-else-if="memorySummary">
            <div class="memory-summary-grid">
              <div><strong>{{ memorySummary.totalNodes }}</strong><span>记忆节点</span></div>
              <div><strong>{{ memorySummary.totalEdges }}</strong><span>关系</span></div>
              <div><strong>{{ memorySummary.communities }}</strong><span>社区</span></div>
              <div><strong>{{ memorySummary.vectorCount ?? 0 }}</strong><span>向量</span></div>
              <div><strong>{{ memorySummary.pendingMessages }}</strong><span>待提取消息</span></div>
            </div>

            <el-alert
              v-if="memorySummary.state === 'backlog'"
              :title="memoryBacklogLabel(memorySummary)"
              type="warning"
              :closable="false"
              show-icon
              class="memory-state-alert"
            />
            <el-alert
              v-else-if="memorySummary.state === 'attention'"
              :title="memoryAttentionLabel(memorySummary)"
              type="error"
              :closable="false"
              show-icon
              class="memory-state-alert"
            />

            <div class="memory-meta-row">
              <span>类型结构</span>
              <el-tag v-for="(count, type) in memorySummary.byType" :key="type" size="small" effect="plain">
                {{ memoryTypeLabel(type) }} {{ count }}
              </el-tag>
              <span v-if="Object.keys(memorySummary.byType).length === 0" class="muted">暂无节点</span>
            </div>

            <div class="memory-meta-row">
              <span>关系结构</span>
              <el-tag v-for="(count, type) in memorySummary.byEdgeType" :key="type" size="small" type="warning" effect="plain">
                {{ memoryEdgeLabel(type) }} {{ count }}
              </el-tag>
              <span v-if="Object.keys(memorySummary.byEdgeType).length === 0" class="muted">暂无关系</span>
            </div>

            <el-descriptions :column="1" size="small" border class="memory-health">
              <el-descriptions-item label="最后更新">
                {{ formatMemoryTime(memorySummary.lastUpdatedAt) }}
              </el-descriptions-item>
              <el-descriptions-item label="最后提取">
                {{ extractionLabel(memorySummary.lastExtraction) }}
              </el-descriptions-item>
              <el-descriptions-item label="最后成功提取">
                {{ successfulExtractionLabel(memorySummary.lastSuccessfulExtraction) }}
              </el-descriptions-item>
              <el-descriptions-item label="提取队列">
                {{ queueStateLabel(memorySummary.queueState) }}
                <span v-if="memorySummary.pendingSessions"> · {{ memorySummary.pendingSessions }} 个会话</span>
                <span v-if="memorySummary.oldestPendingAt"> · 最老 {{ formatMemoryAge(memorySummary.oldestPendingAt) }}</span>
              </el-descriptions-item>
              <el-descriptions-item label="下次重试">
                {{ formatMemoryTime(memorySummary.nextRetryAt) }}
              </el-descriptions-item>
              <el-descriptions-item label="检索模式">
                {{ retrievalModeLabel(memorySummary.retrievalMode) }}
              </el-descriptions-item>
            </el-descriptions>

            <div class="memory-toolbar">
              <el-select v-model="memoryType" clearable placeholder="全部类型" size="small" @change="loadMemoryNodes(0)">
                <el-option label="任务" value="TASK" />
                <el-option label="技能" value="SKILL" />
                <el-option label="事件" value="EVENT" />
              </el-select>
              <el-input
                v-model="memoryQuery"
                clearable
                size="small"
                placeholder="仅搜索当前智能体"
                @keyup.enter="loadMemoryNodes(0)"
                @clear="loadMemoryNodes(0)"
              />
              <el-button size="small" type="primary" @click="loadMemoryNodes(0)">搜索</el-button>
            </div>

            <el-empty v-if="memoryNodes.length === 0" :description="memoryEmptyLabel" :image-size="72" />
            <div v-else class="memory-node-list">
              <button v-for="node in memoryNodes" :key="node.id" class="memory-node" @click="showMemoryNode(node)">
                <span class="memory-node-main">
                  <span class="memory-node-title">
                    <el-tag size="small" :type="memoryNodeType(node.type)">{{ memoryTypeLabel(node.type) }}</el-tag>
                    <strong>{{ node.name }}</strong>
                  </span>
                  <small>{{ node.description || '暂无摘要' }}</small>
                </span>
                <span class="memory-node-meta">验证 {{ node.validatedCount }} 次<br>{{ formatMemoryTime(node.updatedAt) }}</span>
              </button>
            </div>
            <el-pagination
              v-if="memoryTotal > memoryPageSize"
              small
              background
              layout="prev, pager, next"
              :page-size="memoryPageSize"
              :current-page="memoryPage"
              :total="memoryTotal"
              @current-change="changeMemoryPage"
            />

            <div class="memory-subsection">
              <h4>图谱连接</h4>
              <div v-if="memoryGraph.edges.length" class="memory-edge-list">
                <div v-for="edge in memoryGraph.edges.slice(0, 20)" :key="edge.id">
                  <span>{{ graphNodeName(edge.fromId) }}</span>
                  <el-tag size="small" type="warning" effect="plain">{{ memoryEdgeLabel(edge.type) }}</el-tag>
                  <span>{{ graphNodeName(edge.toId) }}</span>
                </div>
              </div>
              <span v-else class="muted">暂无可展示的图谱连接</span>
            </div>

            <div class="memory-subsection">
              <h4>明确批准的共享记忆</h4>
              <div v-if="memoryShares.length" class="memory-share-list">
                <div v-for="share in memoryShares" :key="share.id" class="memory-share">
                  <div>
                    <strong>{{ share.nodeName }}</strong>
                    <small>{{ share.direction === 'incoming' ? `来自 ${share.sourceAgent}` : `共享给 ${share.audience.join('、')}` }}</small>
                  </div>
                  <el-tag size="small" :type="memoryShareType(share.state)">{{ memoryShareLabel(share.state) }}</el-tag>
                </div>
              </div>
              <span v-else class="muted">当前没有共享记忆记录</span>
            </div>
          </template>
        </div>

        <!-- 状态变更历史 -->
        <div v-if="agentsStore.selectedAgentHistory?.length" class="drawer-section">
          <h3>📜 状态变更历史</h3>
          <el-timeline size="small">
            <el-timeline-item
              v-for="h in (agentsStore.selectedAgentHistory || []).slice(0, 10)"
              :key="h.id"
              :type="statusType(h.to_status)"
              placement="top"
            >
              <div class="history-item">
                <span class="history-status">
                  {{ statusLabel(h.from_status ?? '') }} → {{ statusLabel(h.to_status ?? '') }}
                </span>
                <span class="history-task" v-if="h.current_task">{{ h.current_task }}</span>
                <span class="history-time">{{ formatTime(h.changed_at) }}</span>
              </div>
            </el-timeline-item>
          </el-timeline>
        </div>
      </template>
    </el-drawer>

    <el-dialog v-model="memoryDetailVisible" :title="memoryDetail?.name || '记忆内容'" width="min(720px, 96vw)">
      <div v-loading="memoryDetailLoading" class="memory-detail">
        <template v-if="memoryDetail">
          <div class="memory-detail-tags">
            <el-tag :type="memoryNodeType(memoryDetail.type)">{{ memoryTypeLabel(memoryDetail.type) }}</el-tag>
            <el-tag type="info" effect="plain">私有</el-tag>
            <span>验证 {{ memoryDetail.validatedCount }} 次</span>
          </div>
          <p class="memory-detail-description">{{ memoryDetail.description }}</p>
          <pre>{{ memoryDetail.content || '暂无正文' }}</pre>
          <el-alert
            v-if="memoryDetail.contentTruncated"
            title="内容较长，当前仅显示前 20000 字符。"
            type="warning"
            :closable="false"
          />
        </template>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { Loading, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useAgentsStore, type Agent } from '@/stores/agents'
import {
  getAgentGraphMemoryGraph,
  getAgentGraphMemoryNode,
  getAgentGraphMemoryNodes,
  getAgentGraphMemoryShares,
  getAgentGraphMemorySummary,
  type GraphMemoryExtraction,
  type GraphMemoryGraph,
  type GraphMemoryNode,
  type GraphMemoryShare,
  type GraphMemorySummary,
} from '@/api/openclaw'

const agentsStore = useAgentsStore()

// ===================== 状态 =====================
const activeTab = ref('team')
const activeFilter = ref<'all' | 'online' | 'busy' | 'offline' | 'idle'>('all')
const drawerVisible = ref(false)
const memoryLoading = ref(false)
const memoryError = ref('')
const memorySummary = ref<GraphMemorySummary | null>(null)
const memoryNodes = ref<GraphMemoryNode[]>([])
const memoryTotal = ref(0)
const memoryPage = ref(1)
const memoryPageSize = 20
const memoryType = ref('')
const memoryQuery = ref('')
const memoryShares = ref<GraphMemoryShare[]>([])
const memoryGraph = ref<GraphMemoryGraph>({ agentId: '', nodes: [], edges: [], limited: false })
const memoryDetailVisible = ref(false)
const memoryDetailLoading = ref(false)
const memoryDetail = ref<GraphMemoryNode | null>(null)

const filterOptions = [
  { label: '全部', value: 'all' as const, icon: '📊' },
  { label: '在线', value: 'online' as const, icon: '🟢' },
  { label: '忙碌', value: 'busy' as const, icon: '🟡' },
  { label: '空闲', value: 'idle' as const, icon: '🔵' },
  { label: '离线', value: 'offline' as const, icon: '⚫' }
]

// ===================== 计算属性 =====================
const total = computed(() => agentsStore.agents.length)
const onlineCount = computed(() => agentsStore.agents.filter(a => a.status === 'online').length)
const busyCount = computed(() => agentsStore.agents.filter(a => a.status === 'busy').length)
const offlineCount = computed(() => agentsStore.agents.filter(a => a.status === 'offline').length)
const agentById = computed(() => new Map(agentsStore.agents.map(agent => [agent.agent_id, agent])))
const organizationAgentCount = computed(() => organizationGroups.value.reduce((sum, group) => sum + group.members.length, 0))

const filteredAgents = computed(() => {
  const agents = agentsStore.agents
  if (activeFilter.value === 'all') return agents
  return agents.filter(a => a.status === activeFilter.value)
})

const selectedAgent = computed(() => agentsStore.selectedAgent)
const organizationGroups = computed(() => {
  const org = agentsStore.organization
  if (!org) return []
  const nodes = [org.root, ...(org.nodes || [])].filter(Boolean)
  const groups = nodes.filter(node => node.node_type === 'group')
  return groups.map(group => {
    const members = nodes
      .filter(node => node.parent_id === group.id && ['agent', 'assistant', 'person'].includes(node.node_type))
      .map(node => {
        const id = node.agent_id || node.id
        const agent = agentById.value.get(id)
        if (!agent) return null
        return {
          id,
          name: node.name || agent.agent_name || id,
          title: node.title,
          emoji: node.emoji,
          agent,
        }
      })
      .filter(Boolean) as Array<{ id: string; name: string; title?: string; emoji?: string; agent: Agent }>
    return { id: group.id, name: group.name, title: group.title, members }
  }).filter(group => group.members.length)
})

const drawerTitle = computed(() => {
  if (!selectedAgent.value) return '智能体详情'
  return `${agentEmoji(selectedAgent.value.agent_id)} ${selectedAgent.value.agent_name || selectedAgent.value.agent_id}`
})
const memoryEmptyLabel = computed(() => {
  if (memorySummary.value?.state === 'not_initialized') return '该智能体尚未初始化私有记忆库'
  if (memorySummary.value?.state === 'empty') return '私有记忆库已初始化，暂无有效节点'
  return memoryQuery.value || memoryType.value ? '没有匹配的记忆' : '暂无记忆节点'
})

function filterCount(value: string): number {
  switch (value) {
    case 'all': return agentsStore.agents.length
    case 'online': return onlineCount.value
    case 'busy': return busyCount.value
    case 'idle': return agentsStore.agents.filter(a => a.status === 'idle').length
    case 'offline': return offlineCount.value
    default: return 0
  }
}

// ===================== 工具函数 =====================
function statusType(status: string): '' | 'success' | 'warning' | 'info' | 'danger' {
  const map: Record<string, '' | 'success' | 'warning' | 'info' | 'danger'> = {
    online: 'success',
    busy: 'warning',
    idle: 'info',
    offline: 'danger'
  }
  return map[status] || 'info'
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    online: '在线',
    busy: '忙碌',
    idle: '空闲',
    pending: '待命',
    offline: '离线'
  }
  return map[status] || status || '未知'
}

function workStatusType(status: string): '' | 'success' | 'warning' | 'info' | 'danger' {
  const map: Record<string, '' | 'success' | 'warning' | 'info' | 'danger'> = {
    completed: 'success',
    review: 'warning',
    in_progress: '',
    running: '',
    ready: 'info',
    queued: 'info',
    blocked: 'danger',
    failed: 'danger'
  }
  return map[status] || 'info'
}

function workStatusLabel(status: string): string {
  const map: Record<string, string> = {
    completed: '已完成',
    review: '待评审',
    in_progress: '执行中',
    running: '执行中',
    ready: '待执行',
    queued: '排队中',
    blocked: '已阻塞',
    failed: '执行失败'
  }
  return map[status] || status
}

function healthLabel(health: string): string {
  const map: Record<string, string> = {
    healthy: '健康',
    warning: '警告',
    critical: '严重',
    offline: '离线'
  }
  return map[health] || health
}

function metricStatus(value: number | null, threshold: number): '' | 'success' | 'warning' | 'exception' {
  if (value == null) return ''
  if (value >= threshold) return 'exception'
  if (value >= threshold * 0.7) return 'warning'
  return 'success'
}

function heartbeatText(agent: Agent): string {
  if (agent.status === 'offline') return '离线'
  if (agent.heartbeat_age_seconds == null) return '未知'
  const s = agent.heartbeat_age_seconds
  if (s < 10) return '刚刚'
  if (s < 60) return `${Math.round(s)}秒前`
  if (s < 3600) return `${Math.round(s / 60)}分钟前`
  return `${Math.round(s / 3600)}小时前`
}

function heartbeatClass(agent: Agent): string {
  if (agent.status === 'offline') return 'heartbeat-offline'
  const s = agent.heartbeat_age_seconds ?? Infinity
  if (s <= 60) return 'heartbeat-ok'
  if (s <= 300) return 'heartbeat-warn'
  return 'heartbeat-critical'
}

function formatTime(iso: string): string {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    return d.toLocaleString('zh-CN', { hour12: false })
  } catch {
    return iso
  }
}

function formatMemoryTime(value?: number | null): string {
  if (!value) return '暂无'
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

function memoryStateLabel(state: GraphMemorySummary['state']): string {
  return ({ not_initialized: '尚未初始化', empty: '已初始化·暂无记忆', ready: '正常', backlog: '待处理', attention: '需检查' })[state]
}

function memoryStateType(state: GraphMemorySummary['state']): '' | 'success' | 'warning' | 'info' | 'danger' {
  return ({ not_initialized: 'info', empty: 'info', ready: 'success', backlog: 'warning', attention: 'danger' } as const)[state]
}

function formatMemoryAge(value?: number | null): string {
  if (!value) return '无积压'
  const seconds = Math.max(0, Math.floor((Date.now() - value) / 1000))
  if (seconds < 60) return `${seconds}秒`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}分钟`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}小时`
  return `${Math.floor(seconds / 86400)}天`
}

function queueStateLabel(state?: string): string {
  return ({
    idle: '空闲', processing: '提取中', pending: '待处理', retrying: '等待重试', backlog: '已积压', stalled: '已停滞',
    blocked: '已阻塞', dead_letter: '有死信', failed: '失败', error: '异常', unknown: '未知',
  } as Record<string, string>)[state || 'unknown'] || state || '未知'
}

function retrievalModeLabel(mode?: string): string {
  return ({ fts5: '关键词 FTS5', vector: '向量', hybrid: '关键词 + 向量', unavailable: '不可用' } as Record<string, string>)[mode || ''] || mode || '未报告'
}

function memoryBacklogLabel(summary: GraphMemorySummary): string {
  const age = summary.oldestPendingAt ? `，最老已等待 ${formatMemoryAge(summary.oldestPendingAt)}` : ''
  return `记忆提取待处理：${summary.pendingMessages} 条消息 / ${summary.pendingSessions ?? 0} 个会话${age}`
}

function memoryAttentionLabel(summary: GraphMemorySummary): string {
  const failures = summary.extractionFailureCount ?? 0
  const deadLetters = summary.deadLetterCount ?? 0
  return `记忆提取需检查：失败 ${failures} 次，死信 ${deadLetters} 条`
}

function memoryTypeLabel(type: string): string {
  return ({ TASK: '任务', SKILL: '技能', EVENT: '事件' } as Record<string, string>)[type] || type
}

function memoryNodeType(type: string): '' | 'success' | 'warning' | 'info' | 'danger' {
  return ({ TASK: 'success', SKILL: 'warning', EVENT: 'info' } as Record<string, '' | 'success' | 'warning' | 'info' | 'danger'>)[type] || 'info'
}

function memoryEdgeLabel(type: string): string {
  return ({ USED_SKILL: '使用技能', SOLVED_BY: '由其解决', REQUIRES: '依赖', PATCHES: '修复', CONFLICTS_WITH: '冲突' } as Record<string, string>)[type] || type
}

function memoryShareLabel(state: GraphMemoryShare['state']): string {
  return ({ active: '有效', expired: '已过期', revoked: '已撤销', invalid: '已失效' })[state]
}

function memoryShareType(state: GraphMemoryShare['state']): '' | 'success' | 'warning' | 'info' | 'danger' {
  return ({ active: 'success', expired: 'warning', revoked: 'info', invalid: 'danger' } as const)[state]
}

function extractionLabel(extraction?: GraphMemoryExtraction | null): string {
  if (!extraction) return '暂无提取记录'
  const outcome = ({ started: '进行中', succeeded: '成功', failed: '失败' })[extraction.outcome]
  return `${outcome} · ${formatMemoryTime(extraction.createdAt)} · ${extraction.nodeCount} 节点 / ${extraction.edgeCount} 关系`
}

function successfulExtractionLabel(extraction?: number | null): string {
  return formatMemoryTime(extraction)
}

function graphNodeName(nodeId: string): string {
  return memoryGraph.value.nodes.find(node => node.id === nodeId)?.name || nodeId
}

function agentEmoji(id: string): string {
  const map: Record<string, string> = {
    optimus: '🤖',
    leonardo: '🟦',
    raphael: '🟥',
    donatello: '🟪',
    michelangelo: '🟧',
    ironhide: '🛡️',
    perceptor: '🚗',
    ratchet: '🚑',
    wheeljack: '🔧',
    soundwave: '🔷',
    jazz: '🎷',
    bumblebee: '🐝',
    shockwave: '🟣',
    'ultra-magnus': '🔵',
    'wheeljack-leonardo': '🟦',
    'wheeljack-raphael': '🟥',
    'wheeljack-donatello': '🟪',
    'wheeljack-michelangelo': '🟧'
  }
  return map[id] || '🤖'
}

function avatarColor(id: string): string {
  let hash = 0
  for (let i = 0; i < id.length; i++) {
    hash = id.charCodeAt(i) + ((hash << 5) - hash)
  }
  const h = Math.abs(hash) % 360
  return `hsl(${h}, 45%, 35%)`
}

// ===================== 操作 =====================
function selectAgent(agentId: string) {
  agentsStore.selectAgent(agentId)
  drawerVisible.value = true
  void loadGraphMemory(agentId)
}

async function loadGraphMemory(agentId: string) {
  memoryLoading.value = true
  memoryError.value = ''
  memorySummary.value = null
  memoryNodes.value = []
  memoryShares.value = []
  memoryGraph.value = { agentId, nodes: [], edges: [], limited: false }
  memoryTotal.value = 0
  memoryPage.value = 1
  memoryType.value = ''
  memoryQuery.value = ''
  try {
    const [summary, nodes, graph, shares] = await Promise.all([
      getAgentGraphMemorySummary(agentId),
      getAgentGraphMemoryNodes(agentId, { limit: memoryPageSize, offset: 0 }),
      getAgentGraphMemoryGraph(agentId),
      getAgentGraphMemoryShares(agentId),
    ])
    if (selectedAgent.value?.agent_id !== agentId) return
    memorySummary.value = summary
    memoryNodes.value = nodes.nodes
    memoryTotal.value = nodes.total
    memoryGraph.value = graph
    memoryShares.value = shares.shares
  } catch (error: any) {
    memoryError.value = error?.response?.data?.detail || '记忆服务暂时不可用'
  } finally {
    if (selectedAgent.value?.agent_id === agentId) memoryLoading.value = false
  }
}

async function loadMemoryNodes(offset: number) {
  const agentId = selectedAgent.value?.agent_id
  if (!agentId) return
  try {
    const result = await getAgentGraphMemoryNodes(agentId, {
      limit: memoryPageSize,
      offset,
      type: memoryType.value || undefined,
      q: memoryQuery.value.trim() || undefined,
    })
    if (selectedAgent.value?.agent_id !== agentId) return
    memoryNodes.value = result.nodes
    memoryTotal.value = result.total
    memoryPage.value = Math.floor(offset / memoryPageSize) + 1
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '记忆列表读取失败')
  }
}

function changeMemoryPage(page: number) {
  void loadMemoryNodes((page - 1) * memoryPageSize)
}

async function showMemoryNode(node: GraphMemoryNode) {
  const agentId = selectedAgent.value?.agent_id
  if (!agentId) return
  memoryDetail.value = null
  memoryDetailVisible.value = true
  memoryDetailLoading.value = true
  try {
    const result = await getAgentGraphMemoryNode(agentId, node.id)
    memoryDetail.value = result.node
  } catch (error: any) {
    memoryDetailVisible.value = false
    ElMessage.error(error?.response?.data?.detail || '记忆内容读取失败')
  } finally {
    memoryDetailLoading.value = false
  }
}

async function refresh() {
  await agentsStore.fetchAgents()
  ElMessage.success('刷新完成')
}

// ===================== 生命周期 =====================
onMounted(async () => {
  // 加载 Agent 数据
  await agentsStore.fetchAgents()

  // 尝试连接 WebSocket 获取实时推送
  const token = localStorage.getItem('jwt_token')
  if (token) {
    agentsStore.connectWebSocket(token)
  }
})

onUnmounted(() => {
  agentsStore.disconnectWebSocket()
})
</script>

<style scoped>
.agents-page {
  padding: 16px;
  min-height: 100%;
}

.agents-tabs {
  margin-top: 4px;
}

:deep(.agents-tabs > .el-tabs__header) {
  margin-bottom: 16px;
}

/* ===================== 页面头部 ===================== */
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 12px;
}

.page-title h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 800;
  color: #e0e0e0;
}

.page-desc {
  margin: 4px 0 0;
  color: #888;
  font-size: 13px;
}

.page-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.ws-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #888;
}

.ws-indicator.connected {
  color: #67c23a;
}

.ws-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #888;
}

.ws-indicator.connected .ws-dot {
  background: #67c23a;
  box-shadow: 0 0 6px #67c23a;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* ===================== 统计卡片 ===================== */
.stats-row {
  margin-bottom: 16px;
}

.stat-card {
  border-radius: 8px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  border: 1px solid #333;
  background: #1a1a1a;
  transition: transform 0.15s, box-shadow 0.15s;
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

.stat-label {
  color: #888;
  font-size: 13px;
}

.stat-value {
  color: #e0e0e0;
  font-size: 28px;
  font-weight: 800;
}

.stat-total .stat-value { color: #409eff; }
.stat-online .stat-value { color: #67c23a; }
.stat-busy .stat-value { color: #e6a23c; }
.stat-offline .stat-value { color: #909399; }

/* ===================== 筛选栏 ===================== */
.filter-bar {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}

.filter-badge {
  margin-left: 4px;
  font-size: 11px;
  opacity: 0.8;
}

/* ===================== 组织架构 ===================== */
.organization-board {
  margin-bottom: 18px;
  padding: 16px;
  border: 1px solid #30363d;
  border-radius: 8px;
  background: #161b22;
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.section-head h2 {
  margin: 0 0 4px;
  color: #e0e0e0;
  font-size: 16px;
}

.section-head p {
  margin: 0;
  color: #888;
  font-size: 12px;
}

.organization-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 12px;
}

.organization-group {
  display: grid;
  gap: 10px;
  padding: 12px;
  border: 1px solid #30363d;
  border-radius: 8px;
  background: #0d1117;
}

.organization-group header {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}

.organization-group header strong {
  color: #e0e0e0;
  font-size: 14px;
}

.organization-group header span {
  color: #888;
  font-size: 12px;
}

.organization-members {
  display: grid;
  gap: 8px;
}

.org-member {
  min-height: 54px;
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  padding: 8px;
  border: 1px solid #30363d;
  border-radius: 6px;
  color: inherit;
  background: #1a1f27;
  cursor: pointer;
  text-align: left;
}

.org-member:hover {
  border-color: #409eff;
  background: rgba(64, 158, 255, 0.08);
}

.org-avatar {
  width: 34px;
  height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  color: #fff;
  font-size: 17px;
}

.org-member-main {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.org-member-main strong {
  color: #e0e0e0;
  font-size: 13px;
}

.org-member-main small {
  color: #888;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ===================== Loading ===================== */
.loading-wrapper {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 0;
  color: #888;
}

.loading-spinner {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.loading-text {
  margin-top: 12px;
  font-size: 14px;
}

/* ===================== Agent 卡片网格 ===================== */
.agent-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}

.agent-card {
  cursor: pointer;
  transition: transform 0.15s, box-shadow 0.15s;
  border-radius: 10px;
  border: 1px solid #333;
  background: #1a1a1a;
}

.agent-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 8px 24px rgba(64, 158, 255, 0.15);
  border-color: #409eff;
}

:deep(.el-card__body) {
  padding: 16px;
}

/* 卡片头部 */
.agent-card-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.agent-avatar {
  width: 42px;
  height: 42px;
  border-radius: 10px;
  display: grid;
  place-items: center;
  font-size: 20px;
  flex-shrink: 0;
  color: #fff;
}

.agent-info {
  flex: 1;
  min-width: 0;
}

.agent-name {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 700;
  color: #e0e0e0;
}

.agent-id {
  font-size: 12px;
  color: #666;
  margin-top: 2px;
}

.muted { color: #888; }

/* 当前任务 */
.agent-task {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
  border-top: 1px solid #2a2a2a;
  border-bottom: 1px solid #2a2a2a;
  margin-bottom: 10px;
}

.task-label {
  font-size: 12px;
  color: #888;
  flex-shrink: 0;
}

.task-value {
  font-size: 13px;
  color: #b0b0b0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

/* 资源指标 */
.agent-metrics {
  display: grid;
  gap: 8px;
  margin-bottom: 10px;
}

.metric-item {
  display: grid;
  grid-template-columns: 36px 1fr 40px;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.metric-label {
  color: #888;
}

.metric-value {
  color: #b0b0b0;
  text-align: right;
  font-size: 11px;
}

:deep(.el-progress-bar__outer) {
  border-radius: 2px;
}

/* 卡片底部 */
.agent-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 8px;
  border-top: 1px solid #2a2a2a;
  font-size: 12px;
}

.heartbeat {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #888;
}

.heartbeat-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #888;
}

.heartbeat-ok .heartbeat-dot {
  background: #67c23a;
  box-shadow: 0 0 4px #67c23a;
}

.heartbeat-warn .heartbeat-dot {
  background: #e6a23c;
  box-shadow: 0 0 4px #e6a23c;
}

.heartbeat-critical .heartbeat-dot {
  background: #f56c6c;
  box-shadow: 0 0 4px #f56c6c;
}

.heartbeat-offline .heartbeat-dot {
  background: #909399;
}

.health-score {
  color: #67c23a;
  font-weight: 600;
}

/* ===================== Drawer ===================== */
.drawer-agent-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.drawer-avatar {
  width: 52px;
  height: 52px;
  border-radius: 12px;
  display: grid;
  place-items: center;
  font-size: 26px;
  color: #fff;
}

.drawer-agent-name {
  font-size: 18px;
  font-weight: 700;
  color: #e0e0e0;
  margin-bottom: 6px;
}

.drawer-section {
  margin-bottom: 20px;
}

.drawer-section h3 {
  margin: 0 0 10px;
  font-size: 14px;
  font-weight: 700;
  color: #e0e0e0;
}

.drawer-section p {
  margin: 0;
  color: #b0b0b0;
  font-size: 13px;
}

.graph-memory-section {
  padding-top: 4px;
}

.memory-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.memory-boundary {
  margin-bottom: 12px;
}

.memory-state-alert {
  margin-bottom: 12px;
}

.memory-loading {
  min-height: 96px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #888;
}

.memory-summary-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 12px;
}

.memory-summary-grid > div {
  display: grid;
  gap: 2px;
  padding: 10px;
  border: 1px solid #30363d;
  border-radius: 7px;
  background: #161b22;
}

.memory-summary-grid strong {
  color: #409eff;
  font-size: 20px;
}

.memory-summary-grid span {
  color: #888;
  font-size: 11px;
}

.memory-meta-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin: 8px 0;
  color: #aaa;
  font-size: 12px;
}

.memory-meta-row > span:first-child {
  min-width: 64px;
  color: #888;
}

.memory-health {
  margin: 12px 0;
}

.memory-toolbar {
  display: grid;
  grid-template-columns: 118px minmax(0, 1fr) auto;
  gap: 8px;
  margin: 12px 0;
}

.memory-node-list {
  display: grid;
  gap: 8px;
  margin-bottom: 12px;
}

.memory-node {
  width: 100%;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  padding: 10px;
  border: 1px solid #30363d;
  border-radius: 7px;
  color: inherit;
  background: #161b22;
  cursor: pointer;
  text-align: left;
}

.memory-node:hover {
  border-color: #409eff;
  background: rgba(64, 158, 255, 0.08);
}

.memory-node-main {
  display: grid;
  gap: 5px;
  min-width: 0;
}

.memory-node-title {
  display: flex;
  align-items: center;
  gap: 7px;
}

.memory-node-main strong {
  color: #e0e0e0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.memory-node-main small,
.memory-share small {
  color: #888;
}

.memory-node-meta {
  color: #777;
  font-size: 11px;
  line-height: 1.55;
  text-align: right;
  white-space: nowrap;
}

.memory-subsection {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid #30363d;
}

.memory-subsection h4 {
  margin: 0 0 9px;
  color: #d8d8d8;
  font-size: 13px;
}

.memory-edge-list,
.memory-share-list {
  display: grid;
  gap: 7px;
}

.memory-edge-list > div {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: center;
  gap: 7px;
  color: #b0b0b0;
  font-size: 12px;
}

.memory-share {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid #30363d;
  border-radius: 7px;
  background: #161b22;
}

.memory-share > div {
  display: grid;
  gap: 3px;
}

.memory-detail-tags {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  color: #888;
  font-size: 12px;
}

.memory-detail-description {
  margin: 14px 0;
  color: #b0b0b0;
  line-height: 1.6;
}

.memory-detail pre {
  max-height: 55vh;
  overflow: auto;
  margin: 0 0 12px;
  padding: 14px;
  border: 1px solid #30363d;
  border-radius: 7px;
  color: #d8dee9;
  background: #0d1117;
  font: inherit;
  line-height: 1.65;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.history-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.history-status {
  font-size: 13px;
  color: #b0b0b0;
}

.history-task {
  font-size: 12px;
  color: #888;
}

.history-time {
  font-size: 11px;
  color: #666;
}

/* ===================== 响应式 ===================== */
@media (max-width: 768px) {
  .agents-page {
    padding: 12px;
  }

  .agent-grid {
    grid-template-columns: 1fr;
  }

  .organization-grid {
    grid-template-columns: 1fr;
  }

  .memory-summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .memory-toolbar {
    grid-template-columns: 1fr;
  }

  .page-title h1 {
    font-size: 18px;
  }

  .stat-value {
    font-size: 22px;
  }
}

@media (max-width: 480px) {
  .stats-row .el-col {
    margin-bottom: 8px;
  }
}
</style>
