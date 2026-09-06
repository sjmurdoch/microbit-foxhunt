/**
 * UI for the fox hunt flasher.
 *
 * Everything with a decision in it lives in device.js (pure), serial.js
 * (transport) or flasher.js (USB). This file is wiring: fetch, buttons, text.
 */
import { Flasher, BoardRefused, webUsbAvailable } from "./flasher.js";
import { Monitor } from "./monitor.js";
import { renderRadioConfig, tallyBoards } from "./device.js";

const $ = (id) => document.getElementById(id);
const GROUP_KEY = "foxhunt.group";

let manifest = null;
let sources = {};
let flasher = null;
let monitor = null;
let board = null;

const text = (el, s) => { el.textContent = s; };
const show = (el, on = true) => { el.hidden = !on; };

/**
 * Say what is happening, immediately.
 *
 * The slow steps are the device chooser (as long as the user takes), reading a
 * board over the REPL (a few seconds), and a full flash (23 seconds). Greying
 * out a button is not enough feedback for any of them -- the page reads as
 * broken. Every await below is bracketed by one of these.
 */
function busy(message) {
  const el = $("status");
  if (!message) {
    show(el, false);
    el.innerHTML = "";
    return;
  }
  el.className = "status";
  el.innerHTML = `<span class="spinner" aria-hidden="true"></span><span>${escapeHtml(message)}</span>`;
  show(el, true);
}

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
  const note = "Fetching MicroPython " + manifest.micropython.version + " (1.2 MB, once)\u2026";
  busy(note);
  onNote && onNote(note);
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

function clearBoardUi(warning, kind) {
  board = null;
  show($("board"), false);
  show($("act"), false);
  show($("forget"), false);
  show($("monitor-panel"), false);
  show($("result"), false);
  text($("connect"), "Connect a micro:bit");
  // Not #result: that lives inside the "Flash it" section, which has just been
  // hidden, so a message put there would never be seen.
  if (warning) banner($("next-prompt"), kind || "warn", warning);
  else show($("next-prompt"), false);
}

async function connect() {
  const button = $("connect");
  button.disabled = true;
  busy("Opening the device chooser\u2026");
  show($("result"), false);
  try {
    // If a board is already on screen, this button says "Connect a different
    // micro:bit" and must mean it: drop the remembered device so the picker
    // appears, rather than reconnecting to what is already there -- or, if it
    // has since been unplugged, failing on a dead handle.
    const info = await flasher.connect({ chooseAgain: board !== null });
    show($("next-prompt"), false);
    text(button, "Connect a different micro:bit");
    show($("forget"), true);

    // Show the board the moment we can identify it, rather than holding the
    // page blank through several seconds of REPL conversation.
    board = { ...info, survey: null, surveyState: "pending" };
    renderBoard();
    show($("act"), true);

    try {
      board.survey = await flasher.survey();
      board.surveyState = "done";
      renderBoard();
      await flasher.reset();
    } catch (e) {
      console.warn("[foxhunt] survey failed", e);
      board.surveyState = "failed";
      renderBoard();
    }
    busy(null);
  } catch (e) {
    busy(null);
    if (e instanceof BoardRefused) {
      banner($("board"), "bad", `<strong>This board will not be flashed.</strong><br>${e.message}`);
      show($("board"), true);
      show($("act"), false);
      show($("next-prompt"), false);
    } else if (e && e.code === "no-device-selected") {
      // Either the dialog was dismissed, which needs no comment, or every
      // attached board has been excluded by "Done with this board".
      if (flasher.flashed.length) {
        banner($("next-prompt"), "warn",
          "No board was chosen. Boards you have already set up are hidden from " +
          "the chooser, so plug in the next one &mdash; or reload the page if " +
          "you need to go back to one of them.");
      }
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
  } else if (board.surveyState === "pending") {
    rows.push(["Firmware", "<span class='note'>reading\u2026</span>"]);
    rows.push(["Currently", "<span class='note'>reading\u2026</span>"]);
  } else {
    rows.push(["Currently", "could not be read &mdash; it will still flash"]);
  }
  // A board on a different group from the one selected will be flashed onto the
  // selected group, which is usually what is wanted -- but if the user is here
  // to diagnose a hunt that "does not work", this is the answer, and it is
  // otherwise invisible. AGENTS.md section 5: the symptom is silence.
  let mismatch = "";
  if (s && s.group !== null && s.group !== currentGroup()) {
    mismatch =
      `<p class="banner warn">This board is on <strong>group ${s.group}</strong>, but you have ` +
      `<strong>group ${currentGroup()}</strong> selected above. Boards on different groups cannot ` +
      `hear each other, and nothing on the board says so. Flashing it now will move it to ` +
      `group ${currentGroup()}.</p>`;
  }

  $("board").className = "card";
  $("board").innerHTML =
    "<dl class='kv'>" +
    rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("") +
    "</dl>" + mismatch;
  show($("board"), true);

  if (!s && board.surveyState === "pending") {
    text($("forecast"), "Checking what the board is running\u2026");
  } else {
    const forecast = s ? s.forecast
      : { full: true, seconds: 25, why: "the board's firmware could not be read" };
    text($("forecast"),
      forecast.full
        ? `This will take about ${forecast.seconds} seconds, because ${forecast.why}. Do not unplug it.`
        : `This should take a few seconds, because ${forecast.why}.`);
  }
  refreshGroup();
  renderTally();
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
  setNote(`Preparing to flash the ${manifest.roles[role].label.toLowerCase()}\u2026`);
  busy("Preparing\u2026");

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
      // The next thing to do goes in the success message. It used to live only
      // as "Done with this board" further up the page, which is nowhere near
      // where anyone is looking after a flash finishes -- so setting up a class
      // set meant hunting for the next step fifteen times.
      banner($("result"), "ok",
        `<strong>${label} flashed and running.</strong><br>` +
        `Write <strong>${label} &middot; group ${group}</strong> on a sticker and put it on ` +
        `this board.<br>` +
        `<span class="note">${stageLabel(stage)} in ${seconds.toFixed(1)} s; ` +
        `contents checked against the board.</span>` +
        `<p class="row"><button id="next-board" class="primary">Done &mdash; set up another board</button></p>`);
      const next = $("next-board");
      if (next) next.addEventListener("click", nextBoard);
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
    if (board) {
      board.survey = await safeSurvey();
      board.surveyState = board.survey ? "done" : "failed";
      if (board.survey) renderBoard();
    }
  } catch (e) {
    banner($("result"), "bad",
      `<strong>Flashing failed.</strong> ${escapeHtml(String(e.message || e))}<br>` +
      `<span class="note">The board may need flashing again before it will run.</span>`);
  } finally {
    busy(null);
    show($("progress"), false);
    $("bar-fill").style.width = "0";
    buttons.forEach((b) => { b.disabled = false; });
    refreshGroup();
  }
}

/** Finish with this board and get ready for the next one. */
async function nextBoard() {
  busy("Finishing with this board\u2026");
  if (monitor) monitor.stop();
  await flasher.forget(true);
  busy(null);
  const { boards } = boardTally();
  clearBoardUi(
    `<strong>${boards} board${boards === 1 ? "" : "s"} done.</strong> ` +
    "Unplug this one, plug in the next, and press <em>Connect a micro:bit</em>.",
    "ok");
  renderTally();
  $("connect").scrollIntoView({ behavior: "smooth", block: "center" });
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
    busy("Flashing the listener onto this board\u2026");
    monitor = new Monitor(flasher, {
      onStart: () => { $("monitor-out").innerHTML = "<p>Listening\u2026</p>"; },
      onUpdate: (state) => renderMonitor(state),
    });
    await monitor.start(group);
    renderSession();
    busy(null);
  } catch (e) {
    busy(null);
    banner($("monitor-out"), "bad", escapeHtml(String(e.message || e)));
  }
}

function renderMonitor(state) {
  const zones = manifest.monitor.zones;
  // Two different facts, deliberately shown separately. "Hearing now" is what
  // this spot can pick up at this moment and drops away as the fox moves off;
  // "confirmed" is integration_check.py's rule, which is about whether the fox
  // transmits all three beacons at all, and is cumulative on purpose.
  const now = zones.map((z) =>
    state.current.includes(z) ? `<strong>${z}</strong>` : `<span class="note">${z}</span>`).join(" ");
  const ever = zones.map((z) =>
    state.ever.includes(z) ? `<strong>${z}</strong>` : `<span class="note">${z}</span>`).join(" ");

  $("monitor-out").className = "card";
  $("monitor-out").innerHTML =
    `<dl class="kv">
       <dt>Hearing now</dt><dd>${state.live ? now : "<span class='note'>nothing</span>"}</dd>
       <dt>Signal</dt><dd>${state.rssi === null ? "<span class='note'>&mdash;</span>" : state.rssi + " dBm"}</dd>
       <dt>Confirmed</dt><dd>${ever}</dd>
       <dt>Packets</dt><dd>${state.count}</dd>
     </dl>` +
    monitorAdvice(state);
}

function monitorAdvice(state) {
  if (!state.live) {
    return state.count === 0
      ? `<p class="note">Nothing heard yet. Check the fox is powered up and that both boards are on group ${currentGroup()}.</p>`
      : `<p class="banner warn">No signal now &mdash; out of range, or the fox has stopped.</p>`;
  }
  const closest = state.current[state.current.length - 1];
  const near = closest === "Z3" ? "Very close to the fox."
    : closest === "Z2" ? "Getting warm."
      : "In range, but a long way off.";
  return `<p class="note">${near}</p>` +
    (state.ok
      ? `<p class="banner ok">All three zones confirmed &mdash; the fox is transmitting correctly.</p>`
      : `<p class="note">Not yet confirmed: ${state.missing.join(", ")}. Walk towards the fox to pick up the weaker beacons.</p>`);
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
    busy("Building the .hex\u2026");
    const image = flasher.buildImage(role, group);
    const blob = new Blob([image.hex], { type: "application/octet-stream" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `foxhunt-${role}-group${group}-microbitV2.hex`;
    a.click();
    URL.revokeObjectURL(url);
  } finally {
    busy(null);
    text(button, label);
    button.disabled = false;
  }
}

// --- session ---------------------------------------------------------------

const boardTally = () => tallyBoards(flasher.flashed);

function renderTally() {
  const { byGroup, boards } = boardTally();
  if (!boards) {
    show($("tally"), false);
    return;
  }
  const describe = (counts) => Object.entries(counts)
    .map(([role, n]) => `<strong>${n}</strong> ${manifest.roles[role].label}${n === 1 ? "" : "s"}`)
    .join(", ");
  // Grouped, so running two hunts at once reads correctly. A single line taken
  // from the currently selected group would misdescribe everything set up
  // before the group was changed.
  const lines = byGroup.map((g) =>
    `Group <strong>${g.group}</strong>: ${describe(g.counts)}` +
    (g.counts.fox ? "" : ' <span class="warn-text">&mdash; no Fox yet</span>'));
  $("tally").innerHTML = "Set up so far &mdash; " + lines.join(" &middot; ");
  show($("tally"), true);
}

function renderSession() {
  const { latest, boards } = boardTally();
  const body = $("session-table").querySelector("tbody");
  body.innerHTML = latest
    .map((f, i) => `<tr><td>${i + 1}<span class="note mono"> · ${(f.serialNumber || "?").slice(0, 8)}</span></td>` +
                   `<td>${manifest.roles[f.role].label}</td><td>${f.group}</td></tr>`)
    .join("");
  $("session-heading").textContent =
    boards === 1 ? "1 board set up" : `${boards} boards set up`;
  show($("session"), boards > 0);
  renderTally();
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// --- start -----------------------------------------------------------------

async function init() {
  busy("Loading\u2026");
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
  flasher.onStatus = busy;
  flasher.onUnplugged = () => {
    if (monitor) monitor.stop();
    busy(null);
    clearBoardUi(
      "<strong>That board was unplugged.</strong> Plug the next one in, then " +
      "press <em>Connect a micro:bit</em>.");
  };
  refreshGroup();

  $("connect").addEventListener("click", connect);
  $("forget").addEventListener("click", async () => {
    busy("Disconnecting\u2026");
    if (monitor) monitor.stop();
    await flasher.forget(true);
    busy(null);
    clearBoardUi();
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

  if (webUsbAvailable()) $("connect").disabled = false;
  busy(null);
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
