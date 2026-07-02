<template>
  <div class="data-admin-page">
    <el-row :gutter="16" class="stats-row">
      <el-col v-for="item in statItems" :key="item.label" :xs="12" :md="4">
        <el-card shadow="hover" class="stat-card">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </el-card>
      </el-col>
    </el-row>

    <el-tabs v-model="activeTab" class="admin-tabs">
      <el-tab-pane label="统一数据库" name="database">
        <el-row :gutter="18">
          <el-col :xs="24" :lg="10">
            <el-card shadow="hover" class="panel">
              <template #header>
                <div class="panel-header">
                  <span>统一数据库</span>
                  <el-button size="small" type="primary" @click="loadAll">刷新</el-button>
                </div>
              </template>
              <el-skeleton v-if="loading" :rows="6" animated />
              <template v-else>
                <el-alert
                  :title="overview?.database.status === 'ready' ? '数据库连接正常' : '数据库状态异常'"
                  :type="overview?.database.status === 'ready' ? 'success' : 'warning'"
                  :closable="false"
                  show-icon
                />
                <div class="db-path">{{ overview?.database.path }}</div>
                <el-table :data="overview?.database.schema || []" size="small" height="420">
                  <el-table-column prop="name" label="数据表" />
                  <el-table-column prop="rows" label="记录数" width="100" align="right" />
                </el-table>
              </template>
            </el-card>
          </el-col>

          <el-col :xs="24" :lg="14">
            <el-card shadow="hover" class="panel">
              <template #header>
                <div class="panel-header">
                  <span>数据源</span>
                  <el-tag>{{ overview?.data_sources.length || 0 }} 个</el-tag>
                </div>
              </template>
              <el-table :data="overview?.data_sources || []" size="small" height="520">
                <el-table-column prop="name" label="名称" min-width="220" show-overflow-tooltip />
                <el-table-column label="类型" width="90">
                  <template #default="{ row }">{{ sourceTypeLabel(row.source_type) }}</template>
                </el-table-column>
                <el-table-column prop="record_count" label="记录" width="90" align="right" />
                <el-table-column prop="status" label="状态" width="100">
                  <template #default="{ row }">
                    <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">{{ statusLabel(row.status) }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="path" label="路径" min-width="260" show-overflow-tooltip />
              </el-table>
            </el-card>
          </el-col>
        </el-row>
      </el-tab-pane>

      <el-tab-pane label="智能体档案" name="agents">
        <el-card shadow="hover" class="panel">
          <template #header>
            <div class="panel-header">
              <div>
                <span>智能体主数据</span>
                <small>统一库 agents 表</small>
              </div>
              <div class="header-actions">
                <el-input v-model="agentQuery" size="small" clearable placeholder="搜索智能体" />
                <el-button size="small" @click="syncAgents">同步 JSON</el-button>
                <el-button size="small" type="primary" :loading="agentsLoading" @click="loadAgents">刷新</el-button>
              </div>
            </div>
          </template>

          <el-table :data="filteredAgents" size="small" height="560" row-key="id">
            <el-table-column label="智能体" min-width="180" fixed>
              <template #default="{ row }">
                <div class="agent-cell">
                  <span class="avatar">{{ row.emoji || '👤' }}</span>
                  <span>
                    <strong>{{ row.name }}</strong>
                    <small>{{ row.id }}</small>
                  </span>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="role" label="角色" min-width="150" show-overflow-tooltip />
            <el-table-column prop="category" label="类别" width="110">
              <template #default="{ row }">{{ categoryLabel(row.category) }}</template>
            </el-table-column>
            <el-table-column prop="team" label="团队" width="120" show-overflow-tooltip />
            <el-table-column prop="status" label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="agentStatusType(row.status)" size="small">{{ agentStatusLabel(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="启用" width="80" align="center">
              <template #default="{ row }">
                <el-switch :model-value="row.enabled" size="small" @change="toggleAgent(row, 'enabled', $event)" />
              </template>
            </el-table-column>
            <el-table-column label="组织显示" width="100" align="center">
              <template #default="{ row }">
                <el-switch :model-value="row.visible_in_org" size="small" @change="toggleAgent(row, 'visible_in_org', $event)" />
              </template>
            </el-table-column>
            <el-table-column label="分身" width="80" align="center">
              <template #default="{ row }">
                <el-tag v-if="row.is_clone" type="info" size="small">分身</el-tag>
                <span v-else class="muted">-</span>
              </template>
            </el-table-column>
            <el-table-column prop="source" label="来源" width="150" show-overflow-tooltip />
            <el-table-column label="操作" width="110" fixed="right">
              <template #default="{ row }">
                <el-button size="small" type="primary" text @click="editAgent(row)">编辑</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="组织节点" name="org">
        <el-card shadow="hover" class="panel">
          <template #header>
            <div class="panel-header">
              <div>
                <span>智能体组织结构</span>
                <small>统一库 agent_org_nodes 表；分组用于归类，不在组织看板显示为卡片</small>
              </div>
              <div class="header-actions">
                <el-button size="small" @click="syncOrg">同步 JSON</el-button>
                <el-button size="small" type="primary" :loading="orgLoading" @click="loadOrg">刷新</el-button>
              </div>
            </div>
          </template>

          <el-table :data="orgRows" size="small" height="560" row-key="id">
            <el-table-column prop="level" label="层级" width="80" />
            <el-table-column label="节点" min-width="190">
              <template #default="{ row }">
                <div class="agent-cell">
                  <span class="avatar">{{ row.emoji || (row.node_type === 'group' ? '📁' : '👤') }}</span>
                  <span>
                    <strong>{{ row.name }}</strong>
                    <small>{{ row.id }}</small>
                  </span>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="parent_id" label="上级" width="150" show-overflow-tooltip />
            <el-table-column prop="agent_id" label="Agent ID" width="160" show-overflow-tooltip />
            <el-table-column prop="node_type" label="类型" width="100">
              <template #default="{ row }">{{ nodeTypeLabel(row.node_type) }}</template>
            </el-table-column>
            <el-table-column prop="title" label="说明" min-width="220" show-overflow-tooltip />
            <el-table-column prop="order" label="排序" width="80" align="right" />
            <el-table-column label="显示" width="80" align="center">
              <template #default="{ row }">
                <el-tag :type="row.visible === false ? 'info' : 'success'" size="small">{{ row.visible === false ? '隐藏' : '显示' }}</el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <el-drawer v-model="agentDrawer" title="编辑智能体" size="420px">
      <el-form v-if="agentForm" label-position="top">
        <el-form-item label="名称">
          <el-input v-model="agentForm.name" />
        </el-form-item>
        <el-form-item label="显示名">
          <el-input v-model="agentForm.display_name" />
        </el-form-item>
        <el-form-item label="Emoji">
          <el-input v-model="agentForm.emoji" maxlength="4" />
        </el-form-item>
        <el-form-item label="角色">
          <el-input v-model="agentForm.role" />
        </el-form-item>
        <el-form-item label="团队">
          <el-input v-model="agentForm.team" />
        </el-form-item>
        <el-form-item label="类别">
          <el-select v-model="agentForm.category" clearable>
            <el-option label="总协调" value="coordinator" />
            <el-option label="项目经理" value="pm" />
            <el-option label="开发执行" value="developer" />
            <el-option label="保障" value="support" />
            <el-option label="助理" value="assistant" />
            <el-option label="智能体" value="agent" />
          </el-select>
        </el-form-item>
        <el-form-item label="开关">
          <div class="switch-grid">
            <el-checkbox v-model="agentForm.enabled">启用</el-checkbox>
            <el-checkbox v-model="agentForm.visible">列表可见</el-checkbox>
            <el-checkbox v-model="agentForm.visible_in_org">组织显示</el-checkbox>
            <el-checkbox v-model="agentForm.is_clone">分身</el-checkbox>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="agentDrawer = false">取消</el-button>
        <el-button type="primary" :loading="savingAgent" @click="saveAgent">保存</el-button>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getAdminAgentOrg,
  getAdminAgents,
  getDataOverview,
  importAdminAgentOrg,
  importAdminAgents,
  updateAdminAgent,
  type AdminAgent,
  type AdminAgentOrg,
  type AdminAgentOrgNode,
  type DataOverview
} from '@/api/dataAdmin'

const activeTab = ref('database')
const loading = ref(false)
const agentsLoading = ref(false)
const orgLoading = ref(false)
const savingAgent = ref(false)
const overview = ref<DataOverview | null>(null)
const agents = ref<AdminAgent[]>([])
const org = ref<AdminAgentOrg | null>(null)
const agentQuery = ref('')
const agentDrawer = ref(false)
const agentForm = ref<AdminAgent | null>(null)

const statItems = computed(() => {
  const totals = overview.value?.totals || {}
  return [
    { label: '项目', value: totals.projects || 0 },
    { label: '任务', value: totals.tasks || 0 },
    { label: '开发要点', value: totals.development_points || 0 },
    { label: '智能体', value: totals.agents || 0 },
    { label: '组织节点', value: totals.agent_org_nodes || 0 },
    { label: '设备', value: totals.devices || 0 },
  ]
})

const filteredAgents = computed(() => {
  const keyword = agentQuery.value.trim().toLowerCase()
  if (!keyword) return agents.value
  return agents.value.filter(agent => [agent.id, agent.name, agent.role, agent.team, agent.category].some(value => String(value || '').toLowerCase().includes(keyword)))
})

const orgRows = computed(() => {
  if (!org.value?.root) return []
  const nodes = [org.value.root, ...(org.value.nodes || [])]
  const byParent = new Map<string, AdminAgentOrgNode[]>()
  for (const node of nodes) {
    const key = node.parent_id || ''
    if (!byParent.has(key)) byParent.set(key, [])
    byParent.get(key)!.push(node)
  }
  for (const list of byParent.values()) list.sort((a, b) => (a.order || 999) - (b.order || 999) || a.name.localeCompare(b.name, 'zh-CN'))
  const rows: Array<AdminAgentOrgNode & { level: number }> = []
  const walk = (parentId: string, level: number) => {
    for (const node of byParent.get(parentId) || []) {
      rows.push({ ...node, level })
      walk(node.id, level + 1)
    }
  }
  walk('', 0)
  return rows
})

async function loadAll() {
  loading.value = true
  try {
    await Promise.all([loadOverview(), loadAgents(), loadOrg()])
  } finally {
    loading.value = false
  }
}

async function loadOverview() {
  overview.value = await getDataOverview()
}

async function loadAgents() {
  agentsLoading.value = true
  try {
    const data = await getAdminAgents()
    agents.value = data.agents || []
  } catch {
    ElMessage.error('智能体主数据加载失败')
  } finally {
    agentsLoading.value = false
  }
}

async function loadOrg() {
  orgLoading.value = true
  try {
    org.value = await getAdminAgentOrg(true)
  } catch {
    ElMessage.error('组织节点加载失败')
  } finally {
    orgLoading.value = false
  }
}

async function syncAgents() {
  await importAdminAgents()
  await Promise.all([loadAgents(), loadOverview()])
  ElMessage.success('智能体 JSON 已同步到统一库')
}

async function syncOrg() {
  await importAdminAgentOrg()
  await Promise.all([loadOrg(), loadOverview()])
  ElMessage.success('组织 JSON 已同步到统一库')
}

function editAgent(agent: AdminAgent) {
  agentForm.value = { ...agent }
  agentDrawer.value = true
}

async function saveAgent() {
  if (!agentForm.value) return
  savingAgent.value = true
  try {
    const updated = await updateAdminAgent(agentForm.value.id, agentForm.value)
    agents.value = agents.value.map(agent => agent.id === updated.id ? updated : agent)
    agentDrawer.value = false
    ElMessage.success('智能体档案已保存')
  } finally {
    savingAgent.value = false
  }
}

async function toggleAgent(agent: AdminAgent, key: 'enabled' | 'visible_in_org', value: string | number | boolean) {
  const updated = await updateAdminAgent(agent.id, { [key]: Boolean(value) })
  agents.value = agents.value.map(item => item.id === updated.id ? updated : item)
}

onMounted(loadAll)

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    active: '启用',
    inactive: '停用',
    ready: '就绪',
    error: '异常'
  }
  return map[status] || status
}

function sourceTypeLabel(type: string): string {
  const map: Record<string, string> = {
    json: 'JSON',
    sqlite: 'SQLite',
    api: '接口',
    file: '文件'
  }
  return map[type] || type
}

function agentStatusLabel(status = '') {
  return ({ online: '在线', busy: '忙碌', idle: '空闲', pending: '待命', offline: '离线' } as Record<string, string>)[status] || status || '未知'
}

function agentStatusType(status = ''): '' | 'success' | 'warning' | 'info' | 'danger' {
  return ({ online: 'success', busy: 'warning', idle: 'info', pending: 'warning', offline: 'danger' } as Record<string, '' | 'success' | 'warning' | 'info' | 'danger'>)[status] || 'info'
}

function categoryLabel(category = '') {
  return ({ coordinator: '总协调', pm: '项目经理', developer: '开发', support: '保障', assistant: '助理', agent: '智能体' } as Record<string, string>)[category] || category || '-'
}

function nodeTypeLabel(type = '') {
  return ({ person: '负责人', assistant: '助理', agent: '智能体', group: '分组', placeholder: '占位' } as Record<string, string>)[type] || type
}
</script>

<style scoped>
.data-admin-page {
  min-height: 100%;
}

.stats-row {
  margin-bottom: 16px;
}

.stat-card,
.panel {
  border-radius: 8px;
}

.stat-card :deep(.el-card__body) {
  display: grid;
  gap: 8px;
}

.stat-card span,
.muted,
.panel-header small {
  color: #909399;
  font-size: 13px;
}

.stat-card strong {
  color: #303133;
  font-size: 24px;
}

.admin-tabs {
  min-width: 0;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}

.panel-header > div:first-child {
  display: grid;
  gap: 3px;
}

.header-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

.header-actions .el-input {
  width: 180px;
}

.db-path {
  margin: 12px 0;
  color: #606266;
  font-size: 13px;
  word-break: break-all;
}

.agent-cell {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
}

.agent-cell .avatar {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  background: #f5f7fa;
  flex: 0 0 auto;
}

.agent-cell span:last-child {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.agent-cell strong,
.agent-cell small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-cell strong {
  color: #303133;
}

.agent-cell small {
  color: #909399;
  font-size: 12px;
}

.switch-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

@media (max-width: 1100px) {
  .panel-header,
  .header-actions {
    align-items: stretch;
    flex-direction: column;
  }

  .header-actions .el-input {
    width: 100%;
  }
}
</style>
