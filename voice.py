"""Dictation with Claude Code's own speech-to-text service (the one behind /voice).

T3's page records the microphone and posts 16 kHz 16-bit mono audio to helper.py, which streams
it here to wss://api.anthropic.com/api/ws/speech_to_text/voice_stream, signed in with Claude
Code's login from ~/.claude/.credentials.json. The login never leaves this process.

This service is undocumented and meant for Claude Code, so a Claude Code update can change or
close it at any time. When that happens dictation shows the error and nothing else breaks.
"""
import base64, json, os, socket, ssl, struct, threading, time, urllib.parse

HOST = "api.anthropic.com"
PATH = "/api/ws/speech_to_text/voice_stream"
CREDENTIALS = os.path.join(os.path.expanduser("~"), ".claude", ".credentials.json")
KEEPALIVE = json.dumps({"type": "KeepAlive"})
CLOSE = json.dumps({"type": "CloseStream"})


def token():
    try:
        with open(CREDENTIALS, encoding="utf-8") as f:
            oauth = json.load(f).get("claudeAiOauth") or {}
    except (OSError, ValueError):
        oauth = {}
    if not oauth.get("accessToken"):
        raise ValueError("Claude Code isn't signed in. Run claude and sign in first.")
    if oauth.get("expiresAt", 0) / 1000 < time.time() + 30:
        raise ValueError("Claude Code's sign-in has expired. Send any message in a Claude chat to renew it, then try again.")
    return oauth["accessToken"]


class Socket:
    """Just enough of a WebSocket client (RFC 6455) for this one stream."""

    def __init__(self, query, headers):
        raw = socket.create_connection((HOST, 443), timeout=10)
        self.s = ssl.create_default_context().wrap_socket(raw, server_hostname=HOST)
        key = base64.b64encode(os.urandom(16)).decode()
        lines = [f"GET {PATH}?{urllib.parse.urlencode(query)} HTTP/1.1", f"Host: {HOST}", "Upgrade: websocket",
                 "Connection: Upgrade", f"Sec-WebSocket-Key: {key}", "Sec-WebSocket-Version: 13",
                 *(f"{k}: {v}" for k, v in headers.items())]
        self.s.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
        reply = b""
        while b"\r\n\r\n" not in reply:
            chunk = self.s.recv(4096)
            if not chunk:
                break
            reply += chunk
        head, _, self.buf = reply.partition(b"\r\n\r\n")
        status = head.split(b"\r\n", 1)[0].decode(errors="replace")
        if " 101 " not in status + " ":
            self.s.close()
            raise ValueError(f"The speech service refused the connection ({status.split(' ', 1)[-1]}).")
        self.s.settimeout(None)
        self.lock = threading.Lock()

    def send(self, data, text=False):
        payload = data.encode() if text else data
        n = len(payload)
        head = bytes([0x81 if text else 0x82])
        head += bytes([0x80 | n]) if n < 126 else (bytes([0x80 | 126]) + struct.pack(">H", n) if n < 65536
                                                      else bytes([0x80 | 127]) + struct.pack(">Q", n))
        mask = os.urandom(4)
        body = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        with self.lock:
            self.s.sendall(head + mask + body)

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.s.recv(65536)
            if not chunk:
                raise EOFError
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def recv(self):
        """The next text message, or None when the stream closes."""
        while True:
            b1, b2 = self._read(2)
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            data = self._read(n)
            op = b1 & 0x0F
            if op == 0x8:
                return None
            if op == 0x9:  # ping
                with self.lock:
                    self.s.sendall(bytes([0x8A, 0x80]) + os.urandom(4))
            elif op == 0x1:
                return data.decode("utf-8", "replace")

    def close(self):
        try:
            self.s.close()
        except OSError:
            pass


class Dictation:
    """One recording: audio in, transcript out."""

    def __init__(self, language="en"):
        self.final, self.interim, self.error, self.done = [], "", None, False
        self.ws = Socket({"encoding": "linear16", "sample_rate": "16000", "channels": "1", "endpointing_ms": "300",
                          "utterance_end_ms": "1000", "language": language, "use_conversation_engine": "true"},
                         {"Authorization": f"Bearer {token()}", "User-Agent": "claude-cli", "x-app": "cli"})
        self.ws.send(KEEPALIVE, text=True)
        self.last = time.time()
        threading.Thread(target=self._listen, daemon=True).start()

    def _listen(self):
        try:
            while True:
                msg = self.ws.recv()
                if msg is None:
                    break
                m = json.loads(msg)
                kind = m.get("type")
                if kind in ("TranscriptInterim", "TranscriptText"):  # the current phrase so far
                    self.interim = m.get("data") or ""
                elif kind == "TranscriptEndpoint":  # the phrase is finished
                    if self.interim:
                        self.final.append(self.interim)
                    self.interim = ""
                elif kind in ("TranscriptError", "error"):
                    self.error = m.get("description") or m.get("message") or m.get("error_code") or "transcription error"
        except (OSError, EOFError, ValueError) as e:
            if not self.done:
                self.error = self.error or f"connection lost: {e}"
        finally:
            self.done = True
            self.ws.close()

    def audio(self, pcm):
        if self.done:
            return
        if pcm:
            self.ws.send(pcm)
        elif time.time() - self.last > 8:
            self.ws.send(KEEPALIVE, text=True)
        self.last = time.time()

    def text(self):
        return " ".join(p.strip() for p in [*self.final, self.interim] if p.strip())

    def stop(self, wait=2.0):
        """Finish: tell the service the audio ended and wait briefly for the last words."""
        if not self.done:
            try:
                self.ws.send(CLOSE, text=True)
            except OSError:
                pass
            end = time.time() + wait
            while not self.done and time.time() < end:
                time.sleep(0.05)
            if self.interim:
                self.final.append(self.interim)
                self.interim = ""
            self.done = True
            self.ws.close()
        return self.text()
