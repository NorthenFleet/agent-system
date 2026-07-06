import apiClient from './client'
import type { FeatureModule, User, UserRole } from './auth'

export interface UserCreatePayload {
  username: string
  password: string
  display_name: string
  role: UserRole
  email?: string
}

export interface UserUpdatePayload {
  display_name?: string
  role?: UserRole
  email?: string
  password?: string
  is_active?: boolean
}

export function listUsers() {
  return apiClient.get<{ users: User[]; total: number }>('/api/v2/users').then(r => r.data)
}

export function createUser(payload: UserCreatePayload) {
  return apiClient.post<{ success: boolean; user: User }>('/api/v2/users', payload).then(r => r.data)
}

export function updateUser(userId: number, payload: UserUpdatePayload) {
  return apiClient.put<{ success: boolean; user: User }>(`/api/v2/users/${userId}`, payload).then(r => r.data)
}

export function deleteUser(userId: number) {
  return apiClient.delete<{ success: boolean; message: string }>(`/api/v2/users/${userId}`).then(r => r.data)
}

export function listModules() {
  return apiClient.get<{ modules: FeatureModule[]; total: number }>('/api/v2/modules').then(r => r.data)
}

export function getUserModules(userId: number) {
  return apiClient.get<{ user: User; modules: FeatureModule[]; module_keys: string[] }>(`/api/v2/modules/users/${userId}`).then(r => r.data)
}

export function updateUserModules(userId: number, moduleKeys: string[]) {
  return apiClient.put<{ success: boolean; user: User; modules: FeatureModule[]; module_keys: string[] }>(
    `/api/v2/modules/users/${userId}`,
    { module_keys: moduleKeys }
  ).then(r => r.data)
}
