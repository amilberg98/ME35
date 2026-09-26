from machine import Pin, SoftI2C, ADC, PWM
import time
import math
import neopixel
import veml6040

# --- Hardware Configuration ---
redColor = Pin(16, Pin.IN, Pin.PULL_UP)
greenColor = Pin(17, Pin.IN, Pin.PULL_UP)
blueColor = Pin(18, Pin.IN, Pin.PULL_UP)
yellowColor = Pin(33, Pin.IN, Pin.PULL_UP)
otherColor = Pin(34, Pin.IN)

transistionBtn = Pin(35, Pin.IN)

light_pin = Pin(25, Pin.IN)
lightsensor = ADC(light_pin)
lightsensor.atten(ADC.ATTN_11DB)  # Full scale ~0-3.3V

np = neopixel.NeoPixel(Pin(15), 1)

servoCatcher = PWM(Pin(4), freq=50, duty_u16=0)
servoSorter = PWM(Pin(5), freq=50, duty_u16=0)


def set_status_led(color):
    """Sets status LED: 'red' = needs training, 'green' = ready/sorting."""
    if color == "red":
        np[0] = (50, 0, 0)
    elif color == "green":
        np[0] = (0, 50, 0)
    else:
        np[0] = (0, 0, 0)
    np.write()


set_status_led("red")

# Initialize I2C & VEML6040 Color Sensor
i2c = SoftI2C(scl=Pin(22), sda=Pin(21))
sensor = veml6040.VEML6040(i2c)
sensor.trigger_measurement()

# --- Global States & Flags ---
DEBOUNCE_MS = 200
last_press_trans = 0
last_press_color = 0

STATE_TRAIN = True
STATE_PLAY = False

LIGHT_THRESHOLD = 3000
MIN_SAMPLES_PER_COLOR = 5

data = []  # Holds (R, G, B, label) tuples

sample_counts = {
    "red": 0,
    "green": 0,
    "blue": 0,
    "yellow": 0,
    "other/black": 0
}

button_flags = {
    "transition": False,
    "red": False,
    "green": False,
    "blue": False,
    "yellow": False,
    "other/black": False
}

color_angles = {
    "red": 0,
    "green": 45,
    "blue": 90,
    "yellow": 135,
    "other/black": 180
}


def clear_button_flags():
    """Resets all button flags to False."""
    for button in button_flags:
        button_flags[button] = False


def button_handler(pin):
    """Debounced IRQ handler with separate timing for transition vs colors."""
    global last_press_trans, last_press_color
    now = time.ticks_ms()

    if pin == transistionBtn:
        if time.ticks_diff(now, last_press_trans) > DEBOUNCE_MS:
            if pin.value() == 0:
                button_flags["transition"] = True
                last_press_trans = now
    else:
        if time.ticks_diff(now, last_press_color) > DEBOUNCE_MS:
            if pin.value() == 0:
                if pin == redColor:
                    button_flags["red"] = True
                elif pin == greenColor:
                    button_flags["green"] = True
                elif pin == blueColor:
                    button_flags["blue"] = True
                elif pin == yellowColor:
                    button_flags["yellow"] = True
                elif pin == otherColor:
                    button_flags["other/black"] = True
                last_press_color = now


# Attach IRQs
redColor.irq(trigger=Pin.IRQ_FALLING, handler=button_handler)
greenColor.irq(trigger=Pin.IRQ_FALLING, handler=button_handler)
blueColor.irq(trigger=Pin.IRQ_FALLING, handler=button_handler)
yellowColor.irq(trigger=Pin.IRQ_FALLING, handler=button_handler)
otherColor.irq(trigger=Pin.IRQ_FALLING, handler=button_handler)
transistionBtn.irq(trigger=Pin.IRQ_FALLING, handler=button_handler)


def get_pressed_color():
    """Waits until a color button IRQ sets a flag."""
    clear_button_flags()
    selected_color = None
    color_keys = ("red", "green", "blue", "yellow", "other/black")

    while selected_color is None:
        for color in color_keys:
            if button_flags[color]:
                selected_color = color
                break
        time.sleep(0.01)

    clear_button_flags()
    return selected_color


def initilizeServos():
    duty = int((2.5 / 20.0) * 65535)  # 180 deg
    servoCatcher.duty_u16(duty)
    duty = int((0.5 / 20.0) * 65535)  # 0 deg
    servoSorter.duty_u16(duty)


def sortColor(color):
    """Moves sorter servo to destination angle and triggers catcher servo."""
    pulse_ms = 0.5 + (color_angles[color] / 180.0) * 2.0
    duty = int((pulse_ms / 20.0) * 65535)
    servoSorter.duty_u16(duty)

    time.sleep(0.3)  # Give sorter servo time to position

    duty_release = int((0.5 / 20.0) * 65535)  # Drop position
    servoCatcher.duty_u16(duty_release)
    time.sleep(1.0)

    duty_reset = int((2.5 / 20.0) * 65535)  # Reset position
    servoCatcher.duty_u16(duty_reset)


def k_nearest_neighbor(x, y, z, k=3):
    if not data:
        return "No Data"
    distances = []
    for d in data:
        dist = math.sqrt((x - d[0])**2 + (y - d[1])**2 + (z - d[2])**2)
        distances.append([dist, d[3]])
    distances.sort()
    k_neighbors = distances[:min(k, len(distances))]
    classes = [dist[1] for dist in k_neighbors]
    return max(set(classes), key=classes.count)


def check_training_status():
    """Returns True if every color has AT LEAST the required sample count."""
    for count in sample_counts.values():
        if count < MIN_SAMPLES_PER_COLOR:
            return False
    return True


def trigger_color_read():
    global STATE_TRAIN, STATE_PLAY
    colorLabel = None

    if lightsensor.read() >= LIGHT_THRESHOLD:
        return

    print("\n--- Block Detected! Reading Color Sensor ---")
    red, green, blue, white = sensor.read_rgbw()
    print(f"Raw RGB Read: R={red}, G={green}, B={blue}")

    # --- TRAINING MODE ---
    if STATE_TRAIN:
        print(">>> Waiting for color button press (Red, Green, Blue, Yellow, Other)...")
        colorLabel = get_pressed_color()

        data.append((red, green, blue, colorLabel))
        sample_counts[colorLabel] += 1
        print(f"SUCCESS: Logged [{colorLabel}] sample (Total: {sample_counts[colorLabel]})")

        print("--- Progress Summary ---")
        for c, count in sample_counts.items():
            print(f"  {c.upper()}: {count}/{MIN_SAMPLES_PER_COLOR} minimum")

        if check_training_status():
            set_status_led("green")
            print("\n" + "="*50)
            print("READY TO GO INTO SORTING MODE")
            print("Press Pin 35 to transition, or keep scanning to add more training samples.")
            print("="*50)
        else:
            set_status_led("red")

    # --- PLAY MODE ---
    elif STATE_PLAY:
        colorLabel = k_nearest_neighbor(red, green, blue, k=3)
        print(f">>> SORTING RESULT: Block is [{colorLabel}] <<<")

    # --- EXECUTE SERVO MOVE IN BOTH MODES ---
    if colorLabel and colorLabel != "No Data":
        sortColor(colorLabel)


# --- Main Program Execution Loop ---
print("System booted into TRAINING mode.")
print(f"Collect at least {MIN_SAMPLES_PER_COLOR} samples for each color.")
initilizeServos()

while True:
    # Check transition button state
    if button_flags["transition"]:
        button_flags["transition"] = False
        if STATE_TRAIN:
            if check_training_status():
                STATE_TRAIN = False
                STATE_PLAY = True
                set_status_led("green")
                print("\n" + "="*50)
                print("*** TRANSITIONING TO SORTING MODE ***")
                print("System is now ready to auto-classify blocks.")
                print("="*50)
            else:
                print(f"\n[!] CANNOT TRANSITION: You need at least {MIN_SAMPLES_PER_COLOR} samples per color class first.")

    # Trigger scan when light threshold is crossed
    if lightsensor.read() < LIGHT_THRESHOLD:
        trigger_color_read()

        # Wait until block clears, but check for transition requests in the background
        while lightsensor.read() < LIGHT_THRESHOLD:
            if button_flags["transition"]:
                button_flags["transition"] = False
                if STATE_TRAIN and check_training_status():
                    STATE_TRAIN = False
                    STATE_PLAY = True
                    set_status_led("green")
                    print("\n" + "="*50)
                    print("*** TRANSITIONING TO SORTING MODE ***")
                    print("="*50)
            time.sleep(0.05)

    time.sleep(0.05)