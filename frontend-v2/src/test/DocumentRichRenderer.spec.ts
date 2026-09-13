import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import DocumentRichRenderer from '@/components/writing/DocumentRichRenderer.vue'
import { getDocumentWritingAsset } from '@/api/writing'

vi.mock('@/api/writing', async importOriginal => {
  const original = await importOriginal<typeof import('@/api/writing')>()
  return { ...original, getDocumentWritingAsset: vi.fn() }
})

describe('DocumentRichRenderer', () => {
  beforeEach(() => {
    vi.mocked(getDocumentWritingAsset).mockResolvedValue(new Blob(['image'], { type: 'image/png' }))
    Object.defineProperty(URL, 'createObjectURL', { value: vi.fn(() => 'blob:rich-renderer'), configurable: true })
    Object.defineProperty(URL, 'revokeObjectURL', { value: vi.fn(), configurable: true })
  })

  afterEach(() => vi.restoreAllMocks())

  it('renders math, image dimensions, merged tables and Unicode without data loss', async () => {
    const wrapper = mount(DocumentRichRenderer, {
      props: {
        projectId: 'project-1',
        documentId: 'document-1',
        content: {
          type: 'doc',
          content: [
            { type: 'paragraph', content: [
              { type: 'text', text: '中文 αβγ 𠮷 x' },
              { type: 'text', text: '2', marks: [{ type: 'superscript' }] },
              { type: 'mathInline', attrs: { latex: 'x_i^2' } },
              { type: 'text', text: '[1-3]', marks: [{ type: 'citation' }] }
            ] },
            { type: 'mathBlock', attrs: { latex: '\\Phi_A=\\sum_i u_i', suffix: '（5.14）' } },
            { type: 'image', attrs: { src: 'assets/diagram.png', alt: '体系结构', width: '145mm', height: '80mm' } },
            { type: 'table', content: [
              { type: 'tableRow', content: [
                { type: 'tableCell', attrs: { colspan: 2, rowspan: 1, colwidth: [200, 200] }, content: [{ type: 'paragraph', content: [{ type: 'text', text: '合并单元格' }] }] },
                { type: 'tableCell', attrs: { colspan: 1, rowspan: 2 }, content: [{ type: 'paragraph', content: [{ type: 'mathInline', attrs: { latex: 'a+b' } }] }] }
              ] },
              { type: 'tableRow', content: [
                { type: 'tableCell', attrs: { colspan: 1, rowspan: 1 }, content: [{ type: 'paragraph', content: [{ type: 'text', text: '第二行' }] }] },
                { type: 'tableCell', attrs: { colspan: 1, rowspan: 1 }, content: [{ type: 'paragraph', content: [{ type: 'text', text: '完整字符✓' }] }] }
              ] }
            ] }
          ]
        }
      }
    })
    await flushPromises()

    expect(wrapper.text()).toContain('中文 αβγ 𠮷 x')
    expect(wrapper.find('sup').text()).toBe('2')
    expect(wrapper.get('sup.document-citation').text()).toBe('[1-3]')
    expect(wrapper.findAll('.katex').length).toBeGreaterThanOrEqual(3)
    expect(wrapper.get('.math-block').attributes('data-math-suffix')).toBe('（5.14）')
    const image = wrapper.get('img[data-asset-src="assets/diagram.png"]')
    expect(image.attributes('src')).toBe('blob:rich-renderer')
    expect(image.attributes('style')).toContain('width: 145mm')
    expect(image.attributes('style')).toContain('height: 80mm')
    expect(wrapper.get('td[colspan="2"]').text()).toContain('合并单元格')
    expect(wrapper.get('td[rowspan="2"]').exists()).toBe(true)
    wrapper.unmount()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:rich-renderer')
  })

  it('keeps invalid and empty LaTeX readable', async () => {
    const wrapper = mount(DocumentRichRenderer, {
      props: {
        projectId: 'project-1',
        documentId: 'document-1',
        content: { type: 'doc', content: [
          { type: 'mathBlock', attrs: { latex: '\\notacommand{' } },
          { type: 'mathBlock', attrs: { latex: '' } }
        ] }
      }
    })
    await flushPromises()

    const invalid = wrapper.findAll('.math-invalid')
    expect(invalid).toHaveLength(2)
    expect(invalid[0].text()).toContain('\\notacommand{')
    expect(invalid[1].text()).toContain('公式内容为空')
    wrapper.unmount()
  })
})
