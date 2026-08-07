import { describe, expect, it } from 'vitest'
import { documentVersionLabel, richTextDeliveryState, richTextOutputSummary } from '@/utils/documentDelivery'

describe('document delivery version display', () => {
  it('keeps the content release separate from the structured edit revision', () => {
    expect(documentVersionLabel({ revision: 31, data_version: 'v30' })).toBe('v30')
  })

  it('distinguishes a newer manuscript from the frozen Word artifact', () => {
    const documentItem = {
      kind: 'rich_text',
      revision: 27,
      data_version: 'v27',
      stats: { chapter_count: 7 },
      metadata: { artifact_version: 25, delivery_state: 'stale' }
    }

    expect(richTextDeliveryState(documentItem)).toBe('stale')
    expect(richTextOutputSummary(documentItem, '草稿')).toBe(
      'Word · v25 · 正文v27 · 7章 · 草稿'
    )
  })

  it('keeps the compact label when manuscript and artifact are aligned', () => {
    const documentItem = {
      kind: 'rich_text',
      revision: 27,
      data_version: 'v27',
      stats: { chapter_count: 7 },
      metadata: { artifact_version: 27, delivery_state: 'aligned' }
    }

    expect(richTextDeliveryState(documentItem)).toBe('aligned')
    expect(richTextOutputSummary(documentItem, '草稿')).toBe(
      'Word · v27 · 7章 · 草稿'
    )
  })

  it('falls back to the document revision when delivery metadata is absent', () => {
    const documentItem = {
      kind: 'rich_text',
      revision: 3,
      stats: { chapter_count: 2 }
    }

    expect(richTextDeliveryState(documentItem)).toBe('')
    expect(richTextOutputSummary(documentItem, '核校')).toBe(
      'Word · v3 · 2章 · 核校'
    )
  })
})
