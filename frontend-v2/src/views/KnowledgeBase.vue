<template>
  <div class="knowledge-base-page">
    <!-- 顶部操作栏 -->
    <div class="top-bar">
      <SearchBar
        @select="onSearchSelect"
        @clear="onSearchClear"
      />
      <div class="top-actions">
        <el-button :icon="Refresh" :loading="loading" @click="refreshTree">刷新</el-button>
      </div>
    </div>

    <!-- 主内容区：左树右预览 -->
    <div class="main-content">
      <!-- 左侧目录树 -->
      <div class="left-panel">
        <DirectoryTree
          :tree-data="treeData"
          @node-click="onTreeNodeClick"
        />
      </div>

      <!-- 右侧文件预览 -->
      <div class="right-panel">
        <FilePreview
          ref="filePreviewRef"
          @navigate="onBacklinkNavigate"
        />
      </div>
    </div>

    <!-- 底部统计栏 -->
    <div class="stats-bar">
      <el-icon><DataAnalysis /></el-icon>
      <span>统计: {{ stats.categories }} 个分类 | {{ stats.directories }} 个子目录 | {{ stats.files }} 个文件</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Refresh, DataAnalysis } from '@element-plus/icons-vue'
import DirectoryTree from '@/components/kb/DirectoryTree.vue'
import FilePreview from '@/components/kb/FilePreview.vue'
import SearchBar from '@/components/kb/SearchBar.vue'
import { getTree, type TreeItem } from '@/api/knowledge'

const treeData = ref<TreeItem[]>([])
const loading = ref(false)
const filePreviewRef = ref()

const stats = ref({
  categories: 0,
  directories: 0,
  files: 0
})

// 加载目录树
async function loadTree() {
  loading.value = true
  try {
    const res = await getTree()
    treeData.value = res.tree
    computeStats(res.tree)
  } catch (e) {
    console.error('目录树加载失败:', e)
  } finally {
    loading.value = false
  }
}

// 计算统计信息
function computeStats(tree: TreeItem[]) {
  let dirs = 0
  let files = 0
  function walk(nodes: TreeItem[]) {
    for (const n of nodes) {
      if (n.type === 'directory') {
        dirs++
        if (n.children) walk(n.children)
      } else {
        files++
      }
    }
  }
  walk(tree)
  stats.value = { categories: tree.length, directories: dirs, files }
}

// 目录树节点点击
function onTreeNodeClick(data: TreeItem) {
  if (data.type === 'file') {
    filePreviewRef.value?.loadFile(data.path)
  }
  // 目录节点不做额外处理（el-tree 自带展开/折叠）
}

// 搜索结果选择
function onSearchSelect(path: string) {
  filePreviewRef.value?.loadFile(path)
}

// 搜索清空
function onSearchClear() {
  // 可选：清空预览
}

// 双向链接跳转
function onBacklinkNavigate(path: string) {
  filePreviewRef.value?.loadFile(path)
}

// 刷新
function refreshTree() {
  loadTree()
}

onMounted(() => {
  loadTree()
})
</script>

<style scoped>
.knowledge-base-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 120px);
  min-height: 500px;
  gap: 12px;
}

.top-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.top-bar .search-bar {
  flex: 1;
}

.main-content {
  display: flex;
  gap: 12px;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.left-panel {
  width: 320px;
  min-width: 240px;
  max-width: 480px;
  background: #fff;
  border-radius: 8px;
  border: 1px solid #e4e7ed;
  overflow: auto;
  flex-shrink: 0;
}

.right-panel {
  flex: 1;
  background: #fff;
  border-radius: 8px;
  border: 1px solid #e4e7ed;
  overflow: auto;
  min-width: 0;
}

.stats-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: #f5f7fa;
  border-radius: 8px;
  font-size: 13px;
  color: #606266;
  flex-shrink: 0;
}

.stats-bar .el-icon {
  font-size: 16px;
}

/* 响应式 */
@media (max-width: 768px) {
  .main-content {
    flex-direction: column;
  }

  .left-panel {
    width: 100%;
    max-width: 100%;
    height: 200px;
  }
}
</style>
