"""Reliably flash a micro:bit. Hardware tool, not a test.

Normally driven by the Makefile (`make flash-fox`, `make flash-hound`).

Why this exists rather than a plain `ufs put`:

* `ufs` always picks the first board it finds and cannot target one of two.
* These boards have DAPLink `Auto Reset: 1`, so opening or closing the serial
  port reboots them. A board that reboots mid-transfer starts executing a
  half-written `main.py`, which corrupts the rest of the copy -- observed in
  practice, with `ufs put` reporting success while the on-device file differed
  from the source.

So: halt the running program, delete `main.py` so the board boots idle, copy
each file, verify it by hash, and write `main.py` last.
"""
import argparse
import hashlib
import sys
import time

import microfs
import serial
import serial.tools.list_ports

BAUD = 115200
MICROBIT_VID, MICROBIT_PID = 0x0D28, 0x0204

# Newest micropython-microbit-v2 release at the time of writing (checked
# 2026-09-06). Only used to point out that a board is behind; update it or
# ignore the hint.
LATEST_MICROPYTHON = "2.1.2"

# Source file -> name on the device. main.py must come last: it is the entry
# point, so nothing should be runnable until every dependency is in place.
ROLES = {
    "fox": [
        ("radio_config.py", "radio_config.py"),
        ("fox.py", "main.py"),
    ],
    "hound": [
        ("radio_config.py", "radio_config.py"),
        ("hound_logic.py", "hound_logic.py"),
        ("hound.py", "main.py"),
    ],
}


def find_microbits():
    return [
        (p.device, p.serial_number)
        for p in serial.tools.list_ports.comports()
        if p.vid == MICROBIT_VID and p.pid == MICROBIT_PID
    ]


def pick_port(explicit):
    if explicit:
        return explicit
    boards = find_microbits()
    if not boards:
        sys.exit("No micro:bit found on USB.")
    if len(boards) > 1:
        lines = ["More than one micro:bit is attached; choose one with PORT=<port>:"]
        lines += ["  %s  (serial %s)" % (d, s) for d, s in boards]
        sys.exit("\n".join(lines))
    return boards[0][0]


def parse_version(text):
    """Comparable tuple (major, minor, patch, is_release).

    The trailing flag makes a pre-release sort *below* its final release, which
    plain tuple comparison would otherwise get backwards: '2.1.0-beta.1' has
    more components than '2.1.0' and so would compare greater.
    """
    core, _, prerelease = text.partition("-")
    parts = []
    for chunk in core.split("."):
        digits = ""
        for ch in chunk:
            if not ch.isdigit():
                break
            digits += ch
        parts.append(int(digits) if digits else 0)
    parts = (parts + [0, 0, 0])[:3]
    return tuple(parts) + (0 if prerelease else 1,)


def board_generation(machine):
    """v1 boards use an nRF51, v2 an nRF52. Flashing a v2 with `uflash`
    silently downgrades it to v1 firmware and disables the speaker, so this is
    worth surfacing."""
    if not machine:
        return "?"
    if "nRF52" in machine:
        return "v2"
    if "nRF51" in machine:
        return "v1"
    return "?"


def describe_firmware(release, machine):
    if release is None:
        return "firmware unknown (board busy?)"
    generation = board_generation(machine)
    text = "micro:bit %s  MicroPython %s" % (generation, release)
    if generation == "v1":
        text += "  ** v1 firmware: no speaker. Likely a uflash downgrade; reflash with a v2 hex **"
    elif parse_version(release) < parse_version(LATEST_MICROPYTHON):
        text += "  (%s available)" % LATEST_MICROPYTHON
    return text


def board_info(port):
    """Ask a board which firmware it runs.

    This briefly interrupts whatever main.py is doing. The board reboots and
    resumes on its own afterwards.
    """
    def query(handle):
        handle.write(b"\r\x03\x03")
        time.sleep(0.2)
        handle.reset_input_buffer()
        out, err = microfs.execute(
            ["import os", "_u = os.uname()", "print(_u.release)", "print(_u.machine)"],
            handle,
        )
        if err:
            raise RuntimeError(err.decode("utf-8", "replace"))
        return out.decode("utf-8", "replace")

    try:
        lines = [l.strip() for l in _session(port, query, tries=3).splitlines() if l.strip()]
    except Exception:  # noqa: BLE001 - a busy board should not break the listing
        return None, None
    release = lines[0] if lines else None
    machine = lines[1] if len(lines) > 1 else None
    return release, machine


def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:12]


def _session(port, fn, tries=6, delay=0.8):
    """Run fn(serial) with retries; raw-REPL entry is flaky when the board
    auto-resets underneath us."""
    last = None
    for attempt in range(tries):
        s = serial.Serial(port, BAUD, timeout=1, parity="N")
        try:
            return fn(s)
        except Exception as exc:  # noqa: BLE001 - retry any transport failure
            last = exc
            time.sleep(delay * (attempt + 1))
        finally:
            s.close()
            time.sleep(0.3)
    raise last


def halt(port):
    """Interrupt whatever main.py is doing so it cannot disturb a transfer."""
    s = serial.Serial(port, BAUD, timeout=1, parity="N")
    try:
        for _ in range(4):
            s.write(b"\r\x03")
            time.sleep(0.15)
        s.reset_input_buffer()
    finally:
        s.close()
        time.sleep(0.3)


def remove_main(port):
    try:
        _session(port, lambda s: microfs.rm("main.py", s))
        return True
    except Exception:
        return False  # nothing to remove is fine


def verified_put(port, src, target, tries=6):
    want = sha(src)
    check = ".flash_verify.tmp"
    for attempt in range(1, tries + 1):
        halt(port)
        try:
            _session(port, lambda s: microfs.put(src, target, s))
            time.sleep(0.4)
            _session(port, lambda s: microfs.get(target, check, s))
            if sha(check) == want:
                print("  %-18s %s  ok" % (target, want))
                return True
            print("  %-18s attempt %d: content mismatch, retrying" % (target, attempt))
        except Exception as exc:  # noqa: BLE001
            print("  %-18s attempt %d: %s, retrying" % (target, attempt, type(exc).__name__))
    return False


def boot_check(port, seconds=5.0):
    """Reset and watch for a traceback from main.py."""
    s = serial.Serial(port, BAUD, timeout=1, parity="N")
    try:
        s.write(b"\r\x03\x03")
        time.sleep(0.3)
        s.reset_input_buffer()
        s.write(b"\x04")  # soft reboot -> run main.py
        deadline = time.time() + seconds
        buf = b""
        while time.time() < deadline:
            n = s.in_waiting
            buf += s.read(n if n else 1)
    finally:
        s.close()
    out = buf.decode("utf-8", "replace")
    if "Traceback" in out or "Error" in out:
        print(out.strip())
        return False
    return True


def flash(role, port):
    files = ROLES[role]
    print("Flashing %s to %s" % (role, port))
    halt(port)
    remove_main(port)  # boot idle so nothing runs mid-transfer
    for src, target in files:
        if not verified_put(port, src, target):
            sys.exit("FAILED: could not write %s reliably." % target)
    if not boot_check(port):
        sys.exit("FAILED: %s does not start cleanly." % role)
    print("%s flashed and running." % role)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("role", choices=sorted(ROLES) + ["list"])
    ap.add_argument("--port", help="serial port; required when two boards are attached")
    args = ap.parse_args()

    if args.role == "list":
        boards = find_microbits()
        if not boards:
            print("No micro:bit found on USB.")
            return 1
        for device, serial_number in boards:
            release, machine = board_info(device)
            print("%s  %s" % (device, describe_firmware(release, machine)))
            print("    serial %s" % serial_number)
        return 0

    flash(args.role, pick_port(args.port))
    return 0


if __name__ == "__main__":
    sys.exit(main())
