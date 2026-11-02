#!/usr/bin/env python3
"""Capture the NDJSON stream with a host monotonic receive time per frame.

Each complete line is stored as one JSON object with an added `host_ns` field
(``time.monotonic_ns()`` at the moment the terminating newline arrived). Raw
serial bytes are saved separately so a capture can be replayed byte-for-byte.

The recorded file is the only input `tools/analyze_stream.py` needs; replay
never touches the device or the wall clock.

Usage:
    python3 tools/stream_capture.py --port /dev/ttyACM0 --duration 60 \
        --out evidence/x/stream.jsonl --raw evidence/x/stream.raw
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from contextlib import ExitStack
from pathlib import Path

ESPTOOL_PY = str(
    Path.home() / ".espressif/python_env/idf6.0_py3.12_env/bin/esptool.py"
)


def reset(port: str) -> None:
    esptool = ESPTOOL_PY if Path(ESPTOOL_PY).exists() else "esptool.py"
    r = subprocess.run(
        [sys.executable, esptool, "--chip", "esp32s3", "-p", port,
         "--before", "default-reset", "--after", "hard-reset", "chip-id"],
        capture_output=True, text=True, timeout=90,
    )
    if r.returncode != 0:
        sys.exit(f"reset failed:\n{r.stdout}\n{r.stderr}")
    time.sleep(0.05)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--duration", type=float, default=60.0)
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--out", required=True, help="JSONL with host_ns per frame")
    ap.add_argument("--raw", default="", help="optional raw serial bytes")
    ap.add_argument("--no-reset", action="store_true")
    args = ap.parse_args()

    out_path = Path(args.out)
    if out_path.exists():
        sys.exit("--out must be a new file")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path = Path(args.raw) if args.raw else None
    if raw_path is not None and raw_path.exists():
        sys.exit("--raw must be a new file")

    if not args.no_reset:
        reset(args.port)

    import serial  # pyserial lives in the ESP-IDF python env

    frames = 0
    bad_lines = 0
    raw_bytes = 0
    buf = bytearray()
    deadline = time.monotonic() + args.duration

    with ExitStack() as stack:
        out = stack.enter_context(open(out_path, "w", encoding="utf-8"))
        raw_file = (stack.enter_context(open(raw_path, "wb"))
                    if raw_path is not None else None)
        ser = stack.enter_context(serial.Serial(args.port, args.baud, timeout=0.05))
        ser.setRTS(False)
        ser.setDTR(False)
        while time.monotonic() < deadline:
            chunk = ser.read(ser.in_waiting or 1)
            if not chunk:
                continue
            raw_bytes += len(chunk)
            if raw_file is not None:
                raw_file.write(chunk)
            buf.extend(chunk)
            while True:
                nl = buf.find(b"\n")
                if nl < 0:
                    break
                line = bytes(buf[:nl])
                del buf[:nl + 1]
                host_ns = time.monotonic_ns()
                text = line.decode("utf-8", errors="replace").rstrip()
                if not text:
                    continue
                try:
                    obj = json.loads(text)
                except json.JSONDecodeError:
                    bad_lines += 1
                    obj = {"raw_line": text}
                obj["host_ns"] = host_ns
                out.write(json.dumps(obj, separators=(",", ":")) + "\n")
                frames += 1
        if raw_file is not None:
            raw_file.write(buf)

    print(f"captured {frames} lines ({bad_lines} non-JSON), {raw_bytes} raw bytes "
          f"in {args.duration:.1f}s -> {out_path}")
    if frames == 0:
        print("NO FRAMES — check port, power and that the image is STREAM mode",
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
