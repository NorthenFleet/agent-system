<template>
  <div class="products-page">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1>🎯 兵棋产品矩阵</h1>
      <p class="page-desc">从手工推演到智能对抗 — 三步递进产品路线图</p>
    </div>

    <!-- Loading 状态 -->
    <div v-if="loading" class="loading-wrapper">
      <el-icon class="loading-spinner" :size="40"><Loading /></el-icon>
      <p class="loading-text">加载产品数据中...</p>
    </div>

    <!-- 空状态 -->
    <el-empty
      v-else-if="products.length === 0"
      description="暂无产品数据"
      :image-size="120"
    >
      <el-button type="primary" @click="loadProducts">刷新</el-button>
    </el-empty>

    <template v-else>
      <!-- 递进关系流程图 — 桌面横向/移动端纵向 -->
      <div class="progression-section">
        <div class="progression-flow">
          <div
            v-for="p in products"
            :key="p.id"
            class="flow-node"
            :class="`status-${p.status}`"
          >
            <div class="flow-icon">{{ p.emoji }}</div>
            <div class="flow-name">{{ p.name }}</div>
            <div class="flow-badge">{{ p.statusLabel }}</div>
          </div>
          <!-- 连接箭头 -->
          <template v-for="i in products.length - 1" :key="`arrow-${i}`">
            <div class="flow-arrow">
              <span class="arrow-text">{{ progressionLabels[i - 1] }}</span>
              <span class="arrow-symbol">→</span>
            </div>
          </template>
        </div>

        <!-- 桌面端 el-steps 备用 -->
        <el-steps class="progression-steps" :space="200" finish-status="wait" simple>
          <el-step
            v-for="p in products"
            :key="`step-${p.id}`"
            :icon="p.emoji"
            :title="p.name"
            :description="p.positioning.split(' + ')[0]"
            :status="p.status === 'done' ? 'finish' : p.status === 'in-progress' ? 'process' : 'wait'"
          />
        </el-steps>
      </div>

      <!-- 产品卡片网格 -->
      <div class="cards-grid">
        <el-card
          v-for="product in products"
          :key="product.id"
          class="product-card"
          shadow="hover"
          :class="{ 'is-active': activeProductId === product.id }"
        >
          <!-- 卡片头部 -->
          <div class="card-header" @click="toggleProduct(product.id)">
            <div class="icon-placeholder">
              <span class="product-emoji">{{ product.emoji }}</span>
              <div class="icon-bg" :class="`bg-${product.status}`"></div>
            </div>
            <div class="card-title-area">
              <h3 class="card-title">{{ product.name }}</h3>
              <el-tag
                :type="statusType(product.status)"
                size="small"
                effect="dark"
                round
              >
                {{ product.statusLabel }}
              </el-tag>
            </div>
          </div>

          <!-- 卡片内容 -->
          <div class="card-body">
            <p class="product-positioning">{{ product.positioning }}</p>

            <!-- 整体进度 -->
            <div class="overall-progress">
              <div class="progress-header">
                <span class="progress-label">整体进度</span>
                <span class="progress-value">{{ calcOverallProgress(product.modules) }}%</span>
              </div>
              <el-progress
                :percentage="calcOverallProgress(product.modules)"
                :stroke-width="10"
                :color="progressColor(product.status)"
                :show-text="false"
              />
            </div>

            <!-- 模块列表 -->
            <div class="modules-list">
              <h4>📦 模块拆解</h4>
              <div
                v-for="mod in product.modules"
                :key="mod.name"
                class="module-item"
              >
                <span class="module-name">{{ mod.name }}</span>
                <div class="module-progress-right">
                  <span class="module-pct">{{ mod.progress }}%</span>
                  <el-progress
                    :percentage="mod.progress"
                    :stroke-width="6"
                    :status="mod.progress === 100 ? 'success' : undefined"
                    :color="statusColor(mod.status)"
                  />
                </div>
              </div>
            </div>
          </div>

          <!-- 展开详情按钮 -->
          <div class="card-footer">
            <el-button
              type="primary"
              text
              @click="toggleProduct(product.id)"
            >
              {{ activeProductId === product.id ? '收起详情 ▲' : '展开详情 ▼' }}
            </el-button>
          </div>

          <!-- 详情面板 — 展开/收起动画 -->
          <el-collapse-transition>
            <div v-show="activeProductId === product.id" class="detail-panel">
              <el-divider content-position="left">📅 里程碑</el-divider>
              <el-timeline>
                <el-timeline-item
                  v-for="(ms, idx) in product.milestones"
                  :key="idx"
                  :timestamp="ms.date"
                  :type="milestoneType(ms.status)"
                  :color="statusDotColor(ms.status)"
                  :hollow="ms.status !== 'done'"
                >
                  {{ ms.name }}
                  <el-tag size="small" :type="statusType(ms.status)" style="margin-left: 8px">
                    {{ milestoneStatusLabel(ms.status) }}
                  </el-tag>
                </el-timeline-item>
              </el-timeline>

              <el-divider />

              <div class="product-meta">
                <el-descriptions :column="1" border size="small">
                  <el-descriptions-item label="类型">{{ product.type }}</el-descriptions-item>
                  <el-descriptions-item label="负责人">{{ product.owner }}</el-descriptions-item>
                  <el-descriptions-item label="状态">
                    <el-tag :type="statusType(product.status)" size="small" round>
                      {{ product.statusLabel }}
                    </el-tag>
                  </el-descriptions-item>
                </el-descriptions>
              </div>
            </div>
          </el-collapse-transition>
        </el-card>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Loading } from '@element-plus/icons-vue'

// 状态映射
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

function progressColor(status: string): string {
  return statusColor(status)
}

function milestoneType(status: string): 'success' | 'primary' | 'info' {
  const map: Record<string, 'success' | 'primary' | 'info'> = {
    'done': 'success',
    'in-progress': 'primary',
    'planning': 'info'
  }
  return map[status] || 'info'
}

function statusDotColor(status: string): string {
  return statusColor(status)
}

function milestoneStatusLabel(status: string): string {
  const map: Record<string, string> = {
    'done': '已完成',
    'in-progress': '进行中',
    'planning': '规划中'
  }
  return map[status] || status
}

function calcOverallProgress(modules: Array<{ progress: number }>): number {
  if (!modules.length) return 0
  return Math.round(modules.reduce((sum, m) => sum + m.progress, 0) / modules.length)
}

// 产品数据
interface Module {
  name: string
  status: string
  progress: number
}

interface Milestone {
  name: string
  date: string
  status: string
}

interface Product {
  id: string
  name: string
  emoji: string
  type: string
  positioning: string
  status: string
  statusLabel: string
  owner: string
  modules: Module[]
  milestones: Milestone[]
}

const products = ref<Product[]>([])
const activeProductId = ref<string | null>(null)
const loading = ref(true)

function toggleProduct(id: string) {
  activeProductId.value = activeProductId.value === id ? null : id
}

// 递进关系标签（从 progression 读取，无则默认）
const progressionLabels = ref<string[]>([])

const localProducts: Product[] = [
  {
    id: 'manual-chess',
    name: '手工纸质兵棋',
    emoji: '📦',
    type: '实体桌游',
    positioning: '规则验证 + 教学推演 + 快速原型',
    status: 'in-progress',
    statusLabel: '原型设计中',
    owner: '待分配',
    modules: [
      { name: '规则体系设计', status: 'in-progress', progress: 40 },
      { name: '地图与棋子原型', status: 'in-progress', progress: 30 },
      { name: '教学关卡设计', status: 'planning', progress: 10 }
    ],
    milestones: [
      { name: '规则初稿完成', date: '2026-07-15', status: 'in-progress' },
      { name: '首版原型可玩', date: '2026-08-01', status: 'planning' }
    ]
  },
  {
    id: 'digital-chess',
    name: '电子化兵棋',
    emoji: '💻',
    type: '数字工具',
    positioning: '规则引擎自动化 + 界面交互 + 多人在线',
    status: 'in-progress',
    statusLabel: '原型设计中',
    owner: '待分配',
    modules: [
      { name: '规则引擎', status: 'planning', progress: 10 },
      { name: '交互界面', status: 'planning', progress: 5 },
      { name: '多人在线同步', status: 'planning', progress: 0 }
    ],
    milestones: [
      { name: '规则引擎 MVP', date: '2026-09-01', status: 'planning' },
      { name: 'Alpha 版内测', date: '2026-10-15', status: 'planning' }
    ]
  },
  {
    id: 'ai-chess',
    name: '智能兵棋',
    emoji: '🤖',
    type: 'AI 对抗',
    positioning: '智能体参与推演 + AI 辅助决策 + RL 训练',
    status: 'planning',
    statusLabel: '规划中',
    owner: '待分配',
    modules: [
      { name: 'AI 决策框架', status: 'planning', progress: 0 },
      { name: '智能体接入', status: 'planning', progress: 0 },
      { name: 'RL 训练管线', status: 'planning', progress: 0 }
    ],
    milestones: [
      { name: '技术方案评审', date: '2026-10-01', status: 'planning' },
      { name: '首个 AI 对手上线', date: '2026-12-01', status: 'planning' }
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
      if (data.progression) {
        progressionLabels.value = data.progression.map((p: any) => p.label || '')
      }
    } else {
      products.value = localProducts
      progressionLabels.value = ['自动裁决', '智能对抗']
    }
  } catch {
    products.value = localProducts
    progressionLabels.value = ['自动裁决', '智能对抗']
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadProducts()
})
</script>

<style scoped>
.products-page {
  max-width: 1200px;
  margin: 0 auto;
}

/* 页面标题 */
.page-header {
  margin-bottom: 24px;
}

.page-header h1 {
  font-size: 24px;
  font-weight: 600;
  color: #1d1e2c;
  margin: 0 0 8px;
}

.page-desc {
  font-size: 14px;
  color: #909399;
  margin: 0;
}

/* Loading 状态 */
.loading-wrapper {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
}

.loading-spinner {
  animation: spin 1s linear infinite;
  color: #409eff;
}

.loading-text {
  margin-top: 12px;
  font-size: 14px;
  color: #909399;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* 递进关系流程图 */
.progression-section {
  margin-bottom: 32px;
  padding: 24px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

/* 自定义流程节点（桌面端默认隐藏，小屏显示） */
.progression-flow {
  display: none;
}

@media (max-width: 768px) {
  .progression-steps {
    display: none;
  }
  .progression-flow {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: center;
    gap: 8px;
  }
  .flow-node {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 12px 16px;
    border-radius: 8px;
    background: #f5f7fa;
    border: 1px solid #e4e7ed;
    transition: background 0.2s;
    min-width: 100px;
  }
  .flow-node.status-in-progress {
    background: #fdf6ec;
    border-color: #e6a23c55;
  }
  .flow-node.status-planning {
    background: #ecf5ff;
    border-color: #409eff55;
  }
  .flow-node.status-done {
    background: #f0f9eb;
    border-color: #67c23a55;
  }
  .flow-icon {
    font-size: 28px;
    margin-bottom: 4px;
  }
  .flow-name {
    font-size: 13px;
    font-weight: 500;
    color: #303133;
    text-align: center;
  }
  .flow-badge {
    font-size: 11px;
    color: #909399;
    margin-top: 2px;
  }
  .flow-arrow {
    display: flex;
    flex-direction: column;
    align-items: center;
    color: #c0c4cc;
  }
  .arrow-symbol {
    font-size: 20px;
    color: #409eff;
  }
  .arrow-text {
    font-size: 10px;
    color: #909399;
    margin-bottom: 2px;
  }
}

.progression-steps :deep(.el-step__title) {
  font-size: 14px;
  font-weight: 500;
}

.progression-steps :deep(.el-step__description) {
  font-size: 12px;
}

/* 卡片网格 — 响应式 */
.cards-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
}

@media (max-width: 1024px) {
  .cards-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 640px) {
  .cards-grid {
    grid-template-columns: 1fr;
  }
}

/* 产品卡片 */
.product-card {
  border-radius: 12px;
  transition: transform 0.25s ease, box-shadow 0.25s ease;
  cursor: pointer;
  overflow: hidden;
}

.product-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
}

.product-card.is-active {
  box-shadow: 0 4px 16px rgba(64, 158, 255, 0.25);
  border-color: #409eff;
}

/* 卡片头部 — 图标占位 */
.card-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.icon-placeholder {
  position: relative;
  width: 52px;
  height: 52px;
  border-radius: 12px;
  overflow: hidden;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.icon-bg {
  position: absolute;
  inset: 0;
  opacity: 0.12;
  transition: opacity 0.2s;
}

.product-card:hover .icon-bg {
  opacity: 0.18;
}

.bg-in-progress { background: linear-gradient(135deg, #e6a23c, #f5c178); }
.bg-planning { background: linear-gradient(135deg, #409eff, #79bbff); }
.bg-done { background: linear-gradient(135deg, #67c23a, #95d475); }

.product-emoji {
  font-size: 28px;
  position: relative;
  z-index: 1;
}

.card-title-area {
  flex: 1;
}

.card-title {
  font-size: 16px;
  font-weight: 600;
  color: #1d1e2c;
  margin: 0 0 6px;
}

.card-body {
  margin-top: 12px;
}

.product-positioning {
  font-size: 13px;
  color: #606266;
  margin: 0 0 16px;
  line-height: 1.5;
}

/* 整体进度 */
.overall-progress {
  margin-bottom: 16px;
}

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.progress-label {
  font-size: 12px;
  color: #909399;
}

.progress-value {
  font-size: 12px;
  font-weight: 600;
  color: #303133;
}

/* 模块列表 */
.modules-list h4 {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  margin: 0 0 12px;
}

.module-item {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.module-name {
  font-size: 12px;
  color: #606266;
  min-width: 90px;
  flex-shrink: 0;
}

.module-progress-right {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
}

.module-pct {
  font-size: 11px;
  color: #909399;
  min-width: 32px;
  text-align: right;
}

/* 卡片底部 */
.card-footer {
  margin-top: 16px;
  text-align: center;
}

/* 详情面板 */
.detail-panel {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #ebeef5;
}

.product-meta {
  margin-top: 12px;
}

/* 详情面板动画 */
.detail-panel {
  animation: fadeIn 0.25s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(-8px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
