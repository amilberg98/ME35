"""
Color Trainer & Tester - Robo ESP32 + VEML6040 (MicroPython)
Trains the center sensor on black, red, green, blue, white, 
saves the data to colors.json, and continuously tests classifications.
"""

from machine import Pin, SoftI2C
import time
import math
import sys
import select

try:
    import json
except ImportError:
    import ujson as json

# =====================================================================
# CONFIG
# =====================================================================
CENTER_I2C = (22, 21)       # Center sensor pins (scl, sda)
BUTTON_PIN = None           # Onboard button GPIO if available, else None

SENSOR_INTEGRATION_MS = 40
TRAIN_COLORS = ("black", "red", "green", "blue", "white")
SAMPLES_PER_COLOR = 10
BRIGHTNESS_WEIGHT = 1.0
SAVE_FILE = "colors.json"

MARKER_MAX_DIST = 0.4
BLACK_THRESHOLD = 300  # Adjust this based on your black vs blue 'w' readings


# =====================================================================
# INPUT HELPERS
# =====================================================================
button = Pin(BUTTON_PIN, Pin.IN, Pin.PULL_UP) if BUTTON_PIN is not None else None
_stdin_poll = select.poll()
_stdin_poll.register(sys.stdin, select.POLLIN)

def read_console():
    chars = []
    while _stdin_poll.poll(40):
        chars.append(sys.stdin.read(1))
    return "".join(chars).strip().lower()

def flush_console():
    while _stdin_poll.poll(0):
        sys.stdin.read(1)

def wait_go(msg, timeout_s=None):
    flush_console()
    print(msg + ("  [ENTER or button]" if button else "  [ENTER]"))
    start = time.ticks_ms()
    while True:
        if button is not None and button.value() == 0:
            time.sleep_ms(30)
            while button.value() == 0:
                time.sleep_ms(10)
            return True
        if _stdin_poll.poll(20):
            read_console()
            return True
        if timeout_s is not None and time.ticks_diff(time.ticks_ms(), start) > timeout_s * 1000:
            return False

# =====================================================================
# SENSOR & COLOR LOGIC
# =====================================================================
class VEML6040:
    ADDR = 0x10
    CONF = 0x02
    TRIG = 0x04

    def __init__(self, i2c):
        self.i2c = i2c
        self._conf(self.CONF)

    def _conf(self, value):
        self.i2c.writeto_mem(self.ADDR, 0x00, bytes([value, 0x00]))

    def _word(self, reg):
        d = self.i2c.readfrom_mem(self.ADDR, reg, 2)
        return d[0] | (d[1] << 8)

    def trigger_measurement(self):
        self._conf(self.CONF | self.TRIG)

    def read_rgbw(self):
        return (self._word(0x08), self._word(0x09), self._word(0x0A), self._word(0x0B))

bus = SoftI2C(scl=Pin(CENTER_I2C[0]), sda=Pin(CENTER_I2C[1]), freq=100000)
if 0x10 not in bus.scan():
    raise RuntimeError("Center VEML6040 not found on pins %s" % str(CENTER_I2C))
center_s = VEML6040(bus)

def read_center():
    center_s.trigger_measurement()
    time.sleep_ms(SENSOR_INTEGRATION_MS + 10)
    return center_s.read_rgbw()

color_means = {}
color_refs = {}
white_w = 1.0

def features(r, g, b, w):
    sw = w if w > 0 else 1e-6
    return (r / sw, g / sw, b / sw, BRIGHTNESS_WEIGHT * w / white_w)

def build_refs():
    global white_w, color_refs
    white_w = max(color_means.get("white", (0, 0, 0, 1))[3],
                  max(m[3] for m in color_means.values()), 1)
    color_refs = {c: features(*m) for c, m in color_means.items()}

def train_colors():
    global color_means
    color_means = {}
    print("\n" + "=" * 50)
    print("COLOUR TRAINING (centre sensor)")
    print("=" * 50)
    for color in TRAIN_COLORS:
        wait_go("Put the CENTRE sensor over [%s]" % color.upper())
        sums = [0.0, 0.0, 0.0, 0.0]
        seen = set()
        for i in range(SAMPLES_PER_COLOR):
            rgbw = read_center()
            seen.add(rgbw)
            if max(rgbw) >= 65000:
                print("  [!] saturated - raise the sensor a little")
            for j in range(4):
                sums[j] += rgbw[j]
        if len(seen) == 1:
            print("  [!] all samples identical - sensor may not be re-measuring")
        color_means[color] = tuple(s / SAMPLES_PER_COLOR for s in sums)
        print("  %s mean RGBW: %s" % (color, tuple(int(v) for v in color_means[color])))
    build_refs()
    try:
        with open(SAVE_FILE, "w") as f:
            json.dump(color_means, f)
        print("Saved training to", SAVE_FILE)
    except OSError:
        print("[!] couldn't save training to file")

def classify_center(rgbw):
    r, g, b, w = rgbw

    if w < BLACK_THRESHOLD:
        return "black"
    
    if not color_refs:
        return None

    f = features(*rgbw)
    best, best_d = None, 1e9
    for c, ref in color_refs.items():
        if c == "black": 
            continue  # Handled by brightness check above
        d = math.sqrt(sum((a - b) ** 2 for a, b in zip(f, ref)))
if d < best_d:
            best, best_d = c, d

    # Uncomment line below if you want to inspect match distances during testing:
    # print(f"Closest: {best} (dist: {best_d:.2f})")

    return best if best_d < MARKER_MAX_DIST else None

def test_colors():
    print("\n" + "=" * 50)
    print("CONTINUOUS LIVE TEST: Move sensor across surfaces.")
    print("Press Ctrl+C to stop.")
    print("=" * 50)
    try:
        while True:
            rgbw = read_center()
            classified = classify_center(rgbw)
            raw_int = tuple(int(v) for v in rgbw)
            print("Class: %-8s | Raw RGBW: %s" % (str(classified), str(raw_int)))
            time.sleep_ms(150)  # Brief pause between continuous readings
    except KeyboardInterrupt:
        print("\nTest mode ended.")

# =====================================================================
# STARTUP
# =====================================================================
try:
    train_colors()
    test_colors()
    print("Program finished.")
except KeyboardInterrupt:
    print("\nProgram stopped.")