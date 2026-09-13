import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import PresentationWorkspace from '@/components/writing/PresentationWorkspace.vue'
import type { PresentationManifest, WritingProjectDocument } from '@/api/writing'

const mocks = vi.hoisted(() => ({
  manifest: undefined as PresentationManifest | undefined,
  createSlideJob: vi.fn(),
  getSlideJob: vi.fn(),
  preview: vi.fn(),
  versions: vi.fn(),
  source: vi.fn(),
  replace: vi.fn(),
  restore: vi.fn(),
  updateBinding: vi.fn(),
  evaluationProfile: vi.fn(),
  evaluation: vi.fn(),
  linkedEvaluation: vi.fn(),
  evaluationProfiles: vi.fn()
}))

vi.mock('@/api/writing', async importOriginal => {
  const original = await importOriginal<Record<string, unknown>>()
  return {
    ...original,
    createPresentationSlideJob: mocks.createSlideJob,
    getPresentationSlideJob: mocks.getSlideJob,
    getPresentationPreview: mocks.preview,
    getPresentationManifest: vi.fn(() => Promise.resolve(mocks.manifest)),
    getDocumentWritingVersions: mocks.versions,
    getWritingDocumentSource: mocks.source,
    replaceWritingDocumentContent: mocks.replace,
    restoreWritingDocumentVersion: mocks.restore,
    updateDocumentStructureBinding: mocks.updateBinding,
    getDocumentEvaluationProfile: mocks.evaluationProfile,
    getDocumentEvaluation: mocks.evaluation,
    getLinkedDocumentEvaluationSummary: mocks.linkedEvaluation,
    getEvaluationProfiles: mocks.evaluationProfiles
  }
})

const document: WritingProjectDocument = {
  id: 'ppt-1',
  title: '博士毕业答辩',
  kind: 'presentation',
  status: 'active',
  sort_order: 1,
  is_primary: false,
  is_output_product: true,
  output_format: 'pptx',
  data_source_ids: [],
  print_profile: 'widescreen_16_9',
  publication_status: 'draft',
  rules_version: '结构v14',
  data_version: '文档v3',
  expected_chapters: 7,
  revision: 3,
  created_at: '2026-07-29T00:00:00Z',
  updated_at: '2026-07-29T00:00:00Z',
  structure_binding: {
    mode: 'mapped',
    source_document_id: 'thesis-1',
    source_version: 'v14',
    source_sha256: 'abc',
    status: 'aligned',
    mapped_items: 2,
    unmapped_items: [],
    changed_sections: []
  },
  stats: {
    slide_count: 2,
    main_slide_count: 1,
    appendix_slide_count: 1,
    notes_count: 2,
    preview_ready: true
  }
}

function manifest(status: 'aligned' | 'stale' = 'aligned'): PresentationManifest {
  return {
    schema: 'openclaw.paper-ppt-system-mapping',
    contract_version: 'v14.1',
    authority: {
      presentation_output: {
        document_version: '文档v3',
        structure_version: '结构v14',
        slide_count: 2,
        main_slide_count: 1,
        appendix_slide_count: 1,
        notes_count: 2,
        status: 'draft'
      }
    },
    structure_binding: {
      ...document.structure_binding!,
      status
    },
    narrative_sections: [],
    slides: [
      {
        slide: 1,
        source_slide: 1,
        title: '理论基础',
        thesis_sections: ['2.1'],
        claim: '指挥控制连接人的决心与模型算法。',
        evidence_level: 'C级',
        evidence_ids: ['MODEL-2.1'],
        notes: '第一页完整讲解稿',
        appendix: false
      },
      {
        slide: 2,
        source_slide: 2,
        title: '补充证据',
        thesis_sections: ['6.4'],
        claim: '单次运行证据受A级门禁约束。',
        evidence_level: 'B级',
        evidence_ids: ['RUN-M0'],
        notes: '第二页完整讲解稿',
        appendix: true
      }
    ]
  }
}

async function mountWorkspace(initialSlide = 1, displayMode: 'full' | 'slides' | 'ai' = 'full') {
  const wrapper = mount(PresentationWorkspace, {
    props: {
      projectId: 'project-1',
      document,
      initialSlide,
      displayMode
    },
    global: { plugins: [ElementPlus] }
  })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  mocks.manifest = manifest()
  mocks.preview.mockResolvedValue(new Blob(['pdf'], { type: 'application/pdf' }))
  mocks.versions.mockResolvedValue({
    versions: [
      {
        name: '当前版本 v3',
        size_bytes: 1024,
        created_at: '2026-07-29T00:00:00Z',
        current: true
      }
    ]
  })
  mocks.evaluationProfile.mockResolvedValue(undefined)
  mocks.evaluation.mockResolvedValue(undefined)
  mocks.linkedEvaluation.mockResolvedValue({ documents: [], defense_ready: false, maturity_level: 'L0' })
  mocks.evaluationProfiles.mockResolvedValue({ profiles: [] })
  mocks.updateBinding.mockResolvedValue(document.structure_binding)
  const proposal = {
    schema: 'openclaw.presentation-slide-proposal.v1',
    id: 'proposal-1',
    status: 'succeeded',
    agent_id: 'presentation-editor',
    slide: 1,
    title: 'AI 页面微调建议',
    summary: '后端生成的结构化建议',
    rationale: '测试建议',
    patch: {
      title: '后端建议标题',
      claim: '后端建议主张。',
      notes: '后端建议讲解稿。',
      evidence_level: 'B级',
      evidence_ids: ['RUN-M0'],
      appendix: false
    }
  }
  mocks.createSlideJob.mockResolvedValue({
    id: 'ppt-job-1',
    status: 'succeeded',
    project_id: 'project-1',
    document_id: 'ppt-1',
    slide: 1,
    agent_id: 'presentation-editor',
    instruction: '测试',
    proposal
  })
  mocks.getSlideJob.mockResolvedValue({
    id: 'ppt-job-1',
    status: 'succeeded',
    project_id: 'project-1',
    document_id: 'ppt-1',
    slide: 1,
    agent_id: 'presentation-editor',
    instruction: '测试',
    proposal
  })
  Object.defineProperty(URL, 'createObjectURL', {
    configurable: true,
    value: vi.fn(() => 'blob:preview')
  })
  Object.defineProperty(URL, 'revokeObjectURL', {
    configurable: true,
    value: vi.fn()
  })
})

describe('PresentationWorkspace', () => {
  it('supports slide-only and AI-only embedding modes for the linked workspace', async () => {
    const slidesOnly = await mountWorkspace(1, 'slides')
    expect(slidesOnly.find('.slide-viewer').exists()).toBe(true)
    expect(slidesOnly.find('.presentation-inspector').exists()).toBe(false)
    slidesOnly.unmount()

    const aiOnly = await mountWorkspace(1, 'ai')
    expect(aiOnly.find('.slide-viewer').exists()).toBe(false)
    expect(aiOnly.find('.presentation-inspector').exists()).toBe(true)
    expect(aiOnly.text()).toContain('当前页结构化编辑')
    aiOnly.unmount()
  })

  it('shows the v14 output summary, mapping and page-level claim', async () => {
    const wrapper = await mountWorkspace()

    expect(wrapper.text()).toContain('PPT · 文档v3 · 2页 · 结构v14 · 草稿')
    expect(wrapper.text()).toContain('当前PPT与源文档 v14 结构一致')
    expect(wrapper.text()).toContain('主答辩')
    expect(wrapper.text()).toContain('附录')
    expect(wrapper.text()).toContain('指挥控制连接人的决心与模型算法')
    expect(wrapper.text()).toContain('2.1')
  })

  it('emits a source-document navigation request from a thesis section link', async () => {
    const wrapper = await mountWorkspace()
    const link = wrapper.findAll('button').find(button => button.text().trim() === '2.1')
    expect(link).toBeTruthy()
    await link!.trigger('click')

    expect(wrapper.emitted('navigate-to-thesis')?.[0]?.[0]).toEqual({
      sourceDocumentId: 'thesis-1',
      section: '2.1'
    })
  })

  it('opens a requested appendix page and warns when the binding is stale', async () => {
    mocks.manifest = manifest('stale')
    const wrapper = await mountWorkspace(2)

    expect(wrapper.text()).toContain('逐页映射已过期')
    expect(wrapper.text()).toContain('单次运行证据受A级门禁约束')
    expect(wrapper.text()).toContain('补充证据')
  })

  it('keeps one PPT when the source document changes and marks optimization as pending', async () => {
    mocks.manifest = {
      ...manifest(),
      structure_binding: {
        ...document.structure_binding!,
        status: 'aligned',
        integrity_status: 'aligned',
        reference_status: 'document_updated',
        referenced_document_revision: 'v15'
      }
    }
    const wrapper = await mountWorkspace()

    expect(wrapper.text()).toContain('源文档已更新至 v15')
    expect(wrapper.text()).toContain('当前 PPT 保持为同一份最新版本')
    expect(wrapper.text()).toContain('正文更新待优化')
  })

  it('saves current slide human edits back to the presentation manifest', async () => {
    const wrapper = await mountWorkspace()
    const tabs = wrapper.findAll('.el-tabs__item')
    await tabs.find(tab => tab.text().includes('人机双写'))!.trigger('click')

    const inputs = wrapper.findAll('input')
    await inputs.find(input => input.attributes('placeholder') === '输入当前页标题')!.setValue('压缩后的理论基础')
    const textareas = wrapper.findAll('textarea')
    await textareas.find(input => input.attributes('placeholder') === '本页要向观众证明什么')!.setValue('指挥控制是任务规划系统的人机协同入口。')
    await textareas.find(input => input.attributes('placeholder') === '答辩或授课时的讲解稿')!.setValue('先说明问题，再说明方法边界。')

    const saveButton = wrapper.findAll('button').find(button => button.text().includes('保存本页'))
    await saveButton!.trigger('click')
    await flushPromises()

    expect(mocks.updateBinding).toHaveBeenCalledWith('project-1', 'ppt-1', expect.objectContaining({
      source_document_id: 'thesis-1',
      manifest: expect.objectContaining({
        slides: expect.arrayContaining([
          expect.objectContaining({
            slide: 1,
            title: '压缩后的理论基础',
            claim: '指挥控制是任务规划系统的人机协同入口。',
            notes: '先说明问题，再说明方法边界。'
          })
        ])
      })
    }))
  })

  it('requests a backend slide proposal and accepts it into the local draft', async () => {
    const wrapper = await mountWorkspace()
    await wrapper.findAll('.el-tabs__item').find(tab => tab.text().includes('人机双写'))!.trigger('click')

    const proposeButton = wrapper.findAll('button').find(button => button.text().includes('生成建议'))
    await proposeButton!.trigger('click')
    await flushPromises()

    expect(mocks.createSlideJob).toHaveBeenCalledWith('project-1', 'ppt-1', expect.objectContaining({
      slide: 1,
      agent_id: 'presentation-editor',
      draft: expect.objectContaining({
        title: '理论基础',
        claim: '指挥控制连接人的决心与模型算法。',
        evidence_ids: ['MODEL-2.1']
      })
    }))
    expect(wrapper.text()).toContain('后端生成的结构化建议')

    const acceptButton = wrapper.findAll('button').find(button => button.text().includes('接受到草稿'))
    await acceptButton!.trigger('click')
    await flushPromises()

    expect(wrapper.findAll('input').find(input => input.attributes('placeholder') === '输入当前页标题')!.element.value).toBe('后端建议标题')
  })
})
