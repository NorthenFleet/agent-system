import apiClient from './client'

export type UserRole = 'admin' | 'agent' | 'viewer'

export interface User {
  id: number
  username: string
  display_name: string
  role: UserRole
  is_active: boolean
  last_login_at: string | null
  module_keys?: string[]
  modules?: FeatureModule[]
}

export interface FeatureModule {
  id: number
  module_key: string
  name: string
  route_path: string
  icon?: string
  description?: string
  sort_order: number
  is_enabled: boolean
  granted?: boolean
}

export interface LoginResponse {
  access_token: string
  token_type: string
  expires_in: number
  user: User
}

export function login(username: string, password: string) {
  return apiClient.post<LoginResponse>('/api/v2/auth/login', { username, password }).then(r => r.data)
}

export function logout() {
  return apiClient.post('/api/v2/auth/logout').then(r => r.data)
}

export function getMe() {
  return apiClient.get<User>('/api/v2/auth/me').then(r => r.data)
}

export function refreshToken(refresh_token: string) {
  return apiClient.post('/api/v2/auth/refresh', { refresh_token }).then(r => r.data)
}
