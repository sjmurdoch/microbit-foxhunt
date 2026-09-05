"""Hardware integration check - NOT a unit test.

Requires two micro:bits on USB running fox.py / hound_integration.py.
Run by hand:  uv run python integration_check.py
"""
import sys
import time

import serial
import serial.tools.list_ports


def main():

    # Find micro:bit serial ports
    ports = list(serial.tools.list_ports.comports())
    microbit_ports = [p.device for p in ports if 'usbmodem' in p.device or 'usbserial' in p.device]

    if len(microbit_ports) < 1:
        print(f"Error: Could not find microbit serial ports. Found {len(microbit_ports)}")
        sys.exit(1)

    # Open all found ports
    serials = [serial.Serial(p, 115200, timeout=0.5) for p in microbit_ports]

    start_time = time.time()
    found_z1 = False
    found_z2 = False
    found_z3 = False

    print("Listening for radio packets from the Fox over serial...")
    time.sleep(1)

    while time.time() - start_time < 5:
        for s in serials:
            try:
                line = s.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    print(f"[{s.port}] {line}")
                    if "Z1" in line: found_z1 = True
                    if "Z2" in line: found_z2 = True
                    if "Z3" in line: found_z3 = True
            except Exception as e:
                pass

        if found_z1 and found_z2 and found_z3:
            print("Integration Test Passed! All 3 zones received successfully.")
            sys.exit(0)

    print("Integration Test Failed! Did not receive all zones.")
    print(f"Z1: {found_z1}, Z2: {found_z2}, Z3: {found_z3}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
