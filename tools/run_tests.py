#!/usr/bin/env python3
"""Flash the test firmware, run the health suite, and collect one verdict per source.

Drives the whole loop with no manual steps: flash, reset, capture serial until
MATRIX_DONE, parse UNIT_RESULT/SUMMARY lines, and exit non-zero when a source
that should be present failed or when the expected population is not there.

A source that does not answer WHO_AM_I=0x70 is reported ABSENT, not FAIL: the
firmware probes all configured CS positions so one image works for 1/2/6/11
modules. Use --expect N to assert how many sources this stage should see.

Usage:
    python3 tools/run_tests.py --port /dev/ttyACM0 --expect 2
    python3 tools/run_tests.py --port /dev/ttyACM0 --expect 1 --no-flash
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
IDF_BAUD = 460800
VERIFY_DIR = PROJECT / "build" / "verify"

ESPTOOL_PY = str(
    Path.home() / ".espressif/python_env/idf6.0_py3.12_env/bin/esptool.py"
)

UNIT_RE = re.compile(
    r"UNIT_RESULT (\d+) (PASS|FAIL|ABSENT) (\d+)/(\d+) raw=0x([0-9A-Fa-f]{2}) (.*)"
)
DONE_RE = re.compile(r"MATRIX_DONE (\d+)")
SUMMARY_RE = re.compile(r"SUMMARY present=(\d+) absent=(\d+) count=(\d+)")


def idf_env() -> None:
    out = subprocess.run(
        ["bash", "-lc", "command -v idf.py"], capture_output=True, text=True
    )
    if out.returncode != 0:
        sys.exit(
            "idf.py not found. Run this first in the same shell:\n"
            "  . $HOME/.espressif/v6.0.2/esp-idf/export.sh"
        )


APP_OFFSET = 0x10000
APP_BIN = PROJECT / "build" / "lsm6dsv16x_test.bin"


def flash(port: str | None) -> None:
    cmd = ["idf.py", "-b", str(IDF_BAUD)]
    if port:
        cmd += ["-p", port]
    cmd += ["flash"]
    print(f"$ {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=PROJECT)
    if r.returncode != 0:
        sys.exit(f"flash failed (exit {r.returncode})")
    verify_image(port)


def verify_image(port: str | None) -> None:
    """Read the app image back and compare it with what was built.

    esptool has reported "Hash of data verified" while leaving most of the
    image as 0xFF. A truncated image then fails to boot with
    "invalid segment length 0xffffffff", which reads like a flash-size
    misconfiguration. Comparing the bytes tells the two apart.
    """
    if port is None:
        return
    want = APP_BIN.read_bytes()
    probe = VERIFY_DIR / "flash_verify.bin"
    cmd = [
        sys.executable, ESPTOOL_PY, "--chip", "esp32s3", "-p", port,
        "--before", "default-reset", "--after", "hard-reset",
        "read-flash", hex(APP_OFFSET), str(len(want)), str(probe),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        print(f"WARNING: could not read the image back\n{r.stderr[-400:]}")
        return
    got = probe.read_bytes()
    if got == want:
        print(f"image verified: {len(want)} bytes at {hex(APP_OFFSET)} match")
        return
    first = next((i for i, (a, b) in enumerate(zip(got, want)) if a != b), 0)
    sys.exit(
        f"FLASH WRITE INCOMPLETE at {hex(APP_OFFSET + first)}: the image on the "
        "board does not match the build. Re-run the flash; if it persists, "
        "check the USB cable and that nothing else holds the port."
    )


def reset_board(port: str) -> None:
    """Reset into the application using esptool's sequence.

    The USB-JTAG bridge ties RTS to GPIO0 (BOOT); holding it high latches the
    ROM downloader ("boot:0x22 / waiting for download"). esptool's reset is
    the path that verifiably works here.
    """
    esptool = ESPTOOL_PY if Path(ESPTOOL_PY).exists() else "esptool.py"
    cmd = [
        sys.executable, esptool, "--chip", "esp32s3", "-p", port,
        "--before", "default-reset", "--after", "hard-reset", "chip-id",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    if r.returncode != 0:
        print(f"reset via esptool failed:\n{r.stdout}\n{r.stderr}")
    time.sleep(0.05)  # open fast so the first UNIT_RESULT is not lost


def read_serial(port: str, timeout_s: float) -> str:
    try:
        import serial
    except ImportError:
        sys.exit(
            "pyserial missing; activate ESP-IDF's python env:\n"
            "  . $HOME/.espressif/v6.0.2/esp-idf/export.sh"
        )

    buf = []
    deadline = time.time() + timeout_s
    with serial.Serial(port, 115200, timeout=0.2) as ser:
        ser.setRTS(False)
        ser.setDTR(False)
        while time.time() < deadline:
            line = ser.readline()
            if not line:
                continue
            text = line.decode("utf-8", errors="replace").rstrip()
            print(f"  | {text}")
            buf.append(text)
            if DONE_RE.search(text):
                break
            if "waiting for download" in text:
                print("\n  !! board came up in the ROM downloader. Release "
                      "BOOT and reset.")
                break
    return "\n".join(buf)


def parse(log: str) -> tuple[list[dict], dict | None, bool]:
    units = []
    for m in UNIT_RE.finditer(log):
        idx, verdict, passed, total, raw, detail = m.groups()
        units.append(
            {
                "index": int(idx),
                "state": verdict,
                "passed": int(passed),
                "total": int(total),
                "who_am_i": int(raw, 16),
                "detail": detail.strip(),
            }
        )
    sm = SUMMARY_RE.search(log)
    summary = (
        None
        if not sm
        else {"present": int(sm.group(1)), "absent": int(sm.group(2)),
              "count": int(sm.group(3))}
    )
    return units, summary, bool(DONE_RE.search(log))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--no-flash", action="store_true")
    ap.add_argument("--timeout", type=float, default=90.0)
    ap.add_argument("--expect", type=int, default=None,
                    help="how many sources should answer (default: don't assert)")
    ap.add_argument("--raw", default="")
    args = ap.parse_args()

    VERIFY_DIR.mkdir(parents=True, exist_ok=True)
    idf_env()
    if not args.no_flash:
        flash(args.port)

    reset_board(args.port)
    log = read_serial(args.port, args.timeout)
    units, summary, done = parse(log)

    print()
    if not units:
        print("NO RESULT — no UNIT_RESULT line. Check power, port, baud 115200,")
        print("            and that the firmware actually rebooted.")
        return 2

    if args.raw:
        Path(args.raw).write_text(log)

    print(f"{'src':>3}  {'state':7}  {'checks':>7}  {'WHO':>5}  detail")
    print("-" * 72)
    for u in units:
        checks = f"{u['passed']}/{u['total']}"
        print(f"{u['index']:>3}  {u['state']:7}  {checks:>7}  "
              f"0x{u['who_am_i']:02X}   {u['detail']}")

    present = [u for u in units if u["state"] != "ABSENT"]
    failed = [u for u in present if u["state"] == "FAIL"]
    absent = [u for u in units if u["state"] == "ABSENT"]

    print()
    if not done:
        print("WARNING: MATRIX_DONE never arrived; the log may be truncated.")
    if summary:
        print(f"summary: present={summary['present']} absent={summary['absent']} "
              f"count={summary['count']}")

    problems = []
    if failed:
        problems.append(f"{len(failed)} present source(s) FAILED")
    if args.expect is not None:
        if len(present) < args.expect:
            problems.append(
                f"expected {args.expect} source(s), only {len(present)} answered")
        elif len(present) > args.expect:
            problems.append(
                f"expected {args.expect} source(s), {len(present)} answered")
    if not done:
        problems.append("log truncated (no MATRIX_DONE)")

    if problems:
        print("RESULT: FAIL — " + "; ".join(problems))
        return 1
    print(f"RESULT: PASS — {len(present)} present, {len(absent)} absent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
