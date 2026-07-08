import apiClient from './client'

// ─── 类型定义 ───

export interface TreeItem {
  id: string
  name: string
  type: 'directory' | 'file'
  path: string
  children?: TreeItem[]
  ext?: string
  size?: number
  mtime?: string
}

export interface FileContent {
  path: string
  name: string
  ext: string
  content: string
  links: string[]
  tags: string[]
  size?: number
  mtime?: string
  error?: string
}

export interface SearchHit {
  path: string
  name: string
  match: 'filename' | 'content'
  line?: number
  preview?: string
}

/** Alias so SearchBar can import it as SearchResult */
export type SearchResult = SearchHit

export interface BacklinkItem {
  path: string
  name: string
  link: string
}

/** Stats 返回值：注意后端 /api/knowledge/tree 返回 total_directories + total_files，
 *  而 /api/knowledge/stats 返回 { nodes, edges, entity_types, ... }。
 *  页面底部统计栏使用 tree 接口返回的数据。 */
export interface KnowledgeTreeStats {
  total_files: number
  total_directories: number
}

// ─── API 端点 ───

/** 获取目录树（全量） */
export async function getTree(): Promise<{ root: string; tree: TreeItem[]; total_files: number; total_directories: number; total_subdirs?: number }> {
  const { data } = await apiClient.get('/api/knowledge/tree')
  return data
}

/** 获取文件内容 */
export async function getFile(path: string): Promise<FileContent> {
  const { data } = await apiClient.get('/api/knowledge/file', { params: { path } })
  return data
}

/** 全文搜索 — 后端返回 { query, nodes: [...], total } */
export async function searchKnowledge(q: string, limit = 50): Promise<{ query: string; total: number; nodes: SearchHit[] }> {
  if (!q) return { query: '', total: 0, nodes: [] }
  const { data } = await apiClient.get('/api/knowledge/search', { params: { q, limit } })
  return data
}

/** 反向链接 — 后端 neighbors 返回 { neighbors, relations, total } */
export async function getBacklinks(path: string): Promise<BacklinkItem[]> {
  try {
    // 后端没有 /api/knowledge/backlinks 端点，用 nodes/{path} 的 neighbors
    const { data } = await apiClient.get(`/api/knowledge/neighbors/${encodeURIComponent(path)}`, {
      params: { limit: 50 }
    })
    // neighbors 返回 [{ id, title, type, path }]
    return (data.neighbors || []).map((n: any) => ({
      path: n.path || '',
      name: n.title || n.id,
      link: n.title || n.id
    }))
  } catch {
    return []
  }
}
