<template>
  <section class="operations" aria-label="成果回流与运行记录">
    <p v-if="error" role="alert">{{ error }}</p><p v-if="message" role="status">{{ message }}</p>
    <h3>成果回流</h3>
    <p>选定已登记的成果或文档修订，保留版本与来源。登记后可另行生成待审核候选。</p>
    <p v-if="!projectId">当前空间未绑定项目，无法导入项目成果或提出项目记忆。</p>
    <form v-if="writeEnabled && projectId" @submit.prevent="importReference">
      <label>成果类型 <select v-model="reference.kind"><option value="artifact">任务成果</option><option value="document">文档修订</option></select></label>
      <label>{{ reference.kind === 'artifact' ? '任务 ID' : '文档 ID' }} <input v-model="reference.container_id" required maxlength="160" /></label>
      <label>{{ reference.kind === 'artifact' ? '成果 ID' : '修订记录 ID' }} <input v-model="reference.object_id" required maxlength="160" /></label>
      <label>登记版本 <input v-model.number="reference.version" type="number" min="1" required /></label>
      <label>登记 SHA-256 <input v-model="reference.expected_hash" required pattern="[a-f0-9]{64}" maxlength="64" /></label>
      <label class="selection"><input v-model="reference.selected" type="checkbox" required />我选定此固定版本；草稿状态继续保留</label>
      <ElButton native-type="submit" type="primary" :disabled="busy || !reference.selected">登记固定成果</ElButton>
    </form>
    <ul><li v-for="entry in overview?.imports" :key="entry.id">{{ entry.reference.kind === 'artifact' ? '任务成果' : '文档修订' }} · {{ entry.reference.object_id }} · 版本 {{ entry.reference.version }} · {{ lifecycle(entry.reference.lifecycle) }}
      <ElButton v-if="writeEnabled" :disabled="busy" @click="enqueue(entry.source_version_id)">生成待审核候选</ElButton></li></ul>
    <h3>项目记忆提案</h3>
    <p>提案保存在知识域，可重新核对依据。正式记忆桥接尚未启用，不会自动发布或影响任务执行。</p>
    <form v-if="writeEnabled && projectId" @submit.prevent="propose">
      <label>知识页 <select v-model="pageId" required :disabled="busy" @change="loadPage"><option value="">请选择</option><option v-for="p in pages" :key="p.id" :value="p.id">{{ p.title }}</option></select></label>
      <label>引用段落 <select v-model="blockId" required><option v-for="block in blocks" :key="block.block_id" :value="block.block_id">{{ block.text.slice(0, 90) }}</option></select></label>
      <label>记忆键 <input v-model="memoryKey" required maxlength="200" /></label>
      <label>建议内容 <textarea v-model="content" required maxlength="12000" /></label>
      <label>提案理由 <input v-model="reason" required maxlength="2000" /></label>
      <ElButton native-type="submit" :disabled="busy || !blockId">保存记忆提案</ElButton>
    </form>
    <ul><li v-for="item in overview?.proposals" :key="item.id">{{ item.id }} · {{ item.status === 'export_only' ? '待跨域处理' : '依据已失效，需复核' }} <ElButton :disabled="busy || item.status !== 'export_only'" @click="readProposal(item.id)">重新核对提案</ElButton></li></ul>
    <article v-if="proposal" aria-label="记忆提案详情"><p>已核对 {{ proposal.knowledge_revision_ref }} · 尚未批准为正式记忆</p><pre>{{ proposal.proposed_content }}</pre><p>来源：{{ proposal.evidence_refs.join('、') }}</p></article>
    <h3>周期维护记录</h3>
    <p>同一 UTC 日、周或月复用一次检查记录；没有变化时不重复提示。此处操作不会创建系统定时任务。</p>
    <div v-if="writeEnabled" class="toolbar"><select v-model="cadence" aria-label="维护周期"><option value="daily">每日</option><option value="weekly">每周</option><option value="monthly">每月</option></select><ElButton :disabled="busy" @click="maintain">执行本期检查</ElButton></div>
    <ul><li v-for="run in receipts" :key="run.id">{{ run.period_key }} · {{ run.report.attention_required ? '发现需要处理的变化' : '无新增处理事项' }} · 待审核 {{ run.report.structural.pending_changes }} · 失败任务 {{ run.report.failed_jobs.length }} · 失效记忆提案 {{ run.report.memory_needs_review.length }}</li></ul>
  </section>
</template>
<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import { ElButton } from 'element-plus'
import * as api from '@/api/knowledgeV3'
const props = defineProps<{ spaceId: string; projectId: string; writeEnabled: boolean }>()
const overview = ref<api.BridgeOverview>(), receipts = ref<api.MaintenanceReceipt[]>([]), pages = ref<api.Item[]>([])
const blocks = ref<api.KnowledgeBlock[]>([]), proposal = ref<api.MemoryProposalResult>()
const reference = reactive<api.ExternalReference>({kind:'artifact', container_id:'', object_id:'', version:1, expected_hash:'', selected:false})
const pageId = ref(''), blockId = ref(''), revision = ref(0), memoryKey = ref(''), content = ref(''), reason = ref(''), cadence = ref('weekly')
const busy = ref(false), error = ref(''), message = ref('')
let alive = true
const keys = new Map<string,string>()
function key(kind: string, body: unknown) { const id = kind + JSON.stringify(body); if (!keys.has(id)) keys.set(id,api.newRequestKey()); return keys.get(id)! }
function lifecycle(value: string) { return ({working:'草稿',draft:'草稿',approved:'已审核',published:'已发布',user_selected_unverified:'用户选定，验收未核实'} as Record<string,string>)[value] || value }
async function refresh() { const [bridges, runs, result] = await Promise.all([api.knowledgeBridges(props.spaceId),api.knowledgeMaintenanceRuns(props.spaceId),api.knowledgeItems(props.spaceId,'pages')]); if (alive) {overview.value=bridges; receipts.value=runs; pages.value=result.items.filter(p=>p.status==='active')} }
async function act(work: () => Promise<void>) { if (busy.value) return; busy.value=true;error.value='';message.value=''; try {await work()} catch(e) {if(alive) error.value=api.knowledgeError(e)} finally {if(alive)busy.value=false} }
async function importReference() { await act(async()=>{await api.importKnowledgeReference(props.spaceId,{...reference},key('import',reference));if(alive)message.value='固定成果已登记；尚未提取或发布。';await refresh()}) }
async function enqueue(id: string) {await act(async()=>{await api.enqueueKnowledge(props.spaceId,id,'',key('enqueue',id));if(alive)message.value='已加入队列，请在待审核中核对来源。'})}
async function loadPage() {blocks.value=[];blockId.value='';revision.value=0;proposal.value=undefined;if(!pageId.value)return;await act(async()=>{const page=await api.knowledgePage(pageId.value);if(alive){blocks.value=page.body_json.blocks;revision.value=page.revision;blockId.value=blocks.value[0]?.block_id||''}})}
async function propose() {await act(async()=>{proposal.value=undefined;const body={page_id:pageId.value,revision:revision.value,block_id:blockId.value,memory_key:memoryKey.value,proposed_content:content.value,reason:reason.value};const result=await api.proposeKnowledgeMemory(props.spaceId,body,key('memory',body));if(alive)proposal.value=result;await refresh()})}
async function readProposal(id: string) {await act(async()=>{proposal.value=undefined;const result=await api.readKnowledgeMemoryProposal(id);if(alive)proposal.value=result})}
async function maintain() {await act(async()=>{await api.maintainKnowledge(props.spaceId,cadence.value);await refresh()})}
onMounted(()=>void act(refresh));onUnmounted(()=>{alive=false})
</script>
<style scoped>
.operations{min-width:0}.operations h3{margin-top:24px}.operations form{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(260px,100%),1fr));gap:12px}.operations label{display:flex;flex-direction:column;gap:4px}.operations input,.operations select,.operations textarea{box-sizing:border-box;max-width:100%;min-width:0;border:1px solid #c4ccd8;border-radius:5px;padding:8px;font:inherit}.operations textarea{min-height:80px}.operations .selection{flex-direction:row;align-items:center}.operations li{margin:10px 0;overflow-wrap:anywhere}.operations pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f7fb;padding:12px}.operations [role=alert]{color:#b42318}.toolbar{display:flex;gap:8px;flex-wrap:wrap}
</style>
