import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { login as apiLogin, logout as apiLogout, getMe, refreshToken as apiRefreshToken } from '@/api/auth'
import type { User } from '@/api/auth'

export type { User } from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const token = ref<string | null>(localStorage.getItem('jwt_token'))
  const refreshToken = ref<string | null>(localStorage.getItem('jwt_refresh_token'))
  const loading = ref(false)

  const isAuthenticated = computed(() => !!token.value)
  const isAdmin = computed(() => user.value?.role === 'admin')
  const displayName = computed(() => user.value?.display_name || '用户')
  const modules = computed(() => user.value?.modules || [])
  const moduleKeys = computed(() => user.value?.module_keys || modules.value.map(item => item.module_key))
  const firstAllowedPath = computed(() => modules.value[0]?.route_path || '/')

  function canAccessModule(moduleKey?: string) {
    if (!moduleKey) return true
    if (isAdmin.value) return true
    return moduleKeys.value.includes(moduleKey)
  }

  async function login(username: string, password: string) {
    loading.value = true
    try {
      const data = await apiLogin(username, password)
      token.value = data.access_token
      refreshToken.value = (data as any).refresh_token || null
      user.value = data.user
      localStorage.setItem('jwt_token', data.access_token)
      if (refreshToken.value) {
        localStorage.setItem('jwt_refresh_token', refreshToken.value)
      }
    } finally {
      loading.value = false
    }
  }

  async function logout() {
    if (token.value) {
      try {
        await apiLogout()
      } catch {
        // 忽略登出失败
      }
    }
    token.value = null
    refreshToken.value = null
    user.value = null
    localStorage.removeItem('jwt_token')
    localStorage.removeItem('jwt_refresh_token')
  }

  async function fetchMe() {
    if (!token.value) return
    try {
      user.value = await getMe()
    } catch {
      token.value = null
      localStorage.removeItem('jwt_token')
    }
  }

  async function doRefreshToken() {
    if (!refreshToken.value) return false
    try {
      const data = await apiRefreshToken(refreshToken.value)
      const nextToken = (data as any).access_token as string
      const nextRefreshToken = ((data as any).refresh_token as string | undefined) || refreshToken.value
      token.value = nextToken
      refreshToken.value = nextRefreshToken
      localStorage.setItem('jwt_token', nextToken)
      localStorage.setItem('jwt_refresh_token', nextRefreshToken)
      return true
    } catch {
      token.value = null
      refreshToken.value = null
      user.value = null
      localStorage.removeItem('jwt_token')
      localStorage.removeItem('jwt_refresh_token')
      return false
    }
  }

  return {
    user,
    token,
    refreshToken,
    loading,
    isAuthenticated,
    isAdmin,
    displayName,
    modules,
    moduleKeys,
    firstAllowedPath,
    canAccessModule,
    login,
    logout,
    fetchMe,
    doRefreshToken,
  }
})
