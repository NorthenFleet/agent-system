import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import AppLayout from '@/components/layout/AppLayout.vue'
import { useAuthStore } from '@/stores/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { public: true }
  },
  {
    path: '/',
    component: AppLayout,
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        name: 'Dashboard',
        component: () => import('@/views/Dashboard.vue'),
        meta: { module: 'dashboard' }
      },
      {
        path: 'projects',
        name: 'Projects',
        component: () => import('@/views/ProjectHub.vue'),
        meta: { module: 'projects' }
      },
      {
        path: 'development',
        name: 'Development',
        component: () => import('@/views/Projects.vue'),
        meta: { workspaceMode: 'development', module: 'development' }
      },
      {
        path: 'writing',
        name: 'Writing',
        component: () => import('@/views/Projects.vue'),
        meta: { workspaceMode: 'writing', module: 'writing' }
      },
      {
        path: 'data-admin',
        name: 'DataAdmin',
        component: () => import('@/views/DataAdmin.vue'),
        meta: { module: 'data-admin' }
      },
      {
        path: 'tasks',
        name: 'Tasks',
        component: () => import('@/views/Tasks.vue'),
        meta: { module: 'tasks' }
      },
      {
        path: 'tasks/kanban',
        name: 'Kanban',
        component: () => import('@/views/Kanban.vue'),
        meta: { module: 'tasks' }
      },
      {
        path: 'tasks/gantt',
        name: 'Gantt',
        component: () => import('@/views/GanttChart.vue'),
        meta: { module: 'tasks' }
      },
      {
        path: 'agents',
        name: 'Agents',
        component: () => import('@/views/Agents.vue'),
        meta: { module: 'agents' }
      },
      {
        path: 'agents/:id',
        name: 'AgentDetail',
        component: () => import('@/views/AgentsDetail.vue'),
        props: true,
        meta: { module: 'agents' }
      },
      {
        path: 'agent-dispatch',
        redirect: '/development'
      },
      {
        path: 'agent-chat',
        redirect: { path: '/agents', query: { tab: 'chat' } }
      },
      {
        path: 'knowledge',
        name: 'Knowledge',
        component: () => import('@/views/Knowledge.vue'),
        meta: { module: 'knowledge' }
      },
      {
        path: 'finance',
        name: 'Finance',
        component: () => import('@/views/Finance.vue'),
        meta: { module: 'finance' }
      },
      {
        path: 'tools',
        name: 'Tools',
        component: () => import('@/views/Tools.vue'),
        meta: { module: 'tools' }
      },
      {
        path: 'skills',
        redirect: '/tools'
      },
      {
        path: 'scheduled',
        redirect: '/tools'
      },
      {
        path: 'devices',
        redirect: '/monitoring'
      },
      {
        path: 'community',
        name: 'Community',
        component: () => import('@/views/Community.vue'),
        meta: { module: 'community' }
      },
      {
        path: 'intelligence',
        name: 'Intelligence',
        component: () => import('@/views/Intelligence.vue'),
        meta: { module: 'intelligence' }
      },
      {
        path: 'news-center',
        name: 'News',
        component: () => import('@/views/News.vue'),
        meta: { module: 'news-center' }
      },
      {
        path: 'products',
        name: 'Products',
        component: () => import('@/views/Products.vue'),
        meta: { module: 'products' }
      },
      {
        path: 'monitoring',
        name: 'Monitoring',
        component: () => import('@/views/Monitoring.vue'),
        meta: { module: 'monitoring' }
      },
      {
        path: 'user-admin',
        name: 'UserAdmin',
        component: () => import('@/views/UserAdmin.vue'),
        meta: { module: 'user-admin' }
      }
    ]
  },
  // 404 兜底
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/NotFound.vue')
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 路由守卫
router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (to.meta.requiresAuth) {
    const token = localStorage.getItem('jwt_token')
    if (!token) {
      return { path: '/login' }
    }
    if (!auth.user && token) {
      await auth.fetchMe()
    }
    const moduleKey = to.meta.module as string | undefined
    if (moduleKey && !auth.canAccessModule(moduleKey)) {
      const nextPath = auth.firstAllowedPath || '/'
      if (to.path !== nextPath) return { path: nextPath }
    }
  }
  if (to.path === '/login') {
    const token = localStorage.getItem('jwt_token')
    if (token) {
      return { path: '/' }
    }
  }
})

export default router
