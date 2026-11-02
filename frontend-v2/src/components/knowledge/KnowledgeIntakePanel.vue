<template>
  <section class="intake" aria-label="知识入库与审核">
    <p v-if="error" role="alert" class="error">{{ error }}</p>
    <p v-if="message" role="status">{{ message }}</p>
    <p v-if="!status">正在读取知识服务状态…</p>
    <p v-else-if="!status.enabled">第二大脑尚未启用。现有知识浏览继续可用。</p>
    <template v-else>
      <header class="toolbar">
        <label>知识空间 <select v-model="spaceId" :disabled="busy" aria-label="知识空间" @change="switchSpace"><option value="">请选择</option><option v-for="space in spaces" :key="space.id" :value="space.id">{{ space.name }}</option></select></label>
        <button :disabled="busy" @click="refresh">刷新</button>
      </header>
      <details v-if="status.write_enabled">
        <summary>新建知识空间</summary>
        <form class="toolbar" @submit.prevent="createSpace">
          <label>名称 <input v-model="spaceName" required maxlength="240" /></label>
          <label>所属项目 <select v-model="projectId"><option value="">个人知识（不绑定项目）</option><option v-for="project in projects" :key="project.id" :value="project.id">{{ project.name }}</option></select></label>
          <button :disabled="busy || !spaceName.trim()">创建</button>
        </form>
      </details>
      <template v-if="spaceId">
        <nav class="toolbar" aria-label="知识操作">
          <button v-for="item in tabs" :key="item.id" :disabled="busy" :aria-pressed="tab === item.id" @click="selectTab(item.id)">{{ item.label }}</button>
        </nav>
        <section v-if="tab === 'jobs'">
          <p>上传后先生成待审核候选。首版保留原文摘录，概念标题由你指定，内容发布前需要审核。</p>
          <p v-if="!status.worker_enabled">自动处理未启用；队列需由已配置的入库调度任务处理。</p>
          <form v-if="status.write_enabled" class="toolbar" @submit.prevent="ingest">
            <label>资料 <input type="file" :disabled="busy" accept=".md,.txt,.pdf" @change="selectFile" /></label>
            <label>归入概念（可选） <input v-model="concept" maxlength="240" /></label>
            <button :disabled="busy || !file">上传并生成候选</button>
          </form>
        </section>
        <section v-if="tab === 'query'">
          <form class="toolbar" @submit.prevent="ask"><label>查询 <input v-model="question" required minlength="2" maxlength="2000" placeholder="输入概念或问题" /></label><button :disabled="busy || question.trim().length < 2">查找依据</button></form>
          <template v-if="answer">
            <p>结果为已审核知识页摘录；请打开原文核对依据，推论和待核实内容会单独标注。</p><pre>{{ answer.answer }}</pre>
            <aside v-for="(conflict, index) in answer.conflicts" :key="index"><strong>矛盾：{{ conflict.source_title }} / {{ conflict.target_title }}</strong><p>{{ conflict.rationale }}{{ conflict.stale ? '（关系引用旧修订，需重新核对）' : '' }}</p><button @click="openReference(conflict.source_ref)">查看一方依据</button><button @click="openReference(conflict.target_ref)">查看另一方依据</button></aside>
            <article v-for="citation in answer.citations" :key="citation.source_ref">
              <button @click="openPage(citation.page_id, citation.revision)">{{ citation.title }} · 修订 {{ citation.revision }}</button>
              <button v-for="ref in citation.citations" :key="ref.span_id" @click="openSource(ref.source_version_id)">原文 {{ locator(ref.locator) }}</button>
            </article>
          </template>
        </section>
        <KnowledgeOperationsPanel v-else-if="tab === 'operations'" :key="spaceId" :space-id="spaceId" :project-id="spaces.find(s => s.id === spaceId)?.project_id || ''" :write-enabled="status.write_enabled" />
        <KnowledgeContextPanel v-else-if="tab === 'context'" :key="spaceId" :space-id="spaceId" :project-id="spaces.find(s => s.id === spaceId)?.project_id || ''" :mode="status.context_mode || 'disabled'" :write-enabled="status.write_enabled" @source="openSource" />
        <KnowledgeMaintenancePanel v-else-if="tab === 'maintenance'" :key="spaceId" :space-id="spaceId" :write-enabled="status.write_enabled" @candidate="openChange" />
        <section v-else>
          <p v-if="!items.length">暂无记录</p>
          <ul class="records"><li v-for="item in items" :key="item.id">
            <span>{{ item.title || item.id }} · {{ stateLabel(item.stage || item.status || '') }}</span>
            <span v-if="item.error_code" class="error">{{ item.error_code }}</span>
            <button v-if="item.change_set_id" @click="openChange(item.change_set_id)">查看候选</button>
            <button v-if="tab === 'jobs' && status.write_enabled && ['failed', 'cancelled'].includes(item.stage || '')" :disabled="busy" @click="retryJob(item.id)">重新入库</button>
            <button v-if="tab === 'jobs' && status.write_enabled && ['queued', 'compiling', 'awaiting_review'].includes(item.stage || '')" :disabled="busy" @click="cancelJob(item.id)">取消任务</button>
            <button v-if="tab === 'changes'" @click="openChange(item.id)">审阅</button>
            <button v-if="tab === 'pages' && item.status === 'active'" @click="openPage(item.id)">查看修订</button>
          </li></ul>
          <div class="toolbar"><button :disabled="offset === 0 || busy" @click="paginate(-50)">上一页</button><span>{{ offset + 1 }}–{{ offset + items.length }} / {{ total }}</span><button :disabled="offset + items.length >= total || busy" @click="paginate(50)">下一页</button></div>
        </section>
      </template>
      <section v-if="change" class="review" aria-label="候选审阅">
        <header class="toolbar"><strong>候选修改 · {{ stateLabel(change.status) }}</strong><button @click="change = null">关闭审阅</button></header>
        <div class="comparison">
          <section><h3>原文依据</h3><article v-for="source in change.sources" :key="source.version_id"><h4>{{ source.title }}</h4><p v-for="(ref, i) in source.external_references" :key="i">登记成果 · 版本 {{ ref.version }} · 原始状态 {{ ref.lifecycle }}；不自动计为独立证据，请核对上游来源链。</p><div v-for="span in source.spans" :key="span.id"><small>{{ locator(span.locator) }}</small><pre>{{ span.text }}</pre></div></article></section>
          <section><h3>拟发布内容</h3><article v-for="page in change.payload.pages" :key="page.page_id"><h4>{{ page.title }} · {{ page.base_revision ? '更新' : '新增' }}</h4><details v-if="before(page.page_id)"><summary>原修订</summary><pre>{{ before(page.page_id) }}</pre></details><p v-if="page.superseded_by">合并后此页退出当前查询，历史保留；目标 {{ page.superseded_by }}</p><p v-if="page.aliases?.length">别名：{{ page.aliases.join('、') }}</p><pre v-for="block in page.blocks" :key="block.block_id">{{ block.text }}</pre></article><article v-for="target in change.relation_targets" :key="target.page_id"><h4>关系目标：{{ target.body_json.title }} · 固定修订 {{ target.revision }}</h4><pre v-for="block in target.body_json.blocks" :key="block.block_id">{{ block.text }}</pre></article><p v-for="(link, i) in change.payload.links" :key="i">关联 {{ link.relation }}：{{ link.rationale }}</p></section>
        </div>
        <template v-if="status?.write_enabled">
          <label>审核说明 <input v-model="reason" maxlength="2000" /></label>
          <div class="toolbar"><button v-if="change.status === 'awaiting_review'" :disabled="busy || !reason.trim()" @click="review('approve')">批准当前修改集</button><button v-if="change.status === 'awaiting_review'" :disabled="busy || !reason.trim()" @click="review('reject')">退回</button><button v-if="change.status === 'approved'" :disabled="busy" @click="publish">发布已批准修订</button></div>
        </template>
      </section>
      <section v-if="detail" class="detail" aria-label="引用详情"><header class="toolbar"><strong>{{ detail.title }}</strong><button @click="detail = null">关闭详情</button></header><pre>{{ detail.text }}</pre></section>
    </template>
  </section>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import * as api from '@/api/knowledgeV3'
import KnowledgeMaintenancePanel from './KnowledgeMaintenancePanel.vue'
import KnowledgeContextPanel from './KnowledgeContextPanel.vue'
import KnowledgeOperationsPanel from './KnowledgeOperationsPanel.vue'

const status = ref<api.KnowledgeStatus | null>(null)
const spaces = ref<api.Space[]>([]), spaceId = ref(''), spaceName = ref(''), projectId = ref('')
const projects = ref<{ id: string; name: string }[]>([])
const items = ref<api.Item[]>([]), total = ref(0), offset = ref(0), tab = ref('jobs')
const file = ref<File | null>(null), concept = ref(''), question = ref(''), reason = ref('')
const change = ref<api.ChangeSet | null>(null), answer = ref<api.Answer | null>(null)
const detail = ref<{ title: string; text: string } | null>(null)
const error = ref(''), message = ref(''), busy = ref(false)
const tabs = [{ id: 'jobs', label: '资料入库' }, { id: 'changes', label: '待审核' }, { id: 'pages', label: '知识页' }, { id: 'query', label: '引用查询' }, { id: 'maintenance', label: '知识维护' }, { id: 'context', label: '上下文对照' }, { id: 'operations', label: '成果与运行' }]
let generation = 0, alive = true, timer: ReturnType<typeof setInterval> | undefined
let fileKey = api.newRequestKey()
const keys = new Map<string, string>()
function key(operation: string) { if (!keys.has(operation)) keys.set(operation, api.newRequestKey()); return keys.get(operation)! }
function locator(value: Record<string, number>) { return value.page ? `第 ${value.page} 页` : `第 ${value.line_start}–${value.line_end} 行` }
function stateLabel(value: string) { return ({ queued: '等待处理', compiling: '正在提取', awaiting_review: '待审核', approved: '已批准，待发布', applied: '已发布', completed: '入库完成', failed: '处理失败', rejected: '已退回', active: '有效', retracted: '已撤回' } as Record<string, string>)[value] || value }
function before(id: string) { const previous = change.value?.before.find(p => p.page_id === id)?.body_json; return previous ? `${previous.title}\n\n${previous.blocks.map(b => b.text).join('\n\n')}` : '' }
async function act(work: () => Promise<void>) {
  if (busy.value) return
  busy.value = true; error.value = ''; message.value = ''
  try { await work() } catch (e) { error.value = api.knowledgeError(e) } finally { busy.value = false }
}
async function refresh() {
  if (!spaceId.value || ['query', 'maintenance', 'context', 'operations'].includes(tab.value)) return
  const selected = spaceId.value, kind = tab.value, current = ++generation
  try {
    const result = await api.knowledgeItems(selected, kind, offset.value)
    if (alive && current === generation) { items.value = result.items; total.value = result.total }
  } catch (e) { if (alive && current === generation) error.value = api.knowledgeError(e) }
}
function switchSpace() { generation++; items.value = []; change.value = null; answer.value = null; detail.value = null; offset.value = 0; void refresh() }
function selectTab(id: string) { tab.value = id; offset.value = 0; items.value = []; void refresh() }
function paginate(delta: number) { offset.value += delta; void refresh() }
function selectFile(event: Event) { file.value = (event.target as HTMLInputElement).files?.[0] || null; fileKey = api.newRequestKey() }
async function createSpace() { await act(async () => {
  const operation = `space:${spaceName.value}:${projectId.value}`
  const space = await api.createKnowledgeSpace(spaceName.value, projectId.value, key(operation))
  spaces.value = await api.knowledgeSpaces(); spaceId.value = space.id; switchSpace()
}) }
async function ingest() { await act(async () => {
  if (!file.value || !spaceId.value) return
  const uploaded = await api.uploadKnowledge(spaceId.value, file.value, key(`upload:${spaceId.value}:${fileKey}`))
  await api.enqueueKnowledge(spaceId.value, uploaded.version_id, concept.value, key(`ingest:${spaceId.value}:${uploaded.version_id}:${concept.value}`))
  message.value = '已加入入库队列；候选完成后请审核。'; await refresh()
}) }
async function openChange(id: string) { await act(async () => { change.value = null; change.value = await api.knowledgeChange(id); reason.value = '' }) }
async function review(decision: string) { await act(async () => {
  if (!change.value) return
  const current = change.value
  try { await api.reviewKnowledge(current, decision, reason.value, key(`review:${current.id}:${current.payload_hash}:${decision}:${reason.value}`)) }
  catch (e) { change.value = null; throw e }
  change.value = await api.knowledgeChange(current.id); await refresh()
}) }
async function publish() { await act(async () => {
  if (!change.value) return
  const current = change.value
  try { await api.publishKnowledge(current, key(`publish:${current.id}:${current.payload_hash}`)) }
  catch (e) { change.value = null; throw e }
  message.value = status.value?.projection_enabled ? '知识修订已发布；投影等待同步，请在知识维护查看状态。' : '知识修订已发布。Markdown/图谱投影尚未启用，当前可从知识页读取。'
  change.value = await api.knowledgeChange(current.id); await refresh()
}) }
async function ask() { await act(async () => { answer.value = null; answer.value = await api.queryKnowledge(spaceId.value, question.value) }) }
async function retryJob(id: string) { await act(async () => { await api.retryKnowledgeJob(id, key(`retry:${id}`)); message.value = '已创建重试任务。'; await refresh() }) }
async function cancelJob(id: string) { await act(async () => { await api.cancelKnowledgeJob(id, key(`cancel:${id}`)); await refresh() }) }
async function openReference(reference: string) { const match = /^kb-page:(kp-[a-f0-9]{32})@(\d+)$/.exec(reference); if (match) await openPage(match[1]!, Number(match[2])) }
async function openPage(id: string, revision?: number) { await act(async () => { detail.value = null; const page = await api.knowledgePage(id, revision); detail.value = { title: `${page.title} · 修订 ${page.revision}`, text: page.body_json.blocks.map(b => b.text).join('\n\n') } }) }
async function openSource(id: string) { await act(async () => { detail.value = null; const source = await api.knowledgeSource(id); detail.value = { title: source.title, text: source.spans.map(s => `${locator(s.locator)}\n${s.text}`).join('\n\n') } }) }
onMounted(async () => {
  await act(async () => { status.value = await api.knowledgeStatus(); if (status.value.enabled) { spaces.value = await api.knowledgeSpaces(); if (status.value.write_enabled) projects.value = await api.knowledgeProjects(); spaceId.value = spaces.value[0]?.id || ''; await refresh() } })
  if (alive) timer = setInterval(() => { if (!busy.value && tab.value === 'jobs') void refresh() }, 5000)
})
onUnmounted(() => { alive = false; generation++; if (timer) clearInterval(timer) })
</script>

<style scoped>
.intake { padding: 14px; color: var(--el-text-color-primary); }
.toolbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin: 12px 0; }
label { display: inline-flex; flex-wrap: wrap; gap: 6px; align-items: center; }
button, input, select { font: inherit; color: inherit; background: var(--el-bg-color); border: 1px solid var(--el-border-color); border-radius: 6px; padding: 6px 10px; max-width: 100%; }
button { cursor: pointer; } button:disabled { opacity: .55; cursor: default; }
button[aria-pressed="true"] { color: var(--el-color-primary); border-color: var(--el-color-primary); }
.records { padding: 0; list-style: none; } .records li { display: flex; gap: 10px; flex-wrap: wrap; padding: 10px 0; border-bottom: 1px solid var(--el-border-color-light); }
.comparison { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.comparison > section { min-width: 0; } pre { font: inherit; white-space: pre-wrap; overflow-wrap: anywhere; }
.review, .detail { border-top: 1px solid var(--el-border-color); margin-top: 18px; padding-top: 14px; }
.error { color: var(--el-color-danger); } h3, h4 { margin: 12px 0; } small { color: var(--el-text-color-secondary); }
@media (max-width: 900px) { .comparison { grid-template-columns: 1fr; } }
</style>
