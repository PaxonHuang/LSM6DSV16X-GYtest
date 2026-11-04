#!/usr/bin/env python3
"""One-command IMU stage test that says what is broken and what to check next.

    tools/imu.py run 6              flash, verify, run the 6-source stage
    tools/imu.py analyze FILE       re-print a saved capture, no hardware
    tools/imu.py audit              run the offline test suite
    tools/imu.py                    interactive prompt

The verdict comes from the capture itself: the firmware reports WHO_AM_I,
per-check counts and, since 2026-11-03, the error class that parked a source.
Those few numbers are enough to separate a missing wire from a bad contact,
which is the part that used to need a person reading the whole log.
"""

from __future__ import annotations

import argparse
import contextlib
import glob
import hashlib
import io
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
PINMAP = PROJECT / "docs" / "evt-a-pinmap.json"
IMAGE = PROJECT / "build" / "lsm6dsv16x_test.bin"
RUNNER = PROJECT / "tools" / "run_tests.py"
PORT_GLOB = "/dev/serial/by-id/usb-Espressif_*"

STAGES = {
    "2": (0, 1),
    "6": (0, 1, 2, 3, 4, 7),
    "11": tuple(range(11)),
}

# Monotone gate map: package = sid // 4 + 1, channel = sid % 4 + 1.
GATE_PINS = {1: (1, 2, 3), 2: (4, 5, 6), 3: (10, 9, 8), 4: (13, 12, 11)}  # /OE, A, Y
MISO_ROW = {"A": "row 11 上", "B": "row 11 下"}

UNIT_RE = re.compile(
    r"^UNIT_RESULT (\d+) (PASS|FAIL|ABSENT) (\d+)/(\d+) raw=0x([0-9A-Fa-f]{2}) ([^\r\n]*)$",
    re.MULTILINE)
SUMMARY_RE = re.compile(r"^SUMMARY present=(\d+) absent=(\d+) count=(\d+)$", re.MULTILINE)
BIND_RE = re.compile(r"^BUS_BIND (\d+) ([AB]) cs=(\d+)$", re.MULTILINE)
STATS_RE = re.compile(r"^BUS_STATS ([AB]) tx=(\d+) err=(\d+)$", re.MULTILINE)
BOOT_RE = re.compile(r"^BOOT_EPOCH (\d+)$", re.MULTILINE)
CFG_RE = re.compile(
    r"unit (\d+): CTRL1=(0x[0-9A-Fa-f]{2}).*STATUS=(0x[0-9A-Fa-f]{2})")
ERR_RE = re.compile(
    r"unit (\d+) errors total=(\d+) es=(\d+) eb=(\d+) ep=(\d+) parked=(\d+)")
HIST_RE = re.compile(r"unit (\d+) status hist: ([^\r\n]*)")


@dataclass
class Source:
    sid: int
    state: str = "UNKNOWN"
    passed: int = 0
    total: int = 0
    who_am_i: int = 0
    detail: str = ""
    status_at_config: int | None = None
    hist: str = ""
    errors: dict[str, int] = field(default_factory=dict)
    bus: str = "?"
    cs: int | None = None


@dataclass
class Capture:
    raw: str
    sources: dict[int, Source] = field(default_factory=dict)
    present: int = 0
    absent: int = 0
    count: int = 0
    boot_epoch: int | None = None
    bus_stats: dict[str, tuple[int, int]] = field(default_factory=dict)

    @property
    def complete(self) -> bool:
        return "MATRIX_DONE" in self.raw


def parse(text: str) -> Capture:
    cap = Capture(raw=text)
    for m in UNIT_RE.finditer(text):
        sid, state, ok, total, who, detail = m.groups()
        cap.sources[int(sid)] = Source(
            sid=int(sid), state=state, passed=int(ok), total=int(total),
            who_am_i=int(who, 16), detail=detail.strip())
    for m in CFG_RE.finditer(text):
        sid = int(m.group(1))
        if sid in cap.sources:
            cap.sources[sid].status_at_config = int(m.group(3), 16)
    for m in HIST_RE.finditer(text):
        sid = int(m.group(1))
        if sid in cap.sources:
            cap.sources[sid].hist = m.group(2).strip()
    for m in ERR_RE.finditer(text):
        sid = int(m.group(1))
        if sid in cap.sources:
            cap.sources[sid].errors = {
                "es": int(m.group(3)), "eb": int(m.group(4)), "ep": int(m.group(5))}
    for m in BIND_RE.finditer(text):
        sid = int(m.group(1))
        if sid in cap.sources:
            cap.sources[sid].bus = m.group(2)
            cap.sources[sid].cs = int(m.group(3))
    sm = SUMMARY_RE.search(text)
    if sm:
        cap.present, cap.absent, cap.count = (int(sm.group(i)) for i in (1, 2, 3))
    bm = BOOT_RE.search(text)
    if bm:
        cap.boot_epoch = int(bm.group(1))
    for m in STATS_RE.finditer(text):
        cap.bus_stats[m.group(1)] = (int(m.group(2)), int(m.group(3)))
    return cap


def gate_pins(sid: int) -> tuple[int, int, int, int]:
    """(package, /OE pin, A pin, Y pin) for one source."""
    pkg, ch = sid // 4 + 1, sid % 4 + 1
    oe, a, y = GATE_PINS[ch]
    return pkg, oe, a, y


def check_lines(src: Source) -> list[str]:
    """The wires worth re-seating for this source, most likely first."""
    pkg, oe, a, y = gate_pins(src.sid)
    cs = f"GPIO{src.cs}" if src.cs is not None else "对应 CS"
    row = MISO_ROW.get(src.bus, "对应 MISO 汇流")
    return [
        f"模块 sid{src.sid} SDO → U{pkg} p{a}",
        f"{cs} → U{pkg} p{oe} (/OE)",
        f"U{pkg} p{y} (Y) → {row}",
        f"模块 sid{src.sid} VCC 是否有 3.3 V",
    ]


@dataclass
class Finding:
    src: Source
    diagnosis: str
    checks: list[str]


def diagnose(cap: Capture, expected: set[int] | None = None) -> list[Finding]:
    """Turn the captured numbers into a verdict plus the next thing to check.

    The rules come from measurements on this bench:
      * 0xFF  - nothing drives the bus for that address, so the gate is off.
      * 0x00  - the gate is on and driving low, so /OE and the output reach the
                bus and the input side (module SDO or its supply) is what's
                missing.
      * ep>0  - the 12-byte block transferred fine but the data was
                implausible, which is a contact problem, not a missing wire.
    """
    out = []
    wanted = expected if expected is not None else set(cap.sources)
    for sid in sorted(cap.sources):
        if sid not in wanted:
            continue  # not wired for this stage: absent is the expected state
        src = cap.sources[sid]
        checks = check_lines(src)

        if src.state == "PASS":
            continue

        if src.state == "ABSENT":
            if src.who_am_i == 0x00:
                what = ("稳定读回 0x00：门是使能着的、输出也已经接到总线上，"
                        "被拉低的是输入端")
                why = [checks[0], checks[3]]
            elif src.who_am_i == 0xFF:
                what = "读回 0xFF：这一路没有驱动总线，门没有导通"
                why = [checks[1], checks[3]]
            else:
                what = f"读回 0x{src.who_am_i:02X}：既不是 0x70 也不是确定的 0x00/0xFF"
                why = checks
            out.append(Finding(src, what, why))
            continue

        # FAIL: the device answered, so the verdict comes from the error class.
        err = src.errors
        if err.get("ep"):
            what = "burst 数据损坏：传输本身成功，但读回的加速度模长不合理"
            hint = "单字节读正常、连续 12 字节读坏，属于该通道接触/信号质量"
            why = [checks[0], checks[2]]
        elif err.get("eb"):
            what = "12 字节 burst 传输失败"
            hint = "SPI 传输层面就失败了"
            why = [checks[2], checks[1]]
        elif err.get("es"):
            what = "STATUS 单字节读传输失败"
            hint = "连单字节都传不动"
            why = [checks[1], checks[0]]
        elif src.status_at_config is not None:
            what = f"寄存器可读（STATUS=0x{src.status_at_config:02X}）但采样窗口没有数据"
            hint = "怀疑器件没有按 ODR 出数或该模块供电不稳"
            why = [checks[3], checks[0]]
        else:
            what = f"自检 {src.passed}/{src.total} 未通过（{src.detail}）"
            hint = "旧固件没有错误分类，无法进一步定性"
            why = checks
        out.append(Finding(src, f"{what}；{hint}", why))

    if expected:
        missing = sorted(expected - set(cap.sources))
        for sid in missing:
            out.append(Finding(Source(sid=sid), "捕获里没有这一路的结果", []))
    return out


def image_identity() -> str:
    if not IMAGE.is_file():
        return "未构建"
    data = IMAGE.read_bytes()
    return f"{len(data)} B  sha256 {hashlib.sha256(data).hexdigest()[:12]}…"


def render(cap: Capture, expected: set[int] | None = None) -> str:
    lines = []
    head = f"镜像 {image_identity()}"
    if expected:
        head += "   阶段 " + ",".join(str(s) for s in sorted(expected))
    else:
        head += "   未指定阶段，按全部 11 路判断"
    lines.append(head)
    if cap.boot_epoch is not None:
        lines.append(f"BOOT_EPOCH {cap.boot_epoch}")
    lines.append("")
    lines.append(f"{'src':>3}  {'状态':<7} {'自检':>7}  {'WHO':>5}  总线  CS")
    lines.append("-" * 52)
    shown = sorted(expected) if expected else sorted(cap.sources)
    for sid in shown:
        s = cap.sources.get(sid)
        if s is None:
            lines.append(f"{sid:>3}  {'缺失':<7} {'-':>7}  {'-':>5}   -   -")
            continue
        lines.append(f"{sid:>3}  {s.state:<7} {s.passed:>3}/{s.total:<3}  "
                     f"0x{s.who_am_i:02X}   {s.bus}   {s.cs if s.cs is not None else '-'}")
    if not cap.complete:
        lines.append("")
        lines.append("注意：捕获里没有 MATRIX_DONE，判断可能不完整。")
    if cap.bus_stats:
        parts = [f"{b} tx={tx} err={err}" for b, (tx, err) in sorted(cap.bus_stats.items())]
        lines.append("")
        lines.append("总线 " + "   ".join(parts))

    findings = diagnose(cap, expected)
    lines.append("")
    if not findings:
        if cap.complete:
            lines.append("判断：全部通过。")
        else:
            lines.append("判断：捕获不完整，没有 MATRIX_DONE，先确认烧录与复位。")
    else:
        lines.append("判断与下一步")
        for f in findings:
            lines.append(f"  src {f.src.sid}  {f.diagnosis}")
            for c in f.checks:
                lines.append(f"          → {c}")
    return "\n".join(lines)


def find_port() -> str:
    ports = sorted(glob.glob(PORT_GLOB))
    if not ports:
        raise SystemExit(
            "没有找到 Espressif 串口。\n"
            "  检查：板子插好了吗？USB 线是不是只能充电不传数据？\n"
            "  插好后用这条命令确认：ls /dev/serial/by-id/")
    if len(ports) > 1:
        raise SystemExit("找到多个 Espressif 串口，用 --port 指定其中一个：\n  "
                         + "\n  ".join(ports))
    return ports[0]


def run_stage(stage: str, port: str | None, keep: str | None) -> int:
    expected = STAGES[stage]
    port = port or find_port()
    workdir = None
    if keep:
        raw_path = Path(keep)
        if raw_path.exists():
            raise SystemExit(f"{keep} 已存在，换一个路径。")
    else:
        # run_tests.py refuses an existing --raw, so reserve a directory and
        # hand it a path that does not exist yet.
        workdir = Path(tempfile.mkdtemp(prefix="imu-"))
        raw_path = workdir / "capture.raw"

    cmd = [sys.executable, str(RUNNER), "--port", port,
           "--expect-sources", ",".join(str(s) for s in expected),
           "--raw", str(raw_path)]
    print(f"$ {' '.join(cmd)}")
    print("烧录并运行健康测试，约 20 秒…", flush=True)
    proc = subprocess.run(cmd, cwd=PROJECT, text=True, capture_output=True)
    # Parse the raw capture, not the runner's stdout: the runner decorates
    # every line with "  | " so the record grammar no longer starts the line.
    if raw_path.is_file() and raw_path.stat().st_size:
        text = raw_path.read_text(encoding="utf-8", errors="replace")
    else:
        text = proc.stdout + proc.stderr
    cap = parse(text)
    print()
    if not cap.sources:
        print("没有解析到任何 UNIT_RESULT，运行器输出如下：")
        print("\n".join((proc.stdout + proc.stderr).strip().splitlines()[-15:]))
    else:
        print(render(cap, set(expected)))

    if workdir is not None:
        shutil.rmtree(workdir, ignore_errors=True)
    if not cap.sources:
        return 1
    return 0 if not diagnose(cap, set(expected)) and cap.complete else 1


def analyze_file(path: str, stage: str | None) -> int:
    expected = set(STAGES[stage]) if stage else None
    cap = parse(Path(path).read_text(encoding="utf-8", errors="replace"))
    print(render(cap, expected))
    return 0 if not diagnose(cap, expected) else 1


def audit() -> int:
    """Run the offline suite quietly; only a failure prints its detail."""
    suite = unittest.defaultTestLoader.discover(str(PROJECT / "tests"), pattern="test_*.py")
    noise = io.StringIO()
    with contextlib.redirect_stdout(noise), contextlib.redirect_stderr(noise):
        result = unittest.TextTestRunner(verbosity=0, stream=noise).run(suite)
    bad = len(result.failures) + len(result.errors)
    print(f"离线测试 {result.testsRun} 项，失败 {bad} 项")
    if bad:
        for case, tb in result.failures + result.errors:
            print(f"\n{case}")
            print(tb.rstrip())
    return 0 if bad == 0 else 1


HELP = """命令
  run 2        2 源：sid 0,1
  run 6        6 源：sid 0,1,2,3,4,7
  run 11       11 源：sid 0 到 10
  run 6 文件名  同上，但把原始输出另存一份，之后可以离线再看
  analyze 文件名 [2|6|11]   离线看一份保存过的结果，不需要接板子
  audit        检查工具本身是否正常（不需要硬件）
  help         显示这份说明
  quit         退出

跑完怎么看
  屏幕上先是一张表，每个源一行：PASS 正常，ABSENT 没找到，FAIL 找到了但没通过。
  表下面是「判断与下一步」，每一行都写明该用万用表查哪根线，从上往下查。

常见情况
  · 显示「没有找到 Espressif 串口」→ 板子没插好，或者 USB 线只供电不传数据
  · 停在「烧录并运行健康测试」不动 → 正常，烧录大约 20 秒
  · 某路读回 0x00 → 那一颗模块的 SDO 或供电没接上
  · 某路读回 0xFF → 这一路的 CS 没接到门（/OE）"""


def banner() -> str:
    try:
        port = find_port()
        port_line = f"串口：{port}"
    except SystemExit:
        port_line = "串口：未找到（板子没插？插好后再 run）"
    return "\n".join([
        "IMU 台架工具",
        f"工程：{PROJECT}",
        port_line,
        f"镜像：{image_identity()}",
        "",
        "第一次用就按这个顺序：",
        "  1. 断电接好线，再上电",
        "  2. 输入 run 6 回车（这个阶段是 sid 0,1,2,3,4,7）",
        "  3. 看最后的「判断与下一步」，照着上面的线去查",
        "",
        "输入 help 看全部命令，quit 退出。",
    ])


def repl() -> int:
    print(banner())
    while True:
        try:
            line = input("\nimu> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        parts = line.split()
        cmd = parts[0].lower()
        try:
            if cmd in ("quit", "exit", "q"):
                print("再见。")
                return 0
            if cmd == "help":
                print(HELP)
            elif cmd == "run" and 2 <= len(parts) <= 3:
                if parts[1] not in STAGES:
                    print(f"阶段只能是 2、6 或 11，你说的是 {parts[1]!r}。输入 help 看说明。")
                    continue
                keep = parts[2] if len(parts) == 3 else None
                print(f"开始跑 {parts[1]} 源阶段…")
                code = run_stage(parts[1], None, keep)
                print("\n本次结果：" + ("通过。" if code == 0 else "有未通过的源，见上面的判断。"))
            elif cmd == "analyze" and 2 <= len(parts) <= 3:
                stage = parts[2] if len(parts) == 3 and parts[2] in STAGES else None
                analyze_file(parts[1], stage)
            elif cmd == "audit":
                audit()
            else:
                print(f"看不懂 {line!r}。输入 help 看可用命令。")
        except SystemExit as exc:
            print(exc)
        except FileNotFoundError as exc:
            print(f"打不开文件：{exc.filename}")
        except Exception as exc:  # keep the prompt alive on a bad command
            print(f"出错：{exc}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("run", help="烧录并跑一个阶段")
    r.add_argument("stage", choices=sorted(STAGES))
    r.add_argument("--port")
    r.add_argument("--keep", help="保留原始捕获到这个路径（默认不保留）")
    a = sub.add_parser("analyze", help="离线重放一份捕获")
    a.add_argument("file")
    a.add_argument("stage", nargs="?", choices=sorted(STAGES),
                   help="该捕获对应的阶段；不给则按全部 11 路判断")
    sub.add_parser("audit", help="跑离线测试")
    args = ap.parse_args()

    if args.cmd == "run":
        return run_stage(args.stage, args.port, args.keep)
    if args.cmd == "analyze":
        return analyze_file(args.file, args.stage)
    if args.cmd == "audit":
        return audit()
    return repl()


if __name__ == "__main__":
    raise SystemExit(main())
