import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import WritingWorkspacePane from '@/components/writing/WritingWorkspacePane.vue'
import { getDocumentFidelityPreview } from '@/api/writing'

vi.mock('@/api/writing', async importOriginal => {
  const original = await importOriginal<typeof import('@/api/writing')>()
  return { ...original, getDocumentFidelityPreview: vi.fn() }
})

describe('WritingWorkspacePane fidelity modes', () => {
  beforeEach(() => {
    vi.mocked(getDocumentFidelityPreview).mockResolvedValue(new Blob(['pdf'], { type: 'application/pdf' }))
    Object.defineProperty(URL, 'createObjectURL', { value: vi.fn(() => 'blob:wps-preview'), configurable: true })
    Object.defineProperty(URL, 'revokeObjectURL', { value: vi.fn(), configurable: true })
  })

  it('switches a rich-text document from editing to read-only WPS preview', async () => {
    const wrapper = mount(WritingWorkspacePane, {
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
})
