// Version bump karo (v2, v3, v4...) sirf tab jab STATIC_ASSETS list badle -
// baaki HTML/data updates ab automatically pick ho jayenge, cache-bump ki zaroorat nahi.
const CACHE_NAME = 'rtg-app-v2';

// Sirf woh files jo shayad hi kabhi badlein - inhe cache-first rakha hai (fast load)
const STATIC_ASSETS = [
  './manifest.json',
  './icon-192.png',
  './icon-512.png'
];

self.addEventListener('install', event => {
  self.skipWaiting(); // naya SW turant activate ho, purane tabs band hone ka wait na kare
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS))
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(cacheNames => Promise.all(
        cacheNames.filter(name => name !== CACHE_NAME).map(name => caches.delete(name))
      ))
      .then(() => self.clients.claim()) // is naye SW ko turant sabhi open tabs par control do
  );
});

self.addEventListener('fetch', event => {
  const req = event.request;

  // App shell (index.html) aur live data (data.csv) => NETWORK-FIRST
  // Matlab: online hote hi hamesha LATEST version/data milega.
  // Offline hone par hi purane cached version par fallback hoga.
  if (req.mode === 'navigate' || req.url.includes('index.html') || req.url.includes('data.csv')) {
    event.respondWith(
      fetch(req)
        .then(res => {
          const resClone = res.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(req, resClone));
          return res;
        })
        .catch(() => caches.match(req))
    );
    return;
  }

  // Baaki static assets (icons, manifest, fonts) => CACHE-FIRST (jaldi load ho)
  event.respondWith(
    caches.match(req).then(cached => cached || fetch(req))
  );
});
