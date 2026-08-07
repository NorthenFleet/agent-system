import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import DocumentStructureStatus from '@/components/writing/DocumentStructureStatus.vue'
import type { WritingStructureSync } from '@/api/writing'

const base: WritingStructureSync = {
  status: 'aligned',
  message: '当前结构与目标目录一致。',
  current_version: 'v14',
  target_version: 'v14',
  current_sha256: 'current',
  target_sha256: 'current',
  source_matches: true,
  chapter_count_delta: 0,
  heading_count_delta: 0,
  changed_chapters: []
}

function render(sync: WritingStructureSync) {
  return mount(DocumentStructureStatus, {
    props: {
      sync,
      targetLabel: '送审目标'
    },
    global: {
      stubs: {
        'el-tag': { template: '<span class="tag"><slot /></span>' }
      }
    }
  })
}

describe('DocumentStructureStatus', () => {
  it('shows an aligned version label', () => {
    const wrapper = render(base)

    expect(wrapper.attributes('data-structure-sync-status')).toBe('aligned')
    expect(wrapper.text()).toContain('当前结构与送审目标一致 · v14')
  })

  it('shows changed chapters when structures diverge', () => {
    const wrapper = render({
      ...base,
      status: 'diverged',
      message: '当前结构与目标目录存在差异，涉及2章。',
      source_matches: false,
      changed_chapters: [2, 5]
    })

    expect(wrapper.attributes('data-structure-sync-status')).toBe('diverged')
    expect(wrapper.text()).toContain('当前结构与送审目标存在差异')
    expect(wrapper.text()).toContain('涉及第2、5章')
  })

  it('shows a missing-target state without hiding the current structure', () => {
    const wrapper = render({
      ...base,
      status: 'missing',
      message: '未设置目标目录，当前结构仍可正常使用。',
      target_version: '',
      target_sha256: '',
      source_matches: false
    })

    expect(wrapper.attributes('data-structure-sync-status')).toBe('missing')
    expect(wrapper.text()).toContain('未设置送审目标')
    expect(wrapper.text()).toContain('当前结构仍可正常使用')
  })
})
