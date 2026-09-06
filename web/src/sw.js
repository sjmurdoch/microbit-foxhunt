/**
 * Offline cache for the flasher.
 *
 * A hunt happens in a field, and a board that needs reflashing at the event
 * will not have a network. Everything the page needs -- including the 1.2 MB
 * MicroPython image -- is cached on first visit.
 *
 * The cache name carries the build stamp, so a redeploy invalidates it. Getting
 * that wrong would pin organisers on a stale flasher indefinitely, which is
 * exactly the class of silent failure this project exists to avoid.
 */
const CACHE = "foxhunt-__STAMP__";

self.addEventListener("install", (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE).then((cache) =>
      // Best effort: a miss here must not stop the worker installing, or one
      // renamed asset makes the whole page uninstallable.
      Promise.allSettled([
        cache.add("./"),
        cache.add("./manifest.json"),
        cache.add("./app.css"),
      ]),
    ),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Cache first: these assets are immutable for a given build, and being
  // offline is the expected case rather than the exception.
  event.respondWith(
    caches.match(request).then((hit) => {
      if (hit) return hit;
      return fetch(request).then((response) => {
        if (response && response.ok) {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(request, copy));
        }
        return response;
      });
    }),
  );
});
