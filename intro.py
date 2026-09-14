import neopixel
import machine
from machine import Pin
import time
from time import ticks_ms, ticks_diff

# RoboESP32 NeoPixel data: GPIO15, 2 pixels total
np = neopixel.NeoPixel(machine.Pin(15), 2)

# Button logic
btn = Pin(34, Pin.IN, Pin.PULL_UP)
btn2 = Pin(35, Pin.IN, Pin.PULL_UP)
DEBOUNCE_MS = 200
last_press = 0


def func(np):
    n = np.n

    # cycle (one white pixel moving)
    for i in range(4 * n):
        for j in range(n):
            np[j] = (0, 0, 0)
        np[i % n] = (255, 255, 255)
        np.write()
        time.sleep_ms(100)

    # bounce (dark pixel on blue background)
    for i in range(4 * n):
        for j in range(n):
            np[j] = (0, 0, 128)

        if (i // n) % 2 == 0:
            np[i % n] = (0, 0, 0)
        else:
            np[n - 1 - (i % n)] = (0, 0, 0)

        np.write()
        time.sleep_ms(60)

    # fade in/out (red)
    for i in range(0, 4 * 256, 8):
        for j in range(n):
            if (i // 256) % 2 == 0:
                val = i & 0xff
            else:
                val = 255 - (i & 0xff)
            np[j] = (val, 0, 0)

        np.write()
        time.sleep_ms(20)

    # clear
    for j in range(n):
        np[j] = (0, 0, 0)
    np.write()

def button_handler(pin):
    global last_press
    now = ticks_ms()
    if ticks_diff(now, last_press) > DEBOUNCE_MS:
        if (pin.value() == 0):
            last_press = now
            print("Button", pin,"pressed!")
            for j in range(3):
                np[0] = (255, 255, 255)
                np[1] = (255, 255, 255)
                np.write()
                time.sleep_ms(200)
                np[0] = (0, 0, 0)
                np[1] = (0, 0, 0)
                np.write()
                time.sleep_ms(200)
            
            
btn.irq(trigger=Pin.IRQ_FALLING, handler=button_handler)
btn2.irq(trigger=Pin.IRQ_FALLING, handler=button_handler)

while True:
    func(np)