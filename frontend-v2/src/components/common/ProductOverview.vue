<template>
  <el-card class="products-overview-card" shadow="hover" @click="goToProducts">
    <template #header>
      <div class="card-header">
        <span class="card-title">🎯 产品矩阵</span>
        <span class="card-link">查看 →</span>
      </div>
    </template>

    <!-- Loading -->
    <div v-if="loading" class="overview-loading">
      <el-icon class="is-loading"><Loading /></el-icon>
    </div>

    <!-- Product list -->
    <div v-else class="product-summaries">
      <div
        v-for="product in products"
        :key="product.id"
        class="product-summary-item"
        :class="`status-${product.status}`"
      >
        <span class="summary-emoji">{{ product.emoji }}</span>
        <div class="summary-info">
          <span class="summary-name">{{ product.name }}</span>
          <el-tag :type="statusType(product.status)" size="small" round>
            {{ product.statusLabel }}
          </el-tag>
        </div>
        <div class="summary-progress">
          <el-progress
            :percentage="calcOverallProgress(product.modules)"
            :stroke-width="6"
            :color="statusColor(product.status)"
            :show-text="false"
          />
          <span class="progress-pct">{{ calcOverallProgress(product.modules) }}%</span>
        </div>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Loading } from '@element-plus/icons-vue'

const router = useRouter()
const products = ref<any[]>([])
const loading = ref(true)

function statusType(status: string): '' | 'success' | 'warning' | 'info' {
  const map: Record<string, '' | 'success' | 'warning' | 'info'> = {
    'done': 'success',
    'in-progress': 'warning',
    'planning': 'info'
  }
  return map[status] || ''
}

function statusColor(status: string): string {
  const map: Record<string, string> = {
    'done': '#67C23A',
    'in-progress': '#E6A23C',
    'planning': '#409EFF'
  }
  return map[status] || '#409EFF'
}

function calcOverallProgress(modules: Array<{ progress: number }>): number {
  if (!modules || !modules.length) return 0
  return Math.round(modules.reduce((sum, m) => sum + m.progress, 0) / modules.length)
}

const localProducts = [
  {
    id: 'manual-chess', name: '手工纸质兵棋', emoji: '📦',
    status: 'in-progress', statusLabel: '原型设计中',
    modules: [
      { name: '规则体系设计', status: 'in-progress', progress: 40 },
      { name: '地图与棋子原型', status: 'in-progress', progress: 30 },
      { name: '教学关卡设计', status: 'planning', progress: 10 }
    ]
  },
  {
    id: 'digital-chess', name: '电子化兵棋', emoji: '💻',
    status: 'in-progress', statusLabel: '原型设计中',
    modules: [
      { name: '规则引擎', status: 'planning', progress: 10 },
      { name: '交互界面', status: 'planning', progress: 5 },
      { name: '多人在线同步', status: 'planning', progress: 0 }
    ]
  },
  {
    id: 'ai-chess', name: '智能兵棋', emoji: '🤖',
    status: 'planning', statusLabel: '规划中',
    modules: [
      { name: 'AI 决策框架', status: 'planning', progress: 0 },
      { name: '智能体接入', status: 'planning', progress: 0 },
      { name: 'RL 训练管线', status: 'planning', progress: 0 }
    ]
  }
]

async function loadProducts() {
  loading.value = true
  try {
    const res = await fetch('/api/v2/products')
    if (res.ok) {
      const data = await res.json()
      products.value = data.products || data
    } else {
      products.value = localProducts
    }
  } catch {
    products.value = localProducts
  } finally {
    loading.value = false
  }
}

function goToProducts() {
  router.push('/products')
}

onMounted(() => {
  loadProducts()
})
</script>

<style scoped>
.products-overview-card {
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  border-radius: 12px;
}

.products-overview-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: #1d1e2c;
}

.card-link {
  font-size: 13px;
  color: #409eff;
  font-weight: 500;
}

.overview-loading {
  display: flex;
  justify-content: center;
  padding: 20px 0;
}

.overview-loading .el-icon {
  font-size: 24px;
  color: #909399;
}

.product-summaries {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.product-summary-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-radius: 8px;
  transition: background 0.15s;
}

.product-summary-item:hover {
  background: #f5f7fa;
}

.summary-emoji {
  font-size: 22px;
  flex-shrink: 0;
}

.summary-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.summary-name {
  font-size: 13px;
  font-weight: 500;
  color: #303133;
}

.summary-progress {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 120px;
  flex-shrink: 0;
}

.progress-pct {
  font-size: 11px;
  color: #909399;
  min-width: 30px;
  text-align: right;
}

/* Status tint */
.product-summary-item.status-in-progress {
  background: linear-gradient(to right, #fdf6ec22, transparent);
}

.product-summary-item.status-planning {
  background: linear-gradient(to right, #ecf5ff22, transparent);
}

.product-summary-item.status-done {
  background: linear-gradient(to right, #f0f9eb22, transparent);
}
</style>
