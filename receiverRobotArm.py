import gc
import math
import network
import secrets
import time

import machine
from machine import PWM, Pin
import uasyncio as asyncio
import urequests as requests
import json

s1 = PWM(Pin(4), freq=50)
s2 = PWM(Pin(18), freq=50)

is_drawing = False


def servo(pwm, deg):
    """Clamps angle between 0-180 and converts to PWM duty cycle."""
    deg = max(0.0, min(180.0, deg))
    us = 500 + (2000 * deg / 180.0)
    pwm.duty_u16(int(us * 65535 / 20000))


# -------------------------------------------------------------------------
# Wi-Fi Setup & API
# -------------------------------------------------------------------------
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect("Tufts_Wireless", "")

print("Connecting to Wi-Fi...", end="")
while not wlan.isconnected():
    time.sleep(0.1)

print("\nConnected! IP Address:", wlan.ifconfig()[0])

def fetch_mate_values():
    # Replace these with your document ID, workspace ID, and assembly element ID
    did = "10bd01c903cddb31dd80fc2b"
    wid = "1684fb46d8931cf553d280c9"  # Found in your browser URL after /w/
    eid = "41de52599c79b9656e3d6c3f"  # Found in your browser URL after /e/
    
    api_url = f"https://cad.onshape.com/api/assemblies/d/{did}/w/{wid}/e/{eid}/matevalues"

    headers = {
        'Accept': 'application/vnd.onshape.v2+json',
        'Content-Type': 'application/json'
    }
    
    response = requests.get(
        api_url, 
        auth=(secrets.onshape_AccKey, secrets.onshape_SecKey),
        headers=headers
    )
    
    angles = []

    if response.status_code == 200:
        data = response.json()
        # Example of iterating through the returned mates
        for mate in data.get("mateValues", []):
            angle = mate.get('rotationZ')
            if angle is not None:
                #print(f"Mate: {mate.get('mateName')} | Angle: {angle}")
                angles.append(math.degrees(angle))
            
    else:
        print(f"Failed to fetch mates. Status Code: {response.status_code}")
        print(response.text)
        
    return angles

while True:
    angles = fetch_mate_values()
    angles[0] *= -1
    angles[1] += 90
    servo(s1, angles[0])
    servo(s2, angles[1])
    time.sleep(0.1)
    
