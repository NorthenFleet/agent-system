(function () {
  const DEFAULT_SCENARIO = {
    centerLat: 24.5,
    centerLon: 123.5,
    title: 'Cesium 战术地球',
    subtitle: 'one-sim 手工推演 · 3D 地球渲染引擎',
    description: '红方运输机释放无人机突击蓝方双伯克防御（台湾以东海域）',
    units: [
      { id: 'red-transport', name: 'Y-20 运输机', side: 'red', type: 'transport', lat: 23.0, lon: 121.0, alt: 8000, sensor_range: 50 },
      { id: 'red-uav-1', name: '攻击无人机编队-1', side: 'red', type: 'uav', lat: 23.5, lon: 121.5, alt: 3000, sensor_range: 30 },
      { id: 'red-uav-2', name: '攻击无人机编队-2', side: 'red', type: 'uav', lat: 23.3, lon: 121.8, alt: 3000, sensor_range: 30 },
      { id: 'red-uav-3', name: '攻击无人机编队-3', side: 'red', type: 'uav', lat: 23.7, lon: 121.3, alt: 3000, sensor_range: 30 },
      { id: 'red-recon-1', name: '侦察无人机-1', side: 'red', type: 'uav', lat: 24.0, lon: 122.0, alt: 5000, sensor_range: 80 },
      { id: 'red-recon-2', name: '侦察无人机-2', side: 'red', type: 'uav', lat: 23.8, lon: 122.2, alt: 5000, sensor_range: 80 },
      { id: 'red-relay-1', name: '通信中继无人机', side: 'red', type: 'uav', lat: 23.2, lon: 121.2, alt: 6000, sensor_range: 100 },
      { id: 'blue-ddg-1', name: 'DDG-87 梅森号', side: 'blue', type: 'destroyer', lat: 25.0, lon: 124.0, alt: 0, sensor_range: 200 },
      { id: 'blue-ddg-2', name: 'DDG-92 Momsen号', side: 'blue', type: 'destroyer', lat: 25.2, lon: 124.3, alt: 0, sensor_range: 200 },
      { id: 'blue-e2d', name: 'E-2D 预警机', side: 'blue', type: 'awacs', lat: 25.5, lon: 125.0, alt: 9000, sensor_range: 400 },
      { id: 'blue-f22-1', name: 'F-22 战斗巡逻-1', side: 'blue', type: 'fighter', lat: 25.3, lon: 124.5, alt: 10000, sensor_range: 150 },
      { id: 'blue-f22-2', name: 'F-22 战斗巡逻-2', side: 'blue', type: 'fighter', lat: 25.1, lon: 124.8, alt: 10000, sensor_range: 150 },
    ],
  }

  const currentScript = document.currentScript
  const scriptUrl = currentScript && currentScript.src
    ? new URL(currentScript.src, window.location.href)
    : new URL('/cesium-embed.js', window.location.href)
  const publicBaseUrl = new URL('.', scriptUrl).href
  const configuredCesiumBaseUrl = currentScript?.dataset?.cesiumBaseUrl
    || window.ONE_SIM_SITUATION_GLOBE_CESIUM_BASE_URL
    || '/node_modules/cesium/Build/Cesium/'
  const cesiumBaseUrl = new URL(configuredCesiumBaseUrl, publicBaseUrl).href
  let cesiumReadyPromise = null
  let styleInjected = false

  function injectStyle() {
    if (styleInjected) return
    styleInjected = true

    const widgetsLink = document.createElement('link')
    widgetsLink.rel = 'stylesheet'
    widgetsLink.href = `${cesiumBaseUrl}Widgets/widgets.css`
    document.head.appendChild(widgetsLink)

    const style = document.createElement('style')
    style.textContent = `
      .one-sim-cesium-root {
        position: relative;
        width: 100%;
        height: 100%;
        min-height: 360px;
        overflow: hidden;
        background: #020617;
        color: #e2e8f0;
        font-family: "Microsoft YaHei", "SF Mono", Consolas, monospace;
      }
      .one-sim-cesium-container {
        position: absolute;
        inset: 0;
      }
      .one-sim-cesium-panel {
        position: absolute;
        top: 16px;
        left: 16px;
        z-index: 100;
        max-width: min(340px, calc(100% - 32px));
        padding: 16px 18px;
        border: 1px solid rgba(59, 130, 246, 0.32);
        border-radius: 12px;
        background: rgba(15, 23, 42, 0.86);
        box-shadow: 0 4px 24px rgba(0, 0, 0, 0.42);
        backdrop-filter: blur(10px);
      }
      .one-sim-cesium-panel h2 {
        margin: 0 0 8px;
        color: #60a5fa;
        font-size: 15px;
        font-weight: 700;
      }
      .one-sim-cesium-panel p {
        margin: 0 0 6px;
        color: #94a3b8;
        font-size: 12px;
        line-height: 1.5;
      }
      .one-sim-cesium-legend {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        margin-top: 10px;
        font-size: 12px;
      }
      .one-sim-cesium-legend-item {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        color: #cbd5e1;
      }
      .one-sim-cesium-dot {
        width: 10px;
        height: 10px;
        border-radius: 999px;
        border: 1px solid rgba(255, 255, 255, 0.32);
      }
      .one-sim-cesium-dot.red { background: #ef4444; }
      .one-sim-cesium-dot.blue { background: #3b82f6; }
      .one-sim-cesium-dot.neutral { background: #94a3b8; }
      .one-sim-cesium-basemaps {
        position: absolute;
        top: 16px;
        right: 16px;
        z-index: 100;
        display: flex;
        gap: 6px;
        padding: 6px;
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 8px;
        background: rgba(15, 23, 42, 0.86);
        backdrop-filter: blur(10px);
      }
      .one-sim-cesium-btn {
        padding: 6px 12px;
        border: 1px solid rgba(255, 255, 255, 0.2);
        border-radius: 6px;
        background: transparent;
        color: #94a3b8;
        cursor: pointer;
        font-size: 12px;
        transition: all 0.2s ease;
      }
      .one-sim-cesium-btn:hover {
        background: rgba(255, 255, 255, 0.1);
        color: #e2e8f0;
      }
      .one-sim-cesium-btn.active {
        border-color: rgba(59, 130, 246, 0.68);
        background: linear-gradient(135deg, rgba(59, 130, 246, 0.82), rgba(37, 99, 235, 0.82));
        color: #fff;
      }
      .one-sim-cesium-root .cesium-credit-container,
      .one-sim-cesium-root .cesium-infoButton {
        display: none !important;
      }
      @media (max-width: 720px) {
        .one-sim-cesium-panel {
          top: 10px;
          left: 10px;
          padding: 12px 14px;
        }
        .one-sim-cesium-basemaps {
          top: auto;
          right: 10px;
          bottom: 10px;
        }
      }
    `
    document.head.appendChild(style)
  }

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const existing = document.querySelector(`script[src="${src}"]`)
      if (existing) {
        existing.addEventListener('load', resolve, { once: true })
        existing.addEventListener('error', reject, { once: true })
        if (window.Cesium) resolve()
        return
      }

      const script = document.createElement('script')
      script.src = src
      script.async = true
      script.onload = resolve
      script.onerror = () => reject(new Error(`Cesium script failed to load: ${src}`))
      document.head.appendChild(script)
    })
  }

  async function ensureCesium() {
    injectStyle()
    if (window.Cesium) return window.Cesium
    if (!cesiumReadyPromise) {
      window.CESIUM_BASE_URL = cesiumBaseUrl
      cesiumReadyPromise = loadScript(`${cesiumBaseUrl}Cesium.js`).then(() => {
        if (!window.Cesium) {
          throw new Error('Cesium loaded but window.Cesium is unavailable')
        }
        window.Cesium.Ion.defaultAccessToken = ''
        return window.Cesium
      })
    }
    return cesiumReadyPromise
  }

  function asBool(value, fallback = true) {
    if (value === undefined || value === null || value === '') return fallback
    if (typeof value === 'boolean') return value
    return !/^(false|0|no|off)$/i.test(String(value))
  }

  function toNumber(value, fallback) {
    const n = Number(value)
    return Number.isFinite(n) ? n : fallback
  }

  function defaultGeospatialBaseUrl() {
    return `${window.location.protocol}//${window.location.hostname}:5140`
  }

  function getUnitLatLon(unit, centerLat, centerLon) {
    if (unit.lat != null && unit.lon != null) return [Number(unit.lat), Number(unit.lon)]
    if (unit.latitude != null && unit.longitude != null) return [Number(unit.latitude), Number(unit.longitude)]
    if (Array.isArray(unit.position_vec)) {
      const [xKm = 0, yKm = 0] = unit.position_vec
      const lat = centerLat + Number(yKm) / 111.0
      const lon = centerLon + Number(xKm) / (111.0 * Math.cos(centerLat * Math.PI / 180))
      return [lat, lon]
    }
    return [centerLat, centerLon]
  }

  function inferAltitude(unit) {
    if (unit.alt != null) return Number(unit.alt)
    if (unit.altitude != null) return Number(unit.altitude)
    const text = `${unit.type || ''} ${unit.unit_type || ''} ${unit.name || ''}`.toLowerCase()
    if (/sub|潜艇/.test(text)) return -50
    if (/ship|destroyer|frigate|carrier|ddg|舰|艇/.test(text)) return 10
    return 5000
  }

  function normalizeUnit(unit, centerLat, centerLon) {
    const [lat, lon] = getUnitLatLon(unit, centerLat, centerLon)
    return {
      id: String(unit.id || unit.name || `unit-${Math.random().toString(16).slice(2)}`),
      name: String(unit.name || unit.id || '未命名兵力'),
      side: unit.side === 'blue' ? 'blue' : unit.side === 'red' ? 'red' : 'neutral',
      type: unit.type || unit.unit_type || 'unit',
      category: unit.category || unit.type || unit.unit_type || 'unit',
      color: unit.color || null,
      lat,
      lon,
      alt: inferAltitude(unit),
      sensor_range: Number(unit.sensor_range || unit.sensorRange || unit.detectionRange || 0),
      attack_range: Number(unit.attack_range || unit.attackRange || unit.weapon_range || unit.weaponRange || 0),
      raw: unit,
    }
  }

  function resolveItemColor(Cesium, unit) {
    if (unit.color) {
      try {
        const custom = Cesium.Color.fromCssColorString(String(unit.color))
        if (custom) return custom
      } catch (_) {
        // Fall through to the stable side/category palette.
      }
    }
    if (unit.side === 'blue') return Cesium.Color.BLUE
    if (unit.side === 'red') return Cesium.Color.RED
    const palette = {
      domain: '#ffb020',
      event: '#f85149',
      news: '#58a6ff',
      vessel: '#39d98a',
      unit: '#94a3b8',
    }
    return Cesium.Color.fromCssColorString(palette[unit.category] || palette.unit)
  }

  function setCameraTarget(Cesium, viewer, lon, lat, rangeMeters, pitchDegrees) {
    const target = Cesium.Cartesian3.fromDegrees(lon, lat, 0)
    viewer.camera.lookAt(
      target,
      new Cesium.HeadingPitchRange(
        Cesium.Math.toRadians(0),
        Cesium.Math.toRadians(pitchDegrees),
        Math.max(1000, rangeMeters)
      )
    )
    viewer.camera.lookAtTransform(Cesium.Matrix4.IDENTITY)
  }

  function getCameraTargetState(Cesium, viewer) {
    const canvas = viewer.scene && viewer.scene.canvas
    const centerPixel = canvas
      ? new Cesium.Cartesian2((canvas.clientWidth || canvas.width || 0) / 2, (canvas.clientHeight || canvas.height || 0) / 2)
      : null
    let picked = null
    if (centerPixel) {
      const ray = viewer.camera.getPickRay(centerPixel)
      if (ray && viewer.scene.globe) {
        picked = viewer.scene.globe.pick(ray, viewer.scene)
      }
      if (!picked) {
        picked = viewer.camera.pickEllipsoid(centerPixel, viewer.scene.globe && viewer.scene.globe.ellipsoid)
      }
    }
    const cartographic = picked
      ? Cesium.Cartographic.fromCartesian(picked)
      : viewer.camera.positionCartographic
    const cameraCartographic = viewer.camera.positionCartographic
    return {
      lon: Cesium.Math.toDegrees(cartographic.longitude),
      lat: Cesium.Math.toDegrees(cartographic.latitude),
      height_m: cameraCartographic.height,
      pitch_deg: Cesium.Math.toDegrees(viewer.camera.pitch),
      heading_deg: Cesium.Math.toDegrees(viewer.camera.heading),
    }
  }

  function buildPanel(root, options) {
    if (!options.showPanel) return
    const panel = document.createElement('div')
    panel.className = 'one-sim-cesium-panel'
    panel.innerHTML = `
      <h2>${options.title || 'Cesium 战术地球'}</h2>
      <p>${options.subtitle || 'one-sim · 3D 战术态势模块'}</p>
      ${options.description ? `<p>${options.description}</p>` : ''}
      <div class="one-sim-cesium-legend">
        <span class="one-sim-cesium-legend-item"><span class="one-sim-cesium-dot red"></span>红方</span>
        <span class="one-sim-cesium-legend-item"><span class="one-sim-cesium-dot blue"></span>蓝方</span>
        <span class="one-sim-cesium-legend-item"><span class="one-sim-cesium-dot neutral"></span>中立</span>
      </div>
    `
    root.appendChild(panel)
  }

  function buildBasemapSwitcher(root, state) {
    if (!state.options.showBasemapSwitcher) return
    const switcher = document.createElement('div')
    switcher.className = 'one-sim-cesium-basemaps'
    const buttons = [
      ['arcgis', '🛰 卫星'],
      ['osm', '🌊 街道'],
      ['local', '▦ 离线'],
      ['none', '◌ 无底图'],
    ]
    for (const [key, label] of buttons) {
      const btn = document.createElement('button')
      btn.className = 'one-sim-cesium-btn'
      btn.dataset.basemap = key
      btn.textContent = label
      btn.addEventListener('click', () => state.setBasemap(key))
      switcher.appendChild(btn)
    }
    root.appendChild(switcher)
    state.basemapSwitcher = switcher
  }

  async function createArcGisProvider(Cesium) {
    const url = 'https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer'
    if (typeof Cesium.ArcGisMapServerImageryProvider.fromUrl === 'function') {
      return Cesium.ArcGisMapServerImageryProvider.fromUrl(url, { enablePickFeatures: false })
    }
    return new Cesium.ArcGisMapServerImageryProvider({ url, enablePickFeatures: false })
  }

  function createLocalNaturalEarthProvider(Cesium) {
    return new Cesium.UrlTemplateImageryProvider({
      url: `${cesiumBaseUrl}Assets/Textures/NaturalEarthII/{z}/{x}/{reverseY}.jpg`,
      tilingScheme: new Cesium.GeographicTilingScheme(),
      maximumLevel: 2,
      enablePickFeatures: false,
      credit: 'Natural Earth II',
    })
  }

  function cesiumLabelVisibility(units, selectedUnitId, budget = 16) {
    const selectedKey = selectedUnitId == null ? '' : String(selectedUnitId)
    return new Set(units.slice().sort((a, b) => {
      const score = (unit) => {
        const type = `${unit.type || ''} ${unit.name || ''}`.toLowerCase()
        let value = String(unit.id) === selectedKey ? 1000 : 0
        if (unit.is_detected || unit.detected) value += 160
        if (/destroyer|frigate|carrier|transport|command|awacs|预警|运输|舰/.test(type)) value += 80
        return value
      }
      return score(b) - score(a) || String(a.id).localeCompare(String(b.id))
    }).slice(0, budget).map((unit) => String(unit.id)))
  }

  function renderUnit(Cesium, viewer, entityMap, unit, options) {
    const isRed = unit.side === 'red'
    const color = resolveItemColor(Cesium, unit)
    const selected = options.selectedUnitId === unit.id
    const labelOrdinal = Number(options.labelOrdinal) || 0
    const labelCount = Math.max(1, Number(options.labelCount) || 1)
    const labelDirection = isRed ? -1 : 1
    const labelOffsetY = (labelOrdinal - (labelCount - 1) / 2) * 24
    const heightReference = unit.alt > 100
      ? Cesium.HeightReference.NONE
      : Cesium.HeightReference.CLAMP_TO_GROUND

    const entity = viewer.entities.add({
      id: `one-sim-item-${unit.id}`,
      name: unit.name,
      position: Cesium.Cartesian3.fromDegrees(unit.lon, unit.lat, unit.alt),
      point: new Cesium.PointGraphics({
        pixelSize: selected ? 22 : 16,
        color,
        outlineColor: Cesium.Color.WHITE,
        outlineWidth: selected ? 4 : 3,
        heightReference,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
        scaleByDistance: new Cesium.NearFarScalar(120000, 1.0, 2200000, 1.35),
      }),
      label: {
        show: options.showLabel !== false,
        text: unit.name,
        font: selected ? 'bold 14px sans-serif' : 'bold 13px sans-serif',
        fillColor: Cesium.Color.WHITE,
        outlineColor: Cesium.Color.BLACK,
        outlineWidth: 2,
        style: Cesium.LabelStyle.FILL_AND_OUTLINE,
        verticalOrigin: Cesium.VerticalOrigin.CENTER,
        horizontalOrigin: isRed ? Cesium.HorizontalOrigin.RIGHT : Cesium.HorizontalOrigin.LEFT,
        pixelOffset: new Cesium.Cartesian2(labelDirection * (selected ? 22 : 18), labelOffsetY),
        showBackground: true,
        backgroundColor: new Cesium.Color(0, 0, 0, 0.62),
        backgroundPadding: new Cesium.Cartesian2(6, 3),
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
        scaleByDistance: new Cesium.NearFarScalar(120000, 1.0, 2200000, 1.12),
        distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, options.labelMaxDistance),
      },
      properties: {
        unitId: unit.id,
        itemId: unit.id,
        category: unit.category,
        unitData: unit.raw || unit,
      },
    })

    entityMap.set(unit.id, { entity, unit })
  }

  function renderUnitRanges(Cesium, viewer, rangeEntities, units, options) {
    for (const entity of rangeEntities.splice(0)) viewer.entities.remove(entity)
    for (const unit of units) {
      const selected = String(options.selectedUnitId || '') === String(unit.id)
      const sideColor = unit.side === 'blue' ? Cesium.Color.BLUE : Cesium.Color.RED
      const ranges = [
        {
          kind: 'detection',
          radiusKm: unit.sensor_range,
          visible: options.showDetectionRange && (options.detectionRangeScope === 'all' || selected),
          color: sideColor,
        },
        {
          kind: 'attack',
          radiusKm: unit.attack_range,
          visible: options.showAttackRange && (options.attackRangeScope === 'all' || selected),
          color: Cesium.Color.ORANGE,
        },
      ]
      for (const range of ranges) {
        if (!range.visible || !(range.radiusKm > 0)) continue
        rangeEntities.push(viewer.entities.add({
          id: `one-sim-range-${range.kind}-${unit.id}`,
          position: Cesium.Cartesian3.fromDegrees(unit.lon, unit.lat, 0),
          ellipse: {
            semiMajorAxis: range.radiusKm * 1000,
            semiMinorAxis: range.radiusKm * 1000,
            material: range.color.withAlpha(range.kind === 'attack' ? 0.08 : 0.1),
            height: 0,
            outline: true,
            outlineColor: range.color.withAlpha(0.5),
            heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
          },
          properties: { unitId: unit.id, rangeKind: range.kind },
        }))
      }
    }
  }

  function overlayColor(Cesium, overlay) {
    if (overlay.color) {
      try {
        const custom = Cesium.Color.fromCssColorString(String(overlay.color))
        if (custom) return custom.withAlpha(Number(overlay.opacity) || 0.82)
      } catch (_) {
        // Fall through to phase colors.
      }
    }
    if (overlay.phase === 'track') return Cesium.Color.fromCssColorString('#7ce7ff').withAlpha(0.82)
    if (overlay.phase === 'movement') return Cesium.Color.CYAN.withAlpha(0.82)
    if (overlay.phase === 'detection') return (overlay.success ? Cesium.Color.LIME : Cesium.Color.RED).withAlpha(overlay.success ? 0.75 : 0.45)
    if (overlay.phase === 'hit') return (overlay.success ? Cesium.Color.ORANGE : Cesium.Color.fromCssColorString('#64748b')).withAlpha(overlay.success ? 0.9 : 0.52)
    if (overlay.phase === 'damage') return (overlay.destroyed ? Cesium.Color.RED : Cesium.Color.ORANGE).withAlpha(0.9)
    return Cesium.Color.WHITE.withAlpha(0.7)
  }

  function overlayLabel(overlay) {
    if (overlay.label) return overlay.label
    if (overlay.phase === 'movement') return '机动'
    if (overlay.phase === 'detection') return overlay.success ? '探测成功' : '探测失败'
    if (overlay.phase === 'hit') return overlay.success ? '命中' : '未命中'
    if (overlay.phase === 'damage') return overlay.destroyed ? '摧毁' : '毁伤'
    return overlay.phase || '裁决'
  }

  function geoPoint(point) {
    if (!point) return null
    const lat = Number(point.lat)
    const lon = Number(point.lon)
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null
    return { lat, lon, alt: Number(point.alt || point.alt_m || 0) || 0 }
  }

  function midpointGeo(a, b) {
    if (!a || !b) return a || b || null
    return {
      lat: (a.lat + b.lat) / 2,
      lon: (a.lon + b.lon) / 2,
      alt: Math.max(a.alt || 0, b.alt || 0) + 8000,
    }
  }

  function renderOverlayLine(Cesium, viewer, overlayEntities, overlay) {
    const from = geoPoint(overlay.fromGeo || overlay.from)
    const to = geoPoint(overlay.toGeo || overlay.to)
    if (!from || !to) return
    const color = overlayColor(Cesium, overlay)
    const positions = [
      Cesium.Cartesian3.fromDegrees(from.lon, from.lat, from.alt || 0),
      Cesium.Cartesian3.fromDegrees(to.lon, to.lat, to.alt || 0),
    ]
    overlayEntities.push(viewer.entities.add({
      id: `one-sim-overlay-line-${overlay.id}`,
      name: `${overlayLabel(overlay)} ${overlay.fromName || ''} → ${overlay.toName || ''}`,
      polyline: {
        positions,
        width: overlay.phase === 'hit' ? 4 : 2,
        material: color,
        clampToGround: true,
      },
      properties: {
        overlayId: overlay.id,
        phase: overlay.phase,
        raw: overlay.raw || overlay,
      },
    }))

    const mid = midpointGeo(from, to)
    if (!mid) return
    overlayEntities.push(viewer.entities.add({
      id: `one-sim-overlay-label-${overlay.id}`,
      position: Cesium.Cartesian3.fromDegrees(mid.lon, mid.lat, mid.alt || 0),
      label: {
        text: overlayLabel(overlay),
        font: '12px sans-serif',
        fillColor: color,
        outlineColor: Cesium.Color.BLACK,
        outlineWidth: 2,
        style: Cesium.LabelStyle.FILL_AND_OUTLINE,
        verticalOrigin: Cesium.VerticalOrigin.CENTER,
        horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
        showBackground: true,
        backgroundColor: new Cesium.Color(0, 0, 0, 0.58),
        backgroundPadding: new Cesium.Cartesian2(4, 2),
      },
    }))
  }

  function renderOverlayMarker(Cesium, viewer, overlayEntities, overlay) {
    const at = geoPoint(overlay.atGeo || overlay.at)
    if (!at) return
    const color = overlayColor(Cesium, overlay)
    overlayEntities.push(viewer.entities.add({
      id: `one-sim-overlay-marker-${overlay.id}`,
      name: `${overlayLabel(overlay)} ${overlay.unitName || ''}`,
      position: Cesium.Cartesian3.fromDegrees(at.lon, at.lat, at.alt || 0),
      point: {
        pixelSize: overlay.destroyed ? 18 : 14,
        color,
        outlineColor: Cesium.Color.WHITE,
        outlineWidth: 2,
        heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
      },
      label: {
        text: overlay.destroyed ? '摧毁' : `毁伤 ${overlay.damage || ''}`,
        font: '12px sans-serif',
        fillColor: color,
        outlineColor: Cesium.Color.BLACK,
        outlineWidth: 2,
        style: Cesium.LabelStyle.FILL_AND_OUTLINE,
        verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
        pixelOffset: new Cesium.Cartesian2(0, -18),
        showBackground: true,
        backgroundColor: new Cesium.Color(0, 0, 0, 0.62),
        backgroundPadding: new Cesium.Cartesian2(4, 2),
      },
      properties: {
        overlayId: overlay.id,
        phase: overlay.phase,
        raw: overlay.raw || overlay,
      },
    }))
  }

  function renderOverlays(Cesium, viewer, overlayEntities, overlays, options) {
    for (const entity of overlayEntities.splice(0)) {
      viewer.entities.remove(entity)
    }
    if (!options.showAdjudicationOverlays) return
    for (const overlay of overlays || []) {
      if (!overlay) continue
      if (overlay.kind === 'marker' || overlay.phase === 'damage') {
        renderOverlayMarker(Cesium, viewer, overlayEntities, overlay)
      } else {
        renderOverlayLine(Cesium, viewer, overlayEntities, overlay)
      }
    }
  }

  function tracksToOverlays(tracks) {
    const overlays = []
    for (const track of tracks || []) {
      const points = Array.isArray(track.points) ? track.points : []
      for (let index = 1; index < points.length; index += 1) {
        const from = points[index - 1]
        const to = points[index]
        overlays.push({
          id: `track-${track.id}-${index}`,
          phase: 'track',
          from: { lat: from.lat, lon: from.lon ?? from.lng, alt_m: from.alt_m || 0 },
          to: { lat: to.lat, lon: to.lon ?? to.lng, alt_m: to.alt_m || 0 },
          color: track.color || (track.active ? '#7ce7ff' : '#2bbbd8'),
          opacity: track.active ? 0.95 : 0.55,
          label: track.label || '',
          raw: track,
        })
      }
    }
    return overlays
  }

  async function mountCesiumTacticalMap(target, inputOptions = {}) {
    const host = typeof target === 'string' ? document.querySelector(target) : target
    if (!host) throw new Error('OneSimCesium.mount target not found')

    const scenario = {
      ...DEFAULT_SCENARIO,
      ...(inputOptions.scenario || {}),
    }
    const options = {
      centerLat: toNumber(inputOptions.centerLat ?? scenario.centerLat, DEFAULT_SCENARIO.centerLat),
      centerLon: toNumber(inputOptions.centerLon ?? scenario.centerLon, DEFAULT_SCENARIO.centerLon),
      cameraHeight: toNumber(inputOptions.cameraHeight ?? inputOptions.height, 600000),
      focusHeight: toNumber(inputOptions.focusHeight, 650000),
      labelMaxDistance: toNumber(inputOptions.labelMaxDistance, 2500000),
      pitchDegrees: toNumber(inputOptions.pitchDegrees, -45),
      basemap: inputOptions.basemap || 'arcgis',
      title: inputOptions.title ?? scenario.title,
      subtitle: inputOptions.subtitle ?? scenario.subtitle,
      description: inputOptions.description ?? scenario.description,
      showPanel: asBool(inputOptions.showPanel, true),
      showBasemapSwitcher: asBool(inputOptions.showBasemapSwitcher, true),
      showDetectionRange: asBool(inputOptions.showDetectionRange, true),
      showAttackRange: asBool(inputOptions.showAttackRange, true),
      detectionRangeScope: inputOptions.detectionRangeScope === 'all' ? 'all' : 'selected',
      attackRangeScope: inputOptions.attackRangeScope === 'all' ? 'all' : 'selected',
      showAdjudicationOverlays: asBool(inputOptions.showAdjudicationOverlays, true),
      autoFit: asBool(inputOptions.autoFit, true),
      recenterWideView: asBool(inputOptions.recenterWideView, true),
      selectedUnitId: inputOptions.selectedUnitId || null,
      onUnitSelect: typeof inputOptions.onUnitSelect === 'function' ? inputOptions.onUnitSelect : null,
      onItemSelect: typeof inputOptions.onItemSelect === 'function' ? inputOptions.onItemSelect : null,
      geospatialBaseUrl: inputOptions.geospatialBaseUrl || defaultGeospatialBaseUrl(),
      localImageryUrl: inputOptions.localImageryUrl || null,
    }
    const Cesium = await ensureCesium()

    host.innerHTML = ''
    host.classList.add('one-sim-cesium-root')
    const cesiumContainer = document.createElement('div')
    cesiumContainer.className = 'one-sim-cesium-container'
    host.appendChild(cesiumContainer)
    buildPanel(host, options)

    const viewer = new Cesium.Viewer(cesiumContainer, {
      baseLayer: false,
      animation: false,
      timeline: false,
      geocoder: false,
      homeButton: true,
      baseLayerPicker: false,
      sceneModePicker: true,
      selectionIndicator: true,
      navigationHelpButton: false,
      fullscreenButton: false,
      shouldAnimate: true,
      infoBox: true,
    })

    const state = {
      options,
      viewer,
      units: [],
      overlays: [],
      tracks: [],
      entityMap: new Map(),
      rangeEntities: [],
      overlayEntities: [],
      basemapSwitcher: null,
      isRecenteringCamera: false,
      hasCenteredWideView: false,
      hasAutoFitUnits: false,
      wideViewHeight: 1800000,
      setBasemap: async (key) => {
        options.basemap = key
        if (state.basemapSwitcher) {
          state.basemapSwitcher.querySelectorAll('.one-sim-cesium-btn').forEach((btn) => {
            btn.classList.toggle('active', btn.dataset.basemap === key)
          })
        }
        const imageryLayers = viewer.imageryLayers
        while (imageryLayers.length > 0) {
          imageryLayers.remove(imageryLayers.get(0))
        }
        try {
          if (key === 'arcgis') {
            imageryLayers.addImageryProvider(await createArcGisProvider(Cesium))
          } else if (key === 'osm') {
            imageryLayers.addImageryProvider(new Cesium.OpenStreetMapImageryProvider({
              url: 'https://a.tile.openstreetmap.org/',
            }))
          } else if (key === 'local') {
            const localUrl = options.localImageryUrl ||
              `${options.geospatialBaseUrl}/datasets/natural-earth-10m/{z}/{x}/{reverseY}.jpg`
            imageryLayers.addImageryProvider(new Cesium.UrlTemplateImageryProvider({
              url: localUrl,
              tilingScheme: new Cesium.GeographicTilingScheme(),
              maximumLevel: 5,
              enablePickFeatures: false,
              credit: 'Natural Earth II',
            }))
          }
        } catch (error) {
          console.error('[OneSimCesium] 在线底图加载失败，切换本地 Natural Earth', error)
          options.basemap = 'local'
          imageryLayers.addImageryProvider(createLocalNaturalEarthProvider(Cesium))
          if (state.basemapSwitcher) {
            state.basemapSwitcher.querySelectorAll('.one-sim-cesium-btn').forEach((btn) => {
              btn.classList.toggle('active', btn.dataset.basemap === 'local')
            })
          }
        }
      },
      setCamera: (height = options.cameraHeight, pitchDegrees = options.pitchDegrees) => {
        setCameraTarget(Cesium, viewer, options.centerLon, options.centerLat, height, pitchDegrees)
      },
      setViewCenter: (lon, lat, height = options.cameraHeight, pitchDegrees = options.pitchDegrees) => {
        const nextLon = toNumber(lon, options.centerLon)
        const nextLat = toNumber(lat, options.centerLat)
        const nextHeight = toNumber(height, options.cameraHeight)
        options.centerLon = nextLon
        options.centerLat = nextLat
        options.cameraHeight = nextHeight
        options.pitchDegrees = toNumber(pitchDegrees, options.pitchDegrees)
        state.isRecenteringCamera = true
        setCameraTarget(Cesium, viewer, nextLon, nextLat, nextHeight, options.pitchDegrees)
        window.setTimeout(() => {
          state.isRecenteringCamera = false
        }, 0)
      },
      getCameraState: () => {
        return getCameraTargetState(Cesium, viewer)
      },
      renderUnits: () => {
        for (const entry of state.entityMap.values()) {
          viewer.entities.remove(entry.entity)
        }
        state.entityMap.clear()
        const visibleUnits = state.units
          .filter((raw) => raw.status !== 'destroyed' && raw.health !== 0)
          .map((raw) => normalizeUnit(raw, options.centerLat, options.centerLon))
        const visibleLabelIds = cesiumLabelVisibility(visibleUnits, options.selectedUnitId, 16)
        const sideCounts = visibleUnits.filter((unit) => visibleLabelIds.has(String(unit.id))).reduce((counts, unit) => {
          counts[unit.side] = (counts[unit.side] || 0) + 1
          return counts
        }, {})
        const sideOrdinals = {}
        for (const unit of visibleUnits) {
          const showLabel = visibleLabelIds.has(String(unit.id))
          const ordinal = showLabel ? (sideOrdinals[unit.side] || 0) : 0
          if (showLabel) sideOrdinals[unit.side] = ordinal + 1
          renderUnit(Cesium, viewer, state.entityMap, unit, {
            ...options,
            showLabel,
            labelOrdinal: ordinal,
            labelCount: sideCounts[unit.side] || 1,
          })
        }
        renderUnitRanges(Cesium, viewer, state.rangeEntities, visibleUnits, options)
        if (options.autoFit && !state.hasAutoFitUnits && state.entityMap.size > 0) {
          state.hasAutoFitUnits = true
          const entities = Array.from(state.entityMap.values()).map((entry) => entry.entity)
          viewer.zoomTo(entities).catch(() => state.setCamera())
        }
      },
      renderOverlays: () => {
        renderOverlays(Cesium, viewer, state.overlayEntities, [
          ...state.overlays,
          ...tracksToOverlays(state.tracks),
        ], options)
      },
    }

    buildBasemapSwitcher(host, state)
    await state.setBasemap(options.basemap)
    state.setCamera()
    viewer.homeButton.viewModel.command.beforeExecute.addEventListener((commandInfo) => {
      commandInfo.cancel = true
      state.hasCenteredWideView = false
      state.setCamera()
    })
    viewer.camera.moveEnd.addEventListener(() => {
      if (!options.recenterWideView) return
      if (state.isRecenteringCamera) return
      const height = viewer.camera.positionCartographic.height
      if (height < state.wideViewHeight) {
        state.hasCenteredWideView = false
        return
      }
      if (state.hasCenteredWideView) return
      state.isRecenteringCamera = true
      state.hasCenteredWideView = true
      state.setCamera(Math.min(height, 24000000), -90)
      window.setTimeout(() => {
        state.isRecenteringCamera = false
      }, 0)
    })

    const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas)
    const pickGlobeGeo = (position) => {
      if (!position) return null
      const ray = viewer.camera.getPickRay(position)
      const cartesian = ray && viewer.scene.globe.pick(ray, viewer.scene)
        || viewer.camera.pickEllipsoid(position, viewer.scene.globe.ellipsoid)
      if (!cartesian) return null
      const cartographic = Cesium.Cartographic.fromCartesian(cartesian)
      return {
        lat: Cesium.Math.toDegrees(cartographic.latitude),
        lon: Cesium.Math.toDegrees(cartographic.longitude),
        alt_m: cartographic.height || 0,
      }
    }
    let lastHoverDispatch = 0
    handler.setInputAction((movement) => {
      const now = performance.now()
      if (now - lastHoverDispatch < 50) return
      lastHoverDispatch = now
      host.dispatchEvent(new CustomEvent('map-hover', {
        detail: { geo: pickGlobeGeo(movement.endPosition), sourceView: 'earth' },
        bubbles: true,
      }))
    }, Cesium.ScreenSpaceEventType.MOUSE_MOVE)
    handler.setInputAction((click) => {
      const picked = viewer.scene.pick(click.position)
      const unitId = picked && picked.id && picked.id.properties
        ? picked.id.properties.unitId?.getValue()
        : null
      const entry = unitId ? state.entityMap.get(unitId) : null
      if (entry) {
        viewer.flyTo(entry.entity, { duration: 1.2 })
      }
      host.dispatchEvent(new CustomEvent('unit-select', {
        detail: entry ? { unitId, unit: entry.unit.raw || entry.unit } : { unitId: null, unit: null },
        bubbles: true,
      }))
      host.dispatchEvent(new CustomEvent('item-select', {
        detail: entry ? { itemId: unitId, item: entry.unit.raw || entry.unit } : { itemId: null, item: null },
        bubbles: true,
      }))
      if (options.onUnitSelect) {
        options.onUnitSelect(entry ? entry.unit.raw || entry.unit : null, unitId || null)
      }
      if (options.onItemSelect) {
        options.onItemSelect(entry ? entry.unit.raw || entry.unit : null, unitId || null)
      }
      if (!entry) {
        const geo = pickGlobeGeo(click.position)
        if (geo) {
          const detail = {
            geo,
            sourceView: 'earth',
          }
          host.dispatchEvent(new CustomEvent('map-pick', { detail, bubbles: true }))
          if (options.onMapPick) options.onMapPick(detail)
        }
      }
    }, Cesium.ScreenSpaceEventType.LEFT_CLICK)

    const api = {
      viewer,
      setUnits(units) {
        state.units = Array.isArray(units) ? units : []
        state.renderUnits()
        state.renderOverlays()
      },
      setItems(items) {
        state.units = Array.isArray(items) ? items : []
        state.hasAutoFitUnits = false
        state.renderUnits()
        state.renderOverlays()
      },
      setTracks(tracks) {
        state.tracks = Array.isArray(tracks) ? tracks : []
        state.renderOverlays()
      },
      setOverlays(overlays) {
        state.overlays = Array.isArray(overlays) ? overlays : []
        state.renderOverlays()
      },
      setSelectedUnit(unitId) {
        options.selectedUnitId = unitId || null
        state.renderUnits()
      },
      setSelectedItem(itemId) {
        options.selectedUnitId = itemId || null
        state.renderUnits()
      },
      setTacticalState(nextState = {}) {
        options.selectedUnitId = nextState.selectedUnitId || null
        options.detectionRangeScope = nextState.detectionRangeScope === 'all' ? 'all' : 'selected'
        options.attackRangeScope = nextState.attackRangeScope === 'all' ? 'all' : 'selected'
        state.units = Array.isArray(nextState.units) ? nextState.units : []
        state.renderUnits()
        state.renderOverlays()
      },
      async setBasemap(key) {
        await state.setBasemap(key)
      },
      setViewCenter(lon, lat, height, pitchDegrees) {
        state.setViewCenter(lon, lat, height, pitchDegrees)
      },
      getCameraState() {
        return state.getCameraState()
      },
      flyToUnit(unitId) {
        const entry = state.entityMap.get(unitId)
        if (entry) viewer.flyTo(entry.entity, { duration: 1.2 })
      },
      flyToItem(itemId) {
        const entry = state.entityMap.get(itemId)
        if (entry) {
          state.setViewCenter(entry.unit.lon, entry.unit.lat, options.focusHeight, -45)
        }
      },
      destroy() {
        handler.destroy()
        state.entityMap.clear()
        state.rangeEntities.splice(0)
        state.overlayEntities.splice(0)
        if (!viewer.isDestroyed()) {
          viewer.destroy()
        }
        host.innerHTML = ''
        host.classList.remove('one-sim-cesium-root')
      },
    }

    api.setItems(inputOptions.items || inputOptions.units || scenario.items || scenario.units || [])
    api.setOverlays(inputOptions.overlays || scenario.overlays || [])
    api.setTracks(inputOptions.tracks || scenario.tracks || [])
    host.__oneSimCesium = api
    return api
  }

  class OneSimCesiumMapElement extends HTMLElement {
    static get observedAttributes() {
      return ['src', 'basemap', 'show-panel', 'show-basemap-switcher', 'show-detection-range', 'auto-fit']
    }

    connectedCallback() {
      this.style.display = this.style.display || 'block'
      if (!this.style.height) this.style.height = '100%'
      this.mount()
    }

    disconnectedCallback() {
      if (this.api) {
        this.api.destroy()
        this.api = null
      }
    }

    attributeChangedCallback() {
      if (this.isConnected) this.mount()
    }

    set units(value) {
      this._units = Array.isArray(value) ? value : []
      if (this.api) this.api.setUnits(this._units)
    }

    get units() {
      return this._units || []
    }

    async mount() {
      if (this._mounting) return
      this._mounting = true
      try {
        if (this.api) {
          this.api.destroy()
          this.api = null
        }
        let scenario = {}
        const src = this.getAttribute('src')
        if (src) {
          const response = await fetch(src)
          const data = await response.json()
          scenario = Array.isArray(data) ? { units: data } : data
        }
        const options = {
          scenario,
          units: this.units.length ? this.units : scenario.units,
          centerLat: this.getAttribute('center-lat') ?? scenario.centerLat,
          centerLon: this.getAttribute('center-lon') ?? scenario.centerLon,
          basemap: this.getAttribute('basemap') || scenario.basemap || 'arcgis',
          title: this.getAttribute('title') || scenario.title,
          subtitle: this.getAttribute('subtitle') || scenario.subtitle,
          description: this.getAttribute('description') || scenario.description,
          showPanel: asBool(this.getAttribute('show-panel'), true),
          showBasemapSwitcher: asBool(this.getAttribute('show-basemap-switcher'), true),
          showDetectionRange: asBool(this.getAttribute('show-detection-range'), true),
          autoFit: asBool(this.getAttribute('auto-fit'), true),
        }
        this.api = await mountCesiumTacticalMap(this, options)
      } finally {
        this._mounting = false
      }
    }
  }

  if (!customElements.get('one-sim-cesium-map')) {
    customElements.define('one-sim-cesium-map', OneSimCesiumMapElement)
  }

  const publicApi = {
    mount: mountCesiumTacticalMap,
    defaultScenario: DEFAULT_SCENARIO,
  }
  window.OneSimSituationGlobe = publicApi
  window.OneSimCesium = publicApi
})()
