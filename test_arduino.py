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
if not port:
    print("No port")
    exit()

s = serial.Serial(port, 9600, timeout=1)
time.sleep(2)

print("Sending happy...")
cmd = {"type": "emotion", "name": "happy", "pitch": 25}
s.write((json.dumps(cmd) + "\n").encode())

start = time.time()
while time.time() - start < 3:
    line = s.readline().decode('utf-8', errors='ignore').strip()
    if line:
        print(f"[{time.time()-start:.2f}] ARDUINO: {line}")
s.close()
