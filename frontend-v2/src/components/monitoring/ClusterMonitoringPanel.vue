<template>
  <section class="cluster-panel" :class="{ 'fetch-stale': clientSnapshotStale }">
    <div class="cluster-heading">
      <div>
        <h2>🖥️ 集群设备</h2>
        <p>网络、采集、服务与身份状态独立展示 · 第一、二阶段只读</p>
      </div>
      <div class="cluster-heading-status">
        <span class="managed-count">{{ snapshot ? `${managedNodes.length} 台受管节点` : '节点清单加载中' }}</span>
        <span v-if="clientSnapshotStale" class="stale-badge">快照陈旧</span>
        <span class="readonly-badge">调度已禁用</span>
      </div>
    </div>

    <div v-if="clientSnapshotStale" class="cluster-fetch-warning" role="alert">
      {{ fetchFailed ? '集群监控请求失败' : '集群监控刷新超时' }}，当前保留上次成功快照并标记为陈旧。
    </div>
    <div
      v-else-if="snapshot && snapshot.discovery.state !== 'fresh'"
      class="cluster-discovery-warning"
      role="status"
    >
      节点发现状态：{{ collectionStateLabel(snapshot.discovery.state) }}；显示数据可能不完整。
    </div>

    <div v-if="!snapshot && loading" class="cluster-placeholder">正在加载集群清单…</div>
    <div v-else-if="!snapshot" class="cluster-placeholder">集群清单暂不可用</div>

    <div v-else class="cluster-grid" data-testid="managed-node-grid">
      <article
        v-for="node in managedNodes"
        :key="node.node_id"
        class="cluster-node-card"
        :class="[networkCardClass(node), { maintenance: node.maintenance, 'snapshot-stale': clientSnapshotStale }]"
      >
        <header class="node-header">
          <div>
            <strong>{{ node.hostname || node.node_id }}</strong>
            <small>{{ node.node_id }} · {{ node.role || '角色待确认' }}</small>
          </div>
          <span class="identity-badge" :class="`identity-${node.identity_status}`">
            {{ node.identity_status === 'confirmed' ? '身份已确认' : '身份待确认' }}
          </span>
        </header>

        <div class="status-grid">
          <div class="status-item">
            <span>网络</span>
            <strong :class="`state-${displayNetworkState(node)}`">{{ displayNetworkLabel(node) }}</strong>
            <small>{{ observationText(node.network.observed_at, node.network.expired) }}</small>
          </div>
          <div class="status-item">
            <span>遥测</span>
            <strong :class="`state-${displayTelemetryState(node)}`">{{ displayTelemetryLabel(node) }}</strong>
            <small>{{ observationText(node.telemetry.observed_at) }}</small>
          </div>
          <div class="status-item">
            <span>服务</span>
            <strong :class="`state-${displayServiceSummary(node).state}`">{{ displayServiceSummary(node).label }}</strong>
            <small>{{ node.services.length ? `${node.services.length} 项探测` : '未上报服务' }}</small>
          </div>
          <div class="status-item">
            <span>调度</span>
            <strong class="state-disabled">不可调度</strong>
            <small>{{ schedulingReasonLabel(node.scheduling.reason) }}</small>
          </div>
        </div>

        <div class="metric-grid" :class="{ 'historical-metrics': clientSnapshotStale }">
          <div><span>CPU</span><strong>{{ percentMetric(node.telemetry.metrics.cpu_percent) }}</strong></div>
          <div><span>CPU 核数</span><strong>{{ countMetric(node.telemetry.metrics.cpu_logical_count) }}</strong></div>
          <div><span>内存</span><strong>{{ percentMetric(node.telemetry.metrics.memory_percent) }}</strong></div>
          <div><span>总内存</span><strong>{{ bytesMetric(node.telemetry.metrics.memory_total_bytes) }}</strong></div>
          <div><span>可用内存</span><strong>{{ bytesMetric(node.telemetry.metrics.memory_available_bytes) }}</strong></div>
          <div><span>可用磁盘</span><strong>{{ bytesMetric(node.telemetry.metrics.disk_free_bytes) }}</strong></div>
          <div><span>硬件型号</span><strong>{{ node.telemetry.metrics.hardware_model || '未采集' }}</strong></div>
          <div><span>架构</span><strong>{{ node.telemetry.metrics.architecture || '未采集' }}</strong></div>
          <div><span>GPU</span><strong>{{ gpuMetric(node) }}</strong></div>
          <div><span>Docker</span><strong>{{ dockerMetric(node) }}</strong></div>
        </div>

        <div v-if="node.telemetry.error" class="telemetry-error">
          采集说明：{{ telemetryErrorLabel(node.telemetry.error) }}
        </div>

        <div class="node-address">{{ node.dns_name || node.addresses[0] || '地址未发现' }}</div>
        <div v-if="node.services.length" class="service-list">
          <span
            v-for="service in node.services"
            :key="service.name"
            class="service-chip"
            :class="serviceIsStale(service) ? 'service-stale' : `service-${service.state}`"
          >
            {{ service.name }} · {{ serviceIsStale(service) ? `上次：${serviceStateLabel(service.state)}` : serviceStateLabel(service.state) }}
          </span>
        </div>
      </article>
    </div>

    <section v-if="snapshot?.execution" class="execution-preparation" data-testid="execution-preparation">
      <header class="execution-header">
        <div>
          <h3>🛡️ 受控执行准备</h3>
          <p>仅展示启用前条件；当前没有远程执行入口。</p>
        </div>
        <span class="execution-disabled">未启用</span>
      </header>

      <div class="execution-governance">
        <div>
          <span>审批权威</span>
          <strong>{{ executionOwnerLabel(snapshot.execution.approval_authority) }}</strong>
        </div>
        <div>
          <span>执行台账</span>
          <strong>{{ executionLedgerLabel(snapshot.execution.ledger) }}</strong>
        </div>
      </div>

      <div class="execution-operations">
        <span>允许操作</span>
        <div v-if="snapshot.execution.operations.length" class="operation-list">
          <div v-for="operation in snapshot.execution.operations" :key="operation.operation" class="operation-item">
            <strong>{{ operationLabel(operation.operation) }}</strong>
            <small>
              {{ operation.read_only ? '只读' : '非只读' }} ·
              {{ operation.supported_os.map(supportedOsLabel).join(' / ') || '无支持系统' }} ·
              最长 {{ operation.max_timeout_seconds }} 秒
            </small>
          </div>
        </div>
        <strong v-else>未声明允许操作</strong>
      </div>

      <div class="execution-blockers">
        <span>全局阻塞项</span>
        <div class="blocker-list">
          <span v-for="blocker in snapshot.execution.blockers" :key="blocker" class="blocker-chip">
            {{ executionBlockerLabel(blocker) }}
          </span>
        </div>
      </div>

      <div class="execution-node-list">
        <div
          v-for="nodeState in managedExecutionNodes"
          :key="nodeState.node_id"
          class="execution-node-row"
          :class="{ 'readiness-stale': clientSnapshotStale }"
        >
          <strong>{{ executionNodeName(nodeState.node_id) }}</strong>
          <span v-if="clientSnapshotStale">快照陈旧，无法判断准备状态</span>
          <span v-else-if="nodeState.blockers.length">
            {{ nodeState.blockers.map(executionBlockerLabel).join('、') }}
          </span>
          <span v-else>基础观测通过，仍不可执行</span>
        </div>
      </div>
    </section>

    <details v-if="unmanagedNodes.length" class="unmanaged-peers">
      <summary>未纳管 / 历史 Tailscale 节点（{{ unmanagedNodes.length }}）</summary>
      <div class="unmanaged-list">
        <div v-for="node in unmanagedNodes" :key="node.node_id">
          <strong>{{ node.hostname || node.node_id }}</strong>
          <span>{{ networkStateLabel(node.network.state) }} · 不参与调度</span>
        </div>
      </div>
    </details>

    <footer v-if="snapshot" class="cluster-footer">
      <span>发现：{{ clientSnapshotStale ? '快照陈旧' : collectionStateLabel(snapshot.discovery.state) }}</span>
      <span>快照：{{ dateTimeText(snapshot.generated_at) }}</span>
      <span v-if="loading">刷新中…</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
  getClusterMonitoring,
  type ClusterMonitoringSnapshot,
  type ClusterNode,
  type ClusterServiceStatus,
  type CollectionState,
  type NetworkState,
  type ServiceState
} from '@/api/clusterMonitoring'

const props = withDefaults(defineProps<{ pollIntervalMs?: number }>(), {
  pollIntervalMs: 30000
})

const snapshot = ref<ClusterMonitoringSnapshot | null>(null)
const loading = ref(false)
const fetchFailed = ref(false)
const nowMs = ref(Date.now())
const lastSuccessfulAt = ref<number | null>(null)
let pollTimer: ReturnType<typeof setInterval> | null = null
let mounted = false
let requestController: AbortController | null = null

const managedNodes = computed(() => snapshot.value?.nodes.filter(node => node.managed) ?? [])
const unmanagedNodes = computed(() => snapshot.value?.nodes.filter(node => !node.managed) ?? [])
const managedExecutionNodes = computed(() => {
  const managedIds = new Set(managedNodes.value.map(node => node.node_id))
  return snapshot.value?.execution?.nodes.filter(node => managedIds.has(node.node_id)) ?? []
})
const clientSnapshotStale = computed(() => fetchFailed.value || (
  lastSuccessfulAt.value != null && nowMs.value - lastSuccessfulAt.value >= 90000
))

async function refresh() {
  if (loading.value) return
  loading.value = true
  requestController = new AbortController()
  try {
    const next = await getClusterMonitoring(requestController.signal)
    if (!mounted) return
    snapshot.value = next
    fetchFailed.value = false
    lastSuccessfulAt.value = Date.now()
    nowMs.value = lastSuccessfulAt.value
  } catch {
    if (mounted) fetchFailed.value = true
  } finally {
    if (mounted) {
      loading.value = false
      requestController = null
    }
  }
}

function networkStateLabel(state: NetworkState) {
  return ({ online: '网络在线', offline: '网络离线', unknown: '网络未知' } as const)[state]
}

function collectionStateLabel(state: CollectionState) {
  return ({ fresh: '数据新鲜', stale: '数据陈旧', missing: '未采集', error: '采集失败' } as const)[state]
}

function serviceStateLabel(state: ServiceState) {
  return ({ healthy: '健康', unhealthy: '异常', unknown: '未知' } as const)[state]
}

function serviceSummary(node: ClusterNode): { state: ServiceState; label: string } {
  if (!node.services.length) return { state: 'unknown', label: '服务未知' }
  if (node.services.some(service => service.state === 'unhealthy')) return { state: 'unhealthy', label: '存在异常' }
  if (node.services.some(service => service.state === 'unknown')) return { state: 'unknown', label: '部分未知' }
  return { state: 'healthy', label: '服务健康' }
}

function displayNetworkState(node: ClusterNode): NetworkState | 'stale' {
  if (clientSnapshotStale.value || snapshot.value?.discovery.state !== 'fresh') return 'stale'
  return node.network.state
}

function displayNetworkLabel(node: ClusterNode) {
  return displayNetworkState(node) === 'stale' ? '快照陈旧' : networkStateLabel(node.network.state)
}

function displayTelemetryState(node: ClusterNode): CollectionState {
  return clientSnapshotStale.value ? 'stale' : node.telemetry.state
}

function displayTelemetryLabel(node: ClusterNode) {
  return clientSnapshotStale.value ? '快照陈旧' : collectionStateLabel(node.telemetry.state)
}

function networkCardClass(node: ClusterNode) {
  const state = displayNetworkState(node)
  return `network-${state === 'stale' ? 'unknown' : state}`
}

function displayServiceSummary(node: ClusterNode): { state: ServiceState | 'stale'; label: string } {
  if (clientSnapshotStale.value) return { state: 'stale', label: node.services.length ? '服务状态陈旧' : '服务未知' }
  if (!node.services.length) return { state: 'unknown', label: '服务未知' }
  const current = node.services.filter(service => !serviceIsStale(service))
  if (!current.length) return { state: 'stale', label: '服务状态陈旧' }
  const summary = serviceSummary({ ...node, services: current })
  if (current.length !== node.services.length && summary.state === 'healthy') {
    return { state: 'unknown', label: '部分未知' }
  }
  return summary
}

function serviceIsStale(service: ClusterServiceStatus) {
  if (clientSnapshotStale.value) return true
  if (!service.observed_at || !snapshot.value) return true
  const observedAt = new Date(service.observed_at).getTime()
  const generatedAt = new Date(snapshot.value.generated_at).getTime()
  if (!Number.isFinite(observedAt) || !Number.isFinite(generatedAt)) return true
  const elapsedSinceFetch = lastSuccessfulAt.value == null ? 0 : Math.max(0, nowMs.value - lastSuccessfulAt.value)
  const referenceTime = generatedAt + elapsedSinceFetch
  return observedAt > referenceTime + 5000 || referenceTime - observedAt >= 90000
}

function percentMetric(value: number | null | undefined) {
  return value == null ? '未采集' : `${value.toFixed(1)}%`
}

function bytesMetric(value: number | null | undefined) {
  if (value == null) return '未采集'
  if (value === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1)
  return `${(value / 1024 ** index).toFixed(index >= 3 ? 1 : 0)} ${units[index]}`
}

function countMetric(value: number | null | undefined) {
  return value == null ? '未采集' : String(value)
}

function gpuMetric(node: ClusterNode) {
  const gpus = node.telemetry.metrics.gpus
  if (!gpus?.length) return '未采集'
  return gpus.map(gpu => gpu.name || '未知 GPU').join('、')
}

function dockerMetric(node: ClusterNode) {
  const state = node.telemetry.metrics.docker_state
  if (state === 'ready') return node.telemetry.metrics.docker_version || '可用'
  if (!state || state === 'unknown') return '未采集'
  if (state === 'unavailable') return '不可用'
  return '探测异常'
}

function telemetryErrorLabel(code: string) {
  const labels: Record<string, string> = {
    collector_not_configured: '采集器未配置',
    collection_failed: '采集失败',
    command_failed: '采集命令失败',
    local_identity_mismatch: '本机身份不匹配',
    node_unreachable: '节点不可达',
    parse_failed: '采集结果无法解析',
    probe_failed: '主机探测失败',
    probe_timeout: '主机探测超时',
    probe_unavailable: '主机探测不可用',
    ssh_failed: 'SSH 采集失败',
    ssh_timeout: 'SSH 采集超时',
    ssh_unavailable: 'SSH 不可用',
    unsupported_os: '操作系统暂不支持'
  }
  return labels[code] || '采集异常'
}

function observationText(value: string | null, expired = false) {
  if (expired) return '节点密钥已过期'
  return value ? dateTimeText(value) : '无观测时间'
}

function dateTimeText(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '时间未知' : date.toLocaleString('zh-CN', { hour12: false })
}

function schedulingReasonLabel(reason: string) {
  return reason === 'phase_2_read_only' ? '阶段二只读' : (reason || '原因未上报')
}

function executionOwnerLabel(value: string) {
  return value === 'command_center' ? '指挥中心' : value
}

function executionLedgerLabel(value: string) {
  return value === 'work_runs' ? '工作运行台账（work_runs）' : value
}

function operationLabel(value: string) {
  return value === 'host.info' ? 'host.info（只读主机信息）' : value
}

function supportedOsLabel(value: string) {
  return ({ linux: 'Linux', macOS: 'macOS', windows: 'Windows' } as Record<string, string>)[value] || value
}

function executionBlockerLabel(value: string) {
  const labels: Record<string, string> = {
    execution_not_activated: '执行能力尚未激活',
    approval_adapter_not_connected: '审批适配器未连接',
    dedicated_credentials_not_configured: '专用凭据未配置',
    production_login_required: '需要生产登录模式',
    identity_unconfirmed: '节点身份未确认',
    maintenance: '节点处于维护状态',
    network_unavailable: '节点网络不可用',
    discovery_not_fresh: '节点发现数据不新鲜',
    telemetry_not_fresh: '硬件遥测不新鲜',
    unsupported_os: '操作系统不在允许范围'
  }
  return labels[value] || '未知阻塞项'
}

function executionNodeName(nodeId: string) {
  const node = managedNodes.value.find(item => item.node_id === nodeId)
  return node?.hostname || nodeId
}

onMounted(() => {
  mounted = true
  void refresh()
  pollTimer = setInterval(() => {
    nowMs.value = Date.now()
    void refresh()
  }, props.pollIntervalMs)
})

onUnmounted(() => {
  mounted = false
  requestController?.abort()
  requestController = null
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = null
})

defineExpose({ refresh })
</script>

<style scoped>
.cluster-panel { margin: 26px 0; }
.cluster-heading { display: flex; justify-content: space-between; align-items: flex-end; gap: 16px; margin-bottom: 14px; }
.cluster-heading h2 { margin: 0; font-size: 18px; color: var(--text-primary); }
.cluster-heading p { margin: 5px 0 0; color: var(--text-secondary); font-size: 12px; }
.cluster-heading-status { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
.managed-count, .stale-badge, .readonly-badge { padding: 5px 10px; border-radius: 999px; font-size: 12px; }
.managed-count { color: #58a6ff; background: rgba(88, 166, 255, .1); border: 1px solid rgba(88, 166, 255, .25); }
.stale-badge { color: #f0a7a3; background: rgba(248, 81, 73, .08); border: 1px solid rgba(248, 81, 73, .25); }
.readonly-badge { color: #d29922; background: rgba(210, 153, 34, .1); border: 1px solid rgba(210, 153, 34, .25); }
.cluster-fetch-warning, .cluster-discovery-warning, .cluster-placeholder { margin-bottom: 14px; padding: 10px 12px; border-radius: 8px; font-size: 13px; }
.cluster-fetch-warning { color: #f0a7a3; background: rgba(248, 81, 73, .08); border: 1px solid rgba(248, 81, 73, .25); }
.cluster-discovery-warning { color: #d29922; background: rgba(210, 153, 34, .08); border: 1px solid rgba(210, 153, 34, .25); }
.cluster-placeholder { color: var(--text-secondary); background: var(--card-bg); border: 1px solid var(--line-color); }
.cluster-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.cluster-node-card { padding: 15px; background: var(--card-bg); border: 1px solid var(--line-color); border-left: 4px solid var(--text-secondary); border-radius: 9px; }
.cluster-node-card.network-online { border-left-color: #3fb950; }
.cluster-node-card.network-offline { border-left-color: #f85149; }
.cluster-node-card.maintenance { opacity: .76; }
.cluster-node-card.snapshot-stale { border-left-color: #d29922; }
.fetch-stale .cluster-node-card { border-top-color: rgba(210, 153, 34, .55); }
.node-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }
.node-header strong, .node-header small { display: block; }
.node-header strong { color: var(--text-primary); font-size: 15px; }
.node-header small, .node-address, .cluster-footer { color: var(--text-secondary); font-size: 11px; }
.identity-badge { white-space: nowrap; padding: 3px 8px; border-radius: 999px; font-size: 11px; }
.identity-confirmed { color: #3fb950; background: rgba(63, 185, 80, .1); }
.identity-unconfirmed { color: #d29922; background: rgba(210, 153, 34, .1); }
.status-grid, .metric-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin-top: 14px; }
.status-item, .metric-grid > div { min-width: 0; padding: 8px; background: var(--panel-bg); border: 1px solid var(--line-color); border-radius: 6px; }
.status-item span, .status-item strong, .status-item small, .metric-grid span, .metric-grid strong { display: block; }
.status-item span, .metric-grid span { color: var(--text-secondary); font-size: 10px; }
.status-item strong, .metric-grid strong { margin-top: 3px; color: var(--text-primary); font-size: 12px; overflow-wrap: anywhere; }
.status-item small { margin-top: 3px; color: var(--text-secondary); font-size: 9px; }
.metric-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.historical-metrics { opacity: .62; }
.state-online, .state-fresh, .state-healthy { color: #3fb950 !important; }
.state-offline, .state-error, .state-unhealthy { color: #f85149 !important; }
.state-stale, .state-unconfirmed, .state-disabled { color: #d29922 !important; }
.state-missing, .state-unknown { color: var(--text-secondary) !important; }
.node-address { margin-top: 11px; overflow-wrap: anywhere; }
.telemetry-error { margin-top: 9px; color: #d29922; font-size: 11px; }
.service-list { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 9px; }
.service-chip { padding: 3px 7px; border-radius: 999px; color: var(--text-secondary); background: var(--panel-bg); font-size: 10px; }
.service-healthy { color: #3fb950; }
.service-unhealthy { color: #f85149; }
.service-stale { color: #d29922; }
.execution-preparation { margin-top: 16px; padding: 15px; background: var(--card-bg); border: 1px solid rgba(210, 153, 34, .3); border-radius: 9px; }
.execution-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
.execution-header h3 { margin: 0; color: var(--text-primary); font-size: 15px; }
.execution-header p { margin: 4px 0 0; color: var(--text-secondary); font-size: 11px; }
.execution-disabled { white-space: nowrap; padding: 4px 9px; color: #d29922; background: rgba(210, 153, 34, .1); border: 1px solid rgba(210, 153, 34, .25); border-radius: 999px; font-size: 11px; }
.execution-governance { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-top: 12px; }
.execution-governance > div, .execution-operations, .execution-blockers { padding: 9px; background: var(--panel-bg); border: 1px solid var(--line-color); border-radius: 7px; }
.execution-governance span, .execution-operations > span, .execution-blockers > span { display: block; color: var(--text-secondary); font-size: 10px; }
.execution-governance strong { display: block; margin-top: 3px; color: var(--text-primary); font-size: 12px; }
.execution-operations, .execution-blockers { margin-top: 8px; }
.operation-list, .blocker-list { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 7px; }
.operation-item { padding: 6px 8px; background: var(--card-bg); border: 1px solid var(--line-color); border-radius: 6px; }
.operation-item strong, .operation-item small { display: block; }
.operation-item strong { color: var(--text-primary); font-size: 11px; }
.operation-item small { margin-top: 2px; color: var(--text-secondary); font-size: 10px; }
.blocker-chip { padding: 4px 7px; color: #d29922; background: rgba(210, 153, 34, .08); border-radius: 999px; font-size: 10px; }
.execution-node-list { display: grid; gap: 6px; margin-top: 9px; }
.execution-node-row { display: flex; justify-content: space-between; gap: 12px; padding: 7px 9px; background: var(--panel-bg); border-radius: 6px; color: #d29922; font-size: 11px; }
.execution-node-row strong { color: var(--text-primary); }
.execution-node-row.readiness-stale { opacity: .68; }
.unmanaged-peers { margin-top: 14px; color: var(--text-secondary); font-size: 12px; }
.unmanaged-peers summary { cursor: pointer; padding: 9px 12px; border: 1px solid var(--line-color); border-radius: 7px; background: var(--panel-bg); }
.unmanaged-list { display: grid; gap: 6px; padding: 9px 12px; }
.unmanaged-list > div { display: flex; justify-content: space-between; gap: 12px; }
.cluster-footer { display: flex; gap: 14px; flex-wrap: wrap; margin-top: 10px; }
@media (max-width: 1100px) { .cluster-grid { grid-template-columns: 1fr; } }
@media (max-width: 700px) {
  .cluster-heading { align-items: flex-start; flex-direction: column; }
  .cluster-heading-status { justify-content: flex-start; }
  .status-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .execution-governance { grid-template-columns: 1fr; }
  .execution-node-row { flex-direction: column; gap: 3px; }
}
</style>
