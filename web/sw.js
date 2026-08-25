const CACHE_NAME = 'daysupply-v1';
const ASSETS = [
  '/',
  '/index.html',
  '/styles.css',
  '/app.js'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      console.log('Opened cache');
      return cache.addAll(ASSETS);
    })
  );
});

self.addEventListener('fetch', event => {
  // Only intercept requests for our own origin assets
  if (event.request.method === 'GET' && event.request.url.startsWith(self.location.origin)) {
    // If it's an API request, network first, fallback to cache
    if (event.request.url.includes('/api/')) {
      event.respondWith(
        fetch(event.request).catch(() => caches.match(event.request))
      );
      return;
    }

    // Static assets: cache first, fallback to network
    event.respondWith(
      caches.match(event.request).then(response => {
        return response || fetch(event.request);
      })
    );
  }
});
