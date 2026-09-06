/**
 * UI for the fox hunt flasher.
 *
 * Everything with a decision in it lives in device.js (pure), serial.js
 * (transport) or flasher.js (USB). This file is wiring: fetch, buttons, text.
 */
import { Flasher, BoardRefused, webUsbAvailable } from "./flasher.js";
import { Monitor } from "./monitor.js";
import { renderRadioConfig } from "./device.js";

const $ = (id) => document.getElementById(id);
const GROUP_KEY = "foxhunt.group";

let manifest = null;
let sources = {};
let flasher = null;
let monitor = null;
let board = null;

const text = (el, s) => { el.textContent = s; };
const show = (el, on = true) => { el.hidden = !on; };

function banner(el, kind, html) {
  el.className = "card banner " + kind;
  el.innerHTML = html;
  show(el);
}

// --- loading ---------------------------------------------------------------

async function loadManifest() {
  manifest = await (await fetch("manifest.json")).json();
  const names = new Set();
  for (const spec of Object.values(manifest.roles)) {
    for (const [src] of spec.files) names.add(src);
  }
  await Promise.all(
    [...names].map(async (n) => { sources[n] = await (await fetch(n)).text(); }),
  );
}

/** The MicroPython image is 1.2 MB, so it is fetched only when first needed. */
async function loadMicroPython(onNote) {
  if (sources.__micropython) return;
  onNote && onNote("Fetching MicroPython " + manifest.micropython.version + "…");
  const path = "micropython/" + manifest.micropython.file;
  sources.__micropython = await (await fetch(path)).text();
}

// --- the radio group -------------------------------------------------------

function currentGroup() {
  return Number($("group").value);
}

function groupIsUsable(group) {
  try {
    renderRadioConfig(sources["radio_config.py"], group, manifest.group);
    return null;
  } catch (e) {
    return e.message;
  }
}

function refreshGroup() {
  const group = currentGroup();
  const problem = groupIsUsable(group);
  text($("group-note"), problem || `Both boards must be flashed on group ${group}.`);
  $("group-note").className = problem ? "note bad-text" : "note";
  for (const id of ["flash-fox", "flash-hound", "monitor-start", "dl-fox", "dl-hound"]) {
    if ($(id)) $(id).disabled = !!problem;
  }
  if (!problem) {
    try { localStorage.setItem(GROUP_KEY, String(group)); } catch (e) { /* private mode */ }
  }
  const warning = flasher && flasher.groupWarning(group);
  if (warning) banner($("group-warning"), "warn", warning);
  else show($("group-warning"), false);
}

// --- connecting ------------------------------------------------------------

async function connect() {
  const button = $("connect");
  button.disabled = true;
  show($("result"), false);
  try {
    const info = await flasher.connect();
    text(button, "Connect a different micro:bit");
    show($("forget"), true);

    let survey = null;
    try {
      survey = await flasher.survey();
      await flasher.reset();
    } catch (e) {
      console.warn("[foxhunt] survey failed", e);
    }
    board = { ...info, survey };
    renderBoard();
    show($("act"), true);
  } catch (e) {
    if (e instanceof BoardRefused) {
      banner($("board"), "bad", `<strong>This board will not be flashed.</strong><br>${e.message}`);
      show($("board"), true);
      show($("act"), false);
    } else if (e && e.code === "no-device-selected") {
      /* the picker was dismissed; say nothing */
    } else if (e && e.code === "device-in-use") {
      banner($("board"), "bad",
        "<strong>Another program has this board.</strong> Close any other tab, " +
        "editor or serial monitor using it, then try again.");
      show($("board"), true);
    } else {
      banner($("board"), "bad", `<strong>Could not connect.</strong> ${escapeHtml(String(e.message || e))}`);
      show($("board"), true);
    }
  } finally {
    button.disabled = false;
  }
}

function renderBoard() {
  const s = board.survey;
  const rows = [
    ["Board", `<span class="mono">${board.serialNumber || "unknown"}</span>`],
    ["Type", `micro:bit ${board.version} (id ${board.boardId})`],
  ];
  if (s) {
    rows.push(["Firmware", `MicroPython ${s.release || "?"}`]);
    rows.push(["Currently", describeCurrent(s)]);
  } else {
    rows.push(["Currently", "could not be read &mdash; it will still flash"]);
  }
  $("board").className = "card";
  $("board").innerHTML =
    "<dl class='kv'>" +
    rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("") +
    "</dl>";
  show($("board"), true);

  const forecast = s ? s.forecast : { full: true, seconds: 25, why: "the board's firmware is unknown" };
  text($("forecast"),
    forecast.full
      ? `This will take about ${forecast.seconds} seconds, because ${forecast.why}. Do not unplug it.`
      : `This should take a few seconds, because ${forecast.why}.`);
  refreshGroup();
}

function describeCurrent(s) {
  if (!s.files.length) return "nothing &mdash; the filesystem is empty";
  const role = s.role ? manifest.roles[s.role].label : "an unrecognised program";
  const group = s.group === null ? "" : ` on group <strong>${s.group}</strong>`;
  const match = s.role
    ? (s.matchesSite ? " (same code as this page)" : " (different code from this page)")
    : "";
  return `${role}${group}${match}`;
}

// --- flashing --------------------------------------------------------------

async function doFlash(role) {
  const group = currentGroup();
  const buttons = ["flash-fox", "flash-hound", "monitor-start", "connect"].map($);
  buttons.forEach((b) => { b.disabled = true; });
  show($("result"), false);
  show($("progress"), true);
  const setNote = (s) => text($("progress-text"), s);

  try {
    await loadMicroPython(setNote);
    setNote("Flashing… do not unplug the board.");
    const { stage, seconds, image } = await flasher.flashRole(role, group, (s, fraction) => {
      if (fraction !== undefined) {
        $("bar-fill").style.width = Math.round(fraction * 100) + "%";
        setNote(`${stageLabel(s)} ${Math.round(fraction * 100)}%`);
      } else {
        setNote(stageLabel(s) + "…");
      }
    });
    $("bar-fill").style.width = "100%";

    setNote("Checking it started…");
    const boot = await flasher.bootCheck(3);
    const verified = await flasher.verify(image.want);
    await flasher.reset();

    const label = manifest.roles[role].label;
    if (boot.ok && verified.ok) {
      banner($("result"), "ok",
        `<strong>${label} flashed and running.</strong><br>` +
        `Radio group <strong>${group}</strong> &mdash; write that on the board.<br>` +
        `<span class="note">${stageLabel(stage)} in ${seconds.toFixed(1)} s; ` +
        `filesystem verified from the board.</span>`);
    } else if (!boot.ok) {
      banner($("result"), "bad",
        `<strong>${label} was written, but it is not running.</strong><br>${escapeHtml(boot.reason)}` +
        (boot.detail ? `<pre class="stream">${escapeHtml(boot.detail)}</pre>` : ""));
    } else {
      const bad = verified.rows.filter((r) => !r.ok).map((r) => r.target).join(", ");
      banner($("result"), "bad",
        `<strong>${label} started, but the files on the board are not what we wrote.</strong><br>` +
        `Mismatched: ${escapeHtml(bad)}. Try flashing again.`);
    }
    renderSession();
    refreshGroup();
    board.survey = await safeSurvey();
    if (board.survey) renderBoard();
  } catch (e) {
    banner($("result"), "bad",
      `<strong>Flashing failed.</strong> ${escapeHtml(String(e.message || e))}<br>` +
      `<span class="note">The board may need flashing again before it will run.</span>`);
  } finally {
    show($("progress"), false);
    $("bar-fill").style.width = "0";
    buttons.forEach((b) => { b.disabled = false; });
    refreshGroup();
  }
}

async function safeSurvey() {
  try {
    const s = await flasher.survey();
    await flasher.reset();
    return s;
  } catch (e) {
    return null;
  }
}

const stageLabel = (stage) =>
  stage === "FullFlashing" ? "Full flash"
    : stage === "PartialFlashing" ? "Quick flash"
      : stage === "Connecting" ? "Connecting"
        : stage === "FindingDevice" ? "Finding the board"
          : "Working";

// --- monitor ---------------------------------------------------------------

async function startMonitor() {
  const group = currentGroup();
  show($("monitor-panel"), true);
  $("monitor-out").innerHTML = "<p class='note'>Flashing the listener…</p>";
  $("monitor-panel").scrollIntoView({ behavior: "smooth", block: "start" });
  try {
    await loadMicroPython();
    monitor = new Monitor(flasher, {
      onStart: () => { $("monitor-out").innerHTML = "<p>Listening…</p>"; },
      onSample: (sample, verdict) => renderMonitor(sample, verdict),
    });
    await monitor.start(group);
    renderSession();
  } catch (e) {
    banner($("monitor-out"), "bad", escapeHtml(String(e.message || e)));
  }
}

function renderMonitor(sample, verdict) {
  const zones = manifest.monitor.zones;
  $("monitor-out").innerHTML =
    `<dl class="kv">
       <dt>Packets</dt><dd>${verdict.count}</dd>
       <dt>Signal</dt><dd>${sample.rssi} dBm</dd>
       <dt>Zones heard</dt><dd>${zones.map((z) =>
         verdict.heard.includes(z) ? `<strong>${z}</strong>` : `<span class="note">${z}</span>`).join(" ")}</dd>
     </dl>` +
    (verdict.ok
      ? `<p class="banner ok">All three zones heard &mdash; the fox is transmitting and this spot can hear it.</p>`
      : `<p class="note">Still waiting for: ${verdict.missing.join(", ")}. Move closer to the fox, or check both boards are on group ${currentGroup()}.</p>`);
}

async function restoreGame() {
  if (monitor) monitor.stop();
  show($("monitor-panel"), false);
  await doFlash("hound");
}

// --- downloads -------------------------------------------------------------

async function download(role) {
  const group = currentGroup();
  const button = $(role === "fox" ? "dl-fox" : "dl-hound");
  const label = button.textContent;
  button.disabled = true;
  text(button, "Building…");
  try {
    await loadMicroPython();
    const image = flasher.buildImage(role, group);
    const blob = new Blob([image.hex], { type: "application/octet-stream" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `foxhunt-${role}-group${group}-microbitV2.hex`;
    a.click();
    URL.revokeObjectURL(url);
  } finally {
    text(button, label);
    button.disabled = false;
  }
}

// --- session ---------------------------------------------------------------

function renderSession() {
  const body = $("session-table").querySelector("tbody");
  body.innerHTML = flasher.flashed
    .map((f) => `<tr><td class="mono">${(f.serialNumber || "?").slice(0, 12)}…</td>` +
                `<td>${manifest.roles[f.role].label}</td><td>${f.group}</td></tr>`)
    .join("");
  show($("session"), flasher.flashed.length > 0);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// --- start -----------------------------------------------------------------

async function init() {
  await loadManifest();

  const input = $("group");
  input.min = manifest.group.min;
  input.max = manifest.group.max;
  let saved = null;
  try { saved = localStorage.getItem(GROUP_KEY); } catch (e) { /* private mode */ }
  input.value = saved || manifest.group.default;
  input.addEventListener("input", refreshGroup);

  if (!webUsbAvailable()) {
    show($("unsupported"), true);
    $("connect").disabled = true;
    for (const id of ["flash-fox", "flash-hound", "monitor-start"]) $(id).disabled = true;
  }

  flasher = new Flasher(manifest, sources);
  refreshGroup();

  $("connect").addEventListener("click", connect);
  $("forget").addEventListener("click", async () => {
    await flasher.forget(true);
    show($("board"), false);
    show($("act"), false);
    show($("forget"), false);
    text($("connect"), "Connect a micro:bit");
  });
  $("flash-fox").addEventListener("click", () => doFlash("fox"));
  $("flash-hound").addEventListener("click", () => doFlash("hound"));
  $("monitor-start").addEventListener("click", startMonitor);
  $("monitor-restore").addEventListener("click", restoreGame);
  $("monitor-stop").addEventListener("click", () => {
    if (monitor) monitor.stop();
    show($("monitor-panel"), false);
  });
  $("dl-fox").addEventListener("click", () => download("fox"));
  $("dl-hound").addEventListener("click", () => download("hound"));

  registerServiceWorker();
}

function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return;
  // Relative, so it works under a project subpath such as /foxhunt/.
  navigator.serviceWorker.register("sw.js").then((reg) => {
    reg.addEventListener("updatefound", () => {
      const fresh = reg.installing;
      fresh && fresh.addEventListener("statechange", () => {
        if (fresh.state === "installed" && navigator.serviceWorker.controller) {
          const note = $("sw-note");
          note.innerHTML = "A newer version of this page is available. " +
            "<button id='sw-reload'>Reload</button>";
          show(note, true);
          $("sw-reload").addEventListener("click", () => location.reload());
        }
      });
    });
  }).catch((e) => console.warn("[foxhunt] service worker:", e));
}

init().catch((e) => {
  document.body.insertAdjacentHTML("afterbegin",
    `<p class="banner bad">This page failed to load: ${escapeHtml(String(e.message || e))}</p>`);
});
