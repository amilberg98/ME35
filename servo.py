from machine import Pin, PWM
servo = PWM(Pin(4), freq=50, duty_u16=0)
angle = 90
pulseWidth = 0.5 + (((180 - angle) / 180) * 2) 
servo.duty_u16(int((pulseWidth / 20) * 65535))