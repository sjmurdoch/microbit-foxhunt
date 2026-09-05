from microbit import *
import radio
import music
import neopixel
np = neopixel.NeoPixel(pin0, 5)
np.clear()
np.show()

speaker.on()
set_volume(255)

radio.on()
radio.config(group=42)

MIN_RSSI = -105
MAX_RSSI = -70

class HoundController:
    def __init__(self):
        self.attenuation_offset = 0
        self.last_packet_time = 0
        self.highest_zone = 0
        self.current_rssi = MIN_RSSI
        self.last_audio_time = running_time()
        
    def process_inputs(self, button_a, button_b):
        if button_a:
            self.attenuation_offset += 5
        if button_b:
            self.attenuation_offset = 0
            
    def process_packet(self, msg_str, rssi, now):
        self.last_packet_time = now
        
        # ONLY use the Z1 (Max Power) packet to determine distance!
        if "Z1" in msg_str:
            if self.current_rssi <= MIN_RSSI:
                self.current_rssi = rssi
            else:
                self.current_rssi = (self.current_rssi * 0.8) + (rssi * 0.2)
                
        if "Z3" in msg_str:
            self.highest_zone = 3
        elif "Z2" in msg_str:
            self.highest_zone = max(self.highest_zone, 2)
        elif "Z1" in msg_str:
            self.highest_zone = max(self.highest_zone, 1)
            
    def check_timeout(self, now):
        if now - self.last_packet_time > 1000:
            self.highest_zone = 0
            self.current_rssi = MIN_RSSI
            
    def get_beep_to_play(self, now):
        beep_interval = 0
        if self.highest_zone == 1: beep_interval = 1000
        elif self.highest_zone == 2: beep_interval = 500
        elif self.highest_zone == 3: beep_interval = 200
        
        if beep_interval > 0 and now - self.last_audio_time > beep_interval:
            zone_to_play = self.highest_zone
            self.last_audio_time = now
            self.highest_zone = 0
            return zone_to_play
        return 0
        
    def get_display_bars(self):
        if self.current_rssi <= MIN_RSSI and self.attenuation_offset == 0:
            return 0
        adjusted_rssi = self.current_rssi - self.attenuation_offset
        percentage = (adjusted_rssi - MIN_RSSI) / (MAX_RSSI - MIN_RSSI)
        percentage = max(0.0, min(1.0, percentage))
        num_bars = int(percentage * 5)
        if percentage > 0 and num_bars == 0:
            num_bars = 1
        return num_bars

controller = HoundController()
last_bars = -1

while True:
    now = running_time()
    
    # 1. Inputs
    controller.process_inputs(button_a.was_pressed(), button_b.was_pressed())
    
    # 2. Process ALL pending radio packets
    while True:
        packet = radio.receive_full()
        if not packet:
            break
        msg = packet[0]
        if msg:
            try:
                msg_str = str(msg, 'utf-8')
                controller.process_packet(msg_str, packet[1], now)
            except:
                pass
                
    # 3. Timeout
    controller.check_timeout(now)
    
    # 4. Audio
    zone_to_play = controller.get_beep_to_play(now)
    if zone_to_play > 0:
        if zone_to_play == 1: music.pitch(400, 100, pin=None)
        elif zone_to_play == 2: music.pitch(800, 100, pin=None)
        elif zone_to_play == 3: music.pitch(1200, 100, pin=None)
        
    # 5. Visuals
    bars = controller.get_display_bars()
    if bars != last_bars:
        for y in range(5):
            if 4 - y < bars:
                for x in range(5):
                    display.set_pixel(x, y, 9)
            else:
                for x in range(5):
                    display.set_pixel(x, y, 0)
        last_bars = bars
                
    sleep(10)
