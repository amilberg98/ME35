from machine import ADC, Pin, SoftI2C
import time
lightsensor = ADC(Pin(25))

i2c = SoftI2C(scl = Pin(22), sda = Pin(21))


while True:
    print(lightsensor.read_u16())
    time.sleep(.1)