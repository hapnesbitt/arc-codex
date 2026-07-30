// ⚠️ BUILD-TIME SED ANCHOR — DO NOT "clean up", pre-stamp, or rename.
// Dockerfile.frontend's runner stage rewrites the literal 'arc-v1' below to
// 'arc-<SW_CACHE_STAMP>' at build time (SW_CACHE_STAMP comes from
// `git describe --always --dirty` via arc.sh cmd_build). If this literal
// is renamed, split across lines, or already stamped, the sed becomes a
// no-op and the build will FAIL LOUDLY with a clear error — the guard is
// there specifically because a silent no-op reintroduces the propagation
// bug we spent real time diagnosing (users stuck on the pre-fix bundle
// with no server-side signal). See memory sw-cache-name-build-stamp.md.
const CACHE_NAME = 'arc-v1';

// Static assets to precache on install.
//
// `/` is a deliberate offline fallback (not an inherited default): PWA users
// with no network get a snapshot of the feed as it stood at deploy time
// instead of a failure page. It is stale by definition and the network-first
// fetch strategy below always prefers the live feed when online, so the
// staleness only manifests when the user is truly offline — an acceptable
// tradeoff for a news site where "feed from three days ago" beats "blank
// error." Revisit only if we build a dedicated /offline surface.
const PRECACHE_URLS = [
  '/',
  '/manifest.json',
  '/icons/icon-192x192.png',
  '/icons/icon-512x512.png',
  '/icons/apple-touch-icon.png',
];

// Install — precache shell assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS))
  );
  self.skipWaiting();
});

// Activate — delete old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

// Fetch strategy:
//   - API calls (/api/*): network-only, never cache
//   - Next.js static chunks (_next/static/*): cache-first (content-hashed)
//   - Everything else: network-first with cache fallback
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET and cross-origin requests
  if (request.method !== 'GET' || url.origin !== self.location.origin) return;

  // API: always network, never cache
  if (url.pathname.startsWith('/api/')) return;

  // Next.js static assets: cache-first (they are content-hashed)
  if (url.pathname.startsWith('/_next/static/')) {
    event.respondWith(
      caches.match(request).then(
        (cached) =>
          cached ||
          fetch(request).then((response) => {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
            return response;
          })
      )
    );
    return;
  }

  // Pages and other assets: network-first, fall back to cache
  event.respondWith(
    fetch(request)
      .then((response) => {
        const clone = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
        return response;
      })
      .catch(() => caches.match(request))
  );
});
