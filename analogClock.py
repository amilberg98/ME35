import network
import urequests
import machine
import time
import neopixel
import gc
from machine import Pin
import secrets

# ----------------------------------------------------
# 1. SETUP & CONFIGURATION
# ----------------------------------------------------
def connect_wifi(SSID, PASSWORD):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("Connecting to WiFi...")
        wlan.connect(SSID, PASSWORD)
        timeout = 0
        while not wlan.isconnected() and timeout < 20:
            time.sleep(0.5)
            timeout += 1
            
    if wlan.isconnected():
        print("Connected! IP:", wlan.ifconfig()[0])
    else:
        print("WiFi Connection Failed!")
    return wlan

# State variables
state = 0  # 0 = clock, 1 = sunrise, 2 = sunset
pm = False
button_pressed_flag = False

# Hardware peripherals
np = neopixel.NeoPixel(Pin(15), 2)
btn = Pin(34, Pin.IN)   # Ensure external pull-up resistor is present on GPIO 34
btn2 = Pin(35, Pin.IN)  # Ensure external pull-up resistor is present on GPIO 35

DEBOUNCE_MS = 200
last_press = 0

# ----------------------------------------------------
# 2. INTERRUPT HANDLERS (Minimal execution time)
# ----------------------------------------------------
def button_handler(pin):
    global last_press, button_pressed_flag
    now = time.ticks_ms()
    if time.ticks_diff(now, last_press) > DEBOUNCE_MS:
        if pin.value() == 0:
            last_press = now
            button_pressed_flag = True

btn.irq(trigger=Pin.IRQ_FALLING, handler=button_handler)
btn2.irq(trigger=Pin.IRQ_FALLING, handler=button_handler)

# ----------------------------------------------------
# 3. SAFE NETWORK TIME FETCH & SUNRISE/SUNSET
# ----------------------------------------------------
def fetch_api_time():
    timeURL = "https://world-time-api3.p.rapidapi.com/timezone/America/New_York"
    headers = {
        "x-rapidapi-key": "ec93a9240bmsh759d6bc3cec6ff8p1602bajsnd9ac831448fc",
        "x-rapidapi-host": "world-time-api3.p.rapidapi.com",
        "User-Agent": "MicroPython ESP32"
    }

    gc.collect()  # Clean RAM before SSL handshake
    response = None

    try:
        response = urequests.get(timeURL, headers=headers)
        if response.status_code == 200:
            data = response.json()
            timestamp = data.get("datetime")
            
            # Null-check payload before string slicing
            if timestamp and len(timestamp) >= 16:
                date_str = timestamp[0:10]
                hour = int(timestamp[11:13])
                minute = int(timestamp[14:16])
                return date_str, hour, minute
            else:
                print("Error: Invalid timestamp format")
        else:
            print("HTTP Request Failed with Status:", response.status_code)

    except Exception as e:
        print("Network error during time fetch:", e)
        
    finally:
        # Guarantee socket closure to avoid memory leaks
        if response is not None:
            response.close()
            
    return None, None, None


def fetch_sunrise_sunset():
    # Correct path is /json (v2 is invalid)
    # formatted=0 returns ISO strings like "2026-09-15T10:24:00+00:00"
    # Added &tzid=America/New_York
    sunriseSunsetURL = "https://api.sunrise-sunset.org/json?lat=42.3611&lng=-71.0571&formatted=0&tzid=America/New_York"
    
    gc.collect()
    response = None
    
    try:
        response = urequests.get(sunriseSunsetURL)
        if response.status_code == 200:
            data = response.json()
            
            # Extract nested 'results' dictionary
            results = data.get("results", {})
            sunrise = results.get("sunrise")
            sunset = results.get("sunset")
            
            if sunrise and sunset:
                # Extract clean HH:MM from ISO strings ("2026-09-15T10:24:00+00:00")
                sunrise_time = sunrise.split("T")[1][:5]
                sunset_time = sunset.split("T")[1][:5]
                
                print(f"Sunrise (New_York): {sunrise_time}, Sunset (New_York): {sunset_time}")
                return sunrise_time, sunset_time
            else:
                print("Error: Invalid or missing timestamp payload")
        else:
            print("HTTP Request Failed with Status:", response.status_code)

    except Exception as e:
        print("Network error during sunrise/sunset fetch:", e)
        
    finally:
        if response is not None:
            response.close()
            
    return None, None



# ----------------------------------------------------
# 4. INITIALIZATION & MAIN LOOP
# ----------------------------------------------------
connect_wifi(secrets.hSSID, secrets.hPASSWORD)
date_str, hour, minute = fetch_api_time()
sunrise_time, sunset_time = fetch_sunrise_sunset()

if hour is not None:
    print(f"Time synced successfully! {date_str} {hour:02d}:{minute:02d}")

while True:
    # Process button triggers outside IRQ context
    if button_pressed_flag:
        print("Button pressed! Processing event...")
        button_pressed_flag = False

    time.sleep_ms(50)