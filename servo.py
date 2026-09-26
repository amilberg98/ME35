from machine import Pin, PWM
servo = PWM(Pin(4), freq=50, duty_u16=0)
servo2 = PWM(Pin(5), freq=50, duty_u16=0)
angle1 = 0
pulseWidth = 0.5 + (((angle1) / 180) * 2) 
servo.duty_u16(int((pulseWidth / 20) * 65535))