from microbit import *
import radio
import music

speaker.on()
set_volume(255)


# Initialize Radio
radio.on()
radio.config(group=42)

# --- State Variables ---
attenuation_offset = 0
last_packet_time = running_time()
highest_zone = 0
current_rssi = -105
last_audio_time = running_time()

# --- Display Constants ---
MIN_RSSI = -105
MAX_RSSI = -40

def draw_bar_graph(rssi, offset):
    # Apply attenuation. 
    # E.g., if RSSI is -50 (strong) and we add 20 attenuation, we treat it as -70.
    adjusted_rssi = rssi - offset
    
    # Calculate percentage (0.0 to 1.0)
    percentage = (adjusted_rssi - MIN_RSSI) / (MAX_RSSI - MIN_RSSI)
    percentage = max(0.0, min(1.0, percentage)) # Clamp between 0 and 1
    
    # Map to 5 rows (0 bars to 5 bars)
    num_bars = int(percentage * 5)
    if percentage > 0 and num_bars == 0:
        num_bars = 1 # Always show at least 1 bar if signal is > MIN_RSSI
        
    display.clear()
    # Draw from bottom (y=4) to top (y=0)
    for y in range(5):
        if 4 - y < num_bars:
            for x in range(5):
                display.set_pixel(x, y, 9)

def play_zone_audio(zone):
    # Using wait=False ensures the tone plays in the background
    # and doesn't block the loop from receiving radio packets.
    if zone == 1:
        music.pitch(400, 100)
    elif zone == 2:
        music.pitch(800, 100)
    elif zone == 3:
        music.pitch(1200, 100)

while True:
    now = running_time()
    
    # --- 1. Input Handling (Attenuator) ---
    if button_a.was_pressed():
        # Increase attenuation (make screen less sensitive)
        attenuation_offset += 5
    if button_b.was_pressed():
        # Decrease attenuation (make screen more sensitive)
        attenuation_offset -= 5
        
    # --- 2. Radio Processing ---
    packet = radio.receive_full()
    if packet:
        msg = packet[0]
        rssi = packet[1]
        
        if msg:
            try:
                # Decode byte array to string
                msg_str = str(msg, 'utf-8')
                
                # Update tracking variables
                current_rssi = rssi
                last_packet_time = now
                
                # Keep track of the highest zone seen between audio beeps
                if "Z3" in msg_str:
                    highest_zone = 3
                elif "Z2" in msg_str:
                    highest_zone = max(highest_zone, 2)
                elif "Z1" in msg_str:
                    highest_zone = max(highest_zone, 1)
            except:
                pass
                
    # --- 3. Timeout Logic ---
    if now - last_packet_time > 1000:
        # Signal lost!
        highest_zone = 0
        current_rssi = MIN_RSSI
        
    # --- 4. Audio Generation ---
    beep_interval = 0
    if highest_zone == 1:
        beep_interval = 1000 # Slow beep
    elif highest_zone == 2:
        beep_interval = 500  # Medium beep
    elif highest_zone == 3:
        beep_interval = 200  # Fast alarm
        
    if beep_interval > 0:
        if now - last_audio_time > beep_interval:
            play_zone_audio(highest_zone)
            last_audio_time = now
            # Reset zone tracking so we have to hear it again before the next beep
            highest_zone = 0 
            
    # --- 5. Visual Update ---
    draw_bar_graph(current_rssi, attenuation_offset)
    
    # Small pause to prevent the loop from overwhelming the CPU
    sleep(10)
