import json

with open('/Users/jennifer/ANIMA/src/main.cpp', 'r') as f:
    content = f.read()

print("LED_BRIGHTNESS" in content)
