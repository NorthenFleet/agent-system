import apiClient from './client'

export interface ChatAttachment {
  id?: string
  name: string
  type: string
  size: number
  data_url?: string
}

export interface ChatAgent {
  id: string
  name: string
  role?: string
  status?: string
  team?: string
  emoji?: string
  title?: string
  parent_id?: string
  path?: string[]
  depth?: number
  current_task?: string
}

export interface ChatAgentNode {
  id: string
  parent_id?: string
  node_type: 'person' | 'assistant' | 'agent' | 'group' | 'placeholder'
  agent_id?: string
  name: string
  emoji?: string
  title?: string
  registered?: boolean
  planned?: boolean
  order?: number
  depth: number
  path: string[]
  agent?: ChatAgent
}

export interface ChatMessage {
  role: 'user' | 'agent' | 'system'
  content: string
  timestamp: string
  attachments?: ChatAttachment[]
}

export interface ConversationSummary {
  agent_id: string
  message_count: number
  last_message?: ChatMessage | null
  last_timestamp?: string | null
}

interface ElasticAgentInstance {
  id: string
  instance_id?: string
  type?: string
  status?: string
  base_agent_id?: string
  base_agent_name?: string
  requested_by?: string
  role?: string
  capabilities?: string[]
  project_id?: string
  task_id?: string
  development_point_id?: string
}

const nameMap: Record<string, string> = {
  optimus: '擎天柱',
  bumblebee: '大黄蜂',
  donatello: '多纳泰罗',
  inspector: '巡检员',
  ironhide: '铁皮',
  jazz: '爵士',
  leonardo: '李奥纳多',
  michelangelo: '米开朗基罗',
  perceptor: '感知器',
  raphael: '拉斐尔',
  ratchet: '救护车',
  shockwave: '震荡波',
  soundwave: '声波',
  'ultra-magnus': '通天晓',
  wheeljack: '千斤顶',
  'wheeljack-donatello': '千斤顶-多纳泰罗',
  'wheeljack-leonardo': '千斤顶-李奥纳多',
  'wheeljack-michelangelo': '千斤顶-米开朗基罗',
  'wheeljack-raphael': '千斤顶-拉斐尔',
  main: '小梦'
}

function chineseName(agent: any) {
  const id = agent.id || agent.agent_id || agent.agent_id
  return agent.name || agent.agent_name || nameMap[id] || id
}

function elasticInstanceName(instance: ElasticAgentInstance) {
  const id = instance.id || instance.instance_id || ''
  if (nameMap[id]) return nameMap[id]
  const requester = nameMap[instance.requested_by || ''] || instance.requested_by || '项目经理'
  return `${requester}-${instance.base_agent_name || nameMap[instance.base_agent_id || ''] || instance.base_agent_id || '分身'}`
}

function elasticInstanceEmoji(instance: ElasticAgentInstance) {
  return {
    leonardo: '🟦',
    raphael: '🟥',
    donatello: '🟪',
    michelangelo: '🟧'
  }[instance.base_agent_id || ''] || '🧩'
}

function elasticInstanceOrder(instance: ElasticAgentInstance) {
  return {
    leonardo: 10,
    raphael: 20,
    donatello: 30,
    michelangelo: 40
  }[instance.base_agent_id || ''] || 99
}

function isActiveElasticInstance(instance: ElasticAgentInstance) {
  return ['assigned', 'queued', 'running', 'in_progress', 'review'].includes(instance.status || '')
}

export async function getChatAgents() {
  const [dashboardRes, organizationRes, instancesRes] = await Promise.all([
    apiClient.get<{ agents: any[] }>('/api/v3/agents/dashboard'),
    apiClient.get<{ root: any; nodes: any[] }>('/api/v3/agents/organization'),
    apiClient
      .get<{ instances: ElasticAgentInstance[] }>('/api/v3/agents/instances')
      .catch(() => ({ data: { instances: [] } }))
  ])
  const dashboardAgents = dashboardRes.data.agents || []
  const organization = organizationRes.data
  const elasticInstances = (instancesRes.data.instances || [])
    .filter(instance => instance.type === 'elastic' && instance.base_agent_id && instance.requested_by && isActiveElasticInstance(instance))
  const agentById = new Map<string, any>()
  dashboardAgents.forEach(agent => {
    const id = agent.id || agent.agent_id
    if (id) agentById.set(id, agent)
  })

  const children = new Map<string, any[]>()
  const organizationNodes = [organization.root, ...(organization.nodes || [])]
  const organizationNodeIds = new Set(organizationNodes.map(node => node?.id).filter(Boolean))

  function addChildNode(node: any) {
    const key = node.parent_id || ''
    if (!children.has(key)) children.set(key, [])
    children.get(key)!.push(node)
  }

  for (const node of organizationNodes) addChildNode(node)

  if (elasticInstances.length && organizationNodeIds.has('development')) {
    const elasticGroupId = 'elastic-ninja-instances'
    if (!organizationNodeIds.has(elasticGroupId)) {
      addChildNode({
        id: elasticGroupId,
        parent_id: 'development',
        node_type: 'group',
        name: '项目经理弹性分身',
        emoji: '🧩',
        title: '项目经理按需创建的忍者神龟执行分身',
        registered: false,
        order: 90
      })
    }

    for (const instance of elasticInstances) {
      const id = instance.id || instance.instance_id
      if (!id || organizationNodeIds.has(id)) continue
      const requester = nameMap[instance.requested_by || ''] || instance.requested_by || '项目经理'
      addChildNode({
        id,
        parent_id: elasticGroupId,
        node_type: 'agent',
        agent_id: id,
        name: elasticInstanceName(instance),
        emoji: elasticInstanceEmoji(instance),
        title: `弹性分身 · ${instance.base_agent_name || nameMap[instance.base_agent_id || ''] || instance.base_agent_id}模板 · ${requester}创建`,
        registered: true,
        planned: instance.status === 'released' || instance.status === 'completed',
        order: elasticInstanceOrder(instance)
      })
    }
  }

  for (const list of children.values()) {
    list.sort((a, b) => (a.order || 999) - (b.order || 999) || String(a.name || '').localeCompare(String(b.name || ''), 'zh-CN'))
  }

  const agents: ChatAgent[] = []
  const nodes: ChatAgentNode[] = []

  function walk(node: any, depth: number, path: string[]) {
    const currentName = node.name || nameMap[node.agent_id] || node.id
    const currentPath = [...path, currentName]
    let agent: ChatAgent | undefined

    if (node.agent_id) {
      const runtimeAgent = agentById.get(node.agent_id)
      const id = node.agent_id
      agent = {
        id,
        name: currentName || chineseName(runtimeAgent || { id }),
        role: node.title || runtimeAgent?.role || runtimeAgent?.profile?.role,
        title: node.title,
        status: runtimeAgent?.status || 'idle',
        team: runtimeAgent?.team || runtimeAgent?.profile?.team,
        emoji: node.emoji,
        parent_id: node.parent_id,
        path: currentPath,
        depth,
        current_task: runtimeAgent?.current_task_title || runtimeAgent?.current_task || '待分配'
      }
      agents.push(agent)
    }

    nodes.push({
      id: node.id,
      parent_id: node.parent_id,
      node_type: node.node_type,
      agent_id: node.agent_id,
      name: currentName,
      emoji: node.emoji,
      title: node.title,
      registered: node.registered,
      planned: node.planned,
      order: node.order,
      depth,
      path: currentPath,
      agent
    })

    for (const child of children.get(node.id) || []) {
      walk(child, depth + 1, currentPath)
    }
  }

  walk(organization.root, 0, [])

  return { agents, nodes }
}

export function getAgentMessages(agentId: string, limit = 80) {
  return apiClient
    .get<{ agent_id: string; messages: ChatMessage[] }>(`/api/v2/chat/${agentId}/messages`, { params: { limit } })
    .then(r => r.data)
}

export function sendAgentMessage(agentId: string, message: string, attachments: ChatAttachment[] = []) {
  return apiClient
    .post<{
      status: string
      agent_id: string
      user_message: string
      agent_response: string
      timestamp: string
      attachments?: ChatAttachment[]
    }>(`/api/v2/chat/${agentId}/send`, { message, attachments }, { timeout: 90000 })
    .then(r => r.data)
}

export function clearAgentMessages(agentId: string) {
  return apiClient.get<{ agent_id: string; cleared: boolean }>(`/api/v2/chat/${agentId}/clear`).then(r => r.data)
}

export function getConversationSummaries() {
  return apiClient
    .get<{ conversations: ConversationSummary[] }>('/api/v2/chat/conversations')
    .then(r => r.data)
}
