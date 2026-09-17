import network
import urequests
import machine
import time
import gc
import neopixel
from machine import Pin, PWM, RTC
import secrets

# ----------------------------------------------------
# SETUP & CONFIGURATION
# ----------------------------------------------------
def connect_wifi(SSID, PASSWORD):
    wlan = network.WLAN(network.STA_IF)
    
    # Reset radio state if it's already active or stuck
    if wlan.active():
        try:
            wlan.disconnect()
        except OSError:
            pass
        wlan.active(False)
        time.sleep(0.5)

    # Re-enable the interface safely
    wlan.active(True)
    time.sleep(0.5)  # Give driver time to settle

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

# ----------------------------------------------------
# INTERRUPT HANDLERS
# ----------------------------------------------------
def button_handler(pin):
    global last_press, state
    now = time.ticks_ms()
    if time.ticks_diff(now, last_press) > DEBOUNCE_MS:
        if pin.value() == 0:
            state = (state + 1) % 3
            last_press = now
            
            
# ----------------------------------------------------
# SAFE NETWORK TIME FETCH & SUNRISE/SUNSET
# ----------------------------------------------------
def fetch_api_time():
    timeURL = "https://world-time-api3.p.rapidapi.com/timezone/America/New_York"
    headers = {
        "x-rapidapi-key": secrets.RapidAPI_key,
        "x-rapidapi-host": "world-time-api3.p.rapidapi.com",
        "User-Agent": "MicroPython ESP32"
    }

    gc.collect()
    response = None

    try:
        response = urequests.get(timeURL, headers=headers)
        if response.status_code == 200:
            data = response.json()
            timestamp = data.get("datetime") # e.g. "2026-09-16T14:30:00-04:00"
            day_of_week = int(data.get("day_of_week"))
            if timestamp and len(timestamp) >= 19:
                year = int(timestamp[0:4])
                month = int(timestamp[5:7])
                day = int(timestamp[8:10])
                hour = int(timestamp[11:13])
                minute = int(timestamp[14:16])
                second = int(timestamp[17:19])
                
                # Sync system RTC with network time
                rtc.datetime((year, month, day, day_of_week, hour, minute, second, 0))
                print("RTC Synchronized with API Time.")
            else:
                print("Error: Invalid timestamp format")
        else:
            print("HTTP Request Failed with Status:", response.status_code)

    except Exception as e:
        print("Network error during time fetch:", e)
        
    finally:
        if response is not None:
            response.close()


def fetch_sunrise_sunset():
    sunriseSunsetURL = "https://api.sunrise-sunset.org/json?lat=42.3611&lng=-71.0571&formatted=0&tzid=America/New_York"
    
    gc.collect()
    response = None
    
    try:
        response = urequests.get(sunriseSunsetURL)
        if response.status_code == 200:
            data = response.json()
            results = data.get("results", {})
            sunrise = results.get("sunrise")
            sunset = results.get("sunset")
            
            if sunrise and sunset:
                times_dict["sunrise"][0] = int(sunrise.split("T")[1][:2])
                times_dict["sunrise"][1] = int(sunrise.split("T")[1][3:5])
                times_dict["sunset"][0] = int(sunset.split("T")[1][:2])
                times_dict["sunset"][1] = int(sunset.split("T")[1][3:5])
            else:
                print("Error: Invalid or missing timestamp payload")
        else:
            print("HTTP Request Failed with Status:", response.status_code)

    except Exception as e:
        print("Network error during sunrise/sunset fetch:", e)
        
    finally:
        if response is not None:
            response.close()

# ----------------------------------------------------
# Time --> Set Servo
# ----------------------------------------------------
def setClock(hour, minute):
    
    if hour is None or minute is None:
        return

    pm = False
    
    # Standard 12-hour clock conversion
    if hour >= 12:
        pm = True
        if hour > 12:
            hour -= 12
    elif hour == 0:
        hour = 12

    timeFiveMinInc = (hour * 12) + (minute // 5)
    angle = timeFiveMinInc * 1.25
    
    # Servo Pulse width map: 0.5ms (0 deg) to 2.5ms (180 deg)
    pulseWidth = 0.5 + (((180 - angle) / 180) * 2) 
    servo.duty_u16(int((pulseWidth / 20) * 65535))
    
    # Update AM/PM LED indicator
    if pm:
        led.on()
    else:
        led.off()

# ----------------------------------------------------
# INITIALIZATION & MAIN LOOP
# ----------------------------------------------------
        
# State variables
state = 0  # 0 = clock, 1 = sunrise, 2 = sunset
times_dict = {"sunrise": [None, None], "sunset": [None, None]}

# NeoPixel setup: GPIO15, 2 pixels
np = neopixel.NeoPixel(machine.Pin(15), 2)

# Hardware peripherals 
btn = Pin(35, Pin.IN)
servo = PWM(Pin(4), freq=50, duty_u16=0)
led = machine.Pin(2, machine.Pin.OUT) # AM/PM Light
led.off()
rtc = RTC()

DEBOUNCE_MS = 200
last_press = 0

btn.irq(trigger=Pin.IRQ_FALLING, handler=button_handler)

connect_wifi(secrets.hSSID, secrets.hPASSWORD)
fetch_api_time()

fetch_sunrise_sunset()

last_state = -1

while True:
    # Read live time from internal RTC
    current_datetime = rtc.datetime()
    current_hour = current_datetime[4]
    current_minute = current_datetime[5]

    # Update hardware on state change OR when the clock minute advances 5 minutes
    if state != last_state or (state == 0 and current_minute >= last_minute + 5):
        np[1] = (0, 0, 0) # Clear second pixel
        
        if state == 0:    # Live Clock
            np[0] = (255, 0, 0)
            setClock(current_hour, current_minute)
            last_minute = current_minute
            print(f"Current Time: {current_hour}:{current_minute}")
        elif state == 1:  # Sunrise
            np[0] = (0, 255, 0)
            setClock(times_dict["sunrise"][0], times_dict["sunrise"][1])
            print(f"Sunrise: {times_dict["sunrise"][0]}:{times_dict["sunrise"][1]}")
        elif state == 2:  # Sunset
            np[0] = (0, 0, 255)
            setClock(times_dict["sunset"][0], times_dict["sunset"][1])
            print(f"Sunset: {times_dict["sunset"][0]}:{times_dict["sunset"][1]}")
            
        np.write()
        last_state = state

    time.sleep(0.1)