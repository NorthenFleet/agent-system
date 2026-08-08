<template>
  <section class="writing-ai-pane" aria-label="AI 协作窗口">
    <header class="ai-pane-head">
      <div class="ai-pane-title">
        <span class="eyebrow">HUMAN × AI</span>
        <strong>协作写作</strong>
      </div>
      <div class="head-actions">
        <el-tooltip content="刷新会话" placement="bottom">
          <el-button
            :icon="Refresh"
            circle
            :loading="loadingMessages"
            aria-label="刷新会话"
            @click="loadMessages()"
          />
        </el-tooltip>
        <label class="target-lock">
          <span>{{ targetLockedLocal ? '已锁定目标' : '跟随焦点' }}</span>
          <el-switch
            :model-value="targetLockedLocal"
            aria-label="锁定 AI 目标"
            @change="setTargetLocked(Boolean($event))"
          />
        </label>
      </div>
    </header>

    <section class="ai-context-strip" :class="{ unavailable: !effectiveTarget }">
      <div class="context-icon"><el-icon><ChatLineSquare /></el-icon></div>
      <div class="context-copy">
        <small>当前目标</small>
        <strong>{{ targetTitle }}</strong>
        <span>{{ targetDetail }}</span>
      </div>
      <el-tag v-if="effectiveTarget" size="small" effect="plain">
        {{ effectiveTarget.kind === 'document' ? '文档' : 'PPT' }}
      </el-tag>
      <el-tag v-else size="small" type="info" effect="plain">待选择</el-tag>
    </section>

    <div class="ai-session-bar">
      <el-select
        v-model="activeConversationId"
        class="conversation-select"
        size="small"
        placeholder="选择会话"
        aria-label="选择 AI 会话"
        @change="handleConversationChange"
      >
        <el-option
          v-for="conversation in conversations"
          :key="conversation.id"
          :label="conversation.title"
          :value="conversation.id"
        />
      </el-select>
      <el-select v-model="selectedAgent" size="small" aria-label="选择协作智能体">
        <el-option
          v-for="agent in availableAgents"
          :key="agent.id"
          :label="agent.name"
          :value="agent.id"
        />
      </el-select>
      <el-button size="small" :loading="creatingConversation" @click="createConversation">
        新会话
      </el-button>
    </div>

    <div ref="messageViewport" class="message-viewport">
      <div v-if="loadingInitial" class="loading-state">
        <el-icon class="is-loading"><Refresh /></el-icon>
        <span>正在恢复协作记录</span>
      </div>
      <el-empty
        v-else-if="!messages.length"
        description="选择目标后，可让智能体生成可审阅的修改建议"
        :image-size="56"
      />
      <article
        v-for="message in messages"
        v-else
        :key="message.id"
        class="ai-message"
        :class="[`role-${message.role}`, `status-${message.status}`]"
      >
        <header>
          <strong>{{ message.role === 'user' ? '我' : activeAgentName }}</strong>
          <div class="message-meta">
            <el-tag
              v-if="message.role === 'assistant'"
              size="small"
              effect="plain"
              :type="statusMeta(message).type"
            >
              {{ statusMeta(message).label }}
            </el-tag>
            <time v-if="message.created_at">{{ formatTime(message.created_at) }}</time>
          </div>
        </header>
        <p>{{ message.content }}</p>
        <div v-if="messageTargetSummary(message)" class="message-target">
          {{ messageTargetSummary(message) }}
        </div>
        <el-alert
          v-if="message.error"
          :title="message.error"
          type="error"
          :closable="false"
          show-icon
        />
        <footer v-if="message.role === 'assistant' && (isPending(message) || message.proposal_ids?.length)">
          <el-button
            v-if="isPending(message)"
            size="small"
            :icon="Close"
            :loading="cancellingMessageId === message.id"
            @click="cancelMessage(message)"
          >
            取消任务
          </el-button>
          <template v-for="proposalId in message.proposal_ids" :key="proposalId">
            <el-tag size="small" effect="plain">建议 {{ shortId(proposalId) }}</el-tag>
            <el-button
              v-if="message.target_context.kind === 'document'"
              size="small"
              type="primary"
              plain
              :disabled="Boolean(proposalDecisions[proposalId])"
              @click="decideProposal(message, proposalId, 'accept')"
            >
              {{ proposalDecisions[proposalId] === 'accept' ? '已接受' : '接受' }}
            </el-button>
            <el-button
              v-if="message.target_context.kind === 'document'"
              size="small"
              :disabled="Boolean(proposalDecisions[proposalId])"
              @click="decideProposal(message, proposalId, 'reject')"
            >
              {{ proposalDecisions[proposalId] === 'reject' ? '已拒绝' : '拒绝' }}
            </el-button>
            <span v-else class="presentation-review-note">请在 PPT 窗口审阅并应用</span>
          </template>
        </footer>
      </article>
    </div>

    <footer class="ai-composer">
      <div class="quick-actions" aria-label="AI 快捷指令">
        <el-button
          v-for="action in quickActions"
          :key="action.key"
          size="small"
          :disabled="!canSubmit"
          @click="runQuickAction(action)"
        >
          {{ action.label }}
        </el-button>
      </div>
      <el-input
        v-model="instruction"
        type="textarea"
        :rows="3"
        resize="none"
        maxlength="4000"
        show-word-limit
        placeholder="说明目标、语气、证据边界和必须保留的内容……"
        aria-label="AI 协作指令"
        @keydown.meta.enter.prevent="submitInstruction()"
        @keydown.ctrl.enter.prevent="submitInstruction()"
      />
      <div class="composer-actions">
        <span>{{ targetLockedLocal ? '提交时使用锁定快照' : '提交时冻结当前目标快照' }}</span>
        <el-button
          type="primary"
          :icon="MagicStick"
          :loading="submitting"
          :disabled="!canSubmit || !instruction.trim()"
          @click="submitInstruction()"
        >
          生成修改建议
        </el-button>
      </div>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ChatLineSquare, Close, MagicStick, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import {
  acceptWritingProposal,
  cancelWritingAiConversationMessage,
  createWritingAiConversation,
  createWritingAiConversationMessage,
  getWritingAiConversationMessages,
  getWritingAiConversations,
  rejectWritingProposal,
  type WritingAiConversation,
  type WritingAiMessage,
  type WritingAiTarget
} from '@/api/writing'

type ProposalDecision = 'accept' | 'reject'
type QuickAction = { key: string; label: string; instruction: string }

const props = withDefaults(defineProps<{
  projectId: string
  target?: WritingAiTarget
  locked?: boolean
  conversationId?: string
}>(), {
  locked: false,
  conversationId: ''
})

const emit = defineEmits<{
  'lock-changed': [locked: boolean]
  'conversation-changed': [conversationId: string]
}>()

const availableAgents = [
  { id: 'ultra-magnus', name: '通天晓 · 文档写作' },
  { id: 'leonardo', name: '李奥纳多 · 结构审稿' },
  { id: 'perceptor', name: '感知器 · 资料核查' },
  { id: 'michelangelo', name: '米开朗基罗 · 演示制作' }
]

const documentActions: QuickAction[] = [
  { key: 'polish', label: '润色', instruction: '在不改变事实、数据和引用含义的前提下润色当前内容，给出修改建议和理由。' },
  { key: 'expand', label: '扩写', instruction: '围绕当前内容补充必要论证和衔接，不虚构数据或来源。' },
  { key: 'compress', label: '压缩', instruction: '压缩当前内容，保留核心主张、关键证据和必要限定条件。' },
  { key: 'verify', label: '核查', instruction: '核查当前内容的逻辑、事实、证据和引用风险，列出问题并给出修订建议。' }
]

const presentationActions: QuickAction[] = [
  { key: 'refine-slide', label: '微调页面', instruction: '优化当前PPT页的标题、核心主张和信息层级，保持原始证据边界。' },
  { key: 'speaker-notes', label: '生成讲稿', instruction: '为当前PPT页生成简洁、连贯且与页面证据一致的讲解稿。' },
  { key: 'compress-slide', label: '压缩要点', instruction: '压缩当前PPT页文字，使核心主张和证据能够快速扫描。' },
  { key: 'verify-slide', label: '核查证据', instruction: '核查当前PPT页的主张、证据和正文映射，给出风险和修改建议。' }
]

const conversations = ref<WritingAiConversation[]>([])
const messages = ref<WritingAiMessage[]>([])
const activeConversationId = ref(props.conversationId)
const selectedAgent = ref('ultra-magnus')
const instruction = ref('')
const targetLockedLocal = ref(props.locked)
const lockedTarget = ref<WritingAiTarget | undefined>(props.locked ? cloneTarget(props.target) : undefined)
const loadingInitial = ref(true)
const loadingMessages = ref(false)
const creatingConversation = ref(false)
const submitting = ref(false)
const cancellingMessageId = ref('')
const proposalDecisions = ref<Record<string, ProposalDecision>>({})
const messageViewport = ref<HTMLElement>()
let pollTimer: ReturnType<typeof setTimeout> | undefined
let bootstrapSequence = 0

const effectiveTarget = computed(() => targetLockedLocal.value ? lockedTarget.value : props.target)
const canSubmit = computed(() => Boolean(activeConversationId.value && effectiveTarget.value?.document_id && !submitting.value))
const activeConversation = computed(() => conversations.value.find(row => row.id === activeConversationId.value))
const activeAgentName = computed(() => (
  availableAgents.find(agent => agent.id === selectedAgent.value)?.name
  || activeConversation.value?.agent_id
  || '协作智能体'
))
const quickActions = computed(() => (
  effectiveTarget.value?.kind === 'presentation' ? presentationActions : documentActions
))
const targetTitle = computed(() => effectiveTarget.value?.document_title || (
  effectiveTarget.value?.kind === 'presentation' ? '当前 PPT' : '当前文档'
))
const targetDetail = computed(() => describeTarget(effectiveTarget.value) || '请先在另一个窗口选择文档、章节或PPT页')

function cloneTarget(target?: WritingAiTarget): WritingAiTarget | undefined {
  if (!target) return undefined
  return JSON.parse(JSON.stringify(target)) as WritingAiTarget
}

function setTargetLocked(locked: boolean) {
  targetLockedLocal.value = locked
  lockedTarget.value = locked ? cloneTarget(props.target) : undefined
  emit('lock-changed', locked)
}

function describeTarget(target?: WritingAiTarget) {
  if (!target) return ''
  if (target.kind === 'presentation') return `第 ${Math.max(1, Number(target.slide || 1))} 页 · 结构版本 ${target.revision ?? '未标注'}`
  if (target.scope === 'selection' && target.selection?.text) {
    const preview = target.selection.text.replace(/\s+/g, ' ').trim()
    return `选区 · ${preview.slice(0, 42)}${preview.length > 42 ? '…' : ''}`
  }
  if (target.section_title) return `${target.section_title} · 修订 ${target.revision ?? '未标注'}`
  if (target.block_id) return `段落 ${shortId(target.block_id)} · 修订 ${target.block_revision ?? '未标注'}`
  return `${target.scope === 'document' ? '全文' : '当前章节'} · 修订 ${target.revision ?? '未标注'}`
}

function messageTargetSummary(message: WritingAiMessage) {
  const target = message.target_context as WritingAiTarget | undefined
  const detail = describeTarget(target)
  return detail ? `目标快照：${target?.document_title || '当前资源'} · ${detail}` : ''
}

function isPending(message: WritingAiMessage) {
  return message.status === 'queued' || message.status === 'running'
}

function statusMeta(message: WritingAiMessage): { label: string; type: '' | 'success' | 'warning' | 'info' | 'danger' } {
  if (message.status === 'queued') return { label: '排队中', type: 'info' }
  if (message.status === 'running') return { label: '生成中', type: 'warning' }
  if (message.status === 'partially_applied') return { label: '部分应用', type: 'warning' }
  if (message.status === 'applied') return { label: '已应用', type: 'success' }
  if (message.status === 'conflicted') return { label: '存在冲突', type: 'danger' }
  if (message.status === 'failed') return { label: '失败', type: 'danger' }
  if (message.status === 'cancelled') return { label: '已取消', type: 'info' }
  if (message.proposal_ids?.length) return { label: '待审建议', type: 'success' }
  return { label: '已完成', type: 'success' }
}

function shortId(value: string) {
  return value.length > 12 ? `${value.slice(0, 8)}…` : value
}

function formatTime(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString('zh-CN', { hour12: false, month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function requestId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  return `ai-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function clearPolling() {
  if (pollTimer) clearTimeout(pollTimer)
  pollTimer = undefined
}

function schedulePolling() {
  clearPolling()
  if (!messages.value.some(isPending)) return
  pollTimer = setTimeout(() => loadMessages(true), 2500)
}

async function scrollToLatest() {
  await nextTick()
  if (messageViewport.value) messageViewport.value.scrollTop = messageViewport.value.scrollHeight
}

async function loadMessages(silent = false) {
  if (!activeConversationId.value) {
    messages.value = []
    return
  }
  if (!silent) loadingMessages.value = true
  try {
    messages.value = await getWritingAiConversationMessages(props.projectId, activeConversationId.value)
    await scrollToLatest()
    schedulePolling()
  } catch (error) {
    if (silent) schedulePolling()
    else ElMessage.error(errorMessage(error, 'AI 会话加载失败'))
  } finally {
    if (!silent) loadingMessages.value = false
  }
}

async function bootstrap() {
  const sequence = ++bootstrapSequence
  loadingInitial.value = true
  clearPolling()
  try {
    const rows = await getWritingAiConversations(props.projectId)
    if (sequence !== bootstrapSequence) return
    conversations.value = rows
    let selected = props.conversationId && rows.some(row => row.id === props.conversationId)
      ? props.conversationId
      : rows[0]?.id || ''
    if (!selected) {
      const created = await createWritingAiConversation(props.projectId, {
        title: '协作写作',
        agent_id: selectedAgent.value
      })
      if (sequence !== bootstrapSequence) return
      conversations.value = [created]
      selected = created.id
    }
    activeConversationId.value = selected
    const conversation = conversations.value.find(row => row.id === selected)
    if (conversation?.agent_id) selectedAgent.value = conversation.agent_id
    emit('conversation-changed', selected)
    await loadMessages()
  } catch (error) {
    if (sequence === bootstrapSequence) ElMessage.error(errorMessage(error, 'AI 协作窗口初始化失败'))
  } finally {
    if (sequence === bootstrapSequence) loadingInitial.value = false
  }
}

async function handleConversationChange(conversationId: string) {
  activeConversationId.value = conversationId
  const conversation = conversations.value.find(row => row.id === conversationId)
  if (conversation?.agent_id) selectedAgent.value = conversation.agent_id
  emit('conversation-changed', conversationId)
  await loadMessages()
}

async function createConversation() {
  creatingConversation.value = true
  try {
    const created = await createWritingAiConversation(props.projectId, {
      title: effectiveTarget.value?.kind === 'presentation' ? 'PPT 协作' : '文档协作',
      agent_id: selectedAgent.value
    })
    conversations.value = [created, ...conversations.value]
    await handleConversationChange(created.id)
  } catch (error) {
    ElMessage.error(errorMessage(error, '新建 AI 会话失败'))
  } finally {
    creatingConversation.value = false
  }
}

async function submitInstruction(value = instruction.value) {
  const content = value.trim()
  const target = cloneTarget(effectiveTarget.value)
  if (!content || !target || !activeConversationId.value) return
  submitting.value = true
  try {
    await createWritingAiConversationMessage(props.projectId, activeConversationId.value, {
      client_message_id: requestId(),
      agent_id: selectedAgent.value,
      content,
      target
    })
    instruction.value = ''
    await loadMessages()
  } catch (error) {
    ElMessage.error(errorMessage(error, 'AI 修改建议提交失败'))
  } finally {
    submitting.value = false
  }
}

async function runQuickAction(action: QuickAction) {
  await submitInstruction(action.instruction)
}

async function cancelMessage(message: WritingAiMessage) {
  if (!activeConversationId.value) return
  cancellingMessageId.value = message.id
  try {
    await cancelWritingAiConversationMessage(props.projectId, activeConversationId.value, message.id)
    await loadMessages()
  } catch (error) {
    ElMessage.error(errorMessage(error, 'AI 任务取消失败'))
  } finally {
    cancellingMessageId.value = ''
  }
}

async function decideProposal(message: WritingAiMessage, proposalId: string, decision: ProposalDecision) {
  const target = message.target_context as WritingAiTarget | undefined
  if (proposalDecisions.value[proposalId]) return
  try {
    if (target?.kind === 'document' && target.document_id) {
      if (decision === 'accept') await acceptWritingProposal(props.projectId, target.document_id, proposalId)
      else await rejectWritingProposal(props.projectId, target.document_id, proposalId)
    }
    proposalDecisions.value = { ...proposalDecisions.value, [proposalId]: decision }
    ElMessage.success(decision === 'accept' ? '建议已接受' : '建议已拒绝')
  } catch (error) {
    ElMessage.error(errorMessage(error, decision === 'accept' ? '接受建议失败' : '拒绝建议失败'))
  }
}

function errorMessage(error: unknown, fallback: string) {
  const detail = (error as any)?.response?.data?.detail
  if (typeof detail === 'string' && detail) return detail
  if (detail?.message) return String(detail.message)
  return fallback
}

watch(() => props.locked, value => {
  if (value === targetLockedLocal.value) return
  targetLockedLocal.value = value
  lockedTarget.value = value ? cloneTarget(props.target) : undefined
})

watch(() => props.target, value => {
  if (targetLockedLocal.value && !lockedTarget.value && value) {
    lockedTarget.value = cloneTarget(value)
  }
})

watch(() => props.conversationId, value => {
  if (!value || value === activeConversationId.value) return
  if (conversations.value.some(row => row.id === value)) handleConversationChange(value)
})

watch(() => props.projectId, bootstrap)
onMounted(bootstrap)
onBeforeUnmount(() => {
  bootstrapSequence += 1
  clearPolling()
})

defineExpose({
  refresh: loadMessages,
  submit: submitInstruction,
  setTargetLocked,
  activeConversationId
})
</script>

<style scoped>
.writing-ai-pane { display: grid; grid-template-rows: auto auto auto minmax(220px, 1fr) auto; min-width: 0; min-height: 640px; height: 100%; overflow: hidden; background: var(--content-bg); color: var(--text-primary); }
.ai-pane-head, .ai-session-bar, .ai-composer { border-color: var(--line-color); background: var(--panel-bg); }
.ai-pane-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; min-width: 0; padding: 10px 12px; border-bottom: 1px solid var(--line-color); }
.ai-pane-title { display: grid; gap: 2px; }
.ai-pane-title .eyebrow { color: var(--view-color-primary); font-size: 9px; }
.ai-pane-title strong { font-size: 14px; }
.head-actions, .target-lock, .message-meta, .composer-actions { display: flex; align-items: center; gap: 8px; }
.target-lock { color: var(--text-secondary); font-size: 10px; white-space: nowrap; }
.ai-context-strip { display: grid; grid-template-columns: 32px minmax(0, 1fr) auto; align-items: center; gap: 9px; margin: 10px 12px 0; padding: 10px; border: 1px solid color-mix(in srgb, var(--view-color-primary) 44%, var(--line-color)); border-radius: 6px; background: color-mix(in srgb, var(--view-color-primary) 7%, var(--card-bg)); }
.ai-context-strip.unavailable { border-color: var(--line-color); background: var(--card-bg); }
.context-icon { display: grid; width: 32px; height: 32px; place-items: center; border-radius: 5px; background: color-mix(in srgb, var(--view-color-primary) 16%, transparent); color: var(--view-color-primary); }
.context-copy { display: grid; gap: 2px; min-width: 0; }
.context-copy small, .context-copy span { overflow: hidden; color: var(--text-secondary); font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.context-copy strong { overflow: hidden; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.ai-session-bar { display: grid; grid-template-columns: minmax(120px, 1fr) minmax(140px, .9fr) auto; gap: 8px; padding: 10px 12px; border-bottom: 1px solid var(--line-color); }
.message-viewport { min-height: 0; overflow-y: auto; padding: 12px; scroll-behavior: smooth; }
.loading-state { display: grid; place-items: center; gap: 8px; min-height: 180px; color: var(--text-secondary); font-size: 11px; }
.ai-message { display: grid; gap: 8px; max-width: 92%; margin-bottom: 12px; padding: 10px 12px; border: 1px solid var(--line-color); border-radius: 6px; background: var(--card-bg); }
.ai-message.role-user { margin-left: auto; border-color: color-mix(in srgb, var(--view-color-primary) 48%, var(--line-color)); background: color-mix(in srgb, var(--view-color-primary) 9%, var(--card-bg)); }
.ai-message.status-conflicted, .ai-message.status-failed { border-color: color-mix(in srgb, var(--el-color-danger) 55%, var(--line-color)); }
.ai-message > header { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.ai-message > header strong { font-size: 11px; }
.ai-message time { color: var(--text-secondary); font-size: 8px; }
.ai-message p { margin: 0; color: var(--text-primary); font-size: 11px; line-height: 1.65; white-space: pre-wrap; word-break: break-word; }
.message-target { padding-top: 6px; border-top: 1px solid var(--line-color); color: var(--text-secondary); font-size: 9px; }
.ai-message > footer { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }
.presentation-review-note { color: var(--text-secondary); font-size: 9px; }
.ai-composer { display: grid; gap: 9px; padding: 10px 12px 12px; border-top: 1px solid var(--line-color); }
.quick-actions { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 6px; }
.quick-actions .el-button { width: 100%; margin: 0; }
.composer-actions { justify-content: space-between; }
.composer-actions > span { color: var(--text-secondary); font-size: 9px; }
@media (max-width: 640px) {
  .writing-ai-pane { min-height: calc(100vh - 260px); }
  .ai-pane-head { align-items: flex-start; }
  .head-actions { align-items: flex-end; flex-direction: column-reverse; }
  .ai-session-bar { grid-template-columns: 1fr auto; }
  .conversation-select { grid-column: 1 / -1; }
  .quick-actions { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .composer-actions { align-items: flex-end; }
  .composer-actions > span { max-width: 44%; }
}
</style>
