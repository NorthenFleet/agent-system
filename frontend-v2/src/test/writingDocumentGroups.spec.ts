import { describe, expect, it } from 'vitest'
import type { WritingProjectDocument } from '@/api/writing'
import { groupWritingDocuments } from '@/utils/writingDocumentGroups'

function document(id: string, kind: WritingProjectDocument['kind'], isOutputProduct: boolean) {
  return { id, kind, is_output_product: isOutputProduct } as WritingProjectDocument
}

describe('groupWritingDocuments', () => {
  it('keeps thesis editions separate from delivery materials and internal sources', () => {
    const groups = groupWritingDocuments([
      document('edition-1', 'rich_text', true),
      document('edition-2', 'rich_text', true),
      document('edition-3', 'rich_text', true),
      document('defense-ppt', 'presentation', true),
      document('archived-candidate', 'rich_text', false)
    ])

    expect(groups.formalDocuments.map(row => row.id)).toEqual(['edition-1', 'edition-2', 'edition-3'])
    expect(groups.deliveryAssets.map(row => row.id)).toEqual(['defense-ppt'])
    expect(groups.internalDataSources.map(row => row.id)).toEqual(['archived-candidate'])
  })
})
