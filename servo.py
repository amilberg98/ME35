from machine import Pin, PWM
servo = PWM(Pin(18), freq=50, duty_u16=0)
angle1 = 180

pulseWidth = 0.5 + (((angle1) / 180) * 2) 
servo.duty_u16(int((pulseWidth / 20) * 65535))