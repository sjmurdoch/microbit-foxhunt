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

from hound_logic import HoundController, BAR_COUNT
from radio_config import RADIO_GROUP

BEEP_MS = 100
BEEP_HZ = {1: 400, 2: 800, 3: 1200}
# Audio does not reach P0 at all once pin=None is passed (see AGENTS.md gotcha
# 3), but WS2812 pixels are bit-banged and an interrupt landing mid-show() can
# still corrupt them. Blank them once the tone has finished, never during it.
NP_SETTLE_MS = 20

np = neopixel.NeoPixel(pin0, 5)
np.clear()
np.show()

speaker.on()
set_volume(255)

radio.on()
radio.config(group=RADIO_GROUP)

controller = HoundController()
last_bars = -1
np_clear_due = 0

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
        np_clear_due = now + BEEP_MS + NP_SETTLE_MS

    if np_clear_due and running_time() >= np_clear_due:
        np.clear()
        np.show()
        np_clear_due = 0

    # Overwrite pixels rather than display.clear(), which strobes the
    # multiplexed matrix.
    bars = controller.get_display_bars()
    if bars != last_bars:
        for y in range(BAR_COUNT):
            brightness = 9 if (BAR_COUNT - 1 - y) < bars else 0
            for x in range(BAR_COUNT):
                display.set_pixel(x, y, brightness)
        last_bars = bars

    sleep(10)
