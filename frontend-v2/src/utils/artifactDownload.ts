export async function artifactDownloadError(error: unknown): Promise<string> {
  const response = (error as { response?: { status?: number; data?: unknown } })?.response
  if (response?.status === 401) return '会话已失效，请刷新页面后重试'
  if (response?.status === 403) return '没有该产物的访问权限'
  let data = response?.data
  if (data instanceof Blob) {
    try { data = JSON.parse(await data.text()) } catch { data = undefined }
  }
  const detail = (data as { detail?: unknown })?.detail
  if (typeof detail === 'string' && detail.trim()) return detail.slice(0, 500)
  return response ? '文件暂不可下载，请稍后重试或核对交付记录' : '网络连接失败或请求超时，请重试下载'
}
