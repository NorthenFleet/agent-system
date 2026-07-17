import apiClient from './client'
import type { Project } from './projects'

export interface ProductDependency {
  product_id: string
  type: string
  description?: string
}

export interface ProductDeployment {
  device?: string
  host?: string
  port?: number
  public_url?: string
  mode?: string
}

export interface ProductRuntime {
  state: 'online' | 'offline' | 'managed' | string
  online?: boolean | null
  summary?: string
  error_code?: string
  details?: Record<string, unknown>
}

export interface ProductProjectReference {
  project_id: string
  project_name: string
  role?: string
  status?: string
}

export interface RegisteredProduct {
  id: string
  name: string
  kind: string
  category?: string
  description?: string
  version?: string
  status?: string
  owner?: string
  repository?: string
  deployment?: ProductDeployment
  capabilities?: string[]
  dependencies?: ProductDependency[]
  runtime?: ProductRuntime
  project_references?: ProductProjectReference[]
  usage_count?: number
}

export interface ProductRegistryResponse {
  schema: string
  version: number
  updated_at?: string
  products: RegisteredProduct[]
  dependencies: Array<ProductDependency & { from: string }>
  summary: {
    total: number
    online: number
    offline: number
    project_bindings: number
  }
}

export function getProductRegistry() {
  return apiClient.get<ProductRegistryResponse>('/api/v2/products').then(response => response.data)
}

export function getProduct(productId: string) {
  return apiClient.get<RegisteredProduct>(`/api/v2/products/${encodeURIComponent(productId)}`).then(response => response.data)
}

export function bindProductToProject(
  projectId: string,
  productId: string,
  payload: { role?: string; status?: string; config?: Record<string, unknown> }
) {
  return apiClient.put<{ project: Project; binding: ProjectProductBinding }>(
    `/api/v2/products/projects/${encodeURIComponent(projectId)}/bindings/${encodeURIComponent(productId)}`,
    payload
  ).then(response => response.data)
}

export function unbindProductFromProject(projectId: string, productId: string) {
  return apiClient.delete<{ project: Project; removed: string }>(
    `/api/v2/products/projects/${encodeURIComponent(projectId)}/bindings/${encodeURIComponent(productId)}`
  ).then(response => response.data)
}

export interface ProjectProductBinding {
  id: string
  project_id: string
  product_id: string
  role?: string
  status?: string
  source?: string
  bound_at?: string
  updated_at?: string
  config?: Record<string, unknown>
}
