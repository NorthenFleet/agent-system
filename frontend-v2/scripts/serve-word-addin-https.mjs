import { createReadStream, existsSync, statSync } from 'node:fs'
import { createServer } from 'node:https'
import { readFile } from 'node:fs/promises'
import { extname, join, normalize, resolve } from 'node:path'

const root = resolve(import.meta.dirname, '../dist')
const port = Number(process.env.WORD_ADDIN_PORT || 3443)
const keyPath = process.env.WORD_ADDIN_TLS_KEY
const certPath = process.env.WORD_ADDIN_TLS_CERT
const apiTarget = new URL(process.env.WORD_ADDIN_API_TARGET || 'http://127.0.0.1:3021')
if (!keyPath || !certPath) throw new Error('WORD_ADDIN_TLS_KEY and WORD_ADDIN_TLS_CERT are required')

const mime = {
  '.css': 'text/css; charset=utf-8', '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json', '.png': 'image/png', '.svg': 'image/svg+xml', '.xml': 'application/xml; charset=utf-8'
}

function logAccess(request, response) {
  const startedAt = Date.now()
  response.once('finish', () => {
    const userAgent = String(request.headers['user-agent'] || '-').replace(/[\r\n]/g, ' ')
    console.log(JSON.stringify({
      event: 'word_addin_http_access',
      method: request.method || 'GET',
      path: request.url || '/',
      status: response.statusCode,
      duration_ms: Date.now() - startedAt,
      user_agent: userAgent.slice(0, 240)
    }))
  })
}

function safePath(urlPath) {
  const pathname = decodeURIComponent(new URL(urlPath, 'https://localhost').pathname)
  const relative = normalize(pathname).replace(/^(\.\.(\/|\\|$))+/, '').replace(/^[/\\]+/, '')
  const candidate = join(root, relative || 'index.html')
  if (!candidate.startsWith(root)) return null
  if (existsSync(candidate) && statSync(candidate).isDirectory()) return join(candidate, 'index.html')
  return candidate
}

const server = createServer({ key: await readFile(keyPath), cert: await readFile(certPath) }, async (request, response) => {
  logAccess(request, response)
  if (request.url?.startsWith('/api/')) {
    const target = new URL(request.url, apiTarget)
    const module = target.protocol === 'https:' ? await import('node:https') : await import('node:http')
    const proxy = module.request(target, { method: request.method, headers: { ...request.headers, host: target.host } }, upstream => {
      response.writeHead(upstream.statusCode || 502, upstream.headers)
      upstream.pipe(response)
    })
    proxy.on('error', error => { response.writeHead(502); response.end(error.message) })
    request.pipe(proxy)
    return
  }
  const filePath = safePath(request.url || '/')
  if (!filePath || !existsSync(filePath) || !statSync(filePath).isFile()) {
    response.writeHead(404); response.end('Not found'); return
  }
  response.writeHead(200, { 'Content-Type': mime[extname(filePath)] || 'application/octet-stream', 'Cache-Control': 'no-store' })
  createReadStream(filePath).pipe(response)
})

server.listen(port, '0.0.0.0', () => console.log(`3021 Word Add-in HTTPS: https://0.0.0.0:${port}`))
