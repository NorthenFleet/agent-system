import { beforeEach, expect, it, vi } from 'vitest'
import { AxiosError, AxiosHeaders, type InternalAxiosRequestConfig } from 'axios'
vi.mock('element-plus', () => ({ ElMessage: { warning: vi.fn(), error: vi.fn() } }))
import { ElMessage } from 'element-plus'
import client from '@/api/client'

beforeEach(() => {
  localStorage.clear()
  localStorage.setItem('auth_login_enabled', 'false')
  localStorage.setItem('jwt_token', 'expired')
  vi.clearAllMocks()
})

function response(config: InternalAxiosRequestConfig, data: unknown, status = 200) {
  return { config, data, status, statusText: String(status), headers: new AxiosHeaders() }
}
function unauthorized(config: InternalAxiosRequestConfig) {
  throw new AxiosError('expired', 'ERR_BAD_REQUEST', config, undefined, response(config, {}, 401))
}

it('renews once for concurrent expired reads and retries with the new token', async () => {
  let renewals = 0
  client.defaults.adapter = async config => {
    if (config.url === '/api/v2/auth/settings') return response(config, { login_enabled: false })
    if (config.url === '/api/v2/auth/development-session') {
      renewals++
      await new Promise(resolve => setTimeout(resolve, 5))
      return response(config, { access_token: 'renewed', user: { id: 1 } })
    }
    if (config.headers.Authorization !== 'Bearer renewed') return unauthorized(config)
    return response(config, { ok: true })
  }
  const results = await Promise.all([client.get('/summary'), client.get('/missions')])
  expect(results.every(r => r.data.ok)).toBe(true)
  expect(renewals).toBe(1)
  expect(localStorage.getItem('jwt_token')).toBe('renewed')
  expect(ElMessage.warning).not.toHaveBeenCalled()
})

it('never retries a failed write', async () => {
  let writes = 0
  client.defaults.adapter = async config => {
    if (config.url === '/api/v2/auth/settings') return response(config, { login_enabled: false })
    if (config.url === '/api/v2/auth/development-session') return response(config, { access_token: 'renewed' })
    writes++
    return unauthorized(config)
  }
  await expect(client.post('/missions', { objective: 'task' })).rejects.toBeDefined()
  expect(writes).toBe(1)
})

it('stops renewal attempts and deduplicates warnings when recovery is denied', async () => {
  let renewals = 0
  client.defaults.adapter = async config => {
    if (config.url === '/api/v2/auth/settings') return response(config, { login_enabled: false })
    if (config.url === '/api/v2/auth/development-session') renewals++
    return unauthorized(config)
  }
  await Promise.allSettled([client.get('/summary'), client.get('/missions')])
  await Promise.allSettled([client.get('/summary'), client.get('/missions')])
  expect(renewals).toBe(1)
  expect(ElMessage.warning).toHaveBeenCalledTimes(1)
})
