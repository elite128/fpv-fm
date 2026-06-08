const CACHE_NAME = "fpv-freq-v1";
const ASSETS = [
  "/",
  "/display",
  "/static/style.css",
  "/static/app.js",
  "/static/display.js",
  "/static/manifest.json",
  "/static/icon.svg"
];

// Install Event - Pre-cache the App Shell
self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS);
    }).then(() => self.skipWaiting())
  );
});

// Activate Event - Clean up old caches
self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch Event - Serve from Cache or Fetch from Network
self.addEventListener("fetch", (e) => {
  // Do not intercept WebSocket connections or REST API calls (REST is `/api/*`)
  const url = new URL(e.request.url);
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/ws")) {
    return;
  }

  e.respondWith(
    caches.match(e.request).then((cachedResponse) => {
      if (cachedResponse) {
        // Fetch a fresh copy in the background to keep the cache updated (stale-while-revalidate)
        fetch(e.request).then((networkResponse) => {
          if (networkResponse.status === 200) {
            caches.open(CACHE_NAME).then((cache) => cache.put(e.request, networkResponse));
          }
        }).catch(() => {/* Ignore network errors when offline */});
        
        return cachedResponse;
      }
      return fetch(e.request);
    })
  );
});
