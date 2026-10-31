const CACHE_NAME = "wearo-shell-v33";
const APP_SHELL = [
  "/",
  "/about",
  "/experiences",
  "/for-business",
  "/for-business/womens-boutique-blouse.webp",
  "/for-business/saree-complete-look.webp",
  "/for-business/retail-traditional-girl.webp",
  "/for-business/jewellery-phone-tryon.webp",
  "/for-business/boutique-phone-tryon.webp",
  "/for-business/saree-phone-tryon.webp",
  "/for-business/retail-phone-tryon.webp",
  "/contact",
  "/app/",
  "/agent/",
  "/manifest.webmanifest",
  "/agent.webmanifest",
  "/wearo-brand.png",
  "/experiences-jewellery-catalogue.png",
  "/tryon-assets/jewellery/model-classic-gold-v2.webp",
  "/tryon-assets/jewellery/model-kundan-v2.webp",
  "/tryon-assets/jewellery/model-temple-v2.webp",
  "/tryon-assets/jewellery/model-emerald-v2.webp",
  "/tryon-assets/jewellery/model-pearl-v2.webp",
  "/tryon-assets/jewellery/product-classic-gold-v2.webp",
  "/tryon-assets/jewellery/product-kundan-v2.webp",
  "/tryon-assets/jewellery/product-temple-v2.webp",
  "/tryon-assets/jewellery/product-meenakari-v2.webp",
  "/tryon-assets/jewellery/product-silver-v2.webp",
  "/wearo-tryon-complete.wav",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request, { cache: "no-store" })
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          return response;
        })
        .catch(async () => {
          const cached = await caches.match(request);
          if (cached) return cached;
          if (url.pathname.startsWith("/agent")) return caches.match("/agent/");
          if (url.pathname.startsWith("/app") || url.pathname.startsWith("/shop")) return caches.match("/app/");
          return caches.match("/");
        }),
    );
    return;
  }

  // A previously installed production worker can still control a later local Vite session.
  // Keep source modules network-first so UI edits are never hidden by that stale worker.
  if (url.pathname.startsWith("/src/")) {
    event.respondWith(
      fetch(request, { cache: "no-store" })
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(() => caches.match(request)),
    );
    return;
  }

  event.respondWith(
    caches.match(request).then(
      (cached) =>
        cached ||
        fetch(request).then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          }
          return response;
        }),
    ),
  );
});
