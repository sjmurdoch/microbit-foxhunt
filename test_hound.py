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


def test_ema_still_smooths_at_the_bottom_of_the_scale(hound):
    """Regression: MIN_RSSI used to double as a "nothing heard yet" marker, so
    any reading at or below it was treated as a fresh start and snapped instead
    of averaging. MIN_RSSI is a real signal level -- it was measured at 20 m --
    so that silently disabled smoothing across the far half of the range,
    exactly where the 7-8 dB stationary noise hurts most."""
    hound.process_packet(pkt(1), MIN_RSSI, 0)   # first reading legitimately snaps
    now = 0
    for rssi in (MIN_RSSI + 3, MIN_RSSI - 3, MIN_RSSI - 1, MIN_RSSI + 1):
        now += 200
        hound.process_packet(pkt(1), rssi, now)
        assert hound.current_rssi != rssi, (
            "reading %d was taken raw; the EMA was skipped" % rssi
        )


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


def test_zone_hold_is_pinned_to_the_signal_timeout():
    """The tone and the display must stop together, and check_timeout relies on
    the equality: it leaves zone expiry to get_current_zone entirely. Decoupling
    these means check_timeout needs its own zone reset again."""
    assert ZONE_HOLD_MS == SIGNAL_TIMEOUT_MS


# --- device compatibility --------------------------------------------------

DEVICE_FILES = (
    "fox.py",
    "hound.py",
    "hound_integration.py",
    "hound_logic.py",
    "radio_config.py",
)


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


def test_calibration_logger_parses():
    """LOGGER_SRC is device code held in a string literal, so neither
    compileall nor the DEVICE_FILES checks above ever see it. A typo in there
    flashes cleanly -- verified_put only compares hashes -- and surfaces
    outdoors."""
    import ast
    import calibrate          # inert at import time; defines constants only

    ast.parse(calibrate.LOGGER_SRC)
    assert calibrate.READY in calibrate.LOGGER_SRC
    assert "__GROUP__" not in calibrate.LOGGER_SRC, "group placeholder not substituted"


def test_calibration_scale_matches_the_hound():
    """Regression: calibrate.py kept its own BAR_COUNT, so it could recommend a
    scale computed against a different number of bars than the hound draws."""
    import calibrate

    assert calibrate.BAR_COUNT is BAR_COUNT


# --- calibration tool ------------------------------------------------------

def test_calibration_ignores_unexpected_zone_tokens():
    """Regression: the zone regex matches Z0 and Z4-Z9 as well, and the dict
    lookup was unguarded. A single stray packet from other kit on the radio
    group raised a KeyError out of sample() and discarded every distance
    already walked."""
    import calibrate

    zones = {1: [], 2: [], 3: []}
    for line in (r"R|b'\x01\x00\x01Z7'|-70",
                 r"R|b'\x01\x00\x01Z0'|-70",
                 "not a reading at all"):
        calibrate.record(line, zones)
    assert zones == {1: [], 2: [], 3: []}
    calibrate.record(r"R|b'\x01\x00\x01Z1'|-52", zones)
    assert zones[1] == [-52]


def test_calibration_takes_the_real_extremes_not_the_end_distances():
    """Regression: MAX_RSSI was read off the nearest distance and MIN_RSSI off
    the furthest. Multipath breaks both assumptions -- the 2026-09-06 field run
    measured -89 dBm at 15 m against -87 at 20 m, a ground-reflection null."""
    import calibrate

    field = [(1, -52.0), (3, -59.0), (8, -80.0), (15, -89.0), (20, -87.0)]
    assert calibrate.recommend(field)["weakest_at"] == 15
    lobe = [(1, -58.0), (3, -52.0), (8, -80.0), (15, -89.0), (20, -87.0)]
    assert calibrate.recommend(lobe)["max_rssi"] == -52


def test_calibration_never_drops_the_scale_below_the_receiver_floor():
    """Rounding the span up to whole bars can push MIN_RSSI under the floor,
    which is what made the original -105 bottom unreachable. Round down
    instead."""
    import calibrate

    scale = calibrate.recommend([(1, -52.0), (30, -94.0)])
    assert scale["min_rssi"] >= calibrate.RECEIVER_FLOOR


def test_calibration_bars_divide_the_span_exactly():
    """ATTEN_STEP is RSSI_SPAN // BAR_COUNT, so a span that does not divide
    would make one press of button A move less than a full bar."""
    import calibrate

    scale = calibrate.recommend([(1, -52.0), (20, -87.0)])
    assert scale["max_rssi"] - scale["min_rssi"] == scale["step"] * BAR_COUNT


def test_calibration_refuses_a_spread_too_narrow_to_draw():
    import calibrate

    assert calibrate.recommend([(1, -52.0), (3, -53.0)]) is None


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


def test_display_geometry_is_not_tied_to_the_bar_count():
    """Regression: hound.py drove both matrix axes from BAR_COUNT, which is a
    tunable the calibration can change. At BAR_COUNT = 4 the top row and the
    right-hand column would never be written again."""
    source = open("hound.py").read()
    assert "MATRIX_SIZE = 5" in source
    assert "range(BAR_COUNT)" not in source


def test_radio_group_is_not_hardcoded_in_device_code():
    """Regression: the group was written out in both fox.py and hound.py, so
    the two roles could silently drift onto different groups."""
    import ast
    for filename in DEVICE_FILES:
        tree = ast.parse(open(filename).read())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if getattr(node.func, "attr", None) != "config":
                continue
            for keyword in node.keywords:
                if keyword.arg == "group":
                    assert not isinstance(keyword.value, ast.Constant), (
                        "%s passes a literal radio group; import it from "
                        "radio_config instead" % filename
                    )


def test_both_roles_take_the_group_from_one_place():
    from radio_config import RADIO_GROUP

    assert 1 <= RADIO_GROUP <= 255
    # 0 is the MicroPython default and 42 the usual tutorial value; both are
    # crowded and invite collisions with other kit nearby.
    assert RADIO_GROUP not in (0, 42)
    for filename in ("fox.py", "hound.py"):
        assert "from radio_config import RADIO_GROUP" in open(filename).read()


# --- the fox's group reveal ------------------------------------------------

def fox_ast():
    import ast

    return ast.parse(open("fox.py").read())


def fox_display_calls(attrs):
    """Calls to display.<attr> in fox.py, for the given attribute names."""
    import ast

    return [n for n in ast.walk(fox_ast())
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute) and n.func.attr in attrs
            and isinstance(n.func.value, ast.Name) and n.func.value.id == "display"]


def test_fox_shows_the_group_without_stopping_the_beacon():
    """display.show blocks by default, and the digits take longer than
    SIGNAL_TIMEOUT_MS. A blocking reveal would therefore silence and blank
    every hound in the field each time someone checked the fox's group -- the
    same trap as the blocking audio in hound.py."""
    import ast

    calls = fox_display_calls(("show", "scroll"))
    assert calls, "the fox no longer shows anything"
    for call in calls:
        waits = [k.value for k in call.keywords if k.arg == "wait"]
        assert waits and all(isinstance(v, ast.Constant) and v.value is False
                             for v in waits), "display call at line %d blocks" % call.lineno

    # The rest of the loop must stay inside the hound's patience too.
    quiet = sum(n.args[0].value for n in ast.walk(fox_ast())
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "sleep" and n.args
                and isinstance(n.args[0], ast.Constant))
    assert quiet < SIGNAL_TIMEOUT_MS, "a full fox cycle outlasts the hound's timeout"


def test_fox_shows_the_configured_group():
    """Not a literal. The whole point of the reveal is to answer "what group is
    this board on?", so a hard-coded number would be worse than no display at
    all -- it could disagree with what the board is actually transmitting on."""
    import ast

    shown = fox_display_calls(("show", "scroll"))
    assert shown, "the fox no longer shows anything"
    names = [d.id for call in shown for d in ast.walk(call.args[0])
             if isinstance(d, ast.Name)]
    assert "RADIO_GROUP" in names, "the fox shows something other than its group"


def test_fox_goes_dark_again_after_showing_the_group():
    """Stealth is the fox's one hard requirement. Lighting the display on a
    button press is deliberate; leaving it lit -- after a press, or after being
    knocked in a hedge -- would hand the game away."""
    import ast

    loop = [n for n in ast.walk(fox_ast()) if isinstance(n, ast.While)][0]
    offs = [n.lineno for n in fox_display_calls(("off",))]
    assert any(line < loop.lineno for line in offs), "the fox does not start dark"
    assert any(line > loop.lineno for line in offs), "the fox never goes dark again"


def test_fox_reads_both_buttons_unconditionally():
    """was_pressed() clears a latch as it reads it. Behind `or` the second
    button is only read when the first was not pressed, so a press on it would
    sit in the latch and fire a spurious reveal on a later pass."""
    import ast

    for node in ast.walk(fox_ast()):
        if not isinstance(node, ast.BoolOp):
            continue
        for inner in ast.walk(node):
            assert not (isinstance(inner, ast.Call)
                        and getattr(inner.func, "attr", None) == "was_pressed"), (
                "fox.py reads a button inside a boolean expression at line %d"
                % node.lineno)
