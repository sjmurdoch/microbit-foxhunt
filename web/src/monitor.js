/**
 * The live radio monitor.
 *
 * Flashes the `integration` role -- hound_integration.py, a stripped hound that
 * prints what it hears instead of beeping -- and streams the result. It is the
 * browser's version of integration_check.py, and applies that tool's pass rule
 * rather than a second copy of it: all three zones heard.
 *
 * Better than the command-line version in one respect: integration_check.py
 * needs *both* boards on USB, so the fox has to sit on the desk. Here only the
 * listening board is tethered and the fox can be out on its battery, where it
 * will actually be.
 *
 * It replaces the game on the board it runs on. The CLI expects you to know
 * that; a page used by someone else has to say so, and offer to put it back.
 *
 * Two things it must get right, both learned the hard way elsewhere in this
 * project. Zones are *held*, not latched, or a fox heard once at 1 m still
 * reads as three zones from 20 m away. And the display is driven by a clock,
 * not by arriving packets -- otherwise it freezes on its last reading exactly
 * when the fox goes out of range, which is the moment it most needs to change.
 */
import { monitorState, parseMonitorLine } from "./device.js";

const TICK_MS = 150;

export class Monitor {
  constructor(flasher, handlers) {
    this.flasher = flasher;
    this.handlers = handlers;
    this.running = false;
    this.reset();
  }

  reset() {
    this.lastSeen = {};        // zone -> timestamp of its most recent packet
    this.everHeard = [];       // cumulative, for the integration_check pass rule
    this.lastPacketAt = null;
    this.lastRssi = null;
    this.count = 0;
    this.carry = "";
  }

  async start(group, onProgress) {
    const result = await this.flasher.flashRole("integration", group, onProgress);
    this.reset();
    this.running = true;
    this.flasher.serial.clear();
    this.loop();
    return result;
  }

  async loop() {
    const zones = this.flasher.manifest.monitor.zones;
    while (this.running) {
      const chunk = this.flasher.serial.buf;
      this.flasher.serial.buf = "";
      if (chunk) {
        const lines = (this.carry + chunk).split(/\r?\n/);
        this.carry = lines.pop();
        for (const line of lines) this.consume(line, zones);
      }
      // Emit every tick, packets or not: going quiet is information.
      this.emit();
      await new Promise((r) => setTimeout(r, TICK_MS));
    }
  }

  consume(line, zones) {
    if (line.includes(this.flasher.manifest.monitor.start)) {
      this.handlers.onStart && this.handlers.onStart();
      return;
    }
    const sample = parseMonitorLine(line, zones);
    if (!sample) return;
    const now = Date.now();
    this.count += 1;
    this.lastPacketAt = now;
    this.lastRssi = sample.rssi;
    if (sample.zone) {
      this.lastSeen[sample.zone] = now;
      if (!this.everHeard.includes(sample.zone)) this.everHeard.push(sample.zone);
    }
  }

  state(now = Date.now()) {
    const monitor = this.flasher.manifest.monitor;
    return monitorState(
      {
        lastSeen: this.lastSeen,
        everHeard: this.everHeard,
        lastPacketAt: this.lastPacketAt,
        lastRssi: this.lastRssi,
        count: this.count,
      },
      now,
      {
        zones: monitor.zones,
        holdMs: monitor.zone_hold_ms,
        timeoutMs: monitor.signal_timeout_ms,
      },
    );
  }

  emit() {
    this.handlers.onUpdate && this.handlers.onUpdate(this.state());
  }

  stop() {
    this.running = false;
  }
}
