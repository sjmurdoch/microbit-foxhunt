/**
 * Offline cache for the flasher.
 *
 * A hunt happens in a field, and a board that needs reflashing at the event
 * will not have a network.
 *
 * What is cached when: install stores the page, the manifest and the stylesheet;
 * everything else lands in the cache the first time it is fetched. So a visit is
 * enough to make the page itself work offline -- measured 2026-09-08, server
 * stopped, page and all five device sources served from cache -- but the 1.2 MB
 * MicroPython image is fetched only by the first flash, so an organiser who
 * loads this at home and flashes nothing has no image to flash with in the
 * field. (This comment used to claim the image was cached on first visit. It is
 * not, and the cache keys say so.)
 *
 * The cache name carries the build stamp, so a redeploy invalidates it. Getting
 * that wrong would pin organisers on a stale flasher indefinitely, which is
 * exactly the class of silent failure this project exists to avoid.
 *
 * The page is fetched network first and everything else cache first. See the
 * fetch handler: a cached page names a bundle that a deploy has already
 * removed, so serving it from cache is how the caching itself breaks the site.
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

/** Store a copy without making the response wait for it. */
function keep(request, response) {
  if (response && response.ok) {
    const copy = response.clone();
    caches.open(CACHE).then((cache) => cache.put(request, copy));
  }
  return response;
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // The page itself is network first, and this is not a preference. It names
  // the bundle by build stamp -- app.<short sha>.js -- so a cached copy from
  // before a deploy names a file that no longer exists on the server, and the
  // activate handler above has just deleted the cache that held it. The page
  // then loads with no script at all: every control dead and the radio group
  // box empty, which looks like a page that has not finished rather than one
  // that has failed. Falling back to the cache keeps the field working, which
  // is the point of caching it.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => keep(request, response))
        .catch(() => caches.match(request).then((hit) => hit || Response.error())),
    );
    return;
  }

  // Everything else is cache first: named by build stamp or immutable for one,
  // and being offline is the expected case rather than the exception.
  event.respondWith(
    caches.match(request).then(
      (hit) => hit || fetch(request).then((response) => keep(request, response)),
    ),
  );
});
