import { describe, expect, it } from 'vitest'
import { nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import WritingLinkedWorkspace from '@/components/writing/WritingLinkedWorkspace.vue'
import type { WritingProjectDocument } from '@/api/writing'

const sourceDocument: WritingProjectDocument = {
  id: 'doc-1',
  title: '博士论文正文',
  kind: 'rich_text',
  status: 'active',
  sort_order: 0,
  is_primary: true,
  is_output_product: true,
  output_format: 'docx',
  data_source_ids: [],
  print_profile: 'doctoral',
  publication_status: 'draft',
  rules_version: 'v1',
  data_version: 'v1',
  expected_chapters: 7,
  revision: 1,
  created_at: '2026-08-07T00:00:00Z',
  updated_at: '2026-08-07T00:00:00Z'
}

const presentationDocument: WritingProjectDocument = {
  ...sourceDocument,
  id: 'ppt-1',
  title: '博士答辩 PPT',
  kind: 'presentation',
  is_primary: false,
  output_format: 'pptx'
}

describe('WritingLinkedWorkspace', () => {
  it('defaults to document on the left and PPT on the right, then swaps panes', async () => {
    const wrapper = mount(WritingLinkedWorkspace, {
      props: {
        projectId: 'project-1',
        sourceDocument,
        presentationDocument,
        sectionId: 'section-1',
        outline: []
      },
      global: {
        plugins: [ElementPlus],
        stubs: {
          WritingWorkspacePane: {
            name: 'WritingWorkspacePane',
            props: ['mode'],
            template: '<div class="pane-stub" :data-mode="mode" />'
          }
        }
      }
    })

    expect(wrapper.text()).toContain('联动工作台')
    expect(wrapper.findAll('.pane-stub').map(node => node.attributes('data-mode'))).toEqual([
      'document',
      'presentation'
    ])

    await wrapper.get('.layout-controls button').trigger('click')
    await nextTick()
    expect(wrapper.findAll('.pane-stub').map(node => node.attributes('data-mode'))).toEqual([
      'presentation',
      'document'
    ])

    wrapper.unmount()
  })

  it('lets either window switch to the AI module', async () => {
    const wrapper = mount(WritingLinkedWorkspace, {
      props: {
        projectId: 'project-1',
        sourceDocument,
        presentationDocument,
        sectionId: 'section-1',
        outline: []
      },
      global: {
        plugins: [ElementPlus],
        stubs: {
          WritingWorkspacePane: {
            name: 'WritingWorkspacePane',
            props: ['mode'],
            template: '<div class="pane-stub" :data-mode="mode" />'
          }
        }
      }
    })

    ;(wrapper.vm as any).leftMode = 'ai'
    await nextTick()
    expect(wrapper.findAll('.pane-stub')[0].attributes('data-mode')).toBe('ai')
    wrapper.unmount()
  })
})
