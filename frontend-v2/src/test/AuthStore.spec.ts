import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const api = vi.hoisted(() => ({
  createDevelopmentSession: vi.fn(),
  getAuthSettings: vi.fn(),
  getMe: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
  refreshToken: vi.fn()
}))

vi.mock('@/api/auth', () => api)

import { useAuthStore } from '@/stores/auth'

const admin = {
  id: 1,
  username: 'admin',
  display_name: '管理员',
  role: 'admin' as const,
  is_active: true,
  last_login_at: null,
  module_keys: ['dashboard'],
  modules: [{ id: 1, module_key: 'dashboard', name: '仪表盘', route_path: '/', sort_order: 1, is_enabled: true }]
}

describe('auth development mode', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('creates a development session when login is disabled', async () => {
    api.getAuthSettings.mockResolvedValue({ login_enabled: false, mode: 'development' })
    api.createDevelopmentSession.mockResolvedValue({
      access_token: 'development-token',
      token_type: 'Bearer',
      expires_in: 43200,
      auth_mode: 'development',
      user: admin
    })

    const store = useAuthStore()
    await store.loadAuthSettings()
    const ready = await store.ensureDevelopmentSession()

    expect(ready).toBe(true)
    expect(store.loginEnabled).toBe(false)
    expect(store.isAuthenticated).toBe(true)
    expect(store.isAdmin).toBe(true)
    expect(localStorage.getItem('jwt_auth_mode')).toBe('development')
  })

  it('removes a development session when login is enabled again', async () => {
    localStorage.setItem('jwt_token', 'development-token')
    localStorage.setItem('jwt_auth_mode', 'development')
    api.getAuthSettings.mockResolvedValue({ login_enabled: true, mode: 'login_required' })

    const store = useAuthStore()
    await store.loadAuthSettings(true)

    expect(store.loginEnabled).toBe(true)
    expect(store.isAuthenticated).toBe(false)
    expect(localStorage.getItem('jwt_token')).toBeNull()
  })
})
