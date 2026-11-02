import { describe, expect, it } from 'vitest'
import { artifactDownloadError } from '@/utils/artifactDownload'

describe('artifact download errors', () => {
  it('decodes JSON returned as a download blob', async () => {
    expect(await artifactDownloadError({ response: { status: 409, data: new Blob([JSON.stringify({ detail: '文件已变化，与该任务登记的版本不一致' })]) } })).toBe('文件已变化，与该任务登记的版本不一致')
  })
  it('handles malformed and absent responses', async () => {
    expect(await artifactDownloadError({ response: { status: 500, data: new Blob(['<html>failed</html>']) } })).toContain('暂不可下载')
    expect(await artifactDownloadError(new Error('network'))).toContain('网络')
  })
  it('uses clear permission errors and ignores non-string detail', async () => {
    expect(await artifactDownloadError({ response: { status: 403 } })).toContain('权限')
    expect(await artifactDownloadError({ response: { status: 409, data: { detail: [{}] } } })).toContain('暂不可下载')
  })
})
