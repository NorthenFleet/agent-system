import { flushPromises, mount } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import DocumentRichRenderer from '@/components/writing/DocumentRichRenderer.vue'

const workspaceSource = readFileSync(
  resolve(process.cwd(), 'src/views/WritingWorkspace.vue'),
  'utf8'
)

function functionSource(name: string, nextName: string) {
  const start = workspaceSource.indexOf(`function ${name}`)
  const end = workspaceSource.indexOf(`function ${nextName}`, start + 1)
  return workspaceSource.slice(start, end)
}

describe('document management phase 0 regressions', () => {
  it.fails('opens a diagram card through an explicit diagram document path', () => {
    const source = functionSource('selectDocument', 'handleLinkedWorkspaceChanged')

    expect(source).toMatch(/nextDocument\?\.kind === ['"]diagram['"]/)
  })

  it.fails('labels diagram statistics with authoritative diagram counts instead of pages', () => {
    const source = functionSource('documentStatLabel', 'documentOutputSummary')

    expect(source).toMatch(/documentItem\.kind === ['"]diagram['"]/)
    expect(source).toContain('node_count')
    expect(source).toContain('edge_count')
  })

  it.fails('keeps internal HTML comments out of the rendered document', async () => {
    const wrapper = mount(DocumentRichRenderer, {
      props: {
        projectId: 'project-1',
        documentId: 'document-1',
        content: {
          type: 'doc',
          content: [{
            type: 'rawMarkdown',
            attrs: {
              markdown: '<!-- v34:chapter-internal-marker -->',
              blockId: 'internal-comment',
              blockRevision: 1
            }
          }]
        }
      }
    })

    try {
      await flushPromises()
      expect(wrapper.text()).not.toContain('v34:chapter-internal-marker')
      expect(wrapper.find('.raw-markdown-block').exists()).toBe(false)
    } finally {
      wrapper.unmount()
    }
  })
})
