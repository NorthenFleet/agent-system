<template>
  <section aria-label="知识维护" class="maintenance">
    <p v-if="error" role="alert">{{ error }}</p><p v-if="message" role="status">{{ message }}</p>
    <button :disabled="busy" @click="load">运行维护检查</button>
    <p v-if="report">检查 {{ report.pages_checked }} 页 · 待处理修改 {{ report.pending_changes }} 批。矛盾由人工标记，检查不会自动裁决。</p>
    <ul><li v-for="(issue, i) in report?.issues" :key="i">{{ issueLabel(issue.kind) }} · {{ issue.message }}</li></ul>
    <section v-if="projection" aria-label="投影健康">
      <h3>Markdown / 图谱投影</h3>
      <p>{{ projectionLabel(projection.status) }}<template v-if="projection.pointer"> · 发布 {{ projection.pointer.sequence }} / 访问版本 {{ projection.pointer.access_epoch }}</template></p>
      <p v-if="projection.status === 'drift'">检测到外部修改。重新生成会保留旧目录和差异，再切换至新版本。</p>
      <ul><li v-for="issue in projection.issues" :key="issue">{{ issue.startsWith('file_hash:') ? '文件变化：' + issue.slice(10) : '投影清单需要核对' }}</li></ul>
      <ul class="events"><li v-for="event in projection.events" :key="event.id">
        {{ event.event_type === 'knowledge.published' ? '知识发布' : '来源撤回' }} · {{ eventLabel(event.status) }} · 尝试 {{ event.attempts }} 次 <span v-if="event.error_code && event.error_code !== 'projection_drift'">处理失败，可查看日志或重放</span>
        <button v-if="writeEnabled && ['retry', 'dead', 'blocked_drift', 'completed'].includes(event.status)" :disabled="busy" @click="replay(event.id, event.status === 'blocked_drift' || projection.status === 'drift')">{{ event.status === 'blocked_drift' || projection.status === 'drift' ? '保留差异并重新生成' : '重放此事件' }}</button>
      </li></ul>
    </section>
    <h3>知识维护候选</h3>
    <p>选定已发布页。改名、编辑、关系与合并仅生成候选，仍需核对并单独发布；合并保留旧修订和来源。</p>
    <div class="toolbar"><button :disabled="busy || offset === 0" @click="listPages(-50)">上一批知识页</button><span>{{ offset + 1 }}–{{ offset + pages.length }} / {{ total }}</span><button :disabled="busy || offset + pages.length >= total" @click="listPages(50)">下一批知识页</button></div>
    <label>知识页 <select v-model="pageId" :disabled="busy" @change="selectPage"><option value="">请选择</option><option v-for="page in pageChoices" :key="page.id" :value="page.id">{{ page.title }} · {{ page.status === 'active' ? '有效' : '已合并' }} · 修订 {{ page.revision }}</option></select></label>
    <div v-if="history" class="toolbar"><span>历史修订：</span><button v-for="revision in history.items" :key="revision.revision" :disabled="busy" @click="viewHistory(revision.revision)">{{ revision.title }} · {{ revision.revision }}</button><span v-if="history.superseded_by">已合并，历史保留</span></div>
    <pre v-if="historicalText">{{ historicalText }}</pre>
    <form v-if="writeEnabled && selected?.status === 'active'" @submit.prevent="propose">
      <div class="toolbar"><label>操作 <select v-model="action" :disabled="busy"><option value="rename">改名</option><option value="edit">编辑有来源的段落</option><option value="relate">添加关系 / 标记矛盾</option><option value="merge">合并至另一页</option></select></label>
        <label v-if="action === 'rename'">新标题 <input v-model="title" maxlength="240" required /></label>
      </div>
      <template v-if="action === 'merge' || action === 'relate'">
        <label>目标页 <select v-model="targetId" required><option value="">请选择另一页</option><option v-for="target in targets" :key="target.id" :value="target.id">{{ target.title }} · 修订 {{ target.revision }}</option></select></label>
        <p>目标列表为当前批次；翻页会加载更多目标，已选知识页保持不变。首版每批展示 50 页。</p>
        <label v-if="action === 'relate'">关系 <select v-model="relation"><option value="RELATED_TO">相关</option><option value="SUPPORTS">支持</option><option value="CONTRADICTS">矛盾（保留双方依据）</option><option value="DERIVED_FROM">推导自</option></select></label>
      </template>
      <div v-if="action === 'edit'"><article v-for="block in blocks" :key="block.block_id"><textarea v-model="block.text" required maxlength="12000" :aria-label="'段落 ' + block.block_id" /><label>判断类型 <select v-model="block.epistemic_status"><option value="reported">来源陈述</option><option value="inference">推论</option><option value="uncertain">待核实</option></select></label><small>保留 {{ block.span_ids.length }} 条原始引用</small></article></div>
      <label>维护理由 <input v-model="reason" required maxlength="1000" /></label><button :disabled="busy || !reason.trim() || (['merge', 'relate'].includes(action) && !targetId)">生成待审核修改集</button>
    </form>
    <form v-if="writeEnabled && selected?.status === 'active' && selected.type === 'concept'" @submit.prevent="append">
      <h3>向此概念追加资料</h3><p>固定目标修订 {{ selected.revision }}，生成多来源候选；冲突时重新读取后再提交。</p>
      <input type="file" accept=".md,.txt,.pdf" :disabled="busy" aria-label="追加来源" @change="selectFile" /><button :disabled="busy || !file">上传并生成追加候选</button>
    </form>
  </section>
</template>
<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import * as api from '@/api/knowledgeV3'
const props = defineProps<{ spaceId: string; writeEnabled: boolean }>()
const emit = defineEmits<{ candidate: [id: string] }>()
const report = ref<api.MaintenanceReport>(), projection = ref<api.ProjectionHealth>()
const pages = ref<api.Item[]>([]), total = ref(0), offset = ref(0), pageId = ref(''), targetId = ref('')
const selected = ref<api.Item>(), targetCache = ref<api.Item[]>([])
const pageChoices = computed(() => Array.from(new Map([...(selected.value ? [selected.value] : []), ...pages.value].map(p => [p.id, p])).values()))
const targets = computed(() => targetCache.value.filter(p => p.id !== pageId.value && p.status === 'active'))
const history = ref<Awaited<ReturnType<typeof api.knowledgeHistory>>>(), historicalText = ref('')
const action = ref<api.MaintenanceRequest['action']>('rename'), title = ref(''), relation = ref('RELATED_TO'), reason = ref('')
const blocks = ref<api.KnowledgeBlock[]>([]), error = ref(''), message = ref(''), busy = ref(false), file = ref<File>()
let alive = true
const keys = new Map<string, string>(); let fileToken = api.newRequestKey()
function key(payload: unknown) { const value = JSON.stringify(payload); if (!keys.has(value)) keys.set(value, api.newRequestKey()); return keys.get(value)! }
function eventLabel(state: string) { return ({ pending: '待处理', processing: '处理中', retry: '等待重试', dead: '重试已用尽', blocked_drift: '外部差异待处理', completed: '已同步', superseded: '已有更新版本' } as Record<string, string>)[state] || '待检查' }
function issueLabel(kind: string) { return ({ contradiction: '矛盾待核对', stale_link: '关联引用旧修订', unavailable_link: '关联不可用', source_retracted: '依据已撤回' } as Record<string, string>)[kind] || '需要复核' }
function projectionLabel(state: string) { return ({ disabled: '投影尚未启用', missing: '尚未生成投影', ready: '投影校验通过', lagging: '投影落后，等待处理', drift: '投影存在外部差异' } as Record<string, string>)[state] || state }
async function act(work: () => Promise<void>) { if (busy.value) return; busy.value = true; error.value = ''; message.value = ''; try { await work() } catch (e) { error.value = api.knowledgeError(e) } finally { busy.value = false } }
async function checks() { const [r, p] = await Promise.all([api.knowledgeMaintenance(props.spaceId), api.knowledgeProjection(props.spaceId)]); report.value = r; projection.value = p }
async function fetchPages() { const result = await api.knowledgeItems(props.spaceId, 'pages', offset.value); pages.value = result.items; total.value = result.total; targetCache.value = Array.from(new Map([...targetCache.value, ...result.items].map(p => [p.id, p])).values()) }
async function load() { await act(async () => { await checks(); await fetchPages() }) }
async function listPages(delta: number) { await act(async () => { offset.value += delta; await fetchPages() }) }
async function selectPage() { await act(async () => { selected.value = undefined; history.value = undefined; blocks.value = []; historicalText.value = ''; targetId.value = ''; if (!pageId.value) return; const choice = pages.value.find(p => p.id === pageId.value); history.value = await api.knowledgeHistory(pageId.value); if (choice?.status === 'active') { const page = await api.knowledgePage(pageId.value); blocks.value = structuredClone(page.body_json.blocks); title.value = page.title; selected.value = { ...choice, revision: page.revision, title: page.title } } }) }
async function viewHistory(revision: number) { await act(async () => { historicalText.value = ''; const page = await api.knowledgePage(pageId.value, revision); historicalText.value = page.body_json.blocks.map(b => b.text).join('\n\n') }) }
async function propose() { await act(async () => { if (!selected.value?.revision) return; const target = targetCache.value.find(p => p.id === targetId.value); const body: api.MaintenanceRequest = { action: action.value, page_id: selected.value.id, base_revision: selected.value.revision, reason: reason.value }; if (action.value === 'rename') body.title = title.value; if (action.value === 'edit') body.blocks = blocks.value; if (action.value === 'merge' || action.value === 'relate') { body.target_page_id = target?.id; body.target_revision = target?.revision; body.relation = relation.value } const result = await api.proposeKnowledgeMaintenance(props.spaceId, body, key(body)); if (alive) emit('candidate', result.id); message.value = '已生成候选，请核对原文和修改。'; await checks() }) }
async function replay(eventId: string, regenerate: boolean) { await act(async () => { await api.replayKnowledgeProjection(props.spaceId, eventId, regenerate, key(['replay', eventId, regenerate])); keys.delete(JSON.stringify(['replay', eventId, regenerate])); message.value = '已加入投影队列；尚未完成同步。'; await checks() }) }
function selectFile(event: Event) { file.value = (event.target as HTMLInputElement).files?.[0]; fileToken = api.newRequestKey() }
async function append() { await act(async () => { if (!file.value || !selected.value) return; const source = await api.uploadKnowledge(props.spaceId, file.value, key(['upload', fileToken])); await api.appendKnowledgeSource(props.spaceId, source.version_id, selected.value, key(['append', fileToken, selected.value.id, selected.value.revision])); message.value = '追加任务已入队，候选生成后在待审核中处理。' }) }
onMounted(load)
onUnmounted(() => { alive = false })
</script>
<style scoped>
.maintenance { padding: 12px 0; } .toolbar { display: flex; gap: 10px; flex-wrap: wrap; margin: 12px 0; align-items: center; }
label { display: inline-flex; gap: 8px; flex-wrap: wrap; align-items: center; margin: 8px; } button, input, select, textarea { font: inherit; color: var(--el-text-color-primary); background: var(--el-bg-color); border: 1px solid var(--el-border-color); border-radius: 6px; padding: 8px; max-width: 100%; }
button { cursor: pointer; } button:disabled { opacity: .5; } textarea { display: block; width: 95%; min-height: 90px; } pre { white-space: pre-wrap; overflow-wrap: anywhere; } [role="alert"] { color: var(--el-color-danger); } .events li { margin: 10px 0; overflow-wrap: anywhere; } form { border-top: 1px solid var(--el-border-color); padding-top: 14px; margin-top: 14px; }
</style>
