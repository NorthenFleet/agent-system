// Isolated UI fixture: no backend, auth token, production data or writes.
// Run: node scripts/preview-knowledge-maintenance.mjs
import { createServer } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath } from 'node:url'
const root = fileURLToPath(new URL('..', import.meta.url))
const contextPreview = process.argv.includes('--context')
const operationsPreview = process.argv.includes('--operations')
const fixture = `
const page = { id: 'p1', title: '研究证据验收', type: 'concept', status: 'active', revision: 3 };
const other = { ...page, id: 'p2', title: '资料可信度', revision: 2 };
export const newRequestKey = () => crypto.randomUUID();
export const knowledgeError = (error) => error?.response?.data?.detail?.message || '隔离样例操作失败';
export const knowledgeItems = async () => ({ items: [page, other], total: 2 });
export const knowledgeMaintenance = async () => ({ pages_checked: 12, pending_changes: 2, issues: [{kind:'contradiction', page_id:'p1', message:'两份来源对验证范围存在不同判断，需核对原文。'}] });
export const knowledgeProjection = async () => ({ status: 'drift', issues: ['file_hash:index.md'], pointer: {sequence: 7, access_epoch: 1}, events: [{id:'event', event_type:'knowledge.published', status:'blocked_drift', attempts:1, error_code:'projection_drift'}] });
export const knowledgeHistory = async () => ({ items: [{revision: 3, title:'研究证据验收'}, {revision:2,title:'任务验收'}], status:'active', superseded_by:'' });
export const knowledgePage = async () => ({ title: page.title, revision: 3, body_json: { blocks: [{block_id:'b1', text:'每项结论保留原始来源和定位。发生冲突时，列出双方证据，交由用户审核。', span_ids:['span'], epistemic_status:'reported'}] } });
export const proposeKnowledgeMaintenance = async () => ({ id: 'fixture-candidate' });
export const replayKnowledgeProjection = async () => ({ status:'pending' });
export const uploadKnowledge = async () => ({ version_id:'fixture-source' });
export const appendKnowledgeSource = async () => ({ stage:'queued' });
const snapshot = {id:'fixture-snapshot', mode:'shadow', injected:false, access_epoch:1, conflict_count:1, candidate_count:2, gaps:[], knowledge_refs:[], budget:{total_chars:12000, baseline_chars:5000, knowledge_chars_limit:3000, knowledge_chars_used:1420},items:[{title:'研究证据核验',revision:3,epistemic_status:'inference',content:'每项结论保留原始来源与定位；发生冲突时列出双方证据，交由用户核对。',evidence:[{ref:'span',source_version_id:'fixture-source',locator:{page:2}}]}]};
export const previewKnowledgeContext = async () => ({...snapshot,id:''});
export const captureKnowledgeContext = async () => snapshot;
export const readKnowledgeContext = async () => { throw {response:{data:{detail:{message:'隔离演练：依据已撤回，旧快照不可使用。'}}}} };

`
const operationsFixture = `
const external = {id:'import-1',source_version_id:'source-1',reference:{kind:'document',object_id:'研究报告修订',version:3,lifecycle:'working'}};
export const knowledgeBridges = async () => ({memory_mode:'export_only',automatic_memory_bridge:false,imports:[external],proposals:[{id:'proposal-1',status:'export_only',reason:''}]});
export const knowledgeMaintenanceRuns = async () => [{id:'run-1',period_key:'weekly:2026-W41',work_run_id:'',report:{attention_required:true,changed:true,notification_sent:false,structural:{pending_changes:2},failed_jobs:[],dead_letters:[],memory_needs_review:['proposal-old']}}];
export const importKnowledgeReference = async () => ({version_id:'source-1',duplicate:false,auto_extract:false});
export const enqueueKnowledge = async () => ({stage:'queued'});
export const proposeKnowledgeMemory = async () => ({id:'proposal-1',mode:'export_only',approved:false,knowledge_revision_ref:'kb-page:研究证据@3',proposed_content:'项目研究结论应保留固定来源及定位。',evidence_refs:['kb-span:证据段落']});
let readCount=0;
export const readKnowledgeMemoryProposal = async () => { if (readCount++) throw {response:{data:{detail:{message:'隔离演练：来源已撤回，旧提案不再可读取。'}}}}; return proposeKnowledgeMemory(); };
export const maintainKnowledge = async () => ({});
`;
const main = `
import { createApp, h } from 'vue';
import Panel from '/@fs/${root}/src/components/knowledge/${operationsPreview ? 'KnowledgeOperationsPanel' : contextPreview ? 'KnowledgeContextPanel' : 'KnowledgeMaintenancePanel'}.vue';
import 'element-plus/dist/index.css';
createApp({ render: () => h(Panel, {spaceId:'fixture', projectId:'fixture-project', mode:'shadow', writeEnabled:true, onCandidate: () => { document.getElementById('result').textContent='隔离候选已生成；正式知识库未写入。' }}) }).mount('#app');
`
const server = await createServer({ configFile: false, root, optimizeDeps: { noDiscovery: true, include: ['vue', 'element-plus'] }, plugins: [vue(), {
  name: 'knowledge-isolated-fixture',
  resolveId(id) { if (id === '@/api/knowledgeV3') return '\0knowledge-fixture'; if (id === '/__knowledge_preview.js') return '\0knowledge-main' },
  load(id) { if (id === '\0knowledge-fixture') return fixture + (operationsPreview ? operationsFixture : ''); if (id === '\0knowledge-main') return main },
  configureServer(server) { server.middlewares.use((req, res, next) => { if (req.url !== '/') return next(); res.setHeader('Content-Type', 'text/html; charset=utf-8'); const html = '<!doctype html><html lang="zh-CN"><meta name="viewport" content="width=device-width, initial-scale=1"><title>知识维护 · 隔离预览</title><style>body{margin:0;padding:24px;font:15px/1.7 system-ui;color:#26364a;background:#f6f8fc}main{max-width:1080px;margin:auto;background:white;padding:24px;border:1px solid #e0e5ec;border-radius:14px}h1{font-size:26px;margin:0}#result{color:#24775b}@media(max-width:600px){body{padding:8px}main{padding:12px}}</style><main><h1>知识维护</h1><p>隔离预览 · 合成数据，不写正式知识库</p><p id="result" role="status"></p><div id="app"></div></main><script type="module" src="/__knowledge_preview.js"></script></html>'; res.end(operationsPreview ? html.replaceAll('知识维护', '成果回流与运行') : contextPreview ? html.replaceAll('知识维护', '知识上下文对照') : html) }) }
}], server: { host: '127.0.0.1', port: 55142, strictPort: true } })
await server.listen()
console.log('Isolated knowledge preview: http://127.0.0.1:55142')
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, async () => { await server.close(); process.exit(0) })
