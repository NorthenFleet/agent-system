<template>
  <div class="knowledge-page">
    <el-row :gutter="16" class="stats-row">
      <el-col :span="6"><el-card class="stat-card" shadow="hover"><span>节点</span><strong>{{ stats?.nodes || 0 }}</strong></el-card></el-col>
      <el-col :span="6"><el-card class="stat-card" shadow="hover"><span>关系</span><strong>{{ stats?.edges || 0 }}</strong></el-card></el-col>
      <el-col :span="6"><el-card class="stat-card" shadow="hover"><span>类型</span><strong>{{ typeCount }}</strong></el-card></el-col>
      <el-col :span="6"><el-card class="stat-card" shadow="hover"><span>可用</span><strong>{{ stats?.available ? '是' : '否' }}</strong></el-card></el-col>
    </el-row>

    <el-row :gutter="18">
      <el-col :span="8">
        <el-card class="panel" shadow="hover">
          <template #header><span>知识类型</span></template>
          <div class="type-list">
            <div v-for="[name, value] in topTypes" :key="name" class="type-row">
              <span>{{ name }}</span>
              <el-progress :percentage="typePercent(value)" :format="() => String(value)" />
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="16">
        <el-card class="panel" shadow="hover">
          <template #header>
            <div class="panel-header">
              <span>知识节点</span>
              <el-input v-model="keyword" size="small" placeholder="搜索标题或类型" clearable style="width: 260px" />
            </div>
          </template>
          <el-table :data="filteredNodes" size="small" height="520">
            <el-table-column prop="title" label="标题" min-width="260" show-overflow-tooltip />
            <el-table-column prop="type" label="类型" width="100" />
            <el-table-column prop="path" label="路径" min-width="320" show-overflow-tooltip />
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getKnowledgeNodes, getKnowledgeStats, type KnowledgeNode, type KnowledgeStats } from '@/api/openclaw'

const stats = ref<KnowledgeStats | null>(null)
const nodes = ref<KnowledgeNode[]>([])
const keyword = ref('')

const typeCount = computed(() => Object.keys(stats.value?.entity_types || {}).length)
const topTypes = computed(() => Object.entries(stats.value?.entity_types || {}).sort((a, b) => b[1] - a[1]).slice(0, 12))
const filteredNodes = computed(() => {
  const key = keyword.value.trim().toLowerCase()
  if (!key) return nodes.value.slice(0, 300)
  return nodes.value.filter(node => `${node.title} ${node.type}`.toLowerCase().includes(key)).slice(0, 300)
})

function typePercent(value: number) {
  const total = stats.value?.nodes || 1
  return Math.max(1, Math.round(value / total * 100))
}

async function loadKnowledge() {
  try {
    const [statsData, nodesData] = await Promise.all([getKnowledgeStats(), getKnowledgeNodes()])
    stats.value = statsData
    nodes.value = nodesData.nodes
  } catch {
    ElMessage.error('知识库数据加载失败')
  }
}

onMounted(loadKnowledge)
</script>

<style scoped>
.knowledge-page {
  display: grid;
  gap: 16px;
}

.stat-card,
.panel {
  border-radius: 8px;
}

.stat-card :deep(.el-card__body) {
  display: grid;
  gap: 8px;
}

.stat-card span {
  color: #909399;
  font-size: 13px;
}

.stat-card strong {
  color: #303133;
  font-size: 24px;
}

.panel-header,
.type-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.type-list {
  display: grid;
  gap: 14px;
}

.type-row span {
  width: 88px;
  color: #606266;
  font-size: 13px;
}

.type-row :deep(.el-progress) {
  flex: 1;
}
</style>
