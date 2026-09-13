import { describe, expect, it, vi } from 'vitest'
import { ApiClient, buildSelectionJob, normalizeOrigin, randomId, resolveCandidate, sha256 } from '../../word-addin/core'

describe('Word Add-in candidate core', () => {
  it('builds a review-only selection job', () => {
    const payload = buildSelectionJob(
      { text: '原段落', sha256: 'a'.repeat(64), style: '正文', documentFingerprint: 'b'.repeat(64) },
      '压缩表述',
      45,
      'block-1'
    )
    expect(payload.scope).toBe('selection')
    expect(payload.risk_policy).toMatchObject({ allow_auto_draft: false, require_human_review: true })
    expect(payload.selection).toMatchObject({ text: '原段落', text_sha256: 'a'.repeat(64), base_revision: 45, block_id: 'block-1' })
  })

  it('resolves the matching proposal and ChangeSet', () => {
    expect(resolveCandidate(
      { id: 'job-1', proposals: [{ id: 'proposal-1', job_id: 'job-1' }] },
      { change_sets: [{ id: 'cs-1', proposal_id: 'proposal-1', base_revision: 45 }] },
      44
    )).toMatchObject({ jobId: 'job-1', proposalId: 'proposal-1', changeSetId: 'cs-1', baseRevision: 45 })
  })

  it('uses bearer auth and candidate context route', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ revision: 45 }) })
    vi.stubGlobal('fetch', fetchMock)
    const client = new ApiClient({ apiOrigin: 'https://host/', projectId: 'p 1', documentId: 'd/1', token: 'jwt' })
    await expect(client.context()).resolves.toEqual({ revision: 45 })
    expect(fetchMock).toHaveBeenCalledWith(
      'https://host/api/v3/writing/projects/p%201/documents/d%2F1/word-addin/context',
      expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer jwt' }) })
    )
  })

  it('normalizes origins and hashes exact paragraph text', async () => {
    expect(normalizeOrigin(' https://host/// ')).toBe('https://host')
    expect(randomId('word-')).toMatch(/^word-[0-9a-f]{32}$/)
    await expect(sha256('abc')).resolves.toBe('ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
  })
})
