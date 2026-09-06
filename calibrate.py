"""Field-calibrate MIN_RSSI / MAX_RSSI for the Hound. Hardware tool, not a test.

Run this OUTDOORS in the real playfield. Indoor propagation is not the same
curve -- see AGENTS.md section 4.

    uv run python calibrate.py --flash      # put the logger on the hound
    uv run python calibrate.py              # then walk the fox out

Keep the hound tethered to USB; carry the fox (on a battery) to each distance
you are prompted for.
"""
import argparse
import os
import re
import statistics
import sys
import time

import serial
import serial.tools.list_ports

from radio_config import RADIO_GROUP

BAUD = 115200
RECEIVER_FLOOR = -95      # nRF52833 bottoms out near -96 dBm
BAR_COUNT = 5

# Blank any attached ZIP LEDs first, exactly as fox.py and hound.py do. They
# power on in a random state (AGENTS.md gotcha 4), and a script that never
# claims pin0 leaves them holding it: a pixel was seen lit while this logger
# was running and dark under hound.py, which does blank the strip on boot.
LOGGER_SRC = '''from microbit import *
import radio
import neopixel
np = neopixel.NeoPixel(pin0, 5)
np.clear()
np.show()
radio.on()
radio.config(group=__GROUP__, queue=200, length=64)
print("CAL_READY")
n = 0
while True:
    p = radio.receive_full()
    if p:
        print("R|%r|%d" % (p[0], p[1]))
        n += 1
        display.set_pixel(2, 2, 9 if (n // 5) % 2 else 4)
    sleep(2)
'''.replace("__GROUP__", str(RADIO_GROUP))  # not %-format: the body contains %r/%d


def find_port():
    for p in serial.tools.list_ports.comports():
        if p.vid == 0x0D28 and p.pid == 0x0204:
            return p.device
    sys.exit("No micro:bit found on USB.")


def flash_logger(port):
    """Write the logger via the same hardened path as `make flash-*`.

    A plain `microfs.put` can report success while leaving a different file on
    the device -- see the comment at the top of flash.py.
    """
    from flash import boot_check, halt, remove_main, verified_put

    tmp = "_cal_logger.py"
    with open(tmp, "w") as fh:
        fh.write(LOGGER_SRC)
    try:
        halt(port)
        remove_main(port)
        if not verified_put(port, tmp, "main.py"):
            sys.exit("FAILED: could not write the logger reliably.")
        if not boot_check(port):
            sys.exit("FAILED: the logger does not start cleanly.")
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    print("")
    print("Logger is on %s and running." % port)
    print("This REPLACED the hound's main.py. When you have finished")
    print("calibrating, restore the game with:  make flash-hound")


def sample(port, seconds):
    """Collect RSSI per zone for `seconds`."""
    s = serial.Serial(port, BAUD, timeout=1, parity="N")
    zones = {1: [], 2: [], 3: []}
    try:
        s.reset_input_buffer()
        deadline = time.time() + seconds
        buf = b""
        while time.time() < deadline:
            n = s.in_waiting
            data = s.read(n if n else 1)
            if not data:
                continue
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                m = re.match(r"R\|(.+)\|(-?\d+)$", line.decode("utf-8", "replace").strip())
                if not m:
                    continue
                z = re.search(r"Z(\d)", m.group(1))
                if z:
                    zones[int(z.group(1))].append(int(m.group(2)))
    finally:
        s.close()
    return zones


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--flash", action="store_true", help="write the logger to the hound and exit")
    ap.add_argument("--port", help="serial port (default: autodetect)")
    ap.add_argument("--seconds", type=float, default=15.0, help="sample time per distance")
    args = ap.parse_args()

    port = args.port or find_port()
    if args.flash:
        flash_logger(port)
        return 0

    print("Calibrating on %s. Ctrl-C when done.\n" % port)
    readings = []
    try:
        while True:
            raw = input("Distance in metres (blank to finish): ").strip()
            if not raw:
                break
            distance = float(raw)
            print("  sampling %.0fs..." % args.seconds)
            zones = sample(port, args.seconds)
            if not zones[1]:
                print("  !! no Z1 packets - out of range or logger not running")
                continue
            median = statistics.median(zones[1])
            readings.append((distance, median))
            print("  %.1f m : Z1 %.1f dBm  (Z1 %d, Z2 %d, Z3 %d packets)\n"
                  % (distance, median, len(zones[1]), len(zones[2]), len(zones[3])))
    except (KeyboardInterrupt, EOFError):
        print()

    if len(readings) < 2:
        print("Need at least two distances to calibrate.")
        return 1

    readings.sort()
    print("\n--- measured ---")
    for d, r in readings:
        print("  %6.1f m : %7.1f dBm" % (d, r))

    nearest, strongest = readings[0]
    furthest = readings[-1][0]
    # The weakest signal is not always the furthest one: a ground-reflection
    # null can leave a mid-range distance quieter than the far edge. Take the
    # real minimum, or everything at the null reads below the bottom bar.
    weakest_at, weakest = min(readings, key=lambda dr: dr[1])

    max_rssi = int(round(strongest))
    min_rssi = max(int(round(weakest)), RECEIVER_FLOOR)

    span = max_rssi - min_rssi
    if span < BAR_COUNT:
        print("\nSignal range is only %d dB - too small to drive %d bars. "
              "Sample a wider spread of distances." % (span, BAR_COUNT))
        return 1

    # Round the span to a whole number of bars so ATTEN_STEP divides exactly.
    # Rounding up drops MIN_RSSI below the weakest reading, which can undo the
    # receiver-floor clamp above, so round down in that case instead.
    step = -(-span // BAR_COUNT)
    if max_rssi - step * BAR_COUNT < RECEIVER_FLOOR:
        step = span // BAR_COUNT
    min_rssi = max_rssi - step * BAR_COUNT

    print("\n--- put these in hound_logic.py ---")
    print("MIN_RSSI = %d      # weakest signal, measured at %.1f m" % (min_rssi, weakest_at))
    print("MAX_RSSI = %d      # saturates at %.1f m, where the attenuator takes over" % (max_rssi, nearest))
    print("\n(ATTEN_STEP derives from these automatically: %d dB = exactly one bar.)" % step)
    if weakest_at != furthest:
        print("\nNote: the weakest signal was at %.1f m, not at the far edge (%.1f m). That\n"
              "is usually a ground-reflection null rather than a bad reading: at 2.4 GHz\n"
              "the first null falls near 2*h1*h2/0.125 m, so about 16 m with both units a\n"
              "metre up. Re-measure %.1f m with the fox raised or lowered by half a metre;\n"
              "the dip should move." % (weakest_at, furthest, weakest_at))
    print("\nThe hound is still running the calibration logger.")
    print("Restore the game with:  make flash-hound")
    if weakest < RECEIVER_FLOOR:
        print("\nNote: %.1f dBm at %.1f m is below the ~%d dBm receiver floor, so MIN_RSSI\n"
              "was clamped. The fox is out of reliable range at that distance."
              % (weakest, weakest_at, RECEIVER_FLOOR))
    return 0


if __name__ == "__main__":
    sys.exit(main())
