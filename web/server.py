import sys
import os
import json
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/../")
from sense.sensor_state import shared_state

# External pipeline reference—set by main.py after creating context_pipeline
context_pipeline_ref = None


class DashboardHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress request log spam
        pass

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/state':
            state = shared_state.get()
            self._json(state)
        else:
            super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        if path == '/woz':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
                active = data.get('active', False)
                from express.serial_bridge import bridge
                bridge.set_woz_mode(active)
                self._json({'ok': True, 'woz_mode': active})
            except Exception as e:
                self._json({'ok': False, 'error': str(e)})

                
        elif path == '/inject':
            # Read body
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
                emotion = data.get('emotion', '').lower()
                VALID = {'relaxed', 'happy', 'focus', 'curious', 'confused',
                         'tired', 'listen', 'shy', 'alert'}
                if emotion not in VALID:
                    self._json({'ok': False, 'error': f'Unknown emotion: {emotion}'})
                    return

                # Force emotion into shared state
                shared_state.update('current_emotion', emotion)

                # Also patch the pipeline's internal state so min-hold doesn't block
                if context_pipeline_ref is not None:
                    context_pipeline_ref.current_emotion = emotion
                    import time
                    # Reset hold timer so it can switch away immediately
                    context_pipeline_ref.emotion_entered_at = time.time() - 999

                # Send hardware command to Arduino
                from express.serial_bridge import bridge
                from config.emotions import get_emotion
                
                if emotion in ['alert', 'shy']:
                    params = get_emotion(f"reflex_{emotion}")
                    if bridge.woz_mode:
                        bridge._send({"type": "reflex", "name": emotion, **params})
                    else:
                        bridge.send_reflex(emotion, params)
                else:
                    params = get_emotion(emotion)
                    if bridge.woz_mode:
                        bridge.send_emotion_woz(params)
                    else:
                        bridge.send_emotion(params)

                print(f"[WEB] 🎛️  Injected emotion: {emotion}")
                self._json({'ok': True, 'emotion': emotion})
            except Exception as e:
                self._json({'ok': False, 'error': str(e)})
        else:
            self.send_response(404)
            self.end_headers()

    def _json(self, obj):
        body = json.dumps(obj).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)


_httpd_instance = None

def run_server():
    global _httpd_instance
    web_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(web_dir)
    server_address = ('', 8080)
    HTTPServer.allow_reuse_address = True
    _httpd_instance = HTTPServer(server_address, DashboardHandler)
    print("🌐 [WEB] Dashboard → http://localhost:8080")
    _httpd_instance.serve_forever()


def stop_dashboard():
    global _httpd_instance
    if _httpd_instance:
        _httpd_instance.shutdown()
        _httpd_instance = None


def start_dashboard(pipeline=None):
    global context_pipeline_ref
    context_pipeline_ref = pipeline
    thread = threading.Thread(target=run_server, daemon=True, name="DashboardServer")
    thread.start()
    return thread


if __name__ == "__main__":
    start_dashboard()
    print("Press Ctrl+C to stop.")
    import time
    while True:
        time.sleep(1)
