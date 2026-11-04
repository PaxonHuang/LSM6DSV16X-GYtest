"""The IMU tool has to turn numbers into a verdict without the hardware.

Each rule here was derived from a measurement on the bench, so these tests
pin the mapping from a captured number to the wire a person should check.
"""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load():
    spec = importlib.util.spec_from_file_location("imu", ROOT / "tools" / "imu.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves type annotations through sys.modules
    sys.modules["imu"] = module
    spec.loader.exec_module(module)
    return module


i = load()


def capture(*units, summary="present=2 absent=9 count=11", done=True):
    lines = [
        "BOOT_EPOCH 7",
        "BUS profile=evta-dual units=11",
    ]
    binds = {0: ("B", 1), 1: ("A", 2), 2: ("A", 4), 3: ("A", 5),
             4: ("A", 6), 5: ("A", 7), 6: ("A", 8), 7: ("B", 9),
             8: ("B", 10), 9: ("B", 14), 10: ("B", 15)}
    for sid, (bus, cs) in binds.items():
        lines.append(f"BUS_BIND {sid} {bus} cs={cs}")
    lines.extend(units)
    lines.append("BUS_STATS A tx=100 err=0")
    lines.append("BUS_STATS B tx=100 err=0")
    lines.append(f"SUMMARY {summary}")
    if done:
        lines.append("MATRIX_DONE 11")
    return "\n".join(lines) + "\n"


def unit(sid, state, passed, total, who, detail="ok", es=0, eb=0, ep=0,
         parked=0, status=0x00, errors_line=True):
    lines = [
        f"I (1) lsm6dsv16x:   unit {sid}: CTRL1=0x06 CTRL2=0x06 CTRL3=0x44 "
        f"CTRL6=0x04 CTRL8=0x00 STATUS=0x{status:02X}",
        f"UNIT_RESULT {sid} {state} {passed}/{total} raw=0x{who:02X} {detail}",
    ]
    if errors_line:
        lines.insert(1, f"I (2) lsm6dsv16x:   unit {sid} errors total={es + eb + ep} "
                        f"es={es} eb={eb} ep={ep} parked={parked}")
    return "\n".join(lines)


def findings_for(text, expected):
    return {f.src.sid: f for f in i.diagnose(i.parse(text), set(expected))}


class ParseTests(unittest.TestCase):
    def test_reads_every_record(self):
        cap = i.parse(capture(unit(0, "PASS", 34, 34, 0x70)))
        self.assertEqual(cap.boot_epoch, 7)
        self.assertEqual(cap.count, 11)
        self.assertEqual(cap.sources[0].state, "PASS")
        self.assertEqual(cap.sources[0].bus, "B")
        self.assertEqual(cap.sources[0].cs, 1)
        self.assertTrue(cap.complete)

    def test_reads_error_classes(self):
        cap = i.parse(capture(unit(1, "FAIL", 25, 32, 0x70, es=0, eb=0, ep=1, parked=1)))
        self.assertEqual(cap.sources[1].errors, {"es": 0, "eb": 0, "ep": 1})

    def test_missing_matrix_done_is_not_complete(self):
        self.assertFalse(i.parse(capture(done=False)).complete)


class GateMapTests(unittest.TestCase):
    def test_packages_are_monotone(self):
        for sid in range(11):
            pkg, _, _, _ = i.gate_pins(sid)
            self.assertEqual(pkg, sid // 4 + 1, f"sid{sid}")

    def test_pins_match_the_wiring_document(self):
        expected = {0: (1, 1, 2, 3), 1: (1, 4, 5, 6), 2: (1, 10, 9, 8),
                    3: (1, 13, 12, 11), 4: (2, 1, 2, 3), 7: (2, 13, 12, 11),
                    10: (3, 10, 9, 8)}
        for sid, want in expected.items():
            self.assertEqual(i.gate_pins(sid), want, f"sid{sid}")


class DiagnoseTests(unittest.TestCase):
    def test_pass_produces_no_finding(self):
        cap = i.parse(capture(unit(0, "PASS", 34, 34, 0x70)))
        self.assertEqual(i.diagnose(cap, {0}), [])

    def test_steady_zero_points_at_the_gate_input(self):
        f = findings_for(capture(unit(2, "ABSENT", 0, 0, 0x00)), [2])[2]
        self.assertIn("输入端", f.diagnosis)
        self.assertIn("U1 p9", f.checks[0])
        self.assertIn("3.3 V", " ".join(f.checks))

    def test_all_ones_points_at_the_gate_enable(self):
        f = findings_for(capture(unit(6, "ABSENT", 0, 0, 0xFF)), [6])[6]
        self.assertIn("没有驱动总线", f.diagnosis)
        self.assertIn("/OE", f.checks[0])

    def test_unknown_byte_does_not_pretend_to_know(self):
        f = findings_for(capture(unit(2, "ABSENT", 0, 0, 0x5A)), [2])[2]
        self.assertIn("0x5A", f.diagnosis)

    def test_corrupt_burst_is_a_contact_problem(self):
        f = findings_for(
            capture(unit(1, "FAIL", 25, 32, 0x70, ep=1, parked=1)), [1])[1]
        self.assertIn("burst 数据损坏", f.diagnosis)
        self.assertIn("接触", f.diagnosis)

    def test_status_transfer_failure_is_reported_as_such(self):
        f = findings_for(
            capture(unit(1, "FAIL", 25, 32, 0x70, es=1, parked=1)), [1])[1]
        self.assertIn("STATUS", f.diagnosis)

    def test_block_transfer_failure_is_reported_as_such(self):
        f = findings_for(
            capture(unit(1, "FAIL", 25, 32, 0x70, eb=1, parked=1)), [1])[1]
        self.assertIn("burst 传输失败", f.diagnosis)

    def test_old_capture_without_error_classes_still_diagnoses(self):
        text = capture(unit(1, "FAIL", 25, 32, 0x70, errors_line=False))
        f = findings_for(text, [1])[1]
        self.assertIn("没有数据", f.diagnosis)

    def test_sources_outside_the_stage_are_not_diagnosed(self):
        text = capture(unit(0, "PASS", 34, 34, 0x70),
                       unit(5, "ABSENT", 0, 0, 0x00),
                       unit(6, "ABSENT", 0, 0, 0xFF))
        self.assertEqual(i.diagnose(i.parse(text), {0}), [])

    def test_missing_expected_source_is_reported(self):
        found = findings_for(capture(unit(0, "PASS", 34, 34, 0x70)), [0, 3])
        self.assertIn(3, found)
        self.assertIn("没有这一路", found[3].diagnosis)


class RenderTests(unittest.TestCase):
    def test_shows_only_the_stage_sources(self):
        text = capture(unit(0, "PASS", 34, 34, 0x70),
                       unit(3, "ABSENT", 0, 0, 0x00))
        out = i.render(i.parse(text), {0, 3})
        self.assertIn("  0  PASS", out)
        self.assertIn("  3  ABSENT", out)
        self.assertNotIn("  5  ", out)
        self.assertIn("判断与下一步", out)

    def test_complete_pass_says_so(self):
        text = capture(unit(0, "PASS", 34, 34, 0x70),
                       summary="present=1 absent=10 count=11")
        out = i.render(i.parse(text), {0})
        self.assertIn("全部通过", out)

    def test_incomplete_capture_is_flagged(self):
        out = i.render(i.parse(capture(unit(0, "PASS", 34, 34, 0x70), done=False)), {0})
        self.assertIn("MATRIX_DONE", out)


if __name__ == "__main__":
    unittest.main()
