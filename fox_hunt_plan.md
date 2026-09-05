# Micro:bit Fox Hunt Game Plan

## 1. System Requirements

### Hardware
*   **Transmitter (The Fox):** 1x BBC micro:bit v2, battery pack.
*   **Receiver(s) (The Hound):** 1+ BBC micro:bit v2, battery pack(s).
*   **Power:** Standard 2xAAA NiMH rechargeable batteries (approx. 800-1000mAh) per device.

### Functional Requirements
*   **The Fox:** Must continuously transmit a signal that allows receivers to determine distance. Must remain dark (no LED display) to stay hidden. Must operate for at least 2 hours on a single battery charge.
*   **The Hound:** 
    *   **Audio Feedback:** Must play distinct tones indicating which "Zone" the user is in (based on transmit power level received). Must go silent if the signal is lost.
    *   **Visual Feedback:** Must display the raw signal strength (RSSI) as a bar graph on the 5x5 LED matrix.
    *   **Attenuator:** Must use buttons A and B to adjust the baseline sensitivity of the LED bar graph, allowing users to measure small changes in RSSI when very close to the transmitter.

## 2. Implementation Plan

### Environment
*   **Language:** MicroPython (or MakeCode, to be decided). MicroPython is recommended for precise control over timing, radio packets, and audio generation.

### Phase 1: The Fox (Transmitter) Logic
1.  **Initialize:** Set a specific radio group (e.g., `radio.config(group=42)`). Turn off the LED display.
2.  **Main Loop (approx. 200ms cycle):**
    *   Set radio transmit power to High (7). Transmit "Z1". Pause 50ms.
    *   Set radio transmit power to Medium (4). Transmit "Z2". Pause 50ms.
    *   Set radio transmit power to Low (1). Transmit "Z3". Pause 100ms.

### Phase 2: The Hound (Receiver) Logic
1.  **Initialize:** Join the same radio group. Initialize variables for `attenuation_offset = 0`, `last_packet_time = 0`, `highest_zone = 0`, `current_rssi = -105`.
2.  **Radio Event Listener:**
    *   On packet receive: Record `last_packet_time = current_time`. Update `current_rssi` from packet metadata.
    *   If packet is "Z3", set `highest_zone = 3`. If "Z2", set `highest_zone = 2`. If "Z1", set `highest_zone = 1`.
3.  **UI Loop (Background/Main Loop):**
    *   **Timeout Check:** If `current_time - last_packet_time > 1000ms`, set `highest_zone = 0` and clear screen.
    *   **Audio Generation:** 
        *   Zone 0: Silent.
        *   Zone 1: Slow, low-pitched beep (e.g., 400Hz every 1 sec).
        *   Zone 2: Faster, medium-pitched beep (e.g., 800Hz every 500ms).
        *   Zone 3: Rapid, high-pitched alarm (e.g., 1200Hz every 100ms).
    *   **Visual Generation:**
        *   Calculate normalized strength: `display_val = current_rssi + attenuation_offset`.
        *   Map `display_val` to the 5 rows of the LED matrix.
    *   **Input Handling:**
        *   Button A pressed: `attenuation_offset -= 5` (De-sensitize / Attenuate).
        *   Button B pressed: `attenuation_offset += 5` (Increase sensitivity).

## 3. Testing Criteria

### Bench Testing (Indoors)
*   **Battery Test:** Run the Fox for 2.5 hours on fresh rechargeable batteries. Ensure it is still transmitting at the end.
*   **Timeout Test:** Turn off the Fox. Verify the Hound goes completely silent and the screen clears within ~1 second.
*   **Attenuator Test:** Place Fox and Hound right next to each other (signal maxed out). Press Button A repeatedly and verify the LED bar graph drops down row by row.

### Field Testing (Outdoors / Game Environment)
*   **Zone Thresholds:** Walk away from the Fox in an open area. Mark the distances where the audio drops from Zone 3 -> 2, and Zone 2 -> 1. Ensure the zones are distinct and not overlapping erratically.
*   **Usability:** Give the Hound to a tester without prior explanation (beyond "follow the sound and use A if the screen fills up"). Verify they can successfully locate the Fox.

## 4. Known Gotchas & Considerations
*   **Multipath Interference:** Indoors, radio waves bounce off metal and walls. RSSI will fluctuate wildly. This game works *much* better outdoors in an open field or woods.
*   **Omnidirectional Antenna:** The micro:bit antenna does not care which way it is pointing. Users *must* use their body to block the signal (body shielding) to determine direction, or simply walk and observe if RSSI goes up or down.
*   **Attenuator Math:** The exact mapping of RSSI (usually -105 to -40) to the 5 LED rows, and the step size of the attenuator buttons, will require tuning during bench testing to feel "right" to the user.
*   **Audio Blocking:** In MicroPython, standard `music.play()` blocks the execution loop. Audio will need to be handled carefully (perhaps using the `audio` module for asynchronous playback, or playing very short tones) so it doesn't prevent the radio from listening for incoming packets.
