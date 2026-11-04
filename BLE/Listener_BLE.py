# Listener (central)

from BLE_CEEO import Listen
import time
import json

NAME = "Maria"     # must match the yeller's name
buffer = b""


def callback(data):
    # Pieces arrive in up to 20-byte chunks; a newline ends each message
    global buffer
    buffer += data
    while b"\n" in buffer:
        line, buffer = buffer.split(b"\n", 1)
        print("Received:", json.loads(line.decode()))


p = None
try:
    p = Listen(NAME, verbose=False)
    p.callback = callback

    print("Looking for", NAME, "...")
    if p.connect_up():
        print("Connected")
        count = 0
        while p.is_connected:
            count += 1
            payload = json.dumps({"from": "listener", "count": count}) + "\n"

            # Send in 20-byte pieces (the default packet size)
            for start in range(0, len(payload), 20):
                p.send(payload[start:start + 20])
                time.sleep_ms(20)

            time.sleep(1)
    print("Lost connection")
finally:
    if p:
        p.disconnect()