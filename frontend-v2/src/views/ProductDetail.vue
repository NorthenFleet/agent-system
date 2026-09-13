<template>
  <div class="product-detail-page" v-loading="loading">
    <header class="detail-head">
      <el-button text :icon="ArrowLeft" @click="router.push('/products')">产品矩阵</el-button>
      <div v-if="product" class="head-actions">
        <el-tag :type="runtimeTagType(product.runtime?.state)" effect="plain">{{ runtimeLabel(product.runtime?.state) }}</el-tag>
        <el-button type="primary" :icon="Refresh" :loading="loading" @click="loadProduct">刷新</el-button>
      </div>
    </header>

    <el-empty v-if="!loading && !product" description="未找到产品" />

    <template v-if="product">
      <section class="identity-band">
        <div class="identity-visual" :style="coverStyle(product)">
          <span>{{ product.short_name || product.name.slice(0, 10) }}</span>
        </div>
        <div class="identity-copy">
          <span>{{ product.category || kindLabel(product.kind) }}</span>
          <h2>{{ product.name }}</h2>
          <p>{{ product.positioning || product.description || '尚未补充产品定位。' }}</p>
          <div class="identity-tags">
            <el-tag effect="plain">{{ kindLabel(product.kind) }}</el-tag>
            <el-tag effect="plain">{{ statusLabel(product.status) }}</el-tag>
            <el-tag v-if="product.owner" effect="plain">负责人 {{ product.owner }}</el-tag>
            <el-tag v-if="product.version" effect="plain">版本 {{ product.version }}</el-tag>
          </div>
        </div>
      </section>

      <main class="detail-layout">
        <section class="detail-main">
          <section class="detail-section">
            <h3>系统介绍</h3>
            <p>{{ product.description || '尚未登记系统介绍。' }}</p>
            <div class="tag-list">
              <el-tag v-for="capability in product.capabilities || []" :key="capability" effect="plain" size="small">{{ capability }}</el-tag>
              <span v-if="!(product.capabilities || []).length" class="empty-inline">尚未登记能力标签</span>
            </div>
          </section>

          <section class="detail-section detail-two-col">
            <div>
              <h3>目标用户</h3>
              <div class="pill-grid">
                <span v-for="user in product.target_users || []" :key="user">{{ user }}</span>
                <span v-if="!(product.target_users || []).length" class="empty-inline">尚未登记目标用户</span>
              </div>
            </div>
            <div>
              <h3>价值说明</h3>
              <ul v-if="product.value_props?.length" class="value-list">
                <li v-for="value in product.value_props" :key="value">{{ value }}</li>
              </ul>
              <span v-else class="empty-inline">尚未登记价值说明</span>
            </div>
          </section>

          <section class="detail-section">
            <h3>应用场景</h3>
            <div class="pill-grid">
              <span v-for="scenario in product.scenarios || []" :key="scenario">{{ scenario }}</span>
              <span v-if="!(product.scenarios || []).length" class="empty-inline">尚未登记场景</span>
            </div>
          </section>

          <section class="detail-section">
            <h3>图片与视频</h3>
            <div v-if="mediaItems.length" class="media-grid">
              <article v-for="item in mediaItems" :key="item.uri">
                <video v-if="item.kind === 'video'" :src="item.objectUrl" controls preload="metadata"></video>
                <img v-else :src="item.objectUrl" :alt="item.title" />
                <div>
                  <strong>{{ item.title }}</strong>
                  <small>{{ item.caption || item.source || '产品运行素材' }}</small>
                </div>
              </article>
            </div>
            <span v-else class="empty-inline">尚未登记图片或视频素材</span>
          </section>

          <section class="detail-section">
            <h3>产品规划书与交付物</h3>
            <div v-if="documentDeliverables.length || deliverables.length" class="evidence-list">
              <article v-for="deliverable in visibleDeliverables" :key="deliverable.id">
                <div>
                  <strong>{{ deliverable.title }}</strong>
                  <small>{{ deliverableKindLabel(deliverable.kind) }} · {{ deliverableStatusLabel(deliverable.status) }}{{ deliverable.version ? ` · ${deliverable.version}` : '' }}</small>
                  <p v-if="deliverable.summary">{{ deliverable.summary }}</p>
                </div>
                <button v-if="deliverable.uri" type="button" @click="openDeliverable(deliverable)">打开</button>
              </article>
            </div>
            <span v-else class="empty-inline">尚未登记产品规划书或交付物</span>
          </section>

          <section class="detail-section">
            <h3>依赖关系</h3>
            <div v-if="product.dependencies?.length" class="dependency-list">
              <article v-for="dependency in product.dependencies" :key="`${dependency.product_id}-${dependency.type}`">
                <strong>{{ dependency.product_id }}</strong>
                <small>{{ dependency.type }}{{ dependency.description ? ` · ${dependency.description}` : '' }}</small>
              </article>
            </div>
            <span v-else class="empty-inline">无登记依赖</span>
          </section>
        </section>

        <aside class="detail-side">
          <section class="detail-section">
            <h3>系统链接</h3>
            <div v-if="systemLinks.length" class="link-list">
              <a v-for="link in systemLinks" :key="`${link.label}-${link.url}`" :href="link.url" target="_blank" rel="noreferrer">
                <LinkIcon />
                <span>{{ link.label }}</span>
              </a>
            </div>
            <span v-else class="empty-inline">尚未登记链接</span>
          </section>

          <section class="detail-section">
            <h3>运行实例</h3>
            <div v-if="runtimeInstances.length" class="compact-list">
              <article v-for="runtime in runtimeInstances" :key="runtime.id">
                <strong>{{ runtime.name }}</strong>
                <small>{{ runtime.environment }} · {{ runtimeLabel(runtime.state) }}{{ runtime.public_url ? ` · ${runtime.public_url}` : '' }}</small>
              </article>
            </div>
            <span v-else class="empty-inline">尚未登记运行实例</span>
          </section>

          <section class="detail-section">
            <h3>发布记录</h3>
            <div v-if="releases.length" class="compact-list">
              <article v-for="release in releases" :key="release.id">
                <strong>{{ release.version }}</strong>
                <small>{{ release.environment }} · {{ releaseStatusLabel(release.status) }}</small>
              </article>
            </div>
            <span v-else class="empty-inline">尚未发布</span>
          </section>

          <section class="detail-section">
            <h3>最近活动</h3>
            <div v-if="timeline.length" class="compact-list">
              <article v-for="event in timeline" :key="event.id">
                <strong>{{ eventLabel(event.event_type) }}</strong>
                <small>{{ formatTime(event.created_at || '') }}</small>
              </article>
            </div>
            <span v-else class="empty-inline">暂无活动</span>
          </section>
        </aside>
      </main>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, Link as LinkIcon, Refresh } from '@element-plus/icons-vue'
import {
  getProduct,
  getProductDeliverables,
  downloadProductAsset,
  getProductReleases,
  getProductRuntimeInstances,
  getProductTimeline,
  type ProductDeliverable,
  type ProductEvent,
  type ProductMediaAsset,
  type ProductRelease,
  type ProductRuntimeInstance,
  type ProductSystemLink,
  type RegisteredProduct
} from '@/api/products'

const props = defineProps<{ productId: string }>()
const router = useRouter()
const loading = ref(false)
const product = ref<RegisteredProduct>()
const deliverables = ref<ProductDeliverable[]>([])
const releases = ref<ProductRelease[]>([])
const runtimeInstances = ref<ProductRuntimeInstance[]>([])
const timeline = ref<ProductEvent[]>([])
const coverUrl = ref('')
const mediaItems = ref<Array<ProductMediaAsset & { objectUrl: string; kind: 'image' | 'video' }>>([])

const documentDeliverables = computed(() => deliverables.value.filter(row => row.kind === 'document'))
const visibleDeliverables = computed(() => [...documentDeliverables.value, ...deliverables.value.filter(row => row.kind !== 'document')].slice(0, 12))
const systemLinks = computed<ProductSystemLink[]>(() => {
  if (!product.value) return []
  const links: ProductSystemLink[] = [...(product.value.system_links || [])]
  if (product.value.deployment?.public_url) links.push({ label: '运行入口', url: product.value.deployment.public_url, kind: 'runtime' })
  if (product.value.deployment?.health_url) links.push({ label: '健康检查', url: product.value.deployment.health_url, kind: 'health' })
  if (product.value.repository) links.push({ label: '代码仓库', url: product.value.repository, kind: 'repository' })
  return links.filter((link, index, array) => link.url && array.findIndex(row => row.url === link.url) === index)
})

async function loadProduct() {
  loading.value = true
  try {
    const [nextProduct, nextDeliverables, nextReleases, nextRuntimes, nextTimeline] = await Promise.all([
      getProduct(props.productId),
      getProductDeliverables(props.productId),
      getProductReleases(props.productId),
      getProductRuntimeInstances(props.productId),
      getProductTimeline(props.productId)
    ])
    product.value = nextProduct
    deliverables.value = nextDeliverables
    releases.value = nextReleases
    runtimeInstances.value = nextRuntimes
    timeline.value = nextTimeline
    await loadCover(nextProduct)
    await loadMedia(nextProduct)
  } finally {
    loading.value = false
  }
}

function coverStyle(row: RegisteredProduct) {
  if (coverUrl.value) return { backgroundImage: `url("${coverUrl.value}")` }
  const swatches: Record<string, string> = {
    platform: 'linear-gradient(135deg, #10233f, #21605e)',
    service: 'linear-gradient(135deg, #1f3b4d, #2d6f99)',
    simulation: 'linear-gradient(135deg, #24351f, #5f7b3a)',
    offering: 'linear-gradient(135deg, #423022, #8b6440)'
  }
  return { backgroundImage: swatches[row.kind] || 'linear-gradient(135deg, #263241, #59616f)' }
}

async function loadCover(row: RegisteredProduct) {
  if (coverUrl.value) URL.revokeObjectURL(coverUrl.value)
  coverUrl.value = ''
  if (!row.cover_image) return
  try {
    const blob = await downloadProductAsset(row.cover_image)
    coverUrl.value = URL.createObjectURL(blob)
  } catch {
    coverUrl.value = ''
  }
}

async function loadMedia(row: RegisteredProduct) {
  mediaItems.value.forEach(item => URL.revokeObjectURL(item.objectUrl))
  mediaItems.value = []
  const loaded = await Promise.all((row.media_assets || []).map(async (asset) => {
    if (!asset.uri) return null
    try {
      const blob = await downloadProductAsset(asset.uri)
      const kind = asset.kind || (blob.type.startsWith('video/') ? 'video' : 'image')
      return { ...asset, kind, objectUrl: URL.createObjectURL(blob) }
    } catch {
      return null
    }
  }))
  mediaItems.value = loaded.filter((item): item is ProductMediaAsset & { objectUrl: string; kind: 'image' | 'video' } => Boolean(item))
}

async function openDeliverable(deliverable: ProductDeliverable) {
  if (!deliverable.uri) return
  if (/^https?:\/\//.test(deliverable.uri)) {
    window.open(deliverable.uri, '_blank', 'noopener,noreferrer')
    return
  }
  const blob = await downloadProductAsset(deliverable.uri)
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = decodeURIComponent(deliverable.uri.split('/').pop() || deliverable.title || 'product-deliverable')
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
function kindLabel(kind?: string) { return ({ platform: '平台', service: '规划服务', simulation: '仿真系统', offering: '业务产品' } as Record<string, string>)[kind || ''] || kind || '产品' }
function statusLabel(status?: string) { return ({ active: '运行中', developing: '开发中', planning: '规划中', archived: '已归档' } as Record<string, string>)[status || ''] || status || '未知' }
function runtimeLabel(state?: string) { return ({ pending: '待部署', deploying: '部署中', online: '在线', degraded: '降级', offline: '离线', failed: '失败', stopped: '已停止', managed: '受管' } as Record<string, string>)[state || ''] || '未知' }
function runtimeTagType(state?: string): 'success' | 'danger' | 'warning' | 'info' { if (state === 'online') return 'success'; if (state === 'offline' || state === 'failed') return 'danger'; if (state === 'degraded' || state === 'deploying') return 'warning'; return 'info' }
function deliverableKindLabel(kind?: string) { return ({ source_code: '代码', service: '服务', document: '文档', model: '模型', dataset: '数据集', scenario: '想定', report: '报告' } as Record<string, string>)[kind || ''] || kind || '交付物' }
function deliverableStatusLabel(status?: string) { return ({ draft: '待验收', accepted: '已验收', rejected: '已退回' } as Record<string, string>)[status || ''] || status || '未知' }
function releaseStatusLabel(status?: string) { return ({ pending: '待发布', deploying: '部署中', active: '已生效', failed: '发布失败', rolled_back: '已回滚' } as Record<string, string>)[status || ''] || status || '未知' }
function eventLabel(type?: string) { return ({ 'product.updated': '产品信息更新', 'deliverable.submitted': '登记交付物', 'deliverable.accepted': '交付物验收通过', 'deliverable.rejected': '交付物退回', 'release.created': '创建发布版本', 'runtime.registered': '登记运行实例', 'runtime.updated': '更新运行实例', 'runtime.health_synced': '同步运行健康', 'runtime.removed': '移除运行实例' } as Record<string, string>)[type || ''] || type || '产品活动' }
function formatTime(value: string) { const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false }) }

watch(() => props.productId, loadProduct)
onMounted(loadProduct)
</script>

<style scoped>
.product-detail-page { display: grid; gap: 16px; min-width: 0; }
.detail-head, .head-actions, .identity-tags { display: flex; align-items: center; gap: 8px; }
.detail-head { justify-content: space-between; }
.identity-band { display: grid; grid-template-columns: minmax(260px, 0.72fr) minmax(0, 1fr); gap: 18px; padding: 14px; border: 1px solid var(--line-color); border-radius: 6px; background: var(--card-bg); }
.identity-visual { display: grid; place-items: end start; min-height: 240px; overflow: hidden; padding: 14px; border-radius: 6px; background-position: center; background-size: cover; color: #fff; }
.identity-visual span { max-width: 100%; padding: 4px 7px; overflow: hidden; border-radius: 4px; background: rgb(0 0 0 / 46%); font-size: 13px; font-weight: 700; text-overflow: ellipsis; white-space: nowrap; }
.identity-copy { display: grid; gap: 10px; align-content: center; min-width: 0; }
.identity-copy > span, .compact-list small, .evidence-list small, .dependency-list small, .empty-inline { color: var(--text-secondary); font-size: 11px; }
.identity-copy h2 { margin: 0; color: var(--text-primary); font-size: 22px; }
.identity-copy p, .detail-section p { margin: 0; color: var(--text-secondary); font-size: 13px; line-height: 1.7; }
.identity-tags { flex-wrap: wrap; }
.detail-layout { display: grid; grid-template-columns: minmax(0, 1fr) minmax(300px, 380px); gap: 14px; align-items: start; }
.detail-main, .detail-side { display: grid; gap: 14px; min-width: 0; }
.detail-section { display: grid; gap: 10px; min-width: 0; padding: 14px; border: 1px solid var(--line-color); border-radius: 6px; background: var(--card-bg); }
.detail-section h3 { margin: 0; color: var(--text-primary); font-size: 14px; }
.detail-two-col { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.detail-two-col > div { display: grid; gap: 10px; min-width: 0; align-content: start; }
.tag-list, .pill-grid { display: flex; flex-wrap: wrap; gap: 7px; }
.pill-grid > span:not(.empty-inline) { padding: 5px 8px; border: 1px solid var(--line-color); border-radius: 5px; color: var(--text-primary); font-size: 12px; background: var(--view-color-faint); }
.value-list { display: grid; gap: 7px; margin: 0; padding: 0; list-style: none; }
.value-list li { position: relative; padding-left: 12px; color: var(--text-secondary); font-size: 12px; line-height: 1.55; }
.value-list li::before { position: absolute; top: 0.64em; left: 0; width: 5px; height: 5px; border-radius: 50%; background: var(--view-color); content: ""; }
.media-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; min-width: 0; }
.media-grid article { display: grid; gap: 8px; min-width: 0; padding: 8px; border: 1px solid var(--line-color); border-radius: 6px; background: color-mix(in srgb, var(--card-bg) 88%, #0d1726); }
.media-grid img, .media-grid video { width: 100%; aspect-ratio: 16 / 9; border-radius: 4px; object-fit: cover; background: #080d16; }
.media-grid strong, .media-grid small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.media-grid strong { color: var(--text-primary); font-size: 12px; }
.media-grid small { color: var(--text-secondary); font-size: 11px; }
.evidence-list, .dependency-list, .compact-list, .link-list { display: grid; min-width: 0; }
.evidence-list article, .dependency-list article, .compact-list article { min-width: 0; padding: 9px 0; border-bottom: 1px solid var(--line-color); }
.evidence-list article { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.evidence-list article:last-child, .dependency-list article:last-child, .compact-list article:last-child { border-bottom: 0; }
.evidence-list strong, .dependency-list strong, .compact-list strong { display: block; overflow: hidden; color: var(--text-primary); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.evidence-list p { margin-top: 4px; font-size: 12px; }
.evidence-list button, .link-list a { color: var(--view-color); font-size: 12px; text-decoration: none; }
.evidence-list button { padding: 0; border: 0; background: transparent; cursor: pointer; }
.link-list a { display: flex; align-items: center; gap: 7px; min-width: 0; padding: 8px 0; border-bottom: 1px solid var(--line-color); }
.link-list a:last-child { border-bottom: 0; }
.link-list svg { width: 14px; height: 14px; flex: none; }
.link-list span, .compact-list small { overflow-wrap: anywhere; }
@media (max-width: 980px) { .identity-band, .detail-layout, .detail-two-col { grid-template-columns: 1fr; } .identity-visual { min-height: 180px; } }
@media (max-width: 680px) { .detail-head { align-items: flex-start; flex-direction: column; } .evidence-list article { display: grid; } }
</style>
