<template>
  <div class="intelligence-page">
    <section class="page-head">
      <div>
        <h1>🌐 情报信息</h1>
        <p>面向特定领域的长期数据积累、空间态势、历史沉淀和专题分析</p>
      </div>
      <el-input
        v-model="keyword"
        class="search-input"
        clearable
        placeholder="搜索领域、数据源、位置或新闻"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
    </section>

    <section class="space-grid">
      <article class="globe-panel">
        <div class="globe-head">
          <div>
            <h2>空间态势地球</h2>
            <p>橙色为长期情报专题，蓝色为新闻热点，绿色为 AIS 舰艇坐标，青色为航迹</p>
          </div>
          <div class="globe-tools">
            <el-switch v-model="showAisLayer" size="small" active-text="舰艇" />
            <el-switch v-model="showTrackLayer" size="small" active-text="航迹" />
            <el-switch v-model="showNewsLayer" size="small" active-text="新闻" />
            <el-tag :type="threeReady ? 'success' : 'warning'" effect="plain">
              {{ threeReady ? '地球已加载' : globeStatus }}
            </el-tag>
          </div>
        </div>
        <div ref="globeContainer" class="globe-canvas">
          <div v-if="!threeReady" class="globe-fallback">
            <span>🌐</span>
            <p>{{ globeStatus }}</p>
          </div>
        </div>
        <div class="space-legend">
          <span><i class="dot dot-domain"></i>长期情报</span>
          <span><i class="dot dot-news"></i>新闻资讯</span>
          <span><i class="dot dot-vessel"></i>AIS 舰艇</span>
          <span><i class="line-sample"></i>航迹</span>
          <span><i class="dot dot-active"></i>当前聚焦</span>
        </div>
      </article>

      <aside class="linked-panel">
        <div class="section-head compact">
          <div>
            <h2>空间与新闻联动</h2>
            <p>{{ activeSummary }}</p>
          </div>
        </div>
        <div class="linked-list">
          <article
            v-for="item in spatialItems"
            :key="item.key"
            class="linked-card"
            :class="{ active: activeSpatialKey === item.key }"
            @click="focusSpatialItem(item)"
          >
            <div>
              <strong>{{ item.name }}</strong>
              <span>{{ spatialTypeLabel(item.type) }} · {{ item.locationLabel }}</span>
            </div>
            <el-tag size="small" :type="spatialTypeTag(item.type)" effect="plain">
              {{ item.countLabel }}
            </el-tag>
          </article>
        </div>
        <div v-if="activeVessel" class="vessel-detail">
          <div class="detail-title">
            <strong>{{ activeVessel.name }}</strong>
            <el-tag size="small" :type="vesselStatusType(activeVessel.status)" effect="plain">
              {{ vesselStatusLabel(activeVessel.status) }}
            </el-tag>
          </div>
          <div class="detail-grid">
            <span>MMSI</span><strong>{{ activeVessel.mmsi }}</strong>
            <span>航速</span><strong>{{ currentVesselPoint(activeVessel)?.speed || '--' }} kn</strong>
            <span>航向</span><strong>{{ currentVesselPoint(activeVessel)?.course || '--' }}°</strong>
            <span>坐标</span><strong>{{ vesselCoordinate(activeVessel) }}</strong>
          </div>
        </div>
      </aside>
    </section>

    <section class="metric-grid">
      <article class="metric-card">
        <span>专题领域</span>
        <strong>{{ filteredDomains.length }}</strong>
        <small>{{ activeDomains }} 个持续采集中</small>
      </article>
      <article class="metric-card">
        <span>AIS 舰艇</span>
        <strong>{{ aisVessels.length }}</strong>
        <small>{{ trackPointCount }} 个历史轨迹点</small>
      </article>
      <article class="metric-card">
        <span>空间点位</span>
        <strong>{{ spatialItems.length }}</strong>
        <small>专题点位与新闻热点合并显示</small>
      </article>
      <article class="metric-card">
        <span>联动新闻</span>
        <strong>{{ relatedNews.length }}</strong>
        <small>来自新闻资讯模块的位置数据</small>
      </article>
    </section>

    <section class="section-panel">
      <div class="section-head">
        <div>
          <h2>AIS 舰艇坐标与航迹</h2>
          <p>当前为示例数据结构，已支持舰艇点、航迹线、状态、航速航向和时间点切换</p>
        </div>
        <div class="time-control">
          <span>{{ selectedTrackTime }}</span>
          <el-slider v-model="trackTimeIndex" :min="0" :max="maxTrackIndex" :show-tooltip="false" size="small" />
        </div>
      </div>
      <div class="vessel-grid">
        <article
          v-for="vessel in aisVessels"
          :key="vessel.id"
          class="vessel-card"
          :class="{ active: activeVesselId === vessel.id }"
          @click="focusVessel(vessel)"
        >
          <div class="vessel-head">
            <div>
              <h3>{{ vessel.name }}</h3>
              <span>{{ vessel.type }} · {{ vessel.area }}</span>
            </div>
            <el-tag size="small" :type="vesselStatusType(vessel.status)" effect="plain">
              {{ vesselStatusLabel(vessel.status) }}
            </el-tag>
          </div>
          <div class="domain-meta">
            <span>MMSI</span><strong>{{ vessel.mmsi }}</strong>
            <span>最新点</span><strong>{{ vesselCoordinate(vessel) }}</strong>
            <span>轨迹点</span><strong>{{ vessel.track.length }} 个</strong>
          </div>
        </article>
      </div>
    </section>

    <section class="section-panel">
      <div class="section-head">
        <div>
          <h2>专题情报库</h2>
          <p>每个专题都有独立的数据源、采集节奏、历史数据、空间范围和分析目标</p>
        </div>
        <el-tag effect="plain">{{ filteredDomains.length }} 个专题</el-tag>
      </div>

      <div class="domain-grid">
        <article
          v-for="domain in filteredDomains"
          :key="domain.id"
          class="domain-card"
          :class="{ active: activeDomainId === domain.id }"
          @click="focusDomain(domain)"
        >
          <div class="card-top">
            <div class="title-wrap">
              <span class="icon-tile">{{ domain.icon }}</span>
              <div>
                <h3>{{ domain.name }}</h3>
                <p>{{ domain.description }}</p>
              </div>
            </div>
            <el-tag :type="statusType(domain.status)" size="small" effect="plain">
              {{ statusLabel(domain.status) }}
            </el-tag>
          </div>

          <div class="domain-meta">
            <span>空间范围</span>
            <strong>{{ domain.locationName }}</strong>
            <span>记录量</span>
            <strong>{{ domain.records }}</strong>
            <span>更新时间</span>
            <strong>{{ domain.updatedAt }}</strong>
          </div>

          <div class="chip-row">
            <el-tag v-for="source in domain.sources" :key="source" size="small" effect="plain">
              {{ source }}
            </el-tag>
          </div>

          <div class="analysis-block">
            <span>分析目标</span>
            <p>{{ domain.goal }}</p>
          </div>
        </article>
      </div>
    </section>

    <section class="section-panel">
      <div class="section-head">
        <div>
          <h2>关联新闻资讯</h2>
          <p>新闻资讯是每日要闻；在这里按空间位置接入，用来辅助长期情报判断</p>
        </div>
        <el-tag effect="plain">{{ relatedNews.length }} 条</el-tag>
      </div>
      <div v-if="relatedNews.length" class="news-grid">
        <article v-for="item in relatedNews" :key="item.id" class="news-card" @click="focusNews(item)">
          <div class="news-line">
            <el-tag size="small" :type="item.priority === 'high' ? 'danger' : 'info'" effect="plain">
              {{ item.category || '资讯' }}
            </el-tag>
            <span>{{ formatDate(item.published_at) }}</span>
          </div>
          <h3>{{ item.title }}</h3>
          <p>{{ item.summary || '暂无摘要' }}</p>
          <div class="news-foot">
            <span>{{ item.source || '未知来源' }}</span>
            <span>{{ locationName(item.location) }}</span>
          </div>
        </article>
      </div>
      <el-empty v-else description="暂无空间关联新闻" :image-size="90" />
    </section>

    <section class="section-panel">
      <div class="section-head">
        <div>
          <h2>采集与沉淀流程</h2>
          <p>情报信息强调连续采集、清洗入库、空间归档、关联分析和长期回溯</p>
        </div>
      </div>

      <div class="pipeline-grid">
        <article v-for="step in pipeline" :key="step.name" class="pipeline-card">
          <span class="step-index">{{ step.index }}</span>
          <h3>{{ step.name }}</h3>
          <p>{{ step.description }}</p>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import { getLocationNews, getNews, getNewsLocations, type NewsItem, type NewsLocation } from '@/api/openclaw'

type DomainStatus = 'active' | 'planning' | 'paused'
type SpatialType = 'domain' | 'news' | 'vessel'
type VesselStatus = 'underway' | 'loitering' | 'silent'

interface IntelligenceDomain {
  id: string
  name: string
  icon: string
  description: string
  status: DomainStatus
  sources: string[]
  records: string
  recordValue: number
  updatedAt: string
  goal: string
  lat: number
  lng: number
  locationName: string
  relatedLocations: string[]
}

interface SpatialItem {
  key: string
  type: SpatialType
  id: string
  name: string
  lat: number
  lng: number
  locationLabel: string
  countLabel: string
}

interface AisTrackPoint {
  time: string
  lat: number
  lng: number
  speed: number
  course: number
}

interface AisVessel {
  id: string
  name: string
  mmsi: string
  type: string
  area: string
  status: VesselStatus
  track: AisTrackPoint[]
}

declare global {
  interface Window {
    THREE?: any
  }
}

const keyword = ref('')
const globeContainer = ref<HTMLElement | null>(null)
const threeReady = ref(false)
const globeStatus = ref('正在加载地球')
const activeSpatialKey = ref('domain:task-planning')
const activeDomainId = ref('task-planning')
const news = ref<NewsItem[]>([])
const newsLocations = ref<Record<string, NewsLocation>>({})
const showAisLayer = ref(true)
const showTrackLayer = ref(true)
const showNewsLayer = ref(true)
const trackTimeIndex = ref(3)
const activeVesselId = ref('ddg-172')

let scene: any
let camera: any
let renderer: any
let earth: any
let animationId = 0
let isDragging = false
let previousMouse = { x: 0, y: 0 }
let markerObjects: any[] = []
let trackObjects: any[] = []
let raycaster: any
let mouse: any

const domains = ref<IntelligenceDomain[]>([
  {
    id: 'task-planning',
    name: '任务规划项目情报',
    icon: '📋',
    description: '长期记录任务规划、拆解、执行反馈和复盘结果',
    status: 'active',
    sources: ['项目管理', '任务列表', '智能体反馈', '复盘记录'],
    records: '12,480',
    recordValue: 12480,
    updatedAt: '持续更新',
    lat: 31.2304,
    lng: 121.4737,
    locationName: '上海 / 项目中心',
    relatedLocations: ['shanghai', 'beijing'],
    goal: '形成可追溯的项目规划知识库，支持项目经理复用历史任务拆解、风险识别和执行模式。'
  },
  {
    id: 'naval-ais',
    name: '海上军舰 AIS 情报',
    icon: '🌊',
    description: '围绕特定海域和目标舰船积累 AIS 轨迹与活动历史',
    status: 'planning',
    sources: ['AIS 数据', '海域网格', '舰船档案', '轨迹时间线'],
    records: '待接入',
    recordValue: 0,
    updatedAt: '规划中',
    lat: 23.5,
    lng: 121.0,
    locationName: '西太平洋 / 近海航道',
    relatedLocations: ['tokyo', 'shenzhen', 'singapore'],
    goal: '长期沉淀舰船位置、航速、航向、靠泊和异常轨迹，形成历史活动画像。'
  },
  {
    id: 'knowledge-assets',
    name: '知识资产情报',
    icon: '🗂️',
    description: '沉淀资料、文档、知识节点与业务主题之间的关系',
    status: 'active',
    sources: ['知识库', '文档撰写', '项目资料', '会议摘要'],
    records: '3,260',
    recordValue: 3260,
    updatedAt: '每日同步',
    lat: 39.9042,
    lng: 116.4074,
    locationName: '北京 / 知识节点',
    relatedLocations: ['beijing'],
    goal: '构建跨项目、跨智能体可复用的背景材料和证据链，减少重复调研。'
  },
  {
    id: 'external-watch',
    name: '外部环境专题',
    icon: '🛰️',
    description: '对指定行业、区域或组织进行长期跟踪，而不是一次性新闻浏览',
    status: 'paused',
    sources: ['RSS', '公开网页', '人工标注', '趋势摘要'],
    records: '860',
    recordValue: 860,
    updatedAt: '暂停采集',
    lat: 37.7749,
    lng: -122.4194,
    locationName: '旧金山 / 外部技术源',
    relatedLocations: ['sanfrancisco', 'newyork', 'london'],
    goal: '把每日碎片信息转化为长期趋势、实体画像和专题判断。'
  }
])

const pipeline = [
  { index: '01', name: '定义专题', description: '明确领域、目标对象、空间范围、采集边界、时间尺度和分析用途。' },
  { index: '02', name: '连续采集', description: '按任务或定时器抓取结构化数据、文件、事件、AIS 轨迹和外部来源。' },
  { index: '03', name: '空间归档', description: '统一经纬度、实体、时间和来源字段，并保留原始证据引用。' },
  { index: '04', name: '历史分析', description: '按时间线、实体、地点和项目关系做检索、回溯与趋势判断。' }
]

const aisVessels = ref<AisVessel[]>([
  {
    id: 'ddg-172',
    name: '示例驱逐舰 DDG-172',
    mmsi: '412001172',
    type: '水面舰艇',
    area: '台湾以东海域',
    status: 'underway',
    track: [
      { time: '00:00', lat: 23.9, lng: 121.2, speed: 14.2, course: 42 },
      { time: '02:00', lat: 24.2, lng: 121.8, speed: 15.1, course: 48 },
      { time: '04:00', lat: 24.55, lng: 122.25, speed: 14.8, course: 53 },
      { time: '06:00', lat: 24.9, lng: 122.74, speed: 16.0, course: 58 }
    ]
  },
  {
    id: 'ffg-529',
    name: '示例护卫舰 FFG-529',
    mmsi: '412001529',
    type: '护卫舰',
    area: '巴士海峡',
    status: 'loitering',
    track: [
      { time: '00:00', lat: 20.8, lng: 119.3, speed: 9.4, course: 95 },
      { time: '02:00', lat: 20.75, lng: 120.0, speed: 8.9, course: 100 },
      { time: '04:00', lat: 20.7, lng: 120.62, speed: 7.8, course: 94 },
      { time: '06:00', lat: 20.82, lng: 121.18, speed: 8.1, course: 76 }
    ]
  },
  {
    id: 'aux-886',
    name: '示例补给舰 AUX-886',
    mmsi: '412001886',
    type: '辅助舰',
    area: '南海北部',
    status: 'silent',
    track: [
      { time: '00:00', lat: 18.4, lng: 113.5, speed: 11.2, course: 22 },
      { time: '02:00', lat: 18.75, lng: 113.72, speed: 10.8, course: 28 },
      { time: '04:00', lat: 19.05, lng: 113.95, speed: 0, course: 0 },
      { time: '06:00', lat: 19.05, lng: 113.95, speed: 0, course: 0 }
    ]
  }
])

const filteredDomains = computed(() => {
  const key = keyword.value.trim().toLowerCase()
  if (!key) return domains.value
  return domains.value.filter(domain => [
    domain.name,
    domain.description,
    domain.goal,
    domain.updatedAt,
    domain.locationName,
    ...domain.sources
  ].some(value => value.toLowerCase().includes(key)))
})

const spatialItems = computed<SpatialItem[]>(() => {
  const domainItems = filteredDomains.value.map(domain => ({
    key: `domain:${domain.id}`,
    type: 'domain' as const,
    id: domain.id,
    name: domain.name,
    lat: domain.lat,
    lng: domain.lng,
    locationLabel: domain.locationName,
    countLabel: domain.records
  }))
  const seen = new Set<string>()
  const newsItems = news.value
    .filter(() => showNewsLayer.value)
    .filter(item => item.location && newsLocations.value[item.location])
    .filter(item => {
      const key = item.location || ''
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
    .map(item => {
      const locationKey = item.location || ''
      const location = newsLocations.value[locationKey]
      const count = news.value.filter(row => row.location === locationKey).length
      return {
        key: `news:${locationKey}`,
        type: 'news' as const,
        id: locationKey,
        name: location.name,
        lat: location.lat,
        lng: location.lng,
        locationLabel: `${location.country || '未知区域'} · 新闻热点`,
        countLabel: `${count} 条`
      }
    })
  const vesselItems = showAisLayer.value
    ? aisVessels.value.map(vessel => {
      const point = currentVesselPoint(vessel) || vessel.track[vessel.track.length - 1]
      return {
        key: `vessel:${vessel.id}`,
        type: 'vessel' as const,
        id: vessel.id,
        name: vessel.name,
        lat: point.lat,
        lng: point.lng,
        locationLabel: `${vessel.area} · ${point.speed} kn / ${point.course}°`,
        countLabel: `${vessel.track.length} 点`
      }
    })
    : []
  return [...domainItems, ...vesselItems, ...newsItems]
})

const activeDomains = computed(() => domains.value.filter(domain => domain.status === 'active').length)
const maxTrackIndex = computed(() => Math.max(0, Math.max(...aisVessels.value.map(vessel => vessel.track.length - 1))))
const selectedTrackTime = computed(() => aisVessels.value[0]?.track[Math.min(trackTimeIndex.value, maxTrackIndex.value)]?.time || '--:--')
const trackPointCount = computed(() => aisVessels.value.reduce((sum, vessel) => sum + vessel.track.length, 0))
const activeVessel = computed(() => aisVessels.value.find(vessel => vessel.id === activeVesselId.value))
const relatedNews = computed(() => {
  const active = activeSpatialKey.value
  const key = active.replace(/^news:/, '').replace(/^domain:/, '')
  if (active.startsWith('news:')) {
    return news.value.filter(item => item.location === key).slice(0, 12)
  }
  if (active.startsWith('vessel:')) {
    return news.value.filter(item => ['tokyo', 'shenzhen', 'singapore'].includes(item.location || '')).slice(0, 12)
  }
  const domain = domains.value.find(item => item.id === key)
  if (!domain) return news.value.slice(0, 8)
  return news.value.filter(item => domain.relatedLocations.includes(item.location || '')).slice(0, 12)
})

const activeSummary = computed(() => {
  const item = spatialItems.value.find(row => row.key === activeSpatialKey.value)
  if (!item) return '选择地球点位或专题卡片查看关联新闻'
  return `${item.name}：${item.locationLabel}`
})

function statusLabel(status: DomainStatus) {
  const labels: Record<DomainStatus, string> = {
    active: '采集中',
    planning: '规划中',
    paused: '暂停'
  }
  return labels[status]
}

function statusType(status: DomainStatus) {
  if (status === 'active') return 'success'
  if (status === 'planning') return 'warning'
  return 'info'
}

function spatialTypeLabel(type: SpatialType) {
  if (type === 'domain') return '长期情报'
  if (type === 'vessel') return 'AIS 舰艇'
  return '新闻热点'
}

function spatialTypeTag(type: SpatialType) {
  if (type === 'domain') return 'warning'
  if (type === 'vessel') return 'success'
  return 'primary'
}

function vesselStatusLabel(status: VesselStatus) {
  const labels: Record<VesselStatus, string> = {
    underway: '航行中',
    loitering: '盘旋/巡弋',
    silent: '静默/停留'
  }
  return labels[status]
}

function vesselStatusType(status: VesselStatus) {
  if (status === 'underway') return 'success'
  if (status === 'loitering') return 'warning'
  return 'info'
}

function currentVesselPoint(vessel: AisVessel) {
  const index = Math.min(trackTimeIndex.value, vessel.track.length - 1)
  return vessel.track[index]
}

function vesselCoordinate(vessel: AisVessel) {
  const point = currentVesselPoint(vessel)
  if (!point) return '--'
  return `${point.lat.toFixed(2)}, ${point.lng.toFixed(2)}`
}

function locationName(locationKey?: string) {
  if (!locationKey) return '未知位置'
  const location = newsLocations.value[locationKey]
  return location ? location.name : locationKey
}

function formatDate(value?: string) {
  if (!value) return '未知时间'
  return value.replace('T', ' ').slice(0, 16)
}

async function loadSpatialNews() {
  try {
    const [newsData, locationsData] = await Promise.all([
      getNews(120),
      getNewsLocations(),
      getLocationNews()
    ])
    news.value = newsData.news || []
    newsLocations.value = locationsData.locations || {}
  } catch (error) {
    console.error(error)
    ElMessage.warning('新闻空间数据加载失败，情报地球仅显示专题点位')
  }
}

function loadThree() {
  if (window.THREE) return Promise.resolve(window.THREE)
  return new Promise<any>((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>('script[data-openclaw-three]')
    if (existing) {
      existing.addEventListener('load', () => resolve(window.THREE))
      existing.addEventListener('error', reject)
      return
    }
    const script = document.createElement('script')
    script.src = 'https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js'
    script.async = true
    script.dataset.openclawThree = 'true'
    script.onload = () => resolve(window.THREE)
    script.onerror = reject
    document.head.appendChild(script)
  })
}

async function initGlobe() {
  await nextTick()
  if (!globeContainer.value) return
  try {
    const THREE = await loadThree()
    if (!globeContainer.value || !THREE) throw new Error('THREE unavailable')
    threeReady.value = true
    globeStatus.value = '地球已加载'

    scene = new THREE.Scene()
    camera = new THREE.PerspectiveCamera(45, globeContainer.value.clientWidth / globeContainer.value.clientHeight, 0.1, 1000)
    camera.position.z = 3
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setPixelRatio(window.devicePixelRatio)
    renderer.setSize(globeContainer.value.clientWidth, globeContainer.value.clientHeight)
    globeContainer.value.appendChild(renderer.domElement)

    const geometry = new THREE.SphereGeometry(1, 64, 64)
    const textureLoader = new THREE.TextureLoader()
    const material = new THREE.MeshPhongMaterial({
      map: textureLoader.load('https://threejs.org/examples/textures/planets/earth_atmos_2048.jpg'),
      bumpMap: textureLoader.load('https://threejs.org/examples/textures/planets/earth_normal_2048.jpg'),
      bumpScale: 0.04,
      specularMap: textureLoader.load('https://threejs.org/examples/textures/planets/earth_specular_2048.jpg'),
      specular: new THREE.Color(0x222222),
      shininess: 5
    })
    earth = new THREE.Mesh(geometry, material)
    scene.add(earth)

    scene.add(new THREE.AmbientLight(0x586069, 1.15))
    const directionalLight = new THREE.DirectionalLight(0xffffff, 1.1)
    directionalLight.position.set(2, 1, 3).normalize()
    scene.add(directionalLight)

    raycaster = new THREE.Raycaster()
    mouse = new THREE.Vector2()
    bindGlobeEvents()
    renderMarkers()
    animateGlobe()
  } catch (error) {
    console.error(error)
    threeReady.value = false
    globeStatus.value = '地球组件加载失败，显示空间点位列表'
  }
}

function bindGlobeEvents() {
  if (!renderer || !globeContainer.value) return
  const canvas = renderer.domElement
  canvas.addEventListener('mousedown', (event: MouseEvent) => {
    isDragging = true
    previousMouse = { x: event.clientX, y: event.clientY }
  })
  canvas.addEventListener('mousemove', (event: MouseEvent) => {
    if (!isDragging || !earth) return
    const deltaX = event.clientX - previousMouse.x
    const deltaY = event.clientY - previousMouse.y
    earth.rotation.y += deltaX * 0.005
    earth.rotation.x += deltaY * 0.005
    previousMouse = { x: event.clientX, y: event.clientY }
  })
  canvas.addEventListener('mouseup', handleGlobeClick)
  canvas.addEventListener('mouseleave', () => { isDragging = false })
  window.addEventListener('resize', resizeGlobe)
}

function animateGlobe() {
  if (!renderer || !scene || !camera) return
  animationId = requestAnimationFrame(animateGlobe)
  if (!isDragging && earth) earth.rotation.y += 0.0005
  renderer.render(scene, camera)
}

function resizeGlobe() {
  if (!globeContainer.value || !renderer || !camera) return
  camera.aspect = globeContainer.value.clientWidth / globeContainer.value.clientHeight
  camera.updateProjectionMatrix()
  renderer.setSize(globeContainer.value.clientWidth, globeContainer.value.clientHeight)
}

function latLngToVector3(lat: number, lng: number, radius = 1.035) {
  const THREE = window.THREE
  const phi = (90 - lat) * (Math.PI / 180)
  const theta = (lng + 180) * (Math.PI / 180)
  return new THREE.Vector3(
    -radius * Math.sin(phi) * Math.cos(theta),
    radius * Math.cos(phi),
    radius * Math.sin(phi) * Math.sin(theta)
  )
}

function renderMarkers() {
  if (!earth || !window.THREE) return
  markerObjects.forEach(marker => earth.remove(marker))
  markerObjects = []
  trackObjects.forEach(track => earth.remove(track))
  trackObjects = []
  if (showTrackLayer.value) {
    aisVessels.value.forEach(vessel => addTrackLine(vessel))
  }
  spatialItems.value.forEach(item => addMarker(item))
}

function addMarker(item: SpatialItem) {
  const THREE = window.THREE
  const active = item.key === activeSpatialKey.value
  const color = active ? 0xf78166 : item.type === 'domain' ? 0xffb020 : item.type === 'vessel' ? 0x39d98a : 0x58a6ff
  const radius = item.type === 'vessel' ? 1.08 : active ? 1.07 : 1.035
  const position = latLngToVector3(item.lat, item.lng, radius)
  const geometry = new THREE.SphereGeometry(item.type === 'vessel' ? 0.04 : active ? 0.045 : 0.032, 16, 16)
  const material = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: active ? 1 : 0.85 })
  const marker = new THREE.Mesh(geometry, material)
  marker.position.copy(position)
  marker.userData = { spatialKey: item.key }
  earth.add(marker)
  markerObjects.push(marker)

  const ringGeometry = new THREE.RingGeometry(active ? 0.055 : 0.04, active ? 0.075 : 0.058, 32)
  const ringMaterial = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: active ? 0.65 : 0.34, side: THREE.DoubleSide })
  const ring = new THREE.Mesh(ringGeometry, ringMaterial)
  ring.position.copy(position)
  ring.lookAt(new THREE.Vector3(0, 0, 0))
  ring.userData = { spatialKey: item.key }
  earth.add(ring)
  markerObjects.push(ring)
}

function addTrackLine(vessel: AisVessel) {
  if (!window.THREE || !earth || vessel.track.length < 2) return
  const THREE = window.THREE
  const active = vessel.id === activeVesselId.value
  const color = active ? 0x7ce7ff : 0x2bbbd8
  const points = vessel.track
    .slice(0, Math.min(trackTimeIndex.value + 1, vessel.track.length))
    .map(point => latLngToVector3(point.lat, point.lng, active ? 1.065 : 1.052))
  if (points.length < 2) return
  const geometry = new THREE.BufferGeometry().setFromPoints(points)
  const material = new THREE.LineBasicMaterial({ color, transparent: true, opacity: active ? 0.95 : 0.58 })
  const line = new THREE.Line(geometry, material)
  earth.add(line)
  trackObjects.push(line)
}

function handleGlobeClick(event: MouseEvent) {
  isDragging = false
  if (!renderer || !raycaster || !mouse || !camera || !globeContainer.value) return
  const rect = renderer.domElement.getBoundingClientRect()
  mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
  mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1
  raycaster.setFromCamera(mouse, camera)
  const hits = raycaster.intersectObjects(markerObjects)
  const hit = hits.find((item: any) => item.object?.userData?.spatialKey)
  if (hit?.object?.userData?.spatialKey) {
    const item = spatialItems.value.find(row => row.key === hit.object.userData.spatialKey)
    if (item) focusSpatialItem(item)
  }
}

function focusSpatialItem(item: SpatialItem) {
  activeSpatialKey.value = item.key
  activeDomainId.value = item.type === 'domain' ? item.id : ''
  activeVesselId.value = item.type === 'vessel' ? item.id : activeVesselId.value
  rotateGlobeTo(item.lat, item.lng)
  renderMarkers()
}

function focusDomain(domain: IntelligenceDomain) {
  focusSpatialItem({
    key: `domain:${domain.id}`,
    type: 'domain',
    id: domain.id,
    name: domain.name,
    lat: domain.lat,
    lng: domain.lng,
    locationLabel: domain.locationName,
    countLabel: domain.records
  })
}

function focusNews(item: NewsItem) {
  if (!item.location || !newsLocations.value[item.location]) return
  const loc = newsLocations.value[item.location]
  focusSpatialItem({
    key: `news:${item.location}`,
    type: 'news',
    id: item.location,
    name: loc.name,
    lat: loc.lat,
    lng: loc.lng,
    locationLabel: `${loc.country || '未知区域'} · 新闻热点`,
    countLabel: `${news.value.filter(row => row.location === item.location).length} 条`
  })
}

function focusVessel(vessel: AisVessel) {
  const point = currentVesselPoint(vessel) || vessel.track[vessel.track.length - 1]
  focusSpatialItem({
    key: `vessel:${vessel.id}`,
    type: 'vessel',
    id: vessel.id,
    name: vessel.name,
    lat: point.lat,
    lng: point.lng,
    locationLabel: `${vessel.area} · ${point.speed} kn / ${point.course}°`,
    countLabel: `${vessel.track.length} 点`
  })
}

function rotateGlobeTo(lat: number, lng: number) {
  if (!earth) return
  earth.rotation.y = -lng * (Math.PI / 180) - Math.PI / 2
  earth.rotation.x = (90 - lat) * (Math.PI / 180) * 0.28
}

onMounted(async () => {
  await loadSpatialNews()
  await initGlobe()
})

watch(spatialItems, () => renderMarkers())
watch([trackTimeIndex, showAisLayer, showTrackLayer, showNewsLayer], () => renderMarkers())

onUnmounted(() => {
  if (animationId) cancelAnimationFrame(animationId)
  window.removeEventListener('resize', resizeGlobe)
  if (renderer?.domElement?.parentNode) renderer.domElement.parentNode.removeChild(renderer.domElement)
  renderer?.dispose?.()
})
</script>

<style scoped>
.intelligence-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  color: var(--text-primary);
}

.page-head,
.metric-card,
.section-panel,
.domain-card,
.vessel-card,
.pipeline-card,
.globe-panel,
.linked-panel,
.linked-card,
.news-card {
  background: var(--card-bg);
  border: 1px solid var(--line-color);
  border-radius: 8px;
}

.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px;
}

.page-head h1,
.globe-head h2,
.section-head h2,
.domain-card h3,
.pipeline-card h3,
.news-card h3 {
  margin: 0;
  letter-spacing: 0;
}

.page-head h1 {
  font-size: 22px;
}

.page-head p,
.globe-head p,
.section-head p,
.title-wrap p,
.analysis-block p,
.pipeline-card p,
.metric-card small,
.domain-meta span,
.linked-card span,
.news-card p,
.news-line,
.news-foot {
  color: var(--text-secondary);
}

.page-head p,
.globe-head p,
.section-head p {
  margin: 6px 0 0;
  font-size: 13px;
}

.search-input {
  width: 320px;
}

.space-grid {
  display: grid;
  grid-template-columns: minmax(420px, 1.5fr) minmax(280px, 0.8fr);
  gap: 12px;
}

.globe-panel,
.linked-panel,
.section-panel {
  padding: 16px;
}

.globe-head,
.section-head,
.card-top,
.news-line,
.news-foot {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.globe-head,
.section-head {
  align-items: flex-start;
  margin-bottom: 14px;
}

.globe-tools {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px 12px;
  min-width: 260px;
}

.globe-head h2,
.section-head h2 {
  font-size: 16px;
}

.section-head.compact {
  margin-bottom: 10px;
}

.globe-canvas {
  position: relative;
  height: 420px;
  overflow: hidden;
  background: radial-gradient(circle at center, #162032 0%, #080b11 68%);
  border: 1px solid rgba(255, 255, 255, 0.055);
  border-radius: 8px;
}

.globe-canvas :deep(canvas) {
  display: block;
  width: 100%;
  height: 100%;
}

.globe-fallback {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  color: var(--text-secondary);
}

.globe-fallback span {
  font-size: 58px;
}

.space-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin-top: 10px;
  color: var(--text-secondary);
  font-size: 12px;
}

.dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  margin-right: 6px;
  border-radius: 50%;
}

.dot-domain {
  background: #ffb020;
}

.dot-news {
  background: #58a6ff;
}

.dot-vessel {
  background: #39d98a;
}

.dot-active {
  background: #f78166;
}

.line-sample {
  display: inline-block;
  width: 18px;
  height: 2px;
  margin: 0 6px 3px 0;
  background: #7ce7ff;
  box-shadow: 0 0 8px rgba(124, 231, 255, 0.55);
  vertical-align: middle;
}

.linked-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 438px;
  overflow: auto;
}

.linked-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px;
  cursor: pointer;
  background: var(--card-bg-soft);
}

.linked-card.active,
.domain-card.active {
  border-color: var(--view-color-strong-border);
  background: var(--view-color-panel);
}

.linked-card strong,
.linked-card span {
  display: block;
}

.linked-card span {
  margin-top: 4px;
  font-size: 12px;
}

.vessel-detail {
  margin-top: 12px;
  padding: 12px;
  background: rgba(57, 217, 138, 0.055);
  border: 1px solid rgba(57, 217, 138, 0.22);
  border-radius: 8px;
}

.detail-title,
.vessel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.detail-grid {
  display: grid;
  grid-template-columns: 56px minmax(0, 1fr);
  gap: 8px 10px;
  margin-top: 12px;
  font-size: 12px;
}

.detail-grid span,
.vessel-head span {
  color: var(--text-secondary);
}

.detail-grid strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}

.metric-grid,
.pipeline-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.metric-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px;
}

.metric-card span {
  color: var(--text-secondary);
  font-size: 13px;
}

.metric-card strong {
  font-size: 24px;
  line-height: 1.1;
}

.domain-grid,
.news-grid,
.vessel-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}

.domain-card,
.vessel-card,
.news-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px;
  background: var(--card-bg-soft);
  cursor: pointer;
}

.vessel-card.active {
  border-color: rgba(124, 231, 255, 0.58);
  background: rgba(124, 231, 255, 0.055);
}

.vessel-head h3 {
  margin: 0 0 5px;
  font-size: 15px;
}

.time-control {
  display: grid;
  grid-template-columns: 54px minmax(160px, 240px);
  align-items: center;
  gap: 10px;
  color: var(--text-secondary);
  font-size: 12px;
}

.title-wrap {
  display: flex;
  align-items: flex-start;
  min-width: 0;
  gap: 10px;
}

.title-wrap h3,
.news-card h3 {
  font-size: 15px;
}

.title-wrap p {
  margin: 5px 0 0;
  font-size: 12px;
  line-height: 1.5;
}

.icon-tile {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  flex: 0 0 38px;
  background: rgba(var(--view-rgb), 0.14);
  border-radius: 7px;
}

.domain-meta {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  gap: 8px 10px;
  padding-top: 10px;
  border-top: 1px solid var(--line-color);
  font-size: 12px;
}

.domain-meta strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}

.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.analysis-block {
  margin-top: auto;
  padding: 10px;
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid rgba(255, 255, 255, 0.045);
  border-radius: 7px;
}

.analysis-block span {
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 600;
}

.analysis-block p,
.pipeline-card p,
.news-card p {
  margin: 6px 0 0;
  font-size: 13px;
  line-height: 1.6;
}

.news-line,
.news-foot {
  align-items: center;
  font-size: 12px;
}

.news-card h3 {
  line-height: 1.45;
}

.news-card p {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}

.pipeline-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.pipeline-card {
  padding: 14px;
  background: var(--card-bg-soft);
}

.step-index {
  display: inline-block;
  margin-bottom: 12px;
  color: rgb(var(--view-rgb));
  font-size: 12px;
  font-weight: 700;
}

:deep(.el-input__wrapper) {
  border-radius: 6px;
}

@media (max-width: 1180px) {
  .space-grid,
  .metric-grid,
  .pipeline-grid {
    grid-template-columns: 1fr;
  }

  .globe-head {
    flex-direction: column;
  }

  .globe-tools {
    justify-content: flex-start;
    min-width: 0;
  }

  .linked-list {
    max-height: 260px;
  }
}

@media (max-width: 820px) {
  .page-head {
    align-items: stretch;
    flex-direction: column;
  }

  .search-input {
    width: 100%;
  }

  .metric-grid {
    grid-template-columns: 1fr;
  }

  .domain-grid,
  .news-grid,
  .vessel-grid {
    grid-template-columns: 1fr;
  }

  .time-control {
    width: 100%;
    grid-template-columns: 48px minmax(0, 1fr);
  }
}
</style>
