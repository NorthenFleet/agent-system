import apiClient from './client'

export interface ChatAgent {
  id: string
  name: string
  role?: string
  status?: string
  team?: string
}

export interface ChatMessage {
  role: 'user' | 'agent' | 'system'
  content: string
  timestamp: string
}

export interface ConversationSummary {
  agent_id: string
  message_count: number
  last_message?: ChatMessage | null
  last_timestamp?: string | null
}

export function getChatAgents() {
  return apiClient.get<{ agents: ChatAgent[] }>('/api/agents').then(r => ({
    agents: (r.data.agents || []).map((agent: any) => ({
      id: agent.id || agent.agent_id,
      name: agent.name || agent.agent_name || agent.id || agent.agent_id,
      role: agent.role,
      status: agent.status,
      team: agent.team
    })).filter(agent => agent.id)
  }))
}

export function getAgentMessages(agentId: string, limit = 80) {
  return apiClient
    .get<{ agent_id: string; messages: ChatMessage[] }>(`/api/v2/chat/${agentId}/messages`, { params: { limit } })
    .then(r => r.data)
}

export function sendAgentMessage(agentId: string, message: string) {
  return apiClient
    .post<{
      status: string
      agent_id: string
      user_message: string
      agent_response: string
      timestamp: string
    }>(`/api/v2/chat/${agentId}/send`, { message }, { timeout: 90000 })
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
