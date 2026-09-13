import type { WritingProjectDocument } from '@/api/writing'

export function groupWritingDocuments(documents: WritingProjectDocument[]) {
  return {
    formalDocuments: documents.filter(row => row.is_output_product && row.kind === 'rich_text'),
    deliveryAssets: documents.filter(row => row.is_output_product && row.kind !== 'rich_text'),
    internalDataSources: documents.filter(row => !row.is_output_product)
  }
}
