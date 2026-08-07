import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessageBox } from 'element-plus'
import CollaborativeWritingEditor from '@/components/writing/CollaborativeWritingEditor.vue'
import type { WritingCollaborationState, WritingDirectoryNode } from '@/api/writing'
import {
  acceptWritingProposal,
  createWritingAiJob,
  getDocumentWritingAsset,
  getWritingAiJob,
  getWritingCollaboration,
  patchWritingCollaborationDraft,
  uploadDocumentWritingAsset
} from '@/api/writing'

vi.mock('@/api/writing', async importOriginal => {
  const original = await importOriginal<typeof import('@/api/writing')>()
  return {
    ...original,
    acceptWritingProposal: vi.fn(),
    createWritingAiJob: vi.fn(),
    createWritingVersion: vi.fn(),
    getDocumentWritingAsset: vi.fn(),
    getWritingAiJob: vi.fn(),
    getWritingCollaboration: vi.fn(),
    patchWritingCollaborationDraft: vi.fn(),
    rejectWritingProposal: vi.fn(),
    uploadDocumentWritingAsset: vi.fn()
  }
})

const outline: WritingDirectoryNode[] = [{
  id: 'root',
  title: '测试论文',
  node_type: 'document',
  source_level: 0,
  level: 0,
  line: 0,
  anchor: 'root',
  target_id: '',
  section_id: '',
  children: [{
    id: 'section-1',
    title: '第一章 绪论',
    node_type: 'section',
    source_level: 1,
    level: 1,
    line: 1,
    anchor: 'section-1',
    target_id: 'section-1',
    section_id: 'section-1',
    children: []
  }]
}]

function collaboration(overrides: Partial<WritingCollaborationState> = {}): WritingCollaborationState {
  return {
    revision: 7,
    document: {
      type: 'doc',
      content: [{
        type: 'paragraph',
        attrs: { blockId: 'block-42', blockRevision: 3 },
        content: [{ type: 'text', text: '保留稳定块属性' }]
      }]
    },
    agents: [{ id: 'academic-editor', name: '学术编辑', model: 'Kimi-K3' }],
    proposals: [],
    ...overrides
  }
}

function twoBlockCollaboration(revision = 7): WritingCollaborationState {
  return collaboration({
    revision,
    document: {
      type: 'doc',
      content: [
        { type: 'paragraph', attrs: { blockId: 'block-a', blockRevision: 3 }, content: [{ type: 'text', text: '第一段' }] },
        { type: 'paragraph', attrs: { blockId: 'block-b', blockRevision: 2 }, content: [{ type: 'text', text: '第二段' }] }
      ]
    }
  })
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}

function mountEditor() {
  return mount(CollaborativeWritingEditor, {
    props: {
      projectId: 'project-1',
      documentId: 'document-1',
      documentTitle: '测试论文',
      sectionId: 'section-1',
      outline,
      selectedNodeId: 'section-1'
    },
    global: { plugins: [ElementPlus] },
    attachTo: document.body
  })
}

beforeEach(() => {
  vi.useFakeTimers()
  Object.defineProperty(URL, 'createObjectURL', { value: vi.fn(() => 'blob:preview-image'), configurable: true })
  Object.defineProperty(URL, 'revokeObjectURL', { value: vi.fn(), configurable: true })
  vi.mocked(getWritingCollaboration).mockResolvedValue(collaboration())
  vi.mocked(getDocumentWritingAsset).mockResolvedValue(new Blob(['fake-png'], { type: 'image/png' }))
  vi.mocked(patchWritingCollaborationDraft).mockResolvedValue(collaboration({ revision: 8 }))
  vi.mocked(uploadDocumentWritingAsset).mockResolvedValue({
    path: 'assets/uploaded-image.png',
    filename: 'uploaded-image.png',
    content_type: 'image/png',
    size_bytes: 8,
    sha256: 'abc',
    url: '/api/v3/writing/projects/project-1/documents/document-1/assets?path=assets/uploaded-image.png'
  })
})

afterEach(() => {
  document.body.innerHTML = ''
  vi.useRealTimers()
  vi.clearAllMocks()
})

describe('CollaborativeWritingEditor', () => {
  it('supports document-only and AI-only embedding modes for the linked workspace', async () => {
    const documentOnly = mount(CollaborativeWritingEditor, {
      props: {
        projectId: 'project-1',
        documentId: 'document-1',
        documentTitle: '测试论文',
        sectionId: 'section-1',
        outline,
        selectedNodeId: 'section-1',
        displayMode: 'document'
      },
      global: { plugins: [ElementPlus] }
    })
    await flushPromises()
    expect(documentOnly.find('.document-workbench').exists()).toBe(true)
    expect(documentOnly.find('.ai-panel').exists()).toBe(false)
    documentOnly.unmount()

    const aiOnly = mount(CollaborativeWritingEditor, {
      props: {
        projectId: 'project-1',
        documentId: 'document-1',
        documentTitle: '测试论文',
        sectionId: 'section-1',
        outline,
        selectedNodeId: 'section-1',
        displayMode: 'ai'
      },
      global: { plugins: [ElementPlus] }
    })
    await flushPromises()
    expect(aiOnly.find('.ai-panel').exists()).toBe(true)
    expect(aiOnly.find('.document-workbench').exists()).toBe(false)
    aiOnly.unmount()
  })

  it('loads Tiptap JSON and preserves stable block identity attributes', async () => {
    const wrapper = mountEditor()
    await flushPromises()

    const block = wrapper.get('[data-block-id="block-42"]')
    expect(block.attributes('data-block-revision')).toBe('3')
    expect(wrapper.text()).toContain('保留稳定块属性')
    expect(getWritingCollaboration).toHaveBeenCalledWith('project-1', 'document-1', 'section-1')

    wrapper.unmount()
  })

  it('debounces draft saves and retries an error on the five-second hard flush', async () => {
    vi.mocked(patchWritingCollaborationDraft)
      .mockRejectedValueOnce(new Error('temporary'))
      .mockResolvedValueOnce(collaboration({ revision: 8 }))
    const wrapper = mountEditor()
    await flushPromises()

    ;(wrapper.vm as any).editor.commands.insertContent(' 新增内容')
    vi.advanceTimersByTime(999)
    await flushPromises()
    expect(patchWritingCollaborationDraft).not.toHaveBeenCalled()

    vi.advanceTimersByTime(1)
    await flushPromises()
    expect(patchWritingCollaborationDraft).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('保存失败')

    vi.advanceTimersByTime(5000)
    await flushPromises()
    expect(patchWritingCollaborationDraft).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('已保存')
    expect(vi.mocked(patchWritingCollaborationDraft).mock.calls[1][2]).toMatchObject({
      base_document_revision: 7,
      section_id: 'section-1'
    })
    expect(vi.mocked(patchWritingCollaborationDraft).mock.calls[1][2].changes).toEqual([
      expect.objectContaining({
        op: 'upsert',
        block_id: 'block-42',
        expected_block_revision: 3,
        node: expect.objectContaining({
          attrs: expect.objectContaining({ blockId: 'block-42', blockRevision: 3 })
        })
      })
    ])

    wrapper.unmount()
  })

  it('polls an AI job and keeps its proposal gated until acceptance', async () => {
    vi.mocked(createWritingAiJob).mockResolvedValue({ id: 'job-1', status: 'queued' })
    vi.mocked(getWritingAiJob).mockResolvedValue({
      id: 'job-1',
      status: 'succeeded',
      proposal: {
        id: 'proposal-1',
        status: 'pending',
        scope: 'section',
        title: '收紧论证边界',
        rationale: '删去无法核验的推断。'
      }
    })
    vi.mocked(acceptWritingProposal).mockResolvedValue(collaboration({
      revision: 8,
      document: {
        type: 'doc',
        content: [{ type: 'paragraph', attrs: { blockId: 'block-42', blockRevision: 4 }, content: [{ type: 'text', text: '人工接受后的正文' }] }]
      },
      proposals: [{ id: 'proposal-1', status: 'accepted' }]
    }))
    const wrapper = mountEditor()
    await flushPromises()

    await wrapper.findAll('.quick-actions button')[1].trigger('click')
    await wrapper.get('.run-ai').trigger('click')
    await flushPromises()
    expect(createWritingAiJob).toHaveBeenCalledWith('project-1', 'document-1', expect.objectContaining({
      agent_id: 'academic-editor',
      scope: 'section',
      section_id: 'section-1'
    }))

    vi.advanceTimersByTime(1200)
    await flushPromises()
    expect(wrapper.text()).toContain('收紧论证边界')
    expect(wrapper.text()).not.toContain('人工接受后的正文')

    const accept = wrapper.findAll('button').find(button => button.text().includes('接受'))
    expect(accept).toBeDefined()
    await accept!.trigger('click')
    await flushPromises()
    expect(acceptWritingProposal).toHaveBeenCalledWith('project-1', 'document-1', 'proposal-1')
    expect(wrapper.text()).toContain('人工接受后的正文')

    wrapper.unmount()
  })

  it('serializes edits made while an autosave request is in flight', async () => {
    const firstSave = deferred<WritingCollaborationState>()
    vi.mocked(patchWritingCollaborationDraft)
      .mockReturnValueOnce(firstSave.promise)
      .mockImplementationOnce(async (_projectId, _documentId, payload) => {
        const node = payload.changes?.find(change => change.op === 'upsert')?.node
        return collaboration({
          revision: 9,
          document: {
            type: 'doc',
            content: [{ ...node, attrs: { ...node?.attrs, blockId: 'block-42', blockRevision: 5 } }]
          }
        })
      })
    const wrapper = mountEditor()
    await flushPromises()

    ;(wrapper.vm as any).editor.commands.insertContent(' 第一次')
    vi.advanceTimersByTime(1000)
    await flushPromises()
    expect(patchWritingCollaborationDraft).toHaveBeenCalledTimes(1)

    ;(wrapper.vm as any).editor.commands.insertContent(' 第二次')
    vi.advanceTimersByTime(1000)
    await flushPromises()
    expect(patchWritingCollaborationDraft).toHaveBeenCalledTimes(1)

    const firstNode = vi.mocked(patchWritingCollaborationDraft).mock.calls[0][2].changes?.[0].node
    firstSave.resolve(collaboration({
      revision: 8,
      document: {
        type: 'doc',
        content: [{ ...firstNode, attrs: { ...firstNode?.attrs, blockId: 'block-42', blockRevision: 4 } }]
      }
    }))
    await flushPromises()

    expect(patchWritingCollaborationDraft).toHaveBeenCalledTimes(2)
    const secondPayload = vi.mocked(patchWritingCollaborationDraft).mock.calls[1][2]
    expect(JSON.stringify(secondPayload)).toContain('第一次 第二次')
    expect(wrapper.text()).toContain('已保存')
    wrapper.unmount()
  })

  it('keeps a local deletion made while the previous save is in flight', async () => {
    vi.mocked(getWritingCollaboration).mockResolvedValue(twoBlockCollaboration())
    const firstSave = deferred<WritingCollaborationState>()
    const secondSave = deferred<WritingCollaborationState>()
    vi.mocked(patchWritingCollaborationDraft)
      .mockReturnValueOnce(firstSave.promise)
      .mockReturnValueOnce(secondSave.promise)
    const wrapper = mountEditor()
    await flushPromises()
    const activeEditor = (wrapper.vm as any).editor

    activeEditor.commands.setTextSelection(2)
    activeEditor.commands.insertContent('已改')
    vi.advanceTimersByTime(1000)
    await flushPromises()
    expect(patchWritingCollaborationDraft).toHaveBeenCalledTimes(1)

    const local = activeEditor.getJSON()
    activeEditor.commands.setContent({ ...local, content: [local.content[0]] })
    firstSave.resolve(twoBlockCollaboration(8))
    await flushPromises()

    expect(wrapper.text()).not.toContain('第二段')
    expect(patchWritingCollaborationDraft).toHaveBeenCalledTimes(2)
    expect(vi.mocked(patchWritingCollaborationDraft).mock.calls[1][2].changes).toEqual(
      expect.arrayContaining([expect.objectContaining({ op: 'delete', block_id: 'block-b' })])
    )
    secondSave.resolve(collaboration({
      revision: 9,
      document: { type: 'doc', content: [activeEditor.getJSON().content[0]] }
    }))
    await flushPromises()
    wrapper.unmount()
  })

  it('persists a pure block reorder as explicit move operations', async () => {
    vi.mocked(getWritingCollaboration).mockResolvedValue(twoBlockCollaboration())
    vi.mocked(patchWritingCollaborationDraft).mockResolvedValue(twoBlockCollaboration(8))
    const wrapper = mountEditor()
    await flushPromises()
    const activeEditor = (wrapper.vm as any).editor
    const current = activeEditor.getJSON()

    activeEditor.commands.setContent({ ...current, content: [...current.content].reverse() })
    vi.advanceTimersByTime(1000)
    await flushPromises()

    const changes = vi.mocked(patchWritingCollaborationDraft).mock.calls[0][2].changes || []
    expect(changes.filter(change => change.op === 'move_after')).toHaveLength(2)
    expect(changes.filter(change => change.op === 'move_after')[0]).toMatchObject({
      op: 'move_after', block_id: 'block-b', after_block_id: ''
    })
    wrapper.unmount()
  })

  it('inserts image metadata and display math blocks as structured editor content', async () => {
    const wrapper = mountEditor()
    await flushPromises()
    vi.spyOn(ElMessageBox, 'prompt')
      .mockResolvedValueOnce({ value: 'assets/diagram.png｜图1 系统结构｜系统结构示意图', action: 'confirm' } as any)
      .mockResolvedValueOnce({ value: '\\\\Phi_A^{rob}(t)=\\\\mathbb{E}[\\\\widehat\\\\Phi_A(t)]', action: 'confirm' } as any)

    await wrapper.get('[aria-label="插入图片"]').trigger('click')
    await flushPromises()
    await wrapper.get('[aria-label="插入公式"]').trigger('click')
    await flushPromises()

    const content = (wrapper.vm as any).editor.getJSON().content
    expect(JSON.stringify(content)).toContain('assets/diagram.png')
    expect(JSON.stringify(content)).toContain('图1 系统结构')
    expect(JSON.stringify(content)).toContain('系统结构示意图')
    expect(JSON.stringify(content)).toContain('artifactKind')
    expect(JSON.stringify(content)).toContain('figure-caption')
    expect(JSON.stringify(content)).toContain('rawMarkdown')
    const formula = content.find((node: any) => node.type === 'rawMarkdown')
    expect(formula?.attrs.markdown).toMatch(/^\$\$\n/)
    expect(formula?.attrs.markdown).toContain('Phi_A')
    expect(formula?.attrs.markdown).toMatch(/\n\$\$$/)
    expect(formula?.attrs.artifactKind).toBe('equation')
    expect(formula?.attrs.artifactLabel).toBe('式 1')
    wrapper.unmount()
  })

  it('inserts table captions and table artifact metadata', async () => {
    const wrapper = mountEditor()
    await flushPromises()
    vi.spyOn(ElMessageBox, 'prompt')
      .mockResolvedValueOnce({ value: '核心参数对比', action: 'confirm' } as any)

    await wrapper.get('[aria-label="插入表格"]').trigger('click')
    await flushPromises()

    const content = (wrapper.vm as any).editor.getJSON().content
    const caption = content.find((node: any) => node.attrs?.artifactKind === 'table-caption')
    const table = content.find((node: any) => node.type === 'table')
    expect(caption?.content?.[0]?.text).toBe('表 1 核心参数对比')
    expect(table?.attrs).toMatchObject({
      artifactKind: 'table',
      artifactLabel: '表 1',
      artifactTitle: '核心参数对比'
    })
    expect(JSON.stringify(table)).toContain('tableHeader')
    wrapper.unmount()
  })

  it('renumbers figure, table and equation artifacts with their captions', async () => {
    const wrapper = mountEditor()
    await flushPromises()
    const activeEditor = (wrapper.vm as any).editor

    activeEditor.commands.setContent({
      type: 'doc',
      content: [
        {
          type: 'image',
          attrs: {
            src: 'assets/a.png',
            alt: '体系结构',
            title: '体系结构',
            artifactKind: 'figure',
            artifactLabel: '图 9',
            artifactTitle: '体系结构'
          }
        },
        {
          type: 'paragraph',
          attrs: { artifactKind: 'figure-caption', artifactLabel: '图 9', artifactTitle: '体系结构' },
          content: [{ type: 'text', text: '图 9 体系结构' }]
        },
        {
          type: 'paragraph',
          attrs: { artifactKind: 'table-caption', artifactLabel: '表 7', artifactTitle: '参数表' },
          content: [{ type: 'text', text: '表 7 参数表' }]
        },
        {
          type: 'table',
          attrs: { artifactKind: 'table', artifactLabel: '表 7', artifactTitle: '参数表' },
          content: [{
            type: 'tableRow',
            content: [
              { type: 'tableHeader', content: [{ type: 'paragraph', content: [{ type: 'text', text: '指标' }] }] },
              { type: 'tableHeader', content: [{ type: 'paragraph', content: [{ type: 'text', text: '数值' }] }] }
            ]
          }]
        },
        {
          type: 'rawMarkdown',
          attrs: {
            markdown: '$$\\nE=mc^2\\n$$',
            artifactKind: 'equation',
            artifactLabel: '式 5',
            artifactTitle: 'E=mc^2'
          }
        }
      ]
    })
    ;(wrapper.vm as any).renumberArtifacts(false)
    await flushPromises()

    const content = activeEditor.getJSON().content
    expect(content[0].attrs.artifactLabel).toBe('图 1')
    expect(content[1].attrs.artifactLabel).toBe('图 1')
    expect(content[1].content[0].text).toBe('图 1 体系结构')
    expect(content[2].attrs.artifactLabel).toBe('表 1')
    expect(content[2].content[0].text).toBe('表 1 参数表')
    expect(content[3].attrs.artifactLabel).toBe('表 1')
    expect(content[4].attrs.artifactLabel).toBe('式 1')
    expect(wrapper.text()).toContain('图 1')
    expect(wrapper.text()).toContain('表 1')
    expect(wrapper.text()).toContain('式 1')
    wrapper.unmount()
  })

  it('blocks export preflight when a project image asset is missing', async () => {
    vi.mocked(getWritingCollaboration).mockResolvedValue(collaboration({
      document: {
        type: 'doc',
        content: [
          {
            type: 'image',
            attrs: {
              src: 'assets/missing.png',
              alt: '缺失图片',
              title: '缺失图片',
              blockId: 'image-1',
              blockRevision: 1,
              artifactKind: 'figure',
              artifactLabel: '图 1',
              artifactTitle: '缺失图片'
            }
          },
          {
            type: 'paragraph',
            attrs: { blockId: 'caption-1', blockRevision: 1, artifactKind: 'figure-caption', artifactLabel: '图 1', artifactTitle: '缺失图片' },
            content: [{ type: 'text', text: '图 1 缺失图片' }]
          }
        ]
      }
    }))
    vi.mocked(getDocumentWritingAsset).mockRejectedValue(new Error('not found'))
    const wrapper = mountEditor()
    await flushPromises()

    const result = await (wrapper.vm as any).prepareExportPreflight()
    await flushPromises()

    expect(result.ok).toBe(false)
    expect(result.issues).toEqual(expect.arrayContaining([
      expect.objectContaining({
        severity: 'blocker',
        message: expect.stringContaining('缺失图片资源：assets/missing.png')
      })
    ]))
    expect(wrapper.get('img[data-asset-src="assets/missing.png"]').classes()).toContain('asset-missing')
    wrapper.unmount()
  })

  it('renumbers stale artifact labels during export preflight before saving', async () => {
    vi.mocked(getWritingCollaboration).mockResolvedValue(collaboration({
      document: {
        type: 'doc',
        content: [
          {
            type: 'image',
            attrs: {
              src: 'assets/a.png',
              alt: '体系结构',
              title: '体系结构',
              blockId: 'image-1',
              blockRevision: 1,
              artifactKind: 'figure',
              artifactLabel: '图 9',
              artifactTitle: '体系结构'
            }
          },
          {
            type: 'paragraph',
            attrs: { blockId: 'caption-1', blockRevision: 1, artifactKind: 'figure-caption', artifactLabel: '图 9', artifactTitle: '体系结构' },
            content: [{ type: 'text', text: '图 9 体系结构' }]
          }
        ]
      }
    }))
    vi.mocked(patchWritingCollaborationDraft).mockImplementation(async (_projectId, _documentId, payload) => {
      const content = (payload.changes || [])
        .filter(change => change.node)
        .map(change => change.node)
      return collaboration({
        revision: 8,
        document: { type: 'doc', content }
      })
    })
    const wrapper = mountEditor()
    await flushPromises()

    const result = await (wrapper.vm as any).prepareExportPreflight()
    await flushPromises()

    expect(result.ok).toBe(true)
    expect(result.issues).toEqual(expect.arrayContaining([
      expect.objectContaining({
        severity: 'warning',
        message: expect.stringContaining('已自动重排图、表、公式编号')
      })
    ]))
    expect(patchWritingCollaborationDraft).toHaveBeenCalled()
    expect(JSON.stringify(vi.mocked(patchWritingCollaborationDraft).mock.calls[0][2])).toContain('图 1')
    wrapper.unmount()
  })

  it('lists artifact sources and inserts cross references from the artifact list', async () => {
    const wrapper = mountEditor()
    await flushPromises()
    vi.spyOn(ElMessageBox, 'prompt')
      .mockResolvedValueOnce({ value: 'assets/diagram.png｜系统结构｜系统结构示意图', action: 'confirm' } as any)
      .mockResolvedValueOnce({ value: '\\\\alpha + \\\\beta', action: 'confirm' } as any)

    await wrapper.get('[aria-label="插入图片"]').trigger('click')
    await flushPromises()
    await wrapper.get('[aria-label="插入公式"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('项目资产')
    expect(wrapper.find('.math-preview').text()).toBe('\\\\alpha + \\\\beta')

    const referenceButtons = wrapper.findAll('.artifact-list button').filter(button => button.text() === '引用')
    expect(referenceButtons.length).toBeGreaterThanOrEqual(2)
    await referenceButtons[0].trigger('click')
    await flushPromises()

    const contentText = JSON.stringify((wrapper.vm as any).editor.getJSON())
    expect(contentText).toContain('见图 1')
    wrapper.unmount()
  })

  it('uploads a local image asset and inserts it as a project asset figure', async () => {
    const wrapper = mountEditor()
    await flushPromises()
    const input = wrapper.get('.asset-input').element as HTMLInputElement
    const file = new File(['fake-png'], '体系结构.png', { type: 'image/png' })
    Object.defineProperty(input, 'files', { value: [file], configurable: true })

    await wrapper.get('[aria-label="上传图片"]').trigger('click')
    await wrapper.get('.asset-input').trigger('change')
    await flushPromises()

    expect(uploadDocumentWritingAsset).toHaveBeenCalledWith('project-1', 'document-1', file)
    const contentText = JSON.stringify((wrapper.vm as any).editor.getJSON())
    expect(contentText).toContain('assets/uploaded-image.png')
    expect(contentText).toContain('体系结构')
    expect(contentText).toContain('figure-caption')
    expect(wrapper.text()).toContain('项目资产')
    wrapper.unmount()
  })

  it('renders project asset images through authenticated blob previews without changing JSON src', async () => {
    vi.mocked(getWritingCollaboration).mockResolvedValue(collaboration({
      document: {
        type: 'doc',
        content: [
          {
            type: 'image',
            attrs: {
              src: 'assets/existing.png',
              alt: '已有图片',
              title: '已有图片',
              blockId: 'image-1',
              blockRevision: 1,
              artifactKind: 'figure',
              artifactLabel: '图 1',
              artifactTitle: '已有图片'
            }
          },
          {
            type: 'paragraph',
            attrs: { blockId: 'caption-1', blockRevision: 1, artifactKind: 'figure-caption' },
            content: [{ type: 'text', text: '图 1 已有图片' }]
          }
        ]
      }
    }))
    const wrapper = mountEditor()
    await flushPromises()

    expect(getDocumentWritingAsset).toHaveBeenCalledWith('project-1', 'document-1', 'assets/existing.png')
    const image = wrapper.get('img[data-asset-src="assets/existing.png"]')
    expect(image.attributes('src')).toBe('blob:preview-image')
    expect(JSON.stringify((wrapper.vm as any).editor.getJSON())).toContain('"src":"assets/existing.png"')
    wrapper.unmount()
  })

  it('does not replace the last valid editor state with invalid server JSON', async () => {
    vi.mocked(getWritingCollaboration).mockResolvedValue(collaboration({
      document: {
        type: 'doc',
        content: [{ type: 'unsupportedBlock', content: [{ type: 'text', text: '不应加载' }] }]
      }
    }))
    const wrapper = mountEditor()
    await flushPromises()

    expect(wrapper.text()).not.toContain('不应加载')
    expect((wrapper.vm as any).editor.getJSON().content[0].type).toBe('paragraph')
    expect(patchWritingCollaborationDraft).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
