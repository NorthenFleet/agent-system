import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import WritingWorkspacePane from '@/components/writing/WritingWorkspacePane.vue'
import {
  checkDocumentGenOfficeProof,
  getDocumentFidelityPreview,
  getDocumentGenOfficeProof,
  getGenOfficeStatus
} from '@/api/writing'

vi.mock('@/api/writing', async importOriginal => {
  const original = await importOriginal<typeof import('@/api/writing')>()
  return {
    ...original,
    getDocumentFidelityPreview: vi.fn(),
    getDocumentGenOfficeProof: vi.fn(),
    getGenOfficeStatus: vi.fn(),
    checkDocumentGenOfficeProof: vi.fn()
  }
})

describe('WritingWorkspacePane fidelity modes', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getDocumentFidelityPreview).mockResolvedValue(new Blob(['pdf'], { type: 'application/pdf' }))
    vi.mocked(getGenOfficeStatus).mockResolvedValue({
      installed: true,
      reachable: true,
      version: '0.10.1038',
      mcp_version: '0.10.0',
      channel: 'stable',
      mode: 'read_only',
      capabilities: { docs_read: true, docs_check: true, render: true, docs_apply: false, visible_editor: false }
    })
    vi.mocked(getDocumentGenOfficeProof).mockResolvedValue(new Blob(['png'], { type: 'image/png' }))
    vi.mocked(checkDocumentGenOfficeProof).mockResolvedValue({
      schema: 'openclaw.genoffice-readonly-check.v1',
      engine: { version: '0.10.1038', mcp_version: '0.10.0', channel: 'stable', mode: 'read_only', version_gate: 'tested', notice: '只读' },
      source: { kind: 'imported_original_docx', sha256: 'a'.repeat(64), read_only: true, authority: 'imported_source_only', notice: '不会写回正文' },
      read: { summary: '3 blocks', blocks: 3, range: '0-2', items: [] },
      check: { summary: '1 issue', counts: { error: 0, warning: 1, info: 0 }, issues: [{ id: 'W1', level: 'warning', message: '目录过期' }], truncated: false }
    })
    Object.defineProperty(URL, 'createObjectURL', {
      value: vi.fn((blob: Blob) => blob.type === 'image/png' ? 'blob:office-proof' : 'blob:wps-preview'),
      configurable: true
    })
    Object.defineProperty(URL, 'revokeObjectURL', { value: vi.fn(), configurable: true })
  })

  function mountPane() {
    return mount(WritingWorkspacePane, {
      props: {
        mode: 'document',
        projectId: 'project-1',
        sourceDocument: { id: 'document-1', title: '研究报告', kind: 'rich_text' } as any,
        sectionId: 'section-1',
        outline: []
      },
      global: {
        plugins: [ElementPlus],
        stubs: {
          CollaborativeWritingEditor: {
            template: '<div data-test="editor">编辑视图</div>',
            methods: { flushDraft: () => true }
          },
          PresentationWorkspace: true,
          WritingAiPane: true
        }
      }
    })
  }

  it('switches a rich-text document from editing to read-only WPS preview', async () => {
    const wrapper = mountPane()
    await flushPromises()
    expect(wrapper.text()).toContain('编辑视图')

    await (wrapper.vm as any).changeDocumentView('preview')
    await flushPromises()

    expect(getDocumentFidelityPreview).toHaveBeenCalledWith('project-1', 'document-1')
    expect(wrapper.get('.wps-preview iframe').attributes('src')).toBe('blob:wps-preview')
    expect(wrapper.text()).toContain('最终 DOCX 同源分页、只读')
    wrapper.unmount()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:wps-preview')
  })

  it('shows a separate read-only GenOffice proof and structural check', async () => {
    const wrapper = mountPane()

    await (wrapper.vm as any).changeDocumentView('office')
    await flushPromises()

    expect(getGenOfficeStatus).toHaveBeenCalledTimes(1)
    expect(getDocumentGenOfficeProof).toHaveBeenCalledWith('project-1', 'document-1')
    expect(wrapper.get('.office-proof img').attributes('src')).toBe('blob:office-proof')
    expect(wrapper.text()).toContain('只读取已导入的 Word 原件')
    expect(wrapper.text()).toContain('GenOffice 0.10.1038 · MCP 0.10.0 · 只读模式')

    await (wrapper.vm as any).runOfficeCheck()
    await flushPromises()

    expect(checkDocumentGenOfficeProof).toHaveBeenCalledWith('project-1', 'document-1')
    expect(wrapper.text()).toContain('目录过期')
    wrapper.unmount()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:office-proof')
  })

  it('ignores an in-flight GenOffice proof after the document context changes', async () => {
    const oldProof = new Blob(['old proof'], { type: 'image/png' })
    const newProof = new Blob(['new proof'], { type: 'image/png' })
    let resolveOldProof!: (proof: Blob) => void
    const oldProofRequest = new Promise<Blob>(resolve => {
      resolveOldProof = resolve
    })
    vi.mocked(getDocumentGenOfficeProof)
      .mockImplementationOnce(() => oldProofRequest)
      .mockResolvedValueOnce(newProof)
    vi.mocked(URL.createObjectURL).mockImplementation(blob => (
      blob === oldProof ? 'blob:old-office-proof' : 'blob:new-office-proof'
    ))

    const wrapper = mountPane()
    const firstOfficeLoad = (wrapper.vm as any).changeDocumentView('office')
    await flushPromises()
    expect(getDocumentGenOfficeProof).toHaveBeenCalledWith('project-1', 'document-1')

    await wrapper.setProps({
      projectId: 'project-2',
      sourceDocument: { id: 'document-2', title: '第二份研究报告', kind: 'rich_text' } as any
    })
    await flushPromises()
    await flushPromises()

    expect(getDocumentGenOfficeProof).toHaveBeenLastCalledWith('project-2', 'document-2')
    expect(wrapper.get('.office-proof img').attributes('src')).toBe('blob:new-office-proof')

    resolveOldProof(oldProof)
    await firstOfficeLoad
    await flushPromises()

    expect(wrapper.get('.office-proof img').attributes('src')).toBe('blob:new-office-proof')
    expect(vi.mocked(URL.createObjectURL).mock.calls.some(([blob]) => blob === oldProof)).toBe(false)
  })

  it('keeps structured editing usable when the GenOffice engine is unavailable', async () => {
    vi.mocked(getGenOfficeStatus).mockResolvedValueOnce({
      installed: false,
      reachable: false,
      version: '',
      channel: 'stable',
      mode: 'unavailable',
      capabilities: { docs_read: false, docs_check: false, render: false, docs_apply: false, visible_editor: false },
      reason: 'GenOffice 验签或 Sidecar 尚未就绪'
    })
    const wrapper = mountPane()

    await (wrapper.vm as any).changeDocumentView('office')
    await flushPromises()

    expect(getDocumentGenOfficeProof).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('GenOffice 验签或 Sidecar 尚未就绪')

    await (wrapper.vm as any).changeDocumentView('edit')
    await flushPromises()
    expect(wrapper.get('[data-test="editor"]').text()).toBe('编辑视图')
  })
})
