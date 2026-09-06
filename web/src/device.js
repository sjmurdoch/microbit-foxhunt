/**
 * Pure helpers for the fox hunt web flasher.
 *
 * No DOM, no USB, no fetch -- everything here runs under node, and test_site.py
 * runs it there and compares the results against the Python implementations and
 * against digests measured on a real board. That matters most for
 * `deviceDigest`: the same arithmetic exists in build_site.py and, as a
 * MicroPython snippet, on the micro:bit itself. Three copies that must agree,
 * so all three are pinned by tests.
 *
 * Same reasoning as hound_logic.py: pull the pure part out of anything that
 * needs hardware, or the arithmetic never gets tested.
 */

/** Fingerprint one file exactly as the board does. */
export function deviceDigest(bytes) {
  let h = 0;
  for (const c of bytes) h = (h * 31 + c) >>> 0;
  return h >>> 0;
}

export function digestText(text) {
  return deviceDigest(new TextEncoder().encode(text));
}

/**
 * radio_config.py with the organiser's group substituted.
 *
 * A single literal replace, matching build_site.render_radio_config, because
 * the fox and the hound stop hearing each other if these two disagree and the
 * symptom is silence (AGENTS.md section 5).
 */
export function renderRadioConfig(template, group, cfg) {
  const { placeholder, min, max, avoid } = cfg;
  if (!Number.isInteger(group)) throw new Error(`radio group must be a whole number, got ${group}`);
  if (group < min || group > max) throw new Error(`radio group ${group} is outside ${min}-${max}`);
  if (avoid.includes(group)) {
    throw new Error(`radio group ${group} invites collisions with other kit; pick another`);
  }
  if (!template.includes(placeholder)) throw new Error(`template has no ${placeholder}`);
  return template.split(placeholder).join(String(group));
}

/** Read the group back out of a radio_config.py taken off a board. */
export function groupFromConfig(text) {
  const m = text.match(/^RADIO_GROUP\s*=\s*(\d+)\s*$/m);
  return m ? Number(m[1]) : null;
}

// What the board prints when it is at the REPL rather than running main.py.
// Kept identical to flash.REPL_MARKERS: MicroPython emits the banner and prompt
// after main.py returns or raises, so either means the program is not running.
export const REPL_MARKERS = [">>> ", 'Type "help()"'];
const ERROR_RE = /^\w*(Error|Exception):/m;

/**
 * Did the program actually start?
 *
 * fox.py and hound.py print nothing at all when they are healthy, so silence is
 * simultaneously the success signal and the symptom of a dead board. This is
 * flash.py's boot_check, minus its "was the board really reset?" arm -- the
 * library resets the target itself after flashing and starts serial first so
 * the startup output is captured, which was measured on 2026-09-06.
 */
export function bootVerdict(text, expect) {
  if (/Traceback/.test(text) || ERROR_RE.test(text)) {
    return { ok: false, reason: "the program raised", detail: text.trim() };
  }
  for (const marker of REPL_MARKERS) {
    if (text.includes(marker)) {
      return { ok: false, reason: "the board is at the REPL, so main.py is not running", detail: text.trim() };
    }
  }
  if (expect && !text.includes(expect)) {
    return { ok: false, reason: `expected ${expect} from the board`, detail: text.trim() };
  }
  return { ok: true, reason: expect ? `announced ${expect}` : "running silently", detail: text.trim() };
}

/**
 * Take everything after the last sentinel.
 *
 * Measured 2026-09-06: a raw-REPL reply arrived with about 28 characters
 * missing from the front. Parsing positionally would have read that as a
 * different program. So the snippet prints a sentinel and we slice from it;
 * losing the sentinel itself is a failure we can see, rather than one we
 * silently misread.
 */
export function sliceAfterSentinel(text, sentinel) {
  const at = text.lastIndexOf(sentinel);
  return at === -1 ? null : text.slice(at + sentinel.length);
}

/** Parse `SUM <name> <digest>` lines out of a raw-REPL reply. */
export function parseDigests(text) {
  const out = {};
  for (const m of text.matchAll(/^SUM (\S+) (\d+)$/gm)) out[m[1]] = Number(m[2]);
  return out;
}

/**
 * Name the role by matching main.py against each role's entry point.
 *
 * Entry-point digests are group-independent, since radio_config.py is never
 * main.py. test_site.py asserts the three roles digest distinctly.
 */
export function roleFromMain(mainDigest, entryDigests) {
  for (const [role, digest] of Object.entries(entryDigests)) {
    if (digest === mainDigest) return role;
  }
  return null;
}

/**
 * One line of hound_integration.py's output.
 *
 * It prints the payload with %r because MicroPython's radio prepends a 3-byte
 * header and the result is not necessarily valid UTF-8 (AGENTS.md gotcha 1), so
 * the zone token is matched inside the repr rather than decoded.
 */
export function parseMonitorLine(line, zones) {
  const m = line.match(/HOUND_RX:\s*(.*?)\s*RSSI:\s*(-?\d+)/);
  if (!m) return null;
  const payload = m[1];
  const zone = zones.find((z) => payload.includes(z)) || null;
  return { payload, rssi: Number(m[2]), zone };
}

/** integration_check.py's pass rule: every zone heard. */
export function monitorVerdict(heard, zones) {
  const missing = zones.filter((z) => !heard.includes(z));
  return { ok: missing.length === 0, missing };
}

/**
 * Which flash path a board is in for, before it starts.
 *
 * Measured 2026-09-06: 22.7 s when the firmware differs, 1.4-2.5 s when it
 * matches. Worth telling the user which one they are about to get.
 */
export function flashForecast(boardRelease, bundled) {
  if (boardRelease === null || boardRelease === undefined) {
    return { full: true, seconds: 25, why: "the board's firmware is unknown" };
  }
  if (boardRelease !== bundled) {
    return { full: true, seconds: 25, why: `the board runs MicroPython ${boardRelease}, not ${bundled}` };
  }
  return { full: false, seconds: 3, why: `the board already runs MicroPython ${bundled}` };
}

/**
 * Does this error mean the board we remembered is no longer there?
 *
 * microbit-connection defaults to DeviceSelectionMode.AlwaysAsk, which
 * "attempts to connect to known device, otherwise asks". Once a board has been
 * unplugged the cached USBDevice is still *known* but dead, so connecting fails
 * deep inside a USB transfer -- "Failed to execute 'transferOut' on
 * 'USBDevice': The device was disconnected" -- instead of falling through to
 * the picker. The cure is to forget the device and ask again, so this decides
 * when to do that.
 */
export function isStaleDevice(error) {
  if (!error) return false;
  if (error.code === "device-disconnected" || error.code === "connection-error") return true;
  return /device was disconnected|transfer(In|Out)|No device opened|device is not open/i
    .test(String(error.message || error));
}
