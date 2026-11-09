// Minimal service worker: makes the app installable and loads the shell
// (HTML/manifest/icon) instantly on repeat visits. It never caches weather
// data — AgriMet (via the relay or /api/daily) and Open-Meteo always go to
// the network so water-use numbers are current.

const CACHE_NAME = "sw-wheat-et-shell-v4";
const SHELL_FILES = ["./index.html", "./manifest.json", "./icon.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_FILES)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  const isData =
    url.pathname.startsWith("/api/") ||
    url.pathname.includes("/data/") ||
    url.hostname.includes("usbr.gov") ||
    url.hostname.includes("workers.dev") ||
    url.hostname.includes("open-meteo.com") ||
    url.hostname.includes("tile.openstreetmap.org");
  if (isData || event.request.method !== "GET") return;   // straight to network

  // App shell: network-first so updates show up, cache as offline fallback.
  if (url.origin === self.location.origin) {
    event.respondWith(
      fetch(event.request)
        .then((resp) => {
          const copy = resp.clone();
          caches.open(CACHE_NAME).then((c) => c.put(event.request, copy)).catch(() => {});
          return resp;
        })
        .catch(() => caches.match(event.request))
    );
  }
});
