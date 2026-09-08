/**
 * Counting how the site is used, without tracking anybody.
 *
 * The audience is children in schools and Scout groups, and a teacher may have
 * to answer for this page to a data protection officer. So the design is the
 * conservative one, and these properties are load-bearing rather than stylistic:
 *
 *  - No cookies, no localStorage, no identifier of any kind. Nothing is stored
 *    on the visitor's device, which is also what keeps this outside PECR's
 *    consent rules -- so the site needs no cookie banner. Repeat visits are
 *    counted server-side by GoatCounter's own rotating, non-identifiable hash.
 *  - EVENTS is a closed set. The page holds a board's DAPLink serial number,
 *    which is a hardware identifier; an allowlist is what makes it impossible
 *    for a later edit to beacon it by accident. test_site.py checks that every
 *    name a call site uses is in the set, so adding an event means adding it in
 *    build_site.py where the set is built.
 *  - The radio group is reported as group/default or group/other, never the
 *    number. Whether organisers move off the default is the open question in
 *    AGENTS.md section 8; the value answers nothing further, so it is not sent.
 *
 * Nothing here may break a flash in a field: every call is wrapped, nothing is
 * awaited, and nothing is retried or queued. An offline page loses the count,
 * which is the right trade -- a queue would be both storage on the device and a
 * way for an event to arrive long after the fact.
 *
 * Blockers will block the requests. That is the visitor's choice working, and
 * nothing on the page depends on a beacon succeeding.
 *
 * The wire format is GoatCounter's /count endpoint, whose parameters are
 * documented as stable: p path or event name, t title, r referrer, e event
 * flag, s screen size, rnd cache buster. It answers with a 1x1 GIF.
 */

// Injected by build_site.py through esbuild --define. Empty endpoint = off,
// which is the default, so a fork or a local build sends nothing.
const CONFIG = __ANALYTICS__;

export const ENDPOINT = CONFIG.endpoint;
export const HOSTS = CONFIG.hosts;
export const EVENTS = CONFIG.events;

/**
 * The namespace every reported path goes under.
 *
 * The counting lands in the personal site's own GoatCounter site, because the
 * hunt is part of that site rather than a thing of its own -- so without a
 * shared prefix its events would scatter through that site's own paths with no
 * way to tell them apart. With one, a single filter on the dashboard shows the
 * hunt and nothing else, and the site's own traffic stays clean of it.
 */
export const PREFIX = CONFIG.prefix;

/**
 * Whether anything may be sent at all.
 *
 * The host check is a second, independent guard on top of the endpoint: a fork
 * that inherits the committed configuration is served from a different host, so
 * it still sends nothing without anyone having to remember to turn it off.
 */
export function enabled() {
  try {
    if (!ENDPOINT || !HOSTS.length) return false;
    if (HOSTS.indexOf(location.hostname) === -1) return false;
    return true;
  } catch (e) {
    return false;
  }
}

/**
 * Fire one request. Returns whether it was sent, which is what the tests and
 * the caller can see; whether it arrived is deliberately not knowable here.
 *
 * The image is attached to the document and removed once it settles: an Image
 * with no reference can be collected before the request goes out.
 */
function send(params) {
  if (!enabled()) return false;
  try {
    params.rnd = String(Math.random()).slice(2, 10);
    const query = Object.keys(params)
      .filter((k) => params[k] !== "" && params[k] !== undefined)
      .map((k) => encodeURIComponent(k) + "=" + encodeURIComponent(params[k]))
      .join("&");
    const img = document.createElement("img");
    img.setAttribute("alt", "");
    img.setAttribute("aria-hidden", "true");
    img.style.position = "absolute";
    img.style.width = img.style.height = "1px";
    img.style.opacity = "0";
    const done = () => { if (img.parentNode) img.parentNode.removeChild(img); };
    img.addEventListener("load", done);
    img.addEventListener("error", done);
    img.src = ENDPOINT + "?" + query;
    document.body.appendChild(img);
    return true;
  } catch (e) {
    return false;
  }
}

/**
 * Which page this is, under the namespace.
 *
 * Derived from the last path segment rather than reported as the raw pathname,
 * so the identity survives the site moving: it reads the same whether it is
 * served from /radio-treasure-hunt/ on Pages, from a domain root, or from
 * anywhere else. index and the bare directory both report the prefix itself.
 */
export function pagePath() {
  let page = "";
  try {
    const path = location.pathname || "/";
    // A trailing slash is a directory index, where the last segment names the
    // directory rather than a page -- so /radio-treasure-hunt/ is the front
    // page, not a page called radio-treasure-hunt.
    if (!path.endsWith("/")) {
      page = (path.split("/").filter(Boolean).pop() || "").replace(/\.html$/, "");
      if (page === "index") page = "";
    }
  } catch (e) {
    page = "";
  }
  return "/" + PREFIX + (page ? "/" + page : "/");
}

/** The page itself. Called once per page, from each entry point. */
export function pageview() {
  try {
    return send({
      p: pagePath(),
      t: document.title,
      r: document.referrer,
      s: [screen.width, screen.height, devicePixelRatio || 1].join(","),
    });
  } catch (e) {
    return false;
  }
}

/**
 * One event. `name` must be in EVENTS: an unknown name is dropped rather than
 * sent, so a typo loses a count instead of inventing a path on the dashboard.
 */
export function event(name) {
  // The allowlist holds the bare vocabulary; the namespace is added here, in
  // one place, so call sites stay readable and the test that scans them still
  // sees the names it is checking.
  if (EVENTS.indexOf(name) === -1) return false;
  const path = PREFIX + "/" + name;
  return send({ p: path, e: "1", t: path });
}

// Role-shaped events. The role keys come from flash.ROLES via the generated
// allowlist and are never written down here -- AGENTS.md section 9 on two
// copies of a fact drifting. These are the only way to build a name that is
// not a literal, which is what keeps the allowlist test able to see them all.
export function flashed(role, ok) {
  return event("flash/" + role + (ok ? "/ok" : "/failed"));
}

export function identified(role) {
  return event("identify/" + (role || "unknown"));
}

export function downloaded(role) {
  return event("download/" + role);
}

/**
 * How far a session got. These are the numbers that say whether the project is
 * used, as opposed to visited, so they are worth more than any page view.
 *
 * Each fires at most once per session, and a session is one page load -- there
 * is no identifier, so nothing joins two visits together and nothing here can
 * count a person. A session that sets up twelve boards therefore contributes
 * one count to each bucket up to 10+, which is what makes "sessions that
 * reached ten boards" readable straight off the dashboard as a count of
 * class-scale set-ups.
 *
 * hunt/ready is the strongest single measure: a Treasure and at least one Hound
 * set up in the same session is a playable game prepared. It is still a proxy
 * -- it says a hunt was made ready, never that it was played, and section
 * "Reading impact" in archive/ANALYTICS_PLAN.md is explicit about that.
 */
const BOARD_BUCKETS = [[10, "10+"], [5, "5-9"], [2, "2-4"], [1, "1"]];
const reached = new Set();

export function session(boards, playable) {
  for (const [least, name] of BOARD_BUCKETS) {
    if (boards >= least) milestone("session/boards/" + name);
  }
  if (playable) milestone("hunt/ready");
}

/** Once per page load, however many times it is called. */
function milestone(name) {
  if (reached.has(name)) return false;
  reached.add(name);
  return event(name);
}

/** group/default or group/other -- see the minimisation note at the top. */
export function group(value, defaultGroup) {
  return event(Number(value) === Number(defaultGroup) ? "group/default" : "group/other");
}
