MIN_RSSI = -105
MAX_RSSI = -70

class HoundController:
    def __init__(self):
        self.attenuation_offset = 0
        self.last_packet_time = 0
        self.highest_zone = 0
        self.current_rssi = MIN_RSSI
        self.last_audio_time = 0
        
    def process_inputs(self, button_a, button_b):
        if button_a:
            self.attenuation_offset += 5
        if button_b:
            self.attenuation_offset = 0
            
    def process_packet(self, msg_str, rssi, now):
        if self.current_rssi <= MIN_RSSI:
            self.current_rssi = rssi
        else:
            self.current_rssi = (self.current_rssi * 0.8) + (rssi * 0.2)
        self.last_packet_time = now
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
