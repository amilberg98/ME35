from machine import Pin, SoftI2C, ADC, PWM
import time
import math
import neopixel
import veml6040

# =====================================================================
# CONFIG - everything you should need to tune lives here
# =====================================================================

# --- Block detection (light sensor) ---
LIGHT_THRESHOLD = 3000       # ADC reading BELOW this = block present
LIGHT_SAMPLES = 4            # average this many ADC reads per check
SETTLE_MS = 150              # wait for the block to stop moving before reading colour

# --- Colour sensor ---
READS_PER_SAMPLE = 5         # average this many sensor reads per block
SENSOR_INTEGRATION_MS = 40   # VEML6040 default integration time (40 ms)
SATURATION = 65000           # 16-bit counts near this = sensor saturated

# --- KNN ---
MIN_SAMPLES_PER_COLOR = 5
K = 3
BRIGHTNESS_SCALE = 30000.0   # roughly the R+G+B total you see for a bright block
BRIGHTNESS_WEIGHT = 0.5      # how much overall brightness matters vs. hue (0 = ignore)

# --- Servos ---
SERVO_MIN_US = 500           # pulse width at 0 deg   (try 1000 if your servo buzzes/jams)
SERVO_MAX_US = 2500          # pulse width at 180 deg (try 2000 if your servo buzzes/jams)

BIN_ANGLES = {               # sorter servo angle for each bin - CALIBRATE THESE
    "red": 0,
    "green": 45,
    "blue": 90,
    "yellow": 135,
    "other/black": 180,
}
SORTER_TRAVEL_MS = 600       # time for sorter to swing to position (was 300 - too short for 180 deg)
CATCHER_HOLD_ANGLE = 180
CATCHER_DROP_ANGLE = 0
CATCHER_DROP_MS = 1000

COLORS = ("red", "green", "blue", "yellow", "other/black")

# =====================================================================
# HARDWARE
# =====================================================================

# NOTE: GPIO 34 and 35 are INPUT-ONLY on the ESP32 and have NO internal
# pull-up. They MUST have an external ~10k pull-up resistor to 3.3V or
# they will float and fire random interrupts.
buttons = {
    "red":         Pin(16, Pin.IN, Pin.PULL_UP),
    "green":       Pin(17, Pin.IN, Pin.PULL_UP),
    "blue":        Pin(18, Pin.IN, Pin.PULL_UP),
    "yellow":      Pin(33, Pin.IN, Pin.PULL_UP),
    "other/black": Pin(34, Pin.IN),   # external pull-up required
}
transition_btn = Pin(35, Pin.IN)      # external pull-up required

lightsensor = ADC(Pin(25, Pin.IN))
lightsensor.atten(ADC.ATTN_11DB)

np = neopixel.NeoPixel(Pin(15), 1)

servo_catcher = PWM(Pin(4), freq=50, duty_u16=0)
servo_sorter = PWM(Pin(5), freq=50, duty_u16=0)

i2c = SoftI2C(scl=Pin(22), sda=Pin(21))
sensor = veml6040.VEML6040(i2c)


def set_status_led(color):
    """'red' = still training, 'green' = enough data / sorting."""
    np[0] = {"red": (50, 0, 0), "green": (0, 50, 0)}.get(color, (0, 0, 0))
    np.write()


def servo_write(servo, angle):
    angle = max(0, min(180, angle))
    us = SERVO_MIN_US + (SERVO_MAX_US - SERVO_MIN_US) * angle / 180.0
    servo.duty_u16(int(us / 20000.0 * 65535))


def init_servos():
    servo_write(servo_catcher, CATCHER_HOLD_ANGLE)
    servo_write(servo_sorter, BIN_ANGLES["red"])


def sort_to_bin(color):
    """Swing the sorter to the bin, then open and re-close the catcher."""
    print("Sorter -> %s (%d deg)" % (color, BIN_ANGLES[color]))
    servo_write(servo_sorter, BIN_ANGLES[color])
    time.sleep_ms(SORTER_TRAVEL_MS)
    servo_write(servo_catcher, CATCHER_DROP_ANGLE)
    time.sleep_ms(CATCHER_DROP_MS)
    servo_write(servo_catcher, CATCHER_HOLD_ANGLE)


# =====================================================================
# BUTTONS (interrupt driven, debounced)
# =====================================================================
DEBOUNCE_MS = 200
_last_press = {name: 0 for name in COLORS}
_last_press["transition"] = 0
button_flags = {name: False for name in COLORS}
button_flags["transition"] = False
_pin_to_name = {id(pin): name for name, pin in buttons.items()}
_pin_to_name[id(transition_btn)] = "transition"


def clear_button_flags():
    for k in button_flags:
        button_flags[k] = False


def _button_irq(pin):
    name = _pin_to_name.get(id(pin))
    if name is None:
        return
    now = time.ticks_ms()
    if time.ticks_diff(now, _last_press[name]) > DEBOUNCE_MS and pin.value() == 0:
        button_flags[name] = True
        _last_press[name] = now


for _p in buttons.values():
    _p.irq(trigger=Pin.IRQ_FALLING, handler=_button_irq)
transition_btn.irq(trigger=Pin.IRQ_FALLING, handler=_button_irq)


def wait_for_color_button():
    """Block until a colour button is pressed. Returns None if the
    transition button is pressed instead (= discard this sample)."""
    clear_button_flags()
    while True:
        for color in COLORS:
            if button_flags[color]:
                clear_button_flags()
                return color
        if button_flags["transition"]:
            clear_button_flags()
            return None
        time.sleep_ms(10)


# =====================================================================
# SENSORS
# =====================================================================
def light_level():
    total = 0
    for _ in range(LIGHT_SAMPLES):
        total += lightsensor.read()
    return total // LIGHT_SAMPLES


def block_present():
    return light_level() < LIGHT_THRESHOLD


def read_color():
    """Trigger a fresh measurement each time and average several reads."""
    rs = gs = bs = ws = 0
    for _ in range(READS_PER_SAMPLE):
        sensor.trigger_measurement()
        time.sleep_ms(SENSOR_INTEGRATION_MS + 10)
        r, g, b, w = sensor.read_rgbw()
        rs += r; gs += g; bs += b; ws += w
    n = READS_PER_SAMPLE
    r, g, b, w = rs / n, gs / n, bs / n, ws / n
    if max(r, g, b, w) >= SATURATION:
        print("[!] Sensor is SATURATED - lower the integration time or move the block further away")
    return r, g, b, w


# =====================================================================
# KNN
# =====================================================================
data = []  # list of (features_tuple, label)
sample_counts = {c: 0 for c in COLORS}


def features(r, g, b, w):
    """Convert raw counts to a distance-friendly feature vector.

    Raw RGB counts are dominated by how BRIGHT the reading is (block
    distance, ambient light), not what colour it is. Normalising by the
    total gives a 'chromaticity' that describes the hue only, and we add
    a small scaled brightness term so black/dark blocks are still separable.
    """
    s = r + g + b
    if s <= 0:
        return (0.0, 0.0, 0.0, 0.0)
    bright = min(s / BRIGHTNESS_SCALE, 1.0) * BRIGHTNESS_WEIGHT
    return (r / s, g / s, b / s, bright)


def knn(feat, k=K, verbose=True):
    if not data:
        return None
    neighbors = []
    for f, label in data:
        d = math.sqrt(sum((a - b) ** 2 for a, b in zip(feat, f)))
        neighbors.append((d, label))
    neighbors.sort(key=lambda t: t[0])
    neighbors = neighbors[:min(k, len(neighbors))]

    # Distance-weighted vote: closer neighbours count more, and it breaks ties.
    votes = {}
    for d, label in neighbors:
        votes[label] = votes.get(label, 0.0) + 1.0 / (d + 1e-6)
    winner = max(votes, key=votes.get)

    if verbose:
        print("  nearest:", ["%s (%.3f)" % (l, d) for d, l in neighbors])
    return winner


def training_complete():
    return all(sample_counts[c] >= MIN_SAMPLES_PER_COLOR for c in COLORS)


def print_progress():
    print("--- Progress ---")
    for c in COLORS:
        print("  %-12s %d/%d" % (c.upper(), sample_counts[c], MIN_SAMPLES_PER_COLOR))


# =====================================================================
# MODES
# =====================================================================
MODE_TRAIN = "train"
MODE_SORT = "sort"
mode = MODE_TRAIN


def handle_transition():
    """Called whenever the transition button flag is set."""
    global mode
    button_flags["transition"] = False
    if mode == MODE_TRAIN:
        if training_complete():
            mode = MODE_SORT
            set_status_led("green")
            print("\n" + "=" * 50)
            print("*** SORTING MODE ***")
            print("=" * 50)
        else:
            print("[!] Need at least %d samples per colour first." % MIN_SAMPLES_PER_COLOR)
            print_progress()
    else:
        mode = MODE_TRAIN
        set_status_led("green" if training_complete() else "red")
        print("\n*** Back to TRAINING mode (adding more samples) ***")


def process_block():
    print("\n--- Block detected ---")
    time.sleep_ms(SETTLE_MS)
    if not block_present():
        print("(false trigger, block gone)")
        return

    r, g, b, w = read_color()
    feat = features(r, g, b, w)
    print("Raw: R=%d G=%d B=%d W=%d   norm: r=%.3f g=%.3f b=%.3f" %
          (r, g, b, w, feat[0], feat[1], feat[2]))

    if mode == MODE_TRAIN:
        # Show what the model would currently guess - useful sanity check.
        guess = knn(feat, verbose=False)
        if guess:
            print("(model currently thinks: %s)" % guess)
        print(">>> Press the colour button for this block (transition button = discard)")
        label = wait_for_color_button()
        if label is None:
            print("Sample discarded.")
            return
        data.append((feat, label))
        sample_counts[label] += 1
        print("Logged [%s] (%d total)" % (label, sample_counts[label]))
        print_progress()
        if training_complete():
            set_status_led("green")
            print("READY - press transition button to start sorting, or keep training.")
    else:
        label = knn(feat)
        print(">>> SORTED AS: [%s]" % label)

    if label:
        sort_to_bin(label)


# =====================================================================
# MAIN
# =====================================================================
set_status_led("red")
init_servos()

print("Booted into TRAINING mode. Need %d samples per colour." % MIN_SAMPLES_PER_COLOR)
print_progress()

while True:
    if button_flags["transition"]:
        handle_transition()

    if block_present():
        process_block()
        # wait for the block to clear, still honouring the transition button
        while block_present():
            if button_flags["transition"]:
                handle_transition()
            time.sleep_ms(50)

    time.sleep_ms(50)
