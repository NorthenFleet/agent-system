import { Mark, mergeAttributes, Node } from '@tiptap/core'
import Image from '@tiptap/extension-image'
import katex from 'katex'
import 'katex/dist/katex.min.css'

export function isProjectAssetPath(src: string) {
  const value = src.trim()
  return Boolean(value && !/^https?:\/\//i.test(value) && !/^blob:|^data:/i.test(value) && !value.startsWith('/'))
}

function dimensionStyle(attributes: Record<string, unknown>) {
  const width = String(attributes.width || '').trim()
  const height = String(attributes.height || '').trim()
  return [width ? `width:${width}` : '', height ? `height:${height}` : ''].filter(Boolean).join(';')
}

export const AssetImage = Image.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      width: { default: null },
      height: { default: null },
      sourceAttributes: { default: '' }
    }
  },
  renderHTML({ HTMLAttributes }) {
    const src = String(HTMLAttributes.src || '')
    const style = dimensionStyle(HTMLAttributes)
    const attributes = { ...HTMLAttributes }
    if (isProjectAssetPath(src)) delete attributes.src
    return ['img', {
      ...attributes,
      ...(style ? { style } : {}),
      ...(isProjectAssetPath(src) ? { 'data-asset-src': src } : {})
    }]
  }
})

function mathAttributes() {
  return {
    latex: { default: '' },
    suffix: { default: '' },
    sourceMarkdown: { default: '' },
    sourceFormat: { default: '' },
    artifactKind: { default: null },
    artifactLabel: { default: null },
    artifactTitle: { default: null },
    blockId: { default: null },
    blockRevision: { default: 1 }
  }
}

function renderMathElement(element: HTMLElement, latex: string, displayMode: boolean) {
  element.dataset.latex = latex
  element.dataset.renderedLatex = latex
  if (!latex.trim()) {
    element.textContent = '公式内容为空'
    element.classList.add('math-invalid')
    return
  }
  try {
    katex.render(latex, element, {
      displayMode,
      output: 'htmlAndMathml',
      throwOnError: true,
      strict: 'warn',
      trust: false
    })
    element.classList.remove('math-invalid')
  } catch {
    element.textContent = latex
    element.classList.add('math-invalid')
  }
}

function mathNodeView(displayMode: boolean) {
  return ({ node }: { node: any }) => {
    const element = document.createElement(displayMode ? 'div' : 'span')
    element.className = `math-node ${displayMode ? 'math-block' : 'math-inline'}`
    if (displayMode) {
      element.dataset.mathBlock = ''
      element.dataset.mathSuffix = String(node.attrs.suffix || '')
    } else {
      element.dataset.mathInline = ''
    }
    renderMathElement(element, String(node.attrs.latex || ''), displayMode)
    return {
      dom: element,
      update(updatedNode: any) {
        if (updatedNode.type !== node.type) return false
        if (displayMode) element.dataset.mathSuffix = String(updatedNode.attrs.suffix || '')
        renderMathElement(element, String(updatedNode.attrs.latex || ''), displayMode)
        node = updatedNode
        return true
      }
    }
  }
}

export const MathInline = Node.create({
  name: 'mathInline',
  group: 'inline',
  inline: true,
  atom: true,
  selectable: true,
  addAttributes: mathAttributes,
  parseHTML() { return [{ tag: 'span[data-math-inline]' }] },
  addNodeView() { return mathNodeView(false) },
  renderHTML({ node, HTMLAttributes }) {
    return ['span', mergeAttributes(HTMLAttributes, {
      'data-math-inline': '',
      'data-latex': String(node.attrs.latex || ''),
      class: 'math-node math-inline'
    })]
  }
})

export const MathBlock = Node.create({
  name: 'mathBlock',
  group: 'block',
  atom: true,
  selectable: true,
  addAttributes: mathAttributes,
  parseHTML() { return [{ tag: 'div[data-math-block]' }] },
  addNodeView() { return mathNodeView(true) },
  renderHTML({ node, HTMLAttributes }) {
    return ['div', mergeAttributes(HTMLAttributes, {
      'data-math-block': '',
      'data-latex': String(node.attrs.latex || ''),
      'data-math-suffix': String(node.attrs.suffix || ''),
      class: 'math-node math-block'
    })]
  }
})

function semanticMark(name: string, tag: string) {
  return Mark.create({
    name,
    parseHTML() { return [{ tag }] },
    renderHTML({ HTMLAttributes }) { return [tag, HTMLAttributes, 0] }
  })
}

export const Superscript = semanticMark('superscript', 'sup')
export const Subscript = semanticMark('subscript', 'sub')
export const Citation = Mark.create({
  name: 'citation',
  inclusive: false,
  parseHTML() {
    return [
      { tag: 'sup[data-document-citation]' },
      { tag: 'sup.document-citation' }
    ]
  },
  renderHTML({ HTMLAttributes }) {
    return ['sup', mergeAttributes(HTMLAttributes, {
      'data-document-citation': '',
      class: 'document-citation'
    }), 0]
  }
})

export function renderMathNodes(root?: ParentNode | null) {
  if (!root) return
  root.querySelectorAll<HTMLElement>('.math-node[data-latex]').forEach(element => {
    const latex = element.dataset.latex || ''
    if (element.dataset.renderedLatex === latex) return
    element.dataset.renderedLatex = latex
    renderMathElement(element, latex, element.hasAttribute('data-math-block'))
  })
}
