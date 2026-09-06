/**
 * Talking to MicroPython's REPL from the browser.
 *
 * Serial here is *not* the CDC port that flash.py uses. microbit-connection
 * carries it over DAPLink's CMSIS-DAP vendor commands 0x83/0x84, which has two
 * happy consequences: opening it does not auto-reset the board (AGENTS.md
 * section 5's `Auto Reset: 1` behaviour is a CDC property), and the connection
 * survives a flash. Everything below was measured on a v2 board running 2.1.2
 * on 2026-09-06; the numbers are not guesses.
 *
 * The one thing to be careful about: Ctrl-D *inside the raw REPL* means
 * "execute the block", and is completely unrelated to Ctrl-D at the friendly
 * prompt, which soft-reboots and -- after the radio has run -- corrupts the
 * heap (AGENTS.md gotcha 10). This module never sends the latter. To reboot, it
 * asks for a real hardware reset with microbit.reset(), exactly as
 * flash.py:_hard_reset does.
 */
import { sliceAfterSentinel } from "./device.js";

// DAPLink's serial write carries a single length byte, so a write cannot exceed
// 255 bytes. 32 with a short gap was lossless across 20 consecutive runs.
export const WRITE_CHUNK = 32;
export const WRITE_GAP_MS = 15;

// Printed by every snippet before its payload. Leading output can be *lost*,
// not merely stale -- one measured reply was missing 28 characters from the
// front -- so nothing is ever parsed positionally.
export const SENTINEL = "--FOXHUNT--";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export class ReplError extends Error {}

export class SerialLink {
  constructor(usb) {
    this.usb = usb;
    this.buf = "";
    // Attached in the constructor, before anything can call flash(). The
    // library only saturates DAPLink's CDC buffers when a serialdata listener
    // already exists, and without that the post-flash startup output is
    // consumed by the CDC side and never reaches us -- silence that looks
    // exactly like a healthy fox.
    usb.addEventListener("serialdata", (d) => {
      this.buf += d && d.data !== undefined ? d.data : String(d);
    });
  }

  clear() {
    this.buf = "";
  }

  /** Let the line go quiet, then discard whatever was already buffered.
   *
   * The first read after connecting can contain stale ring-buffer bytes from
   * whatever ran before. flash.py calls reset_input_buffer() for the same
   * reason. */
  async settle(ms = 400) {
    await sleep(ms);
    this.buf = "";
  }

  async write(text) {
    for (let i = 0; i < text.length; i += WRITE_CHUNK) {
      await this.usb.serialWrite(text.slice(i, i + WRITE_CHUNK));
      await sleep(WRITE_GAP_MS);
    }
  }

  async waitFor(predicate, timeoutMs) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      if (predicate(this.buf)) return { ok: true, text: this.buf };
      await sleep(40);
    }
    return { ok: false, text: this.buf };
  }

  /** Collect everything that arrives over a fixed window. */
  async collect(ms) {
    this.buf = "";
    await sleep(ms);
    return this.buf;
  }

  /** Stop whatever main.py is doing and get a prompt. */
  async interrupt(timeoutMs = 3000) {
    await this.settle(200);
    await this.write("\r\x03\x03");
    const { ok, text } = await this.waitFor((b) => b.includes(">>>"), timeoutMs);
    if (!ok) throw new ReplError("the board did not answer at the REPL");
    return text;
  }

  /**
   * Run a block in the raw REPL and return everything after the sentinel.
   *
   * The caller's code must print SENTINEL before anything it wants back.
   */
  async rawExec(code, timeoutMs = 8000) {
    this.buf = "";
    await this.write("\x01");
    const entered = await this.waitFor((b) => b.includes("raw REPL"), 3000);
    if (!entered.ok) throw new ReplError("could not enter the raw REPL");

    this.buf = "";
    await this.write(`print(${JSON.stringify(SENTINEL)})\r` + code + "\r");
    await this.write("\x04");
    const done = await this.waitFor((b) => b.includes("\x04>"), timeoutMs);
    await this.write("\x02");
    await sleep(200);

    const payload = sliceAfterSentinel(done.text, SENTINEL);
    if (payload === null) {
      throw new ReplError("the board's reply did not contain the sentinel");
    }
    if (/Traceback|^\w*(Error|Exception):/m.test(payload)) {
      throw new ReplError("the board raised: " + payload.trim().slice(0, 200));
    }
    return payload;
  }

  /**
   * Reboot in hardware and confirm the command got through.
   *
   * Never Ctrl-D. flash.py measured hound.py failing 5 of 5 soft reboots with
   * bogus tracebacks after the radio had run, and 0 of 14 on a hardware reset.
   */
  async reset(timeoutMs = 3000) {
    this.buf = "";
    await this.write("\rimport microbit\rmicrobit.reset()\r");
    const { ok } = await this.waitFor((b) => b.includes("microbit.reset()"), timeoutMs);
    if (!ok) throw new ReplError("the board did not acknowledge the reset");
    await sleep(400);
    this.buf = "";
  }
}

/**
 * The snippet that surveys a board.
 *
 * Digests are computed *on the device* and only the results come back. Reading
 * the files themselves would push 12.9 KB of hex through DAPLink's 512-byte
 * ring buffer for no benefit. radio_config.py is the exception: it is 481 bytes
 * and its contents carry the radio group, which is the fact an organiser
 * actually needs, so it is printed in full.
 */
export const SURVEY_SNIPPET = [
  "import os",
  "print('UNAME', os.uname().release, '|', os.uname().machine)",
  "print('LS', os.listdir())",
  "for _n in os.listdir():",
  "    _f = open(_n, 'rb')",
  "    _h = 0",
  "    while True:",
  "        _b = _f.read(64)",
  "        if not _b: break",
  "        for _c in _b: _h = (_h * 31 + _c) & 0xFFFFFFFF",
  "    _f.close()",
  "    print('SUM', _n, _h)",
  "try:",
  "    _f = open('radio_config.py')",
  "    print('CFG_START')",
  "    print(_f.read())",
  "    print('CFG_END')",
  "    _f.close()",
  "except OSError:",
  "    print('CFG_MISSING')",
  "",
].join("\r");

export function parseSurvey(text) {
  const uname = text.match(/^UNAME (\S+) \| (.*)$/m);
  const ls = text.match(/^LS \[(.*)\]$/m);
  const cfg = text.match(/CFG_START\r?\n([\s\S]*?)\r?\nCFG_END/);
  return {
    release: uname ? uname[1] : null,
    machine: uname ? uname[2].trim() : null,
    files: ls
      ? ls[1].split(",").map((s) => s.trim().replace(/^'|'$/g, "")).filter(Boolean)
      : [],
    config: cfg ? cfg[1] : null,
  };
}
