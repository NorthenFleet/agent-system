// Service Worker for OpenClaw Team Dashboard - 离线缓存策略
const CACHE_NAME = 'agent-os-mobile-v1';
const STATIC_CACHE = 'agent-os-static-v1';
const DYNAMIC_CACHE = 'agent-os-dynamic-v1';

// 静态资源缓存 (安装时缓存)
const STATIC_ASSETS = [
  '/',
  '/mobile',
  '/manifest.json',
  '/icons/icon-192x192.png',
  '/icons/icon-512x512.png',
];

// 安装事件 - 缓存静态资源
self.addEventListener('install', (event) => {
  console.log('[SW] Installing Service Worker...');
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => {
        console.log('[SW] Caching static assets');
        return cache.addAll(STATIC_ASSETS);
      })
      .then(() => {
        console.log('[SW] Installation complete, skipping waiting');
        self.skipWaiting();
      })
      .catch((err) => {
        console.error('[SW] Installation failed:', err);
      })
  );
});

// 激活事件 - 清理旧缓存
self.addEventListener('activate', (event) => {
  console.log('[SW] Activating Service Worker...');
  event.waitUntil(
    caches.keys()
      .then((keys) => {
        return Promise.all(
          keys
            .filter((key) => key !== STATIC_CACHE && key !== DYNAMIC_CACHE)
            .map((key) => {
              console.log('[SW] Removing old cache:', key);
              return caches.delete(key);
            })
        );
      })
      .then(() => {
        console.log('[SW] Activation complete');
        self.clients.claim();
      })
  );
});

// 获取事件 - 缓存策略
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // 跳过非 GET 请求
  if (request.method !== 'GET') {
    return;
  }

  // API 请求 - 网络优先，失败时返回缓存
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirstStrategy(request));
    return;
  }

  // WebSocket 请求 - 直接通过网络
  if (url.protocol === 'ws:' || url.protocol === 'wss:') {
    return;
  }

  // 静态资源 - 缓存优先
  if (isStaticAsset(url)) {
    event.respondWith(cacheFirstStrategy(request));
    return;
  }

  // HTML 页面 - 缓存优先
  if (request.headers.get('accept')?.includes('text/html')) {
    event.respondWith(cacheFirstStrategy(request));
    return;
  }

  // 其他请求 - 网络优先
  event.respondWith(networkFirstStrategy(request));
});

// 判断是否为静态资源
function isStaticAsset(url) {
  const staticExtensions = [
    '.js', '.css', '.png', '.jpg', '.jpeg', '.gif', '.svg', 
    '.woff', '.woff2', '.ttf', '.eot', '.ico', '.json'
  ];
  return staticExtensions.some(ext => url.pathname.endsWith(ext));
}

// 缓存优先策略 (Cache First)
async function cacheFirstStrategy(request) {
  const cachedResponse = await caches.match(request);
  if (cachedResponse) {
    console.log('[SW] Cache hit:', request.url);
    // 后台更新缓存
    fetchAndCache(request);
    return cachedResponse;
  }
  
  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      const cache = await caches.open(DYNAMIC_CACHE);
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (error) {
    console.error('[SW] Fetch failed:', error);
    // 返回离线页面
    return caches.match('/');
  }
}

// 网络优先策略 (Network First)
async function networkFirstStrategy(request) {
  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      const cache = await caches.open(DYNAMIC_CACHE);
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (error) {
    console.log('[SW] Network failed, trying cache:', request.url);
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }
    // 如果是 API 请求失败，返回错误响应
    if (request.url.includes('/api/')) {
      return new Response(
        JSON.stringify({ error: 'Offline', message: '网络连接不可用' }),
        { status: 503, headers: { 'Content-Type': 'application/json' } }
      );
    }
    return caches.match('/');
  }
}

// 后台更新缓存
async function fetchAndCache(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(DYNAMIC_CACHE);
      cache.put(request, response.clone());
    }
  } catch (error) {
    // 忽略后台更新错误
  }
}

// 消息处理
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
  if (event.data && event.data.type === 'CLEAR_CACHE') {
    caches.keys().then((keys) => {
      keys.forEach((key) => caches.delete(key));
    });
  }
});

// 后台同步 (可选)
self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-data') {
    event.waitUntil(syncData());
  }
});

async function syncData() {
  // 实现数据同步逻辑
  console.log('[SW] Syncing data...');
}

// 推送通知 (可选)
self.addEventListener('push', (event) => {
  const data = event.data?.json() || {};
  const title = data.title || '团队看板';
  const options = {
    body: data.body || '有新的更新',
    icon: '/icons/icon-192x192.png',
    badge: '/icons/icon-72x72.png',
    tag: 'dashboard-notification',
  };
  event.waitUntil(
    self.registration.showNotification(title, options)
  );
});
