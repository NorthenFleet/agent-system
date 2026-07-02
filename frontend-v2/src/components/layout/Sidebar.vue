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
      <el-menu-item index="/">
        <el-icon><Monitor /></el-icon>
        <span>仪表盘</span>
      </el-menu-item>
      <el-menu-item index="/projects">
        <el-icon><FolderOpened /></el-icon>
        <span>项目管理</span>
      </el-menu-item>
      <el-menu-item index="/data-admin">
        <el-icon><Coin /></el-icon>
        <span>数据管理</span>
      </el-menu-item>
      <el-menu-item index="/agents">
        <el-icon><Cpu /></el-icon>
        <span>智能体团队</span>
      </el-menu-item>
      <el-menu-item index="/agent-chat">
        <el-icon><ChatLineRound /></el-icon>
        <span>智能体对话</span>
      </el-menu-item>
      <el-menu-item index="/knowledge">
        <el-icon><Collection /></el-icon>
        <span>知识库</span>
      </el-menu-item>
      <el-menu-item index="/skills">
        <el-icon><Tools /></el-icon>
        <span>技能管理</span>
      </el-menu-item>
      <el-menu-item index="/scheduled">
        <el-icon><Calendar /></el-icon>
        <span>定时任务</span>
      </el-menu-item>
      <el-menu-item index="/devices">
        <el-icon><Platform /></el-icon>
        <span>设备清单</span>
      </el-menu-item>
      <el-menu-item index="/community">
        <el-icon><ChatLineRound /></el-icon>
        <span>活动社区</span>
      </el-menu-item>
      <el-menu-item index="/news-center">
        <el-icon><Document /></el-icon>
        <span>新闻资讯</span>
      </el-menu-item>
      <el-menu-item index="/tasks">
        <el-icon><List /></el-icon>
        <span>任务列表</span>
      </el-menu-item>
      <el-menu-item index="/products">
        <el-icon><Grid /></el-icon>
        <span>产品矩阵</span>
      </el-menu-item>
      <el-menu-item index="/legacy" @click.prevent="openLegacy">
        <el-icon><Link /></el-icon>
        <span>旧版入口</span>
      </el-menu-item>
    </el-menu>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { Calendar, ChatLineRound, Coin, Collection, Cpu, Document, FolderOpened, Grid, Link, List, Monitor, Platform, Tools } from '@element-plus/icons-vue'

const route = useRoute()
const activeMenu = computed(() => {
  const path = route.path
  if (path === '/') return '/'
  if (path.startsWith('/projects')) return '/projects'
  if (path.startsWith('/data-admin')) return '/data-admin'
  if (path.startsWith('/tasks/kanban')) return '/tasks/kanban'
  if (path.startsWith('/tasks/gantt')) return '/tasks/gantt'
  if (path.startsWith('/tasks')) return '/tasks'
  if (path.startsWith('/agents')) return '/agents'
  if (path.startsWith('/agent-chat')) return '/agent-chat'
  if (path.startsWith('/knowledge')) return '/knowledge'
  if (path.startsWith('/skills')) return '/skills'
  if (path.startsWith('/scheduled')) return '/scheduled'
  if (path.startsWith('/devices')) return '/devices'
  if (path.startsWith('/community')) return '/community'
  if (path.startsWith('/news-center')) return '/news-center'
  if (path.startsWith('/products')) return '/products'
  return '/'
})

function openLegacy() {
  window.location.href = '/legacy'
}
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
