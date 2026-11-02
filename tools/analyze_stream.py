#!/usr/bin/env python3
"""Deterministic offline analysis of a captured NDJSON stream.

Input is the file written by `tools/stream_capture.py`, so a replay reads only
the recorded host monotonic receive times and frame contents — no device, no
wall clock, identical output every run.

Time semantics (kept separate on purpose):
    sensor sample time  = unknown (not measured; no FIFO timestamp here)
    MCU read time       = u.mt (esp_timer_get_time, µs)
    MCU transmit time   = frame t (ms, when the frame was built)
    host receive time   = host_ns (time.monotonic_ns, ns)

No cross-clock absolute latency is claimed: only within-source intervals use
MCU time, and arrival gaps use host time.

Usage:
    python3 tools/analyze_stream.py --input cap.jsonl
    python3 tools/analyze_stream.py --input cap.jsonl --window 10 --out r.json
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections.abc import Sequence
from pathlib import Path


def _pct(values: Sequence[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * q))))
    return ordered[idx]


def _deltas(values: list[int]) -> list[int]:
    return [b - a for a, b in zip(values, values[1:])]


def analyze(frames: list[dict], window_s: float = 10.0) -> dict:
    """Aggregate one capture. Pure: no time or device access."""
    if not frames:
        raise ValueError("no frames")
    everything = frames
    frames = [f for f in frames if "u" in f]
    if not frames:
        raise ValueError("no NDJSON frames (only boot/log lines)")
    non_frame_lines = len(everything) - len(frames)

    first_ns = frames[0]["host_ns"]
    last_ns = frames[-1]["host_ns"]
    span_s = (last_ns - first_ns) / 1e9
    n = len(frames)

    arrivals = [f["host_ns"] for f in frames]
    intervals_us = [d / 1000.0 for d in _deltas(arrivals)]
    med_us = statistics.median(intervals_us) if intervals_us else None
    # A USB/transmit gap is an arrival interval well beyond the normal cadence.
    gap_limit_us = max(3 * med_us, 100_000.0) if med_us is not None else None
    gaps = [x for x in intervals_us if gap_limit_us is not None and x > gap_limit_us]

    boots = [f.get("b") for f in frames if "b" in f]
    boot_changes = sum(1 for a, b in zip(boots, boots[1:]) if a != b)
    t_seq = [f["t"] for f in frames if isinstance(f.get("t"), (int, float))]
    t_regressions = sum(1 for a, b in zip(t_seq, t_seq[1:]) if b < a)

    sources = sorted({u["i"] for f in frames for u in f.get("u", [])
                      if u.get("on") == 1})
    per_source: dict[str, dict] = {}
    for sid in sources:
        rows = [u for f in frames for u in f.get("u", [])
                if u.get("i") == sid and u.get("on") == 1]
        if not rows:
            continue
        fresh = [u for u in rows if u.get("va") == 1]
        seq = [u.get("sq") for u in fresh if isinstance(u.get("sq"), int)]
        seq_gaps = sum(max(0, b - a - 1) for a, b in zip(seq, seq[1:]))
        read_us = _deltas([u["mt"] for u in fresh if isinstance(u.get("mt"), int)])
        last_error = rows[-1].get("e", 0)
        per_source[str(sid)] = {
            "frames": len(rows),
            "new_samples": len(fresh),
            "snapshot_frames": len(rows) - len(fresh),
            "valid_ratio": len(fresh) / len(rows) if rows else None,
            "seq_first": seq[0] if seq else None,
            "seq_last": seq[-1] if seq else None,
            "seq_gaps": seq_gaps,
            "read_rate_hz": ((seq[-1] - seq[0]) / span_s
                             if len(seq) > 1 and span_s > 0 else None),
            "mcu_read_interval_us": {
                "median": statistics.median(read_us) if read_us else None,
                "p95": _pct(read_us, 0.95),
                "max": max(read_us) if read_us else None,
            },
            "errors_delta": last_error - rows[0].get("e", 0),
            "duplicate_delta": rows[-1].get("d", 0) - rows[0].get("d", 0),
            "snapshot_counter_delta": rows[-1].get("sk", 0) - rows[0].get("sk", 0),
        }

    windows: list[dict] = []
    if span_s > 0:
        width = max(1, int(window_s * 1e9))
        buckets: dict[int, list[dict]] = {}
        for f in frames:
            buckets.setdefault((f["host_ns"] - first_ns) // width, []).append(f)
        for idx in sorted(buckets):
            wf = buckets[idx]
            counts = {}
            for f in wf:
                for u in f.get("u", []):
                    if u.get("on") == 1 and u.get("va") == 1:
                        counts[u["i"]] = counts.get(u["i"], 0) + 1
            windows.append({
                "start_s": round(idx * window_s, 3),
                "frames": len(wf),
                "new_samples": {str(k): v for k, v in sorted(counts.items())},
            })

    return {
        "frames": n,
        "non_frame_lines": non_frame_lines,
        "span_s": round(span_s, 3),
        "frame_rate_hz": round(n / span_s, 2) if span_s > 0 else None,
        "boot_epochs": sorted({b for b in boots if b is not None}),
        "boot_changes": boot_changes,
        "mcu_time_regressions": t_regressions,
        "arrival_interval_us": {
            "median": med_us,
            "p95": _pct(intervals_us, 0.95),
            "max": max(intervals_us) if intervals_us else None,
            "gap_limit": gap_limit_us,
            "gaps": len(gaps),
            "max_gap_us": max(gaps) if gaps else 0.0,
        },
        "backpressure": {
            "late_last": frames[-1].get("late"),
            "mwus_max_all_frames": max(f.get("mwus", 0) for f in frames),
        },
        "sources": per_source,
        "windows": windows,
        "time_semantics": {
            "sensor_sample_time": "unknown",
            "mcu_read_time": "frame.u[].mt (esp_timer µs)",
            "mcu_transmit_time": "frame.t (ms)",
            "host_receive_time": "frame.host_ns (time.monotonic_ns)",
        },
    }


def load(path: Path) -> list[dict]:
    frames = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        obj = json.loads(line)
        if "host_ns" not in obj:
            raise ValueError(f"{path}:{lineno}: missing host_ns")
        frames.append(obj)
    frames.sort(key=lambda f: f["host_ns"])
    return frames


def render(r: dict) -> str:
    lines = [
        f"frames={r['frames']} non_frame_lines={r['non_frame_lines']} "
        f"span={r['span_s']}s rate={r['frame_rate_hz']}Hz",
        f"boot_epochs={r['boot_epochs']} changes={r['boot_changes']} "
        f"mcu_time_regressions={r['mcu_time_regressions']}",
        f"arrival median={r['arrival_interval_us']['median']}us "
        f"p95={r['arrival_interval_us']['p95']}us "
        f"max={r['arrival_interval_us']['max']}us "
        f"gaps={r['arrival_interval_us']['gaps']} "
        f"(limit {r['arrival_interval_us']['gap_limit']}us)",
        f"backpressure late={r['backpressure']['late_last']} "
        f"mwus_max={r['backpressure']['mwus_max_all_frames']}us",
        "",
        f"{'src':>3} {'frames':>7} {'new':>6} {'snap':>6} {'valid':>7} "
        f"{'seq_gap':>7} {'rateHz':>7} {'read_med':>8} {'err':>4} {'dup':>4}",
    ]
    for sid, s in r["sources"].items():
        lines.append(
            f"{sid:>3} {s['frames']:>7} {s['new_samples']:>6} "
            f"{s['snapshot_frames']:>6} {s['valid_ratio']:>7.3f} "
            f"{s['seq_gaps']:>7} "
            f"{(s['read_rate_hz'] or 0):>7.1f} "
            f"{(s['mcu_read_interval_us']['median'] or 0):>8.0f} "
            f"{s['errors_delta']:>4} {s['duplicate_delta']:>4}")
    if r["windows"]:
        lines += ["", f"windows ({len(r['windows'])}):"]
        for w in r["windows"]:
            lines.append(f"  +{w['start_s']:>6.1f}s frames={w['frames']:>4} "
                         f"new={w['new_samples']}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--window", type=float, default=10.0)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    result = analyze(load(Path(args.input)), args.window)
    print(render(result))
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2) + "\n")
        print(f"\njson: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
