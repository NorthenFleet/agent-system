import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const clusterApi = vi.hoisted(() => ({
  getClusterMonitoring: vi.fn()
}))

vi.mock('@/api/clusterMonitoring', async importOriginal => ({
  ...(await importOriginal<typeof import('@/api/clusterMonitoring')>()),
  getClusterMonitoring: clusterApi.getClusterMonitoring
}))

import ClusterMonitoringPanel from '@/components/monitoring/ClusterMonitoringPanel.vue'
import type { ClusterExecutionPreparation, ClusterMonitoringSnapshot, ClusterNode } from '@/api/clusterMonitoring'

function node(overrides: Partial<ClusterNode> = {}): ClusterNode {
  return {
    node_id: 'mac-mini-01',
    tailscale_id: 'node-ts-01',
    hostname: 'apple-mac-mini',
    dns_name: 'apple-mac-mini.tail.example.ts.net',
    addresses: ['100.81.208.50'],
    os: 'macOS',
    role: 'control',
    managed: true,
    identity_status: 'confirmed',
    legacy_device_id: null,
    domain_refs: {},
    maintenance: false,
    network: { state: 'online', observed_at: '2026-09-25T01:00:00Z', expired: false },
    telemetry: {
      state: 'fresh',
      observed_at: '2026-09-25T01:00:00Z',
      source: 'ssh',
      error: null,
      metrics: {
        cpu_percent: 0,
        memory_percent: 42.5,
        memory_available_bytes: 8589934592,
        disk_free_bytes: 107374182400,
        architecture: 'arm64',
        hardware_model: 'Macmini9,1',
        cpu_logical_count: 8,
        memory_total_bytes: 17179869184,
        docker_state: 'ready',
        docker_version: '27.1.1',
        gpus: null
      }
    },
    services: [{ name: 'openclaw-3021', state: 'healthy', observed_at: '2026-09-25T01:00:00Z' }],
    scheduling: { eligible: false, reason: 'phase_2_read_only' },
    ...overrides
  }
}

function snapshot(nodes: ClusterNode[], discovery: ClusterMonitoringSnapshot['discovery']['state'] = 'fresh'): ClusterMonitoringSnapshot {
  return {
    schema_version: 'cluster-monitoring.v1',
    generated_at: '2026-09-25T01:00:00Z',
    mode: 'read_only',
    discovery: { state: discovery, observed_at: '2026-09-25T01:00:00Z', error: null },
    nodes
  }
}

function execution(
  nodes: ClusterExecutionPreparation['nodes'] = [{ node_id: 'mac-mini-01', ready: false, blockers: [] }]
): ClusterExecutionPreparation {
  return {
    schema_version: 'cluster-execution-preparation.v1',
    mode: 'preparation_only',
    enabled: false,
    ledger: 'work_runs',
    approval_authority: 'command_center',
    operations: [{
      operation: 'host.info', read_only: true, supported_os: ['linux', 'macOS'], max_timeout_seconds: 15
    }],
    blockers: [
      'execution_not_activated',
      'approval_adapter_not_connected',
      'dedicated_credentials_not_configured'
    ],
    nodes
  }
}

let wrappers: VueWrapper[] = []

async function mountPanel() {
  const wrapper = mount(ClusterMonitoringPanel, { props: { pollIntervalMs: 60000 } })
  wrappers.push(wrapper)
  await flushPromises()
  return wrapper
}

describe('ClusterMonitoringPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    wrappers.forEach(wrapper => wrapper.unmount())
    wrappers = []
  })

  it('独立展示陈旧、缺失、在线但未就绪状态，缺失指标不伪装为 0', async () => {
    const nodes = Array.from({ length: 7 }, (_, index) => node({
      node_id: `node-${index + 1}`,
      tailscale_id: `tailscale-${index + 1}`,
      hostname: `cluster-node-${index + 1}`
    }))
    nodes[0] = node({
      node_id: 'online-unready',
      hostname: 'online-unready',
      identity_status: 'unconfirmed',
      telemetry: { state: 'missing', observed_at: null, source: null, error: 'collector_not_configured', metrics: {} },
      services: []
    })
    nodes[1] = node({
      node_id: 'stale-node',
      hostname: 'stale-node',
      telemetry: {
        state: 'stale', observed_at: '2026-09-24T01:00:00Z', source: 'ssh', error: 'secret raw stderr',
        metrics: { cpu_percent: null, memory_percent: null }
      },
      services: [{ name: 'old-service', state: 'healthy', observed_at: '2026-09-24T01:00:00Z' }]
    })
    clusterApi.getClusterMonitoring.mockResolvedValue(snapshot(nodes, 'fresh'))

    const wrapper = await mountPanel()

    expect(wrapper.text()).toContain('7 台受管节点')
    expect(wrapper.text()).toContain('网络在线')
    expect(wrapper.text()).toContain('身份待确认')
    expect(wrapper.text()).toContain('未采集')
    expect(wrapper.text()).toContain('数据陈旧')
    expect(wrapper.text()).toContain('服务未知')
    expect(wrapper.text()).toContain('不可调度')
    expect(wrapper.text()).toContain('0.0%')
    expect(wrapper.text()).toContain('Macmini9,1')
    expect(wrapper.text()).toContain('27.1.1')
    expect(wrapper.text()).toContain('采集器未配置')
    expect(wrapper.text()).toContain('采集异常')
    expect(wrapper.text()).not.toContain('secret raw stderr')
    const staleCard = wrapper.findAll('.cluster-node-card').find(card => card.text().includes('stale-node'))
    expect(staleCard?.text()).toContain('服务状态陈旧')
    expect(staleCard?.text()).toContain('old-service · 上次：健康')
  })

  it('硬件遥测失败时仍独立显示新鲜 HTTP 服务健康', async () => {
    clusterApi.getClusterMonitoring.mockResolvedValue(snapshot([
      node({
        telemetry: {
          state: 'error', observed_at: null, source: 'ssh', error: 'ssh_unavailable', metrics: {}
        },
        services: [{ name: 'openclaw-3021', state: 'healthy', observed_at: '2026-09-25T01:00:00Z' }]
      })
    ]))

    const wrapper = await mountPanel()

    expect(wrapper.text()).toContain('采集失败')
    expect(wrapper.text()).toContain('SSH 不可用')
    expect(wrapper.text()).toContain('服务健康')
    expect(wrapper.text()).toContain('openclaw-3021 · 健康')
    expect(wrapper.find('.service-chip.service-healthy').exists()).toBe(true)
  })

  it('节点发现陈旧时遮蔽旧网络在线状态，但保留独立的新鲜遥测结果', async () => {
    clusterApi.getClusterMonitoring.mockResolvedValue(snapshot([node()], 'stale'))

    const wrapper = await mountPanel()

    expect(wrapper.text()).toContain('节点发现状态：数据陈旧')
    expect(wrapper.text()).toContain('快照陈旧')
    expect(wrapper.text()).not.toContain('网络在线')
    expect(wrapper.find('.cluster-node-card.network-online').exists()).toBe(false)
    expect(wrapper.text()).toContain('数据新鲜')
    expect(wrapper.text()).toContain('服务健康')
  })

  it('把未纳管历史节点与受管节点分区且默认折叠', async () => {
    clusterApi.getClusterMonitoring.mockResolvedValue(snapshot([
      node(),
      node({ node_id: 'old-peer', tailscale_id: 'old-ts', hostname: 'old-windows', managed: false })
    ]))

    const wrapper = await mountPanel()
    const details = wrapper.get('details.unmanaged-peers')

    expect(wrapper.get('[data-testid="managed-node-grid"]').findAll('.cluster-node-card')).toHaveLength(1)
    expect(details.attributes('open')).toBeUndefined()
    expect(details.text()).toContain('未纳管 / 历史 Tailscale 节点（1）')
    expect(details.text()).toContain('old-windows')
  })

  it('请求失败时保留上次快照并标陈旧，恢复后更新并清除告警', async () => {
    clusterApi.getClusterMonitoring.mockResolvedValueOnce(snapshot([node()]))
    const wrapper = await mountPanel()

    expect(wrapper.text()).toContain('apple-mac-mini')
    clusterApi.getClusterMonitoring.mockRejectedValueOnce(new Error('offline'))
    await (wrapper.vm as unknown as { refresh: () => Promise<void> }).refresh()
    await flushPromises()

    expect(wrapper.text()).toContain('apple-mac-mini')
    expect(wrapper.get('[role="alert"]').text()).toContain('保留上次成功快照')
    expect(wrapper.text()).not.toContain('网络在线')
    expect(wrapper.text()).not.toContain('服务健康')
    expect(wrapper.find('.cluster-node-card.network-online').exists()).toBe(false)
    expect(wrapper.find('.service-chip.service-healthy').exists()).toBe(false)
    expect(wrapper.text()).toContain('快照陈旧')

    clusterApi.getClusterMonitoring.mockResolvedValueOnce(snapshot([
      node({ hostname: 'apple-mac-mini-recovered' })
    ]))
    await (wrapper.vm as unknown as { refresh: () => Promise<void> }).refresh()
    await flushPromises()

    expect(wrapper.text()).toContain('apple-mac-mini-recovered')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })

  it('已有请求未完成时不会启动重叠轮询', async () => {
    let resolveRequest!: (value: ClusterMonitoringSnapshot) => void
    clusterApi.getClusterMonitoring.mockImplementation(() => new Promise(resolve => {
      resolveRequest = resolve
    }))

    const wrapper = mount(ClusterMonitoringPanel, { props: { pollIntervalMs: 60000 } })
    wrappers.push(wrapper)
    await flushPromises()
    void (wrapper.vm as unknown as { refresh: () => Promise<void> }).refresh()
    void (wrapper.vm as unknown as { refresh: () => Promise<void> }).refresh()

    expect(clusterApi.getClusterMonitoring).toHaveBeenCalledTimes(1)
    resolveRequest(snapshot([node()]))
    await flushPromises()
    expect(wrapper.text()).toContain('apple-mac-mini')
  })

  it('卸载时取消未完成请求并清理轮询生命周期', async () => {
    clusterApi.getClusterMonitoring.mockImplementation(() => new Promise(() => undefined))
    const wrapper = mount(ClusterMonitoringPanel, { props: { pollIntervalMs: 60000 } })
    wrappers.push(wrapper)
    await flushPromises()

    const signal = clusterApi.getClusterMonitoring.mock.calls[0][0] as AbortSignal
    expect(signal.aborted).toBe(false)
    wrapper.unmount()
    expect(signal.aborted).toBe(true)
  })

  it('展示默认关闭的受控执行准备信息且不提供操作按钮', async () => {
    clusterApi.getClusterMonitoring.mockResolvedValue({
      ...snapshot([node()]),
      execution: execution()
    })

    const wrapper = await mountPanel()
    const panel = wrapper.get('[data-testid="execution-preparation"]')

    expect(panel.text()).toContain('受控执行准备')
    expect(panel.text()).toContain('未启用')
    expect(panel.text()).toContain('host.info（只读主机信息）')
    expect(panel.text()).toContain('Linux / macOS')
    expect(panel.text()).toContain('最长 15 秒')
    expect(panel.text()).toContain('指挥中心')
    expect(panel.text()).toContain('工作运行台账（work_runs）')
    expect(panel.text()).toContain('执行能力尚未激活')
    expect(panel.findAll('button')).toHaveLength(0)
  })

  it('逐节点展示准备阻塞项，空阻塞也明确保持不可执行', async () => {
    const compute = node({
      node_id: 'compute-linux-01', tailscale_id: 'compute-ts-01', hostname: 'compute-linux-01', role: 'compute'
    })
    clusterApi.getClusterMonitoring.mockResolvedValue({
      ...snapshot([node(), compute]),
      execution: execution([
        { node_id: 'mac-mini-01', ready: false, blockers: ['identity_unconfirmed', 'maintenance'] },
        { node_id: 'compute-linux-01', ready: false, blockers: [] }
      ])
    })

    const wrapper = await mountPanel()
    const rows = wrapper.findAll('.execution-node-row')

    expect(rows[0].text()).toContain('节点身份未确认')
    expect(rows[0].text()).toContain('节点处于维护状态')
    expect(rows[1].text()).toContain('基础观测通过，仍不可执行')
  })

  it('客户端快照陈旧时遮蔽逐节点准备判断', async () => {
    clusterApi.getClusterMonitoring.mockResolvedValueOnce({
      ...snapshot([node()]),
      execution: execution([{ node_id: 'mac-mini-01', ready: false, blockers: ['identity_unconfirmed'] }])
    })
    const wrapper = await mountPanel()
    expect(wrapper.text()).toContain('节点身份未确认')

    clusterApi.getClusterMonitoring.mockRejectedValueOnce(new Error('offline'))
    await (wrapper.vm as unknown as { refresh: () => Promise<void> }).refresh()
    await flushPromises()

    const row = wrapper.get('.execution-node-row')
    expect(row.text()).toContain('快照陈旧，无法判断准备状态')
    expect(row.text()).not.toContain('节点身份未确认')
  })

  it('旧版快照没有 execution 字段时保持兼容并隐藏准备区', async () => {
    clusterApi.getClusterMonitoring.mockResolvedValue(snapshot([node()]))

    const wrapper = await mountPanel()

    expect(wrapper.find('[data-testid="execution-preparation"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('apple-mac-mini')
  })
})
