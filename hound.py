"""The Hound (receiver) -- hardware layer.

Maps micro:bit hardware onto HoundController. All game logic lives in
hound_logic.py so it can be unit tested; BOTH files must be flashed:

    ufs put hound_logic.py
    ufs put hound.py main.py
"""
from microbit import *
import radio
import music
import neopixel

from hound_logic import HoundController
from radio_config import RADIO_GROUP

BEEP_MS = 100
BEEP_HZ = {1: 400, 2: 800, 3: 1200}

# The LED matrix is physically 5x5, which is a hardware fact and not the same
# thing as BAR_COUNT. BAR_COUNT is a tunable that a recalibration can change,
# and it used to drive both loops below: dropping it to 4 would have left row 4
# and column 4 holding whatever was last written to them for good, since the
# bars != last_bars guard means the matrix is only redrawn when the count moves.
MATRIX_SIZE = 5

# Blank any attached ZIP LEDs once, at boot. They power on in a random state
# (AGENTS.md gotcha 4) and nothing in the game uses them, so this is the only
# show() the hound ever does -- deliberately before any tone can play. There
# used to be a second clear after each beep; it is gone (AGENTS.md gotcha 8).
np = neopixel.NeoPixel(pin0, 5)
np.clear()
np.show()

speaker.on()
set_volume(255)

radio.on()
radio.config(group=RADIO_GROUP)

controller = HoundController()
last_bars = -1

while True:
    now = running_time()

    controller.process_inputs(button_a.was_pressed(), button_b.was_pressed())

    # Drain the entire hardware queue every tick so packets that arrived while
    # a tone was sounding do not back up and go stale.
    while True:
        packet = radio.receive_full()
        if not packet:
            break
        if packet[0]:
            controller.process_packet(packet[0], packet[1], now)

    controller.check_timeout(now)

    zone = controller.get_beep_to_play(now)
    if zone:
        # wait=False keeps the radio loop responsive. Blocking here measured
        # 118 ms per beep and left the hound deaf 62% of wall-clock time.
        music.pitch(BEEP_HZ[zone], BEEP_MS, pin=None, wait=False)

    # Overwrite pixels rather than display.clear(), which strobes the
    # multiplexed matrix.
    bars = controller.get_display_bars()
    if bars != last_bars:
        lit = min(bars, MATRIX_SIZE)          # fills from the bottom row up
        for y in range(MATRIX_SIZE):
            brightness = 9 if (MATRIX_SIZE - 1 - y) < lit else 0
            for x in range(MATRIX_SIZE):
                display.set_pixel(x, y, brightness)
        last_bars = bars

    sleep(10)
