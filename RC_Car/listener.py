# Listener (central)

from BLE_CEEO import Listen
from machine import Pin, PWM, I2C, SoftI2C
import time, json, math
import veml6040

NAME = "Justin"     # must match the yeller's name
buffer = b""

DRIVE_SPEED = 1     # forward speed while on the line (0-1)
leftSpeed = 0
rightSpeed = 0

# motor pins
left_fwd  = PWM(Pin(27), freq=20000, duty_u16=0)
left_rev  = PWM(Pin(14), freq=20000, duty_u16=0)
right_fwd = PWM(Pin(12), freq=20000, duty_u16=0)
right_rev = PWM(Pin(13), freq=20000, duty_u16=0)

i2c = I2C(0, sda=Pin(21), scl=Pin(22), freq=400000)
print("I2C devices:", i2c.scan())
sensor = veml6040.VEML6040(i2c)
sensor.set_integration_time(veml6040.IT_80MS)   # must match knn_test.py

# ----------- DRIVING FUNCS -----------
def _set(fwd, rev, speed):
    speed = max(-1.0, min(1.0, speed))
    if speed >= 0:
        rev.duty_u16(0)                      # turn the other side off first
        fwd.duty_u16(int(speed * 65535))
    else:
        fwd.duty_u16(0)
        rev.duty_u16(int(-speed * 65535))

def drive(left, right):
    _set(left_fwd, left_rev, left)
    _set(right_fwd, right_rev, right)

def stop():
    for p in (left_fwd, left_rev, right_fwd, right_rev):
        p.duty_u16(0)
# --------- COLOR SENSING ---------
K = 5
CONFIRM_LINE = 2       # reads in a row before floor <-> black/color is believed

# sensor init
_last = {}
_bad = [0]

def read_safe(sensor):
    """Retry a failed read; reuse the last good one for a brief glitch."""
    for _ in range(4):
        try:
            _last[id(sensor)], _bad[0] = sensor.read_rgbw(), 0
            return _last[id(sensor)]
        except OSError:
            time.sleep_ms(3)
    _bad[0] += 1
    if _bad[0] > 25 or id(sensor) not in _last:
        raise OSError("sensor stopped answering: check cable and battery")
    return _last[id(sensor)]

with open("knn.json") as f:
    KNN = json.load(f)          # [[r/w, g/w, b/w], label] ...

def classify(rgbw):
    r, g, b, w = rgbw
    if w <= 0:
        return "black"          # no light at all: treat as dark
    x, y, z = r / w, g / w, b / w
    best = []                   # K nearest as (dist, label)
    for (px, py, pz), lab in KNN:
        d = (px - x) ** 2 + (py - y) ** 2 + (pz - z) ** 2
        if len(best) < K or d < best[-1][0]:
            best.append((d, lab))
            best.sort()
            if len(best) > K:
                best.pop()
    votes = {}
    for _, lab in best:
        votes[lab] = votes.get(lab, 0) + 1
    return max(votes, key=votes.get)

# --------- BLE -------------
def callback(data):
    # Pieces arrive in up to 20-byte chunks; a newline ends each message
    global buffer
    buffer += data
    while b"\n" in buffer:
        line, buffer = buffer.split(b"\n", 1)

        try:
            accel = json.loads(line.decode())
            pitch = accel["pitch"] / 100
            roll = accel["roll"] / 200
        except (ValueError, KeyError, UnicodeError):
            print("bad line:", line)     # helps you see what's arriving
            continue

        leftSpeed = max(-DRIVE_SPEED, min(DRIVE_SPEED, DRIVE_SPEED*(pitch + roll)))
        rightSpeed = max(-DRIVE_SPEED, min(DRIVE_SPEED, DRIVE_SPEED*(pitch - roll)))

        drive(leftSpeed, rightSpeed)



# -----------------------------------
p = None
try:
    p = Listen(NAME, verbose=False)
    p.callback = callback

    print("Looking for", NAME, "...")
    if p.connect_up():
        print("Connected")
        while p.is_connected:
            lab = classify(read_safe(sensor))
            payload = json.dumps({"color": lab}) + "\n"

            # Send in 20-byte pieces (the default packet size)
            for start in range(0, len(payload), 20):
                p.send(payload[start:start + 20])
                time.sleep_ms(20)

            time.sleep(0.1)
    print("Lost connection")
finally:
    if p:
        p.disconnect()