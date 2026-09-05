# Micro:bit Fox Hunt (ARDF) System Design

This document describes the Micro:bit Fox Hunt project: its design, architecture, the hardware quirks discovered during development, and the radio characteristics measured on real boards. It is intended as a guide for code review and future maintenance.

## 1. High-Level Design

The system implements an "Amateur Radio Direction Finding" (ARDF) game using two BBC micro:bit v2 devices communicating over the 2.4 GHz radio band.

1. **The Fox (Transmitter)**: a hidden beacon. To create proximity zones without asking the seeker to interpret raw radio data, it cycles its transmit power (max, medium, low) once every 200 ms.
2. **The Hound (Receiver)**: the player's tracker. It gives auditory feedback (a beep whose cadence and pitch indicate which zone the player is in) and visual feedback (a 5x5 LED bar graph of raw signal strength).

### Equipment and operating requirements

| | |
|---|---|
| Fox | 1x BBC micro:bit v2 plus a battery pack |
| Hound | 1 or more micro:bit v2, each with a battery pack |
| Power | 2x AAA NiMH rechargeable (roughly 800–1000 mAh) per device |

Hounds are passive receivers, so **any number of players can hunt the same fox** without interfering with each other or with the fox.

The fox must stay dark (no LED display) and run for **at least 2 hours on one charge**. That endurance requirement has never been measured — see section 8.

## 2. Intended Functionality

* **Audio zones (coarse tracking)**: closer to the fox, the hound starts hearing the weaker, lower-power beacons. Slow beep when only the strongest beacon is heard, medium beep for the middle beacon, rapid alarm when the weakest is detected.
* **Visual bar graph (fine tracking)**: the LED matrix displays smoothed RSSI, using an exponential moving average to suppress multipath jitter while staying responsive to movement.
* **The attenuator**: the bar graph saturates while the player is still some way from the fox. **Button A** adds attenuation so tracking can continue at close range; **Button B** resets it to zero.

## 3. Architecture & Code Mapping

### `fox.py` (the beacon)
A short procedural script. It loops forever setting `radio.config(power=X)` and broadcasting `"Z1"`, `"Z2"`, `"Z3"`. It calls `display.off()` and clears any attached ZIP/NeoPixels on pin 0 so the fox stays hidden.

### `radio_config.py` (shared settings)
Holds `RADIO_GROUP`, the one thing the fox and the hound must agree on. Imported by both so the value cannot drift; a test asserts no device file passes a literal `group=`. Avoid group 0 (the MicroPython default, so any unconfigured board sits on it) and 42 (what most tutorials use) — both invite collisions with other kit in the room.

### `hound_logic.py` (the state machine)
The `HoundController` class: a pure-Python state machine with no `microbit` imports, so it can be unit tested on a desktop.

* **Inputs**: `process_inputs` (button states), `process_packet` (raw payload bytes, RSSI, timestamp), `check_timeout`.
* **Signal isolation**: only the `Z1` (max power) beacon updates the distance reading. Using any other zone would make the bar graph oscillate in step with the fox's transmit-power cycle rather than with the player's movement.
* **Zone hold**: `get_current_zone` reports the highest zone heard within `ZONE_HOLD_MS`, rather than latching a zone and clearing it after each beep. See section 6.
* **Outputs**: `get_beep_to_play`, `get_display_bars`.

### `hound.py` (hardware integration)
The receiver's main loop. It imports `HoundController` from `hound_logic` — **the logic is not duplicated here, so both files must be flashed** (section 5). It maps buttons, the radio queue and the system clock onto the state machine, drains the entire `radio.receive_full()` queue every tick, plays tones asynchronously, and drives the LED matrix by overwriting pixel brightness.

### Tests
`test_hound.py` is the unit suite (`pytest`). `integration_check.py` and `calibrate.py` are **hardware tools, not tests** — they need boards attached and are run by hand. `pyproject.toml` restricts collection to `test_hound.py` so they can never be imported during a test run.

## 4. Measured radio characteristics

Measured on two micro:bit v2 boards (DAPLink 0257, MicroPython 1.13). **These are indoor line-of-sight measurements. They are not a substitute for calibrating in the real playfield.**

### Transmit power

The firmware's `power_dbm_table` is `{0:-30, 1:-20, 2:-16, 3:-12, 4:-8, 5:-4, 6:0, 7:4}` dBm. The three game zones therefore sit roughly 12 dB apart, which was confirmed on air:

| Zone | `power=` | dBm | RSSI at 1 cm | RSSI at 2 m | RSSI at 5 m | RSSI at 11 m |
|------|---------|-----|--------------|-------------|-------------|--------------|
| Z1 | 7 | +4  | −26.0 | −65.7 (100%) | −66.6 (100%) | −85.2 (80%) |
| Z2 | 4 | −8  | −38.0 | −76.9 (100%) | −78.8 (96%)  | −92.0 (3%)  |
| Z3 | 1 | −20 | −49.4 | −87.9 (70%)  | −90.4 (25%)  | not heard   |

Percentages are packet reception rates.

### Propagation is not a smooth curve indoors

```
 2 m : -65.7 dBm
 5 m : -66.6 dBm    <- only 0.9 dB apart (path-loss exponent 0.22)
11 m : -85.2 dBm    <- then an 18.6 dB cliff (exponent 5.43)
```

Indoors there is effectively **no usable distance gradient between 2 m and 5 m**, then a very steep one. Reflections channel energy over the short range before something blocks it. Consequences:

* Attempts to predict RSSI from a single path-loss exponent were wrong by up to 20.7 dB. Do not calibrate this game from a model, and do not calibrate it indoors.
* Stationary RSSI noise was 7–8 dB peak-to-peak — more than one bar's worth — so some display jitter is unavoidable.
* Free space (exponent 2.0) predicts roughly −81 dBm at 22 m, so outdoors the signal should behave far more monotonically. Calibrate there.

### Receiver floor

The nRF52833 bottoms out near −96 dBm. This was visible in practice: Z2 at −92 dBm only got 3% of packets through. **`MIN_RSSI = -105` is therefore below anything the radio can receive**, so the bottom of the scale is unreachable.

### Things that are *not* problems

* `radio.config(power=N)` **does not reset `group`** on micro:bit v2. The firmware copies the current config and overwrites only the supplied keywords (`microbit_radio_config_t new_config = radio_config;`). Verified on air: a listener on group 0 heard nothing while the fox cycled power on group 42. The v1 firmware differs — do not carry this assumption backwards.
* The default receive queue of 3 is sufficient. With the fox at 5 Hz and the old blocking audio, reception was still 294/294 packets, because `hound.py` drains the whole queue every tick.

## 5. Flashing and tooling

Everything goes through the Makefile; run `make help` for the list.

```sh
make check          # parse every source file, then run the tests
make devices        # list attached micro:bits and their serial ports
make flash-hound    # flash the hound (both its files)
make flash-fox      # flash the fox
make flash FOX_PORT=<port> HOUND_PORT=<port>    # both boards at once
```

Flashing targets depend on `check`, so code that fails its tests never reaches a board.

**Use `microfs` (`ufs`), never `uflash`.** `uflash` v2.0.0 bundles micro:bit **v1** firmware and will silently downgrade a v2 board, disabling the speaker.

### Firmware is never touched by flashing

`ufs` copies Python files onto the filesystem of whatever MicroPython is already installed. Nothing in this project writes firmware, so a board keeps the runtime it arrived with. `make devices` reports it:

```
/dev/cu.usbmodem1402  micro:bit v2  MicroPython 2.1.2
    serial 9906360200052820726e40a4da840fa7000000006e052820
```

It flags two things worth catching early: a board behind the newest release, and a board running **v1** firmware, which is the fingerprint of an accidental `uflash` (the generation is read from `os.uname().machine` — nRF51 is v1, nRF52 is v2). Note `sys.implementation` is not useful here: every micro:bit v2 release from 2.0.0 to 2.1.2 reports MicroPython core 1.13, so only `os.uname().release` identifies the build.

`LATEST_MICROPYTHON` in `flash.py` is a hand-maintained constant, last checked 2026-09-06 against v2.1.2; it only drives the "newer available" hint.

To update firmware, drag a `micropython-microbit-v2.X.Y.hex` onto the `MICROBIT` USB drive. **This erases the filesystem**, so update firmware first and then re-run `make flash-fox` / `make flash-hound` — doing it the other way round wipes the code and leaves a board that looks dead. Be aware an update also invalidates the radio measurements in section 4 if the radio stack changes.

### `ufs put` is not safe on its own

`ufs put` can report success while leaving a **different file on the device**. Observed here: `main.py` written as `36b3f2c0` read back as `98c4f8ff`, and the board then failed to boot with an `IndentationError` on a file that was perfectly valid on disk. The cause is the auto-reset below — the board reboots mid-transfer and starts executing a half-written `main.py`, which disrupts the rest of the copy.

`flash.py` works around this, and `make flash-*` uses it: halt the running program, delete `main.py` so the board boots idle, copy each file, **verify it by hash**, write `main.py` last, then reset and check for a traceback. If you flash by hand instead, verify the result — do not trust a silent success.

Both roles need `radio_config.py`, which holds the shared radio group. The hound additionally needs `hound_logic.py`. `main.py` is written last in each case:

| Role | Files on the board |
|------|--------------------|
| Fox | `radio_config.py`, `fox.py` as `main.py` |
| Hound | `radio_config.py`, `hound_logic.py`, `hound.py` as `main.py` |

**Changing the radio group means reflashing both boards.** They will not hear each other otherwise, and the symptom is silent — the hound simply never receives anything and times out.

### DAPLink auto-reset

`DETAILS.TXT` on these boards reports `Auto Reset: 1`. **Opening or closing the USB serial port reboots the micro:bit.** Practical consequences:

* A board cannot be left sitting in the REPL while another tool touches the port — it will reset and start running `main.py` again.
* Anything typed into the REPL is lost as soon as the connection drops, so identification tricks like `display.scroll(...)` do not survive.
* `ufs`/`microfs` operations are affected too; retry logic around raw-REPL entry is worth having in host-side scripts.

### Two boards at once

The `ufs` command-line tool always picks the first micro:bit it finds and cannot target a specific one. To drive two boards, open a `serial.Serial(port, 115200, timeout=1, parity="N")` yourself and pass it to `microfs.put/get/ls/execute(..., serial=...)`.

## 6. Design decisions worth preserving

### Zone hold, not latch-and-reset

The zone is remembered for `ZONE_HOLD_MS` after its beacon was last heard. An earlier implementation latched the highest zone seen and then cleared it to zero after every beep, which made each interval a coin flip on whether a packet from the weakest beacon happened to land. Because Z3 is the weakest beacon and the first to suffer loss, this produced **tone changes on 48% of beeps while standing still at 5 m**, and 14% at 2 m. With the hold window those fall to roughly 7% and 0%.

`ZONE_HOLD_MS` must never be shorter than the slowest beep interval, or the outer zone could expire before its own beep fell due and go permanently silent. It is pinned to `SIGNAL_TIMEOUT_MS` so the tone stops and the display blanks at the same moment. There is a test asserting this.

A residual remains at zone boundaries: a single stray packet from a closer beacon upgrades the tone for a full hold window. This is arguably correct — the hound genuinely did hear it — and hysteresis was not added because requiring two detections would make the danger zone harder to enter.

### Attenuator step is derived, not hard-coded

`ATTEN_STEP = RSSI_SPAN // BAR_COUNT`, so one press of button A always moves the bar graph by exactly one row. A hard-coded 5 dB step against 7 dB bars meant **4 of 8 presses produced no visible change on real hardware**. Deriving the step keeps the guarantee if the scale is recalibrated. Attenuation is also capped so the display cannot be pressed into a permanently dead state.

## 7. Hardware quirks and gotchas

1. **MicroPython radio headers**: `radio.send()` prepends a 3-byte header, and `receive_full()` returns it (confirmed on air: `b'\x01\x00\x01P0'`). Strict equality fails; match with `in`. The payload is raw bytes, so match against bytes (`b"Z1" in payload`) and skip decoding entirely.
2. **Varying transmit power vs RSSI**: because the fox cycles power, received RSSI fluctuates in step with the cycle. The hound updates its distance reading only on `Z1`.
3. **Audio output pin vs the speaker** (a previous version of this document had this wrong): the v2 speaker is **not** wired to the P0 edge connector. They are separate pins — `microbit_pin.c` gives P0 as `MICROBIT_HAL_PIN_P0` (0) and the speaker as `MICROBIT_HAL_PIN_SPEAKER` (31) — and they are independently controllable, with [the docs](https://microbit-micropython.readthedocs.io/en/v2-docs/speaker.html) noting that `speaker.off()` "does not disable sound output to an edge connector pin". What is true is that audio **defaults** to P0 and the speaker mirrors it, which is a software routing default. Passing `pin=None` routes audio to no pin at all (`microbit_pinaudio.c` turns it into `microbit_hal_audio_select_pin(-1)`) while the speaker keeps sounding. So `pin=None` is genuinely necessary and genuinely sufficient to keep audio off P0; there is no unavoidable hardware cross-talk.

4. **NeoPixel startup state**: ZIP LEDs power on in a random state. Both scripts call `clear()` then `show()` on boot to guarantee stealth.
5. **LED matrix flicker**: the matrix is multiplexed, and `display.clear()` inside a rapid loop strobes it. Overwrite pixel brightness (`0` or `9`) instead.
6. **`uflash` firmware downgrade**: see section 5.
7. **Blocking audio**: `music.pitch(f, ms, pin=None)` blocks by default. Measured at 118 ms per beep, giving a 129 ms loop period against 11.5 ms when quiet — the hound was deaf for **62% of wall-clock time** in the danger zone. Pass `wait=False`, and defer the NeoPixel clear until the tone has actually ended.

8. **NeoPixels are timing-critical, and that is probably the real reason for the clear-after-beep**: WS2812 pixels are bit-banged at ~800 kHz with tight tolerances, so an interrupt landing mid-`show()` can corrupt the bitstream and leave pixels lit in random colours. Audio runs off a hardware timer, so it can interrupt `show()` regardless of which pin the audio goes to. This is the most likely explanation for the flashing that commit `d253d31` was written to hide, since `pin=None` was already in place by then (`82b2cfc`) and, per gotcha 3, actually works. Two consequences: moving the pixels to P1/P2 would **not** help, and `hound.py` defers its `np.clear()` until the tone has finished rather than firing it during playback. Whether the clear is needed at all is untested — see section 8.

9. **The antenna is omnidirectional**: the micro:bit's PCB antenna gives essentially no directional information, so the hound cannot show a bearing — only a strength. Players find the fox either by walking and watching whether the reading rises, or by **body shielding**: a human body absorbs enough 2.4 GHz to drop the signal noticeably, so turning on the spot until the reading dips means the fox is behind you. This is what PLAYER_GUIDE means by "turn your body". It also means the reading depends on how the device is held, which is part of what a field calibration has to absorb — calibrate holding the hound the way a child will.

## 8. Open items

* **`MIN_RSSI` / `MAX_RSSI` are not field-calibrated.** The present values (−105 / −70) place the bottom of the scale below the receiver floor and saturate the display over the close half of the playfield. Correct values cannot be derived from the indoor data in section 4. Run `calibrate.py` outdoors in the real playfield; it prints the two constants directly.
* **`EMA_ALPHA` (0.8)** was tuned for a <300 ms response before the 7–8 dB stationary noise floor was known. Revisit alongside the calibration, with outdoor data.
* **Z3 may be too weak indoors.** At −87.9 dBm it sits near the receiver floor even at 2 m, so the danger zone never reads cleanly indoors. Outdoors it should be stronger; if not, raise the Z3 transmit power.

* **Is the NeoPixel clear-after-beep needed at all?** It was added against a mechanism that turned out to be wrong (gotcha 3). The pixels are vestigial — nothing in the game uses them, both scripts only blank them — so the cheapest answer may be not to attach them, or not to construct the `NeoPixel` object. Test with a strip attached: play tones for a few minutes with the deferred clear removed and see whether any pixel lights.

### Acceptance tests not yet run

Carried over from the original plan; none of these can be satisfied from a desk.

* **Battery endurance.** The fox is required to run for 2 hours and has never been timed. Run it for 2.5 h on freshly charged cells and confirm it is still transmitting at the end.
* **Outdoor zone thresholds.** Walk away from the fox in the open and record where the audio drops from zone 3 to 2, and 2 to 1. Everything measured so far is indoors, where propagation was flat from 2 m to 5 m and then fell off a cliff (section 4).
* **Usability with a real player.** Hand the hound to a child who has not been briefed beyond "follow the sound, press A if the screen fills up" and confirm they can find the fox.

## History

`archive/` holds superseded working documents, kept for context rather than guidance:

* `fox_hunt_plan.md` — the original design and implementation plan. Everything in it is either built, superseded by measurements in section 4, or carried into the sections above.
* `FIX_PLAN.md` — the remediation plan for the 2026-09-05 code review and field test. All stages complete.
