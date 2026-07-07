// Legacy service worker cleanup for OpenClaw V2.
// The old cache-first worker can keep serving stale SPA bundles after deploys.
// V2 is network-first/live, so this worker clears legacy caches and unregisters.

self.addEventListener('install', (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.map((key) => caches.delete(key)));
    const clients = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const client of clients) {
      client.postMessage({ type: 'OPENCLAW_SW_CLEARED' });
    }
    await self.registration.unregister();
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', () => {
  // Intentionally do not intercept requests.
});
