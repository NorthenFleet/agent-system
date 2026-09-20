import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const productsApi = vi.hoisted(() => ({
  bindProductToProject: vi.fn(), createProduct: vi.fn(), createProductRelease: vi.fn(),
  createProductRuntimeInstance: vi.fn(), deleteProduct: vi.fn(), deleteProductRuntimeInstance: vi.fn(),
  downloadProductAsset: vi.fn(), getProductDeliverables: vi.fn(), getProductRegistry: vi.fn(),
  getProductReleases: vi.fn(), getProductRuntimeInstances: vi.fn(), getProductTimeline: vi.fn(),
  reviewProductDeliverable: vi.fn(), submitProductDeliverable: vi.fn(), syncProductRuntimeHealth: vi.fn(),
  syncProductRuntimeInstanceHealth: vi.fn(), unbindProductFromProject: vi.fn(), updateProduct: vi.fn(),
  updateProductRuntimeInstance: vi.fn()
}))
const projectsApi = vi.hoisted(() => ({ getProjects: vi.fn() }))

vi.mock('@/api/products', () => productsApi)
vi.mock('@/api/projects', () => projectsApi)

import ProductOverview from '@/components/common/ProductOverview.vue'
import Products from '@/views/Products.vue'

const registry = {
  schema: 'product-registry', version: 2, updated_at: '2026-09-17T00:00:00Z',
  products: [
    {
      id: 'openclaw-3021', name: 'OpenClaw 智能体系统', short_name: 'OpenClaw', kind: 'platform',
      category: '总体平台', description: '统一管理任务、项目、知识和产品', positioning: '智能体业务的统一入口',
      status: 'active', owner: 'optimus', version: 'v2.0', capabilities: ['任务编排'], value_props: ['统一管理'],
      portfolio_group: 'platform', display_order: 1, runtime: { state: 'online', online: true, summary: '服务正常' },
      usage_count: 3, delivery_summary: { total: 2, accepted: 1, pending_review: 1 }, project_references: [], runtime_instances: []
    },
    {
      id: 'ai-planning-5130', name: '智能筹划系统', short_name: '智能筹划', kind: 'service',
      category: '规划能力', description: '任务拆解与重规划', positioning: '将业务目标转换为可执行计划',
      status: 'active', owner: 'optimus', version: 'v1.0', capabilities: ['计划生成'], portfolio_group: 'capability',
      display_order: 2, runtime: { state: 'online', online: true, summary: '服务正常' }, usage_count: 2,
      delivery_summary: { total: 0, accepted: 0, pending_review: 0 }, project_references: [], runtime_instances: []
    },
    {
      id: 'one-sim', name: 'One-Sim 仿真系统', short_name: 'One-Sim', kind: 'simulation', category: '仿真',
      description: '验证规划执行效果', status: 'developing', owner: 'perceptor', version: 'v0.8', capabilities: ['仿真验证'],
      portfolio_group: 'capability', display_order: 3, runtime: { state: 'offline', online: false, summary: '待启动' },
      usage_count: 1, delivery_summary: { total: 0, accepted: 0, pending_review: 0 }, project_references: [], runtime_instances: []
    }
  ],
  dependencies: [
    { from: 'openclaw-3021', product_id: 'ai-planning-5130', type: 'uses' },
    { from: 'ai-planning-5130', product_id: 'one-sim', type: 'validates' }
  ],
  summary: { total: 3, online: 2, offline: 1, project_bindings: 6 }
}

let wrappers: VueWrapper[] = []

async function testRouter(initialPath = '/products') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/products', name: 'Products', component: Products },
      { path: '/products/:productId', name: 'ProductDetail', component: { template: '<div>detail</div>' } },
      { path: '/projects', name: 'Projects', component: { template: '<div>projects</div>' } }
    ]
  })
  await router.push(initialPath)
  await router.isReady()
  return router
}

async function mountProducts(path = '/products') {
  const router = await testRouter(path)
  const wrapper = mount(Products, { global: { plugins: [ElementPlus, router] } })
  wrappers.push(wrapper)
  await flushPromises()
  return { wrapper, router }
}

describe('Products 产品注册表', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    productsApi.getProductRegistry.mockResolvedValue(structuredClone(registry))
    productsApi.getProductDeliverables.mockResolvedValue([])
    productsApi.getProductReleases.mockResolvedValue([])
    productsApi.getProductRuntimeInstances.mockResolvedValue([])
    productsApi.getProductTimeline.mockResolvedValue([])
    projectsApi.getProjects.mockResolvedValue({
      projects: [{ id: 'project-1', name: '生产系统', status: 'active', progress: 30, product_bindings: [] }]
    })
  })

  afterEach(() => {
    wrappers.forEach(wrapper => wrapper.unmount())
    wrappers = []
    vi.restoreAllMocks()
  })

  it('渲染实际注册指标、产品体系和运行状态', async () => {
    const { wrapper } = await mountProducts()

    expect(wrapper.text()).toContain('产品矩阵')
    expect(wrapper.text()).toContain('OpenClaw 智能体系统')
    expect(wrapper.text()).toContain('智能筹划系统')
    expect(wrapper.text()).toContain('One-Sim 仿真系统')
    expect(wrapper.text()).toContain('在线系统2')
    expect(wrapper.findAll('.product-card')).toHaveLength(3)
  })

  it('根据路由查询选中产品和项目上下文', async () => {
    const { wrapper } = await mountProducts('/products?product_id=ai-planning-5130&project_id=project-1')

    expect((wrapper.vm as any).selectedProduct.id).toBe('ai-planning-5130')
    expect(wrapper.text()).toContain('当前项目')
    expect(wrapper.text()).toContain('生产系统')
  })

  it('点击产品卡片进入产品详情', async () => {
    const { wrapper, router } = await mountProducts()

    await wrapper.findAll('.product-card')[1].trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('ProductDetail')
    expect(router.currentRoute.value.params.productId).toBe('ai-planning-5130')
  })

  it('注册表请求失败后正确结束 loading', async () => {
    productsApi.getProductRegistry.mockRejectedValue(new Error('registry unavailable'))
    const { wrapper } = await mountProducts()

    expect((wrapper.vm as any).loading).toBe(false)
    expect(wrapper.findAll('.product-card')).toHaveLength(0)
  })

  it('空注册表不会生成伪产品或选中项', async () => {
    productsApi.getProductRegistry.mockResolvedValue({
      ...structuredClone(registry), products: [], dependencies: [],
      summary: { total: 0, online: 0, offline: 0, project_bindings: 0 }
    })
    const { wrapper } = await mountProducts()

    expect(wrapper.findAll('.product-card')).toHaveLength(0)
    expect((wrapper.vm as any).selectedProduct).toBeUndefined()
  })
})

describe('ProductOverview 产品概览', () => {
  afterEach(() => {
    wrappers.forEach(wrapper => wrapper.unmount())
    wrappers = []
  })

  it('在 API 不可用时使用明确的本地降级数据', async () => {
    vi.mocked(global.fetch).mockRejectedValueOnce(new Error('offline'))
    const router = await testRouter()
    const wrapper = mount(ProductOverview, { global: { plugins: [ElementPlus, router] } })
    wrappers.push(wrapper)
    await flushPromises()

    expect(wrapper.text()).toContain('手工纸质兵棋')
    expect(wrapper.text()).toContain('查看')
  })
})
