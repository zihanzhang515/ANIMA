import urllib.request
import json
data = json.dumps({"active": True}).encode('utf-8')
req = urllib.request.Request("http://localhost:8080/woz", data=data, method="POST")
try:
    with urllib.request.urlopen(req) as response:
        print(response.read().decode())
except Exception as e:
    print(f"Error: {e}")
