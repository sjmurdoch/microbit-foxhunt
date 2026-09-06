"""A stripped hound that prints what it hears. Used by integration_check.py.

No audio, no display, no smoothing -- just the raw radio, so a failure can only
be the radio. Flash it with `make flash-integration`; `make flash-hound` puts
the real game back.
"""
from microbit import *
import radio

from radio_config import RADIO_GROUP

radio.on()
radio.config(group=RADIO_GROUP)
print("HOUND_START")

while True:
    packet = radio.receive_full()
    if packet and packet[0]:
        # Print the payload raw. It carries MicroPython's 3-byte header and is
        # not necessarily valid UTF-8, so %r rather than a decode that can fail
        # (AGENTS.md gotcha 1).
        print("HOUND_RX: %r RSSI: %d" % (packet[0], packet[1]))
    sleep(10)
