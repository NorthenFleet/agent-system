import { vi } from 'vitest'
import ElementPlus from 'element-plus'

// Stub fetch globally for API mocking
global.fetch = vi.fn()

// Mock Element Plus icons — Sidebar uses Monitor, List, Cpu, Grid
vi.mock('@element-plus/icons-vue', () => ({
  Loading: { name: 'Loading', render: () => null },
  Monitor: { name: 'Monitor', render: () => null },
  List: { name: 'List', render: () => null },
  Cpu: { name: 'Cpu', render: () => null },
  Grid: { name: 'Grid', render: () => null },
  Sunny: { name: 'Sunny', render: () => null },
  Moon: { name: 'Moon', render: () => null },
  User: { name: 'User', render: () => null },
  Tickets: { name: 'Tickets', render: () => null },
  Tools: { name: 'Tools', render: () => null },
  Star: { name: 'Star', render: () => null }
}))
