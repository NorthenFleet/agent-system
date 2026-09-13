<template>
  <EditorContent :editor="editor" class="document-rich-renderer" />
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, watch } from 'vue'
import { Node, type JSONContent } from '@tiptap/core'
import { TableKit } from '@tiptap/extension-table'
import StarterKit from '@tiptap/starter-kit'
import { EditorContent, useEditor } from '@tiptap/vue-3'
import { getDocumentWritingAsset } from '@/api/writing'
import {
  AssetImage, Citation, MathBlock, MathInline, Subscript, Superscript,
  isProjectAssetPath, renderMathNodes
} from './documentRichExtensions'

const props = defineProps<{
  projectId: string
  documentId: string
  content: JSONContent
}>()

const objectUrls: string[] = []

const RendererAssetImage = AssetImage.extend({
  addNodeView() {
    return ({ node }) => {
      const image = document.createElement('img')
      const apply = (currentNode: typeof node) => {
        const attrs = currentNode.attrs || {}
        const source = String(attrs.src || '')
        image.alt = String(attrs.alt || '')
        image.title = String(attrs.title || '')
        image.style.width = String(attrs.width || '')
        image.style.height = String(attrs.height || '')
        image.style.maxWidth = '100%'
        if (!isProjectAssetPath(source)) {
          image.src = source
          return
        }
        image.dataset.assetSrc = source
        void getDocumentWritingAsset(props.projectId, props.documentId, source).then(blob => {
          const url = URL.createObjectURL(blob)
          objectUrls.push(url)
          image.src = url
          image.dataset.assetLoaded = '1'
          image.classList.remove('asset-missing')
        }).catch(() => {
          image.classList.add('asset-missing')
          image.alt ||= `缺失图片：${source}`
        })
      }
      apply(node)
      return {
        dom: image,
        update(updatedNode) {
          if (updatedNode.type !== node.type) return false
          apply(updatedNode)
          node = updatedNode
          return true
        }
      }
    }
  }
})

const RawMarkdown = Node.create({
  name: 'rawMarkdown', group: 'block', atom: true,
  addAttributes() { return { markdown: { default: '' }, blockId: { default: null }, blockRevision: { default: 1 } } },
  parseHTML() { return [{ tag: 'pre[data-raw-markdown]' }] },
  renderHTML({ node }) { return ['pre', { 'data-raw-markdown': '', class: 'raw-markdown-block' }, ['code', {}, String(node.attrs.markdown || '')]] }
})

const editor = useEditor({
  extensions: [
    StarterKit,
    RendererAssetImage.configure({ inline: false, allowBase64: false }),
    MathInline,
    MathBlock,
    Citation,
    Superscript,
    Subscript,
    TableKit,
    RawMarkdown
  ],
  content: props.content,
  editable: false,
  editorProps: { attributes: { 'aria-label': '结构化文档阅读器' } },
  onCreate: () => { void hydrate() },
  onUpdate: () => { void hydrate() }
})

function assetPaths(node: JSONContent): string[] {
  const values: string[] = []
  if (node.type === 'image') {
    const src = String(node.attrs?.src || '')
    if (isProjectAssetPath(src)) values.push(src)
  }
  for (const child of node.content || []) values.push(...assetPaths(child))
  return values
}

async function hydrate() {
  await nextTick()
  const root = editor.value?.view.dom
  if (!root) return
  renderMathNodes(root)
  const paths = Array.from(new Set(assetPaths(editor.value?.getJSON() || props.content)))
  await Promise.all(paths.map(async path => {
    const image = Array.from(root.querySelectorAll<HTMLImageElement>('img[data-asset-src]'))
      .find(item => item.dataset.assetSrc === path)
    if (!image || image.dataset.assetLoaded === '1') return
    try {
      const blob = await getDocumentWritingAsset(props.projectId, props.documentId, path)
      const url = URL.createObjectURL(blob)
      objectUrls.push(url)
      image.src = url
      image.dataset.assetLoaded = '1'
      image.classList.remove('asset-missing')
    } catch {
      image.classList.add('asset-missing')
      image.alt ||= `缺失图片：${path}`
    }
  }))
}

watch(() => props.content, content => {
  editor.value?.commands.setContent(content, { emitUpdate: false, errorOnInvalidContent: true })
  void hydrate()
}, { deep: true })

watch(editor, value => { if (value) void hydrate() }, { immediate: true })
onBeforeUnmount(() => objectUrls.forEach(url => URL.revokeObjectURL(url)))
</script>

<style scoped>
.document-rich-renderer :deep(.tiptap) { color: #23272d; outline: none; font-family: "Times New Roman", "Noto Serif SC", "Songti SC", SimSun, "STIX Two Math", "Apple Symbols", serif; font-size: 15px; line-height: 1.95; }
.document-rich-renderer :deep(h1) { margin: 1.8em 0 .9em; text-align: center; }
.document-rich-renderer :deep(h2) { margin: 1.6em 0 .8em; }
.document-rich-renderer :deep(h3) { margin: 1.4em 0 .65em; }
.document-rich-renderer :deep(p) { margin: .8em 0; }
.document-rich-renderer :deep(.tiptap > p) { text-indent: 2em; }
.document-rich-renderer :deep(.tiptap > p.artifact-figure-caption), .document-rich-renderer :deep(.tiptap > p.artifact-table-caption) { text-indent: 0; }
.document-rich-renderer :deep(.document-citation) { font-size: .72em; line-height: 0; vertical-align: super; white-space: nowrap; }
.document-rich-renderer :deep(img) { display: block; max-width: 100%; height: auto; margin: 1.4em auto; }
.document-rich-renderer :deep(img.asset-missing) { min-height: 120px; border: 1px dashed #ef4444; background: repeating-linear-gradient(45deg, #fff, #fff 10px, #fee2e2 10px, #fee2e2 20px); }
.document-rich-renderer :deep(table) { display: table; width: 100%; margin: 1.25em auto; border-collapse: collapse; }
.document-rich-renderer :deep(th), .document-rich-renderer :deep(td) { padding: 7px 9px; border: 1px solid #aeb5bf; vertical-align: middle; text-align: center !important; }
.document-rich-renderer :deep(th p), .document-rich-renderer :deep(td p) { text-align: center !important; text-indent: 0; }
.document-rich-renderer :deep(th) { background: #f2f4f7; font-weight: 600; }
.document-rich-renderer :deep(.math-inline) { display: inline-block; vertical-align: middle; }
.document-rich-renderer :deep(.math-block) { position: relative; min-height: 48px; margin: 1.25em 0; padding: 10px 64px 10px 12px; overflow-x: auto; text-align: center; }
.document-rich-renderer :deep(.math-block[data-math-suffix]:not([data-math-suffix=""])::after) { position: absolute; right: 12px; top: 50%; content: attr(data-math-suffix); transform: translateY(-50%); }
.document-rich-renderer :deep(.math-invalid) { color: #b42318; font-family: ui-monospace, monospace; white-space: pre-wrap; }
.document-rich-renderer :deep(.raw-markdown-block) { overflow-x: auto; white-space: pre-wrap; }
@media (max-width: 900px) { .document-rich-renderer :deep(.tableWrapper) { overflow-x: auto; } }
</style>
