#!/usr/bin/env python3
"""Capture the firmware's serial log.

Opens the port with RTS/DTR deasserted (the USB-JTAG bridge ties RTS to BOOT;
leaving it high would hold the part in the ROM downloader), optionally resets
via esptool, then reads until a stop marker or timeout. Raw bytes are saved so
a later analysis does not depend on this process's scrollback.

Usage:
    python3 tools/capture.py [--port /dev/ttyACM0] [--timeout 30]
                             [--stop MATRIX_DONE|STREAM_READY] [--raw out.bin]
                             [--no-reset]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
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
        print(f"reset failed:\n{r.stdout}\n{r.stderr}", file=sys.stderr)
    time.sleep(0.05)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--stop", default="MATRIX_DONE")
    ap.add_argument("--raw", default="")
    ap.add_argument("--no-reset", action="store_true")
    ap.add_argument("--pulse-reset", action="store_true",
                    help="open the port first, then pulse DTR to reset; keeps "
                         "the boot log instead of losing the first second")
    args = ap.parse_args()

    if not args.no_reset and not args.pulse_reset:
        reset(args.port)

    import serial  # pyserial is in the ESP-IDF python env

    raw = bytearray()
    lines: list[str] = []
    deadline = time.time() + args.timeout
    with serial.Serial(args.port, 115200, timeout=0.2) as ser:
        ser.setRTS(False)
        ser.setDTR(False)
        if args.pulse_reset:
            # USB-JTAG bridge: RTS -> GPIO0 (BOOT), DTR -> EN. Hold BOOT
            # released and pulse EN so the ROM loads the app, not the
            # downloader.
            ser.setRTS(False)
            ser.setDTR(True)
            time.sleep(0.06)
            ser.setDTR(False)
            time.sleep(0.15)
        while time.time() < deadline:
            chunk = ser.readline()
            if not chunk:
                continue
            raw.extend(chunk)
            text = chunk.decode("utf-8", errors="replace").rstrip()
            print(text)
            lines.append(text)
            if args.stop and args.stop in text:
                break
            if "waiting for download" in text:
                print("!! board is in the ROM downloader; release BOOT and reset")
                break

    if args.raw:
        Path(args.raw).write_bytes(bytes(raw))
        print(f"\nraw saved: {args.raw} ({len(raw)} bytes)")

    joined = "\n".join(lines)
    if "UNIT_RESULT" in joined or "MATRIX_DONE" in joined or "STREAM_READY" in joined:
        return 0
    print("\nno expected marker seen", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
