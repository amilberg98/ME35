from machine import Pin, PWM, disable_irq, enable_irq
import time
import math
import gc
import json
import network
import _thread
import requests
import secrets

L1, L2 = 10.0, 8.0          # arm link lengths
DEG_PER_COUNT = .05         # servo degrees per encoder count
HOME1, HOME2 = 90.0, 90.0   # servo angles the arm starts at

SEND_INTERVAL_MS = 100

MATE_IDS = {
    "Revolute 1": "MpfOOC6h38nFu3MAD",
    "Revolute 2": "M/nbqdyZ7Cw/6S+M+",
}

# Latest angles in radians, shared between the control loop and the sender thread
lock = _thread.allocate_lock()
latest = [math.radians(HOME1), math.radians(HOME2)]


class Count(object):
    def __init__(self, A, B):
        self.A = Pin(A, Pin.IN)
        self.B = Pin(B, Pin.IN)
        self.counter = 0

        self.A.irq(self.cb, self.A.IRQ_FALLING | self.A.IRQ_RISING)  # interrupt on line A
        self.B.irq(self.cb, self.B.IRQ_FALLING | self.B.IRQ_RISING)  # interrupt on line B

    def cb(self, msg):
        other, inc = (self.B, 1) if msg == self.A else (self.A, -1)  # define other line and increment
        self.counter += -inc if msg.value() != other.value() else inc

    def delta(self):
        # counts since the last call, then start counting again from 0
        state = disable_irq()          # stop interrupts so no count is lost mid-read
        d = self.counter
        self.counter = 0
        enable_irq(state)
        return d

def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("Connecting to WiFi...")
        wlan.connect(secrets.SSID)
        while not wlan.isconnected():
            time.sleep(0.5)
    print("Connected! IP address:", wlan.ifconfig()[0])
    return wlan


def servo(pwm, deg):
    us = 500 + 2000 * deg / 180                  # 0-180 deg -> 0.5-2.5 ms pulse
    pwm.duty_u16(int(us * 65535 / 20000))


def tip(a1, a2):
    # forward kinematics: tip = R(t1)[L1,0] + R(t1+t2)[L2,0]
    t1 = math.radians(a1)
    t2 = math.radians(a2 - 90)                   # elbow servo 90 = arm straight
    x = L1 * math.cos(t1) + L2 * math.cos(t1 + t2)
    y = L1 * math.sin(t1) + L2 * math.sin(t1 + t2)
    return x, y

def post_angles(angle_1, angle_2):   
    data = {
        "mateValues": [
            {"jsonType": "Revolute", "featureId": MATE_IDS["Revolute 1"],
             "mateName": "Revolute 1", "ownerOccurrencePath": [],
             "rotationZ": angle_1},
            {"jsonType": "Revolute", "featureId": MATE_IDS["Revolute 2"],
             "mateName": "Revolute 2", "ownerOccurrencePath": [],
             "rotationZ": angle_2},
        ]
    }
    response = None
    start = time.ticks_ms()
    try:
        response = requests.post(
            secrets.onshape_url,
            auth=(secrets.onshape_access_key, secrets.onshape_secret_key),
            json=data,
        )
        elapsed = time.ticks_diff(time.ticks_ms(), start)
        if response.status_code == 200:
            print("[POST] OK   R1 {:>7.4f} rad  R2 {:>7.4f} rad  ({} ms)".format(
                angle_1, angle_2, elapsed))
        else:
            print("[POST] ERROR", response.status_code)
            try:
                print("   ", str(json.loads(response.text).get("message", ""))[:200])
            except ValueError:
                print("   ", response.text[:200])
    except Exception as e:
        print("[POST] failed:", e)
    finally:
        if response is not None:
            response.close()
        gc.collect()


def sender(wlan):
    """Background thread: sends the latest angles at most every SEND_INTERVAL_MS."""
    last_sent = None
    while True:
        start = time.ticks_ms()

        if not wlan.isconnected():
            print("[WIFI] reconnecting...")
            connect_wifi()

        lock.acquire()
        r1, r2 = latest[0], latest[1]
        lock.release()

        # Only send when something actually changed
        if (last_sent is None
                or abs(r1 - last_sent[0]) > 1e-4
                or abs(r2 - last_sent[1]) > 1e-4):
            post_angles(r1, r2)
            last_sent = (r1, r2)

        elapsed = time.ticks_diff(time.ticks_ms(), start)
        time.sleep_ms(max(0, SEND_INTERVAL_MS - elapsed))


# ---------- Main ----------
wlan = connect_wifi()

enc_shoulder = Count(32, 39)
enc_elbow = Count(25, 33)      # must not share a pin with enc_shoulder
s1 = PWM(Pin(4), freq=50)
s2 = PWM(Pin(18), freq=50)

# start at the 0 point, wherever the encoders happen to be
a1, a2 = HOME1, HOME2
servo(s1, a1)
servo(s2, a2)
time.sleep(1)
enc_shoulder.delta()           # throw away any counts from start-up
enc_elbow.delta()

# HTTPS needs a bigger stack than the default thread stack
_thread.stack_size(16 * 1024)
_thread.start_new_thread(sender, (wlan,))

while True:
    d1 = enc_shoulder.delta()
    d2 = enc_elbow.delta()
    if d1 or d2:
        a1 = max(0, min(180, a1 + d1 * DEG_PER_COUNT))
        a2 = max(0, min(180, a2 + d2 * DEG_PER_COUNT))
        servo(s1, a1)
        servo(s2, a2)
        x, y = tip(a1, a2)
        print("shoulder=%.1f elbow=%.1f  tip x=%.1f y=%.1f" % (a1, a2, x, y))

        # Hand the new angles to the sender thread instead of posting here
        lock.acquire()
        latest[0] = math.radians(a2 - 90)
        latest[1] = math.radians(-1*a1)
        lock.release()

    time.sleep_ms(10)