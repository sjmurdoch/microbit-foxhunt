"""The Fox (transmitter) -- a hidden beacon.

Cycles transmit power so the hound can tell roughly how close it is, and stays
dark: no display, no ZIP LEDs. Pressing either button breaks that stealth for a
moment on purpose, to show the radio group -- see the comment in the loop.
"""
from microbit import *
import radio
import neopixel

from radio_config import RADIO_GROUP

# How long each digit of the group is held when a button asks for it. Groups
# run to 255, so the display is lit for at most three of these.
GROUP_DIGIT_MS = 600

np = neopixel.NeoPixel(pin0, 5)
np.clear()
np.show()

# Initialize Radio
radio.on()
radio.config(group=RADIO_GROUP)

# Turn off the display so the Fox stays hidden
display.off()

# While the group is being shown, when to go dark again. 0 means dark now.
reveal_until = 0

while True:
    # Either button shows the radio group. A wrong group is completely silent
    # on the air -- the hounds simply never hear anything -- so without this
    # the only way to ask a board what it is set to is to plug it into a
    # computer, which is no use once the fox is out in a field.
    #
    # Both buttons are read every pass, and deliberately not as `a or b`:
    # was_pressed() clears a latch, so short-circuiting would leave button B's
    # press stored and fire a second reveal on the next loop.
    pressed_a = button_a.was_pressed()
    pressed_b = button_b.was_pressed()
    if pressed_a or pressed_b:
        display.on()
        # wait=False, or the beacon stops for as long as the digits take. That
        # is over the hound's SIGNAL_TIMEOUT_MS, so every hound in the field
        # would fall silent and blank each time someone checked the group --
        # the same reason hound.py plays its tones asynchronously.
        display.show(str(RADIO_GROUP), delay=GROUP_DIGIT_MS, wait=False)
        reveal_until = running_time() + GROUP_DIGIT_MS * len(str(RADIO_GROUP))

    # --- Zone 1 (Heard furthest away) ---
    radio.config(power=7)  # Max power
    radio.send("Z1")
    sleep(50)

    # --- Zone 2 (Heard at medium distance) ---
    radio.config(power=4)  # Medium power
    radio.send("Z2")
    sleep(50)

    # --- Zone 3 (Heard only when very close) ---
    radio.config(power=1)  # Low power
    radio.send("Z3")
    sleep(100)

    # Dark again as soon as the digits have played, so a fox that is pressed --
    # or knocked -- while hidden does not stay lit and give itself away.
    if reveal_until and running_time() >= reveal_until:
        display.off()
        reveal_until = 0

    # Total loop time ~ 200ms
