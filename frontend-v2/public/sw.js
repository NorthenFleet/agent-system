/* Service Worker — 渐进式 Web 应用离线缓存 */
const CACHE_NAME = 'kanban-v2-v1'
const STATIC_ASSETS = [
  '/',
  '/index.html',
]

// 安装：缓存静态资源
self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  )
  // 立即激活新版本
  self.skipWaiting()
})

// 激活：清理旧缓存
self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((names) =>
      Promise.all(names.filter(n => n !== CACHE_NAME).map(n => caches.delete(n)))
    )
  )
  // 立即接管所有页面
  self.clients.claim()
})

// 请求：网络优先，回退到缓存
self.addEventListener('fetch', (e) => {
  // 忽略非 GET 请求
  if (e.request.method !== 'GET') return

  e.respondWith(
    fetch(e.request)
      .then((response) => {
        // 缓存成功的响应
        if (response && response.ok) {
          const clone = response.clone()
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(e.request, clone)
          })
        }
        return response
      })
      .catch(() => caches.match(e.request))
  )
})
