import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import DiagramWorkspace from '@/components/writing/DiagramWorkspace.vue'
import {
  getWritingCollaboration,
  getWritingDiagram,
  getWritingDiagramReferences,
  publishWritingDiagramToDocument,
  updateWritingDiagramDraft
} from '@/api/writing'

const graphFromJson = vi.fn()
const graphDispose = vi.fn()

vi.mock('@antv/x6', () => {
  class Plugin {}
  class Graph {
    constructor(options: { container: HTMLElement }) {
      options.container.dataset.graphReady = 'true'
    }
    use() { return this }
    on() { return this }
    bindKey() { return this }
    fromJSON(value: unknown) { graphFromJson(value) }
    toJSON() { return { cells: [] } }
    zoomToFit() {}
    centerContent() {}
    zoom() { return 1 }
    getSelectedCells() { return [] }
    dispose() { graphDispose() }
  }
  return {
    Graph,
    Selection: Plugin,
    Snapline: Plugin,
    History: Plugin,
    Clipboard: Plugin,
    Keyboard: Plugin,
    MiniMap: Plugin
  }
})

vi.mock('@dagrejs/dagre', () => ({
  graphlib: { Graph: class {} },
  layout: vi.fn()
}))

vi.mock('@/api/writing', async importOriginal => {
  const original = await importOriginal<typeof import('@/api/writing')>()
  return {
    ...original,
    getWritingCollaboration: vi.fn(),
    getWritingDiagram: vi.fn(),
    getWritingDiagramReferences: vi.fn(),
    publishWritingDiagramToDocument: vi.fn(),
    updateWritingDiagramDraft: vi.fn()
  }
})

describe('DiagramWorkspace', () => {
  beforeEach(() => {
    graphFromJson.mockClear()
    graphDispose.mockClear()
    vi.mocked(getWritingDiagram).mockResolvedValue({
      document: { id: 'diagram-1', title: '技术路线图', kind: 'diagram' } as any,
      diagram: {
        schema_version: 1,
        project_id: 'project-1',
        document_id: 'diagram-1',
        revision: 1,
        title: '技术路线图',
        diagram_type: 'research-roadmap',
        theme_id: 'academic',
        page_settings: {},
        cells: [{ id: 'problem', type: 'node', cell_revision: 1, x: 80, y: 80, label: '科学问题' }],
        content_sha256: 'checksum',
        updated_at: '2026-08-09T00:00:00Z'
      }
    })
    vi.mocked(getWritingDiagramReferences).mockResolvedValue({ references: [] })
    vi.mocked(getWritingCollaboration).mockResolvedValue({
      revision: 7,
      document_revision: 7,
      document: {
        type: 'doc',
        content: [{ type: 'paragraph', attrs: { blockId: 'anchor-block', blockRevision: 1 } }]
      }
    } as any)
    vi.mocked(publishWritingDiagramToDocument).mockResolvedValue({
      idempotent_replay: false,
      diagram_revision: 1,
      document_revision: 8,
      inserted_block_ids: ['figure', 'caption'],
      asset: { path: 'assets/figure.svg', url: '/asset', sha256: 'sha' },
      reference: {
        id: 'reference-1',
        diagram_document_id: 'diagram-1',
        diagram_revision: 1,
        target_document_id: 'document-1',
        target_kind: 'rich_text',
        export_format: 'svg',
        crop_or_viewbox: {},
        caption: '技术路线图',
        status: 'current'
      },
      document: {} as any
    })
    vi.mocked(updateWritingDiagramDraft).mockResolvedValue({
      schema_version: 1,
      project_id: 'project-1',
      document_id: 'diagram-1',
      revision: 1,
      title: '技术路线图',
      diagram_type: 'research-roadmap',
      theme_id: 'academic',
      page_settings: {},
      cells: [],
      content_sha256: 'checksum',
      updated_at: '2026-08-09T00:00:00Z'
    })
  })

  it('mounts X6 only after the loading state exposes the canvas element', async () => {
    const wrapper = mount(DiagramWorkspace, {
      props: { projectId: 'project-1', diagramId: 'diagram-1' },
      global: { plugins: [ElementPlus] }
    })
    await flushPromises()

    expect(wrapper.get('.diagram-canvas').attributes('data-graph-ready')).toBe('true')
    expect(graphFromJson).toHaveBeenCalledWith([
      expect.objectContaining({ id: 'problem', label: '科学问题' })
    ])
    wrapper.unmount()
    expect(graphDispose).toHaveBeenCalled()
  })

  it('publishes a fixed diagram revision into the current document section', async () => {
    const wrapper = mount(DiagramWorkspace, {
      props: {
        projectId: 'project-1',
        diagramId: 'diagram-1',
        documentTargetId: 'document-1',
        documentSectionId: 'section-1'
      },
      global: { plugins: [ElementPlus] }
    })
    await flushPromises()

    const button = wrapper.findAll('button').find(row => row.text().includes('插入文档'))
    expect(button).toBeTruthy()
    await button!.trigger('click')
    await flushPromises()

    expect(publishWritingDiagramToDocument).toHaveBeenCalledWith(
      'project-1',
      'diagram-1',
      expect.objectContaining({
        target_document_id: 'document-1',
        target_section_id: 'section-1',
        expected_document_revision: 7,
        expected_diagram_revision: 1,
        anchor_block_id: 'anchor-block'
      })
    )
  })
})
