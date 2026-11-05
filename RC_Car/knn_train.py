# knn_train.py -- MicroPython, ESP32. Timed KNN training, no buttons.
# Saves knn.json after every color: [[[nr, ng, nb], label], ...]
from machine import Pin, I2C
import time, json, os
import veml6040

COLORS = ["floor", "red"]   # edit to your colors
PREP_SECONDS = 5
SAMPLE_SECONDS = 3
SAMPLE_MS = 100
FILE = "knn.json"

i2c = I2C(0, sda=Pin(21), scl=Pin(22), freq=400000)
print("I2C devices:", i2c.scan())
sensor = veml6040.VEML6040(i2c)
sensor.set_integration_time(veml6040.IT_80MS)   # must match knn_test.py

data = []
for name in COLORS:
    print("\n>>> Next color: '%s'" % name)
    for s in range(PREP_SECONDS, 0, -1):
        print("  get ready... %d" % s)
        time.sleep(1)
    print("  SAMPLING '%s' -- hold at driving height, wiggle slightly" % name)

    n = 0
    sums = [0.0, 0.0, 0.0]
    end = time.ticks_add(time.ticks_ms(), SAMPLE_SECONDS * 1000)
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        r, g, b, w = sensor.read_rgbw()
        if w > 0:
            f = [r / w, g / w, b / w]
            data.append([f, name])
            n += 1
            for i in range(3):
                sums[i] += f[i]
        time.sleep_ms(SAMPLE_MS)

    if n:
        print("  got %d samples, mean rgb/w = (%.3f, %.3f, %.3f)" % (n, sums[0] / n, sums[1] / n, sums[2] / n))
    else:
        print("  WARNING: no valid samples for", name)

    with open(FILE, "w") as f:          # save progress after each color
        json.dump(data, f)
    print("  saved so far:", len(data), "samples")

print("\nDone. Files on board:", os.listdir())
print("%s size: %d bytes" % (FILE, os.stat(FILE)[6]))