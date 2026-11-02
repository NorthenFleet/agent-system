import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  knowledgeStatus: vi.fn(), knowledgeSpaces: vi.fn(), knowledgeProjects: vi.fn(), createKnowledgeSpace: vi.fn(),
  uploadKnowledge: vi.fn(), enqueueKnowledge: vi.fn(), knowledgeItems: vi.fn(),
  knowledgeChange: vi.fn(), reviewKnowledge: vi.fn(), publishKnowledge: vi.fn(),
  queryKnowledge: vi.fn(), knowledgePage: vi.fn(), knowledgeSource: vi.fn(), retryKnowledgeJob: vi.fn(), cancelKnowledgeJob: vi.fn()
}))
vi.mock('@/api/knowledgeV3', async original => ({
  ...(await original<typeof import('@/api/knowledgeV3')>()), ...mocks
}))
import KnowledgeIntakePanel from '@/components/knowledge/KnowledgeIntakePanel.vue'

let wrapper: VueWrapper
const candidate = {
  id: 'candidate-1', status: 'awaiting_review', payload_hash: 'a'.repeat(64), before: [],
  payload: { extraction_mode: 'extractive-v1', links: [], pages: [{ page_id: 'p', base_revision: 0, title: '任务验收', blocks: [{ block_id: 'b', text: '<script>bad()</script>', span_ids: ['s'] }] }] },
  sources: [{ version_id: 'v', title: '原始资料', spans: [{ id: 's', text: '必须核对原始证据', locator: { line_start: 1, line_end: 1 } }] }]
}
async function button(text: string) {
  const target = wrapper.findAll('button').find(b => b.text() === text)
  expect(target, text).toBeTruthy()
  await target!.trigger('click'); await flushPromises()
}
async function mountPanel() { wrapper = mount(KnowledgeIntakePanel); await flushPromises() }

describe('knowledge intake', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    mocks.knowledgeStatus.mockResolvedValue({ enabled: true, write_enabled: true, worker_enabled: true })
    mocks.knowledgeSpaces.mockResolvedValue([{ id: 'space', name: '研究', project_id: '' }])
    mocks.knowledgeProjects.mockResolvedValue([])
    mocks.knowledgeItems.mockResolvedValue({ items: [], total: 0 })
  })
  afterEach(() => wrapper?.unmount())

  it('does not call gated APIs while disabled', async () => {
    mocks.knowledgeStatus.mockResolvedValue({ enabled: false })
    await mountPanel()
    expect(wrapper.text()).toContain('第二大脑尚未启用')
    expect(mocks.knowledgeSpaces).not.toHaveBeenCalled()
    expect(mocks.knowledgeItems).not.toHaveBeenCalled()
  })

  it('reviews the visible hash and publishes in separate steps', async () => {
    mocks.knowledgeItems.mockResolvedValue({ items: [{ id: 'job', change_set_id: candidate.id, stage: 'awaiting_review' }], total: 1 })
    mocks.knowledgeChange.mockResolvedValue(candidate)
    await mountPanel(); await button('查看候选')
    expect(wrapper.text()).toContain('必须核对原始证据')
    expect(wrapper.find('script').exists()).toBe(false)
    expect(wrapper.text()).toContain('<script>bad()</script>')
    expect(wrapper.findAll('button').find(b => b.text() === '批准当前修改集')?.attributes('disabled')).toBeDefined()
    await wrapper.find('.review input').setValue('已逐段核对')
    mocks.knowledgeChange.mockResolvedValue({ ...candidate, status: 'approved' })
    await button('批准当前修改集')
    expect(mocks.reviewKnowledge).toHaveBeenCalledWith(candidate, 'approve', '已逐段核对', expect.any(String))
    expect(mocks.publishKnowledge).not.toHaveBeenCalled()
    mocks.publishKnowledge.mockResolvedValue({ release_id: 'release', projection_status: 'pending' })
    mocks.knowledgeChange.mockResolvedValue({ ...candidate, status: 'applied' })
    await button('发布已批准修订')
    expect(wrapper.text()).toContain('Markdown/图谱投影尚未启用')
  })

  it('invalidates a stale approval preview instead of retrying new content', async () => {
    mocks.knowledgeItems.mockResolvedValue({ items: [{ id: 'job', change_set_id: candidate.id }], total: 1 })
    mocks.knowledgeChange.mockResolvedValue(candidate)
    await mountPanel(); await button('查看候选')
    await wrapper.find('.review input').setValue('核对')
    mocks.reviewKnowledge.mockRejectedValue({ response: { data: { detail: { message: '页面已变化，请重新生成修改集' } } } })
    await button('批准当前修改集')
    expect(wrapper.get('[role="alert"]').text()).toContain('页面已变化')
    expect(wrapper.find('[aria-label="候选审阅"]').exists()).toBe(false)
    expect(mocks.publishKnowledge).not.toHaveBeenCalled()
  })

  it('shows abstention without fabricated citations', async () => {
    mocks.queryKnowledge.mockResolvedValue({ answer_mode: 'extractive', answer: '知识库没有找到足够依据。', citations: [], gaps: ['火星'] })
    await mountPanel(); await button('引用查询')
    await wrapper.find('input[placeholder="输入概念或问题"]').setValue('火星大气温度')
    await wrapper.find('input[placeholder="输入概念或问题"]').element.closest('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await flushPromises()
    expect(wrapper.text()).toContain('知识库没有找到足够依据')
  })

  it('uses a new upload request key after selecting a different file', async () => {
    mocks.uploadKnowledge.mockResolvedValue({ version_id: 'v' })
    mocks.enqueueKnowledge.mockResolvedValue({ id: 'job' })
    await mountPanel()
    const input = wrapper.get('input[type="file"]')
    Object.defineProperty(input.element, 'files', { configurable: true, value: [new File(['first'], 'a.md')] })
    await input.trigger('change'); await input.element.closest('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); await flushPromises()
    const first = mocks.uploadKnowledge.mock.calls[0]![2]
    Object.defineProperty(input.element, 'files', { configurable: true, value: [new File(['second'], 'b.md')] })
    await input.trigger('change'); await input.element.closest('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); await flushPromises()
    expect(mocks.uploadKnowledge.mock.calls[1]![2]).not.toBe(first)
  })

  it('lets a failed import create an explicit retry without republishing anything', async () => {
    mocks.knowledgeItems.mockResolvedValue({ items: [{ id: 'failed-job', stage: 'failed', error_code: 'parse_timeout' }], total: 1 })
    mocks.retryKnowledgeJob.mockResolvedValue({ id: 'new-job', stage: 'queued' })
    await mountPanel(); await button('重新入库')
    expect(mocks.retryKnowledgeJob).toHaveBeenCalledWith('failed-job', expect.any(String))
    expect(mocks.publishKnowledge).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('已创建重试任务')
  })
  it('shows the fixed relation target and both source sides before review', async () => {
    mocks.knowledgeItems.mockResolvedValue({ items: [{ id: 'job', change_set_id: candidate.id }], total: 1 })
    mocks.knowledgeChange.mockResolvedValue({ ...candidate,
      relation_targets: [{ page_id: 'opposing', revision: 2, body_json: { title: '相反观点', blocks: [{ block_id: 'x', text: '对方固定修订内容' }] } }],
      sources: [...candidate.sources, { version_id: 'other', title: '另一份原始资料', spans: [{ id: 'other-span', text: '原文持相反观点', locator: { page: 1 } }] }]
    })
    await mountPanel(); await button('查看候选')
    expect(wrapper.text()).toContain('相反观点 · 固定修订 2')
    expect(wrapper.text()).toContain('对方固定修订内容')
    expect(wrapper.text()).toContain('原文持相反观点')
  })

})
