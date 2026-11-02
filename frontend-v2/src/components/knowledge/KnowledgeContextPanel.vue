<template>
  <section aria-label="知识上下文对照" class="context-panel">
    <p>Shadow 仅比较候选知识，不送入任务执行，不改变已审核记忆的排序。</p>
    <p v-if="mode !== 'shadow'">知识上下文对照尚未开启。正式注入仍关闭。</p>
    <p v-else-if="!projectId">此空间未绑定项目，请选择有明确项目范围的知识空间。</p>
    <template v-else>
      <p v-if="error" role="alert">{{ error }}</p>
      <form @submit.prevent="generate(false)">
        <label>任务问题 <input v-model="question" required minlength="2" maxlength="2000" :disabled="busy" /></label>
        <label>总字符预算 <input v-model.number="totalChars" type="number" min="1000" max="30000" :disabled="busy" /></label>
        <label>已有背景占用 <input v-model.number="baselineChars" type="number" min="0" max="100000" :disabled="busy" /></label>
        <div class="actions"><button :disabled="busy || question.trim().length < 2">只读预览</button><button v-if="writeEnabled" type="button" :disabled="busy || question.trim().length < 2" @click="generate(true)">保存对照快照</button></div>
      </form>
      <article v-if="snapshot" aria-label="候选知识背景">
        <p role="status">{{ snapshot.id ? '对照快照已保存' : '只读预览，未保存' }} · 未注入执行</p>
        <p>知识预算 {{ snapshot.budget.knowledge_chars_used }} / {{ snapshot.budget.knowledge_chars_limit }} 字符，最多占总预算 25%；已有背景保留。</p>
        <p v-if="snapshot.conflict_count">存在 {{ snapshot.conflict_count }} 组已标记矛盾，请在引用查询中核对双方依据。</p>
        <p v-if="!snapshot.items.length">{{ snapshot.gaps.includes('budget_exhausted') ? '剩余预算不足，未加入知识内容。' : '未找到可用知识依据。' }}</p>
        <section v-for="(item, index) in snapshot.items" :key="index"><h4>{{ item.title }} · 修订 {{ item.revision }} · {{ epistemicLabel(item.epistemic_status) }}</h4><pre>{{ item.content }}</pre><button v-for="evidence in item.evidence" :key="evidence.ref" :disabled="busy" @click="$emit('source', evidence.source_version_id)">核对原文 · {{ evidence.locator.page ? '第 ' + evidence.locator.page + ' 页' : '第 ' + evidence.locator.line_start + ' 行' }}</button></section>
        <button v-if="snapshot.id" :disabled="busy" @click="revalidate">重新校验快照与访问权限</button>
      </article>
    </template>
  </section>
</template>
<script setup lang="ts">
import { onUnmounted, ref } from 'vue'
import * as api from '@/api/knowledgeV3'
const props = defineProps<{ spaceId: string; projectId: string; mode: string; writeEnabled: boolean }>()
defineEmits<{ source: [id: string] }>()
const question = ref(''), totalChars = ref(12000), baselineChars = ref(0), busy = ref(false), error = ref('')
const snapshot = ref<api.ShadowSnapshot | null>(null)
const keys = new Map<string, string>(); let alive = true
function epistemicLabel(status: string) { return ({ reported: '知识页陈述', inference: '推论', uncertain: '待核实' } as Record<string, string>)[status] || '待核对' }
async function act(operation: () => Promise<api.ShadowSnapshot>) { if (busy.value) return; busy.value = true; error.value = ''; snapshot.value = null; try { const result = await operation(); if (alive) snapshot.value = result } catch (e) { if (alive) error.value = api.knowledgeError(e) } finally { busy.value = false } }
async function generate(save: boolean) { const body = { project_id: props.projectId, query: question.value, total_chars: totalChars.value, baseline_chars: baselineChars.value }; const hash = JSON.stringify(body); if (!keys.has(hash)) keys.set(hash, api.newRequestKey()); await act(() => save ? api.captureKnowledgeContext(props.spaceId, body, keys.get(hash)!) : api.previewKnowledgeContext(props.spaceId, body)); if (save && snapshot.value?.id) keys.delete(hash) }
async function revalidate() { const id = snapshot.value?.id; if (id) await act(() => api.readKnowledgeContext(id, props.projectId)) }
onUnmounted(() => { alive = false })
</script>
<style scoped>
.context-panel { padding: 12px 0; } form { display: flex; flex-wrap: wrap; gap: 12px; align-items: end; } label { display: flex; flex-direction: column; gap: 6px; max-width: 100%; } input, button { font: inherit; color: var(--el-text-color-primary); background: var(--el-bg-color); border: 1px solid var(--el-border-color); border-radius: 6px; padding: 8px; max-width: 100%; box-sizing: border-box; } .actions { display: flex; gap: 8px; flex-wrap: wrap; } button { cursor: pointer; } button:disabled { opacity: .5; } article { border-top: 1px solid var(--el-border-color); margin-top: 20px; } article section { margin-bottom: 18px; } pre { white-space: pre-wrap; overflow-wrap: anywhere; font: inherit; } [role="alert"] { color: var(--el-color-danger); }
</style>
