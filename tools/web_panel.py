#!/usr/bin/env python3
"""Live multi-IMU monitor for LSM6DSV16X sources on an ESP32-S3.

Two front ends over one state object:
  * web  — serves web/ and pushes NDJSON frames over Server-Sent Events
  * CLI  — a terminal dashboard (`--cli`), no browser needed

The firmware in STREAM mode reports every configured source, including absent
ones (`on:0`), and emits HOTPLUG lines when a source appears or disappears.
Both front ends show that state directly, so a missing module is not mistaken
for a zero-reading sensor.

    tools/mode.sh stream && idf.py flash -p /dev/ttyACM0
    python3 tools/web_panel.py --port /dev/ttyACM0          # browser panel
    python3 tools/web_panel.py --port /dev/ttyACM0 --cli    # terminal dashboard
    python3 tools/web_panel.py --simulate --units 11        # no hardware
"""

from __future__ import annotations

import argparse
import json
import math
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parent.parent / "web"

STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".svg": "image/svg+xml",
}


class State:
    """Newest frame per source, observed rate, and link/event health."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.units: dict[int, dict] = {}
        self.prev: dict[int, tuple[int, int, int]] = {}
        self.events: list[dict] = []
        self.frames = 0
        self.last_frame_at: float | None = None
        self.connected = False
        self.error: str | None = None
        self.ready: int | None = None

    def event(self, text: str) -> None:
        with self.lock:
            self.events.append({"at": time.strftime("%H:%M:%S"), "text": text})
            self.events = self.events[-50:]

    def update(self, frame: dict) -> None:
        with self.lock:
            t = int(frame.get("t", 0))
            for u in frame.get("u", []):
                i = int(u["i"])
                rec = {**u, "t": t}
                p = self.prev.get(i)
                na, ng = int(u.get("na", 0)), int(u.get("ng", 0))
                if p and t > p[0] and u.get("on"):
                    dt = (t - p[0]) / 1000.0
                    rec["rate_a"] = round((na - p[1]) / dt, 1)
                    rec["rate_g"] = round((ng - p[2]) / dt, 1)
                else:
                    rec["rate_a"] = None
                    rec["rate_g"] = None
                self.prev[i] = (t, na, ng)
                self.units[i] = rec
            self.frames += 1
            self.last_frame_at = time.time()
            self.connected = True
            self.error = None

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "units": [self.units[k] for k in sorted(self.units)],
                "frames": self.frames,
                "age_ms": (
                    None
                    if self.last_frame_at is None
                    else round((time.time() - self.last_frame_at) * 1000)
                ),
                "connected": self.connected,
                "error": self.error,
                "ready": self.ready,
                "events": list(self.events[-8:]),
            }


STATE = State()


def serial_reader(port: str, baud: int) -> None:
    """Follow the firmware's NDJSON stream, reconnecting if the board drops.

    The board resets on open, and esptool briefly steals the port during a
    flash, so both are normal and handled by retrying rather than exiting.
    """
    import serial  # imported here so --simulate works without pyserial

    while True:
        try:
            with serial.Serial(port, baud, timeout=1.0) as ser:
                for sig in ("setRTS", "setDTR"):
                    if hasattr(ser, sig):
                        getattr(ser, sig)(False)
                while True:
                    raw = ser.readline()
                    if not raw:
                        continue
                    line = raw.decode("utf-8", errors="replace").strip()
                    if line.startswith("{"):
                        try:
                            STATE.update(json.loads(line))
                        except json.JSONDecodeError:
                            continue
                    elif line.startswith("HOTPLUG") or line.startswith("STREAM_READY"):
                        STATE.event(line)
                        if line.startswith("STREAM_READY"):
                            try:
                                STATE.ready = int(line.split()[1])
                            except (IndexError, ValueError):
                                pass
                    elif line.startswith(("SUMMARY", "UNIT_RESULT", "BUS ")):
                        STATE.event(line)
        except Exception as exc:  # noqa: BLE001 - surfaced to the panel
            with STATE.lock:
                STATE.connected = False
                STATE.error = f"{type(exc).__name__}: {exc}"
            time.sleep(1.0)


def simulator(units: int = 1, absent: set[int] | None = None) -> None:
    """Drive virtual sources so the UI can be checked without hardware."""
    absent = absent or set()
    t0 = time.time()
    na = [0] * units
    ng = [0] * units
    while True:
        t = time.time() - t0
        frame_units = []
        for i in range(units):
            on = 0 if i in absent else 1
            ph = i * 0.7
            roll = math.sin(t * 0.7 + ph) * 0.6
            pitch = math.cos(t * 0.5 + ph) * 0.4
            yaw = t * 0.3 + ph
            cr, sr = math.cos(roll / 2), math.sin(roll / 2)
            cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
            cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
            qx = sr * cp * cy - cr * sp * sy
            qy = cr * sp * cy + sr * cp * sy
            qz = cr * cp * sy - sr * sp * cy
            qw = cr * cp * cy + sr * sp * sy
            n = random.uniform(-0.02, 0.02)
            acc = (-math.sin(pitch) + n,
                   math.sin(roll) * 0.4 + n,
                   math.cos(pitch) * math.cos(roll))
            gyro = (math.cos(t * 0.7 + ph) * 0.42 + n,
                    -math.sin(t * 0.5 + ph) * 0.2 + n,
                    0.3 + n)
            if on:
                na[i] += 2
                ng[i] += 2
            frame_units.append({
                "i": i, "on": on, "id": 0x70 if on else 0, "cs": [1, 2, 4, 5, 6, 7, 8, 9, 10, 14, 15][i],
                "e": 0, "na": na[i], "ng": ng[i],
                "a": [round(v, 3) for v in acc],
                "g": [round(v, 3) for v in gyro],
                "q": [round(qx, 4), round(qy, 4), round(qz, 4), round(qw, 4)],
                "aq": 1, "va": on, "vg": on,
            })
        STATE.update({"t": int(t * 1000), "u": frame_units})
        time.sleep(0.02)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - stdlib name
        if "/stream" in self.path:
            return
        print(f"  {self.address_string()} {format % args}")

    def _send_bytes(self, body: bytes, ctype: str, code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - required name
        path = self.path.split("?", 1)[0]
        if path == "/stream":
            return self._stream()
        if path == "/api/status":
            body = json.dumps(STATE.snapshot()).encode()
            return self._send_bytes(body, "application/json")

        rel = "index.html" if path == "/" else path.lstrip("/")
        target = (WEB_ROOT / rel).resolve()
        if not str(target).startswith(str(WEB_ROOT.resolve())) or not target.is_file():
            return self._send_bytes(b"not found", "text/plain", 404)
        ctype = STATIC_TYPES.get(target.suffix, "application/octet-stream")
        return self._send_bytes(target.read_bytes(), ctype)

    def _stream(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        last_frames = -1
        last_keepalive = time.time()
        try:
            while True:
                with STATE.lock:
                    frames = STATE.frames
                if frames != last_frames:
                    last_frames = frames
                    payload = json.dumps(STATE.snapshot())
                    self.wfile.write(f"data: {payload}\n\n".encode())
                    self.wfile.flush()
                    last_keepalive = time.time()
                elif time.time() - last_keepalive > 15:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    last_keepalive = time.time()
                time.sleep(0.01)
        except (BrokenPipeError, ConnectionResetError):
            return


def fmt(v, spec: str) -> str:
    return "-" if v is None else format(v, spec)


def cli_dashboard() -> None:
    """Terminal view: one line per source, updated in place once a second."""
    try:
        while True:
            s = STATE.snapshot()
            units = s["units"]
            online = sum(1 for u in units if u.get("on"))
            out = ["\x1b[2J\x1b[H"]  # clear + home
            out.append(
                f"LSM6DSV16X  frames={s['frames']}  age={s['age_ms']}ms  "
                f"present={online}/{len(units) if units else '?'}"
                + (f"  error={s['error']}" if s["error"] else "")
                + "\n"
            )
            out.append(
                f"{'idx':>3} {'CS':>3} {'state':7} {'ID':>4} {'a[g]':^21} "
                f"{'g[dps]':^21} {'rate a/g':>11} {'err':>5}\n"
            )
            out.append("-" * 92 + "\n")
            for u in units:
                on = u.get("on")
                a = u.get("a") or [0, 0, 0]
                g = u.get("g") or [0, 0, 0]
                state = "ONLINE" if on else "ABSENT"
                ident = f"{u.get('id', 0):02X}" if on else "--"
                rate = (f"{fmt(u.get('rate_a'), '.0f')}/{fmt(u.get('rate_g'), '.0f')}"
                        if on else "-")
                if on:
                    body = (f"{a[0]:>6.2f} {a[1]:>6.2f} {a[2]:>6.2f} "
                            f"{g[0]:>6.1f} {g[1]:>6.1f} {g[2]:>6.1f} ")
                else:
                    body = f"{'—':>21} {'—':>21} "
                out.append(
                    f"{u['i']:>3} {u.get('cs', '?'):>3} {state:7} {ident:>4} "
                    f"{body}{rate:>11} {u.get('e', 0):>5}\n"
                )
            if s["events"]:
                out.append("\nrecent events:\n")
                for e in s["events"][-5:]:
                    out.append(f"  {e['at']}  {e['text']}\n")
            out.append("\nCtrl+C to stop\n")
            print("".join(out), end="", flush=True)
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nstopped")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyACM0", help="serial port")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--http-port", type=int, default=8000)
    ap.add_argument("--simulate", action="store_true",
                    help="synthetic motion, no hardware")
    ap.add_argument("--units", type=int, default=1,
                    help="virtual unit count for --simulate")
    ap.add_argument("--absent", default="",
                    help="comma-separated virtual indexes to mark absent")
    ap.add_argument("--cli", action="store_true", help="terminal dashboard")
    ap.add_argument("--no-http", action="store_true", help="don't start the web server")
    args = ap.parse_args()

    absent = {int(x) for x in args.absent.split(",") if x.strip()}

    if args.simulate:
        print(f"simulate: {args.units} virtual source(s)"
              + (f", absent={sorted(absent)}" if absent else ""))
        threading.Thread(target=simulator, args=(args.units, absent), daemon=True).start()
    else:
        print(f"reading {args.port} at {args.baud} baud")
        threading.Thread(target=serial_reader, args=(args.port, args.baud), daemon=True).start()

    if args.cli:
        cli_dashboard()
        return 0

    if args.no_http:
        # Headless: keep the reader alive without a browser.
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            return 0

    if not (WEB_ROOT / "index.html").is_file():
        print(f"web/ not found at {WEB_ROOT}")
        return 2

    server = ThreadingHTTPServer(("127.0.0.1", args.http_port), Handler)
    print(f"panel: http://127.0.0.1:{args.http_port}   (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
