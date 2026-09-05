from microbit import *
import radio
import music

from radio_config import RADIO_GROUP

radio.on()
radio.config(group=RADIO_GROUP)
print("HOUND_START")

while True:
    packet = radio.receive_full()
    if packet:
        msg = packet[0]
        rssi = packet[1]
        if msg:
            try:
                msg_str = str(msg, 'utf-8')
                print("HOUND_RX:", msg_str, "RSSI:", rssi)
            except:
                pass
    sleep(10)
