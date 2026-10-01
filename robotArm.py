from machine import Pin, PWM, disable_irq, enable_irq
import time
import math
 
L1, L2 = 10.0, 8.0      # arm link lengths
DEG_PER_COUNT = .05     # servo degrees per encoder count
HOME1, HOME2 = 90.0, 90.0  # servo angles the arm starts at
 
 
class Count(object):
    def __init__(self,A,B):
        self.A = Pin(A, Pin.IN)
        self.B = Pin(B, Pin.IN)
        self.counter = 0
 
        self.A.irq(self.cb,self.A.IRQ_FALLING|self.A.IRQ_RISING) #interrupt on line A
        self.B.irq(self.cb,self.B.IRQ_FALLING|self.B.IRQ_RISING) #interrupt on line B
 
    def cb(self,msg):
        other,inc = (self.B,1) if msg == self.A else (self.A,-1) #define other line and increment
        self.counter += -inc if msg.value()!=other.value() else  inc 
 
    def delta(self):
        # counts since the last call, then start counting again from 0
        state = disable_irq()          # stop interrupts so no count is lost mid-read
        d = self.counter
        self.counter = 0
        enable_irq(state)
        return d
 
 
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
 
 
enc_shoulder = Count(32, 33)
enc_elbow = Count(25, 26)      # must not share a pin with enc_shoulder
s1 = PWM(Pin(4), freq=50)
s2 = PWM(Pin(18), freq=50)
 
# start at the 0 point, wherever the encoders happen to be
a1, a2 = HOME1, HOME2
servo(s1, a1)
servo(s2, a2)
time.sleep(1)
enc_shoulder.delta()           # throw away any counts from start-up
enc_elbow.delta()
 
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
 
    time.sleep(0.02)