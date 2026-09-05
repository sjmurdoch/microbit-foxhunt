"""Pure-Python state machine for the Hound (receiver).

Deliberately imports nothing from `microbit`, so it can be unit-tested on a
desktop. `hound.py` imports this module, which means BOTH files must be copied
to the board -- see AGENTS.md section 5.
"""

# --- Signal scale ----------------------------------------------------------
# WARNING: not yet field-calibrated. Measured indoors (see AGENTS.md section 4)
# the Z1 beacon read -65.7 dBm at 2 m and -85.2 dBm at 11 m, so MAX_RSSI = -70
# saturates the display over the close half of the playfield. Run calibrate.py
# outdoors in the real playfield before a game.
MIN_RSSI = -105
MAX_RSSI = -70

BAR_COUNT = 5
RSSI_SPAN = MAX_RSSI - MIN_RSSI

# One press of button A must move the bar graph by exactly one bar. Deriving
# the step from the scale keeps that true if the scale is ever recalibrated.
# (A hard-coded 5 dB step against 7 dB bars made half of all presses do
# nothing -- measured on hardware at 2 m.)
ATTEN_STEP = RSSI_SPAN // BAR_COUNT
MAX_ATTENUATION = ATTEN_STEP * 10

# --- Timing ----------------------------------------------------------------
FOX_CYCLE_MS = 200        # fox.py emits Z1, Z2, Z3 once per 200 ms
SIGNAL_TIMEOUT_MS = 1000  # no packets at all -> silent and blank
BEEP_INTERVAL_MS = {1: 1000, 2: 500, 3: 200}

# How long a zone is remembered after its beacon was last heard: 5 fox cycles,
# so several dropped packets in a row do not change the tone. This must not be
# shorter than the slowest beep interval, or a zone could expire before its own
# beep fell due; keeping it equal to SIGNAL_TIMEOUT_MS also means the tone stops
# and the display blanks at the same moment.
ZONE_HOLD_MS = SIGNAL_TIMEOUT_MS

# Weight given to the newest RSSI reading. Stationary noise was measured at
# 7-8 dB peak-to-peak (more than one bar), so lowering this trades display
# jitter against the documented <300 ms response target.
EMA_ALPHA = 0.8

# Highest zone first: Z3 is the weakest beacon and so the closest range.
ZONE_TOKENS = ((3, b"Z3"), (2, b"Z2"), (1, b"Z1"))


class HoundController:
    def __init__(self):
        self.attenuation_offset = 0
        self.last_packet_time = 0
        self.current_rssi = MIN_RSSI
        self.last_audio_time = 0
        self.zone_last_seen = {1: None, 2: None, 3: None}

    def process_inputs(self, button_a, button_b):
        if button_a:
            self.attenuation_offset = min(
                self.attenuation_offset + ATTEN_STEP, MAX_ATTENUATION
            )
        if button_b:
            self.attenuation_offset = 0

    def process_packet(self, payload, rssi, now):
        """Feed one raw radio packet in.

        `payload` is the bytes object from radio.receive_full(), which still
        carries MicroPython's 3-byte b'\\x01\\x00\\x01' header -- hence the
        substring test rather than equality.
        """
        self.last_packet_time = now

        # Only the max-power Z1 beacon drives the distance reading. Using any
        # other zone would make the bar graph oscillate in step with the fox's
        # transmit-power cycle rather than with the player's movement.
        if b"Z1" in payload:
            if self.current_rssi <= MIN_RSSI:
                self.current_rssi = rssi
            else:
                self.current_rssi = (
                    self.current_rssi * (1.0 - EMA_ALPHA) + rssi * EMA_ALPHA
                )

        for zone, token in ZONE_TOKENS:
            if token in payload:
                self.zone_last_seen[zone] = now
                break

    def check_timeout(self, now):
        if now - self.last_packet_time > SIGNAL_TIMEOUT_MS:
            self.current_rssi = MIN_RSSI
            self.zone_last_seen = {1: None, 2: None, 3: None}

    def get_current_zone(self, now):
        """Highest zone heard recently.

        A hold window rather than a latch-and-reset: the weakest beacon is the
        first to suffer packet loss, and clearing the zone after every beep
        made each interval a coin flip on whether a Z3 happened to land. That
        produced tone changes on 48% of beeps while standing still at 5 m.
        """
        for zone in (3, 2, 1):
            seen = self.zone_last_seen[zone]
            if seen is not None and now - seen <= ZONE_HOLD_MS:
                return zone
        return 0

    def get_beep_to_play(self, now):
        """Return the zone whose tone is due now, or 0 for silence."""
        zone = self.get_current_zone(now)
        if zone == 0:
            return 0
        if now - self.last_audio_time >= BEEP_INTERVAL_MS[zone]:
            self.last_audio_time = now
            return zone
        return 0

    def get_display_bars(self):
        adjusted = self.current_rssi - self.attenuation_offset
        fraction = (adjusted - MIN_RSSI) / float(RSSI_SPAN)
        fraction = max(0.0, min(1.0, fraction))
        bars = int(fraction * BAR_COUNT)
        # Any detectable signal deserves at least one bar.
        if fraction > 0 and bars == 0:
            bars = 1
        return bars
