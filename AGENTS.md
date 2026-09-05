# Micro:bit Fox Hunt Game

This project implements an "Amateur Radio Direction Finding" (ARDF) style fox hunt game for BBC micro:bit v2s. 

## What the Code Does
- **The Fox (Transmitter)**: Rapidly loops through three transmit power levels (Max, Medium, Low), sending a corresponding zone identifier ("Z1", "Z2", "Z3"). Its screen is kept dark to remain hidden.
- **The Hound (Receiver)**: Listens for radio packets. It uses the highest received zone to play audio beeps (slow for Z1, fast for Z3) and maps the raw signal strength (RSSI) to a 5x5 LED bar graph. 
- **The Attenuator**: The Hound includes an attenuator to dynamically adjust the sensitivity of the LED meter. The `MAX_RSSI` is calibrated to `-70` so that the meter maxes out when the player is still a few meters away. When the screen fills, players press **Button A** to add 5 points of attenuation (desensitizing the meter) to track the signal closer. **Button B** instantly resets the attenuation to 0.

## Project Structure
- `fox.py`: The lightweight transmitter script.
- `hound.py`: The complex receiver script that integrates the pure logic state machine with hardware calls.
- `hound_logic.py`: A pure-Python state machine (`HoundController`) decoupled from hardware, allowing for deterministic testing of the timeout logic, string parsing, and attenuator math.
- `test_hound.py`: A comprehensive `pytest` suite that asserts the logic of `hound_logic.py`.
- `run_integration_test.py`: A host-side Python script that connects to the micro:bits over USB to verify they are communicating correctly over the radio.
- `fox_hunt_plan.md`: The initial design artifact.

## How to Use It
1. Use the [official micro:bit Python editor](https://python.microbit.org/v/2) or a tool like `microfs` (`ufs`) to copy the code to the boards. **Do not use `uflash` for micro:bit v2 devices** (see Gotchas below).
2. Connect both micro:bits to battery packs.
3. Hide the Fox.
4. Give the Hound to players. The screen will light up more as they get closer. If the screen completely fills, they press **Button A** to add attenuation. If they lose the signal, they press **Button B** to reset it.

## Gotchas to Avoid in the Future

1. **MicroPython Radio Headers**: `radio.receive_full()` returns raw bytes. MicroPython prepends a 3-byte header (`\x01\x00\x01`) to all radio packets. Do not use strict equality (`==`) when comparing string payloads. Use the `in` operator (e.g., `if "Z1" in payload:`) to safely ignore the header.
2. **`uflash` Downgrades Firmware**: The `uflash` CLI tool relies on a bundled `.hex` firmware. Older versions of `uflash` (like v2.0.0) bundle the **micro:bit v1** firmware. Flashing a v2 board with `uflash` will downgrade it to v1, causing the built-in speaker and other v2 features to fail silently. Use `microfs` (`ufs put script.py main.py`) to safely push code without destroying the firmware.
3. **Pin 0 Audio Interference**: By default, the micro:bit v2 mirrors its speaker audio output as an analog PWM signal to the edge connector Pin 0 (for v1 headphone compatibility). If you have NeoPixels/ZIP LEDs connected to Pin 0, the audio signal will cause them to flash wildly. You must explicitly set `pin=None` in audio calls (e.g., `music.pitch(400, 100, pin=None)`) to prevent this.
4. **NeoPixel Startup State**: ZIP LEDs/NeoPixels can sometimes retain state or power on randomly. We explicitly import `neopixel` and call `np.clear()` at the top of the scripts to guarantee they are dark.
5. **Radio Packet Backlog**: If your main loop uses blocking operations (like a 100ms audio beep or sleep), the radio queue can quickly back up since packets arrive asynchronously. Always use an inner `while True:` loop to drain and process all pending `radio.receive_full()` packets before advancing the rest of your hardware logic.
