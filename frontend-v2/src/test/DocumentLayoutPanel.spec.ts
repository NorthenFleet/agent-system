import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import DocumentLayoutPanel from '@/components/writing/DocumentLayoutPanel.vue'
import type { DocumentLayoutProfile, DocumentLayoutState } from '@/api/writing'

const profile = (id = 'course-plan-word-a1b2c3', type = 'course_plan'): DocumentLayoutProfile => ({
  id, name: '课程教学计划·当前 Word 模板', version: 'sha-a1b2c3',
  applies_to: { kind: 'rich_text', document_types: [type] },
  authority_source: { sha256: 'a1b2c3d4e5f6', filename: '课程教学计划-v14.docx', document_title: '课程教学计划' },
  template_path: '/template.docx', template_sha256: 'a1b2c3d4e5f6', status: 'validated', page: {}, styles: {}, rules: { template_mode: 'reference_docx' },
  preview: { pdf_path: '/preview.pdf', page_count: 3, showcase_pages: [{ kind: 'cover', label: '封面/首页', page: 1 }, { kind: 'frontmatter', label: '目录或前置页', page: 2 }, { kind: 'body', label: '正文样式', page: 3 }] }
})

function layoutState(status: 'aligned' | 'stale' | 'missing' = 'aligned'): DocumentLayoutState {
  const current = profile()
  return {
    profiles: [current, profile('course-plan-word-d4e5f6', 'course_plan')], profile: current,
    template_catalog: { document_type: 'course_plan', same_type_count: 2, total_count: 2 },
    binding: { profile_id: current.id, content_version: 22, layout_revision: 'R1', status, changed_reasons: status === 'stale' ? ['正文哈希已变化'] : [], latest_delivery: { docx_path: '/delivery.docx' } },
    cover: {}, frontmatter: { abstract_zh: 'pending', abstract_en: 'pending', keywords_zh: 'pending', keywords_en: 'pending', toc: 'generated' },
    audit: { generated_at: '2026-08-03T00:00:00Z', compliance_score: 100, status: 'passed', checks: [{ key: 'page', label: '页面设置', passed: true, detail: '符合当前模板', severity: 'blocker' }], blockers: [], warnings: [], page_anomalies: [] },
    sample: { docx_path: '/sample.docx', pdf_path: '/sample.pdf' }, display: { content: '正文v22', template: '排版模板v1', delivery: '交付R1', publication_status: 'draft' }
  }
}

function mountPanel(layout = layoutState()) { return mount(DocumentLayoutPanel, { props: { layout, templatePreviewUrls: { 'course-plan-word-a1b2c3:1': 'blob:cover', 'course-plan-word-a1b2c3:2': 'blob:toc', 'course-plan-word-a1b2c3:3': 'blob:body' } }, global: { plugins: [ElementPlus] } }) }

describe('DocumentLayoutPanel', () => {
  it('shows real Word template cards and independent delivery state', () => {
    const wrapper = mountPanel()
    expect(wrapper.text()).toContain('历史 Word 版式库')
    expect(wrapper.text()).toContain('课程教学计划·当前 Word 模板')
    expect(wrapper.text()).toContain('第 1 页 · 封面/首页')
    expect(wrapper.text()).toContain('第 2 页 · 目录或前置页')
    expect(wrapper.text()).toContain('正文v22 · 排版模板v1 · 交付R1 · 草稿')
    expect(wrapper.findAll('img')).toHaveLength(3)
  })

  it('does not render generic thesis cover fields for a reference Word', () => {
    const wrapper = mountPanel()
    expect(wrapper.text()).toContain('来自选中 Word，不套用通用规则')
    expect(wrapper.text()).not.toContain('导师职称')
    expect(wrapper.text()).not.toContain('宋体 / Times New Roman')
  })

  it('emits a binding change only after selecting another template', async () => {
    const wrapper = mountPanel()
    const select = wrapper.findAll('button').find(button => button.text().includes('选择此模板'))
    expect(select).toBeTruthy()
    await select!.trigger('click')
    expect(wrapper.emitted('save')?.[0]?.[0]).toMatchObject({ profile_id: 'course-plan-word-d4e5f6', layout_revision: 'R1', cover: {} })
  })

  it('shows explicit stale reasons instead of silently presenting an old delivery', () => {
    const wrapper = mountPanel(layoutState('stale'))
    expect(wrapper.text()).toContain('需重排')
    expect(wrapper.text()).toContain('正文哈希已变化')
  })

  it('opens the selected template preview instead of manufacturing a sample', async () => {
    const wrapper = mountPanel()
    const preview = wrapper.findAll('button').find(button => button.text().includes('查看完整 Word 样张'))
    await preview!.trigger('click')
    expect(wrapper.emitted('preview-template')?.[0]).toEqual(['course-plan-word-a1b2c3'])
  })
})
