import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ previewKnowledgeContext: vi.fn(), captureKnowledgeContext: vi.fn(), readKnowledgeContext: vi.fn() }))
vi.mock('@/api/knowledgeV3', async original => ({ ...(await original<typeof import('@/api/knowledgeV3')>()), ...mocks }))
import Panel from '@/components/knowledge/KnowledgeContextPanel.vue'
let wrapper: VueWrapper
const snapshot = { id:'snap', mode:'shadow', injected:false, access_epoch:1, items:[{title:'受控知识', revision:2, epistemic_status:'inference', content:'<script>来源内容不能执行</script>',evidence:[{ref:'span',source_version_id:'v1',locator:{page:2}}]}],budget:{total_chars:12000,baseline_chars:0,knowledge_chars_limit:3000,knowledge_chars_used:1000}, gaps:[],conflict_count:1 }
async function start(overrides = {}) { wrapper=mount(Panel,{props:{spaceId:'space',projectId:'project-a',mode:'shadow',writeEnabled:true,...overrides}}); await flushPromises() }
async function click(text: string) { await wrapper.findAll('button').find(b=>b.text()===text)!.trigger('click'); await flushPromises() }
describe('knowledge context shadow',()=>{
  beforeEach(()=>{vi.resetAllMocks();mocks.previewKnowledgeContext.mockResolvedValue({...snapshot,id:''});mocks.captureKnowledgeContext.mockResolvedValue(snapshot)})
  afterEach(()=>wrapper?.unmount())
  it('keeps disabled and unscoped modes inert',async()=>{await start({mode:'disabled'});expect(wrapper.find('form').exists()).toBe(false);expect(mocks.previewKnowledgeContext).not.toHaveBeenCalled();await wrapper.setProps({mode:'shadow',projectId:''});expect(wrapper.text()).toContain('未绑定项目')})
  it('renders untrusted content as text and shows no-injection status',async()=>{await start();await wrapper.get('input[minlength="2"]').setValue('来源验证');await wrapper.get('form').trigger('submit');await flushPromises();expect(wrapper.find('script').exists()).toBe(false);expect(wrapper.text()).toContain('未注入执行');expect(wrapper.text()).toContain('推论');expect(wrapper.text()).toContain('25%');expect(wrapper.text()).toContain('存在 1 组已标记矛盾');expect(mocks.captureKnowledgeContext).not.toHaveBeenCalled()})
  it('clears stale snapshot content before reporting revoked access',async()=>{await start();await wrapper.get('input[minlength="2"]').setValue('来源验证');await click('保存对照快照');mocks.readKnowledgeContext.mockRejectedValue({response:{data:{detail:{message:'知识访问状态已变化，请重新生成'}}}});await click('重新校验快照与访问权限');expect(wrapper.find('[aria-label="候选知识背景"]').exists()).toBe(false);expect(wrapper.get('[role="alert"]').text()).toContain('访问状态已变化')})
  it('distinguishes budget exhaustion from absent evidence',async()=>{mocks.previewKnowledgeContext.mockResolvedValue({...snapshot,id:'',items:[],gaps:['budget_exhausted']});await start({writeEnabled:false});await wrapper.get('input[minlength="2"]').setValue('来源验证');await wrapper.get('form').trigger('submit');await flushPromises();expect(wrapper.text()).toContain('剩余预算不足');expect(wrapper.text()).not.toContain('保存对照快照')})
  it('reuses the request key after a lost capture response',async()=>{await start();await wrapper.get('input[minlength="2"]').setValue('来源验证');mocks.captureKnowledgeContext.mockRejectedValueOnce(new Error('network'));await click('保存对照快照');await click('保存对照快照');expect(mocks.captureKnowledgeContext.mock.calls[0]![2]).toBe(mocks.captureKnowledgeContext.mock.calls[1]![2])})
  it('uses a fresh key for an explicitly requested new snapshot after success',async()=>{await start();await wrapper.get('input[minlength="2"]').setValue('来源验证');await click('保存对照快照');await click('保存对照快照');expect(mocks.captureKnowledgeContext.mock.calls[0]![2]).not.toBe(mocks.captureKnowledgeContext.mock.calls[1]![2])})

})
