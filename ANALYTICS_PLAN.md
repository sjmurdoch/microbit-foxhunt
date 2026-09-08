# Analytics for the Radio Treasure Hunt site — plan

Status: built 2026-09-08; the server half is written and not yet deployed. Written 2026-09-08.

Evidence markers as in the archived web setup plan: **[measured]** — run here, with the numbers; **[source]** — read out of vendor documentation or shipped code, with the URL and the date; **[unverified]** — reasoning, not yet settled.

## 1. Why, and what it has to answer

The site has been deployed for two days and nothing is known about who reaches it or what they do there. That is not idle curiosity: `AGENTS.md` section 8 carries a list of open questions that usage data answers directly, and which no amount of desk work will.

| Open question in AGENTS.md §8 | What tells us |
|---|---|
| "Someone on Firefox, Safari or an iPad, whose only route is the `.hex` download" | browser and OS breakdown; `download/*` events against `flash/*` ones |
| "A Chromebook, probably the commonest school deployment and still untested" | Chrome OS in the OS breakdown |
| "A radio group other than 16" | `group/other` against `group/default` |
| "Offline operation is half verified" | `flash/offline` — a flash begun with `navigator.onLine` false |
| "The teaching materials with real children" | views and prints of the worksheet, hunt card and lesson plan |
| Whether anyone is stopped by the v1 refusal | `connect/refused-v1` |

Two further things are worth knowing and are invisible today: how often a flash **fails**, and how often a board flashes but does not come up (`boot-check/failed`). Both are silent failures in the field, which is the class of bug this project spends most of its care on.

## 2. Why not GitHub Pages

Pages is static hosting. It runs no code of ours, and it exposes no access log — there is no server-side route to any of this. So the collector has to live elsewhere; only the collector moves, and the site stays on Pages.

**Decision (2026-09-08, chosen by the project owner): self-hosted GoatCounter** on a server they already run. No third party sees the traffic, the data stays under their control, and it comes with a dashboard, which a bespoke endpoint would not.

It lands on `wordpress-prod` (`secblog`), the Rocky 10 box that already serves `benthamsgaze.org` and the static `murdoch.is`, deployed by `site-wordpress.yml` in the sysadmin repo. **No new domain name is available**, so it has to share a name with the static site.

That is a solved problem, but only once the source is read rather than the blog posts. Two claims that are widely repeated and are wrong for v2.7.0 **[source: `cmd/goatcounter/serve.go` at v2.7.0, read 2026-09-08]**:

* **`-tls none` is not a thing.** The flag's values are `http`, a `.pem` path, `acme[:cache]` and `rdr`, and **`http` — "don't serve any TLS" — is the default**, which is exactly what is wanted behind Apache.
* **Subdirectories are supported.** `-base-path` exists and its help names this case: *"in some cases it's useful to run GoatCounter under a path ('example.com/stats'), in which case you'll need to set this to '/stats'"*.

**The hunt is counted as part of murdoch.is, not as a site of its own.** GoatCounter is multi-site and selects a site by the `Host` header, so a separate site was possible -- but the hunt is part of the owner's personal site rather than a thing standing on its own, and it is counted that way. What that costs is separability, and a namespace buys it back: **every path this site reports, page views and events alike, goes under `radio-treasure-hunt/`**, so one filter on the dashboard shows the hunt and only the hunt, and the personal site's own paths stay clean of it. `https://murdoch.is/radio-treasure-hunt` was checked and is a 404, so the namespace collides with nothing already served.

Page identity is derived from the last path segment rather than reported as the raw pathname, so it survives the site moving -- from `/radio-treasure-hunt/` on Pages to a custom domain or a domain root -- without silently splitting one page's history in two.

So GoatCounter runs on the loopback under `-base-path /stats`, and Apache reverse-proxies `/stats` on the existing `murdoch.is` vhost. Everything moves under that prefix, which means the beacon endpoint is `https://murdoch.is/stats/count` and the dashboard is a normal browser page at `https://murdoch.is/stats/` behind GoatCounter's own login — no new name, no certificate change, and no SSH tunnel to read the numbers. Sites are matched by `Host`, so Apache passes it through (`ProxyPreserveHost On`) and the site is created with `-vhost=murdoch.is`.

## 3. Privacy posture

The audience is children in schools and Scout groups, and a teacher may have to answer for this site to a data protection officer. The design is therefore the conservative one, and the properties below are the ones to preserve if this is ever changed.

* **No cookies, no `localStorage`, no persistent identifier of any kind.** GoatCounter identifies a repeat visit server-side with a rotating, non-identifiable hash **[source: goatcounter.com/help, read 2026-09-08]**; nothing is stored on the visitor's device. Storing nothing on the device is also what keeps this outside PECR's consent rules, so the site needs no cookie banner.
* **No third-party script and no third-party request.** The beacon goes to the project owner's own host.
* **Do Not Track and Global Privacy Control are honoured**, and honoured by not sending anything at all rather than by sending a flag.
* **A fixed event allowlist.** The client can only ever send one of a known set of strings, listed in one place and pinned by a test. This is the guard that matters most: the page holds a board's DAPLink serial number, which is a hardware identifier, and an allowlist makes it impossible for a future edit to beacon it by accident.
* **Data minimisation over completeness.** The radio group is reported as `group/default` or `group/other`, never the number itself: whether organisers move off the default is the open question, and the specific value answers nothing further.
* **It says so on the page.** A short "What this page counts" note, in plain words, listing what is sent.

## 4. What is sent

One GET to the `/count` endpoint per page view and per event. The parameters are GoatCounter's documented, compatibility-guaranteed set **[source: goatcounter.com/help/pixel, read 2026-09-08]**: `p` path or event name, `t` title, `r` referrer, `e` event flag, `s` screen size, `rnd` cache buster. The endpoint answers with a 1×1 GIF.

Page views use the page path. Events use these names, and only these:

```
connect/ok            connect/refused-v1     connect/failed
flash/<role>/ok       flash/<role>/failed    flash/offline
identify/<role>       identify/unknown       boot-check/failed
monitor/start         download/<role>
group/default         group/other
webusb/available      webusb/unsupported
session/boards/1      session/boards/2-4     session/boards/5-9
session/boards/10+    hunt/ready
print/<page>
```

`<role>` comes from `flash.ROLES` and is never written down a second time — AGENTS.md section 9 is explicit that two copies of a fact will drift, so the allowlist is generated at build time from the same mapping the manifest is.

## 5. Reading impact off this

Page views are not impact. What the project owner has to be able to say is how much the thing is used and what it led to, and these are the numbers that carry that, in rough order of how much weight they bear.

| Claim | The number | What it really means |
|---|---|---|
| Boards prepared | `flash/<role>/ok` | Someone had hardware in their hand and set it up. The strongest evidence of real use, because it cannot happen by browsing. |
| Complete hunts prepared | `hunt/ready` | A Treasure and at least one Hound set up in the same sitting: a playable game. Fires once per session. |
| Class-scale use | `session/boards/10+` | Sittings that set up ten or more boards, which is a class set rather than a hobbyist. `5-9`, `2-4` and `1` give the shape of the rest. |
| Teaching materials used | `print/worksheet`, `print/lesson-plan`, `print/hunt-card` | Someone put paper in a printer, which is a stronger signal than opening the page. |
| Reach | visits, and GoatCounter's own country and browser breakdown | Ordinary audience numbers, and the only cross-session measure -- there is no identifier, so "unique visitors" is GoatCounter's rotating hash, not people. |
| Who is turned away | `webusb/unsupported` against `webusb/available` | The size of the Firefox/Safari/iPad population, feature-detected rather than guessed from a user agent. |

**And what it does not license.** This matters more than the table, because the numbers will end up in a report where someone may push back on them.

* **A prepared hunt is not a played hunt.** `hunt/ready` says boards were set up, and nothing at all about whether a game happened, whether children enjoyed it, or whether anyone learned anything. The acceptance test for that is still watching a class use it -- AGENTS.md section 8 says so and analytics does not change it.
* **Everything here undercounts, by an unknown amount.** Blockers, Do Not Track, and a school network that blocks the stats host all remove real use from the figures, and the last of those is likeliest in exactly the population being measured. Treat every number as a floor.
* **Offline use is invisible.** The page is built to work in a field with no network, and a beacon sent there never arrives. A hunt run entirely from a cached page counts as nothing.
* **Site-level totals are not the hunt's.** Because this is counted inside the personal site, the dashboard's unfiltered totals, and its browser and country breakdowns, mix the hunt with everything else on `murdoch.is`. Filter by the namespace before quoting any number as the hunt's.
* **A session is one page load, not a person.** Someone who sets up boards over two visits is two sessions; nothing joins them, deliberately.
* **A board set up twice counts once.** The tally is by serial number, so reflashing is not inflation -- but a board set up in two separate sittings is two counts.

## 6. Every browser, not only the ones that can flash

The page has always had two audiences: Chrome and Edge, which can set boards up over WebUSB, and everything else -- Firefox, Safari, iOS and iPadOS -- whose only route is downloading a `.hex` and dragging it onto the board. The second group has to be counted too, and has to work.

**It did not work.** Building this found that the bundle carried optional chaining, which is ES2020, so Safari 13.0 and older Firefox failed to *parse* it. That is not a degraded page: it is no JavaScript at all, which on those browsers means dead controls, an empty radio group box, no `.hex` download and no analytics -- on precisely the browsers that depend on the download. The bundles are now built with `--target=es2019` and a test builds them for real and fails on either ES2020 operator. WebUSB itself stays a runtime feature check, which is the right shape: the API's absence is a fact about the browser, not a syntax level.

`webusb/available` and `webusb/unsupported` are feature-detected once per page. Guessing from the user agent would be wrong in both directions -- Chrome on iOS has no WebUSB at all, and a Chromium on Linux can be missing its udev rules.

The `.hex` route can be counted (`download/<role>`) but not followed: nothing of ours runs on the board afterwards, so whether the file was ever dragged onto a micro:bit is unknowable. That asymmetry is worth stating whenever the two routes are compared.

## 7. Shape of the change

**One copy of the beacon.** `web/src/analytics.js` is shared by two esbuild entry points: `main.js` for the setup page and `teaching.js` for the three teaching pages, which today load a hand-copied `web/teaching.js` with no bundling. Bundling the second entry is what avoids a second copy of the beacon living in a plain script.

**The endpoint is a build-time input, not a runtime fetch.** esbuild `--define` substitutes it into both bundles, so there is no configuration request to make and nothing to fail when a field laptop is offline.

**Configuration** follows the project rule that a setting belongs in TOML and must also be settable from the command line and the environment, consistently:

| | |
|---|---|
| `pyproject.toml` | `[tool.foxhunt.analytics] endpoint`, `hosts` |
| Environment | `FOXHUNT_ANALYTICS_ENDPOINT`, `FOXHUNT_ANALYTICS_HOSTS` |
| Command line | `--analytics-endpoint`, `--analytics-hosts`, `--no-analytics` |

Precedence is command line, then environment, then the file, then off. **Empty means off, and off is the default**, so a fork, a local `make site`, and `make site-serve` send nothing without anyone having to remember. `build_site.py` prints the endpoint it built with, so a build that quietly lost its analytics is visible in the CI log rather than silent.

**`hosts` is a second, independent guard**: the beacon fires only when `location.hostname` is one of them. A fork that copies the committed config still sends nothing, because it is served from a different host.

**The service worker needs no change.** It only intercepts same-origin `GET`s, and the beacon is cross-origin, so it passes straight through.

## 8. Failure behaviour

Analytics must never be able to break a flash in a field. So: every call is wrapped, nothing is awaited, nothing retries, and nothing is queued for later. An offline page simply loses the count. A queue would be both a persistence mechanism on the visitor's device and a way for an event to arrive long after the fact, which is worse on both counts than losing it.

Ad and tracker blockers will block the requests. That is the visitor's choice working correctly; nothing is done to work around it, and nothing on the page depends on the beacon succeeding.

## 9. Server side

To be run by the project owner on their own host; recorded here so the site's half and the server's half are documented together **[source: github.com/arp242/goatcounter, read 2026-09-08; not yet run]**.

```sh
# Go 1.21+ and a C compiler (SQLite).
git clone --branch=release-2.7 https://github.com/arp242/goatcounter
cd goatcounter && go build ./cmd/goatcounter

./goatcounter db create site -vhost=stats.example.org -user.email=you@example.org
./goatcounter serve -listen=:443 -tls=tls,rdr,acme
```

The site's endpoint is then `https://stats.example.org/count`. Two things to check on the server once it is up, neither of which can be checked from here:

* that it is not retaining IP addresses beyond what the session hash needs;
* that the dashboard is not publicly readable, unless that is wanted.

## 10. Tests

In `test_site.py`, in the style of the ones already there:

* the built page contains no endpoint at all when analytics is unconfigured — the default, and the one that protects forks;
* configuring an endpoint puts it in both bundles, and only there;
* every event name a call site uses is in the allowlist, and the allowlist covers every role in `flash.ROLES`;
* the allowlist contains nothing that looks like an identifier — asserted by construction: the names are a closed set;
* precedence: command line beats environment beats file;
* the privacy note names the same things the allowlist sends, so the page cannot promise less than the code does;
* the teaching bundle is stamped and referenced by all three teaching pages.

## 11. Not doing

* **No funnel or session correlation.** GoatCounter's own session hash gives "unique visits" without one; anything more would mean an identifier we would have to defend.
* **No custom dimensions or properties.** They exist in other products; GoatCounter events are paths, and the vocabulary above is shaped to suit that.
* **No analytics on the `.hex` download itself.** It is a static file on Pages, so a download that starts is countable as a click event and no more; whether the file was used cannot be known.

## 12. Open afterwards

* End-to-end verification needs a real endpoint: build with it, load the page, and confirm the hit appears on the dashboard. Until that is done the client half is **[unverified]** against a live server, however well tested it is here.
* Whether a school network or a managed Chromebook blocks the stats host — plausible, and it would bias exactly the population most worth measuring.
