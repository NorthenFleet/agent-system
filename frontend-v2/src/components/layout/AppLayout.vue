<template>
  <div class="app-layout" :style="themeStyle" :data-view-theme="themeName">
    <Sidebar />
    <div class="main-content">
      <TopBar />
      <div class="page-content">
        <router-view />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import Sidebar from './Sidebar.vue'
import TopBar from './TopBar.vue'

const route = useRoute()

const routeThemes: Record<string, { name: string; rgb: string }> = {
  '/': { name: 'dashboard', rgb: '88, 166, 255' },
  '/projects': { name: 'projects', rgb: '88, 166, 255' },
  '/development': { name: 'development', rgb: '88, 166, 255' },
  '/writing': { name: 'writing', rgb: '88, 166, 255' },
  '/data-admin': { name: 'data-admin', rgb: '88, 166, 255' },
  '/tasks': { name: 'tasks', rgb: '88, 166, 255' },
  '/tasks/kanban': { name: 'kanban', rgb: '88, 166, 255' },
  '/tasks/gantt': { name: 'gantt', rgb: '88, 166, 255' },
  '/agents': { name: 'agents', rgb: '88, 166, 255' },
  '/agent-chat': { name: 'agent-chat', rgb: '88, 166, 255' },
  '/knowledge': { name: 'knowledge', rgb: '88, 166, 255' },
  '/tools': { name: 'tools', rgb: '88, 166, 255' },
  '/skills': { name: 'tools', rgb: '88, 166, 255' },
  '/scheduled': { name: 'tools', rgb: '88, 166, 255' },
  '/devices': { name: 'monitoring', rgb: '88, 166, 255' },
  '/community': { name: 'community', rgb: '88, 166, 255' },
  '/intelligence': { name: 'intelligence', rgb: '88, 166, 255' },
  '/news-center': { name: 'news', rgb: '88, 166, 255' },
  '/products': { name: 'products', rgb: '88, 166, 255' },
  '/monitoring': { name: 'monitoring', rgb: '88, 166, 255' },
  '/user-admin': { name: 'user-admin', rgb: '88, 166, 255' }
}

const activeTheme = computed(() => routeThemes[route.path] || routeThemes['/'])
const themeName = computed(() => activeTheme.value.name)
const themeStyle = computed(() => ({ '--view-rgb': activeTheme.value.rgb }))
</script>

<style scoped>
.app-layout {
  --view-rgb: 88, 166, 255;
  --view-color: rgb(var(--view-rgb));
  --view-color-faint: rgba(var(--view-rgb), 0.045);
  --view-color-soft: rgba(var(--view-rgb), 0.075);
  --view-color-panel: rgba(var(--view-rgb), 0.105);
  --view-color-border: rgba(var(--view-rgb), 0.24);
  --view-color-strong-border: rgba(var(--view-rgb), 0.42);
  --view-color-shadow: rgba(0, 0, 0, 0.22);
  --app-bg: #0d1117;
  --panel-bg: #161b22;
  --card-bg: #21262d;
  --card-bg-soft: #1f242c;
  --text-primary: #c9d1d9;
  --text-secondary: #8b949e;
  --line-color: #30363d;
  display: flex;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
}

.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--app-bg);
}

.page-content {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}
</style>
