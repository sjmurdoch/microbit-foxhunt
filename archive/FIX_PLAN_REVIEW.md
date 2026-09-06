# Remediation plan — whole-project code review, 2026-09-06

Fifteen findings from a full-project review (the earlier `archive/FIX_PLAN.md` covered only the 2026-09-05 review). Each was reproduced against the source before being accepted. Work in four commits so the game-logic change stays separable from the tooling.

## Stage 1 — the state machine (`hound_logic.py`)

1. **`MIN_RSSI` is doing double duty as a "no reading yet" sentinel.** `process_packet` snaps instead of averaging whenever `current_rssi <= MIN_RSSI`, and MIN_RSSI is now −87 — inside the real signal range. Reproduced: the packet train `[-84,-90,-88,-86,-91,-85,-89,-87]` yields `-84, -88.8, -88, -86, -90.0, -85, -88.2, -87`, five of eight raw. Add an explicit `have_reading` flag.
2. **The `zone_last_seen` reset in `check_timeout` cannot fire.** `ZONE_HOLD_MS == SIGNAL_TIMEOUT_MS`, so `get_current_zone` has already expired every zone. Remove it and pin the equality with a test, so the one remaining expiry path is the load-bearing one.

## Stage 2 — the display (`hound.py`)

3. **`BAR_COUNT` doubles as the matrix width and height.** Set `BAR_COUNT = 4` and row 4 and column 4 are never written again. Introduce `MATRIX_SIZE = 5` for the hardware.

## Stage 3 — host tooling (`calibrate.py`, `flash.py`, `integration_check.py`, `hound_integration.py`)

4. **`calibrate.sample()` raises `KeyError` on a stray Z-token** (`Z0`, `Z4`–`Z9` all match the regex), killing the process and discarding every distance already walked.
5. **`MAX_RSSI` comes from the nearest reading, not the strongest** — the same null bug already fixed at the `MIN_RSSI` end.
6. **`calibrate.find_port()` silently picks the first of two boards**, where `flash.pick_port()` refuses to guess. Reuse it.
7. **`calibrate.BAR_COUNT` is a second copy** of `hound_logic.BAR_COUNT`.
8. **`flash._session` and `verified_put` open the port outside their retry blocks**, so the transient they exist to absorb aborts the flash.
9. **`boot_check` passes on silence.** The logger prints `CAL_READY`; check for it.
10. **`remove_main` conflates "no main.py" with "board unreachable"**, and `flash()` discards the result.
11. **`LOGGER_SRC` is device code nothing ever parses.**
12. **`integration_check.py` opens any `usbmodem` device** and swallows every read error.
13. **`hound_integration.py` is orphaned** — not in `ROLES`, `DEVICE_SRC`, or `DEVICE_FILES`, so `make integration` has no way to work.

## Stage 4 — documentation (`AGENTS.md`)

14. AGENTS.md says pytest collects only `test_hound.py`; it collects `test_flash.py` too.
15. `boot_check`'s docstring says 0/8 hardware resets, AGENTS.md says 14 of 14.

Plus a new section of standing advice for future agents, carrying the durable lessons out of this plan.

## Verification

`make check` between stages. Stage 2 and stage 3 also get a hardware pass on the attached board (serial `…726e40a4`, `/dev/cu.usbmodem11402`), since neither the display code nor the flashing path is reachable from the unit suite.
