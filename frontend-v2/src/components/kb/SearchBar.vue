<template>
  <div class="search-bar">
    <el-input
      v-model="query"
      placeholder="搜索知识库..."
      clearable
      :prefix-icon="Search"
      @keyup.enter="doSearch"
      @clear="clearSearch"
    />
    <el-button :loading="loading" @click="doSearch">搜索</el-button>

    <!-- 搜索结果下拉 -->
    <div v-if="results.length" class="search-results">
      <div class="results-header">
        <span>找到 {{ total }} 条结果</span>
        <el-button text size="small" @click="clearSearch">清空</el-button>
      </div>
      <div class="results-list">
        <div
          v-for="(item, idx) in results"
          :key="idx"
          class="result-item"
          @click="selectResult(item)"
        >
          <div class="result-name">
            <el-icon><Document /></el-icon>
            <span>{{ item.name }}</span>
            <el-tag
              size="small"
              :type="item.match === 'filename' ? 'primary' : 'info'"
            >{{ item.match === 'filename' ? '文件名' : '内容' }}</el-tag>
          </div>
          <div v-if="item.preview" class="result-preview">
            {{ item.preview }}
          </div>
          <div class="result-path">{{ item.path }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Search, Document } from '@element-plus/icons-vue'
import { searchKnowledge, type SearchHit } from '@/api/knowledge'

const emit = defineEmits<{
  (e: 'select', path: string): void
  (e: 'clear'): void
}>()

const query = ref('')
const loading = ref(false)
const results = ref<SearchHit[]>([])
const total = ref(0)

async function doSearch() {
  const q = query.value.trim()
  if (!q) {
    clearSearch()
    return
  }
  loading.value = true
  try {
    const res = await searchKnowledge(q, 50)
    results.value = res.nodes
    total.value = res.total
  } catch {
    results.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function clearSearch() {
  query.value = ''
  results.value = []
  total.value = 0
  emit('clear')
}

function selectResult(item: SearchHit) {
  emit('select', item.path)
  clearSearch()
}
</script>

<style scoped>
.search-bar {
  position: relative;
  display: flex;
  gap: 8px;
  align-items: center;
}

.search-results {
  position: absolute;
  top: calc(100% + 8px);
  left: 0;
  right: 0;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  z-index: 100;
  max-height: 400px;
  overflow: auto;
}

.results-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  border-bottom: 1px solid #e4e7ed;
  font-size: 13px;
  color: #606266;
}

.results-list {
  padding: 8px;
}

.result-item {
  padding: 8px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.2s;
}

.result-item:hover {
  background: #f5f7fa;
}

.result-name {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
  font-size: 14px;
  color: #303133;
}

.result-preview {
  margin-top: 4px;
  font-size: 12px;
  color: #606266;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.result-path {
  margin-top: 2px;
  font-size: 11px;
  color: #909399;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
