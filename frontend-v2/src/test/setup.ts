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
  Star: { name: 'Star', render: () => null },
  Download: { name: 'Download', render: () => null },
  FullScreen: { name: 'FullScreen', render: () => null },
  Refresh: { name: 'Refresh', render: () => null },
  Upload: { name: 'Upload', render: () => null },
  Back: { name: 'Back', render: () => null },
  Check: { name: 'Check', render: () => null },
  ChatLineSquare: { name: 'ChatLineSquare', render: () => null },
  Clock: { name: 'Clock', render: () => null },
  Close: { name: 'Close', render: () => null },
  DArrowLeft: { name: 'DArrowLeft', render: () => null },
  Document: { name: 'Document', render: () => null },
  Expand: { name: 'Expand', render: () => null },
  Fold: { name: 'Fold', render: () => null },
  MagicStick: { name: 'MagicStick', render: () => null },
  Rank: { name: 'Rank', render: () => null },
  Right: { name: 'Right', render: () => null },
  Sort: { name: 'Sort', render: () => null },
  EditPen: { name: 'EditPen', render: () => null },
  FolderOpened: { name: 'FolderOpened', render: () => null },
  Plus: { name: 'Plus', render: () => null },
  Picture: { name: 'Picture', render: () => null },
  Search: { name: 'Search', render: () => null },
  UploadFilled: { name: 'UploadFilled', render: () => null },
  VideoPlay: { name: 'VideoPlay', render: () => null },
  ArrowDown: { name: 'ArrowDown', render: () => null },
  ArrowUp: { name: 'ArrowUp', render: () => null },
  Delete: { name: 'Delete', render: () => null }
}))
