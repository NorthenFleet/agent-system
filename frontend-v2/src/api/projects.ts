import apiClient from './client'

export interface DevelopmentPoint {
  id: string
  title: string
  status: string
  weight?: number
  assigned_agent?: string
  completion_evidence?: string
}

export interface ProjectTask {
  id: string
  title: string
  description?: string
  assignee_agent?: string
  status: string
  priority?: string
  progress: number
  development_points: DevelopmentPoint[]
}

export interface Project {
  id: string
  name: string
  description?: string
  status: string
  priority?: string
  owner_agent?: string
  progress: number
  current_phase?: string
  design_doc?: {
    summary?: string
    usage_requirements?: unknown[]
    parallel_tasks?: unknown[]
    data_structure?: unknown
    system_architecture?: unknown
    system_functions?: unknown[]
    api_interfaces?: unknown[]
  }
  tasks: ProjectTask[]
}

export function getProjects() {
  return apiClient.get<{ projects: Project[]; total: number }>('/api/v3/projects').then(r => r.data)
}
