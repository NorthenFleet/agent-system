import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  createDevelopmentSession,
  getAuthSettings,
  getMe,
  login as apiLogin,
  logout as apiLogout,
  refreshToken as apiRefreshToken
} from '@/api/auth'
import type { User } from '@/api/auth'

export type { User } from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const token = ref<string | null>(localStorage.getItem('jwt_token'))
  const refreshToken = ref<string | null>(localStorage.getItem('jwt_refresh_token'))
  const authMode = ref<'authenticated' | 'development'>(
    localStorage.getItem('jwt_auth_mode') === 'development' ? 'development' : 'authenticated'
  )
  const loginEnabled = ref(localStorage.getItem('auth_login_enabled') !== 'false')
  const authSettingsLoaded = ref(false)
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

  function clearSession() {
    token.value = null
    refreshToken.value = null
    user.value = null
    authMode.value = 'authenticated'
    localStorage.removeItem('jwt_token')
    localStorage.removeItem('jwt_refresh_token')
    localStorage.removeItem('jwt_auth_mode')
  }

  function persistSession(data: any, mode: 'authenticated' | 'development') {
    token.value = data.access_token
    refreshToken.value = data.refresh_token || null
    user.value = data.user
    authMode.value = mode
    localStorage.setItem('jwt_token', data.access_token)
    localStorage.setItem('jwt_auth_mode', mode)
    if (refreshToken.value) localStorage.setItem('jwt_refresh_token', refreshToken.value)
    else localStorage.removeItem('jwt_refresh_token')
  }

  async function loadAuthSettings(force = false) {
    if (authSettingsLoaded.value && !force) return loginEnabled.value
    try {
      const data = await getAuthSettings()
      loginEnabled.value = data.login_enabled
      authSettingsLoaded.value = true
      localStorage.setItem('auth_login_enabled', String(data.login_enabled))
      if (data.login_enabled && authMode.value === 'development') clearSession()
    } catch {
      loginEnabled.value = true
      authSettingsLoaded.value = true
      localStorage.setItem('auth_login_enabled', 'true')
    }
    return loginEnabled.value
  }

  async function ensureDevelopmentSession() {
    if (loginEnabled.value) return false
    if (token.value && await fetchMe()) return true
    try {
      const data = await createDevelopmentSession()
      persistSession(data, 'development')
      return true
    } catch {
      clearSession()
      return false
    }
  }

  async function login(username: string, password: string) {
    loading.value = true
    try {
      const data = await apiLogin(username, password)
      persistSession(data, 'authenticated')
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
    clearSession()
  }

  async function fetchMe() {
    if (!token.value) return false
    try {
      user.value = await getMe()
      return true
    } catch {
      clearSession()
      return false
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
      clearSession()
      return false
    }
  }

  return {
    user,
    token,
    refreshToken,
    authMode,
    loginEnabled,
    authSettingsLoaded,
    loading,
    isAuthenticated,
    isAdmin,
    displayName,
    modules,
    moduleKeys,
    firstAllowedPath,
    canAccessModule,
    loadAuthSettings,
    ensureDevelopmentSession,
    login,
    logout,
    fetchMe,
    doRefreshToken,
  }
})
