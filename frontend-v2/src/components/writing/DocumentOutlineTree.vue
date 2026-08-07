<template>
  <aside ref="treeRoot" class="document-outline">
    <header class="outline-toolbar">
      <input v-model="search" type="search" placeholder="搜索目录" aria-label="搜索目录" />
      <div class="outline-actions" aria-label="目录展开控制">
        <button type="button" :disabled="!branchNodes.length || searchActive" @click="expandAll">展开全部</button>
        <button type="button" :disabled="!branchNodes.length || searchActive" @click="collapseAll">收起全部</button>
      </div>
    </header>

    <div class="outline-tree" role="tree" aria-label="文档目录树">
      <div
        v-for="(node, index) in visibleNodes"
        :key="node.id"
        class="outline-row"
        :class="[`level-${node.level}`, { active: selectedNodeId === node.id }]"
        role="treeitem"
        :aria-level="node.level + 1"
        :aria-expanded="node.children.length ? expanded(node) : undefined"
        :aria-current="selectedNodeId === node.id ? 'location' : undefined"
      >
        <button
          v-if="node.children.length"
          type="button"
          class="outline-toggle"
          :aria-label="`${expanded(node) ? '收起' : '展开'}${node.title}`"
          :aria-expanded="expanded(node)"
          :disabled="searchActive"
          @click.stop="toggle(node)"
        >
          <span aria-hidden="true">{{ expanded(node) ? '▾' : '▸' }}</span>
        </button>
        <span v-else class="outline-toggle-placeholder" aria-hidden="true">{{ node.level >= 3 ? '·' : '—' }}</span>

        <button
          type="button"
          class="outline-node"
          :class="`level-${node.level}`"
          :data-outline-node-id="node.id"
          @click="activate(node)"
          @keydown="handleKeydown($event, node, index)"
        >
          <span class="outline-label"><strong>{{ node.title }}</strong></span>
          <small v-if="node.node_type === 'document'">
            {{ node.children.length }} 项
            <template v-if="node.metadata?.labels?.length"> · {{ node.metadata.labels.join(' · ') }}</template>
          </small>
          <small v-else-if="node.level === 1">{{ node.children.length }} 节 · {{ formatNumber(node.word_count) }}</small>
          <small v-else-if="node.children.length">{{ node.children.length }} 小节</small>
        </button>
      </div>
      <p v-if="!visibleNodes.length" class="outline-empty">没有匹配的目录项</p>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { WritingDirectoryNode } from '@/api/writing'

const props = defineProps<{
  nodes: WritingDirectoryNode[]
  projectId: string
  documentId: string
  selectedNodeId?: string
}>()

const emit = defineEmits<{
  select: [node: WritingDirectoryNode]
}>()

const treeRoot = ref<HTMLElement>()
const search = ref('')
const collapsedIds = ref<Set<string>>(new Set())
const storageKey = computed(() => `writing-outline:${props.projectId}:${props.documentId}`)
const searchActive = computed(() => Boolean(search.value.trim()))

function walk(nodes: WritingDirectoryNode[], visit: (node: WritingDirectoryNode, ancestors: WritingDirectoryNode[]) => void, ancestors: WritingDirectoryNode[] = []) {
  nodes.forEach(node => {
    visit(node, ancestors)
    walk(node.children, visit, [...ancestors, node])
  })
}

function findPath(nodeId: string) {
  let result: WritingDirectoryNode[] = []
  walk(props.nodes, (node, ancestors) => {
    if (node.id === nodeId) result = [...ancestors, node]
  })
  return result
}

function branchIds() {
  const ids: string[] = []
  walk(props.nodes, node => {
    if (node.children.length) ids.push(node.id)
  })
  return ids
}

const branchNodes = computed(() => branchIds())

function restoreState() {
  const available = new Set(branchIds())
  let restored: string[] | undefined
  try {
    restored = JSON.parse(localStorage.getItem(storageKey.value) || 'null') || undefined
  } catch {
    restored = undefined
  }
  if (restored) {
    collapsedIds.value = new Set(restored.filter(id => available.has(id)))
  } else {
    collapsedIds.value = new Set(
      branchIds().filter(id => props.nodes.every(root => root.id !== id))
    )
  }
  expandSelectedPath(false)
}

function persistState() {
  try {
    localStorage.setItem(storageKey.value, JSON.stringify([...collapsedIds.value]))
  } catch {
    // Storage can be unavailable in private or hardened browser contexts.
  }
}

function expandSelectedPath(persist = true) {
  if (!props.selectedNodeId) return
  const next = new Set(collapsedIds.value)
  findPath(props.selectedNodeId).slice(0, -1).forEach(node => next.delete(node.id))
  collapsedIds.value = next
  if (persist) persistState()
}

function filterTree(nodes: WritingDirectoryNode[], keyword: string): WritingDirectoryNode[] {
  if (!keyword) return nodes
  return nodes.flatMap(node => {
    const children = filterTree(node.children, keyword)
    if (node.title.toLocaleLowerCase('zh-CN').includes(keyword) || children.length) {
      return [{ ...node, children }]
    }
    return []
  })
}

function flattenTree(nodes: WritingDirectoryNode[]): WritingDirectoryNode[] {
  return nodes.flatMap(node => {
    const children = searchActive.value || !collapsedIds.value.has(node.id)
      ? flattenTree(node.children)
      : []
    return [node, ...children]
  })
}

const visibleNodes = computed(() => {
  const keyword = search.value.trim().toLocaleLowerCase('zh-CN')
  return flattenTree(filterTree(props.nodes, keyword))
})

function expanded(node: WritingDirectoryNode) {
  return searchActive.value || !collapsedIds.value.has(node.id)
}

function toggle(node: WritingDirectoryNode) {
  if (!node.children.length || searchActive.value) return
  const next = new Set(collapsedIds.value)
  if (next.has(node.id)) next.delete(node.id)
  else next.add(node.id)
  collapsedIds.value = next
  persistState()
}

function expandAll() {
  collapsedIds.value = new Set()
  persistState()
}

function collapseAll() {
  collapsedIds.value = new Set(branchIds())
  persistState()
}

function activate(node: WritingDirectoryNode) {
  if (node.node_type === 'document') {
    toggle(node)
    return
  }
  emit('select', node)
}

function focusNode(nodeId?: string) {
  if (!nodeId) return
  const escaped = typeof CSS !== 'undefined' && CSS.escape ? CSS.escape(nodeId) : nodeId.replaceAll('"', '\\"')
  treeRoot.value?.querySelector<HTMLButtonElement>(`[data-outline-node-id="${escaped}"]`)?.focus()
}

function handleKeydown(event: KeyboardEvent, node: WritingDirectoryNode, index: number) {
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    focusNode(visibleNodes.value[index + 1]?.id)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    focusNode(visibleNodes.value[index - 1]?.id)
  } else if (event.key === 'ArrowRight' && node.children.length) {
    event.preventDefault()
    if (!expanded(node)) toggle(node)
    else focusNode(node.children[0]?.id)
  } else if (event.key === 'ArrowLeft') {
    event.preventDefault()
    if (node.children.length && expanded(node)) {
      toggle(node)
    } else {
      const path = findPath(node.id)
      focusNode(path[path.length - 2]?.id)
    }
  } else if (event.key === 'Enter') {
    event.preventDefault()
    activate(node)
  } else if (event.key === ' ') {
    event.preventDefault()
    if (node.children.length) toggle(node)
    else activate(node)
  }
}

function formatNumber(value?: number | null) {
  return new Intl.NumberFormat('zh-CN').format(value || 0)
}

watch(
  [storageKey, () => props.nodes],
  restoreState,
  { immediate: true }
)
watch(() => props.selectedNodeId, () => expandSelectedPath())
</script>

<style scoped>
.document-outline {
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--line-color);
  border-radius: 6px;
  background: var(--card-bg);
}
.outline-toolbar { display: grid; gap: 8px; }
.outline-toolbar input {
  width: 100%;
  min-width: 0;
  height: 32px;
  padding: 0 10px;
  border: 1px solid var(--line-color);
  border-radius: 4px;
  color: var(--text-primary);
  outline: none;
  background: var(--page-bg);
}
.outline-toolbar input:focus { border-color: var(--view-color-primary); }
.outline-actions { display: flex; gap: 6px; justify-content: flex-end; }
.outline-actions button {
  padding: 3px 7px;
  border: 1px solid var(--line-color);
  border-radius: 3px;
  color: var(--text-secondary);
  font-size: 10px;
  background: transparent;
  cursor: pointer;
}
.outline-actions button:hover:not(:disabled) { color: var(--view-color-primary); border-color: var(--view-color-primary); }
.outline-actions button:disabled { cursor: default; opacity: .45; }
.outline-tree { display: grid; gap: 2px; max-height: calc(100vh - 350px); margin-top: 8px; overflow-y: auto; }
.outline-row { display: grid; grid-template-columns: 24px minmax(0, 1fr); align-items: start; min-width: 0; }
.outline-row.level-1 { padding-left: 12px; }
.outline-row.level-2 { padding-left: 28px; }
.outline-row.level-3 { padding-left: 44px; opacity: .9; }
.outline-toggle, .outline-toggle-placeholder {
  display: grid;
  width: 24px;
  min-width: 24px;
  height: 32px;
  place-items: center;
  border: 0;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1;
  background: transparent;
}
.outline-toggle { border-radius: 3px; cursor: pointer; }
.outline-toggle:hover:not(:disabled), .outline-toggle:focus-visible { color: var(--view-color-primary); background: var(--view-color-faint); }
.outline-toggle:disabled { cursor: default; opacity: .7; }
.outline-node {
  display: grid;
  gap: 3px;
  min-width: 0;
  padding: 7px 8px;
  border: 0;
  border-left: 2px solid transparent;
  color: inherit;
  text-align: left;
  background: transparent;
  cursor: pointer;
}
.outline-node:hover, .outline-node:focus-visible, .outline-row.active .outline-node {
  border-left-color: var(--view-color-primary);
  outline: none;
  background: var(--view-color-faint);
}
.outline-node.level-0 { padding-top: 9px; padding-bottom: 9px; }
.outline-node.level-3 { padding-top: 5px; padding-bottom: 5px; }
.outline-node strong { min-width: 0; color: var(--text-primary); font-size: 11px; line-height: 1.4; overflow-wrap: anywhere; }
.outline-node.level-0 strong { font-size: 11.5px; }
.outline-node.level-2 strong { font-size: 10.5px; font-weight: 600; }
.outline-node.level-3 strong { color: var(--text-secondary); font-size: 10px; font-weight: 500; }
.outline-node small { color: var(--text-secondary); font-size: 9px; }
.outline-empty { margin: 16px 4px; color: var(--text-secondary); font-size: 11px; text-align: center; }
@media (max-width: 900px) {
  .outline-tree { max-height: none; }
}
</style>
