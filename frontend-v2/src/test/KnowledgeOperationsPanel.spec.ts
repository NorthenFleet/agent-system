import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
const mocks=vi.hoisted(()=>({knowledgeBridges:vi.fn(),knowledgeMaintenanceRuns:vi.fn(),knowledgeItems:vi.fn(),knowledgePage:vi.fn(),importKnowledgeReference:vi.fn(),proposeKnowledgeMemory:vi.fn(),readKnowledgeMemoryProposal:vi.fn(),maintainKnowledge:vi.fn(),enqueueKnowledge:vi.fn()}))
vi.mock('@/api/knowledgeV3',async original=>({...await original<typeof import('@/api/knowledgeV3')>(),...mocks}))
import Panel from '@/components/knowledge/KnowledgeOperationsPanel.vue'
let wrapper: VueWrapper
const proposal={id:'proposal',mode:'export_only',approved:false,proposed_content:'<script>不能执行</script>',knowledge_revision_ref:'kb-page:p@1',evidence_refs:['span-1']}
async function start(props={}) {wrapper=mount(Panel,{props:{spaceId:'space',projectId:'project-a',writeEnabled:true,...props}});await flushPromises()}
async function click(text: string) {await wrapper.findAll('button').find(b=>b.text()===text)!.trigger('click');await flushPromises()}
describe('knowledge operations',()=>{
  beforeEach(()=>{vi.resetAllMocks();mocks.knowledgeBridges.mockResolvedValue({imports:[],proposals:[{id:'proposal',status:'export_only'}]});mocks.knowledgeMaintenanceRuns.mockResolvedValue([]);mocks.knowledgeItems.mockResolvedValue({items:[]});mocks.importKnowledgeReference.mockResolvedValue({version_id:'v1'})})
  afterEach(()=>wrapper?.unmount())
  it('keeps readonly and unscoped users out of write forms',async()=>{await start({writeEnabled:false});expect(wrapper.findAll('form')).toHaveLength(0);expect(wrapper.text()).not.toContain('执行本期检查');await wrapper.setProps({writeEnabled:true,projectId:''});expect(wrapper.findAll('form')).toHaveLength(0);expect(wrapper.text()).toContain('未绑定项目')})
  it('registers only explicit fixed selection and does not enqueue automatically',async()=>{await start();expect(wrapper.findAll('button').find(b=>b.text()==='登记固定成果')!.attributes('disabled')).toBeDefined();await wrapper.get('input[type=checkbox]').setValue(true);await wrapper.findAll('form')[0]!.trigger('submit');await flushPromises();expect(mocks.importKnowledgeReference).toHaveBeenCalled();expect(mocks.enqueueKnowledge).not.toHaveBeenCalled();expect(wrapper.text()).toContain('尚未提取或发布')})
  it('reuses import key on a lost response',async()=>{await start();await wrapper.get('input[type=checkbox]').setValue(true);mocks.importKnowledgeReference.mockRejectedValueOnce(new Error('lost'));await wrapper.findAll('form')[0]!.trigger('submit');await flushPromises();await wrapper.findAll('form')[0]!.trigger('submit');await flushPromises();expect(mocks.importKnowledgeReference.mock.calls[0]![2]).toBe(mocks.importKnowledgeReference.mock.calls[1]![2])})
  it('escapes proposal text and clears it when revalidation fails',async()=>{await start();mocks.readKnowledgeMemoryProposal.mockResolvedValueOnce(proposal);await click('重新核对提案');expect(wrapper.find('script').exists()).toBe(false);expect(wrapper.text()).toContain('<script>不能执行</script>');mocks.readKnowledgeMemoryProposal.mockRejectedValueOnce({response:{data:{detail:{message:'来源已撤回'}}}});await click('重新核对提案');expect(wrapper.find('[aria-label="记忆提案详情"]').exists()).toBe(false);expect(wrapper.get('[role=alert]').text()).toContain('撤回')})
  it('runs a period check without creating a scheduler',async()=>{await start();await click('执行本期检查');expect(mocks.maintainKnowledge).toHaveBeenCalledWith('space','weekly');expect(wrapper.text()).toContain('不会创建系统定时任务')})
})
