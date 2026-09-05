# Fox Hunt — Review & Field-Test Remediation Plan

Findings from the code review of 2026-09-05 plus the hardware field test (two micro:bit v2 boards, indoor line-of-sight at 2 m / 5 m / 11 m). Each item lists the fix and how it is verified.

## Stage 1 — Test infrastructure (no behavioural change)

1. **`pytest` crashes on collection, 0 tests run.** `run_integration_test.py` matches pytest's `*_test.py` glob and calls `sys.exit(1)` at import time. Rename to `integration_check.py` and guard the body behind `if __name__ == "__main__":`. Verify: `pytest` exits 0 and runs the suite.
2. **`test_speaker.py` is not a test** — a stub holding a URL and a comment. Delete.
3. **No project config.** Add `pyproject.toml` with pytest settings and project metadata.

## Stage 2 — Structural (no behavioural change)

4. **`hound.py` duplicates `HoundController` and never imports `hound_logic`.** The tests exercise `hound_logic.py`; the device runs a copy that has already drifted (`last_audio_time`). Make `hound.py` import the tested module. Both files must now be flashed to the board.

## Stage 3 — Logic defects

5. **Attenuator step (5 dB) is smaller than one bar (7 dB).** Measured on hardware: 4 of 8 Button-A presses produced no visible change. Derive the step from the scale so one press is always exactly one bar.
6. **Attenuation is unbounded.** Cap it so the display cannot be pressed into a permanently dead state.
7. **Zone flicker at boundaries.** `get_beep_to_play` latches the highest zone then resets it to 0 after every beep, so each window is a coin flip on marginal reception. Measured 48% tone changes at 5 m while standing still, 14% at 2 m. Replace with per-zone last-seen timestamps and a hold window spanning several fox cycles.
8. **Audio blocks the loop 62% of the time** (measured 118 ms per beep, loop period 129 ms vs 11.5 ms quiet). Use `music.pitch(..., wait=False)` and defer the NeoPixel crosstalk clear until the tone has actually finished.
9. **Bare `except:`** swallows `KeyboardInterrupt`, making the board hard to interrupt from the REPL.
10. **Needless decode.** `receive_full()` returns bytes; match on bytes and drop the `str()` call and its try/except.
11. **Dead condition** in `get_display_bars` (`and self.attenuation_offset == 0`) — the general path already returns 0.

## Stage 4 — Tests

12. Cover what was previously untested: signal isolation (the invariant AGENTS.md calls critical), EMA smoothing, the Button-A path, the attenuation cap, zone hold and decay, bar thresholds, packet backlog, and radio headers.

## Stage 5 — Documentation

13. Record the measured radio characteristics, the DAPLink auto-reset behaviour, the two-file flashing procedure, and the calibration status in AGENTS.md.

## Deliberately NOT changed

- **`MIN_RSSI` / `MAX_RSSI`.** Measured indoors: −65.7 dBm at 2 m, −66.6 at 5 m, −85.2 at 11 m — flat over 2→5 m (n = 0.22), then a cliff (n = 5.43). Three attempts to predict RSSI from a model were wrong by up to 20.7 dB. The indoor curve is not the outdoor curve, so no defensible values can be derived from this data. `calibrate.py` is provided to measure them properly in the real playfield.
- **EMA weighting (80/20).** Measured 7–8 dB of stationary RSSI noise, which is more than one bar, so the display will jitter. Retuning this trades against the documented <300 ms response target and should be decided with outdoor data, not indoor.
- **NeoPixels on pin0.** Moving them to pin1/pin2 would eliminate the speaker crosstalk at source rather than mitigating it, but that is a physical wiring change.
