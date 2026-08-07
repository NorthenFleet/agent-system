import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import DocumentLayoutPanel from '@/components/writing/DocumentLayoutPanel.vue'
import type { DocumentLayoutState } from '@/api/writing'

function layoutState(status: 'aligned' | 'stale' | 'missing' = 'aligned'): DocumentLayoutState {
  return {
    profiles: [{
      id: 'rich_text.doctoral.second_edition_formal.v1',
      name: '博士论文第二版正式排版',
      version: '1.0.0',
      applies_to: { kind: 'rich_text', document_types: ['博士论文'] },
      authority_source: { path: '/authority.docx', sha256: 'cce0e6ebb84f23f17b34c97cb57c59a' },
      template_path: '/template.docx',
      template_sha256: 'abcdef0123456789abcdef0123456789',
      status: 'validated',
      page: { margin_top_mm: 37, margin_bottom_mm: 35, margin_left_mm: 28, margin_right_mm: 26 },
      styles: {},
      rules: {}
    }],
    profile: {
      id: 'rich_text.doctoral.second_edition_formal.v1',
      name: '博士论文第二版正式排版',
      version: '1.0.0',
      applies_to: { kind: 'rich_text', document_types: ['博士论文'] },
      authority_source: { path: '/authority.docx', sha256: 'cce0e6ebb84f23f17b34c97cb57c59a' },
      template_path: '/template.docx',
      template_sha256: 'abcdef0123456789abcdef0123456789',
      status: 'validated',
      page: { margin_top_mm: 37, margin_bottom_mm: 35, margin_left_mm: 28, margin_right_mm: 26 },
      styles: {},
      rules: {}
    },
    binding: {
      profile_id: 'rich_text.doctoral.second_edition_formal.v1',
      content_version: 22,
      layout_revision: 'R1',
      status,
      changed_reasons: status === 'stale' ? ['正文哈希已变化'] : [],
      latest_delivery: { docx_path: '/delivery.docx' },
      delivery_history: [{ layout_revision: 'R1', content_version: 22, created_at: '2026-08-03', audit_score: 100 }]
    },
    cover: { title: '测试博士论文', author: '测试作者', advisor: '测试导师', advisor_title: '研究员', institution: '测试单位', date: '2026年8月' },
    frontmatter: { abstract_zh: 'pending', abstract_en: 'pending', keywords_zh: 'pending', keywords_en: 'pending', toc: 'generated' },
    audit: {
      generated_at: '2026-08-03T00:00:00Z',
      compliance_score: 100,
      status: 'passed',
      checks: [{ key: 'page', label: 'A4页面与页边距', passed: true, detail: '符合当前模板', severity: 'blocker' }],
      blockers: [],
      warnings: ['摘要待同步'],
      page_anomalies: []
    },
    sample: { docx_path: '/sample.docx', pdf_path: '/sample.pdf' },
    display: { content: '正文v22', template: '排版模板v1', delivery: '交付R1', publication_status: 'draft' }
  }
}

function mountPanel(layout = layoutState()) {
  return mount(DocumentLayoutPanel, {
    props: { layout },
    global: { plugins: [ElementPlus] }
  })
}

describe('DocumentLayoutPanel', () => {
  it('shows the bound template, independent versions, and draft frontmatter warning', () => {
    const wrapper = mountPanel()
    expect(wrapper.text()).toContain('博士论文第二版正式排版')
    expect(wrapper.text()).toContain('正文v22 · 排版模板v1 · 交付R1 · 草稿')
    expect(wrapper.text()).toContain('中文摘要、英文摘要或关键词尚未同步')
    expect(wrapper.text()).toContain('排版合规度')
    expect(wrapper.text()).toContain('100')
  })

  it('renders template rules and editable cover fields from backend data', () => {
    const wrapper = mountPanel()
    expect(wrapper.text()).toContain('A4 · 上37mm · 下35mm · 左28mm · 右26mm')
    expect(wrapper.text()).toContain('宋体 / Times New Roman · 10.5磅 · 固定18磅')
    const inputs = wrapper.findAll('input')
    expect(inputs.some(input => input.element.value === '测试博士论文')).toBe(true)
    expect(inputs.some(input => input.element.value === '测试作者')).toBe(true)
  })

  it('emits the selected template and edited cover on save', async () => {
    const wrapper = mountPanel()
    const title = wrapper.findAll('input').find(input => input.element.value === '测试博士论文')
    expect(title).toBeTruthy()
    await title!.setValue('修改后的论文题目')
    const saveButton = wrapper.findAll('button').find(button => button.text().includes('保存封面'))
    await saveButton!.trigger('click')
    expect(wrapper.emitted('save')?.[0]?.[0]).toMatchObject({
      profile_id: 'rich_text.doctoral.second_edition_formal.v1',
      layout_revision: 'R1',
      cover: { title: '修改后的论文题目' }
    })
  })

  it('shows explicit stale reasons instead of silently presenting an old delivery', () => {
    const wrapper = mountPanel(layoutState('stale'))
    expect(wrapper.text()).toContain('需重排')
    expect(wrapper.text()).toContain('正文哈希已变化')
  })
})
