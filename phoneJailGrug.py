import time
from machine import Pin, ADC, SoftI2C, Timer, PWM
import lis3dh
import math


# ==========================================
# HELPER FUNCTIONS & INTERRUPT
# ==========================================

def servo_angle(angle):
    # Servo Pulse width map: 0.5ms (0 deg) to 2.5ms (180 deg)
    pulseWidth = 0.5 + (((180 - angle) / 180) * 2) 
    servo.duty_u16(int((pulseWidth / 20) * 65535))

def pitch_roll():
    """Computes pitch and roll in degrees from X, Y, Z acceleration."""
    x, y, z = sensor.read_xyz()
    roll = math.atan2(y, z) * (180.0 / math.pi)
    pitch = math.atan2(-x, math.sqrt(y * y + z * z)) * (180.0 / math.pi)
    return pitch, roll

def play_tone(freq, duration_ms):
    """Plays a specific frequency tone for a given duration"""
    if freq > 0:
        buzzer.freq(freq)
        buzzer.duty(512)  # 50% duty cycle (loudest volume)
    else:
        buzzer.duty(0)
        
    time.sleep_ms(duration_ms)
    buzzer.duty(0)  # Turn off
    time.sleep_ms(50)  # Brief gap

def success_sound():
    """Super Mario Bros. Level Completed Fanfare"""
    notes = [
        (523, 120),  # C5
        (659, 120),  # E5
        (784, 120),  # G5
        (1047, 120), # C6
        (880, 120),  # A5
        (988, 120),  # B5
        (1047, 400)  # C6 (held)
    ]
    for freq, duration in notes:
        play_tone(freq, duration)

def failure_sound():
    # Crisp, punchy opening notes
    play_tone(147, 280)  # Wah 1 (D3)
    play_tone(139, 280)  # Wah 2 (C#3)
    play_tone(131, 280)  # Wah 3 (C3)
    
    # Deep, dramatic final slide down into the abyss (123 Hz down to 98 Hz)
    for freq in range(123, 97, -1):
        buzzer.freq(freq)
        buzzer.duty(512)
        time.sleep_ms(30)  # Slower, lingering drag on the final note
        
    # Shut off the buzzer completely at the end
    buzzer.duty(0)

def multiplex_callback(timer):
    global current_digit
    
    # 1. Turn off both digits (blanking)
    digit_pins[0].value(0)
    digit_pins[1].value(0)
    
    # 2. Get tens or units based on current_digit
    if current_digit == 0:
        number = counter // 10
    else:
        number = counter % 10
        
    # 3. Output segment pattern
    seg_pattern = NUMBERS[number]
    for j in range(7):
        segment_pins[j].value(seg_pattern[j])
        
    # 4. Turn on the active digit
    digit_pins[current_digit].value(1)
    
    # 5. Flip to the other digit for the next tick
    current_digit = 1 - current_digit  # Toggles between 0 and 1

# ==========================================
# CONSTANTS & CONFIGURATION
# ==========================================
# State machine: 0 = Standby, 1 = Studying, 2 = Failure, 3 = Finished Studying
STATE = 0

# Segment encoding for numbers 0-9 (Common Anode / Active LOW)
NUMBERS = {
    0: [0, 0, 0, 0, 0, 0, 1],
    1: [1, 0, 0, 1, 1, 1, 1],
    2: [0, 0, 1, 0, 0, 1, 0],
    3: [0, 0, 0, 0, 1, 1, 0],
    4: [1, 0, 0, 1, 1, 0, 0],
    5: [0, 1, 0, 0, 1, 0, 0],
    6: [0, 1, 0, 0, 0, 0, 0],
    7: [0, 0, 0, 1, 1, 1, 1],
    8: [0, 0, 0, 0, 0, 0, 0],
    9: [0, 0, 0, 0, 1, 0, 0]
}

# ==========================================
# HARDWARE INITIALIZATION
# ==========================================
# Button setup
btn = Pin(35, Pin.IN)

def button_handler(pin):
    global STATE
    if STATE == 0:
        STATE = 1

btn.irq(trigger=Pin.IRQ_FALLING, handler=button_handler)

# I2C & LIS3DH Accelerometer
i2c = SoftI2C(scl=Pin(22), sda=Pin(21))
sensor = lis3dh.LIS3DH(i2c)

# Joysticks (ADC)
vrx = ADC(Pin(39))
vry = ADC(Pin(32))
vrx.atten(ADC.ATTN_11DB)
vry.atten(ADC.ATTN_11DB)

# 7-Segment Display Pins
segment_pins = [Pin(p, Pin.OUT) for p in [4, 14, 27, 2, 25, 33, 15]]
digit_pins = [Pin(18, Pin.OUT), Pin(19, Pin.OUT)]

# Initialize buzzer on GPIO 23
buzzer = PWM(Pin(23))
buzzer.duty(0)  # Ensure it starts off

# Servo to Pin D4, 50Hz PWM, 20 ms duty cycle
servo = PWM(Pin(5), freq=50, duty_u16=0)
servo_angle(100)

# Setup a hardware timer (Timer 0) AFTER variables are initialized
display_timer = Timer(0)
display_timer.init(period=8, mode=Timer.PERIODIC, callback=multiplex_callback)


# ==========================================
# STATE & TIMING VARIABLES
# ==========================================
counter = 0
center = 1870
deadzone = 50

last_count_time = 0
current_delay_ms = 500  # Default slow rate

current_digit = 0


# ==========================================
# MAIN LOOP & STATE FUNCTIONS
# ==========================================

def standby():
    global STATE, counter, last_count_time, current_delay_ms
    while STATE == 0:
        # Check joystick and update counter based on elapsed time (non-blocking)
        raw_y = vry.read()
        offset =  center - raw_y
        now = time.ticks_ms()
        
        if abs(offset) > deadzone:
            magnitude = min(abs(offset), 2048)
            current_delay_ms = max(30, 500 - (magnitude / 4.45))
            
            if time.ticks_diff(now, last_count_time) > current_delay_ms:
                if offset > 0:
                    counter += 1
                else:
                    counter -= 1
                    
                counter = max(0, min(counter, 99))
                last_count_time = now
                print(f"Count: {counter} | Delay: {current_delay_ms:.1f}ms")
        else:
            last_count_time = now
        
def studying():
    global STATE, counter
    
    # Get reference starting point
    resting_pitch, resting_roll = pitch_roll()
    
    # Track timing for the 1-minute countdown decrement
    last_minute_tick = time.ticks_ms()
    
    print(f"Studying session started. Initial count: {counter}")
    
    while STATE == 1:
        # 1. Check current orientation against baseline
        pitch, roll = pitch_roll()
        
        # If posture/orientation shifts by MORE than 20 degrees -> Failure
        if abs(pitch - resting_pitch) > 20 or abs(roll - resting_roll) > 20:
            print("Posture deviated > 20°! Entering Failure state.")
            STATE = 2  # Failure state
            break
            
        # 2. Check if counter has hit 0 -> Pass / Finished Studying
        if counter <= 0:
            print("Study session completed successfully!")
            STATE = 3  # Finished Studying state
            break
            
        # 3. Decrement counter every 1 minute (60,000 ms)
        now = time.ticks_ms()
        if time.ticks_diff(now, last_minute_tick) >= 1000:  # 60,000ms = 1 minute
            counter = max(0, counter - 1)
            print(f"1 minute passed. Counter remaining: {counter}")
            last_minute_tick = now
            
        # Small delay so the CPU isn't pegged at 100% 
        # (The hardware timer continues refreshing the 7-segment display in the background)
        time.sleep_ms(100)


while True:
    if STATE == 0:    # Standby
        standby()
    elif STATE == 1:  # Studying
        studying()
    elif STATE == 2:  # Failure
        failure_sound()
        servo_angle(0)
        time.sleep_ms(400)
        servo_angle(100)
        STATE = 0
    elif STATE == 3:  # Finished Studying
        success_sound()
        servo_angle(0)
        time.sleep_ms(400)
        servo_angle(100)
        STATE = 0
    else:
        STATE = 0