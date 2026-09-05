MIN_RSSI = -105
MAX_RSSI = -40

def calculate_num_bars(rssi, offset):
    adjusted_rssi = rssi - offset
    percentage = (adjusted_rssi - MIN_RSSI) / (MAX_RSSI - MIN_RSSI)
    percentage = max(0.0, min(1.0, percentage))
    num_bars = int(percentage * 5)
    if percentage > 0 and num_bars == 0:
        num_bars = 1
    return num_bars

def calculate_highest_zone(msg_str, current_zone):
    if msg_str == "Z3":
        return 3
    elif msg_str == "Z2":
        return max(current_zone, 2)
    elif msg_str == "Z1":
        return max(current_zone, 1)
    return current_zone

def get_beep_interval(zone):
    if zone == 1: return 1000
    if zone == 2: return 500
    if zone == 3: return 200
    return 0
