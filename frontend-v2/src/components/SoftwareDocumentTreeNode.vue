<template>
  <ul class="document-tree-level">
    <li v-for="node in visibleNodes" :key="node.id">
      <details v-if="node.kind === 'folder'" :open="shouldOpen(node)">
        <summary>
          <Folder />
          <span class="document-tree-node-label" :title="node.label">{{ node.label }}</span>
          <em>{{ visibleChildren(node).length }}</em>
        </summary>
        <SoftwareDocumentTreeNode
          :nodes="node.children"
          :selected-path="selectedPath"
          :text-filter="textFilter"
          :category-filter="categoryFilter"
          @select="$emit('select', $event)"
        />
      </details>
      <button
        v-else
        type="button"
        :class="['document-tree-file', { active: selectedPath === node.path }]"
        @click="$emit('select', node)"
      >
        <Document />
        <span class="document-tree-node-label" :title="node.label">{{ node.label }}</span>
        <em>{{ node.extension }}</em>
      </button>
    </li>
  </ul>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Document, Folder } from '@element-plus/icons-vue'
import type { SoftwareDocumentNode } from '@/api/projects'

defineOptions({ name: 'SoftwareDocumentTreeNode' })

const props = defineProps<{
  nodes: SoftwareDocumentNode[]
  selectedPath: string
  textFilter: string
  categoryFilter: string
}>()

defineEmits<{ select: [node: SoftwareDocumentNode] }>()

const visibleNodes = computed(() => props.nodes.filter(matchesNode))

function matchesNode(node: SoftwareDocumentNode): boolean {
  if (node.kind === 'folder') return node.children.some(matchesNode)
  const textMatch = !props.textFilter || node.label.toLowerCase().includes(props.textFilter.toLowerCase())
    || node.path.toLowerCase().includes(props.textFilter.toLowerCase())
  const categoryMatch = !props.categoryFilter || node.category === props.categoryFilter
  return textMatch && categoryMatch
}

function visibleChildren(node: SoftwareDocumentNode) {
  return node.children.filter(matchesNode)
}

function shouldOpen(node: SoftwareDocumentNode) {
  if (props.textFilter || props.categoryFilter) return true
  return ['docs', 'architecture', 'data_lake', 'structure'].includes(node.label)
}
</script>

<style scoped>
.document-tree-level {
  margin: 0;
  padding: 0 0 0 13px;
  list-style: none;
}

.document-tree-level:first-child { padding-left: 0; }
.document-tree-level li { min-width: 0; }
details > summary,
.document-tree-file {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  height: 28px;
  padding: 0 6px;
  color: var(--el-text-color-regular);
  border: 0;
  border-radius: 3px;
  background: transparent;
  cursor: pointer;
  font-size: 11px;
  text-align: left;
}

details > summary { list-style: none; }
details > summary::-webkit-details-marker { display: none; }
details > summary::before {
  content: '›';
  width: 9px;
  color: var(--el-text-color-placeholder);
  transform: rotate(0deg);
  transition: transform .14s ease;
}
details[open] > summary::before { transform: rotate(90deg); }
.document-tree-file { padding-left: 21px; }
details > summary:hover,
.document-tree-file:hover { background: var(--el-fill-color-light); }
.document-tree-file.active { color: var(--el-color-primary); background: var(--el-color-primary-light-9); }
svg { width: 14px; flex: none; color: var(--el-color-primary); }
.document-tree-node-label { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
em { margin-left: auto; color: var(--el-text-color-placeholder); font-size: 9px; font-style: normal; text-transform: uppercase; }
</style>
