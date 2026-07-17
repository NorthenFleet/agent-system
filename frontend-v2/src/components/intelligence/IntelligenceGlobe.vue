<template>
  <article class="globe-panel" data-testid="intelligence-globe">
    <div class="globe-head">
      <div>
        <h2>空间态势地球</h2>
        <p>专题、新闻热点、AIS 舰艇和历史航迹统一映射到真实经纬度</p>
      </div>
      <div class="globe-tools">
        <el-switch v-model="eventsEnabled" size="small" active-text="事件" />
        <el-switch v-model="vesselsEnabled" size="small" active-text="舰艇" />
        <el-switch v-model="tracksEnabled" size="small" active-text="航迹" />
        <el-switch v-model="newsEnabled" size="small" active-text="新闻" />
        <el-switch v-model="autoRotate" size="small" active-text="自转" />
        <el-tooltip :content="displayMode === 'day' ? '切换夜间地球' : '切换昼间地球'">
          <el-button circle size="small" :aria-label="displayMode === 'day' ? '切换夜间地球' : '切换昼间地球'" @click="toggleDisplayMode">
            <el-icon><Moon v-if="displayMode === 'day'" /><Sunny v-else /></el-icon>
          </el-button>
        </el-tooltip>
        <el-tooltip content="显示或隐藏经纬网">
          <el-button circle size="small" :type="showGraticule ? 'primary' : 'default'" aria-label="显示或隐藏经纬网" @click="showGraticule = !showGraticule">
            <el-icon><Grid /></el-icon>
          </el-button>
        </el-tooltip>
        <el-tooltip content="复位地球视角">
          <el-button circle size="small" aria-label="复位地球视角" @click="resetView">
            <el-icon><Aim /></el-icon>
          </el-button>
        </el-tooltip>
        <el-tag :type="ready ? 'success' : 'warning'" effect="plain">{{ status }}</el-tag>
      </div>
    </div>

    <div class="globe-stage">
      <div ref="canvasHost" class="globe-canvas" aria-label="三维空间态势地球">
        <div v-if="!ready" class="globe-fallback">
          <span>🌐</span>
          <p>{{ status }}</p>
        </div>
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
import { Aim, Grid, Moon, Sunny } from '@element-plus/icons-vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { latLngToCartesian } from '@/globe/coordinates'
import type { GlobeSpatialItem, GlobeTrack } from '@/globe/types'

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

const canvasHost = ref<HTMLElement | null>(null)
const ready = ref(false)
const status = ref('正在加载地球')
const autoRotate = ref(true)
const showGraticule = ref(true)
const displayMode = ref<'day' | 'night'>('day')

const vesselsEnabled = computed({
  get: () => props.showVessels,
  set: value => emit('update:showVessels', value)
})
const tracksEnabled = computed({
  get: () => props.showTracks,
  set: value => emit('update:showTracks', value)
})
const newsEnabled = computed({
  get: () => props.showNews,
  set: value => emit('update:showNews', value)
})
const eventsEnabled = computed({
  get: () => props.showEvents,
  set: value => emit('update:showEvents', value)
})
const activeItem = computed(() => props.items.find(item => item.key === props.activeKey))

let scene: THREE.Scene | undefined
let camera: THREE.PerspectiveCamera | undefined
let renderer: THREE.WebGLRenderer | undefined
let controls: OrbitControls | undefined
let earthRoot: THREE.Group | undefined
let markerLayer: THREE.Group | undefined
let trackLayer: THREE.Group | undefined
let graticuleLayer: THREE.Group | undefined
let earthMaterial: THREE.MeshPhongMaterial | undefined
let cloudMesh: THREE.Mesh | undefined
let sunlight: THREE.DirectionalLight | undefined
let resizeObserver: ResizeObserver | undefined
let animationId = 0
let pointerStart = { x: 0, y: 0 }
let markerMeshes: THREE.Mesh[] = []
let pulseMarkers: Array<{ mesh: THREE.Mesh; phase: number }> = []

function toVector3(lat: number, lng: number, radius = 1) {
  const point = latLngToCartesian(lat, lng, radius)
  return new THREE.Vector3(point.x, point.y, point.z)
}

function formatCoordinate(lat: number, lng: number) {
  const ns = lat >= 0 ? 'N' : 'S'
  const ew = lng >= 0 ? 'E' : 'W'
  return `${Math.abs(lat).toFixed(4)}°${ns}  ${Math.abs(lng).toFixed(4)}°${ew}`
}

function createGraticule() {
  const group = new THREE.Group()
  const material = new THREE.LineBasicMaterial({ color: 0x58a6ff, transparent: true, opacity: 0.14 })
  for (let lat = -60; lat <= 60; lat += 30) {
    const points: THREE.Vector3[] = []
    for (let lng = -180; lng <= 180; lng += 3) points.push(toVector3(lat, lng, 1.006))
    group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), material.clone()))
  }
  for (let lng = -180; lng < 180; lng += 30) {
    const points: THREE.Vector3[] = []
    for (let lat = -90; lat <= 90; lat += 3) points.push(toVector3(lat, lng, 1.006))
    group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), material.clone()))
  }
  return group
}

function greatCirclePoints(points: Array<{ lat: number; lng: number }>, radius: number) {
  const result: THREE.Vector3[] = []
  points.forEach((point, index) => {
    if (index === 0) {
      result.push(toVector3(point.lat, point.lng, radius))
      return
    }
    const start = toVector3(points[index - 1].lat, points[index - 1].lng, 1)
    const end = toVector3(point.lat, point.lng, 1)
    const angle = start.angleTo(end)
    const segments = Math.max(4, Math.ceil(angle / (Math.PI / 90)))
    for (let step = 1; step <= segments; step += 1) {
      const interpolated = start.clone().lerp(end, step / segments).normalize().multiplyScalar(radius)
      result.push(interpolated)
    }
  })
  return result
}

function clearGroup(group?: THREE.Group) {
  if (!group) return
  while (group.children.length) {
    const child = group.children[0]
    if (!child) continue
    group.remove(child)
    child.traverse(object => {
      const mesh = object as THREE.Mesh
      mesh.geometry?.dispose?.()
      const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
      materials.filter(Boolean).forEach(material => (material as THREE.Material).dispose())
    })
  }
}

function renderSpatialLayers() {
  if (!markerLayer || !trackLayer) return
  clearGroup(markerLayer)
  clearGroup(trackLayer)
  markerMeshes = []
  pulseMarkers = []

  props.items.forEach(item => {
    const active = item.key === props.activeKey
    const color = active ? 0xffffff : item.type === 'event' ? 0xf85149 : item.type === 'domain' ? 0xffb020 : item.type === 'vessel' ? 0x39d98a : 0x58a6ff
    const radius = item.type === 'vessel' ? 1.055 : active ? 1.045 : 1.025
    const position = toVector3(item.lat, item.lng, radius)
    const marker = new THREE.Mesh(
      new THREE.SphereGeometry(item.type === 'vessel' ? 0.032 : active ? 0.037 : 0.026, 16, 16),
      new THREE.MeshBasicMaterial({ color, transparent: true, opacity: active ? 1 : 0.9 })
    )
    marker.position.copy(position)
    marker.userData = { spatialKey: item.key }
    markerLayer?.add(marker)
    markerMeshes.push(marker)

    const ring = new THREE.Mesh(
      new THREE.RingGeometry(active ? 0.045 : 0.032, active ? 0.064 : 0.047, 32),
      new THREE.MeshBasicMaterial({ color, transparent: true, opacity: active ? 0.62 : 0.32, side: THREE.DoubleSide })
    )
    ring.position.copy(position)
    ring.lookAt(0, 0, 0)
    markerLayer?.add(ring)
    pulseMarkers.push({ mesh: ring, phase: Math.random() * Math.PI * 2 })
  })

  if (!props.showTracks) return
  props.tracks.forEach(track => {
    if (track.points.length < 2) return
    const geometry = new THREE.BufferGeometry().setFromPoints(greatCirclePoints(track.points, track.active ? 1.045 : 1.035))
    const material = new THREE.LineBasicMaterial({
      color: track.active ? 0x7ce7ff : 0x2bbbd8,
      transparent: true,
      opacity: track.active ? 0.95 : 0.55
    })
    trackLayer?.add(new THREE.Line(geometry, material))
  })
}

function updateDisplayMode() {
  if (!earthMaterial || !sunlight) return
  const night = displayMode.value === 'night'
  earthMaterial.emissiveIntensity = night ? 1.05 : 0.28
  earthMaterial.color.setHex(night ? 0x8aa0ba : 0xffffff)
  sunlight.intensity = night ? 0.55 : 1.45
  if (scene) scene.background = new THREE.Color(night ? 0x060a12 : 0x0b111b)
}

function toggleDisplayMode() {
  displayMode.value = displayMode.value === 'day' ? 'night' : 'day'
  updateDisplayMode()
}

function focus(item: GlobeSpatialItem) {
  if (!camera || !controls) return
  const distance = Math.max(2.35, camera.position.length())
  camera.position.copy(toVector3(item.lat, item.lng, distance))
  controls.target.set(0, 0, 0)
  controls.update()
}

function resetView() {
  if (!camera || !controls) return
  camera.position.set(0, 0.25, 3)
  controls.target.set(0, 0, 0)
  controls.update()
}

function selectAtPointer(event: PointerEvent) {
  if (!renderer || !camera) return
  const distance = Math.hypot(event.clientX - pointerStart.x, event.clientY - pointerStart.y)
  if (distance > 6) return
  const rect = renderer.domElement.getBoundingClientRect()
  const pointer = new THREE.Vector2(
    ((event.clientX - rect.left) / rect.width) * 2 - 1,
    -((event.clientY - rect.top) / rect.height) * 2 + 1
  )
  const raycaster = new THREE.Raycaster()
  raycaster.setFromCamera(pointer, camera)
  const hits = raycaster.intersectObjects(markerMeshes)
  const key = hits[0]?.object?.userData?.spatialKey
  const item = props.items.find(row => row.key === key)
  if (item) emit('select', item)
}

function rememberPointerStart(event: PointerEvent) {
  pointerStart = { x: event.clientX, y: event.clientY }
}

async function initGlobe() {
  await nextTick()
  const host = canvasHost.value
  if (!host) return
  try {
    scene = new THREE.Scene()
    scene.background = new THREE.Color(0x0b111b)
    camera = new THREE.PerspectiveCamera(44, Math.max(host.clientWidth, 1) / Math.max(host.clientHeight, 1), 0.1, 100)
    camera.position.set(0, 0.25, 3)
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'high-performance' })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setSize(Math.max(host.clientWidth, 1), Math.max(host.clientHeight, 1), false)
    renderer.outputColorSpace = THREE.SRGBColorSpace
    host.appendChild(renderer.domElement)

    controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.enablePan = false
    controls.minDistance = 2.15
    controls.maxDistance = 5.2
    controls.autoRotateSpeed = 0.45

    const loader = new THREE.TextureLoader()
    const [dayTexture, nightTexture, normalTexture, specularTexture, cloudTexture] = await Promise.all([
      loader.loadAsync('/assets/globe/earth-day.jpg'),
      loader.loadAsync('/assets/globe/earth-night.jpg'),
      loader.loadAsync('/assets/globe/earth-normal.jpg'),
      loader.loadAsync('/assets/globe/earth-specular.jpg'),
      loader.loadAsync('/assets/globe/earth-clouds.png')
    ])
    dayTexture.colorSpace = THREE.SRGBColorSpace
    nightTexture.colorSpace = THREE.SRGBColorSpace
    cloudTexture.colorSpace = THREE.SRGBColorSpace
    ;[dayTexture, nightTexture, normalTexture, specularTexture, cloudTexture].forEach(texture => {
      texture.anisotropy = Math.min(8, renderer?.capabilities.getMaxAnisotropy() || 1)
    })

    earthRoot = new THREE.Group()
    scene.add(earthRoot)
    earthMaterial = new THREE.MeshPhongMaterial({
      map: dayTexture,
      emissiveMap: nightTexture,
      emissive: new THREE.Color(0x9bbcff),
      emissiveIntensity: 0.28,
      normalMap: normalTexture,
      normalScale: new THREE.Vector2(0.65, 0.65),
      specularMap: specularTexture,
      specular: new THREE.Color(0x4c6f8f),
      shininess: 14
    })
    earthRoot.add(new THREE.Mesh(new THREE.SphereGeometry(1, 96, 96), earthMaterial))

    cloudMesh = new THREE.Mesh(
      new THREE.SphereGeometry(1.012, 72, 72),
      new THREE.MeshPhongMaterial({ map: cloudTexture, transparent: true, opacity: 0.28, depthWrite: false })
    )
    earthRoot.add(cloudMesh)
    earthRoot.add(new THREE.Mesh(
      new THREE.SphereGeometry(1.06, 64, 64),
      new THREE.MeshBasicMaterial({ color: 0x58a6ff, transparent: true, opacity: 0.075, side: THREE.BackSide, depthWrite: false })
    ))

    graticuleLayer = createGraticule()
    markerLayer = new THREE.Group()
    trackLayer = new THREE.Group()
    earthRoot.add(graticuleLayer, trackLayer, markerLayer)

    sunlight = new THREE.DirectionalLight(0xfff4df, 1.45)
    sunlight.position.set(4, 2.5, 4)
    scene.add(sunlight)
    scene.add(new THREE.AmbientLight(0x47617d, 0.78))

    renderer.domElement.addEventListener('pointerdown', rememberPointerStart)
    renderer.domElement.addEventListener('pointerup', selectAtPointer)
    resizeObserver = new ResizeObserver(entries => {
      const entry = entries[0]
      if (!entry || !camera || !renderer) return
      const width = Math.max(entry.contentRect.width, 1)
      const height = Math.max(entry.contentRect.height, 1)
      camera.aspect = width / height
      camera.updateProjectionMatrix()
      renderer.setSize(width, height, false)
    })
    resizeObserver.observe(host)

    renderSpatialLayers()
    updateDisplayMode()
    ready.value = true
    status.value = '地球已加载'
    emit('ready', true)

    const animate = (time: number) => {
      animationId = requestAnimationFrame(animate)
      if (!renderer || !scene || !camera || !controls) return
      controls.autoRotate = autoRotate.value
      controls.update()
      if (cloudMesh) cloudMesh.rotation.y += 0.00012
      if (graticuleLayer) graticuleLayer.visible = showGraticule.value
      pulseMarkers.forEach((pulse, index) => {
        const wave = (Math.sin(time * 0.002 + pulse.phase + index * 0.15) + 1) / 2
        pulse.mesh.scale.setScalar(1 + wave * 0.55)
        ;(pulse.mesh.material as THREE.MeshBasicMaterial).opacity = 0.48 - wave * 0.22
      })
      renderer.render(scene, camera)
    }
    animationId = requestAnimationFrame(animate)
  } catch (error) {
    console.error('Intelligence globe initialization failed', error)
    status.value = '地球资源加载失败'
    ready.value = false
    emit('ready', false)
  }
}

function disposeScene() {
  if (animationId) cancelAnimationFrame(animationId)
  resizeObserver?.disconnect()
  controls?.dispose()
  renderer?.domElement.removeEventListener('pointerdown', rememberPointerStart)
  renderer?.domElement.removeEventListener('pointerup', selectAtPointer)
  scene?.traverse(object => {
    const mesh = object as THREE.Mesh
    mesh.geometry?.dispose?.()
    const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
    materials.filter(Boolean).forEach(material => {
      const typed = material as THREE.MeshStandardMaterial
      Object.values(typed).forEach(value => {
        if (value instanceof THREE.Texture) value.dispose()
      })
      typed.dispose()
    })
  })
  renderer?.dispose()
  renderer?.forceContextLoss()
  if (renderer?.domElement.parentNode) renderer.domElement.parentNode.removeChild(renderer.domElement)
}

watch([
  () => props.items,
  () => props.tracks,
  () => props.activeKey,
  () => props.showTracks
], renderSpatialLayers, { deep: true })
watch(showGraticule, value => {
  if (graticuleLayer) graticuleLayer.visible = value
})
watch(activeItem, item => {
  if (item && ready.value) focus(item)
})

onMounted(initGlobe)
onUnmounted(disposeScene)

defineExpose({ focus, resetView })
</script>

<style scoped>
.globe-panel {
  min-width: 0;
  overflow: hidden;
  background: var(--card-bg);
  border: 1px solid var(--line-color);
  border-radius: 8px;
}

.globe-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--line-color);
}

.globe-head h2 {
  margin: 0;
  color: var(--text-primary);
  font-size: 16px;
  letter-spacing: 0;
}

.globe-head p {
  margin: 5px 0 0;
  color: var(--text-secondary);
  font-size: 12px;
}

.globe-tools {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 10px;
}

.globe-stage {
  position: relative;
  min-height: 460px;
  background: #0b111b;
}

.globe-canvas {
  position: absolute;
  inset: 0;
  overflow: hidden;
  cursor: grab;
}

.globe-canvas:active {
  cursor: grabbing;
}

.globe-canvas :deep(canvas) {
  display: block;
  width: 100%;
  height: 100%;
  touch-action: none;
}

.globe-fallback {
  position: absolute;
  inset: 0;
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 8px;
  color: var(--text-secondary);
}

.globe-fallback span {
  font-size: 42px;
}

.globe-fallback p {
  margin: 0;
}

.coordinate-readout {
  position: absolute;
  top: 16px;
  left: 16px;
  display: grid;
  gap: 3px;
  max-width: min(320px, calc(100% - 32px));
  padding: 10px 12px;
  background: rgba(13, 17, 23, 0.88);
  border: 1px solid rgba(88, 166, 255, 0.35);
  border-radius: 6px;
  pointer-events: none;
}

.coordinate-readout span,
.coordinate-readout strong,
.coordinate-readout small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.coordinate-readout span {
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 600;
}

.coordinate-readout strong {
  color: #7ce7ff;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.coordinate-readout small {
  color: var(--text-secondary);
  font-size: 11px;
}

.space-legend {
  position: absolute;
  right: 14px;
  bottom: 14px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  max-width: calc(100% - 28px);
  padding: 8px 10px;
  background: rgba(13, 17, 23, 0.86);
  border: 1px solid rgba(48, 54, 61, 0.9);
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 11px;
  pointer-events: none;
}

.space-legend span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.dot-domain { background: #ffb020; }
.dot-event { background: #f85149; }
.dot-news { background: #58a6ff; }
.dot-vessel { background: #39d98a; }
.dot-active { background: #f78166; }

.line-sample {
  width: 16px;
  height: 2px;
  background: #7ce7ff;
}

@media (max-width: 900px) {
  .globe-head {
    flex-direction: column;
  }

  .globe-tools {
    justify-content: flex-start;
  }

  .globe-stage {
    min-height: 400px;
  }
}

@media (max-width: 560px) {
  .globe-stage {
    min-height: 340px;
  }

  .coordinate-readout {
    top: 10px;
    left: 10px;
  }

  .space-legend {
    right: 10px;
    bottom: 10px;
  }
}
</style>
