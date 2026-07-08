import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getAgentsLive, getAgentHistory } from '@/api/agents'
import { getAgentHealth, getHealthTrend, type AgentHealthScore, type HealthTrendPoint } from '@/api/health'
import { getAgentDashboard, getAgentOrganization, type AgentDashboardItem, type AgentOrganization } from '@/api/openclaw'
import { getWsClient } from '@/ws/client'

export interface Agent {
  agent_id: string
  agent_name: string
  status: 'online' | 'busy' | 'idle' | 'offline'
  raw_status?: string
  current_task: string | null
  last_heartbeat: string | null
  heartbeat_age_seconds: number | null
  seconds_ago?: number
  health: 'healthy' | 'warning' | 'critical' | 'offline'
  health_score?: number
  cpu_usage: number | null
  memory_usage: number | null
  task_queue_len?: number
  metadata?: Record<string, unknown>
}

export interface AgentStatusHistory {
  id: number
  agent_id: string
  from_status: string | null
  to_status: string
  current_task: string | null
  triggered_by: string | null
  changed_at: string
}

export interface AgentListResponse {
  agents: Agent[]
  total: number
  online?: number
  busy?: number
  idle?: number
  offline?: number
}

export interface AgentHistoryResponse {
  agent_id: string
  history: AgentStatusHistory[]
  total: number
}

export interface WsMessage {
  type: 'agent_status_change' | 'task_status_change' | 'heartbeat_update' | 'status_update' | 'task_comment'
  data: Record<string, unknown>
  timestamp?: string
}

export const useAgentsStore = defineStore('agents', () => {
  const agents = ref<Agent[]>([])
  const loading = ref(false)
  const wsConnected = ref(false)
  const selectedAgent = ref<Agent | null>(null)
  const selectedAgentHistory = ref<AgentStatusHistory[]>([])
  const organization = ref<AgentOrganization | null>(null)
  const notifications = ref<Array<{
    type: string
    message: string
    timestamp: string
  }>>([])

  // 健康度评分数据
  const healthScores = ref<Map<string, AgentHealthScore>>(new Map())
  const healthTrend = ref<HealthTrendPoint[]>([])
  const healthLoading = ref(false)

  let wsClient: ReturnType<typeof getWsClient> | null = null

  async function fetchAgents() {
    loading.value = true
    try {
      const [res, dashboardRes, organizationRes, healthRes] = await Promise.allSettled([
        getAgentsLive(),
        getAgentDashboard(),
        getAgentOrganization(),
        getAgentHealth()
      ])

      const liveAgents = res.status === 'fulfilled' ? res.value.agents : []
      const dashboardAgents = dashboardRes.status === 'fulfilled' ? dashboardRes.value.agents : []
      if (organizationRes.status === 'fulfilled') {
        organization.value = organizationRes.value
      }

      agents.value = mergeAgentSources(liveAgents, dashboardAgents, organization.value)

      if (res.status === 'fulfilled') {
        const normalizedLiveAgents = res.value.agents.map(a => ({
          ...a,
          heartbeat_age_seconds: a.seconds_ago ?? a.heartbeat_age_seconds ?? null,
          health: computeHealth(a.seconds_ago ?? a.heartbeat_age_seconds)
        }))
        agents.value = mergeAgentSources(normalizedLiveAgents, dashboardAgents, organization.value)
      }

      if (healthRes.status === 'fulfilled') {
        const scores = Array.isArray(healthRes.value) ? healthRes.value : (healthRes.value.agents || [])
        const scoreMap = new Map<string, AgentHealthScore>()
        scores.forEach(s => scoreMap.set(s.agent_id, s))
        healthScores.value = scoreMap

        // 将评分同步到 agents 中
        agents.value.forEach(a => {
          const hs = scoreMap.get(a.agent_id)
          if (hs) a.health_score = hs.score
        })
      }
    } catch {
      agents.value = []
    } finally {
      loading.value = false
    }
  }

  function mergeAgentSources(liveAgents: Agent[], dashboardAgents: AgentDashboardItem[], org: AgentOrganization | null): Agent[] {
    const liveById = new Map(liveAgents.map(agent => [agent.agent_id, agent]))
    const dashboardById = new Map(dashboardAgents.map(agent => [agent.agent_id || agent.id, agent]))
    const orgNodes = [org?.root, ...(org?.nodes || [])].filter(Boolean)
    const orgAgentNodes = orgNodes.filter(node => ['agent', 'assistant', 'person'].includes(node?.node_type || ''))
    const parentNames = new Map((org?.nodes || []).map(node => [node.id, node.name]))
    if (org?.root) parentNames.set(org.root.id, org.root.name)

    const ids = new Set<string>()
    liveAgents.forEach(agent => ids.add(agent.agent_id))
    dashboardAgents.forEach(agent => ids.add(agent.agent_id || agent.id))
    orgAgentNodes.forEach(node => ids.add(node?.agent_id || node?.id || ''))
    ids.delete('')

    return Array.from(ids)
      .map(id => {
        const live = liveById.get(id)
        const dashboard = dashboardById.get(id)
        const orgNode = orgAgentNodes.find(node => (node?.agent_id || node?.id) === id)
        return normalizeAgent(id, live, dashboard, orgNode, parentNames)
      })
      .filter(Boolean) as Agent[]
  }

  function normalizeAgent(
    id: string,
    live?: Agent,
    dashboard?: AgentDashboardItem,
    orgNode?: NonNullable<AgentOrganization['root']>,
    parentNames?: Map<string, string>
  ): Agent {
    const rawStatus = live?.status || dashboard?.status || 'offline'
    const heartbeatAge = live?.seconds_ago ?? live?.heartbeat_age_seconds ?? null
    const metadata = {
      ...(live?.metadata || {}),
      role: dashboard?.role || dashboard?.profile?.role || orgNode?.title || live?.metadata?.role,
      team: dashboard?.team || dashboard?.profile?.team || (orgNode?.parent_id ? parentNames?.get(orgNode.parent_id) : undefined),
      organization_title: orgNode?.title,
      node_type: orgNode?.node_type,
      source: dashboard?.source || 'agent-organization',
    }
    return {
      agent_id: id,
      agent_name: live?.agent_name || dashboard?.agent_name || dashboard?.name || orgNode?.name || id,
      status: normalizeStatus(rawStatus),
      raw_status: rawStatus,
      current_task: live?.current_task || dashboard?.current_task || dashboard?.current_task_title || null,
      last_heartbeat: live?.last_heartbeat || dashboard?.last_seen || dashboard?.updated_at || null,
      heartbeat_age_seconds: heartbeatAge,
      seconds_ago: live?.seconds_ago,
      health: live?.health || computeHealth(heartbeatAge),
      health_score: live?.health_score,
      cpu_usage: live?.cpu_usage ?? null,
      memory_usage: live?.memory_usage ?? null,
      task_queue_len: live?.task_queue_len,
      metadata,
    }
  }

  function normalizeStatus(status: string | undefined): Agent['status'] {
    const normalized = String(status || '').toLowerCase()
    if (['online', 'running', 'active', 'healthy'].includes(normalized)) return 'online'
    if (['busy', 'working', 'review'].includes(normalized)) return 'busy'
    if (['idle', 'available', 'pending', 'standby'].includes(normalized)) return 'idle'
    return 'offline'
  }

  async function fetchAgentHistory(agentId: string) {
    try {
      const res = await getAgentHistory(agentId, { limit: 50 })
      selectedAgentHistory.value = res.history
    } catch {
      selectedAgentHistory.value = []
    }
  }

  function selectAgent(agentId: string) {
    const agent = agents.value.find(a => a.agent_id === agentId)
    selectedAgent.value = agent || null
    if (agent) {
      fetchAgentHistory(agentId)
    }
  }

  /**
   * 连接 WebSocket — 使用 WsClient 内置指数退避重连
   * 重连策略: 1s → 2s → 4s → 8s → 16s → 30s（上限）
   */
  function connectWebSocket(token: string) {
    wsClient = getWsClient(token, {
      baseDelay: 1000,
      maxDelay: 30000,
      pongTimeout: 60000,
      autoPong: true,
    })

    wsClient.on('connected', () => {
      wsConnected.value = true
      console.log('[WebSocket] 已连接（指数退避重连就绪）')
    })

    wsClient.on('heartbeat_update', (msg) => {
      handleWsMessage({ type: 'heartbeat_update', data: msg.data, timestamp: msg.timestamp })
    })

    wsClient.on('status_update', (msg) => {
      handleWsMessage({ type: 'status_update', data: msg.data, timestamp: msg.timestamp })
    })

    wsClient.on('agent_status_change', (msg) => {
      handleWsMessage({ type: 'agent_status_change', data: msg.data, timestamp: msg.timestamp })
    })

    wsClient.on('task_status_change', (msg) => {
      handleWsMessage({ type: 'task_status_change', data: msg.data, timestamp: msg.timestamp })
    })

    wsClient.on('error', (msg) => {
      console.error('[WebSocket] 连接错误:', msg.data)
    })

    wsClient.on('disconnected', (msg) => {
      wsConnected.value = false
      console.warn('[WebSocket] 已断开，达到最大重连次数:', msg.data)
    })

    wsClient.connect()
  }

  function disconnectWebSocket() {
    if (wsClient) {
      wsClient.close()
      wsClient = null
    }
    wsConnected.value = false
  }

  function handleWsMessage(message: WsMessage) {
    switch (message.type) {
      case 'agent_status_change': {
        const data = message.data as { agent_id?: string; agent_name?: string; from_status?: string; to_status?: string; current_task?: string; timestamp?: string }
        if (data.agent_id) {
          updateAgentStatus(data.agent_id, data.to_status || 'offline', data.current_task || null)
        }
        addNotification({
          type: 'agent',
          message: `${data.agent_name || data.agent_id} 状态变更: ${data.from_status} → ${data.to_status}`,
          timestamp: data.timestamp || new Date().toISOString()
        })
        break
      }
      case 'heartbeat_update': {
        const data = message.data as { agent_id?: string; status?: string; cpu_usage?: number; memory_usage?: number; seconds_ago?: number; timestamp?: string }
        if (data.agent_id) {
          updateHeartbeat(data.agent_id, data)
        }
        break
      }
      case 'task_status_change': {
        const data = message.data as { task_id?: string; from_status?: string; to_status?: string; assignee?: string; timestamp?: string }
        addNotification({
          type: 'task',
          message: `任务 ${data.task_id} 状态变更: ${data.from_status} → ${data.to_status}`,
          timestamp: data.timestamp || new Date().toISOString()
        })
        break
      }
    }
  }

  function updateAgentStatus(agentId: string, status: string, currentTask: string | null) {
    const agent = agents.value.find(a => a.agent_id === agentId)
    if (agent) {
      agent.status = status as Agent['status']
      agent.current_task = currentTask
      agent.last_heartbeat = new Date().toISOString()
      agent.heartbeat_age_seconds = 0
      agent.health = 'healthy'
    }
    if (selectedAgent.value?.agent_id === agentId) {
      selectedAgent.value.status = status as Agent['status']
      selectedAgent.value.current_task = currentTask
    }
  }

  function updateHeartbeat(agentId: string, data: { status?: string; cpu_usage?: number; memory_usage?: number; seconds_ago?: number }) {
    const agent = agents.value.find(a => a.agent_id === agentId)
    if (agent) {
      agent.last_heartbeat = new Date().toISOString()
      if (data.status) agent.status = data.status as Agent['status']
      if (data.cpu_usage != null) agent.cpu_usage = data.cpu_usage
      if (data.memory_usage != null) agent.memory_usage = data.memory_usage
      if (data.seconds_ago != null) {
        agent.heartbeat_age_seconds = data.seconds_ago
        agent.health = computeHealth(data.seconds_ago)
      }
    }
  }

  function computeHealth(ageSeconds: number | null | undefined): Agent['health'] {
    if (ageSeconds == null) return 'offline'
    if (ageSeconds <= 60) return 'healthy'
    if (ageSeconds <= 300) return 'warning'
    return 'critical'
  }

  function getHealthScore(agentId: string): number | undefined {
    return healthScores.value.get(agentId)?.score
  }

  async function fetchHealthTrend(agentId: string, hours = 24) {
    healthLoading.value = true
    try {
      const res = await getHealthTrend(agentId, hours)
      healthTrend.value = res.trend || []
    } catch {
      healthTrend.value = []
    } finally {
      healthLoading.value = false
    }
  }

  function getHealthScoreData(agentId: string): AgentHealthScore | undefined {
    return healthScores.value.get(agentId)
  }

  function addNotification(notification: { type: string; message: string; timestamp: string }) {
    notifications.value.unshift(notification)
    if (notifications.value.length > 50) {
      notifications.value.pop()
    }
  }

  return {
    agents,
    loading,
    wsConnected,
    selectedAgent,
    selectedAgentHistory,
    organization,
    notifications,
    healthScores,
    healthTrend,
    healthLoading,
    fetchAgents,
    fetchAgentHistory,
    selectAgent,
    connectWebSocket,
    disconnectWebSocket,
    addNotification,
    getHealthScore,
    fetchHealthTrend,
    getHealthScoreData
  }
})
