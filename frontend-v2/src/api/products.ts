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

export interface ProductDeliverableSummary {
  total: number
  accepted: number
  pending_review: number
  latest?: {
    id: string
    title: string
    kind: string
    status: string
    version?: string
    created_at?: string
  } | null
}

export interface ProductRelease {
  id: string
  version: string
  environment: string
  status: string
  deployment_url?: string
  released_at?: string
  source_deliverable_id?: string
  release_note?: string
  released_by_agent_id?: string
}

export interface ProductDeliverable {
  id: string
  product_id: string
  project_id?: string
  task_id?: string
  kind: string
  title: string
  uri?: string
  version?: string
  status: string
  summary?: string
  produced_by_agent_id?: string
  created_at?: string
  reviewed_at?: string
  review_note?: string
}

export interface ProductRuntimeInstance {
  id: string
  product_id: string
  name: string
  environment: string
  state: string
  release_id?: string
  version?: string
  device?: string
  host?: string
  port?: number | null
  public_url?: string
  health_url?: string
  summary?: string
  metadata?: Record<string, unknown>
  created_at?: string
  updated_at?: string
  last_observed_at?: string
}

export interface ProductEvent {
  id: string
  product_id: string
  event_type: string
  payload?: Record<string, unknown>
  created_at?: string
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
  tags?: string[]
  dependencies?: ProductDependency[]
  runtime?: ProductRuntime
  project_references?: ProductProjectReference[]
  usage_count?: number
  delivery_summary?: ProductDeliverableSummary
  current_release?: ProductRelease | null
  runtime_instances?: ProductRuntimeInstance[]
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

export function getProductDeliverables(productId: string) {
  return apiClient.get<{ deliverables: ProductDeliverable[] }>(
    `/api/v2/products/${encodeURIComponent(productId)}/deliverables`
  ).then(response => response.data.deliverables)
}

export function getProductReleases(productId: string) {
  return apiClient.get<{ releases: ProductRelease[] }>(
    `/api/v2/products/${encodeURIComponent(productId)}/releases`
  ).then(response => response.data.releases)
}

export function getProductTimeline(productId: string) {
  return apiClient.get<{ events: ProductEvent[] }>(
    `/api/v2/products/${encodeURIComponent(productId)}/timeline`
  ).then(response => response.data.events)
}

export function createProduct(payload: Omit<RegisteredProduct, 'runtime' | 'project_references' | 'usage_count' | 'delivery_summary' | 'current_release' | 'runtime_instances'>) {
  return apiClient.post<RegisteredProduct>('/api/v2/products', payload).then(response => response.data)
}

export function updateProduct(productId: string, payload: Partial<RegisteredProduct>) {
  return apiClient.put<RegisteredProduct>(`/api/v2/products/${encodeURIComponent(productId)}`, payload).then(response => response.data)
}

export function deleteProduct(productId: string) {
  return apiClient.delete<{ deleted: boolean; product_id: string }>(
    `/api/v2/products/${encodeURIComponent(productId)}`
  ).then(response => response.data)
}

export function submitProductDeliverable(productId: string, payload: Omit<ProductDeliverable, 'id' | 'product_id' | 'status' | 'created_at' | 'reviewed_at'>) {
  return apiClient.post<ProductDeliverable>(
    `/api/v2/products/${encodeURIComponent(productId)}/deliverables`,
    payload
  ).then(response => response.data)
}

export function reviewProductDeliverable(productId: string, deliverableId: string, payload: { accepted: boolean; reviewed_by_agent_id: string; review_note?: string }) {
  return apiClient.post<ProductDeliverable>(
    `/api/v2/products/${encodeURIComponent(productId)}/deliverables/${encodeURIComponent(deliverableId)}/review`,
    payload
  ).then(response => response.data)
}

export function createProductRelease(productId: string, payload: Omit<ProductRelease, 'id' | 'product_id' | 'created_at' | 'released_at'>) {
  return apiClient.post<ProductRelease>(
    `/api/v2/products/${encodeURIComponent(productId)}/releases`,
    payload
  ).then(response => response.data)
}

export function getProductRuntimeInstances(productId: string) {
  return apiClient.get<{ runtime_instances: ProductRuntimeInstance[] }>(
    `/api/v2/products/${encodeURIComponent(productId)}/runtimes`
  ).then(response => response.data.runtime_instances)
}

export function createProductRuntimeInstance(productId: string, payload: Omit<ProductRuntimeInstance, 'id' | 'product_id' | 'created_at' | 'updated_at'>) {
  return apiClient.post<ProductRuntimeInstance>(
    `/api/v2/products/${encodeURIComponent(productId)}/runtimes`,
    payload
  ).then(response => response.data)
}

export function updateProductRuntimeInstance(productId: string, runtimeInstanceId: string, payload: Partial<ProductRuntimeInstance>) {
  return apiClient.patch<ProductRuntimeInstance>(
    `/api/v2/products/${encodeURIComponent(productId)}/runtimes/${encodeURIComponent(runtimeInstanceId)}`,
    payload
  ).then(response => response.data)
}

export function deleteProductRuntimeInstance(productId: string, runtimeInstanceId: string) {
  return apiClient.delete<{ deleted: boolean; runtime_instance_id: string }>(
    `/api/v2/products/${encodeURIComponent(productId)}/runtimes/${encodeURIComponent(runtimeInstanceId)}`
  ).then(response => response.data)
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
