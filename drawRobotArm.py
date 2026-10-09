import gc
import math
import network
import secrets
import socket
import time

import machine
from machine import PWM, Pin
import uasyncio as asyncio

# -------------------------------------------------------------------------
# Robot Set Up & Calibration
# -------------------------------------------------------------------------
L1, L2 = 9.3, 10.16  # Link lengths in cm

s1 = PWM(Pin(4), freq=50)
s2 = PWM(Pin(18), freq=50)

is_drawing = False


def servo(pwm, deg):
    """Clamps angle between 0-180 and converts to PWM duty cycle."""
    deg = max(0.0, min(180.0, deg))
    us = 500 + (2000 * deg / 180.0)
    pwm.duty_u16(int(us * 65535 / 20000))


def calculate_inverse_kinematics(x, y, l1=L1, l2=L2):
    """Calculates absolute physical servo angles (0 to 180 deg) for Quadrant 1."""
    x = max(0.5, x)
    y = max(0.5, y)

    r_sq = x**2 + y**2
    r = math.sqrt(r_sq)

    # Singularity prevention: Max total reach is L1 + L2 = 19.46 cm.
    # Cap slightly below physical max reach (16.5 cm) to avoid elbow lockup
    max_reach = 16.5
    min_reach = 1.0
    if r > max_reach:
        x = x * (max_reach / r)
        y = y * (max_reach / r)
        r_sq = x**2 + y**2
    elif r < min_reach:
        x = x * (min_reach / r)
        y = y * (min_reach / r)
        r_sq = x**2 + y**2

    # Law of Cosines for interior elbow angle (alpha)
    cos_alpha = (l1**2 + l2**2 - r_sq) / (2 * l1 * l2)
    cos_alpha = max(-1.0, min(1.0, cos_alpha))
    alpha = math.acos(cos_alpha)

    # Calculate shoulder base angle (theta1)
    gamma = math.atan2(y, x)
    cos_beta = (l1**2 + r_sq - l2**2) / (2 * l1 * r)
    cos_beta = max(-1.0, min(1.0, cos_beta))
    beta = math.acos(cos_beta)

    theta1_rad = gamma + beta
    theta2_rad = alpha

    s1_deg = math.degrees(theta1_rad)
    s2_deg = math.degrees(theta2_rad)

    return s1_deg, s2_deg


box_side = (L1 + L2) / 1.414
cx, cy = box_side / 2, box_side / 2

# Set home position to safe workspace center
deg1_home, deg2_home = calculate_inverse_kinematics(cx, cy)
servo(s1, deg1_home)
servo(s2, deg2_home)


# -------------------------------------------------------------------------
# Trajectory Generation
# -------------------------------------------------------------------------
def linspace(start, stop, num):
    if num <= 1:
        return [start]
    step = (stop - start) / (num - 1)
    return [start + i * step for i in range(num)]


def generate_shape_points(shape_type, num_points):
    t_vals = linspace(0.0, 2.0 * math.pi, num_points)

    if shape_type == "Circle":
        # Full box diameter circle centered at (cx, cy)
        radius = box_side / 2.0
        x = [cx + radius * math.cos(t) for t in t_vals]
        y = [cy + radius * math.sin(t) for t in t_vals]

    elif shape_type == "Square":
        side = box_side
        x0, y0 = 0.0, 0.0
        pts_per_side = num_points // 4
        s_x = linspace(x0, x0 + side, pts_per_side)
        s_y = linspace(y0, y0 + side, pts_per_side)
        s_x_rev = linspace(x0 + side, x0, pts_per_side)
        s_y_rev = linspace(y0 + side, y0, pts_per_side)

        x = s_x + [x0 + side] * pts_per_side + s_x_rev + [x0] * pts_per_side
        y = [y0] * pts_per_side + s_y + [y0 + side] * pts_per_side + s_y_rev

    elif shape_type == "Star":
        x, y = [], []
        # Outer tip extends to full box boundary (r = box_side / 2)
        r_outer = box_side / 2.0
        r_inner = r_outer * 0.4
        r_mid = (r_outer + r_inner) / 2.0
        r_amp = (r_outer - r_inner) / 2.0
        for t in t_vals:
            r = r_mid + r_amp * math.cos(5.0 * t)
            x.append(cx + r * math.cos(t))
            y.append(cy + r * math.sin(t))

    elif shape_type == "Heart":
        x, y = [], []
        # Scaled to fill the full box_side width and height
        scale_x = box_side / 32.0  # Horizontal range (-16 to +16 = 32)
        scale_y = box_side / 28.0  # Vertical range (~28)
        for t in t_vals:
            x.append(cx + scale_x * (16.0 * (math.sin(t) ** 3)))
            y.append(
                cy
                + scale_y
                * (
                    13.0 * math.cos(t)
                    - 5.0 * math.cos(2.0 * t)
                    - 2.0 * math.cos(3.0 * t)
                    - math.cos(4.0 * t)
                )
            )
    else:
        x, y = [cx], [cy]

    return x, y


# -------------------------------------------------------------------------
# Asynchronous Drawing Task
# -------------------------------------------------------------------------
async def draw_shape_async(shape_name):
    global is_drawing
    if is_drawing:
        print("Already drawing a shape. Command ignored.")
        return

    is_drawing = True
    print(f"Started drawing: {shape_name}")

    x_pts, y_pts = generate_shape_points(shape_name, 200)

    try:
        for pass_num in range(1):
            for x, y in zip(x_pts, y_pts):
                deg1, deg2 = calculate_inverse_kinematics(x, y)
                servo(s1, deg1)
                servo(s2, deg2)
                await asyncio.sleep_ms(25)
    finally:
        is_drawing = False
        print(f"Finished drawing: {shape_name}")


# -------------------------------------------------------------------------
# Wi-Fi Setup
# -------------------------------------------------------------------------
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(secrets.SSID, secrets.PASSWORD)

print("Connecting to Wi-Fi...", end="")
while not wlan.isconnected():
    time.sleep(0.1)

print("\nConnected! IP Address:", wlan.ifconfig()[0])


# -------------------------------------------------------------------------
# Web Server & Request Handler
# -------------------------------------------------------------------------
def get_html():
    return """<!DOCTYPE html>
<html>
<head>
    <title>ESP32 Robot Arm</title>
    <style>
        body { font-family: Arial; text-align: center; margin-top: 50px; }
        button { padding: 15px 25px; font-size: 18px; margin: 10px; cursor: pointer; }
        .status { font-weight: bold; }
        .busy { color: #d9534f; }
        .ready { color: #5cb85c; }
    </style>
</head>
<body>
    <h1>ESP32 Robot Arm Control</h1>
    <p>Status: <span id="status" class="status">Checking...</span></p>

    <div>
        <button onclick="draw('Circle')">Circle</button>
        <button onclick="draw('Square')">Square</button>
        <button onclick="draw('Star')">Star</button>
        <button onclick="draw('Heart')">Heart</button>
    </div>

    <script>
        async function updateStatus() {
            try {
                let res = await fetch('/status');
                let data = await res.json();
                let statusEl = document.getElementById('status');
                if (data.is_drawing) {
                    statusEl.innerText = "BUSY - Drawing in progress...";
                    statusEl.className = "status busy";
                } else {
                    statusEl.innerText = "READY";
                    statusEl.className = "status ready";
                }
            } catch (e) {
                console.error("Failed to fetch status:", e);
            }
        }

        async function draw(shapeName) {
            await fetch('/draw', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: 'shape=' + shapeName
            });
            updateStatus();
        }

        setInterval(updateStatus, 1000);
        updateStatus();
    </script>
</body>
</html>
"""


async def handle_client(reader, writer):
    try:
        raw_request = await reader.read(2048)
        request = raw_request.decode("utf-8")

        lines = request.split("\r\n")
        if not lines or len(lines[0]) == 0:
            await writer.aclose()
            return

        method, path, _ = lines[0].split(" ")

        if path == "/status":
            body = '{"is_drawing": ' + ("true" if is_drawing else "false") + "}"
            headers = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Connection: close\r\n\r\n"
            )
            writer.write((headers + body).encode("utf-8"))
            await writer.drain()

        elif path == "/draw" and method == "POST":
            parts = request.split("\r\n\r\n")
            if len(parts) > 1 and "shape=" in parts[1]:
                selected_shape = parts[1].split("=")[1]
                asyncio.create_task(draw_shape_async(selected_shape))

            body = '{"status": "ok"}'
            headers = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Connection: close\r\n\r\n"
            )
            writer.write((headers + body).encode("utf-8"))
            await writer.drain()

        else:
            body = get_html()
            headers = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: text/html\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Connection: close\r\n\r\n"
            )
            writer.write((headers + body).encode("utf-8"))
            await writer.drain()

    except Exception as e:
        print(f"Client handler error: {e}")

    finally:
        await writer.aclose()


# -------------------------------------------------------------------------
# Main Task
# -------------------------------------------------------------------------
async def main():
    server = await asyncio.start_server(handle_client, "0.0.0.0", 80)
    print("Async Server running on port 80...")

    while True:
        gc.collect()
        await asyncio.sleep(5)


try:
    asyncio.run(main())
except KeyboardInterrupt:
    print("Server stopped.")