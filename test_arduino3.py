import serial
import serial.tools.list_ports

def get_port():
    for p in serial.tools.list_ports.comports():
        if "usbmodem" in p.device:
            return p.device
    ports = list(serial.tools.list_ports.comports())
    return ports[0].device if ports else None

port = get_port()
print("Port:", port)
s = serial.Serial(port, 9600, timeout=1)
s.setDTR(False)
import time
time.sleep(1)
s.flushInput()
s.setDTR(True)

print("Reading...")
for _ in range(15):
    line = s.readline().decode('utf-8', errors='ignore').strip()
    if line:
        print("ARDUINO:", line)
s.close()
