import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import WritingLinkedWorkspace from '@/components/writing/WritingLinkedWorkspace.vue'
import type { WritingProjectDocument } from '@/api/writing'
import { getWritingWorkbenchPreference, updateWritingWorkbenchPreference } from '@/api/writing'

vi.mock('@/api/writing', async importOriginal => {
  const original = await importOriginal<typeof import('@/api/writing')>()
  return {
    ...original,
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

function preference(revision = 0) {
  return {
    schema_version: 1 as const,
    revision,
    preset: 'writing' as const,
    split_percent: 42,
    panes: {
      left: { module: 'ai' as const, ai_target_locked: false },
      right: { module: 'document' as const, resource_id: 'doc-1', section_id: 'section-1', ai_target_locked: false }
    }
  }
}

function mountWorkbench() {
  return mount(WritingLinkedWorkspace, {
    props: {
      projectId: 'project-1', sourceDocument, presentationDocument,
      sourceDocuments: [sourceDocument], presentationDocuments: [presentationDocument],
      sectionId: 'section-1', outline: []
    },
    global: {
      plugins: [ElementPlus],
      stubs: {
        WritingWorkspacePane: {
          name: 'WritingWorkspacePane',
          props: ['mode', 'readOnly', 'sourceDocument', 'presentationDocument'],
          template: '<div class="pane-stub" :data-mode="mode" :data-readonly="String(Boolean(readOnly))" />'
        }
      }
    }
  })
}

beforeEach(() => {
  vi.mocked(getWritingWorkbenchPreference).mockResolvedValue(preference())
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

    await (wrapper.vm as any).applyPreset('comparison')
    await flushPromises()
    expect(wrapper.findAll('.pane-stub').map(node => node.attributes('data-mode'))).toEqual(['document', 'presentation'])
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
})
