"""Tiny dependency-free WebSocket client for ComfyUI's /ws (live previews + step progress).

Only what ComfyUI needs: client handshake, unmasked server frames (text / binary / ping / close),
fragmented messages. Runs a daemon reader thread; every failure just leaves the fields empty, so the
caller falls back to HTTP polling.
Binary frames: 4-byte big-endian event type (1 = PREVIEW_IMAGE) + 4-byte image format (1 = JPEG, 2 = PNG) + image bytes.
"""
import base64
import json
import os
import socket
import struct
import threading
import urllib.parse

PREVIEW_IMAGE = 1


def ws_url(http_url, client_id):
    u = urllib.parse.urlparse(http_url)
    return ("wss" if u.scheme == "https" else "ws"), u.hostname or "127.0.0.1", u.port or (443 if u.scheme == "https" else 80), \
        f"{u.path.rstrip('/')}/ws?clientId={urllib.parse.quote(client_id)}"


def parse_binary(data):
    """(event_type, image_bytes) from a ComfyUI binary frame, or (type, None)."""
    if len(data) < 8:
        return None, None
    etype, _fmt = struct.unpack(">II", data[:8])
    return etype, (data[8:] if etype == PREVIEW_IMAGE else None)


class ComfyWS:
    def __init__(self, http_url, client_id, timeout=4):
        self.preview = None          # newest preview image bytes (JPEG/PNG)
        self.previews = 0            # how many preview frames arrived
        self.progress = None         # (value, max) for the running prompt
        self.prompt_id = None        # set by the caller after /prompt
        self.done = False            # 'executing' with node None for our prompt
        self.error = None
        self._lock = threading.Lock()
        scheme, host, port, path = ws_url(http_url, client_id)
        if scheme != "ws":
            raise OSError("wss not supported")
        self.sock = socket.create_connection((host, port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                           f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(1024)
            if not chunk:
                raise OSError("WebSocket handshake closed")
            head += chunk
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise OSError("WebSocket handshake refused: " + head.split(b"\r\n", 1)[0].decode(errors="replace"))
        self._buf = head.split(b"\r\n\r\n", 1)[1]
        self.sock.settimeout(None)
        self._alive = True
        threading.Thread(target=self._reader, daemon=True).start()

    # ---- framing
    def _recv(self, n):
        while len(self._buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise OSError("closed")
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def _frame(self):
        b1, b2 = self._recv(2)
        fin, op, ln = b1 & 0x80, b1 & 0x0F, b2 & 0x7F
        if ln == 126:
            ln = struct.unpack(">H", self._recv(2))[0]
        elif ln == 127:
            ln = struct.unpack(">Q", self._recv(8))[0]
        mask = self._recv(4) if b2 & 0x80 else None
        data = self._recv(ln)
        if mask:
            data = bytes(c ^ mask[i % 4] for i, c in enumerate(data))
        return bool(fin), op, data

    def _send(self, op, payload=b""):
        mask = os.urandom(4)
        head = bytes([0x80 | op]) + (bytes([0x80 | len(payload)]) if len(payload) < 126 else bytes([0x80 | 126]) + struct.pack(">H", len(payload)))
        self.sock.sendall(head + mask + bytes(c ^ mask[i % 4] for i, c in enumerate(payload)))

    def _reader(self):
        msg, mop = b"", None
        try:
            while self._alive:
                fin, op, data = self._frame()
                if op == 0x9:
                    self._send(0xA, data); continue
                if op == 0x8:
                    break
                if op in (0x1, 0x2):
                    msg, mop = data, op
                elif op == 0x0:
                    msg += data
                if fin and mop:
                    self.handle(mop, msg); msg, mop = b"", None
        except (OSError, ValueError, struct.error):
            pass
        self._alive = False

    def handle(self, op, data):
        if op == 0x2:
            etype, img = parse_binary(data)
            if img:
                with self._lock:
                    self.preview = img; self.previews += 1
            return
        try:
            m = json.loads(data.decode("utf-8"))
        except ValueError:
            return
        t, d = m.get("type"), m.get("data") or {}
        if self.prompt_id and d.get("prompt_id") not in (None, self.prompt_id):
            return
        if t == "progress":
            self.progress = (int(d.get("value", 0)), int(d.get("max", 0) or 1))
        elif t == "executing" and d.get("node") is None and d.get("prompt_id") == self.prompt_id:
            self.done = True
        elif t == "execution_error":
            self.error = d.get("exception_message") or "execution error"

    def close(self):
        self._alive = False
        try:
            self._send(0x8)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


def connect(http_url, client_id):
    try:
        return ComfyWS(http_url, client_id)
    except (OSError, ValueError):
        return None
