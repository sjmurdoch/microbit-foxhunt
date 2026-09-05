# Micro:bit Fox Hunt (ARDF) System Design

This document provides a comprehensive overview of the Micro:bit Fox Hunt project, outlining its high-level design, intended functionality, system architecture, and specific hardware quirks encountered during development. This is intended to serve as a guide for code review and future maintenance.

## 1. High-Level Design

The system implements an "Amateur Radio Direction Finding" (ARDF) game using two BBC micro:bit v2 devices communicating via the 2.4GHz radio band. 

The architecture is divided into two distinct roles:
1. **The Fox (Transmitter)**: A hidden device that acts as a beacon. To simulate varying proximity zones without requiring the seeker to interpret raw radio data, the Fox rapidly cycles its transmission power (Max, Medium, Low). 
2. **The Hound (Receiver)**: A portable tracking device used by the player. It provides two forms of feedback: a visual 5x5 LED bar graph indicating raw signal strength (distance/direction), and an auditory beep that increases in frequency as the player enters higher-power transmission zones.

## 2. Intended Functionality

The Hound provides a nuanced "hot and cold" tracking experience through the combination of auditory and visual feedback:

* **Audio Zones (Coarse Tracking)**: As the player gets closer to the Fox, the Hound picks up weaker, lower-power beacons. It plays a slow beep when only the strongest beacon is heard, a medium beep for the middle beacon, and a rapid alarm when the weakest beacon is detected.
* **Visual Bar Graph (Fine Tracking)**: The LED matrix displays the raw Signal Strength (RSSI). To ensure responsiveness, the visual display utilizes an **Exponential Moving Average (EMA)** smoothing filter (80% new data / 20% historical data) to eliminate erratic multipath radio bouncing while maintaining a <300ms reaction time to physical movement.
* **The Attenuator**: The visual bar graph is deliberately calibrated to saturate (fill 5 bars) when the player is still several meters away from the Fox. When saturated, the player presses **Button A** to add digital attenuation, desensitizing the meter so they can continue tracking the signal peak at close range. **Button B** resets the attenuation to zero.

## 3. Architecture & Code Mapping

The codebase is strictly decoupled to separate physical hardware interactions from the underlying state machine, enabling robust unit testing.

### `fox.py` (The Beacon)
A lightweight procedural script. It loops infinitely, setting `radio.config(power=X)` and broadcasting string identifiers (`"Z1"`, `"Z2"`, `"Z3"`). It explicitly clears any attached ZIP/NeoPixels on Pin 0 to remain hidden.

### `hound_logic.py` (The State Machine)
Contains the `HoundController` class. This is a pure-Python state machine completely decoupled from the micro:bit hardware. 
* **Input Mapping**: Takes in button states (`process_inputs`), raw radio strings, signal strengths, and timestamps (`process_packet`). 
* **Signal Isolation**: Explicitly isolates the `Z1` (Max Power) beacon for RSSI distance calculation to prevent the bar graph from oscillating in sync with the Fox's dropping transmit power cycle.
* **Output Generation**: Exposes `get_beep_to_play()` and `get_display_bars()` which calculate timeouts, smoothing, and attenuation offsets.
* **Testing**: Accompanied by `test_hound.py`, a comprehensive `pytest` suite that simulates radio packet backlogs, out-of-order zones, and timeouts deterministically.

### `hound.py` (The Hardware Integration)
The main execution loop for the receiver. 
* **Event Loop**: It instantiates the `HoundController` and maps physical hardware events (buttons, radio queue, system clock) into the state machine.
* **Queue Draining**: Contains a critical inner `while True:` loop to drain the entire `radio.receive_full()` hardware queue on every tick. This prevents asynchronous packets from backing up when the main loop is blocked by synchronous audio playback.
* **Hardware Output**: Drives the LED matrix by explicitly overwriting pixel brightness (avoiding `display.clear()` flicker) and triggers `music.pitch()`.

---

## 4. Hardware Quirks & Gotchas

During development, several micro:bit hardware limitations were discovered and mitigated:

1. **MicroPython Radio Headers**: `radio.receive_full()` returns raw bytes, which includes a hidden 3-byte MicroPython header (`\x01\x00\x01`). Strict string equality (`==`) fails; the code must use the `in` operator (e.g., `if "Z1" in payload:`).
2. **Varying Transmit Power vs RSSI**: Because the Fox cycles transmit power to create audio zones, the Hound will receive packets with artificially fluctuating RSSI values. The Hound's bar graph is programmed to *only* update its distance calculation upon receiving the `Z1` (Max Power) beacon.
3. **Pin 0 Audio Cross-talk**: On the micro:bit v2, the built-in speaker is physically hardwired to the Pin 0 edge connector. Calling `music.pitch()` sends electrical PWM signals down Pin 0, which causes attached ZIP/NeoPixels to flash randomly. 
    * *Mitigation 1*: Audio calls must explicitly use `pin=None` (e.g., `music.pitch(400, 100, pin=None)`).
    * *Mitigation 2*: Because cross-talk is unavoidable at a hardware level, `np.clear()` and `np.show()` are called immediately after every beep to prevent the LEDs from staying stuck on.
4. **NeoPixel Startup State**: ZIP LEDs often power on in a random state. `neopixel.clear()` followed by `neopixel.show()` is explicitly called on boot in both scripts to guarantee stealth.
5. **LED Matrix Flicker**: The micro:bit LED matrix is multiplexed. Calling `display.clear()` inside a rapid loop causes the hardware to physically turn off for a microsecond, creating a harsh strobe effect. The code avoids this by explicitly overwriting pixel states (`0` or `9`).
6. **`uflash` Firmware Downgrade**: The CLI tool `uflash` (v2.0.0) bundles the older micro:bit v1 firmware. Flashing a v2 board with `uflash` silently downgrades it to v1, disabling the built-in speaker. Code must be flashed using `microfs` (`ufs put script.py main.py`) to preserve the correct firmware.
