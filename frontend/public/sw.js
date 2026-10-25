// Deliberately cache only the static offline notice and icons, never audio,
// API responses, the authenticated application HTML or login redirects.
const CACHE = "playpod-offline-v4";
self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(CACHE);
      for (const path of [
        "/offline.html",
        "/icons/icon-192.png",
        "/icons/icon-512.png",
      ]) {
        try {
          const response = await fetch(path, { cache: "reload" });
          if (
            !response.ok ||
            response.redirected ||
            new URL(response.url).origin !== self.location.origin
          )
            continue;
          if (
            path === "/offline.html" &&
            !(await response.clone().text()).includes("data-playpod-offline")
          )
            continue;
          await cache.put(path, response);
        } catch {}
      }
    })(),
  );
  // No skipWaiting or automatic page reload during playback.
});
self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      for (const key of await caches.keys())
        if (key.startsWith("playpod-offline-") && key !== CACHE)
          await caches.delete(key);
      await self.clients.claim();
    })(),
  );
});
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/icons/") && event.request.method === "GET") {
    event.respondWith(
      fetch(event.request).catch(() => caches.match(event.request)),
    );
    return;
  }
  if (event.request.mode !== "navigate" || url.pathname !== "/") return;
  event.respondWith(
    fetch(event.request).catch(
      async () =>
        (await caches.match("/offline.html")) ||
        new Response("PlayPod offline.", {
          status: 503,
          headers: { "Content-Type": "text/plain;charset=utf-8" },
        }),
    ),
  );
});
