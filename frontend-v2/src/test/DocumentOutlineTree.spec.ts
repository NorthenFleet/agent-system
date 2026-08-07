import { beforeAll, beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import DocumentOutlineTree from '@/components/writing/DocumentOutlineTree.vue'
import type { WritingDirectoryNode } from '@/api/writing'

function node(
  id: string,
  title: string,
  level: 0 | 1 | 2 | 3,
  children: WritingDirectoryNode[] = []
): WritingDirectoryNode {
  return {
    id,
    title,
    node_type: level === 0 ? 'document' : level === 1 ? 'section' : 'heading',
    source_level: level,
    level,
    line: level,
    anchor: id,
    target_id: level === 0 ? '' : `${id}-target`,
    section_id: level === 0 ? '' : 'chapter-1',
    word_count: level <= 1 ? 100 : null,
    children
  }
}

const tree = [
  node('root', '测试文档', 0, [
    node('chapter-1', '第一章', 1, [
      node('heading-1', '1.1 背景', 2, [
        node('heading-1-1', '1.1.1 问题', 3)
      ])
    ]),
    node('chapter-2', '第二章', 1)
  ])
]

const storage = new Map<string, string>()

beforeAll(() => {
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: {
      clear: () => storage.clear(),
      getItem: (key: string) => storage.get(key) ?? null,
      key: (index: number) => [...storage.keys()][index] ?? null,
      removeItem: (key: string) => storage.delete(key),
      setItem: (key: string, value: string) => storage.set(key, String(value)),
      get length() {
        return storage.size
      }
    }
  })
})

function mountTree(options: { documentId?: string; selectedNodeId?: string } = {}) {
  return mount(DocumentOutlineTree, {
    props: {
      nodes: tree,
      projectId: 'project-1',
      documentId: options.documentId || 'document-1',
      selectedNodeId: options.selectedNodeId || ''
    }
  })
}

beforeEach(() => localStorage.clear())

describe('DocumentOutlineTree', () => {
  it('defaults to the document root and first-level sections', () => {
    const wrapper = mountTree()

    expect(wrapper.text()).toContain('测试文档')
    expect(wrapper.text()).toContain('第一章')
    expect(wrapper.text()).toContain('第二章')
    expect(wrapper.text()).not.toContain('1.1 背景')
  })

  it('expands and collapses a branch with persistent state', async () => {
    const wrapper = mountTree()
    await wrapper.get('button[aria-label="展开第一章"]').trigger('click')

    expect(wrapper.text()).toContain('1.1 背景')
    expect(localStorage.getItem('writing-outline:project-1:document-1')).toBe('["heading-1"]')

    await wrapper.get('button[aria-label="收起第一章"]').trigger('click')
    expect(wrapper.text()).not.toContain('1.1 背景')
  })

  it('supports expand-all and collapse-all for the whole document', async () => {
    const wrapper = mountTree()
    const actions = wrapper.findAll('.outline-actions button')

    await actions[0].trigger('click')
    expect(wrapper.text()).toContain('1.1.1 问题')

    await actions[1].trigger('click')
    expect(wrapper.text()).toContain('测试文档')
    expect(wrapper.text()).not.toContain('第一章')

    await actions[0].trigger('click')
    expect(wrapper.text()).toContain('1.1.1 问题')
  })

  it('temporarily expands matching paths and restores the previous state', async () => {
    const wrapper = mountTree()
    const input = wrapper.get('input[aria-label="搜索目录"]')

    await input.setValue('问题')
    expect(wrapper.text()).toContain('第一章')
    expect(wrapper.text()).toContain('1.1 背景')
    expect(wrapper.text()).toContain('1.1.1 问题')

    await input.setValue('')
    expect(wrapper.text()).not.toContain('1.1 背景')
  })

  it('keeps collapse state isolated by document', async () => {
    const first = mountTree({ documentId: 'document-1' })
    await first.get('button[aria-label="展开第一章"]').trigger('click')
    first.unmount()

    const second = mountTree({ documentId: 'document-2' })
    expect(second.text()).not.toContain('1.1 背景')

    const restored = mountTree({ documentId: 'document-1' })
    expect(restored.text()).toContain('1.1 背景')
  })

  it('expands the selected path and emits heading selection', async () => {
    const wrapper = mountTree({ selectedNodeId: 'heading-1-1' })

    expect(wrapper.text()).toContain('1.1.1 问题')
    await wrapper.get('[data-outline-node-id="heading-1-1"]').trigger('click')
    expect(wrapper.emitted('select')?.[0]?.[0]).toMatchObject({ id: 'heading-1-1' })
  })

  it('supports keyboard expansion and navigation', async () => {
    const wrapper = mountTree()
    const chapter = wrapper.get('[data-outline-node-id="chapter-1"]')

    await chapter.trigger('keydown', { key: 'ArrowRight' })
    expect(wrapper.text()).toContain('1.1 背景')

    await chapter.trigger('keydown', { key: 'ArrowLeft' })
    expect(wrapper.text()).not.toContain('1.1 背景')
  })
})
