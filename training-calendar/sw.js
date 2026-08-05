/* Cache-first service worker. Bump VERSION when any precached file changes. */
const VERSION = "tc-v2";
const PRECACHE = [
  "./",
  "index.html",
  "style.css",
  "app.js",
  "data.js",
  "manifest.webmanifest",
  "fonts/fonts.css",
  "fonts/Oswald.woff2",
  "fonts/Inter.woff2",
  "fonts/IBMPlexMono-400.woff2",
  "fonts/IBMPlexMono-500.woff2",
  "icons/icon-192.png",
  "icons/icon-512.png",
  "icons/icon-512-maskable.png",
  "icons/apple-touch-icon.png",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(PRECACHE)));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  if (e.request.method !== "GET") return;
  e.respondWith(
    caches.match(e.request, { ignoreSearch: true }).then(
      (hit) =>
        hit ||
        fetch(e.request).then((res) => {
          if (res.ok && new URL(e.request.url).origin === location.origin) {
            const copy = res.clone();
            caches.open(VERSION).then((c) => c.put(e.request, copy));
          }
          return res;
        })
    )
  );
});
