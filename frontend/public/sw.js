// Offline-capable shell: cache static assets so on-device tools keep working without a connection.
const CACHE = "folio-v2";
const SHARED = "folio-share-target"; // a PDF shared to the installed app, picked up by /reader

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(["/", "/icon.svg", "/manifest.webmanifest"])));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE && k !== SHARED).map((k) => caches.delete(k)))),
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method === "POST" && url.origin === location.origin && url.pathname === "/reader/share") {
    event.respondWith(
      (async () => {
        const form = await event.request.formData();
        const file = form.getAll("file").find((f) => f && typeof f !== "string");
        if (file) {
          const cache = await caches.open(SHARED);
          await cache.put("/shared-file", new Response(file, { headers: { "x-file-name": encodeURIComponent(file.name || "shared.pdf") } }));
        }
        return Response.redirect("/reader?shared=1", 303);
      })(),
    );
    return;
  }
  // Never cache API traffic or user files.
  if (event.request.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/api") || url.pathname.startsWith("/v1")) {
    return;
  }
  if (url.pathname.startsWith("/_next/static/")) {
    event.respondWith(
      caches.match(event.request).then(
        (hit) => hit || fetch(event.request).then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(event.request, copy));
          return res;
        }),
      ),
    );
    return;
  }
  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(event.request, copy));
          return res;
        })
        .catch(() => caches.match(event.request).then((hit) => hit || caches.match("/"))),
    );
  }
});
