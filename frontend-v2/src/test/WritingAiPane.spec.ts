import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import WritingAiPane from '@/components/writing/WritingAiPane.vue'
import type { WritingAiMessage, WritingAiTarget } from '@/api/writing'

const mocks = vi.hoisted(() => ({
  getConversations: vi.fn(),
  createConversation: vi.fn(),
  getMessages: vi.fn(),
  createMessage: vi.fn(),
  cancelMessage: vi.fn(),
  acceptProposal: vi.fn(),
  rejectProposal: vi.fn()
}))

vi.mock('@/api/writing', async importOriginal => {
  const original = await importOriginal<Record<string, unknown>>()
  return {
    ...original,
    getWritingAiConversations: mocks.getConversations,
    createWritingAiConversation: mocks.createConversation,
    getWritingAiConversationMessages: mocks.getMessages,
    createWritingAiConversationMessage: mocks.createMessage,
    cancelWritingAiConversationMessage: mocks.cancelMessage,
    acceptWritingProposal: mocks.acceptProposal,
    rejectWritingProposal: mocks.rejectProposal
  }
})

const conversation = {
  id: 'conversation-1',
  project_id: 'project-1',
  agent_id: 'ultra-magnus',
  title: '协作写作',
  status: 'active'
}

const documentTarget: WritingAiTarget = {
  kind: 'document',
  document_id: 'document-1',
  document_title: '博士论文正文',
  scope: 'block',
  section_id: 'section-1',
  section_title: '第1章 绪论',
  block_id: 'block-1',
  block_revision: 3,
  revision: 12
}

function assistantMessage(status = 'running'): WritingAiMessage {
  return {
    id: 'message-ai-1',
    conversation_id: conversation.id,
    role: 'assistant',
    content: status === 'running' ? '正在生成修改建议……' : '建议正文',
    target_context: documentTarget,
    job_kind: 'document',
    job_id: 'job-1',
    proposal_ids: [],
    status
  }
}

async function mountPane(props: Record<string, unknown> = {}) {
  const wrapper = mount(WritingAiPane, {
    props: {
      projectId: 'project-1',
      target: documentTarget,
      ...props
    },
    global: { plugins: [ElementPlus] }
  })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.getConversations.mockResolvedValue([conversation])
  mocks.createConversation.mockResolvedValue(conversation)
  mocks.getMessages.mockResolvedValue([])
  mocks.createMessage.mockResolvedValue({
    response_message_id: 'message-ai-1',
    job: { id: 'job-1', status: 'queued' }
  })
  mocks.cancelMessage.mockResolvedValue({ ...assistantMessage(), status: 'cancelled' })
  mocks.acceptProposal.mockResolvedValue({ revision: 13 })
  mocks.rejectProposal.mockResolvedValue({ revision: 12 })
})

describe('WritingAiPane', () => {
  it('restores a project conversation without mounting hidden document or PPT editors', async () => {
    const wrapper = await mountPane()

    expect(wrapper.text()).toContain('协作写作')
    expect(wrapper.text()).toContain('博士论文正文')
    expect(wrapper.find('.co-writing').exists()).toBe(false)
    expect(wrapper.find('.presentation-workspace').exists()).toBe(false)
    expect(wrapper.emitted('conversation-changed')?.[0]).toEqual([conversation.id])

    wrapper.unmount()
  })

  it('locks an immutable target snapshot before submitting a message', async () => {
    const wrapper = await mountPane()
    ;(wrapper.vm as any).setTargetLocked(true)

    const changedTarget: WritingAiTarget = {
      ...documentTarget,
      block_id: 'block-2',
      block_revision: 8,
      revision: 14
    }
    await wrapper.setProps({ target: changedTarget })
    await wrapper.get('textarea[aria-label="AI 协作指令"]').setValue('检查这个段落的证据边界')
    await wrapper.get('.composer-actions .el-button--primary').trigger('click')
    await flushPromises()

    expect(wrapper.emitted('lock-changed')?.[0]).toEqual([true])
    expect(mocks.createMessage).toHaveBeenCalledTimes(1)
    const payload = mocks.createMessage.mock.calls[0][2]
    expect(payload.content).toBe('检查这个段落的证据边界')
    expect(payload.target.block_id).toBe('block-1')
    expect(payload.target.block_revision).toBe(3)

    wrapper.unmount()
  })

  it('shows a running task and cancels it through the conversation endpoint', async () => {
    mocks.getMessages.mockResolvedValue([
      {
        id: 'message-user-1',
        conversation_id: conversation.id,
        role: 'user',
        content: '润色当前段落',
        target_context: documentTarget,
        proposal_ids: [],
        status: 'completed'
      },
      assistantMessage()
    ])
    const wrapper = await mountPane()

    expect(wrapper.text()).toContain('生成中')
    await wrapper.get('.role-assistant footer button').trigger('click')
    await flushPromises()

    expect(mocks.cancelMessage).toHaveBeenCalledWith(
      'project-1',
      conversation.id,
      'message-ai-1'
    )

    wrapper.unmount()
  })

  it('notifies the linked document pane after accepting an AI proposal', async () => {
    mocks.getMessages.mockResolvedValue([
      {
        ...assistantMessage('review_required'),
        proposal_ids: ['proposal-1']
      }
    ])
    const wrapper = await mountPane()

    await wrapper.get('.role-assistant footer .el-button--primary').trigger('click')
    await flushPromises()

    expect(mocks.acceptProposal).toHaveBeenCalledWith('project-1', 'document-1', 'proposal-1')
    expect(wrapper.emitted('document-changed')?.[0]).toEqual(['document-1'])

    wrapper.unmount()
  })
})
