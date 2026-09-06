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
import re
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

# What the board prints when it is sitting at the REPL rather than running
# main.py. MicroPython emits the banner and prompt after main.py returns or
# raises, so seeing either means the program is not running.
REPL_MARKERS = (">>> ", 'Type "help()"')

# Some failures print an exception without a traceback header.
ERROR_RE = re.compile(r"^\w*(Error|Exception):", re.M)

# Typed at the REPL to reboot the board. Everything up to the echo of it is the
# host's own conversation with the REPL, not output from the program.
RESET_ECHO = "microbit.reset()"
RESET_CMD = b"import microbit\r" + RESET_ECHO.encode() + b"\r"

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
    # A stripped hound that prints what it hears, for integration_check.py.
    # Without an entry here there is no supported way to get it onto a board.
    "integration": [
        ("radio_config.py", "radio_config.py"),
        ("hound_integration.py", "main.py"),
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
    auto-resets underneath us.

    Opening the port is inside the retry, not before it: closing the port
    reboots the board, so the tty can still be gone when the next attempt comes
    round. That is precisely the transient this function exists to absorb, and
    letting it escape would abort a flash on the first try.
    """
    last = None
    for attempt in range(tries):
        s = None
        try:
            s = serial.Serial(port, BAUD, timeout=1, parity="N")
            return fn(s)
        except Exception as exc:  # noqa: BLE001 - retry any transport failure
            last = exc
            time.sleep(delay * (attempt + 1))
        finally:
            if s is not None:
                s.close()
            time.sleep(0.3)
    raise last


def halt(port, tries=3):
    """Interrupt whatever main.py is doing so it cannot disturb a transfer.

    Deliberately never raises: a board that will not be interrupted is
    verified_put's problem, and it retries the whole write. Going through
    _session keeps the port open inside the retry.
    """
    def interrupt(handle):
        for _ in range(4):
            handle.write(b"\r\x03")
            time.sleep(0.15)
        handle.reset_input_buffer()

    try:
        _session(port, interrupt, tries=tries)
    except Exception:  # noqa: BLE001 - best effort
        pass


def remove_main(port):
    """Delete main.py so the board boots idle.

    Returns True only when main.py is known to be gone. A failed rm is
    ambiguous: there may simply have been no main.py, or the board may be busy
    running one. Those are very different -- the second is exactly the
    reboot-mid-transfer case this module exists to prevent -- so ask the board
    rather than assuming the benign reading.
    """
    try:
        _session(port, lambda s: microfs.rm("main.py", s))
        return True
    except Exception:  # noqa: BLE001 - may just mean there was nothing to remove
        pass
    try:
        return "main.py" not in _session(port, lambda s: microfs.ls(s))
    except Exception:  # noqa: BLE001 - board unreachable; assume the worst
        return False


def verified_put(port, src, target, tries=6):
    want = sha(src)
    check = ".flash_verify.tmp"
    for attempt in range(1, tries + 1):
        try:
            halt(port)
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


def _read_for(handle, seconds, stop=None):
    deadline = time.time() + seconds
    buf = b""
    while time.time() < deadline:
        n = handle.in_waiting
        buf += handle.read(n if n else 1)
        if stop and stop in buf:
            break
    return buf.decode("utf-8", "replace")


def _hard_reset(handle):
    """Reboot the board in hardware, and confirm the command got through.

    Opening the port is meant to do this on its own -- these boards report
    DAPLink `Auto Reset: 1` -- but it does not always. Measured here: the first
    open after another process had held the port left the board exactly where
    it was, sitting at the REPL, while the opens after it did reset. A boot
    check that examines a board which never rebooted is worse than no check at
    all, so ask MicroPython to reset itself instead.

    This must NOT be a Ctrl-D soft reboot; see boot_check. microbit.reset() is
    a real hardware reset, which is the clean one.

    Returns the raw output, or None if the board never answered.
    """
    for _ in range(4):
        handle.write(b"\r\x03")
        time.sleep(0.15)
    handle.reset_input_buffer()
    handle.write(RESET_CMD)
    out = _read_for(handle, 3.0, stop=RESET_ECHO.encode())
    return out if RESET_ECHO in out else None


def boot_check(port, seconds=5.0, expect=None):
    """Reset the board and check that main.py is actually running.

    Do NOT soft reboot with Ctrl-D. Soft-rebooting a program that has used the
    radio corrupts the heap -- the peripheral stays live across the reboot
    while MicroPython reinitialises memory underneath it -- and the corruption
    surfaces as tracebacks from a file that is byte-for-byte correct on the
    device: IndentationError at a different line each time, SyntaxError on
    valid code, or an impossible MemoryError. Measured on v2.1.2: hound.py
    failed 5/5 soft reboots, a radio-only script 1/5, a script that never calls
    radio.on() 0/5, and hound.py 0/14 on a hardware reset. See AGENTS.md
    gotcha 10.

    Three things can go wrong, and silence tells them apart from a healthy
    board only once the reset is known to have happened -- fox.py and hound.py
    print nothing at all when they are working:

    * main.py raised: there is a traceback.
    * main.py is missing, or returned, so the board fell through to the REPL.
      MicroPython prints its banner and prompt then, which is why REPL_MARKERS
      is a failure rather than a curiosity.
    * the board is wedged, or never rebooted: it does not answer _hard_reset.

    `expect` names a string the program must print -- the calibration logger
    prints CAL_READY -- which makes the whole thing a positive check.
    """
    s = serial.Serial(port, BAUD, timeout=1, parity="N")
    try:
        if _hard_reset(s) is None:
            print("  the board did not answer at the REPL, so it was never reset.")
            return False
        out = _read_for(s, seconds)
    finally:
        s.close()
        time.sleep(0.3)

    if "Traceback" in out or ERROR_RE.search(out):
        print(out.strip())
        return False
    for marker in REPL_MARKERS:
        if marker in out:
            print("  the board is at the REPL, so main.py is not running:")
            print(out.strip())
            return False
    if expect is not None and expect not in out:
        print("  expected %r from the board; got %r" % (expect, out.strip()))
        return False
    return True


def flash(role, port):
    files = ROLES[role]
    print("Flashing %s to %s" % (role, port))
    halt(port)
    if not remove_main(port):  # boot idle so nothing runs mid-transfer
        print("  warning: could not confirm main.py is gone. If the board is")
        print("           still running it, a reboot mid-transfer can corrupt")
        print("           the copy -- the hash check below is the backstop.")
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
