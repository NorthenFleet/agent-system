import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getAgentsLive, getAgentHistory, createWsAgent } from '@/api/agents'

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
  type: 'agent_status_change' | 'task_status_change' | 'heartbeat_update' | 'task_comment'
  data: Record<string, unknown>
}

export const useAgentsStore = defineStore('agents', () => {
  const agents = ref<Agent[]>([])
  const loading = ref(false)
  const wsConnected = ref(false)
  const selectedAgent = ref<Agent | null>(null)
  const selectedAgentHistory = ref<AgentStatusHistory[]>([])
  const notifications = ref<Array<{
    type: string
    message: string
    timestamp: string
  }>>([])

  let ws: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null

  async function fetchAgents() {
    loading.value = true
    try {
      const res = await getAgentsLive()
      // Normalize seconds_ago → heartbeat_age_seconds
      agents.value = res.agents.map(a => ({
        ...a,
        heartbeat_age_seconds: a.seconds_ago ?? a.heartbeat_age_seconds ?? null,
        health: computeHealth(a.seconds_ago ?? a.heartbeat_age_seconds)
      }))
    } catch {
      agents.value = []
    } finally {
      loading.value = false
    }
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

  function connectWebSocket(token: string) {
    if (ws) {
      ws.close()
    }

    ws = createWsAgent(token)

    ws.onopen = () => {
      wsConnected.value = true
      console.log('[WebSocket] 已连接')
    }

    ws.onmessage = (event: MessageEvent) => {
      try {
        const message: WsMessage = JSON.parse(event.data)
        handleWsMessage(message)
      } catch {
        console.warn('[WebSocket] 解析消息失败', event.data)
      }
    }

    ws.onclose = () => {
      wsConnected.value = false
      console.log('[WebSocket] 已断开，5秒后重连...')
      reconnectTimer = setTimeout(() => {
        if (token) connectWebSocket(token)
      }, 5000)
    }

    ws.onerror = () => {
      console.error('[WebSocket] 连接错误')
    }
  }

  function disconnectWebSocket() {
    if (ws) {
      ws.close()
      ws = null
    }
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
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
    notifications,
    fetchAgents,
    fetchAgentHistory,
    selectAgent,
    connectWebSocket,
    disconnectWebSocket,
    addNotification
  }
})
