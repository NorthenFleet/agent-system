export type RichTextDeliveryState = 'aligned' | 'stale' | 'missing' | ''

interface RichTextDeliveryLike {
  kind: string
  revision: number
  data_version?: string
  metadata?: Record<string, any>
  stats?: { chapter_count?: number }
}

function versionLabel(value: unknown, fallback = '') {
  const text = String(value ?? '').trim()
  if (!text) return fallback
  if (/^v\d+/i.test(text) || !/^\d+$/.test(text)) return text
  return `v${text}`
}

export function documentVersionLabel(
  documentItem: Pick<RichTextDeliveryLike, 'revision' | 'data_version'>
) {
  return versionLabel(documentItem.data_version, `v${documentItem.revision}`)
}

export function richTextDeliveryState(documentItem: RichTextDeliveryLike): RichTextDeliveryState {
  if (documentItem.kind !== 'rich_text') return ''
  const metadata = documentItem.metadata || {}
  const explicit = String(metadata.delivery_state || '').trim().toLowerCase()
  if (['aligned', 'stale', 'missing'].includes(explicit)) return explicit as RichTextDeliveryState
  const layoutStatus = String(metadata.layout_binding?.status || '').trim().toLowerCase()
  if (['aligned', 'stale', 'missing'].includes(layoutStatus)) return layoutStatus as RichTextDeliveryState
  return ''
}

export function richTextOutputSummary(
  documentItem: RichTextDeliveryLike,
  publicationText: string
) {
  const manuscriptVersion = documentVersionLabel(documentItem)
  const artifactVersion = versionLabel(
    documentItem.metadata?.artifact_version,
    manuscriptVersion
  )
  const chapterCount = Number(documentItem.stats?.chapter_count || 0)
  const versionPart = artifactVersion !== manuscriptVersion
    ? `${artifactVersion} · 正文${manuscriptVersion}`
    : manuscriptVersion
  return `Word · ${versionPart} · ${chapterCount}章 · ${publicationText}`
}
