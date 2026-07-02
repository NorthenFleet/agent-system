import apiClient from './client'

export interface LoginResponse {
  access_token: string
  token_type: string
  expires_in: number
  user: {
    id: number
    username: string
    display_name: string
    role: string
    is_active: boolean
    last_login_at: string | null
  }
}

export function login(username: string, password: string) {
  return apiClient.post<LoginResponse>('/api/v2/auth/login', { username, password }).then(r => r.data)
}

export function logout() {
  return apiClient.post('/api/v2/auth/logout').then(r => r.data)
}

export function getMe() {
  return apiClient.get('/api/v2/auth/me').then(r => r.data)
}

export function refreshToken(refresh_token: string) {
  return apiClient.post('/api/v2/auth/refresh', { refresh_token }).then(r => r.data)
}
