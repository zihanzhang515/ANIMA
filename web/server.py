import sys
import os
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/../")
from sense.sensor_state import shared_state

# Pipeline references set by main.py
context_pipeline_ref  = None
realtime_pipeline_ref = None


class DashboardHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress request log spam

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/state':
            self._json(shared_state.get())
        else:
            super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path

        if path == '/inject':
            length = int(self.headers.get('Content-Length', 0))
            body   = self.rfile.read(length)
            try:
                data    = json.loads(body)
                emotion = data.get('emotion', '').lower()
                VALID   = {'relaxed', 'happy', 'focus', 'curious', 'confused',
                           'tired', 'listen', 'shy', 'alert'}
                if emotion not in VALID:
                    self._json({'ok': False, 'error': f'Unknown emotion: {emotion}'})
                    return

                from express.serial_bridge import bridge
                from config.emotions import get_emotion

                # ── 1. shared_state（网页显示用）──────────────────────
                shared_state.force_update('current_emotion', emotion)

                # ── 2. 同步 context_pipeline（重置 hold timer）────────
                if context_pipeline_ref is not None:
                    import time as _t
                    context_pipeline_ref.current_emotion    = emotion
                    context_pipeline_ref.emotion_entered_at = _t.time() - 999

                # ── 3. 同步 realtime_pipeline（防止 idle 覆盖）────────
                if realtime_pipeline_ref is not None:
                    realtime_pipeline_ref.set_emotion(emotion)

                # ── 4. 发送 Arduino 指令 ──────────────────────────────
                if emotion in ('alert', 'shy'):
                    # 使用正确的 reflex_ 前缀 key 获取反射参数
                    params = get_emotion(f'reflex_{emotion}')
                    bridge.send_reflex(emotion, params)
                else:
                    params = get_emotion(emotion)
                    bridge.send_emotion(params)

                print(f"[WEB] 🎛️  Inject: {emotion}")
                self._json({'ok': True, 'emotion': emotion})

            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                traceback.print_exc()
                self._json({'ok': False, 'error': str(e), 'traceback': tb})

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
    ThreadingHTTPServer.allow_reuse_address = True
    _httpd_instance = ThreadingHTTPServer(('', 8080), DashboardHandler)
    print("🌐 [WEB] Dashboard → http://localhost:8080")
    _httpd_instance.serve_forever()


def stop_dashboard():
    global _httpd_instance
    if _httpd_instance:
        _httpd_instance.shutdown()
        _httpd_instance = None


def start_dashboard(pipeline=None, realtime_pipeline=None):
    global context_pipeline_ref, realtime_pipeline_ref
    context_pipeline_ref  = pipeline
    realtime_pipeline_ref = realtime_pipeline
    thread = threading.Thread(target=run_server, daemon=True, name="DashboardServer")
    thread.start()
    return thread


if __name__ == "__main__":
    start_dashboard()
    import time
    while True:
        time.sleep(1)
