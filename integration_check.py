"""Hardware integration check - NOT a unit test.

Needs two micro:bits on USB: the fox (`make flash-fox`) and a board running
hound_integration.py (`make flash-integration`), which is a stripped hound that
prints what it hears instead of beeping.

Run by hand:  make integration
"""
import sys
import time

import serial

from flash import BAUD, find_microbits

LISTEN_SECONDS = 5
ZONES = ("Z1", "Z2", "Z3")


def main():
    boards = find_microbits()
    if len(boards) < 2:
        # One board is not "nearly there": with only the fox attached this
        # would listen to silence and then blame the radio.
        print("Need two micro:bits on USB, the fox and the hound. Found %d:" % len(boards))
        for device, serial_number in boards:
            print("  %s  (serial %s)" % (device, serial_number))
        print("Flash them with 'make flash-fox' and 'make flash-integration'.")
        return 1

    # Opening a port reboots the board (AGENTS.md section 5), so both restart
    # here and the fox begins its cycle from the top.
    handles = [serial.Serial(device, BAUD, timeout=0.5) for device, _ in boards]
    heard = set()
    try:
        print("Listening %ds for the fox's beacons..." % LISTEN_SECONDS)
        deadline = time.time() + LISTEN_SECONDS
        while time.time() < deadline and len(heard) < len(ZONES):
            for handle in handles:
                try:
                    line = handle.readline().decode("utf-8", "replace").strip()
                except serial.SerialException as exc:
                    # A port that has gone away will never come back within the
                    # window, and silently retrying it just burns the clock.
                    print("%s: %s" % (handle.port, exc))
                    return 1
                if not line:
                    continue
                print("[%s] %s" % (handle.port, line))
                heard.update(z for z in ZONES if z in line)
    finally:
        for handle in handles:
            handle.close()

    if len(heard) == len(ZONES):
        print("PASS: heard all three zones.")
        return 0
    print("FAIL: heard %s, missing %s."
          % (sorted(heard) or "nothing", sorted(set(ZONES) - heard)))
    return 1


if __name__ == "__main__":
    sys.exit(main())
