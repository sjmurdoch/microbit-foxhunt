"""Unit tests for the Hound state machine.

Payloads are raw bytes exactly as radio.receive_full() delivers them, i.e.
carrying MicroPython's 3-byte header.
"""
import pytest

from hound_logic import (
    ATTEN_STEP,
    BAR_COUNT,
    BEEP_INTERVAL_MS,
    MAX_ATTENUATION,
    MAX_RSSI,
    MIN_RSSI,
    SIGNAL_TIMEOUT_MS,
    ZONE_HOLD_MS,
    HoundController,
)

HEADER = b"\x01\x00\x01"


def pkt(zone):
    """A packet as it actually arrives off the radio."""
    return HEADER + b"Z%d" % zone


@pytest.fixture
def hound():
    return HoundController()


# --- display ---------------------------------------------------------------

def test_no_signal_shows_no_bars(hound):
    assert hound.get_display_bars() == 0


def test_bars_are_monotonic_across_the_whole_scale(hound):
    seen = []
    for rssi in range(MIN_RSSI, MAX_RSSI + 1):
        hound.current_rssi = rssi
        seen.append(hound.get_display_bars())
    assert seen == sorted(seen), "bar count must never fall as signal rises"
    assert seen[0] == 0 and seen[-1] == BAR_COUNT
    assert set(seen) == set(range(BAR_COUNT + 1)), "every bar level must be reachable"


def test_saturates_rather_than_overflowing(hound):
    hound.current_rssi = MAX_RSSI + 50
    assert hound.get_display_bars() == BAR_COUNT


def test_any_detectable_signal_lights_at_least_one_bar(hound):
    hound.current_rssi = MIN_RSSI + 1
    assert hound.get_display_bars() == 1


# --- attenuator ------------------------------------------------------------

def test_button_a_drops_exactly_one_bar_per_press(hound):
    """Regression: a 5 dB step against 7 dB bars made half of all presses
    produce no visible change (measured on hardware at 2 m)."""
    hound.current_rssi = MAX_RSSI
    previous = hound.get_display_bars()
    assert previous == BAR_COUNT
    for _ in range(BAR_COUNT):
        hound.process_inputs(button_a=True, button_b=False)
        current = hound.get_display_bars()
        assert current == previous - 1, "each press must move exactly one bar"
        previous = current


def test_attenuation_is_capped(hound):
    for _ in range(100):
        hound.process_inputs(button_a=True, button_b=False)
    assert hound.attenuation_offset == MAX_ATTENUATION


def test_button_b_resets_attenuation(hound):
    hound.current_rssi = MAX_RSSI
    for _ in range(3):
        hound.process_inputs(button_a=True, button_b=False)
    assert hound.get_display_bars() < BAR_COUNT
    hound.process_inputs(button_a=False, button_b=True)
    assert hound.attenuation_offset == 0
    assert hound.get_display_bars() == BAR_COUNT


# --- RSSI handling ---------------------------------------------------------

def test_only_z1_drives_the_distance_reading(hound):
    """The fox cycles transmit power, so anything but the max-power beacon
    would make the bar graph track the fox's power cycle, not the player."""
    hound.process_packet(pkt(1), -70, 0)
    settled = hound.current_rssi
    hound.process_packet(pkt(2), -100, 50)
    hound.process_packet(pkt(3), -105, 100)
    assert hound.current_rssi == settled


def test_first_reading_snaps_instead_of_averaging_up_from_the_floor(hound):
    hound.process_packet(pkt(1), -60, 0)
    assert hound.current_rssi == -60


def test_ema_smooths_subsequent_readings(hound):
    hound.process_packet(pkt(1), -60, 0)
    hound.process_packet(pkt(1), -80, 200)
    assert -80 < hound.current_rssi < -60, "a single outlier must not fully move it"


def test_radio_header_does_not_break_matching(hound):
    hound.process_packet(pkt(2), -80, 0)
    assert hound.get_current_zone(0) == 2


def test_unknown_payload_is_ignored(hound):
    hound.process_packet(HEADER + b"HELLO", -50, 0)
    assert hound.get_current_zone(0) == 0


# --- zones -----------------------------------------------------------------

def test_closest_zone_wins(hound):
    for zone in (1, 2, 3):
        hound.process_packet(pkt(zone), -70, 0)
    assert hound.get_current_zone(0) == 3


def test_zone_survives_dropped_packets(hound):
    """Regression: Z3 is the weakest beacon and the first to drop out. Latching
    then clearing the zone after every beep produced tone changes on 48% of
    beeps while standing still at 5 m."""
    now = 0
    played = []
    for cycle in range(100):
        hound.process_packet(pkt(1), -66, now)
        hound.process_packet(pkt(2), -78, now + 50)
        if cycle % 3 == 0:                       # only 33% of Z3 get through
            hound.process_packet(pkt(3), -90, now + 100)
        for _ in range(20):                      # main loop ticks at ~10 ms
            zone = hound.get_beep_to_play(now)
            if zone:
                played.append(zone)
            now += 10
    assert played, "should have beeped"
    assert set(played) == {3}, "alarm must not stutter down to a slower tone"


def test_zone_decays_once_the_beacon_stops(hound):
    hound.process_packet(pkt(3), -90, 0)
    assert hound.get_current_zone(ZONE_HOLD_MS) == 3
    assert hound.get_current_zone(ZONE_HOLD_MS + 1) < 3


def test_falls_back_to_the_outer_zone_when_close_beacons_vanish(hound):
    hound.process_packet(pkt(3), -90, 0)
    hound.process_packet(pkt(1), -66, 0)
    hound.process_packet(pkt(1), -66, ZONE_HOLD_MS + 100)
    assert hound.get_current_zone(ZONE_HOLD_MS + 100) == 1


# --- audio timing ----------------------------------------------------------

@pytest.mark.parametrize("zone", [1, 2, 3])
def test_beep_cadence_matches_the_zone(hound, zone):
    interval = BEEP_INTERVAL_MS[zone]
    hound.process_packet(pkt(zone), -70, 0)
    assert hound.get_beep_to_play(interval - 1) == 0
    assert hound.get_beep_to_play(interval) == zone
    assert hound.get_beep_to_play(interval + 1) == 0, "must not double-fire"


def test_silent_with_no_signal(hound):
    assert hound.get_beep_to_play(5000) == 0


def test_beeping_does_not_clear_the_zone(hound):
    """The old implementation zeroed the zone after every beep."""
    hound.process_packet(pkt(3), -90, 0)
    assert hound.get_beep_to_play(200) == 3
    assert hound.get_current_zone(210) == 3


# --- timeout ---------------------------------------------------------------

def test_timeout_silences_and_blanks(hound):
    hound.process_packet(pkt(3), -50, 0)
    hound.check_timeout(SIGNAL_TIMEOUT_MS)
    assert hound.get_current_zone(SIGNAL_TIMEOUT_MS) == 3
    hound.check_timeout(SIGNAL_TIMEOUT_MS + 1)
    assert hound.get_display_bars() == 0
    assert hound.get_beep_to_play(SIGNAL_TIMEOUT_MS + 1) == 0


def test_recovers_after_a_timeout(hound):
    hound.process_packet(pkt(1), -60, 0)
    hound.check_timeout(SIGNAL_TIMEOUT_MS + 1)
    assert hound.get_display_bars() == 0
    hound.process_packet(pkt(1), -60, 5000)
    assert hound.current_rssi == -60
    assert hound.get_display_bars() > 0


# --- queue behaviour -------------------------------------------------------

def test_packet_backlog_is_handled(hound):
    """hound.py drains the whole radio queue on one tick, so a burst of
    packets can arrive bearing the same timestamp."""
    for zone in (1, 2, 3, 1, 2, 3):
        hound.process_packet(pkt(zone), -70, 500)
    assert hound.get_current_zone(500) == 3
    assert hound.get_beep_to_play(500) == 3


def test_zone_hold_outlasts_the_slowest_beep():
    """A zone must never expire before its own beep falls due, or the outer
    zone would go permanently silent on a marginal link."""
    assert ZONE_HOLD_MS >= max(BEEP_INTERVAL_MS.values())


# --- device compatibility --------------------------------------------------

DEVICE_FILES = ("fox.py", "hound.py", "hound_logic.py")


@pytest.mark.parametrize("filename", DEVICE_FILES)
def test_device_files_parse(filename):
    import ast
    ast.parse(open(filename).read())


@pytest.mark.parametrize("filename", DEVICE_FILES)
def test_device_files_avoid_fstrings(filename):
    """MicroPython on the micro:bit is not a full CPython; keep device code to
    the conservative subset."""
    import ast
    tree = ast.parse(open(filename).read())
    offenders = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.JoinedStr)]
    assert not offenders, "f-strings at lines %s" % offenders


def test_logic_module_imports_no_hardware():
    """hound_logic must stay testable off-device."""
    import ast
    tree = ast.parse(open("hound_logic.py").read())
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert not [m for m in imported if m in ("microbit", "radio", "music", "neopixel")]


def test_hound_imports_the_tested_logic():
    """Regression: hound.py once carried its own copy of HoundController, so
    the tests and the device ran different code."""
    source = open("hound.py").read()
    assert "from hound_logic import" in source
    assert "class HoundController" not in source
