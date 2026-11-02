"""Offline replay checks for tools/analyze_stream.py."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    'stream', Path(__file__).parents[1] / 'tools/analyze_stream.py')
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


def frame(host_ns, t, b=1, sq=1, mt=0, va=1, e=0, d=0, sk=0, late=0, mwus=0):
    return {
        'host_ns': host_ns, 't': t, 'f': 0, 'b': b, 'late': late, 'mwus': mwus,
        'u': [{'i': 0, 'on': 1, 'id': 0x70, 'cs': 1, 'e': e, 'na': sq,
               'ng': sq, 'sq': sq, 'mt': mt, 'd': d, 'sk': sk,
               'va': va, 'vg': va}],
    }


class AnalyzeTest(unittest.TestCase):
    def test_clean_capture(self):
        frames = [frame(i * 20_000_000, i * 20, sq=i + 1, mt=i * 20_000)
                  for i in range(4)]
        r = s.analyze(frames)
        self.assertEqual(r['frames'], 4)
        self.assertAlmostEqual(r['span_s'], 0.06)
        src = r['sources']['0']
        self.assertEqual(src['new_samples'], 4)
        self.assertEqual(src['seq_gaps'], 0)
        self.assertAlmostEqual(src['valid_ratio'], 1.0)
        self.assertEqual(r['boot_changes'], 0)

    def test_seq_gap_counts_missing_reads(self):
        frames = [frame(i * 20_000_000, i * 20, sq=q, mt=i * 20_000)
                  for i, q in enumerate((1, 2, 5, 6))]
        r = s.analyze(frames)
        self.assertEqual(r['sources']['0']['seq_gaps'], 2)

    def test_reboot_detected(self):
        frames = [frame(0, 100, b=3), frame(20_000_000, 120, b=3),
                  frame(40_000_000, 5, b=4)]
        r = s.analyze(frames)
        self.assertEqual(r['boot_changes'], 1)
        self.assertEqual(r['mcu_time_regressions'], 1)

    def test_usb_gap_and_snapshot(self):
        frames = [frame(0, 0), frame(20_000_000, 20),
                  frame(1_020_000_000, 40, va=0, sq=2),
                  frame(1_040_000_000, 60)]
        r = s.analyze(frames)
        self.assertGreaterEqual(r['arrival_interval_us']['gaps'], 1)
        self.assertEqual(r['sources']['0']['snapshot_frames'], 1)

    def test_replay_is_deterministic(self):
        frames = [frame(i * 20_000_000, i * 20, sq=i + 1) for i in range(5)]
        with tempfile.NamedTemporaryFile('w', suffix='.jsonl', delete=False) as fh:
            for fr in frames:
                fh.write(json.dumps(fr) + '\n')
            path = Path(fh.name)
        try:
            a = s.analyze(s.load(path))
            b = s.analyze(s.load(path))
        finally:
            path.unlink()
        self.assertEqual(a, b)


if __name__ == '__main__':
    unittest.main()
