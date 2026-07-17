<template>
  <div class="agent-chat-page">
    <section class="agent-rail">
      <div class="rail-head">
        <div>
          <h2>智能体对话</h2>
          <p>选择团队成员，直接推进业务和项目事项</p>
        </div>
        <el-button :icon="Refresh" circle @click="loadAgents" />
      </div>

      <el-input
        v-model="agentQuery"
        placeholder="搜索智能体"
        :prefix-icon="Search"
        clearable
      />

      <div class="agent-tree">
        <button
          v-for="node in filteredTreeNodes"
          :key="node.id"
          class="agent-row"
          :class="{
            active: node.agent?.id === selectedAgent?.id,
            group: !node.agent,
            planned: node.planned
          }"
          :style="{ '--depth': node.depth }"
          :disabled="!node.agent && !hasTreeChildren(node)"
          :aria-expanded="hasTreeChildren(node) ? !isTreeCollapsed(node.id) : undefined"
          @click="handleTreeNodeClick(node)"
        >
          <span class="tree-line" />
          <el-icon v-if="hasTreeChildren(node)" class="tree-toggle">
            <CaretRight v-if="isTreeCollapsed(node.id)" />
            <CaretBottom v-else />
          </el-icon>
          <span v-else class="tree-toggle-spacer" />
          <span class="avatar">{{ node.emoji || agentInitial(node.agent || node) }}</span>
          <span class="agent-main">
            <span class="agent-name">{{ node.name }}</span>
            <span class="agent-meta">{{ node.agent ? agentMeta(node.agent) : node.title || '组织分组' }}</span>
          </span>
          <span v-if="node.agent" class="status-dot" :class="node.agent.status || 'idle'" />
        </button>
      </div>
    </section>

    <section class="chat-panel">
      <div class="chat-head">
        <div>
          <span class="chat-window-kicker">对话窗口</span>
          <h1>{{ selectedAgent?.name || '选择智能体' }}</h1>
          <p>{{ selectedAgent ? `${selectedAgent.role || '团队智能体'} · ${selectedAgent.id}` : '从左侧选择一个智能体开始对话' }}</p>
        </div>
        <div class="head-actions">
          <el-segmented v-model="mode" :options="modeOptions" />
          <el-button :icon="Delete" @click="confirmClear" :disabled="!selectedAgent || messages.length === 0" />
        </div>
      </div>

      <div ref="messagesEl" class="messages">
        <div v-if="!selectedAgent" class="empty-state">
          <h3>选择智能体开始协作</h3>
          <p>可以与任意智能体讨论业务管理、项目计划、任务拆解、风险处置和开发实现。</p>
        </div>

        <template v-else>
          <div v-if="messages.length === 0 && !loadingMessages" class="empty-state">
            <h3>还没有对话</h3>
            <p>使用右侧快捷语境，或者直接输入你要推进的事项。</p>
          </div>

          <div
            v-for="(message, index) in messages"
            :key="`${message.timestamp}-${index}`"
            class="message"
            :class="message.role === 'user' ? 'from-user' : 'from-agent'"
          >
            <div class="message-meta">
              <span>{{ message.role === 'user' ? '你' : selectedAgent.name }}</span>
              <time>{{ formatTime(message.timestamp) }}</time>
            </div>
            <p>{{ message.content }}</p>
            <div v-if="message.attachments?.length" class="message-attachments">
              <a
                v-for="attachment in message.attachments"
                :key="attachment.id || attachment.name"
                class="attachment-chip"
                :href="attachment.data_url"
                target="_blank"
                rel="noreferrer"
              >
                <span class="attachment-icon">{{ attachment.type.startsWith('image/') ? '图' : '文' }}</span>
                <span>
                  <strong>{{ attachment.name }}</strong>
                  <small>{{ formatFileSize(attachment.size) }} · {{ attachment.type || '文件' }}</small>
                </span>
              </a>
            </div>
          </div>

          <div v-if="sending" class="message from-agent pending">
            <div class="message-meta">
              <span>{{ selectedAgent.name }}</span>
              <time>正在回复</time>
            </div>
            <p>正在整理回复...</p>
          </div>
        </template>
      </div>

      <div class="composer">
        <div class="composer-main">
          <el-input
            v-model="draft"
            type="textarea"
            :rows="3"
            resize="none"
            :placeholder="selectedAgent ? '输入业务问题、项目需求、开发任务，也可以添加图片或文件...' : '请先选择智能体'"
            :disabled="!selectedAgent || sending"
            @keydown.meta.enter.prevent="sendMessage"
            @keydown.ctrl.enter.prevent="sendMessage"
          />
          <div v-if="selectedAttachments.length" class="selected-attachments">
            <span v-for="attachment in selectedAttachments" :key="attachment.id" class="selected-attachment">
              <span>{{ attachment.type.startsWith('image/') ? '图片' : '文件' }}</span>
              <strong>{{ attachment.name }}</strong>
              <small>{{ formatFileSize(attachment.size) }}</small>
              <button type="button" @click="removeAttachment(attachment.id)">移除</button>
            </span>
          </div>
          <input ref="fileInput" class="hidden-file-input" type="file" multiple accept="image/*,.pdf,.doc,.docx,.xls,.xlsx,.csv,.txt,.md" @change="handleFileChange" />
        </div>
        <div class="composer-actions">
          <el-button :icon="Paperclip" :disabled="!selectedAgent || sending" @click="openFilePicker" />
          <el-button type="primary" :icon="Promotion" :loading="sending" :disabled="!canSend" @click="sendMessage">
            发送
          </el-button>
        </div>
      </div>
    </section>

    <aside class="context-panel">
      <section>
        <h3>Codex 开发任务</h3>
        <div v-if="selectedAgent && isDevelopmentAgent" class="codex-panel">
          <el-input
            v-model="codexInstruction"
            type="textarea"
            :rows="3"
            resize="none"
            placeholder="描述要让该智能体执行的代码任务..."
            :disabled="creatingCodexJob"
          />
          <div class="codex-actions">
            <el-button type="primary" :loading="creatingCodexJob" :disabled="!codexInstruction.trim()" @click="startCodexJob">
              发起任务
            </el-button>
            <el-button :loading="loadingCodexJobs" @click="loadCodexJobs">刷新</el-button>
          </div>
        </div>
        <p v-else-if="selectedAgent" class="muted">当前智能体不是开发执行角色，请选择李奥纳多、多纳泰罗、拉斐尔或米开朗基罗。</p>
        <p v-else class="muted">选择开发智能体后可发起 Codex 任务。</p>

        <div v-if="codexJobs.length" class="codex-job-list">
          <button
            v-for="job in codexJobs"
            :key="job.id"
            class="codex-job"
            :class="{ active: selectedCodexJob?.id === job.id }"
            @click="selectCodexJob(job.id)"
          >
            <span>{{ job.instruction }}</span>
            <small>{{ codexStatusLabel(job.status) }} · {{ formatTime(job.created_at) }}</small>
          </button>
        </div>

        <div v-if="selectedCodexJob" class="codex-detail">
          <div class="codex-detail-head">
            <span>{{ selectedCodexJob.id }}</span>
            <el-tag size="small" :type="codexStatusType(selectedCodexJob.status)">{{ codexStatusLabel(selectedCodexJob.status) }}</el-tag>
          </div>
          <p v-if="selectedCodexJob.error" class="codex-error">{{ selectedCodexJob.error }}</p>
          <pre v-if="selectedCodexJob.summary" class="codex-summary">{{ selectedCodexJob.summary }}</pre>
          <pre v-else class="codex-log">{{ codexLogsText }}</pre>
          <div class="codex-actions">
            <el-button size="small" @click="refreshSelectedCodexJob">刷新日志</el-button>
            <el-button
              v-if="selectedCodexJob.status === 'running' || selectedCodexJob.status === 'queued'"
              size="small"
              type="warning"
              @click="cancelSelectedCodexJob"
            >
              取消
            </el-button>
          </div>
        </div>
      </section>

      <section>
        <h3>快捷语境</h3>
        <div class="prompt-list">
          <button v-for="prompt in activePrompts" :key="prompt.title" @click="usePrompt(prompt.text)">
            <span>{{ prompt.title }}</span>
            <small>{{ prompt.desc }}</small>
          </button>
        </div>
      </section>

      <section>
        <h3>最近会话</h3>
        <div class="conversation-list">
          <button
            v-for="conversation in conversations"
            :key="conversation.agent_id"
            @click="selectConversation(conversation.agent_id)"
          >
            <span>{{ agentName(conversation.agent_id) }}</span>
            <small>{{ conversation.message_count }} 条 · {{ formatTime(conversation.last_timestamp || '') }}</small>
          </button>
          <p v-if="conversations.length === 0" class="muted">暂无会话记录</p>
        </div>
      </section>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CaretBottom, CaretRight, Delete, Paperclip, Promotion, Refresh, Search } from '@element-plus/icons-vue'
import {
  clearAgentMessages,
  getAgentMessages,
  getChatAgents,
  getConversationSummaries,
  sendAgentMessage,
  type ChatAgent,
  type ChatAgentNode,
  type ChatAttachment,
  type ChatMessage,
  type ConversationSummary
} from '@/api/chat'
import {
  cancelCodexJob,
  createCodexJob,
  getCodexJobLogs,
  listCodexJobs,
  type CodexJob,
  type CodexJobStatus
} from '@/api/codex'

const agents = ref<ChatAgent[]>([])
const agentTreeNodes = ref<ChatAgentNode[]>([])
const conversations = ref<ConversationSummary[]>([])
const selectedAgent = ref<ChatAgent | null>(null)
const messages = ref<ChatMessage[]>([])
const draft = ref('')
const mode = ref('business')
const agentQuery = ref('')
const collapsedTreeNodeIds = ref(new Set<string>())
const sending = ref(false)
const loadingMessages = ref(false)
const messagesEl = ref<HTMLElement | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const selectedAttachments = ref<ChatAttachment[]>([])
const codexInstruction = ref('')
const codexJobs = ref<CodexJob[]>([])
const selectedCodexJob = ref<CodexJob | null>(null)
const codexLogs = ref<string[]>([])
const creatingCodexJob = ref(false)
const loadingCodexJobs = ref(false)
let codexPoller: number | undefined

const modeOptions = [
  { label: '业务管理', value: 'business' },
  { label: '项目开发', value: 'development' }
]

const prompts = {
  business: [
    { title: '经营复盘', desc: '指标、问题、动作', text: '请基于当前业务目标，帮我做一次经营复盘：列出关键指标、主要问题、优先动作和需要我决策的事项。' },
    { title: '风险处置', desc: '识别和缓解', text: '请从业务管理角度识别当前事项的主要风险，按影响程度排序，并给出缓解方案和负责人建议。' },
    { title: '会议准备', desc: '议程和结论', text: '请帮我准备一次管理会议：给出议程、需要确认的决策、会前资料和会后跟进清单。' }
  ],
  development: [
    { title: '需求拆解', desc: '范围和验收', text: '请把这个项目开发需求拆成可执行任务，说明范围边界、验收标准、依赖关系和建议排期。' },
    { title: '技术方案', desc: '实现和风险', text: '请给出技术实现方案：包括模块设计、接口变化、数据流、测试计划和潜在风险。' },
    { title: '开发推进', desc: '下一步动作', text: '请根据当前开发状态，给出下一步推进计划，明确今天可以完成的动作和阻塞项。' }
  ]
}

const activePrompts = computed(() => prompts[mode.value as keyof typeof prompts])
const developmentAgentIds = new Set(['leonardo', 'donatello', 'raphael', 'michelangelo'])
const isDevelopmentAgent = computed(() => Boolean(selectedAgent.value && developmentAgentIds.has(selectedAgent.value.id)))
const codexLogsText = computed(() => codexLogs.value.join('').slice(-12000) || '暂无日志')
const treeChildrenByParent = computed(() => {
  const map = new Map<string, ChatAgentNode[]>()
  for (const node of agentTreeNodes.value) {
    const key = node.parent_id || ''
    if (!map.has(key)) map.set(key, [])
    map.get(key)!.push(node)
  }
  return map
})
const treeNodeById = computed(() => {
  const map = new Map<string, ChatAgentNode>()
  for (const node of agentTreeNodes.value) map.set(node.id, node)
  return map
})
const filteredTreeNodes = computed(() => {
  const q = agentQuery.value.trim().toLowerCase()
  if (!q) return agentTreeNodes.value.filter(isTreeNodeVisible)
  const visibleNodeIds = new Set<string>()

  for (const node of agentTreeNodes.value) {
    const text = `${node.name} ${node.agent_id || ''} ${node.title || ''} ${node.agent?.role || ''} ${(node.path || []).join(' ')}`.toLowerCase()
    if (text.includes(q)) {
      addNodeWithAncestors(node, visibleNodeIds)
      if (!node.agent) addDescendants(node.id, visibleNodeIds)
    }
  }

  return agentTreeNodes.value.filter(node => visibleNodeIds.has(node.id))
})
const canSend = computed(() => Boolean(selectedAgent.value && (draft.value.trim() || selectedAttachments.value.length) && !sending.value))

onMounted(async () => {
  await Promise.all([loadAgents(), loadConversations()])
  codexPoller = window.setInterval(() => {
    if (selectedCodexJob.value?.status === 'queued' || selectedCodexJob.value?.status === 'running') {
      refreshSelectedCodexJob()
    }
  }, 5000)
})

onBeforeUnmount(() => {
  if (codexPoller) window.clearInterval(codexPoller)
})

watch(selectedAgent, async () => {
  selectedCodexJob.value = null
  codexLogs.value = []
  codexInstruction.value = ''
  await loadCodexJobs()
})

async function loadAgents() {
  try {
    const res = await getChatAgents()
    agents.value = res.agents
    agentTreeNodes.value = res.nodes
    if (!selectedAgent.value && agents.value.length > 0) {
      await selectAgent(agents.value[0])
    }
  } catch {
    ElMessage.error('智能体列表加载失败')
  }
}

async function loadConversations() {
  try {
    const res = await getConversationSummaries()
    conversations.value = res.conversations || []
  } catch {
    conversations.value = []
  }
}

async function selectAgent(agent: ChatAgent) {
  selectedAgent.value = agent
  await loadMessages(agent.id)
}

async function loadCodexJobs() {
  if (!selectedAgent.value) {
    codexJobs.value = []
    return
  }
  loadingCodexJobs.value = true
  try {
    const res = await listCodexJobs(selectedAgent.value.id)
    codexJobs.value = res.jobs || []
  } catch {
    codexJobs.value = []
  } finally {
    loadingCodexJobs.value = false
  }
}

async function startCodexJob() {
  if (!selectedAgent.value || !codexInstruction.value.trim()) return
  creatingCodexJob.value = true
  try {
    const res = await createCodexJob({
      agent_id: selectedAgent.value.id,
      instruction: codexInstruction.value.trim()
    })
    codexInstruction.value = ''
    selectedCodexJob.value = res.job
    codexLogs.value = []
    ElMessage.success('Codex 开发任务已发起')
    await loadCodexJobs()
    await refreshSelectedCodexJob()
  } catch {
    ElMessage.error('Codex 开发任务创建失败')
  } finally {
    creatingCodexJob.value = false
  }
}

async function selectCodexJob(jobId: string) {
  const job = codexJobs.value.find(item => item.id === jobId)
  selectedCodexJob.value = job || null
  await refreshSelectedCodexJob()
}

async function refreshSelectedCodexJob() {
  if (!selectedCodexJob.value) return
  const res = await getCodexJobLogs(selectedCodexJob.value.id)
  selectedCodexJob.value = res.job
  codexLogs.value = res.logs || []
  await loadCodexJobs()
}

async function cancelSelectedCodexJob() {
  if (!selectedCodexJob.value) return
  const res = await cancelCodexJob(selectedCodexJob.value.id)
  selectedCodexJob.value = res.job
  await refreshSelectedCodexJob()
}

async function loadMessages(agentId: string) {
  loadingMessages.value = true
  try {
    const res = await getAgentMessages(agentId)
    messages.value = res.messages || []
    await scrollToBottom()
  } catch {
    messages.value = []
  } finally {
    loadingMessages.value = false
  }
}

async function sendMessage() {
  if (!canSend.value || !selectedAgent.value) return
  const text = draft.value.trim() || '请结合附件内容进行分析。'
  const attachments = selectedAttachments.value.slice()
  const agent = selectedAgent.value
  draft.value = ''
  selectedAttachments.value = []
  const optimisticMessage: ChatMessage = { role: 'user', content: text, timestamp: new Date().toISOString(), attachments }
  messages.value.push(optimisticMessage)
  await scrollToBottom()

  sending.value = true
  try {
    const res = await sendAgentMessage(agent.id, text, attachments)
    messages.value.push({
      role: 'agent',
      content: res.agent_response,
      timestamp: res.timestamp || new Date().toISOString()
    })
    await loadConversations()
  } catch {
    messages.value = messages.value.filter(message => message !== optimisticMessage)
    draft.value = text
    selectedAttachments.value = attachments
    ElMessage.error('OpenClaw 智能体调用失败，请检查服务日志')
  } finally {
    sending.value = false
    await scrollToBottom()
  }
}

async function confirmClear() {
  if (!selectedAgent.value) return
  await ElMessageBox.confirm(`清空与 ${selectedAgent.value.name} 的对话记录？`, '确认清空', {
    confirmButtonText: '清空',
    cancelButtonText: '取消',
    type: 'warning'
  })
  await clearAgentMessages(selectedAgent.value.id)
  messages.value = []
  await loadConversations()
}

function usePrompt(text: string) {
  draft.value = draft.value ? `${draft.value}\n\n${text}` : text
}

function selectConversation(agentId: string) {
  const agent = agents.value.find(item => item.id === agentId)
  if (agent) selectAgent(agent)
}

function handleTreeNodeClick(node: ChatAgentNode) {
  if (node.agent) {
    selectAgent(node.agent)
    return
  }
  if (hasTreeChildren(node)) toggleTreeNode(node.id)
}

function hasTreeChildren(node: ChatAgentNode) {
  return Boolean(treeChildrenByParent.value.get(node.id)?.length)
}

function isTreeCollapsed(nodeId: string) {
  return collapsedTreeNodeIds.value.has(nodeId)
}

function toggleTreeNode(nodeId: string) {
  const next = new Set(collapsedTreeNodeIds.value)
  if (next.has(nodeId)) next.delete(nodeId)
  else next.add(nodeId)
  collapsedTreeNodeIds.value = next
}

function isTreeNodeVisible(node: ChatAgentNode) {
  let parentId = node.parent_id
  while (parentId) {
    if (collapsedTreeNodeIds.value.has(parentId)) return false
    parentId = treeNodeById.value.get(parentId)?.parent_id
  }
  return true
}

function addNodeWithAncestors(node: ChatAgentNode, ids: Set<string>) {
  ids.add(node.id)
  let parentId = node.parent_id
  while (parentId) {
    ids.add(parentId)
    parentId = treeNodeById.value.get(parentId)?.parent_id
  }
}

function addDescendants(nodeId: string, ids: Set<string>) {
  for (const child of treeChildrenByParent.value.get(nodeId) || []) {
    ids.add(child.id)
    addDescendants(child.id, ids)
  }
}

function agentName(agentId: string) {
  return agents.value.find(agent => agent.id === agentId)?.name || agentId
}

function agentMeta(agent: ChatAgent) {
  const path = (agent.path || []).slice(0, -1).join(' / ')
  return [agent.role || agent.title, path || agent.team || agent.id].filter(Boolean).join(' · ')
}

function agentInitial(agent: Pick<ChatAgent, 'name' | 'id'> | ChatAgentNode) {
  return (agent.name || agent.id).slice(0, 1).toUpperCase()
}

function openFilePicker() {
  fileInput.value?.click()
}

async function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files || [])
  if (!files.length) return

  try {
    const attachments = await Promise.all(files.map(fileToAttachment))
    selectedAttachments.value.push(...attachments)
  } catch {
    ElMessage.error('附件读取失败')
  } finally {
    input.value = ''
  }
}

function fileToAttachment(file: File): Promise<ChatAttachment> {
  const maxSize = 8 * 1024 * 1024
  if (file.size > maxSize) {
    ElMessage.warning(`${file.name} 超过 8MB，已跳过`)
    return Promise.resolve({
      id: `${Date.now()}-${file.name}`,
      name: file.name,
      type: file.type || 'application/octet-stream',
      size: file.size
    })
  }

  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve({
      id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      name: file.name,
      type: file.type || 'application/octet-stream',
      size: file.size,
      data_url: String(reader.result || '')
    })
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

function removeAttachment(id?: string) {
  selectedAttachments.value = selectedAttachments.value.filter(item => item.id !== id)
}

function formatFileSize(size = 0) {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function codexStatusLabel(status: CodexJobStatus) {
  return {
    queued: '排队中',
    running: '执行中',
    succeeded: '已完成',
    failed: '失败',
    cancelled: '已取消'
  }[status] || status
}

function codexStatusType(status: CodexJobStatus) {
  return {
    queued: 'info',
    running: 'primary',
    succeeded: 'success',
    failed: 'danger',
    cancelled: 'warning'
  }[status] || 'info'
}

function formatTime(value: string) {
  if (!value) return '无记录'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '无记录'
  return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

async function scrollToBottom() {
  await nextTick()
  if (messagesEl.value) {
    // 优化: 使用 scrollIntoView 替代直接读写 scrollTop
    // 之前: read scrollHeight → write scrollTop = Layout Thrashing
    // 现在: scrollIntoView 由浏览器优化，避免强制 reflow
    const container = messagesEl.value
    const lastMsg = container.lastElementChild
    if (lastMsg) {
      lastMsg.scrollIntoView({ behavior: 'smooth', block: 'end' })
    } else {
      container.scrollTop = container.scrollHeight
    }
  }
}
</script>

<style scoped>
.agent-chat-page {
  display: grid;
  grid-template-columns: clamp(210px, 18vw, 260px) minmax(0, 1fr) clamp(170px, 15vw, 220px);
  gap: 12px;
  height: calc(100vh - 96px);
  min-height: 0;
  overflow: hidden;
}

.agent-rail,
.chat-panel,
.context-panel {
  min-height: 0;
  border: 1px solid var(--line-color);
  background: var(--panel-bg);
}

.agent-rail,
.context-panel {
  padding: 16px;
}

.agent-rail {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.rail-head,
.chat-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

h1,
h2,
h3,
p {
  margin: 0;
}

h1 {
  font-size: 20px;
  color: var(--text-primary);
}

h2 {
  font-size: 16px;
  color: var(--text-primary);
}

h3 {
  font-size: 14px;
  color: var(--text-primary);
  margin-bottom: 10px;
}

.rail-head p,
.chat-head p,
.muted {
  color: var(--text-secondary);
  font-size: 13px;
  margin-top: 4px;
}

.agent-tree {
  display: flex;
  flex-direction: column;
  flex: 1;
  gap: 6px;
  margin-top: 14px;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.agent-row,
.prompt-list button,
.conversation-list button {
  border: 1px solid transparent;
  background: transparent;
  color: var(--text-primary);
  cursor: pointer;
  text-align: left;
}

.agent-row {
  display: grid;
  grid-template-columns: calc(var(--depth, 0) * 14px) 16px 32px minmax(0, 1fr) 10px;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  border-radius: 6px;
}

.agent-row:disabled {
  cursor: default;
}

.agent-row:hover,
.agent-row.active {
  border-color: var(--view-color-border);
  background: var(--view-color-soft);
}

.agent-row.group {
  color: var(--text-secondary);
  background: transparent;
}

.agent-row.group:hover {
  border-color: transparent;
  background: transparent;
}

.agent-row.planned {
  opacity: 0.66;
}

.tree-line {
  width: 100%;
  height: 1px;
  border-top: 1px solid rgba(139, 148, 158, 0.24);
}

.tree-toggle,
.tree-toggle-spacer {
  width: 16px;
  height: 16px;
}

.tree-toggle {
  color: var(--text-secondary);
}

.tree-toggle-spacer {
  display: block;
}

.avatar {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 6px;
  background: rgba(var(--view-rgb), 0.18);
  color: var(--view-color);
  font-weight: 700;
}

.agent-main {
  min-width: 0;
}

.agent-name,
.agent-meta {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-name {
  font-size: 14px;
}

.agent-meta {
  margin-top: 2px;
  color: var(--text-secondary);
  font-size: 12px;
}

.status-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #8b949e;
}

.status-dot.online,
.status-dot.busy {
  background: #2ea043;
}

.status-dot.idle {
  background: #d29922;
}

.status-dot.offline {
  background: #6e7681;
}

.chat-panel {
  display: flex;
  flex-direction: column;
  min-width: 0;
  border-color: rgba(var(--view-rgb), 0.52);
  overflow: hidden;
  box-shadow: inset 0 0 0 1px rgba(var(--view-rgb), 0.12);
}

.chat-head {
  padding: 14px 16px;
  border-bottom: 1px solid var(--line-color);
  background: rgba(var(--view-rgb), 0.08);
}

.chat-window-kicker {
  display: block;
  margin-bottom: 4px;
  color: var(--view-color);
  font-size: 12px;
  font-weight: 700;
}

.head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.messages {
  flex: 1;
  min-height: 0;
  padding: 18px 20px;
  overflow-y: auto;
  overscroll-behavior: contain;
  background:
    linear-gradient(180deg, rgba(13, 17, 23, 0.18), rgba(13, 17, 23, 0)),
    var(--panel-bg);
}

.empty-state {
  display: grid;
  place-items: center;
  align-content: center;
  min-height: 300px;
  color: var(--text-secondary);
  text-align: center;
  gap: 8px;
}

.empty-state h3 {
  margin: 0;
}

.message {
  max-width: min(94%, 1120px);
  margin-bottom: 14px;
  padding: 12px 14px;
  border: 1px solid var(--line-color);
  border-radius: 6px;
  background: var(--card-bg-soft);
}

.message.from-user {
  margin-left: auto;
  border-color: var(--view-color-border);
  background: var(--view-color-soft);
}

.message.pending {
  opacity: 0.72;
}

.message-meta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
  color: var(--text-secondary);
  font-size: 12px;
}

.message p {
  color: var(--text-primary);
  line-height: 1.65;
  white-space: pre-wrap;
}

.message-attachments {
  display: grid;
  gap: 8px;
  margin-top: 10px;
}

.attachment-chip {
  display: grid;
  grid-template-columns: 28px 1fr;
  gap: 8px;
  align-items: center;
  max-width: 360px;
  padding: 8px;
  border: 1px solid var(--line-color);
  border-radius: 6px;
  color: var(--text-primary);
  text-decoration: none;
  background: rgba(13, 17, 23, 0.52);
}

.attachment-icon {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  color: var(--view-color);
  background: rgba(var(--view-rgb), 0.18);
  font-size: 12px;
  font-weight: 700;
}

.attachment-chip strong,
.attachment-chip small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.attachment-chip strong {
  font-size: 12px;
}

.attachment-chip small {
  margin-top: 2px;
  color: var(--text-secondary);
  font-size: 11px;
}

.composer {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 10px;
  padding: 14px 16px;
  border-top: 1px solid var(--line-color);
  background: #0d1117;
}

.composer-main {
  min-width: 0;
}

.composer-actions {
  display: grid;
  grid-template-columns: 38px 92px;
  gap: 8px;
  align-self: end;
}

.hidden-file-input {
  display: none;
}

.selected-attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.selected-attachment {
  display: inline-grid;
  grid-template-columns: auto minmax(70px, 160px) auto auto;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  padding: 6px 8px;
  border: 1px solid var(--line-color);
  border-radius: 6px;
  color: var(--text-primary);
  background: var(--card-bg-soft);
  font-size: 12px;
}

.selected-attachment strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.selected-attachment small {
  color: var(--text-secondary);
}

.selected-attachment button {
  border: 0;
  color: var(--view-color);
  background: transparent;
  cursor: pointer;
}

.context-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 12px;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.codex-panel,
.codex-detail {
  display: grid;
  gap: 10px;
}

.codex-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.codex-job-list {
  display: grid;
  gap: 8px;
  margin-top: 10px;
}

.codex-job {
  display: grid;
  gap: 4px;
  width: 100%;
  padding: 10px;
  border: 1px solid var(--line-color);
  border-radius: 6px;
  color: var(--text-primary);
  text-align: left;
  cursor: pointer;
  background: var(--card-bg-soft);
}

.codex-job:hover,
.codex-job.active {
  border-color: var(--view-color-border);
  background: var(--view-color-soft);
}

.codex-job span,
.codex-job small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.codex-job small {
  color: var(--text-secondary);
  font-size: 12px;
}

.codex-detail {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--line-color);
}

.codex-detail-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  color: var(--text-secondary);
  font-size: 12px;
}

.codex-detail-head span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.codex-summary,
.codex-log,
.codex-error {
  max-height: 240px;
  margin: 0;
  padding: 10px;
  overflow: auto;
  border: 1px solid var(--line-color);
  border-radius: 6px;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  line-height: 1.55;
  color: var(--text-primary);
  background: #0d1117;
}

.codex-error {
  color: #ff7b72;
}

.prompt-list,
.conversation-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.prompt-list button,
.conversation-list button {
  width: 100%;
  padding: 10px;
  border-color: var(--line-color);
  border-radius: 6px;
  background: var(--card-bg-soft);
}

.prompt-list button:hover,
.conversation-list button:hover {
  border-color: var(--view-color-border);
  background: var(--view-color-soft);
}

.prompt-list span,
.conversation-list span,
.prompt-list small,
.conversation-list small {
  display: block;
}

.prompt-list span,
.conversation-list span {
  font-size: 13px;
  color: var(--text-primary);
}

.prompt-list small,
.conversation-list small {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-secondary);
}

@media (max-width: 1180px) {
  .agent-chat-page {
    grid-template-columns: 240px 1fr;
  }

  .context-panel {
    grid-column: 1 / -1;
    max-height: 300px;
  }
}

@media (max-width: 820px) {
  .agent-chat-page {
    grid-template-columns: 1fr;
    grid-template-rows: auto minmax(520px, 1fr) auto;
    height: auto;
    min-height: calc(100vh - 96px);
    overflow: visible;
  }

  .agent-rail,
  .chat-panel,
  .context-panel {
    grid-column: 1;
    grid-row: auto;
  }

  .agent-tree {
    flex: none;
    max-height: 260px;
  }

  .chat-head,
  .head-actions {
    align-items: flex-start;
    flex-direction: column;
  }

  .message {
    max-width: 100%;
  }

  .composer,
  .composer-actions {
    grid-template-columns: 1fr;
  }
}
</style>
