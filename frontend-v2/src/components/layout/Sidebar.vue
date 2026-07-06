<template>
  <div class="sidebar">
    <div class="sidebar-header">
      <span class="logo-icon">🤖</span>
      <span class="logo-text">OpenClaw</span>
    </div>
    <el-menu
      :default-active="activeMenu"
      class="sidebar-menu"
      background-color="#161b22"
      text-color="#8b949e"
      active-text-color="var(--view-color)"
      :collapse="false"
      router
    >
      <template v-for="section in menuSections" :key="section.key">
        <div v-if="section.items.length" class="menu-section-title">{{ section.title }}</div>
        <el-menu-item v-for="item in section.items" :key="item.module_key" :index="item.route_path">
          <el-icon><component :is="iconMap[item.icon || 'Monitor'] || Monitor" /></el-icon>
          <span>{{ item.name }}</span>
        </el-menu-item>
      </template>
    </el-menu>
  </div>
</template>

<script setup lang="ts">
import { computed, type Component } from 'vue'
import { useRoute } from 'vue-router'
import {
  Calendar,
  ChatLineRound,
  Coin,
  Collection,
  Cpu,
  Document,
  EditPen,
  FolderOpened,
  Grid,
  List,
  MapLocation,
  Money,
  Monitor,
  Platform,
  Promotion,
  Tools,
  User
} from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const auth = useAuthStore()

const productModuleKeys = ['projects', 'development', 'writing', 'finance', 'products']
const productionModuleKeys = [
  'data-admin',
  'agents',
  'agent-dispatch',
  'agent-chat',
  'knowledge',
  'tools',
  'devices',
  'community',
  'news-center',
  'tasks',
  'monitoring'
]

const iconMap: Record<string, Component> = {
  Calendar,
  ChatLineRound,
  Coin,
  Collection,
  Cpu,
  Document,
  EditPen,
  FolderOpened,
  Grid,
  List,
  MapLocation,
  Money,
  Monitor,
  Platform,
  Promotion,
  Tools,
  User
}

const menuItems = computed(() => {
  const modules = auth.modules
  if (!modules.length) {
    return []
  }
  return [...modules]
    .filter(item => item.is_enabled !== false)
    .sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0))
})

const menuSections = computed(() => {
  const byKey = new Map(menuItems.value.map(item => [item.module_key, item]))
  const sectionItems = (keys: string[]) => keys.map(key => byKey.get(key)).filter(Boolean) as typeof menuItems.value
  const sectioned = new Set([...productModuleKeys, ...productionModuleKeys])
  return [
    { key: 'home', title: '总览', items: sectionItems(['dashboard']) },
    { key: 'product', title: '产品侧', items: sectionItems(productModuleKeys) },
    { key: 'production', title: '生产侧', items: sectionItems(productionModuleKeys) },
    { key: 'system', title: '系统', items: menuItems.value.filter(item => !sectioned.has(item.module_key) && item.module_key !== 'dashboard') }
  ]
})

const activeMenu = computed(() => {
  const path = route.path
  const direct = menuItems.value.find(item => item.route_path === path)
  if (direct) return direct.route_path
  const parent = menuItems.value
    .filter(item => item.route_path !== '/' && path.startsWith(item.route_path))
    .sort((a, b) => b.route_path.length - a.route_path.length)[0]
  if (parent) return parent.route_path
  if (path.startsWith('/tools')) return '/tools'
  if (path.startsWith('/development')) return '/development'
  if (path.startsWith('/writing')) return '/writing'
  if (path.startsWith('/projects')) return '/projects'
  if (path.startsWith('/tasks')) return '/tasks'
  if (path.startsWith('/agents')) return '/agents'
  return menuItems.value[0]?.route_path || '/'
})
</script>

<style scoped>
.sidebar {
  width: 220px;
  background: #161b22;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  border-right: 1px solid #30363d;
  box-shadow: none;
}

.sidebar-header {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border-bottom: 1px solid #30363d;
  padding: 0 16px;
}

.logo-icon {
  font-size: 22px;
}

.logo-text {
  font-size: 14px;
  font-weight: 600;
  color: #c9d1d9;
}

.sidebar-menu {
  flex: 1;
  border-right: none;
  padding: 8px 0;
  overflow-y: auto;
}

.menu-section-title {
  margin: 12px 14px 4px;
  color: #6e7681;
  font-size: 11px;
  font-weight: 700;
}

:deep(.el-menu-item) {
  margin: 4px 8px;
  border-radius: 6px;
}

:deep(.el-menu-item.is-active) {
  background-color: rgba(var(--view-rgb), 0.14) !important;
  box-shadow: inset 3px 0 0 var(--view-color);
}

:deep(.el-sub-menu .el-menu-item) {
  margin: 2px 8px 2px 16px;
  font-size: 13px;
}
</style>
