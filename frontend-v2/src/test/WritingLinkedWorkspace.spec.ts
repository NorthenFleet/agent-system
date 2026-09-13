import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import WritingLinkedWorkspace from '@/components/writing/WritingLinkedWorkspace.vue'
import type { WritingProjectDocument } from '@/api/writing'
import {
  compareWritingDocuments,
  getDocumentWritingWorkspace,
  getWritingDiagrams,
  getWritingWorkbenchPreference,
  updateWritingWorkbenchPreference
} from '@/api/writing'

vi.mock('@/api/writing', async importOriginal => {
  const original = await importOriginal<typeof import('@/api/writing')>()
  return {
    ...original,
    compareWritingDocuments: vi.fn(),
    getDocumentWritingWorkspace: vi.fn(),
    getWritingDiagrams: vi.fn(),
    getWritingWorkbenchPreference: vi.fn(),
    updateWritingWorkbenchPreference: vi.fn()
  }
})

const sourceDocument: WritingProjectDocument = {
  id: 'doc-1', title: '博士论文正文', kind: 'rich_text', status: 'active', sort_order: 0,
  is_primary: true, is_output_product: true, output_format: 'docx', data_source_ids: [],
  print_profile: 'doctoral', publication_status: 'draft', rules_version: 'v1', data_version: 'v1',
  product_type: '', course_unit_ids: [], quality_profile: '', required_for_release: false, source_refs: [],
  expected_chapters: 7, revision: 1, created_at: '2026-08-07T00:00:00Z', updated_at: '2026-08-07T00:00:00Z'
}

const presentationDocument: WritingProjectDocument = {
  ...sourceDocument, id: 'ppt-1', title: '博士答辩 PPT', kind: 'presentation', is_primary: false, output_format: 'pptx'
}

const historicalDocument: WritingProjectDocument = {
  ...sourceDocument,
  id: 'doc-2',
  title: '博士论文·第二版',
  is_primary: false,
  edit_policy: 'read_only',
  delivery_role: 'historical_reference',
  lineage: { series_id: 'doctoral-thesis', edition_label: '第二版', sequence: 2, source_type: 'chapter_bundle', source_checksum: 'b'.repeat(64) }
}

function preference(revision = 0) {
  return {
    schema_version: 2 as const,
    revision,
    preset: 'writing' as const,
    split_percent: 42,
    panes: {
      left: { module: 'ai' as const, ai_target_locked: false },
      right: { module: 'document' as const, resource_id: 'doc-1', section_id: 'section-1', ai_target_locked: false }
    }
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}

function mountWorkbench(extraProps: Record<string, unknown> = {}) {
  return mount(WritingLinkedWorkspace, {
    props: {
      projectId: 'project-1', sourceDocument, presentationDocument,
      sourceDocuments: [historicalDocument, sourceDocument], presentationDocuments: [presentationDocument],
      sectionId: 'section-1', outline: [],
      ...extraProps
    },
    global: {
      plugins: [ElementPlus],
      stubs: {
        WritingWorkspacePane: {
          name: 'WritingWorkspacePane',
          props: ['mode', 'readOnly', 'sourceDocument', 'presentationDocument', 'sectionId'],
          template: '<div class="pane-stub" :data-mode="mode" :data-readonly="String(Boolean(readOnly))" :data-section="sectionId || \'\'" />'
        }
      }
    }
  })
}

beforeEach(() => {
  vi.mocked(getWritingWorkbenchPreference).mockResolvedValue(preference())
  vi.mocked(getDocumentWritingWorkspace).mockResolvedValue({ directory: [] } as any)
  vi.mocked(getWritingDiagrams).mockResolvedValue({ diagrams: [] })
  vi.mocked(compareWritingDocuments).mockResolvedValue({
    cache_key: 'compare', cached: false,
    left: { document_id: 'doc-2', title: '第二版', revision: 1, checksum: 'b' },
    right: { document_id: 'doc-1', title: '第三版', revision: 1, checksum: 'a' },
    summary: { added: 1, deleted: 0, modified: 1, unchanged: 2 },
    sections: []
  })
  vi.mocked(updateWritingWorkbenchPreference).mockImplementation(async (_projectId, payload) => ({
    ...payload,
    revision: Number(payload.expected_revision || 0) + 1
  } as any))
})

describe('WritingLinkedWorkspace', () => {
  it('opens the writing preset as AI plus document and supports comparison preset', async () => {
    const wrapper = mountWorkbench()
    await flushPromises()

    expect(wrapper.text()).toContain('协同工作台')
    expect(wrapper.findAll('.pane-stub').map(node => node.attributes('data-mode'))).toEqual(['ai', 'document'])

    await (wrapper.vm as any).applyPreset('document_compare')
    await flushPromises()
    expect(wrapper.findAll('.pane-stub').map(node => node.attributes('data-mode'))).toEqual(['document', 'document'])
    expect(wrapper.findAll('.pane-stub').map(node => node.attributes('data-section'))).toEqual(['', ''])
    expect(wrapper.text()).toContain('版本差异')
    wrapper.unmount()
  })

  it('does not substitute an unrelated first presentation when the document has no binding', async () => {
    const wrapper = mountWorkbench({
      presentationDocument: undefined,
      initialPreset: 'presentation',
      initialPresetOverride: true
    })
    await flushPromises()

    expect((wrapper.vm as any).rightPane.module).toBe('presentation')
    expect((wrapper.vm as any).rightPane.resource_id).toBeUndefined()
    wrapper.unmount()
  })

  it('opens the diagramming preset as AI plus a selected diagram', async () => {
    vi.mocked(getWritingDiagrams).mockResolvedValue({
      diagrams: [{
        id: 'diagram-1', title: '论文技术路线图', kind: 'diagram', status: 'active',
        edit_policy: 'editable', revision: 3, updated_at: '2026-08-09T00:00:00Z'
      } as any]
    })
    const wrapper = mountWorkbench()
    await flushPromises()

    await (wrapper.vm as any).applyPreset('diagramming')
    await flushPromises()

    expect(wrapper.findAll('.pane-stub').map(node => node.attributes('data-mode'))).toEqual(['ai', 'diagram'])
    expect((wrapper.vm as any).rightPane.resource_id).toBe('diagram-1')
    wrapper.unmount()
  })

  it('enforces single-write multi-read when both panes open the same resource', async () => {
    const wrapper = mountWorkbench()
    await flushPromises()

    ;(wrapper.vm as any).leftPane = { module: 'document', resource_id: 'doc-1', section_id: 'section-1' }
    ;(wrapper.vm as any).rightPane = { module: 'document', resource_id: 'doc-1', section_id: 'section-1' }
    await flushPromises()

    const panes = wrapper.findAll('.pane-stub')
    expect(panes[0].attributes('data-readonly')).toBe('false')
    expect(panes[1].attributes('data-readonly')).toBe('true')
    wrapper.unmount()
  })

  it('swaps complete pane state instead of only swapping visible labels', async () => {
    const wrapper = mountWorkbench()
    await flushPromises()

    await (wrapper.vm as any).swapPanes()
    await flushPromises()
    expect(wrapper.findAll('.pane-stub').map(node => node.attributes('data-mode'))).toEqual(['document', 'ai'])
    wrapper.unmount()
  })

  it('labels the primary candidate as the current body authority and the old deliverable as frozen', async () => {
    const wrapper = mountWorkbench()
    await flushPromises()
    const label = (wrapper.vm as any).documentOptionLabel

    expect(label({
      ...sourceDocument,
      delivery_role: 'candidate',
      is_primary: true
    })).toContain('当前正文权威，交付待冻结')
    expect(label({
      ...sourceDocument,
      delivery_role: 'deliverable',
      edit_policy: 'read_only',
      is_primary: false
    })).toContain('冻结交付基线，只读')
    wrapper.unmount()
  })

  it('lets an explicit legacy URL preset override a stored layout', async () => {
    vi.mocked(getWritingWorkbenchPreference).mockResolvedValue({
      ...preference(9),
      preset: 'document_presentation',
      split_percent: 50,
      panes: {
        left: { module: 'document', resource_id: 'doc-1', section_id: 'section-1', ai_target_locked: false },
        right: { module: 'presentation', resource_id: 'ppt-1', slide: 1, ai_target_locked: false }
      }
    })
    const wrapper = mountWorkbench({ initialPreset: 'presentation', initialPresetOverride: true })
    await flushPromises()

    expect(wrapper.findAll('.pane-stub').map(node => node.attributes('data-mode'))).toEqual(['ai', 'presentation'])
    wrapper.unmount()
  })

  it('replaces a stored document that is no longer available and persists the repaired layout', async () => {
    vi.mocked(getWritingWorkbenchPreference).mockResolvedValue({
      ...preference(7),
      preset: 'custom',
      panes: {
        left: { module: 'document', resource_id: 'archived-candidate', section_id: 'stale-section', ai_target_locked: false },
        right: { module: 'document', resource_id: 'doc-1', section_id: 'section-1', ai_target_locked: false }
      }
    } as any)
    const wrapper = mountWorkbench()
    await flushPromises()

    expect((wrapper.vm as any).leftPane.resource_id).toBe('doc-2')
    expect((wrapper.vm as any).leftPane.section_id).toBeUndefined()
    expect((wrapper.vm as any).rightPane.resource_id).toBe('doc-1')
    await new Promise(resolve => setTimeout(resolve, 550))
    await flushPromises()
    expect(updateWritingWorkbenchPreference).toHaveBeenCalledWith(
      'project-1',
      expect.objectContaining({
        expected_revision: 7,
        panes: expect.objectContaining({
          left: expect.objectContaining({ resource_id: 'doc-2' }),
          right: expect.objectContaining({ resource_id: 'doc-1' })
        })
      })
    )
    wrapper.unmount()
  })

  it('serializes layout saves so a queued update uses the latest revision', async () => {
    vi.mocked(getWritingWorkbenchPreference).mockResolvedValue(preference(4))
    const wrapper = mountWorkbench()
    await flushPromises()
    await new Promise(resolve => setTimeout(resolve, 550))
    await flushPromises()
    const initialRevision = Number((wrapper.vm as any).preferenceRevision)
    const firstSave = deferred<any>()
    vi.mocked(updateWritingWorkbenchPreference).mockReset()
    vi.mocked(updateWritingWorkbenchPreference)
      .mockReturnValueOnce(firstSave.promise)
      .mockImplementationOnce(async (_projectId, payload) => ({
        ...payload,
        revision: Number(payload.expected_revision || 0) + 1
      } as any))

    ;(wrapper.vm as any).splitPercent = 44
    ;(wrapper.vm as any).schedulePersist()
    await new Promise(resolve => setTimeout(resolve, 550))
    expect(updateWritingWorkbenchPreference).toHaveBeenCalledTimes(1)
    expect(updateWritingWorkbenchPreference).toHaveBeenLastCalledWith(
      'project-1',
      expect.objectContaining({ expected_revision: initialRevision, split_percent: 44 })
    )

    ;(wrapper.vm as any).splitPercent = 46
    ;(wrapper.vm as any).schedulePersist()
    await new Promise(resolve => setTimeout(resolve, 550))
    expect(updateWritingWorkbenchPreference).toHaveBeenCalledTimes(1)

    firstSave.resolve({ ...preference(initialRevision + 1), split_percent: 44 })
    await flushPromises()
    expect(updateWritingWorkbenchPreference).toHaveBeenCalledTimes(2)
    expect(updateWritingWorkbenchPreference).toHaveBeenLastCalledWith(
      'project-1',
      expect.objectContaining({ expected_revision: initialRevision + 1, split_percent: 46 })
    )
    wrapper.unmount()
  })

  it('waits for the selected document outline and replaces a stale stored section', async () => {
    const outlineRequest = deferred<any>()
    vi.mocked(getDocumentWritingWorkspace).mockReturnValueOnce(outlineRequest.promise)
    vi.mocked(getWritingWorkbenchPreference).mockResolvedValue({
      ...preference(3),
      panes: {
        left: { module: 'ai', ai_target_locked: false },
        right: { module: 'document', resource_id: 'doc-2', section_id: 'section-from-another-document', ai_target_locked: false }
      }
    } as any)
    const wrapper = mountWorkbench()
    await flushPromises()

    expect(wrapper.findAll('.pane-stub').map(node => node.attributes('data-mode'))).toEqual(['ai'])

    outlineRequest.resolve({
      directory: [{
        id: 'section-2', title: '第一章 绪论', node_type: 'section', source_level: 1,
        level: 1, line: 1, anchor: 'section-2', target_id: 'section-2', section_id: 'section-2', children: []
      }]
    })
    await flushPromises()

    const documentPane = wrapper.findAll('.pane-stub').find(node => node.attributes('data-mode') === 'document')
    expect(documentPane?.attributes('data-section')).toBe('section-2')
    wrapper.unmount()
  })

  it('handles a persisted null section id without crashing outline matching', async () => {
    vi.mocked(getWritingWorkbenchPreference).mockResolvedValue({
      ...preference(5),
      panes: {
        left: { module: 'ai', ai_target_locked: false },
        right: {
          module: 'document', resource_id: 'doc-1', section_id: null, ai_target_locked: false
        }
      }
    } as any)
    vi.mocked(getDocumentWritingWorkspace).mockResolvedValue({
      directory: [{
        id: 'section-1', title: null, node_type: 'section', source_level: 1,
        level: 1, line: 1, anchor: 'section-1', target_id: 'section-1',
        section_id: 'section-1', children: []
      }]
    } as any)

    const wrapper = mountWorkbench()
    await flushPromises()

    expect(wrapper.findAll('.pane-stub').map(node => node.attributes('data-mode'))).toEqual(['ai', 'document'])
    expect((wrapper.vm as any).rightPane.section_id).toBeUndefined()
    wrapper.unmount()
  })

  it('keeps alternate-document outline navigation inside its pane', async () => {
    const wrapper = mountWorkbench()
    await flushPromises()
    const alternateSection = {
      id: 'historical-section-3', title: '第三章 历史版本章节', node_type: 'section', source_level: 1,
      level: 1, line: 10, anchor: 'historical-section-3', target_id: 'historical-section-3',
      section_id: 'historical-section-3', children: []
    } as WritingDirectoryNode
    const currentSection = {
      ...alternateSection,
      id: 'section-1', title: '第一章 绪论', anchor: 'section-1', target_id: 'section-1', section_id: 'section-1'
    }

    ;(wrapper.vm as any).leftPane = { module: 'document', resource_id: 'doc-2', section_id: 'section-2' }
    ;(wrapper.vm as any).handleOutlineSelection('left', alternateSection)
    await flushPromises()
    expect(wrapper.emitted('select-outline')).toBeUndefined()

    ;(wrapper.vm as any).rightPane = { module: 'document', resource_id: 'doc-1', section_id: 'section-1' }
    ;(wrapper.vm as any).handleOutlineSelection('right', currentSection)
    await flushPromises()
    expect(wrapper.emitted('select-outline')).toEqual([[currentSection]])
    wrapper.unmount()
  })

  it('keeps left and right chapter selections independent by default', async () => {
    const leftSection = {
      id: 'historical-section-3', title: '第三章 历史版本章节', node_type: 'section', source_level: 1,
      level: 1, line: 10, anchor: 'historical-section-3', target_id: 'historical-section-3',
      section_id: 'historical-section-3', children: []
    } as WritingDirectoryNode
    const rightSection = {
      ...leftSection,
      id: 'section-4', title: '第四章 当前版本章节', anchor: 'section-4',
      target_id: 'section-4', section_id: 'section-4'
    }
    const originalRightSection = {
      ...rightSection,
      id: 'section-1', title: '第一章 绪论', anchor: 'section-1',
      target_id: 'section-1', section_id: 'section-1'
    }
    vi.mocked(getDocumentWritingWorkspace).mockImplementation(async (_projectId, documentId) => ({
      directory: documentId === historicalDocument.id ? [leftSection] : [originalRightSection, rightSection]
    } as any))
    const wrapper = mountWorkbench({ outline: [originalRightSection, rightSection] })
    await flushPromises()
    await (wrapper.vm as any).applyPreset('document_compare')
    await flushPromises()

    ;(wrapper.vm as any).rightPane = { module: 'document', resource_id: 'doc-1', section_id: 'section-1' }
    ;(wrapper.vm as any).handleOutlineSelection('left', leftSection)
    await flushPromises()
    expect((wrapper.vm as any).leftPane.section_id).toBe(leftSection.section_id)
    expect((wrapper.vm as any).rightPane.section_id).toBe('section-1')

    ;(wrapper.vm as any).handleOutlineSelection('right', rightSection)
    await flushPromises()
    expect((wrapper.vm as any).leftPane.section_id).toBe(leftSection.section_id)
    expect((wrapper.vm as any).rightPane.section_id).toBe(rightSection.section_id)
    wrapper.unmount()
  })

  it('maps equivalent chapters across versions without reusing the other document section id', async () => {
    const historicalSection = {
      id: 'section-01-第一章-绪论', title: '第一章 绪论', node_type: 'section', source_level: 1,
      level: 1, line: 1, anchor: 'section-01-第一章-绪论', target_id: 'section-01-第一章-绪论',
      section_id: 'section-01-第一章-绪论', children: []
    } as WritingDirectoryNode
    const currentSection = {
      ...historicalSection,
      id: 'section-01-第1章-绪论', title: '第1章 绪论', anchor: 'section-01-第1章-绪论',
      target_id: 'section-01-第1章-绪论', section_id: 'section-01-第1章-绪论'
    }
    vi.mocked(getDocumentWritingWorkspace).mockImplementation(async (_projectId, documentId) => ({
      directory: documentId === historicalDocument.id ? [historicalSection] : [currentSection]
    } as any))
    vi.mocked(compareWritingDocuments).mockResolvedValue({
      cache_key: 'compare-numbering', cached: false,
      left: { document_id: historicalDocument.id, title: '第二版', revision: 1, checksum: 'b' },
      right: { document_id: sourceDocument.id, title: '第三版', revision: 1, checksum: 'a' },
      summary: { added: 0, deleted: 0, modified: 1, unchanged: 0 },
      sections: [{
        key: 'chapter-1', left_title: '第一章 绪论', right_title: '第1章 绪论',
        changes: [{ operation: 'modified', left_text: '旧', right_text: '新' }]
      }]
    } as any)

    const wrapper = mountWorkbench({ outline: [currentSection] })
    await flushPromises()
    await (wrapper.vm as any).applyPreset('document_compare')
    await flushPromises()
    ;(wrapper.vm as any).syncComparisonSections = true
    ;(wrapper.vm as any).handleOutlineSelection('left', historicalSection)
    await flushPromises()

    expect((wrapper.vm as any).leftPane.section_id).toBe(historicalSection.section_id)
    expect((wrapper.vm as any).rightPane.section_id).toBe(currentSection.section_id)
    wrapper.unmount()
  })
})
