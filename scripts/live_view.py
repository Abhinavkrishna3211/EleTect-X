"""MJPEG live-view server for EleTect-X HOME_TEST_MODE, run inside the app container.

Adapted from live_view_cv2_host.py (a standalone host-side script that predates
this deployment and used host filesystem paths). This copy runs via
`docker exec eletect-x-main-1 python3 /app/live_view.py` instead, so every path
below is the container-side view of the same bind-mounted directories.

Reads the already-written ring buffer JPEGs rather than opening the camera
itself, so it never contends with home_test.py's exclusive camera handle.
"""
import http.server
import json
import os
import re
import socketserver
import time

import cv2

RING_DIR = '/app/python/data/home_test/ring'
DET_FILE = '/app/python/data/home_test/detections.jsonl'
CONFIG_PATH = '/app/python/services/config.py'

_FIRE_THRESHOLD_RE = re.compile(r'^HOME_TEST_FIRE_MIN_CONFIDENCE\s*=\s*([0-9.]+)', re.MULTILINE)
_threshold_cache = {'mtime': None, 'value': 0.60}

def fire_threshold():
    try:
        mtime = os.path.getmtime(CONFIG_PATH)
    except OSError:
        return _threshold_cache['value']
    if mtime != _threshold_cache['mtime']:
        try:
            with open(CONFIG_PATH) as f:
                text = f.read()
            m = _FIRE_THRESHOLD_RE.search(text)
            if m:
                _threshold_cache['value'] = float(m.group(1))
            _threshold_cache['mtime'] = mtime
        except OSError:
            pass
    return _threshold_cache['value']

def latest_frame_path():
    try:
        names = os.listdir(RING_DIR)
    except FileNotFoundError:
        return None
    if not names:
        return None
    names.sort()
    return os.path.join(RING_DIR, names[-1])

def recent_detections(max_age_s=3.0):
    try:
        with open(DET_FILE, 'rb') as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 40000))
            lines = f.read().decode('utf-8', 'ignore').splitlines()
    except FileNotFoundError:
        return []
    now = time.time()
    out = []
    for line in lines[-60:]:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if now - d.get('wall_s', 0) <= max_age_s:
            out.append(d)
    return out

def last_detection_wall_s():
    try:
        with open(DET_FILE, 'rb') as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 4000))
            lines = f.read().decode('utf-8', 'ignore').splitlines()
    except FileNotFoundError:
        return None
    for line in reversed(lines):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        return d.get('wall_s')
    return None

def annotated_jpeg_bytes(path):
    img = cv2.imread(path)
    if img is None:
        with open(path, 'rb') as f:
            return f.read()
    threshold = fire_threshold()
    dets = recent_detections(max_age_s=3.0)
    last_wall = last_detection_wall_s()
    age_s = (time.time() - last_wall) if last_wall else None
    for d in dets:
        x, y, w, h = int(d.get('x', 0)), int(d.get('y', 0)), int(d.get('width', 0)), int(d.get('height', 0))
        conf = d.get('confidence', 0)
        label = d.get('label', '?')
        if conf >= threshold:
            color = (0, 0, 255)
        elif conf >= 0.3:
            color = (0, 200, 255)
        else:
            color = (0, 200, 0)
        cv2.rectangle(img, (x, y), (x + w, y + h), color, 4)
        text = f'{label} {conf:.2f}'
        ty = max(20, y - 10)
        cv2.putText(img, text, (x + 4, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2, cv2.LINE_AA)
    age_text = f'{age_s:.1f}s' if age_s is not None else 'n/a (no detections logged yet)'
    banner = f'last poll age: {age_text}  fire threshold: {threshold:.2f}'
    cv2.putText(img, banner, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
    ok, buf = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    if not ok:
        with open(path, 'rb') as f:
            return f.read()
    return buf.tobytes()

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        if self.path in ('/', ''):
            html = (b'<html><body style="margin:0;background:#111">'
                    b'<img src="/stream" style="width:100%;height:auto;display:block">'
                    b'</body></html>')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', str(len(html)))
            self.end_headers()
            self.wfile.write(html)
            return
        if self.path == '/stream':
            self.send_response(200)
            self.send_header('Age', '0')
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
            self.end_headers()
            try:
                while True:
                    p = latest_frame_path()
                    if p:
                        try:
                            jpg = annotated_jpeg_bytes(p)
                        except Exception:  # noqa: BLE001 - a bad frame must not end the stream
                            with open(p, 'rb') as f:
                                jpg = f.read()
                        self.wfile.write(b'--FRAME\r\n')
                        self.wfile.write(b'Content-Type: image/jpeg\r\n')
                        self.wfile.write(f'Content-Length: {len(jpg)}\r\n\r\n'.encode())
                        self.wfile.write(jpg)
                        self.wfile.write(b'\r\n')
                    time.sleep(0.2)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        self.send_response(404)
        self.end_headers()

class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

if __name__ == '__main__':
    srv = ThreadingServer(('0.0.0.0', 8090), Handler)
    srv.serve_forever()
