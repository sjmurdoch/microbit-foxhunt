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
 */
import { monitorVerdict, parseMonitorLine } from "./device.js";

export class Monitor {
  constructor(flasher, handlers) {
    this.flasher = flasher;
    this.handlers = handlers;
    this.running = false;
    this.heard = [];
    this.samples = [];
  }

  async start(group, onProgress) {
    const result = await this.flasher.flashRole("integration", group, onProgress);
    this.heard = [];
    this.samples = [];
    this.running = true;
    this.flasher.serial.clear();
    this.loop();
    return result;
  }

  async loop() {
    const zones = this.flasher.manifest.monitor.zones;
    let carry = "";
    while (this.running) {
      const chunk = this.flasher.serial.buf;
      this.flasher.serial.buf = "";
      if (chunk) {
        const lines = (carry + chunk).split(/\r?\n/);
        carry = lines.pop();
        for (const line of lines) this.consume(line, zones);
      }
      await new Promise((r) => setTimeout(r, 120));
    }
  }

  consume(line, zones) {
    if (line.includes(this.flasher.manifest.monitor.start)) {
      this.handlers.onStart && this.handlers.onStart();
      return;
    }
    const sample = parseMonitorLine(line, zones);
    if (!sample) return;
    this.samples.push(sample);
    if (sample.zone && !this.heard.includes(sample.zone)) this.heard.push(sample.zone);
    this.handlers.onSample && this.handlers.onSample(sample, this.verdict());
  }

  verdict() {
    return {
      ...monitorVerdict(this.heard, this.flasher.manifest.monitor.zones),
      heard: [...this.heard],
      count: this.samples.length,
      // A rough range reading. The hound smooths this with an EMA; here it is
      // raw, because the question the organiser is asking is "is the fox alive
      // and can this spot hear it", not "how far away is it".
      lastRssi: this.samples.length ? this.samples[this.samples.length - 1].rssi : null,
    };
  }

  stop() {
    this.running = false;
  }
}
