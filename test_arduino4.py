import serial
import serial.tools.list_ports
import time
import json

def get_port():
    for p in serial.tools.list_ports.comports():
        if any(x in p.description for x in ["Arduino", "usbmodem", "usbserial", "CH340"]):
            return p.device
    ports = list(serial.tools.list_ports.comports())
    if ports:
        return ports[0].device
    return None

port = get_port()
s = serial.Serial(port, 9600, timeout=1)
s.setDTR(False)
time.sleep(1)
s.setDTR(True)

print("Waiting for ready...")
start = time.time()
while time.time() - start < 10:
    line = s.readline().decode('utf-8', errors='ignore').strip()
    if line:
        print(f"ARDUINO: {line}")
        if line == "ANIMA ready":
            break

print("Sending happy...")
cmd = {"type": "emotion", "name": "happy", "pitch": 25}
s.write((json.dumps(cmd) + "\n").encode())

start = time.time()
while time.time() - start < 3:
    line = s.readline().decode('utf-8', errors='ignore').strip()
    if line:
        print(f"ARDUINO: {line}")
s.close()
