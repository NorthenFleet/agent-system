<template>
  <div class="products-page" v-loading="loading">
    <header class="page-head">
      <div>
        <h2>产品矩阵</h2>
        <span>{{ registry?.updated_at ? `更新于 ${formatTime(registry.updated_at)}` : '产品注册表' }}</span>
      </div>
      <el-tooltip content="刷新产品状态" placement="bottom">
        <el-button :icon="Refresh" :loading="loading" aria-label="刷新产品状态" @click="loadProducts" />
      </el-tooltip>
    </header>

    <section class="registry-metrics" aria-label="产品注册统计">
      <div><span>产品</span><strong>{{ registry?.summary.total || 0 }}</strong></div>
      <div><span>在线系统</span><strong>{{ registry?.summary.online || 0 }}</strong></div>
      <div><span>离线系统</span><strong>{{ registry?.summary.offline || 0 }}</strong></div>
      <div><span>项目绑定</span><strong>{{ registry?.summary.project_bindings || 0 }}</strong></div>
    </section>

    <section v-if="projectContextId" class="project-binding-band">
      <div>
        <span>当前项目</span>
        <strong>{{ currentProject?.name || projectContextId }}</strong>
        <small v-if="selectedProduct">
          {{ bindingForSelected ? `${roleLabel(bindingForSelected.role)} · 已绑定` : `尚未使用 ${selectedProduct.name}` }}
        </small>
      </div>
      <div class="binding-actions">
        <el-button text @click="openProject(projectContextId)">返回项目</el-button>
        <el-button
          v-if="selectedProduct?.id !== 'openclaw-3021'"
          :type="bindingForSelected ? 'danger' : 'primary'"
          :plain="Boolean(bindingForSelected)"
          :loading="bindingProduct"
          @click="toggleSelectedBinding"
        >
          {{ bindingForSelected ? '解除绑定' : '绑定到项目' }}
        </el-button>
        <el-tag v-else effect="plain">宿主平台</el-tag>
      </div>
    </section>

    <section v-if="coreProducts.length" class="dependency-band">
      <div class="section-head">
        <h3>核心运行链</h3>
        <el-tag effect="plain">{{ registry?.dependencies.length || 0 }} 项依赖</el-tag>
      </div>
      <div class="core-chain">
        <template v-for="(product, index) in coreProducts" :key="product.id">
          <button type="button" class="chain-product" @click="selectProduct(product)">
            <span>{{ kindLabel(product.kind) }}</span>
            <strong>{{ product.name }}</strong>
            <small>{{ product.runtime?.summary || statusLabel(product.status) }}</small>
          </button>
          <span v-if="index < coreProducts.length - 1" class="chain-arrow">→</span>
        </template>
      </div>
    </section>

    <main class="registry-layout">
      <section class="product-list">
        <div class="section-head">
          <h3>产品目录</h3>
          <el-segmented v-model="kindFilter" :options="kindOptions" size="small" />
        </div>
        <div class="product-grid" role="list" aria-label="产品卡片列表">
          <button
            v-for="product in filteredProducts"
            :key="product.id"
            type="button"
            class="product-card"
            :class="{ selected: selectedProduct?.id === product.id }"
            role="listitem"
            @click="selectProduct(product)"
          >
            <header>
              <span class="product-kind">{{ kindLabel(product.kind) }}</span>
              <el-tag :type="runtimeTagType(product.runtime?.state)" effect="plain" size="small">
                {{ runtimeLabel(product.runtime?.state) }}
              </el-tag>
            </header>
            <div class="product-card-title">
              <strong>{{ product.name }}</strong>
              <small>{{ product.version || '未标版本' }} · {{ product.owner || '未分配负责人' }}</small>
            </div>
            <p>{{ product.description || '尚未补充产品说明。' }}</p>
            <dl class="product-card-stats">
              <div><dt>关联项目</dt><dd>{{ product.usage_count || 0 }}</dd></div>
              <div><dt>有效交付</dt><dd>{{ product.delivery_summary?.accepted || 0 }}</dd></div>
              <div><dt>待验收</dt><dd>{{ product.delivery_summary?.pending_review || 0 }}</dd></div>
            </dl>
            <footer>
              <span>{{ product.current_release ? `当前版本 ${product.current_release.version}` : '尚无发布版本' }}</span>
              <span>{{ product.runtime?.summary || statusLabel(product.status) }}</span>
            </footer>
          </button>
        </div>
      </section>

      <aside v-if="selectedProduct" class="product-detail">
        <header>
          <div>
            <span>{{ selectedProduct.category }}</span>
            <h3>{{ selectedProduct.name }}</h3>
          </div>
          <el-tag :type="runtimeTagType(selectedProduct.runtime?.state)" effect="plain">
            {{ runtimeLabel(selectedProduct.runtime?.state) }}
          </el-tag>
        </header>
        <p>{{ selectedProduct.description }}</p>

        <dl class="product-facts">
          <div><dt>产品标识</dt><dd>{{ selectedProduct.id }}</dd></div>
          <div><dt>版本</dt><dd>{{ selectedProduct.version || '未标版本' }}</dd></div>
          <div><dt>负责人</dt><dd>{{ selectedProduct.owner || '未分配' }}</dd></div>
          <div><dt>运行模式</dt><dd>{{ deploymentModeLabel(selectedProduct.deployment?.mode) }}</dd></div>
        </dl>

        <section>
          <h4>能力</h4>
          <div class="tag-list">
            <el-tag v-for="capability in selectedProduct.capabilities" :key="capability" effect="plain" size="small">
              {{ capability }}
            </el-tag>
          </div>
        </section>

        <section>
          <h4>依赖</h4>
          <div v-if="selectedProduct.dependencies?.length" class="detail-list">
            <div v-for="dependency in selectedProduct.dependencies" :key="dependency.product_id">
              <strong>{{ productName(dependency.product_id) }}</strong>
              <small>{{ dependencyTypeLabel(dependency.type) }}</small>
            </div>
          </div>
          <span v-else class="empty-inline">无产品依赖</span>
        </section>

        <section>
          <h4>项目引用</h4>
          <div v-if="selectedProduct.project_references?.length" class="detail-list">
            <button
              v-for="reference in selectedProduct.project_references"
              :key="reference.project_id"
              type="button"
              @click="openProject(reference.project_id)"
            >
              <strong>{{ reference.project_name }}</strong>
              <small>{{ roleLabel(reference.role) }} · {{ reference.status }}</small>
            </button>
          </div>
          <span v-else class="empty-inline">尚未绑定项目</span>
        </section>

        <section>
          <h4>交付物</h4>
          <div v-if="deliverables.length" class="detail-list">
            <div v-for="deliverable in deliverables" :key="deliverable.id">
              <strong>{{ deliverable.title }}</strong>
              <small>
                {{ deliverableKindLabel(deliverable.kind) }} ·
                {{ deliverableStatusLabel(deliverable.status) }} ·
                {{ formatTime(deliverable.created_at || '') }}
              </small>
            </div>
          </div>
          <span v-else class="empty-inline">该产品尚未登记交付物</span>
        </section>

        <section>
          <h4>发布记录</h4>
          <div v-if="releases.length" class="detail-list">
            <div v-for="release in releases" :key="release.id">
              <strong>{{ release.version }}</strong>
              <small>{{ release.environment }} · {{ release.status }}</small>
            </div>
          </div>
          <span v-else class="empty-inline">尚未发布</span>
        </section>
      </aside>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { getProjects, type Project } from '@/api/projects'
import {
  bindProductToProject,
  getProductDeliverables,
  getProductReleases,
  getProductRegistry,
  unbindProductFromProject,
  type ProductDeliverable,
  type ProjectProductBinding,
  type ProductRelease,
  type RegisteredProduct,
  type ProductRegistryResponse
} from '@/api/products'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const bindingProduct = ref(false)
const registry = ref<ProductRegistryResponse>()
const selectedProduct = ref<RegisteredProduct>()
const deliverables = ref<ProductDeliverable[]>([])
const releases = ref<ProductRelease[]>([])
const currentProject = ref<Project>()
const kindFilter = ref('all')
const kindOptions = [
  { label: '全部', value: 'all' },
  { label: '运行系统', value: 'runtime' },
  { label: '业务产品', value: 'offering' }
]

const filteredProducts = computed(() => {
  const products = registry.value?.products || []
  if (kindFilter.value === 'offering') return products.filter(row => row.kind === 'offering')
  if (kindFilter.value === 'runtime') return products.filter(row => row.kind !== 'offering')
  return products
})
const coreProducts = computed(() => {
  const order = ['openclaw-3021', 'ai-planning-5130', 'one-sim']
  return order.map(id => registry.value?.products.find(row => row.id === id)).filter(Boolean) as RegisteredProduct[]
})
const projectContextId = computed(() => String(route.query.project_id || ''))
const bindingForSelected = computed<ProjectProductBinding | undefined>(() => {
  if (!selectedProduct.value) return undefined
  return currentProject.value?.product_bindings?.find(binding => binding.product_id === selectedProduct.value?.id)
})

async function loadProducts() {
  loading.value = true
  try {
    const [nextRegistry, projectResult] = await Promise.all([
      getProductRegistry(),
      projectContextId.value ? getProjects() : Promise.resolve(undefined)
    ])
    registry.value = nextRegistry
    currentProject.value = projectResult?.projects.find(project => project.id === projectContextId.value)
    const currentId = selectedProduct.value?.id || String(route.query.product_id || '') || 'openclaw-3021'
    selectedProduct.value = registry.value.products.find(row => row.id === currentId) || registry.value.products[0]
    if (selectedProduct.value) await loadProductEvidence(selectedProduct.value.id)
  } catch {
    ElMessage.error('产品注册表加载失败')
  } finally {
    loading.value = false
  }
}

async function selectProduct(product: RegisteredProduct) {
  selectedProduct.value = product
  await loadProductEvidence(product.id)
}

async function loadProductEvidence(productId: string) {
  try {
    const [nextDeliverables, nextReleases] = await Promise.all([
      getProductDeliverables(productId),
      getProductReleases(productId)
    ])
    deliverables.value = nextDeliverables.slice(0, 6)
    releases.value = nextReleases.slice(0, 4)
  } catch {
    deliverables.value = []
    releases.value = []
  }
}

function openProject(projectId: string) {
  router.push({ path: '/projects', query: { project_id: projectId } })
}

function defaultBindingRole(productId: string) {
  if (productId === 'ai-planning-5130') return 'planner'
  if (productId === 'one-sim') return 'simulator'
  return 'uses'
}

async function toggleSelectedBinding() {
  if (!projectContextId.value || !selectedProduct.value || !currentProject.value) return
  bindingProduct.value = true
  try {
    if (bindingForSelected.value) {
      await ElMessageBox.confirm(
        `解除“${currentProject.value.name}”与“${selectedProduct.value.name}”的绑定？已有产品数据不会被删除。`,
        '解除产品绑定',
        { type: 'warning', confirmButtonText: '解除绑定', cancelButtonText: '取消' }
      )
      const result = await unbindProductFromProject(projectContextId.value, selectedProduct.value.id)
      currentProject.value = result.project
      ElMessage.success('产品绑定已解除')
    } else {
      const result = await bindProductToProject(projectContextId.value, selectedProduct.value.id, {
        role: defaultBindingRole(selectedProduct.value.id),
        status: 'bound'
      })
      currentProject.value = result.project
      ElMessage.success('产品已绑定到项目')
    }
    await loadProducts()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error('产品绑定更新失败')
  } finally {
    bindingProduct.value = false
  }
}

function productName(productId: string) {
  return registry.value?.products.find(row => row.id === productId)?.name || productId
}

function kindLabel(kind?: string) {
  return ({ platform: '平台', service: '规划服务', simulation: '仿真系统', offering: '业务产品' } as Record<string, string>)[kind || ''] || kind || '产品'
}

function statusLabel(status?: string) {
  return ({ active: '运行中', developing: '开发中', planning: '规划中' } as Record<string, string>)[status || ''] || status || '未知'
}

function runtimeLabel(state?: string) {
  return ({ online: '在线', offline: '离线', managed: '受管' } as Record<string, string>)[state || ''] || '未知'
}

function runtimeTagType(state?: string): 'success' | 'danger' | 'info' {
  if (state === 'online') return 'success'
  if (state === 'offline') return 'danger'
  return 'info'
}

function deploymentModeLabel(mode?: string) {
  return ({ standalone: '独立部署', 'embedded-planning-situation': '内嵌态势会话', physical: '实体产品', planned: '待部署' } as Record<string, string>)[mode || ''] || mode || '未登记'
}

function dependencyTypeLabel(type?: string) {
  return ({ runtime: '运行时依赖', engine: '引擎依赖', planning: '规划能力', simulation: '仿真能力' } as Record<string, string>)[type || ''] || type || '依赖'
}

function roleLabel(role?: string) {
  return ({ planner: '规划器', simulator: '仿真器', uses: '使用' } as Record<string, string>)[role || ''] || role || '使用'
}

function deliverableKindLabel(kind?: string) {
  return ({ source_code: '代码', service: '服务', document: '文档', model: '模型', dataset: '数据集', scenario: '想定', report: '报告' } as Record<string, string>)[kind || ''] || kind || '交付物'
}

function deliverableStatusLabel(status?: string) {
  return ({ draft: '待验收', accepted: '已验收', rejected: '已退回' } as Record<string, string>)[status || ''] || status || '未知'
}

function formatTime(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}

onMounted(loadProducts)
</script>

<style scoped>
.products-page {
  display: grid;
  gap: 18px;
  min-width: 0;
}

.page-head,
.section-head,
.product-detail > header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.page-head h2,
.page-head span,
.section-head h3,
.product-detail h3,
.product-detail h4,
.product-detail p {
  margin: 0;
}

.page-head h2 {
  color: var(--text-primary);
  font-size: 18px;
}

.page-head span,
.chain-product span,
.chain-product small,
.product-cell small,
.runtime-cell small,
.deployment-cell small,
.product-detail header span,
.detail-list small,
.empty-inline {
  color: var(--text-secondary);
  font-size: 11px;
}

.registry-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  border-top: 1px solid var(--line-color);
  border-bottom: 1px solid var(--line-color);
}

.registry-metrics > div {
  display: grid;
  gap: 4px;
  padding: 10px 12px;
  border-right: 1px solid var(--line-color);
}

.registry-metrics > div:last-child {
  border-right: 0;
}

.registry-metrics span {
  color: var(--text-secondary);
  font-size: 11px;
}

.registry-metrics strong {
  color: var(--text-primary);
  font-size: 20px;
}

.dependency-band,
.project-binding-band,
.product-list,
.product-detail {
  min-width: 0;
  padding: 14px;
  border: 1px solid var(--line-color);
  border-radius: 6px;
  background: var(--card-bg);
}

.project-binding-band {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.project-binding-band > div:first-child {
  display: grid;
  gap: 3px;
}

.project-binding-band span,
.project-binding-band small {
  color: var(--text-secondary);
  font-size: 11px;
}

.project-binding-band strong {
  color: var(--text-primary);
  font-size: 14px;
}

.binding-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
}

.section-head {
  margin-bottom: 12px;
}

.section-head h3,
.product-detail h3 {
  color: var(--text-primary);
  font-size: 14px;
}

.core-chain {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr) auto minmax(0, 1fr);
  gap: 10px;
  align-items: center;
}

.chain-product {
  display: grid;
  gap: 4px;
  min-width: 0;
  padding: 8px 10px;
  border: 0;
  border-left: 2px solid var(--view-color-border);
  color: inherit;
  text-align: left;
  background: transparent;
  cursor: pointer;
}

.chain-product:hover {
  background: var(--view-color-faint);
}

.chain-product strong,
.chain-product small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chain-product strong {
  color: var(--text-primary);
  font-size: 13px;
}

.chain-arrow {
  color: var(--text-secondary);
}

.registry-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(270px, 340px);
  gap: 14px;
  align-items: start;
}

.product-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.product-card {
  display: grid;
  min-height: 224px;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--line-color);
  border-radius: 6px;
  color: inherit;
  text-align: left;
  background: color-mix(in srgb, var(--card-bg) 92%, var(--view-color-faint));
  box-shadow: 0 7px 20px rgb(0 0 0 / 8%);
  cursor: pointer;
  transition: transform 160ms ease, border-color 160ms ease, box-shadow 160ms ease;
}

.product-card:hover {
  transform: translateY(-2px);
  border-color: var(--view-color-border);
  box-shadow: 0 12px 24px rgb(0 0 0 / 13%);
}

.product-card.selected {
  border-color: var(--view-color-border);
  box-shadow: inset 0 0 0 1px var(--view-color-border), 0 12px 24px rgb(0 0 0 / 13%);
}

.product-card > header,
.product-card > footer,
.product-card-stats {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.product-kind,
.product-card-title small,
.product-card p,
.product-card footer,
.product-card-stats dt,
.delivery-highlight small {
  color: var(--text-secondary);
  font-size: 11px;
}

.product-kind {
  padding-left: 8px;
  border-left: 2px solid var(--view-color-border);
}

.product-card-title {
  display: grid;
  gap: 5px;
}

.product-card-title strong {
  color: var(--text-primary);
  font-size: 15px;
}

.product-card p {
  min-height: 34px;
  margin: 0;
  line-height: 1.5;
}

.product-card-stats {
  margin: auto 0 0;
  padding: 9px 0;
  border-top: 1px solid var(--line-color);
  border-bottom: 1px solid var(--line-color);
}

.product-card-stats > div {
  display: grid;
  gap: 4px;
}

.product-card-stats dd {
  margin: 0;
  color: var(--text-primary);
  font-size: 16px;
  font-weight: 600;
}

.product-card > footer {
  align-items: flex-start;
}

.product-card > footer > span:last-child {
  max-width: 55%;
  overflow: hidden;
  text-align: right;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.product-cell,
.runtime-cell,
.deployment-cell {
  display: grid;
  gap: 3px;
}

.product-cell strong,
.product-detail h4,
.detail-list strong {
  color: var(--text-primary);
}

.runtime-cell {
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
}

.runtime-cell small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.product-detail {
  display: grid;
  gap: 16px;
  position: sticky;
  top: 14px;
}

.product-detail p {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.6;
}

.product-detail section {
  display: grid;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid var(--line-color);
}

.product-detail h4 {
  font-size: 12px;
}

.product-facts {
  display: grid;
  margin: 0;
}

.product-facts > div {
  display: grid;
  grid-template-columns: 76px minmax(0, 1fr);
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px solid var(--line-color);
  font-size: 11px;
}

.product-facts dt {
  color: var(--text-secondary);
}

.product-facts dd {
  min-width: 0;
  margin: 0;
  overflow-wrap: anywhere;
  color: var(--text-primary);
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.detail-list {
  display: grid;
}

.detail-list > div,
.detail-list > button {
  display: grid;
  gap: 3px;
  padding: 7px 0;
  border: 0;
  border-bottom: 1px solid var(--line-color);
  color: inherit;
  text-align: left;
  background: transparent;
}

.detail-list > button {
  cursor: pointer;
}

.detail-list > button:hover {
  background: var(--view-color-faint);
}

.delivery-highlight {
  display: grid;
  gap: 4px;
  padding: 10px;
  border-left: 2px solid var(--view-color-border);
  background: var(--view-color-faint);
}

.delivery-highlight strong {
  color: var(--text-primary);
  font-size: 12px;
}

@media (max-width: 980px) {
  .registry-layout {
    grid-template-columns: 1fr;
  }

  .product-detail {
    position: static;
  }
}

@media (max-width: 720px) {
  .registry-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .registry-metrics > div:nth-child(2) {
    border-right: 0;
  }

  .core-chain {
    grid-template-columns: 1fr;
  }

  .chain-arrow {
    display: none;
  }

  .section-head {
    align-items: flex-start;
    flex-direction: column;
  }

  .project-binding-band {
    align-items: flex-start;
    flex-direction: column;
  }

  .product-grid {
    grid-template-columns: 1fr;
  }
}
</style>
