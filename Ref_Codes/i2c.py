from machine import Pin, SoftI2C
import time
import veml6040  # Import driver module
import lis3dh
import math

# --- ESP32 Hardware Configuration ---
# Note: Pins 34 & 35 do not have internal pull-ups.
# Ensure you have external pull-up resistors wired on these pins if using active-low switches.
button_Play = Pin(34, Pin.IN)
button_Train = Pin(35, Pin.IN)

# Initialize SoftI2C bus
i2c = SoftI2C(scl=Pin(22), sda=Pin(21))

# Initialize VEML6040 sensor object with I2C bus
#sensor = veml6040.VEML6040(i2c)
sensor = lis3dh.LIS3DH(i2c)

# --- Color Sensor Settings ---
READS_PER_SAMPLE = 5         # Average this many sensor reads per block
SENSOR_INTEGRATION_MS = 40   # VEML6040 default integration time (40 ms)
SATURATION = 65000           # 16-bit counts near this = sensor saturated


def read_color():
    """Triggers fresh measurements and returns averaged raw channels."""
    rs = gs = bs = ws = 0
    for _ in range(READS_PER_SAMPLE):
        sensor.trigger_measurement()
        time.sleep_ms(SENSOR_INTEGRATION_MS + 10)
        r, g, b, w = sensor.read_rgbw()
        rs += r
        gs += g
        bs += b
        ws += w
        
    n = READS_PER_SAMPLE
    r, g, b, w = rs / n, gs / n, bs / n, ws / n
    
    if max(r, g, b, w) >= SATURATION:
        print("[!] Sensor is SATURATED - lower the integration time or move the block further away")
        
    return r, g, b, w
    
    
def pitch_roll():
    """
    Computes pitch and roll in degrees from the X, Y, and Z acceleration values.
    """
    x, y, z = sensor.read_xyz()
    
    # Calculate roll (rotation around X-axis)
    roll = math.atan2(y, z) * (180.0 / math.pi)
    
    # Calculate pitch (rotation around Y-axis)
    pitch = math.atan2(-x, math.sqrt(y * y + z * z)) * (180.0 / math.pi)
    
    return pitch, roll
    

# --- Main Loop ---
while True:
    
    pitch, roll = pitch_roll()
    
    print(f"Pitch: {pitch}     Roll: {roll}")
    