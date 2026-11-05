# Yeller (peripheral)

from BLE_CEEO import Yell
import time
import json
import lis3dh
import math
from machine import Pin, SoftI2C, PWM
from neopixel import NeoPixel

NAME = "Justin"
buffer = b"" 

# Initialize SoftI2C bus
i2c = SoftI2C(scl=Pin(22), sda=Pin(21))
sensor = lis3dh.LIS3DH(i2c)

def pitch_roll():
    """
    Computes pitch and roll in degrees from the X, Y, and Z acceleration values.
    """
    x, y, z = sensor.read_xyz()
    
    # Calculate roll (rotation around X-axis)
    roll = math.atan2(y, z) * (180.0 / math.pi)
    
    # Calculate pitch (rotation around Y-axis)
    pitch = math.atan2(-x, math.sqrt(y * y + z * z)) * (180.0 / math.pi)
    
    pitch *= 1.1111
    roll *= 1.1111
    
    roll = max(-100.0, min(100.0, roll))
    pitch = max(-100.0, min(100.0, pitch))
    
    return pitch, roll


# =====================================================================
# NEOPIXELS & SPEAKER
# =====================================================================

NEOPIXEL_PIN = 15
NUM_PIXELS = 2
BUZZER_PIN = 23

pixels = NeoPixel(Pin(NEOPIXEL_PIN), NUM_PIXELS)

finish_line = False
COOLDOWN_MS = 1500


def set_pixels(r, g, b):
    for i in range(NUM_PIXELS):
        pixels[i] = (r, g, b)
    pixels.write()


buzzer = PWM(Pin(BUZZER_PIN), freq=1000, duty=0)

JINGLE = ((523, 120), (659, 120), (784, 120), (1047, 300))   # (Hz, ms): C E G high-C

def play_jingle():
    for freq, ms in JINGLE:
        buzzer.freq(freq)
        buzzer.duty_u16(32768)
        time.sleep_ms(ms)
        buzzer.duty_u16(0)
        time.sleep_ms(30)


def callback(data):
    global buffer, finish_line  # <--- Added finish_line here so it modifies the global variable
    buffer += data
    while b"\n" in buffer:
        line, buffer = buffer.split(b"\n", 1)
        parsed_data = json.loads(line.decode())
        print("Received:", parsed_data)
        
        if parsed_data.get("color") == "red":
            finish_line = True
        else:
            finish_line = False


p = None
try:
    p = Yell(NAME, interval_us=30000, verbose=False)
    p.callback = callback

    print("Waiting for a listener...")
    if p.connect_up():
        print("Connected")
        now = time.ticks_ms() - COOLDOWN_MS  # Initialize so it can play immediately on the first red if wanted
        
        while p.is_connected:
            pitch, roll = pitch_roll()
            
            payload = json.dumps({"pitch": pitch, "roll": roll}) + "\n"

            # Send in 20-byte pieces (the default packet size)
            for start in range(0, len(payload), 20):
                p.send(payload[start:start + 20])
                time.sleep_ms(20)

            # Fixed ticks_diff check: compares current time against 'now'
            if finish_line and (time.ticks_diff(time.ticks_ms(), now) >= COOLDOWN_MS):
                play_jingle()
                now = time.ticks_ms()  # Reset cooldown timer
                
            time.sleep(.1)
            
    print("Lost connection")
finally:
    if p:
        p.disconnect()