/**
 * WebUSB connection, board identification and flashing.
 *
 * Unlike flash.py, this writes *firmware* as well as files: the image is
 * MicroPython plus the filesystem, flashed as one hex. Two things follow.
 *
 * The good one: the entire `ufs put` failure class disappears. flash.py halts
 * the board, deletes main.py, copies each file, verifies it by hash and writes
 * main.py last, all because a board that reboots mid-transfer corrupts the
 * copy. None of that applies to an atomic image, so the ROLES *ordering* is
 * irrelevant here even though the mapping is not.
 *
 * The bad one: it pins the MicroPython version, and can silently move a board
 * off a newer release onto ours. That is the same shape of harm as the uflash
 * trap, so the page reads the board's version first and says what it is about
 * to do.
 */
import { createUSBConnection } from "@microbit/microbit-connection/usb";
import { MicropythonFsHex, microbitBoardId } from "@microbit/microbit-fs";

import { SerialLink, SURVEY_SNIPPET, parseSurvey } from "./serial.js";
import {
  bootVerdict,
  digestText,
  flashForecast,
  groupFromConfig,
  isStaleDevice,
  parseDigests,
  renderRadioConfig,
  roleFromMain,
} from "./device.js";

// microbit-connection's ProgressStage values, in words an organiser can read.
const CONNECT_STAGES = {
  Initializing: "Checking the browser can talk to USB\u2026",
  FindingDevice: "Looking for a micro:bit\u2026",
  Connecting: "Opening the board\u2026",
};

export class BoardRefused extends Error {
  constructor(kind, message) {
    super(message);
    this.kind = kind;
  }
}

export class Flasher {
  constructor(manifest, sources) {
    this.manifest = manifest;
    this.sources = sources;
    // pauseOnHidden defaults to true, which pauses the USB connection when the
    // tab is hidden and disconnects instead of resetting after a flash. A
    // 23-second flash must survive someone glancing at another window.
    this.usb = createUSBConnection({ pauseOnHidden: false });
    this.serial = new SerialLink(this.usb);
    this.flashed = [];
    this.attached = false;
    // Benign background errors are normal around connect and disconnect --
    // "No device opened" and "USB read failed" were both seen without anything
    // actually failing. They are logged, never surfaced as a failure.
    this.usb.addEventListener("backgrounderror", (e) => {
      console.warn("[foxhunt] background:", e && e.error && e.error.message);
    });
    // The device chooser is a native dialog and can sit open indefinitely.
    // Without these the page looks frozen for as long as the user takes.
    this.usb.addEventListener("beforerequestdevice", () =>
      this.status("Choose your micro:bit in the browser's dialog\u2026"));
    this.usb.addEventListener("afterrequestdevice", () =>
      this.status("Opening the board\u2026"));

    // Unplugging is a normal thing to do between boards, and the page has to
    // notice rather than keep showing a board that is not there any more.
    if (typeof navigator !== "undefined" && navigator.usb && navigator.usb.addEventListener) {
      navigator.usb.addEventListener("disconnect", () => {
        if (!this.attached) return;
        this.attached = false;
        if (this.onUnplugged) this.onUnplugged();
      });
    }
  }

  /** Where progress messages go. Replaced by the UI; harmless by default. */
  status(message) {
    if (this.onStatus) this.onStatus(message);
  }

  /**
   * Connect, and decide whether we will touch this board at all.
   *
   * Three outcomes, not two. microbit-connection derives the version from the
   * first four characters of the USB serial number, which is burned into the
   * DAPLink chip: 9900/9901 are V1, 9903-9906 are V2, and anything else makes
   * its BoardId constructor throw before a version exists. Treating that third
   * case as "this is a v1 board" would be wrong and unhelpful.
   */
  async connect({ chooseAgain = false } = {}) {
    this.status("Looking for a micro:bit\u2026");
    // "Connect a different micro:bit" means exactly that: drop the remembered
    // board so the picker comes up, whether or not it is still plugged in.
    if (chooseAgain) await this.release();

    const open = () => this.usb.connect({
      progress: (stage) => this.status(CONNECT_STAGES[stage] || "Connecting\u2026"),
    });

    try {
      try {
        await open();
      } catch (e) {
        if (!isStaleDevice(e)) throw e;
        // The remembered board has gone. Forget it and ask for another.
        this.status("That board was unplugged \u2014 choose another\u2026");
        await this.release();
        await open();
      }
    } catch (e) {
      const message = String((e && e.message) || e);
      if (/Could not recognise the Board ID/i.test(message)) {
        throw new BoardRefused(
          "unrecognised",
          "This micro:bit is newer than this flasher knows about. Update the " +
            "flasher rather than the board.");
      }
      if (e && e.code === "firmware-update-required") {
        throw new BoardRefused(
          "old-daplink",
          "This board's DAPLink firmware is too old for WebUSB (0249 or newer " +
            "is needed). Update it, or use the .hex download instead.");
      }
      throw e;
    }

    const device = this.usb.getDevice();
    const serialNumber = (device && device.serialNumber) || null;
    const version = this.usb.getBoardVersion();
    this.attached = true;

    if (version !== "V2") {
      await this.release();
      throw new BoardRefused(
        "v1",
        "This is a micro:bit V1. The fox hunt needs a V2: V1 has no speaker, " +
          "and on V1 radio.config(power=) resets the radio group, which the " +
          "fox changes three times a second.");
    }
    return { version, serialNumber, boardId: serialNumber ? serialNumber.slice(0, 4) : null };
  }

  /** Ask a board what it is currently running. Interrupts the program. */
  async survey() {
    this.status("Pausing the program on the board\u2026");
    await this.serial.interrupt();
    this.status("Reading what is on the board\u2026");
    const text = await this.serial.rawExec(SURVEY_SNIPPET);
    const info = parseSurvey(text);
    const digests = parseDigests(text);

    const entries = {};
    for (const [role, spec] of Object.entries(this.manifest.roles)) {
      entries[role] = digestText(this.sources[spec.entry]);
    }
    const role = digests["main.py"] ? roleFromMain(digests["main.py"], entries) : null;
    const group = info.config ? groupFromConfig(info.config) : null;

    return {
      ...info,
      digests,
      role,
      group,
      matchesSite: role !== null && this.codeMatches(role, digests, group),
      forecast: flashForecast(info.release, this.manifest.micropython.version),
    };
  }

  /** Do the board's digests match what this site would write for that role? */
  codeMatches(role, digests, group) {
    for (const [src, target] of this.manifest.roles[role].files) {
      const text = src === "radio_config.py"
        ? (group === null ? null : this.renderConfig(group))
        : this.sources[src];
      if (text === null || digests[target] !== digestText(text)) return false;
    }
    return true;
  }

  renderConfig(group) {
    return renderRadioConfig(this.sources["radio_config.py"], group, this.manifest.group);
  }

  /** Build the hex for a role. Never keeps the result: it is ~1.3 MB. */
  buildImage(role, group) {
    const fsHex = new MicropythonFsHex([
      { hex: this.sources.__micropython, boardId: microbitBoardId.V2 },
    ]);
    const want = {};
    for (const [src, target] of this.manifest.roles[role].files) {
      const text = src === "radio_config.py" ? this.renderConfig(group) : this.sources[src];
      fsHex.write(target, text);
      want[target] = digestText(text);
    }
    return {
      hex: fsHex.getIntelHex(microbitBoardId.V2),
      want,
      used: fsHex.getStorageUsed(),
      free: fsHex.getStorageRemaining(),
    };
  }

  async flashRole(role, group, onProgress) {
    const image = this.buildImage(role, group);
    let stage = null;
    const started = performance.now();
    await this.usb.flash(
      async (boardVersion) => {
        if (boardVersion !== "V2") {
          throw new BoardRefused("v1", "refusing to flash a " + boardVersion + " board");
        }
        return image.hex;
      },
      {
        partial: true,
        progress: (s, fraction) => {
          if (s === "PartialFlashing" || s === "FullFlashing") stage = s;
          if (onProgress) onProgress(s, fraction);
        },
      },
    );
    const seconds = (performance.now() - started) / 1000;

    const device = this.usb.getDevice();
    this.flashed.push({
      serialNumber: (device && device.serialNumber) || null,
      role,
      group,
      at: new Date().toISOString(),
    });
    return { stage, seconds, image };
  }

  /**
   * Did it start?
   *
   * The library resets the target after flashing and starts serial first so the
   * startup output is captured, so there is no need for flash.py's "was the
   * board really reset?" arm. fox.py and hound.py print nothing when healthy,
   * so an empty capture is the success case -- and the REPL banner is a
   * failure, because it means main.py is missing or returned.
   */
  async bootCheck(seconds = 3, expect = null) {
    const text = await this.serial.collect(seconds * 1000);
    return bootVerdict(text, expect);
  }

  /** Read the filesystem back and confirm it is what we meant to write. */
  async verify(want) {
    this.status("Reading the files back off the board\u2026");
    await this.serial.interrupt();
    const text = await this.serial.rawExec(SURVEY_SNIPPET);
    const got = parseDigests(text);
    const rows = Object.entries(want).map(([target, digest]) => ({
      target,
      want: digest,
      got: got[target],
      ok: got[target] === digest,
    }));
    return { ok: rows.every((r) => r.ok), rows };
  }

  /**
   * A group mismatch is silent on the air, so make it loud here.
   *
   * AGENTS.md section 5: changing the group means reflashing both boards, and
   * the symptom is a hound that simply never hears anything. A picker that is
   * easy to change between boards invites exactly that.
   */
  groupWarning(group) {
    const others = this.flashed.filter((f) => f.group !== group);
    if (!others.length) return null;
    const seen = [...new Set(others.map((f) => f.group))].sort((a, b) => a - b);
    return `You have already flashed ${others.length} board(s) on group ${seen.join(", ")}. ` +
      `Boards on different groups cannot hear each other, and the only symptom is silence.`;
  }

  async reset() {
    this.status("Restarting the board\u2026");
    await this.serial.reset();
  }

  /**
   * Drop the current device so the next connect() shows the picker.
   *
   * Both calls are wrapped: if the board has already been unplugged, tearing
   * down the connection is exactly the operation that throws, and failing here
   * would strand the page on a board that no longer exists.
   */
  async release() {
    this.attached = false;
    try {
      await this.usb.disconnect();
    } catch (e) {
      /* already gone */
    }
    try {
      await this.usb.clearDevice();
    } catch (e) {
      /* already gone */
    }
  }

  /** Finish with this board, and stop the picker offering it again. */
  async forget(exclude = false) {
    if (exclude) {
      const filters = this.flashed
        .map((f) => f.serialNumber)
        .filter(Boolean)
        .map((serialNumber) => ({ serialNumber }));
      if (filters.length) this.usb.setRequestDeviceExclusionFilters(filters);
    }
    await this.release();
  }

  clearExclusions() {
    this.usb.setRequestDeviceExclusionFilters([]);
  }
}

export function webUsbAvailable() {
  return typeof navigator !== "undefined" && !!navigator.usb;
}
