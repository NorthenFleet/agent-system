<template>
  <article class="globe-panel" data-testid="intelligence-globe">
    <div class="globe-head">
      <div>
        <h2>空间态势地球</h2>
        <p>One-Sim Cesium 模块 · 专题、事件、AIS 舰艇、航迹与新闻统一经纬度呈现</p>
      </div>
      <div class="globe-tools">
        <el-switch v-model="eventsEnabled" size="small" active-text="事件" />
        <el-switch v-model="vesselsEnabled" size="small" active-text="舰艇" />
        <el-switch v-model="tracksEnabled" size="small" active-text="航迹" />
        <el-switch v-model="newsEnabled" size="small" active-text="新闻" />
        <el-select v-model="basemap" size="small" class="basemap-select" aria-label="地球底图">
          <el-option label="卫星" value="arcgis" />
          <el-option label="街道" value="osm" />
          <el-option label="离线" value="local" />
          <el-option label="无底图" value="none" />
        </el-select>
        <el-tooltip content="复位地球视角">
          <el-button circle size="small" aria-label="复位地球视角" @click="resetView">
            <el-icon><Aim /></el-icon>
          </el-button>
        </el-tooltip>
        <el-tag :type="ready ? 'success' : 'warning'" effect="plain">{{ status }}</el-tag>
      </div>
    </div>

    <div class="globe-stage">
      <div ref="canvasHost" class="globe-canvas" aria-label="Cesium 三维空间态势地球"></div>
      <div v-if="!ready" class="globe-fallback">
        <span>🌐</span>
        <p>{{ status }}</p>
      </div>

      <div v-if="activeItem" class="coordinate-readout">
        <span>{{ activeItem.name }}</span>
        <strong>{{ formatCoordinate(activeItem.lat, activeItem.lng) }}</strong>
        <small>{{ activeItem.locationLabel }}</small>
      </div>

      <div class="space-legend">
        <span><i class="dot dot-domain"></i>长期情报</span>
        <span><i class="dot dot-event"></i>情报事件</span>
        <span><i class="dot dot-news"></i>新闻资讯</span>
        <span><i class="dot dot-vessel"></i>AIS 舰艇</span>
        <span><i class="line-sample"></i>航迹</span>
        <span><i class="dot dot-active"></i>当前聚焦</span>
      </div>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { Aim } from '@element-plus/icons-vue'
import type { GlobeSpatialItem, GlobeTrack } from '@/globe/types'

type Basemap = 'arcgis' | 'osm' | 'local' | 'none'

interface SituationGlobeController {
  setItems(items: unknown[]): void
  setTracks(tracks: unknown[]): void
  setSelectedItem(id: string | null): void
  setBasemap(key: Basemap): Promise<void>
  setViewCenter(lon: number, lat: number, height?: number, pitch?: number): void
  flyToItem(id: string): void
  destroy(): void
}

interface SituationGlobeModule {
  mount(target: HTMLElement, options: Record<string, unknown>): Promise<SituationGlobeController>
}

declare global {
  interface Window {
    OneSimSituationGlobe?: SituationGlobeModule
    ONE_SIM_SITUATION_GLOBE_CESIUM_BASE_URL?: string
  }
}

const props = withDefaults(defineProps<{
  items: GlobeSpatialItem[]
  tracks: GlobeTrack[]
  activeKey: string
  showVessels?: boolean
  showTracks?: boolean
  showNews?: boolean
  showEvents?: boolean
}>(), {
  showVessels: true,
  showTracks: true,
  showNews: true,
  showEvents: true
})

const emit = defineEmits<{
  select: [item: GlobeSpatialItem]
  ready: [value: boolean]
  'update:showVessels': [value: boolean]
  'update:showTracks': [value: boolean]
  'update:showNews': [value: boolean]
  'update:showEvents': [value: boolean]
}>()

const MODULE_URL = '/vendor/situation-globe/situation-globe.js?v=1.0.3'
const CESIUM_BASE_URL = '/vendor/situation-globe/cesium/'
const canvasHost = ref<HTMLElement | null>(null)
const ready = ref(false)
const status = ref('正在加载态势地球')
const basemap = ref<Basemap>('arcgis')
let globe: SituationGlobeController | null = null

const vesselsEnabled = computed({ get: () => props.showVessels, set: value => emit('update:showVessels', value) })
const tracksEnabled = computed({ get: () => props.showTracks, set: value => emit('update:showTracks', value) })
const newsEnabled = computed({ get: () => props.showNews, set: value => emit('update:showNews', value) })
const eventsEnabled = computed({ get: () => props.showEvents, set: value => emit('update:showEvents', value) })
const activeItem = computed(() => props.items.find(item => item.key === props.activeKey))

const visibleItems = computed(() => props.items.filter(item => {
  if (item.type === 'vessel') return props.showVessels
  if (item.type === 'news') return props.showNews
  if (item.type === 'event') return props.showEvents
  return true
}))

const moduleItems = computed(() => visibleItems.value.map(item => ({
  ...item,
  id: item.key,
  lon: item.lng,
  category: item.type,
  side: 'neutral'
})))

const moduleTracks = computed(() => props.showTracks ? props.tracks.map(track => ({
  ...track,
  points: track.points.map(point => ({ ...point, lon: point.lng }))
})) : [])

function formatCoordinate(lat: number, lng: number) {
  return `${Math.abs(lat).toFixed(4)}°${lat >= 0 ? 'N' : 'S'}  ${Math.abs(lng).toFixed(4)}°${lng >= 0 ? 'E' : 'W'}`
}

function loadModule() {
  if (window.OneSimSituationGlobe) return Promise.resolve(window.OneSimSituationGlobe)
  return new Promise<SituationGlobeModule>((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(`script[src="${MODULE_URL}"]`)
    const script = existing || document.createElement('script')
    const finish = () => window.OneSimSituationGlobe
      ? resolve(window.OneSimSituationGlobe)
      : reject(new Error('OneSimSituationGlobe 未注册'))
    script.addEventListener('load', finish, { once: true })
    script.addEventListener('error', () => reject(new Error('态势地球模块加载失败')), { once: true })
    if (!existing) {
      script.src = MODULE_URL
      script.dataset.cesiumBaseUrl = CESIUM_BASE_URL
      document.head.appendChild(script)
    }
  })
}

async function initGlobe() {
  await nextTick()
  if (!canvasHost.value) return
  try {
    window.ONE_SIM_SITUATION_GLOBE_CESIUM_BASE_URL = CESIUM_BASE_URL
    const module = await loadModule()
    globe = await module.mount(canvasHost.value, {
      items: moduleItems.value,
      tracks: moduleTracks.value,
      selectedUnitId: props.activeKey,
      basemap: basemap.value,
      showPanel: false,
      showBasemapSwitcher: false,
      showDetectionRange: false,
      showAttackRange: false,
      showAdjudicationOverlays: true,
      autoFit: true,
      recenterWideView: false,
      cameraHeight: 16000000,
      focusHeight: 850000,
      pitchDegrees: -90,
      onItemSelect: (_raw: unknown, id: string | null) => {
        if (!id) return
        const item = props.items.find(row => row.key === id)
        if (item) emit('select', item)
      }
    })
    globe.setItems(moduleItems.value)
    globe.setTracks(moduleTracks.value)
    globe.setSelectedItem(props.activeKey)
    globe.setViewCenter(121.4737, 31.2304, 16000000, -90)
    ready.value = true
    status.value = '态势地球已加载'
    emit('ready', true)
  } catch (error) {
    console.error('Situation globe initialization failed', error)
    status.value = '态势地球加载失败'
    emit('ready', false)
  }
}

function focus(item: GlobeSpatialItem) {
  globe?.setSelectedItem(item.key)
  globe?.flyToItem(item.key)
}

function resetView() {
  globe?.setViewCenter(121.4737, 31.2304, 16000000, -90)
}

watch(moduleItems, items => globe?.setItems(items), { deep: true })
watch(moduleTracks, tracks => globe?.setTracks(tracks), { deep: true })
watch(() => props.activeKey, key => {
  globe?.setSelectedItem(key)
})
watch(basemap, value => globe?.setBasemap(value))

onMounted(initGlobe)
onUnmounted(() => {
  globe?.destroy()
  globe = null
})

defineExpose({ focus, resetView })
</script>

<style scoped>
.globe-panel { min-width: 0; overflow: hidden; background: var(--card-bg); border: 1px solid var(--line-color); border-radius: 8px; }
.globe-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; padding: 14px 16px; border-bottom: 1px solid var(--line-color); }
.globe-head h2 { margin: 0; color: var(--text-primary); font-size: 16px; letter-spacing: 0; }
.globe-head p { margin: 5px 0 0; color: var(--text-secondary); font-size: 12px; }
.globe-tools { display: flex; align-items: center; justify-content: flex-end; flex-wrap: wrap; gap: 10px; }
.basemap-select { width: 88px; }
.globe-stage { position: relative; min-height: 460px; background: #0b111b; }
.globe-canvas { position: absolute; inset: 0; overflow: hidden; cursor: grab; }
.globe-canvas:active { cursor: grabbing; }
.globe-canvas :deep(canvas) { display: block; width: 100%; height: 100%; touch-action: none; }
.globe-fallback { position: absolute; inset: 0; display: grid; place-content: center; justify-items: center; gap: 8px; color: var(--text-secondary); pointer-events: none; }
.globe-fallback span { font-size: 42px; }
.globe-fallback p { margin: 0; }
.coordinate-readout { position: absolute; top: 16px; left: 16px; z-index: 4; display: grid; gap: 3px; max-width: min(320px, calc(100% - 32px)); padding: 10px 12px; background: rgba(13, 17, 23, 0.88); border: 1px solid rgba(88, 166, 255, 0.35); border-radius: 6px; pointer-events: none; }
.coordinate-readout span, .coordinate-readout strong, .coordinate-readout small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.coordinate-readout span { color: var(--text-primary); font-size: 13px; font-weight: 600; }
.coordinate-readout strong { color: #7ce7ff; font-size: 12px; font-variant-numeric: tabular-nums; }
.coordinate-readout small { color: var(--text-secondary); font-size: 11px; }
.space-legend { position: absolute; right: 14px; bottom: 14px; z-index: 4; display: flex; flex-wrap: wrap; gap: 10px; max-width: calc(100% - 28px); padding: 8px 10px; background: rgba(13, 17, 23, 0.86); border: 1px solid rgba(48, 54, 61, 0.9); border-radius: 6px; color: var(--text-secondary); font-size: 11px; pointer-events: none; }
.space-legend span { display: inline-flex; align-items: center; gap: 5px; }
.dot { width: 8px; height: 8px; border-radius: 50%; }
.dot-domain { background: #ffb020; } .dot-event { background: #f85149; } .dot-news { background: #58a6ff; } .dot-vessel { background: #39d98a; } .dot-active { background: #fff; }
.line-sample { width: 16px; height: 2px; background: #7ce7ff; }
@media (max-width: 900px) { .globe-head { flex-direction: column; } .globe-tools { justify-content: flex-start; } .globe-stage { min-height: 400px; } }
@media (max-width: 560px) { .globe-stage { min-height: 360px; } .space-legend { left: 10px; right: 10px; bottom: 10px; } }
</style>
