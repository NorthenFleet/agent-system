<template>
  <div class="topbar">
    <div class="topbar-left">
      <span class="page-title">{{ pageTitle }}</span>
    </div>
    <div class="topbar-right">
      <el-tooltip :content="themeStore.isDark ? '切换浅色' : '切换深色'" placement="bottom">
        <el-button
          class="theme-toggle-btn"
          text
          @click="themeStore.toggle"
        >
          <span class="theme-icon">{{ themeStore.isDark ? '☀️' : '🌙' }}</span>
        </el-button>
      </el-tooltip>
      <UserMenu />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import UserMenu from './UserMenu.vue'
import { useThemeStore } from '@/stores/theme'

const route = useRoute()
const themeStore = useThemeStore()

const pageTitle = computed(() => {
  const names: Record<string, string> = {
    '/': '仪表盘',
    '/projects': '项目中枢',
    '/development': '程序开发',
    '/writing': '文档撰写',
    '/data-admin': '数据管理',
    '/tasks': '任务管理',
    '/tasks/kanban': '看板视图',
    '/tasks/gantt': '甘特图',
    '/agents': '智能体团队',
    '/agent-chat': '智能体对话',
    '/knowledge': '知识库',
    '/finance': '财务管理',
    '/tools': '工具管理',
    '/skills': '工具管理',
    '/scheduled': '工具管理',
    '/devices': '系统监视',
    '/community': '活动社区',
    '/intelligence': '情报信息',
    '/news-center': '新闻资讯',
    '/products': '产品矩阵',
    '/monitoring': '系统监视'
  }
  return names[route.path] || 'OpenClaw'
})
</script>

<style scoped>
.topbar {
  height: 56px;
  background: #0d1117;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  border-bottom: 1px solid #30363d;
  box-shadow: none;
}

.page-title {
  font-size: 16px;
  font-weight: 600;
  color: #c9d1d9;
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.theme-toggle-btn {
  font-size: 20px;
  padding: 4px 8px;
  border-radius: 6px;
  transition: background 0.2s;
}

.theme-toggle-btn:hover {
  background: rgba(var(--view-rgb), 0.08);
}

.theme-icon {
  cursor: pointer;
}
</style>
