import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import AppLayout from '@/components/layout/AppLayout.vue'

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
        component: () => import('@/views/Dashboard.vue')
      },
      {
        path: 'projects',
        name: 'Projects',
        component: () => import('@/views/Projects.vue')
      },
      {
        path: 'data-admin',
        name: 'DataAdmin',
        component: () => import('@/views/DataAdmin.vue')
      },
      {
        path: 'tasks',
        name: 'Tasks',
        component: () => import('@/views/Tasks.vue')
      },
      {
        path: 'tasks/kanban',
        name: 'Kanban',
        component: () => import('@/views/Kanban.vue')
      },
      {
        path: 'tasks/gantt',
        name: 'Gantt',
        component: () => import('@/views/GanttChart.vue')
      },
      {
        path: 'agents',
        name: 'Agents',
        component: () => import('@/views/Agents.vue')
      },
      {
        path: 'agent-chat',
        name: 'AgentChat',
        component: () => import('@/views/AgentChat.vue')
      },
      {
        path: 'knowledge',
        name: 'Knowledge',
        component: () => import('@/views/Knowledge.vue')
      },
      {
        path: 'skills',
        name: 'Skills',
        component: () => import('@/views/Skills.vue')
      },
      {
        path: 'scheduled',
        name: 'Scheduled',
        component: () => import('@/views/Scheduled.vue')
      },
      {
        path: 'devices',
        name: 'Devices',
        component: () => import('@/views/Devices.vue')
      },
      {
        path: 'community',
        name: 'Community',
        component: () => import('@/views/Community.vue')
      },
      {
        path: 'news-center',
        name: 'News',
        component: () => import('@/views/News.vue')
      },
      {
        path: 'products',
        name: 'Products',
        component: () => import('@/views/Products.vue')
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
router.beforeEach((to) => {
  if (to.meta.requiresAuth) {
    const token = localStorage.getItem('jwt_token')
    if (!token) {
      return { path: '/login' }
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
