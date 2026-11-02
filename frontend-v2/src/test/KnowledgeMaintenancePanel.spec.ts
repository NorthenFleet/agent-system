import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ knowledgeMaintenance: vi.fn(), knowledgeProjection: vi.fn(), knowledgeItems: vi.fn(), knowledgeHistory: vi.fn(), knowledgePage: vi.fn(), proposeKnowledgeMaintenance: vi.fn(), replayKnowledgeProjection: vi.fn(), uploadKnowledge: vi.fn(), appendKnowledgeSource: vi.fn() }))
vi.mock('@/api/knowledgeV3', async original => ({ ...(await original<typeof import('@/api/knowledgeV3')>()), ...mocks }))
import Panel from '@/components/knowledge/KnowledgeMaintenancePanel.vue'
let wrapper: VueWrapper
const page = { id: 'p1', title: '原概念', status: 'active', type: 'concept', revision: 3 }
async function start(writeEnabled = true) { wrapper = mount(Panel, { props: { spaceId: 'space', writeEnabled } }); await flushPromises() }
async function choose() { await wrapper.findAll('select')[0]!.setValue('p1'); await flushPromises() }
async function click(text: string) { const button = wrapper.findAll('button').find(b => b.text() === text); expect(button).toBeTruthy(); await button!.trigger('click'); await flushPromises() }
describe('knowledge maintenance', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    mocks.knowledgeMaintenance.mockResolvedValue({ pages_checked: 2, pending_changes: 1, issues: [], automatic_semantic_check: false })
    mocks.knowledgeProjection.mockResolvedValue({ status: 'disabled', issues: [], events: [] })
    mocks.knowledgeItems.mockResolvedValue({ items: [page, { ...page, id: 'p2', title: '目标概念', revision: 5 }], total: 2 })
    mocks.knowledgeHistory.mockResolvedValue({ items: [{ revision: 3, title: '原概念' }], status: 'active', superseded_by: '' })
    mocks.knowledgePage.mockResolvedValue({ title: page.title, revision: 3, body_json: { blocks: [{ block_id: 'b', text: '<script>bad()</script>', span_ids: ['fixed-span'], epistemic_status: 'reported' }] } })
    mocks.proposeKnowledgeMaintenance.mockResolvedValue({ id: 'candidate' })
  })
  afterEach(() => wrapper?.unmount())
  it('creates a rename candidate bound to the selected revision without publishing', async () => {
    await start(); await choose()
    await wrapper.get('input[maxlength="240"]').setValue('新概念')
    await wrapper.get('input[maxlength="1000"]').setValue('保留原名别名')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(mocks.proposeKnowledgeMaintenance).toHaveBeenCalledWith('space', expect.objectContaining({ action: 'rename', page_id: 'p1', base_revision: 3, title: '新概念' }), expect.any(String))
    expect(wrapper.emitted('candidate')).toEqual([['candidate']])
  })
  it('pins the other page revision when proposing a contradiction', async () => {
    await start(); await choose()
    await wrapper.findAll('select')[1]!.setValue('relate'); await flushPromises()
    await wrapper.findAll('select')[2]!.setValue('p2')
    await wrapper.findAll('select')[3]!.setValue('CONTRADICTS')
    await wrapper.get('input[maxlength="1000"]').setValue('两份材料观点相反')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(mocks.proposeKnowledgeMaintenance).toHaveBeenCalledWith('space', expect.objectContaining({ target_page_id: 'p2', target_revision: 5, relation: 'CONTRADICTS' }), expect.any(String))
  })
  it('requires explicit regeneration for drift and reports queued rather than synced', async () => {
    mocks.knowledgeProjection.mockResolvedValue({ status: 'drift', issues: ['file_hash:index.md'], events: [{ id: 'evt', status: 'blocked_drift', attempts: 1 }] })
    await start(); await click('保留差异并重新生成')
    expect(mocks.replayKnowledgeProjection).toHaveBeenCalledWith('space', 'evt', true, expect.any(String))
    expect(wrapper.text()).toContain('尚未完成同步')
  })
  it('keeps evidence identifiers when editing and displays history as plain text', async () => {
    await start(); await choose(); await click('原概念 · 3')
    expect(wrapper.find('script').exists()).toBe(false)
    expect(wrapper.text()).toContain('<script>bad()</script>')
    await wrapper.findAll('select')[1]!.setValue('edit')
    await wrapper.get('textarea').setValue('人工解释')
    await wrapper.get('input[maxlength="1000"]').setValue('已核对依据')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(mocks.proposeKnowledgeMaintenance.mock.calls[0]![1].blocks[0].span_ids).toEqual(['fixed-span'])
  })
  it('offers read-only health and history without write actions for viewers', async () => {
    await start(false); await choose()
    expect(wrapper.find('form').exists()).toBe(false)
    expect(mocks.proposeKnowledgeMaintenance).not.toHaveBeenCalled()
  })
  it('reports revision conflicts without opening an unreviewed candidate', async () => {
    mocks.proposeKnowledgeMaintenance.mockRejectedValue({ response: { data: { detail: { message: '知识页已变化，请重新读取' } } } })
    await start(); await choose()
    await wrapper.get('input[maxlength="1000"]').setValue('改名')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('知识页已变化')
    expect(wrapper.emitted('candidate')).toBeUndefined()
  })
})
