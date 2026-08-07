<template>
  <div
    class="document-structure-status"
    :class="`is-${sync.status}`"
    :data-structure-sync-status="sync.status"
  >
    <el-tag :type="tagType" effect="plain">{{ label }}</el-tag>
    <span>{{ sync.message }}</span>
    <small v-if="sync.status === 'diverged' && sync.changed_chapters.length">
      涉及第{{ sync.changed_chapters.join('、') }}章
    </small>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { WritingStructureSync } from '@/api/writing'

const props = withDefaults(defineProps<{
  sync: WritingStructureSync
  targetLabel?: string
}>(), {
  targetLabel: '目标目录'
})

const tagType = computed(() => {
  if (props.sync.status === 'aligned') return 'success'
  if (props.sync.status === 'diverged') return 'warning'
  return 'info'
})

const label = computed(() => {
  if (props.sync.status === 'aligned') {
    const version = props.sync.current_version ? ` · ${props.sync.current_version}` : ''
    return `当前结构与${props.targetLabel}一致${version}`
  }
  if (props.sync.status === 'diverged') return `当前结构与${props.targetLabel}存在差异`
  return `未设置${props.targetLabel}`
})
</script>

<style scoped>
.document-structure-status {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding: 8px 10px;
  border: 1px solid var(--line-color);
  background: var(--view-color-faint);
}

.document-structure-status span {
  min-width: 0;
  color: var(--text-secondary);
  font-size: 11px;
}

.document-structure-status small {
  margin-left: auto;
  color: var(--text-secondary);
  white-space: nowrap;
  font-size: 10px;
}

.document-structure-status.is-diverged {
  border-color: color-mix(in srgb, #e6a23c 45%, var(--line-color));
}
</style>
