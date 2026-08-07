<template>
  <section class="lanshu-architecture-panel">
    <header class="panel-head">
      <div>
        <span class="eyebrow">ARCHITECTURE DIAGRAM</span>
        <h3>{{ title }}</h3>
        <p>岚叔动态架构图 — 黑底手绘风，2秒循环动画</p>
      </div>
      <div class="head-actions">
        <el-button size="small" :type="isGifPlaying ? 'success' : 'primary'" plain @click="toggleView">
          {{ isGifPlaying ? '静态预览' : '播放动画' }}
        </el-button>
        <a :href="gifUrl" download class="head-download">
          <el-button size="small" type="info" plain :icon="Download">下载 GIF</el-button>
        </a>
      </div>
    </header>

    <div class="diagram-container" :class="{ 'gif-mode': isGifPlaying }">
      <template v-if="diagramLoaded">
        <img
          v-if="isGifPlaying"
          :src="gifUrl"
          :alt="title"
          class="diagram-img diagram-gif"
        />
        <img
          v-else
          :src="pngUrl"
          :alt="title"
          class="diagram-img diagram-png"
        />
      </template>
      <el-skeleton v-else :rows="6" animated class="diagram-skeleton" />
    </div>

    <footer class="panel-footer">
      <span>1210×1138 · 20fps · 41帧 · 2.05秒循环</span>
      <span class="footer-spec">
        <el-button size="small" text @click="showSpec = !showSpec">
          {{ showSpec ? '隐藏 Spec' : '查看 JSON Spec' }}
        </el-button>
      </span>
    </footer>

    <el-collapse-transition>
      <pre v-if="showSpec && specText" class="spec-preview">{{ specText }}</pre>
    </el-collapse-transition>
  </section>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Download } from '@element-plus/icons-vue'

const props = defineProps<{
  projectId?: number | string
  diagramKey?: string
  title?: string
}>()

const diagramMap: Record<string, { gif: string; png: string; title: string }> = {
  '1': { gif: '/assets/diagrams/01-system-overview.gif', png: '/assets/diagrams/01-system-overview.png', title: 'OpenClaw 系统全景' },
  '2': { gif: '/assets/diagrams/02-kanban-v3.gif', png: '/assets/diagrams/02-kanban-v3.png', title: '看板 V3' },
  '3': { gif: '/assets/diagrams/03-one-sim.gif', png: '/assets/diagrams/03-one-sim.png', title: 'one-sim 仿真' },
  '4': { gif: '/assets/diagrams/04-phd-thesis.gif', png: '/assets/diagrams/04-phd-thesis.png', title: '博士论文' },
  '5': { gif: '/assets/diagrams/05-command-center.gif', png: '/assets/diagrams/05-command-center.png', title: '3021 指挥中心' },
  '6': { gif: '/assets/diagrams/06-ninja-dispatch.gif', png: '/assets/diagrams/06-ninja-dispatch.png', title: '忍者神龟调度' },
  '7': { gif: '/assets/diagrams/07-pm-dashboard.gif', png: '/assets/diagrams/07-pm-dashboard.png', title: 'PM Dashboard' },
  'kanban-v3': { gif: '/assets/diagrams/02-kanban-v3.gif', png: '/assets/diagrams/02-kanban-v3.png', title: '看板 V3' },
  'kanban_v3': { gif: '/assets/diagrams/02-kanban-v3.gif', png: '/assets/diagrams/02-kanban-v3.png', title: '看板 V3' },
  'one-sim': { gif: '/assets/diagrams/03-one-sim.gif', png: '/assets/diagrams/03-one-sim.png', title: 'one-sim 仿真' },
  'one_sim': { gif: '/assets/diagrams/03-one-sim.gif', png: '/assets/diagrams/03-one-sim.png', title: 'one-sim 仿真' },
  'phd-thesis': { gif: '/assets/diagrams/04-phd-thesis.gif', png: '/assets/diagrams/04-phd-thesis.png', title: '博士论文' },
  'phd_thesis': { gif: '/assets/diagrams/04-phd-thesis.gif', png: '/assets/diagrams/04-phd-thesis.png', title: '博士论文' },
  'command-center': { gif: '/assets/diagrams/05-command-center.gif', png: '/assets/diagrams/05-command-center.png', title: '3021 指挥中心' },
  'command_center': { gif: '/assets/diagrams/05-command-center.gif', png: '/assets/diagrams/05-command-center.png', title: '3021 指挥中心' },
  'ninja-dispatch': { gif: '/assets/diagrams/06-ninja-dispatch.gif', png: '/assets/diagrams/06-ninja-dispatch.png', title: '忍者神龟调度' },
  'ninja_dispatch': { gif: '/assets/diagrams/06-ninja-dispatch.gif', png: '/assets/diagrams/06-ninja-dispatch.png', title: '忍者神龟调度' },
  'pm-dashboard': { gif: '/assets/diagrams/07-pm-dashboard.gif', png: '/assets/diagrams/07-pm-dashboard.png', title: 'PM Dashboard' },
  'pm_dashboard': { gif: '/assets/diagrams/07-pm-dashboard.gif', png: '/assets/diagrams/07-pm-dashboard.png', title: 'PM Dashboard' },
  'system-overview': { gif: '/assets/diagrams/01-system-overview.gif', png: '/assets/diagrams/01-system-overview.png', title: 'OpenClaw 系统全景' },
  'system_overview': { gif: '/assets/diagrams/01-system-overview.gif', png: '/assets/diagrams/01-system-overview.png', title: 'OpenClaw 系统全景' },
}

const resolvedKey = computed(() => {
  if (props.diagramKey && diagramMap[props.diagramKey]) return props.diagramKey
  const pid = String(props.projectId || '')
  if (diagramMap[pid]) return pid
  return null
})

const diagram = computed(() => {
  if (resolvedKey.value) return diagramMap[resolvedKey.value]
  return { gif: '', png: '', title: props.title || '系统架构图' }
})

const gifUrl = computed(() => diagram.value.gif)
const pngUrl = computed(() => diagram.value.png)
const title = computed(() => diagram.value.title)

const isGifPlaying = ref(false)
const diagramLoaded = ref(false)
const showSpec = ref(false)
const specText = ref('')

function toggleView() {
  isGifPlaying.value = !isGifPlaying.value
}

onMounted(() => {
  if (gifUrl.value) {
    const img = new Image()
    img.onload = () => { diagramLoaded.value = true }
    img.onerror = () => { diagramLoaded.value = true }
    img.src = gifUrl.value
  }
})
</script>

<style scoped>
.lanshu-architecture-panel {
  display: grid;
  gap: 12px;
  color: var(--text, #e2e8f0);
}

.panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.panel-head > div {
  display: grid;
  gap: 4px;
}

.panel-head h3 {
  margin: 2px 0 0;
  font-size: 16px;
}

.panel-head p {
  margin: 2px 0 0;
  color: var(--text-secondary, #94a3b8);
  font-size: 12px;
}

.eyebrow {
  color: #62a8ff;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.head-download {
  text-decoration: none;
}

.diagram-container {
  position: relative;
  width: 100%;
  border: 1px solid #2c3c50;
  border-radius: 6px;
  background: #0a0a14;
  overflow: hidden;
}

.diagram-container.gif-mode {
  background: #080810;
}

.diagram-img {
  display: block;
  width: 100%;
  height: auto;
  object-fit: contain;
}

.diagram-gif {
  image-rendering: auto;
}

.diagram-skeleton {
  padding: 24px;
}

.panel-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--text-secondary, #94a3b8);
  font-size: 11px;
  padding-top: 4px;
}

.spec-preview {
  margin: 0;
  padding: 12px;
  border: 1px solid #2c3c50;
  border-radius: 4px;
  background: #111827;
  color: #8bc4ff;
  font-size: 11px;
  line-height: 1.5;
  overflow-x: auto;
  max-height: 300px;
}
</style>
