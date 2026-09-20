import { afterEach, vi } from 'vitest'

// Stub fetch globally for API mocking
global.fetch = vi.fn()

class StorageMock implements Storage {
  private values = new Map<string, string>()

  get length() { return this.values.size }
  clear() { this.values.clear() }
  getItem(key: string) { return this.values.get(String(key)) ?? null }
  key(index: number) { return Array.from(this.values.keys())[index] ?? null }
  removeItem(key: string) { this.values.delete(String(key)) }
  setItem(key: string, value: string) { this.values.set(String(key), String(value)) }
}

const stableLocalStorage = new StorageMock()
Object.defineProperty(globalThis, 'localStorage', {
  configurable: true,
  value: stableLocalStorage
})
Object.defineProperty(window, 'localStorage', {
  configurable: true,
  value: stableLocalStorage
})

afterEach(() => {
  stableLocalStorage.clear()
})

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

global.ResizeObserver = ResizeObserverMock as typeof ResizeObserver

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
  ChatLineRound: { name: 'ChatLineRound', render: () => null },
  CircleClose: { name: 'CircleClose', render: () => null },
  Connection: { name: 'Connection', render: () => null },
  DocumentChecked: { name: 'DocumentChecked', render: () => null },
  Platform: { name: 'Platform', render: () => null },
  Position: { name: 'Position', render: () => null },
  Promotion: { name: 'Promotion', render: () => null },
  Warning: { name: 'Warning', render: () => null },
  ChatLineSquare: { name: 'ChatLineSquare', render: () => null },
  Clock: { name: 'Clock', render: () => null },
  Close: { name: 'Close', render: () => null },
  DArrowLeft: { name: 'DArrowLeft', render: () => null },
  Document: { name: 'Document', render: () => null },
  DocumentAdd: { name: 'DocumentAdd', render: () => null },
  Edit: { name: 'Edit', render: () => null },
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
  Delete: { name: 'Delete', render: () => null },
  Pointer: { name: 'Pointer', render: () => null },
  Lock: { name: 'Lock', render: () => null },
  Operation: { name: 'Operation', render: () => null },
  Setting: { name: 'Setting', render: () => null },
  ZoomIn: { name: 'ZoomIn', render: () => null },
  ZoomOut: { name: 'ZoomOut', render: () => null }
}))
