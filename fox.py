from microbit import *
import radio
import neopixel
np = neopixel.NeoPixel(pin0, 5)
np.clear()
np.show()


# Initialize Radio
radio.on()
radio.config(group=42)

# Turn off the display so the Fox stays hidden
display.off()

while True:
    # --- Zone 1 (Heard furthest away) ---
    radio.config(power=7)  # Max power
    radio.send("Z1")
    sleep(50)
    
    # --- Zone 2 (Heard at medium distance) ---
    radio.config(power=4)  # Medium power
    radio.send("Z2")
    sleep(50)
    
    # --- Zone 3 (Heard only when very close) ---
    radio.config(power=1)  # Low power
    radio.send("Z3")
    sleep(100)
    
    # Total loop time ~ 200ms
