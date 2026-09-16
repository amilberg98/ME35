import network
wlan = network.WLAN()
mac = wlan.config("mac")
print(mac)

import ubinascii
mac_readable = ubinascii.hexlify(mac,":").decode()
print(mac_readable)

#importing the libraries
import network
import urequests
import time
import secrets
import http.client
 
#setting up SSID and password 
 
SSID = secrets.SSID
PASSWORD = secrets.PASSWORD


#function definition 
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("Connecting to WiFi...")
        wlan.connect(SSID, PASSWORD)
        while not wlan.isconnected():
            time.sleep(0.5)
    print("Connected! IP address:", wlan.ifconfig()[0])
    return wlan
 
#function call
connect_wifi()
 
#ON REPL you can type wlan.isconnected() hit ENTER. it will return True
 
 
ISS_URL = "http://api.open-notify.org/iss-now.json"

response = urequests.get(ISS_URL)
data = response.json()
response.close()

print(data)
