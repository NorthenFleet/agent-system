<template>
  <div class="directory-tree">
    <el-input
      v-model="filterText"
      placeholder="筛选目录..."
      clearable
      size="small"
      prefix-icon="Search"
      class="tree-filter"
    />
    <el-tree
      ref="treeRef"
      :data="treeData"
      :props="treeProps"
      node-key="id"
      :filter-node-method="filterNode"
      :default-expanded-keys="['06-projects']"
      highlight-current
      @node-click="handleNodeClick"
    >
      <template #default="{ node, data }">
        <span class="custom-tree-node">
          <el-icon v-if="data.type === 'directory'" class="node-icon folder-icon"><Folder /></el-icon>
          <el-icon v-else-if="data.ext === 'md'" class="node-icon md-icon"><Document /></el-icon>
          <el-icon v-else-if="isImage(data.ext)" class="node-icon img-icon"><Picture /></el-icon>
          <el-icon v-else-if="data.ext === 'pdf'" class="node-icon pdf-icon"><Files /></el-icon>
          <el-icon v-else-if="data.ext === 'docx'" class="node-icon doc-icon"><EditPen /></el-icon>
          <el-icon v-else class="node-icon file-icon"><Files /></el-icon>
          <span class="node-label" :title="node.label">{{ node.label }}</span>
          <el-tag v-if="data.type === 'file'" size="small" class="ext-tag">{{ data.ext }}</el-tag>
        </span>
      </template>
    </el-tree>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { Folder, Document, Picture, Files, EditPen } from '@element-plus/icons-vue'
import type { TreeInstance } from 'element-plus'

const props = defineProps<{
  treeData: any[]
}>()

const emit = defineEmits<{
  (e: 'node-click', data: any): void
}>()

const treeRef = ref<TreeInstance>()
const filterText = ref('')

const treeProps = {
  children: 'children',
  label: 'name'
}

watch(filterText, (val) => {
  treeRef.value?.filter(val)
})

const filterNode = (value: string, data: any) => {
  if (!value) return true
  return data.name.toLowerCase().includes(value.toLowerCase())
}

const isImage = (ext?: string) => ['png', 'jpg', 'jpeg', 'svg', 'gif', 'webp'].includes(ext || '')

const handleNodeClick = (data: any) => {
  emit('node-click', data)
}
</script>

<style scoped>
.directory-tree {
  height: 100%;
  overflow: auto;
  padding: 8px 4px;
}

.tree-filter {
  margin-bottom: 12px;
}

.custom-tree-node {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  min-width: 0;
  padding-right: 8px;
}

.node-icon {
  flex-shrink: 0;
  font-size: 16px;
}

.folder-icon { color: #e6a23c; }
.md-icon { color: #409eff; }
.img-icon { color: #67c23a; }
.pdf-icon { color: #f56c6c; }
.doc-icon { color: #909399; }
.file-icon { color: #909399; }

.node-label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
}

.ext-tag {
  flex-shrink: 0;
  font-size: 10px;
  padding: 0 4px;
  height: 18px;
  line-height: 16px;
}

:deep(.el-tree-node__content) {
  height: 32px;
  border-radius: 6px;
  padding: 0 4px;
}

:deep(.el-tree-node__content:hover) {
  background-color: rgba(64, 158, 255, 0.08);
}

:deep(.el-tree-node.is-current > .el-tree-node__content) {
  background-color: rgba(64, 158, 255, 0.15);
  color: #409eff;
}
</style>
