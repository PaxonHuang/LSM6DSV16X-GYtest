#!/usr/bin/env python3
"""Flash the test firmware, run the health suite, and collect one verdict per source.

Drives the whole loop with no manual steps: flash, reset, capture serial until
MATRIX_DONE, parse UNIT_RESULT/SUMMARY lines, and exit non-zero when a source
that should be present failed or when the expected population is not there.

A source that does not answer WHO_AM_I=0x70 is reported ABSENT, not FAIL: the
firmware probes all configured CS positions so one image works for 1/2/6/11
modules. Use --expect N for sources 0..N-1, or --expect-sources for an explicit set.

Usage:
    python3 tools/run_tests.py --port /dev/ttyACM0 --expect 2
    python3 tools/run_tests.py --port /dev/ttyACM0 --expect 1 --no-flash
"""

from __future__ import annotations

from contextlib import ExitStack
import argparse
import re
import subprocess
import sys
import time
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
IDF_BAUD = 460800
VERIFY_DIR = PROJECT / "build" / "verify"

ESPTOOL_PY = str(
    Path.home() / ".espressif/python_env/idf6.0_py3.12_env/bin/esptool.py"
)

UNIT_RE = re.compile(
    r"^UNIT_RESULT (\d+) (PASS|FAIL|ABSENT) (\d+)/(\d+) raw=0x([0-9A-Fa-f]{2}) ([^\r\n]*)\r?$", re.MULTILINE
)
DONE_RE = re.compile(r"^MATRIX_DONE (\d+)\r?$", re.MULTILINE)
SUMMARY_RE = re.compile(r"^SUMMARY present=(\d+) absent=(\d+) count=(\d+)\r?$", re.MULTILINE)
BUS_RE = re.compile(r"^BUS profile=(\S+) units=(\d+)\r?$", re.MULTILINE)
BIND_RE = re.compile(r"^BUS_BIND (\d+) ([AB]) cs=(\d+)\r?$", re.MULTILINE)
STATS_RE = re.compile(r"^BUS_STATS ([AB]) tx=(\d+) err=(\d+)\r?$", re.MULTILINE)


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
        sys.exit("flash readback requires an explicit port")
    want = APP_BIN.read_bytes()
    if not want:
        sys.exit("empty application image")
    VERIFY_DIR.mkdir(parents=True, exist_ok=True)
    probe = Path(tempfile.mkdtemp(prefix="readback-", dir=VERIFY_DIR)) / "flash_verify.bin"
    print(f"readback evidence: {probe}")
    cmd = [
        sys.executable, ESPTOOL_PY, "--chip", "esp32s3", "-p", port,
        "--before", "default-reset", "--after", "hard-reset",
        "read-flash", hex(APP_OFFSET), str(len(want)), str(probe),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        sys.exit(f"FLASH READBACK FAILED: {exc}")
    if r.returncode != 0:
        sys.exit(f"FLASH READBACK FAILED (exit {r.returncode}): {r.stderr[-400:]}")
    if not probe.is_file():
        sys.exit("FLASH READBACK FAILED: no output image")
    got = probe.read_bytes()
    if got == want:
        print(f"image verified: {len(want)} bytes at {hex(APP_OFFSET)} match")
        return
    first = next((i for i, (a, b) in enumerate(zip(got, want)) if a != b), min(len(got), len(want)))
    sys.exit(
        f"FLASH WRITE INCOMPLETE at {hex(APP_OFFSET + first)}: the image on the "
        "board does not match the build. STOP and preserve the readback; "
        "inspect image, device identity and USB ownership before another run."
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
        sys.exit(f"reset via esptool failed:\n{r.stdout}\n{r.stderr}")
    time.sleep(0.05)  # open fast so the first UNIT_RESULT is not lost


def read_serial(port: str, timeout_s: float, raw_path=None) -> bytes:
    try:
        import serial
    except ImportError:
        sys.exit(
            "pyserial missing; activate ESP-IDF's python env:\n"
            "  . $HOME/.espressif/v6.0.2/esp-idf/export.sh"
        )

    buf = []
    deadline = time.monotonic() + timeout_s
    with ExitStack() as stack:
        raw_file = None if raw_path is None else stack.enter_context(Path(raw_path).open('ab'))
        ser = stack.enter_context(serial.Serial(port, 115200, timeout=0.2))
        ser.setRTS(False)
        ser.setDTR(False)
        line = bytearray()
        while time.monotonic() < deadline:
            # pyserial.readline() can discard accumulated bytes if unplugged
            # before newline. A one-byte read has no unpersisted prefix.
            byte = ser.read(1)
            if not byte:
                continue
            if raw_file is not None:
                raw_file.write(byte)
                raw_file.flush()
            buf.append(byte)
            line.extend(byte)
            if byte != b"\n":
                continue
            text = line.decode("utf-8", errors="replace").rstrip()
            print(f"  | {text}")
            line.clear()
            if DONE_RE.fullmatch(text):
                break
            if "waiting for download" in text:
                print("ROM downloader observed; STOP and preserve evidence.")
                break
    return b"".join(buf)


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


def validate_bus(log: str, units: list[dict], summary: dict | None) -> list[str]:
    """Check the additive bus plan: profile, per-source binding, counters.

    The frozen UNIT_RESULT/SUMMARY/MATRIX_DONE grammar is unchanged; these
    records carry the EVT-A two-bus evidence the health verdict depends on.
    """
    problems = []
    buses = list(BUS_RE.finditer(log))
    binds = list(BIND_RE.finditer(log))
    stats = list(STATS_RE.finditer(log))
    if len(buses) != 1:
        problems.append("exactly one BUS profile record required")
    if log.count("BUS profile=") != len(buses):
        problems.append("malformed BUS profile record")
    if log.count("BUS_BIND") != len(binds):
        problems.append("malformed BUS_BIND record")
    if log.count("BUS_STATS") != len(stats):
        problems.append("malformed BUS_STATS record")
    if not buses:
        return problems
    profile = buses[0].group(1)
    if profile not in ("evta-dual", "legacy-single"):
        problems.append(f"unknown bus profile {profile}")
        return problems
    if summary is None:
        return problems
    count = summary["count"]
    ids = [int(m.group(1)) for m in binds]
    if len(ids) != len(set(ids)) or sorted(ids) != list(range(count)):
        problems.append("BUS_BIND source set incomplete or duplicated")
    for m in binds:
        sid, bus = int(m.group(1)), m.group(2)
        want = "A" if (profile == "legacy-single" or 1 <= sid <= 6) else "B"
        if bus != want:
            problems.append(f"source {sid} bound to bus {bus}, contract wants {want}")
    by_bus: dict[str, tuple[int, int]] = {}
    for m in stats:
        b = m.group(1)
        if b in by_bus:
            problems.append(f"duplicate BUS_STATS {b}")
        by_bus[b] = (int(m.group(2)), int(m.group(3)))
    used = {m.group(2) for m in binds}
    if set(by_bus) != used:
        problems.append("BUS_STATS must cover exactly the buses named by BUS_BIND")
    if profile == "legacy-single" and "B" in used:
        problems.append("legacy-single must not bind a source to bus B")
    for b, (tx, err) in by_bus.items():
        if err > tx:
            problems.append(f"BUS_STATS {b} errors exceed transactions")
    present = [u for u in units if u["state"] != "ABSENT"]
    for u in present:
        b = "A" if (profile == "legacy-single" or 1 <= u["index"] <= 6) else "B"
        if b in by_bus and by_bus[b][0] == 0:
            problems.append(f"source {u['index']} present but bus {b} saw no traffic")
    return problems


def validate_log(log: str, expected: set[int]) -> list[str]:
    """Reject incomplete/mixed matrices before any health PASS is possible."""
    units, summary, done = parse(log)
    problems = []
    summaries = list(SUMMARY_RE.finditer(log))
    endings = list(DONE_RE.finditer(log))
    matches = list(UNIT_RE.finditer(log))
    if len(summaries) != 1 or len(endings) != 1:
        problems.append("exactly one SUMMARY and MATRIX_DONE required")
    ids = [u["index"] for u in units]
    if len(ids) != len(set(ids)):
        problems.append("duplicate source ID")
    if summary is not None:
        count = summary["count"]
        if count < 1 or count > 11 or set(ids) != set(range(count)):
            problems.append("configured source matrix incomplete or out of range")
        present = [u for u in units if u["state"] != "ABSENT"]
        absent = [u for u in units if u["state"] == "ABSENT"]
        if summary["present"] != len(present) or summary["absent"] != len(absent):
            problems.append("SUMMARY population disagrees with UNIT_RESULT")
        if summary["present"] + summary["absent"] != count:
            problems.append("SUMMARY population disagrees with count")
        if endings and int(endings[0].group(1)) != count:
            problems.append("MATRIX_DONE disagrees with SUMMARY count")
        if {u["index"] for u in present} != expected:
            problems.append("present source set disagrees with expected source IDs")
    if len(summaries) == len(endings) == 1:
        if summaries[0].start() > endings[0].start() or any(m.start() > summaries[0].start() for m in matches):
            problems.append("matrix records out of order")
    for u in units:
        if u["state"] == "PASS" and (u["total"] <= 0 or u["passed"] != u["total"] or u["who_am_i"] != 0x70):
            problems.append(f"source {u['index']} inconsistent PASS")
        if u["state"] == "ABSENT" and (u["passed"] != 0 or u["total"] != 0):
            problems.append(f"source {u['index']} inconsistent ABSENT")
        if u["state"] == "FAIL":
            problems.append(f"source {u['index']} FAILED")
    # A malformed sentinel cannot disappear silently during regex parsing.
    for token, pattern in (("UNIT_RESULT", UNIT_RE), ("SUMMARY", SUMMARY_RE), ("MATRIX_DONE", DONE_RE)):
        if log.count(token) != len(list(pattern.finditer(log))):
            problems.append(f"malformed {token} record")
    problems.extend(validate_bus(log, units, summary))
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--no-flash", action="store_true")
    ap.add_argument("--timeout", type=float, default=90.0)
    ap.add_argument("--expect", type=int, default=None,
                    help="exact present population 0..N-1; requires explicit stage")
    ap.add_argument("--expect-sources", help="comma-separated exact present IDs; --expect N defaults to 0..N-1")
    ap.add_argument("--raw", default="")
    args = ap.parse_args()
    if args.expect is not None and not 1 <= args.expect <= 11:
        ap.error('--expect must be 1..11')
    try:
        ids = None if args.expect_sources is None else [int(x) for x in args.expect_sources.split(',')]
    except ValueError:
        ap.error('--expect-sources must contain integer IDs')
    if ids is not None and (not ids or len(ids) != len(set(ids)) or any(x < 0 or x > 10 for x in ids)):
        ap.error('--expect-sources must contain unique IDs in 0..10')
    if ids is None and args.expect is None:
        ap.error('an explicit --expect or --expect-sources is required')
    expected = set(range(args.expect)) if ids is None else set(ids)
    if args.expect is not None and len(expected) != args.expect:
        ap.error('--expect and --expect-sources disagree')
    if args.timeout <= 0 or not args.timeout < float('inf'):
        ap.error('--timeout must be finite and positive')
    if args.raw and Path(args.raw).exists():
        ap.error('--raw must be a new file')

    VERIFY_DIR.mkdir(parents=True, exist_ok=True)
    if not args.raw:
        args.raw = str(VERIFY_DIR / f"capture-{time.time_ns()}.raw")
    # Reserve before any flash/reset so unusable evidence paths fail first.
    with Path(args.raw).open('xb'):
        pass
    print(f"serial evidence: {args.raw}")
    idf_env()
    if not args.no_flash:
        flash(args.port)

    reset_board(args.port)
    captured = read_serial(args.port, args.timeout, args.raw or None)
    log = captured.decode('utf-8', errors='replace')
    units, summary, done = parse(log)

    print()
    if not units:
        print("NO RESULT — no UNIT_RESULT line. Check power, port, baud 115200,")
        print("            and that the firmware actually rebooted.")
        return 2


    print(f"{'src':>3}  {'state':7}  {'checks':>7}  {'WHO':>5}  detail")
    print("-" * 72)
    for u in units:
        checks = f"{u['passed']}/{u['total']}"
        print(f"{u['index']:>3}  {u['state']:7}  {checks:>7}  "
              f"0x{u['who_am_i']:02X}   {u['detail']}")

    present = [u for u in units if u["state"] != "ABSENT"]
    absent = [u for u in units if u["state"] == "ABSENT"]

    print()
    if not done:
        print("WARNING: MATRIX_DONE never arrived; the log may be truncated.")
    if summary:
        print(f"summary: present={summary['present']} absent={summary['absent']} "
              f"count={summary['count']}")

    problems = validate_log(log, expected)
    if problems:
        print("RESULT: FAIL — " + "; ".join(problems))
        return 1
    print(f"RESULT: PASS — {len(present)} present, {len(absent)} absent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
