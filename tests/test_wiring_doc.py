"""The 2/6/11-source wiring document must agree with the frozen pin contract.

A wiring diagram that names the wrong GPIO is worse than no diagram, and the
stage-A table once showed a MISO collection row that the measured board does
not have. These checks pin the document to the contract in three independent
places (generator, pinmap JSON, runner CS map) and pin the committed HTML to
the generator that produced it.
"""
import importlib.util
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "evt-a-wiring-2-6-11.html"


def load_generator():
    spec = importlib.util.spec_from_file_location(
        "gen_evt_a_wiring_html", ROOT / "tools" / "gen_evt_a_wiring_html.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def runner_cs_map():
    text = (ROOT / "tools" / "run_tests.py").read_text()
    body = text.split("CS_MAP = (")[1].split(")")[0]
    return tuple(int(x) for x in body.split(","))


def prepare(g, st):
    st["_sids"] = st["sids"]
    st["_yt"] = g.y_targets(st)
    return st


class WiringDocTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = load_generator()
        cls.stages = [prepare(cls.g, st) for st in cls.g.STAGES]

    def test_every_stage_is_present(self):
        self.assertEqual([s["expect"] for s in self.stages],
                         ["0,1", "0,1,2,3,4,7", "0,1,2,3,4,5,6,7,8,9,10"])

    def test_cs_map_matches_runner_and_pinmap(self):
        import json
        pinmap = json.loads((ROOT / "docs" / "evt-a-pinmap.json").read_text())
        runner = runner_cs_map()
        for sid in range(11):
            self.assertEqual(self.g.CS[sid], runner[sid], f"sid{sid} CS vs runner")
            self.assertEqual(self.g.CS[sid], pinmap["sources"][sid]["cs"],
                             f"sid{sid} CS vs pinmap JSON")
            want_bus = "A" if 1 <= sid <= 6 else "B"
            self.assertEqual(self.g.BUS[sid], want_bus, f"sid{sid} bus")
            self.assertEqual(pinmap["sources"][sid]["bus"], want_bus)

    def test_bus_pins_match_pinmap(self):
        import json
        pinmap = json.loads((ROOT / "docs" / "evt-a-pinmap.json").read_text())
        for bus in ("A", "B"):
            for key in ("sclk", "mosi", "miso"):
                self.assertEqual(self.g.BUSPINS[bus][key], pinmap["buses"][bus][key],
                                 f"bus {bus} {key}")

    def test_gate_channels_matched_to_the_right_cs(self):
        for st in self.stages:
            owner = {}
            for sid in st["sids"]:
                pkg, ch = self.g.GATE[sid]
                self.assertNotIn((pkg, ch), owner,
                                 f"{st['key']}: sid{sid} reuses U{pkg} ch{ch}")
                owner[(pkg, ch)] = sid
                oe_net, oe_lines = self.g.cell(pkg, self.g.CHPIN[ch]["oe"], st)
                self.assertEqual(oe_net, f"SID{sid}_CS",
                                 f"{st['key']}: sid{sid} /OE net")
                self.assertIn(f"GPIO{self.g.CS[sid]}", " ".join(oe_lines),
                              f"{st['key']}: sid{sid} /OE names the wrong GPIO")
                a_net, _ = self.g.cell(pkg, self.g.CHPIN[ch]["a"], st)
                self.assertEqual(a_net, f"SID{sid}_MISO",
                                 f"{st['key']}: sid{sid} gate input")
                y_net, _ = self.g.cell(pkg, self.g.CHPIN[ch]["y"], st)
                self.assertEqual(y_net, f"{self.g.BUS[sid]}_MISO",
                                 f"{st['key']}: sid{sid} gate output on wrong bus")

    def test_unused_channels_are_tied_off(self):
        for st in self.stages:
            used = {(self.g.GATE[s][0], self.g.GATE[s][1]) for s in st["sids"]}
            for pkg in st["pkgs"]:
                for ch, pins in self.g.CHPIN.items():
                    if (pkg, ch) in used:
                        continue
                    oe, _ = self.g.cell(pkg, pins["oe"], st)
                    a, _ = self.g.cell(pkg, pins["a"], st)
                    y, _ = self.g.cell(pkg, pins["y"], st)
                    self.assertEqual((oe, a, y), ("3V3", "GND", "—"),
                                     f"{st['key']}: U{pkg} ch{ch} unused tie")

    def test_stage_a_is_the_direct_build_that_was_measured(self):
        """Stage A passed with no MISO collection row; the document must match."""
        st = next(s for s in self.stages if s["key"] == "s2")
        self.assertEqual(st["_yt"], {})
        for sid in st["sids"]:
            pkg, ch = self.g.GATE[sid]
            _, lines = self.g.cell(pkg, self.g.CHPIN[ch]["y"], st)
            joined = " ".join(lines)
            self.assertIn("直连", joined, f"sid{sid} output should be a direct wire")
            self.assertIn(f"GPIO{self.g.BUSPINS[self.g.BUS[sid]]['miso']}", joined)
        rows = self.g.breadboard_rows(st)
        self.assertNotIn(self.g.ROW_MISO, rows,
                         "stage A must not show a MISO collection row")

    def test_stage_6_is_a_prefix_of_stage_11(self):
        """Wires placed for 6 sources must not have to move for 11."""
        s6 = next(s for s in self.stages if s["key"] == "s6")
        s11 = next(s for s in self.stages if s["key"] == "s11")
        for sid in s6["sids"]:
            self.assertEqual(s6["_yt"][sid], s11["_yt"][sid],
                             f"sid{sid} collection row moves between stages")
        # and every 6-source gate keeps its package and channel
        self.assertTrue(set(s6["sids"]) < set(s11["sids"]))

    def test_collection_rows_never_mix_buses(self):
        for st in self.stages:
            for sid in st["sids"]:
                row, half = st["_yt"].get(sid, ("--", "--"))
                if row == "--":
                    continue
                want_half = "u" if self.g.BUS[sid] == "A" else "l"
                self.assertEqual(half, want_half,
                                 f"{st['key']}: sid{sid} shares a row with the other bus")

    def test_committed_html_is_the_generator_output(self):
        self.assertTrue(DOC.is_file(), "wiring document missing")
        self.assertEqual(DOC.read_text(encoding="utf-8"), self.g.page(),
                         "docs/evt-a-wiring-2-6-11.html is stale; rerun the generator")

    def test_html_carries_each_stage_command_and_cs(self):
        html = self.g.page()
        for st in self.stages:
            self.assertIn(f"--expect-sources {st['expect']}", html)
            for sid in st["sids"]:
                self.assertIn(f"GPIO{self.g.CS[sid]}", html)
        self.assertTrue(re.search(r"<html[\s>]", html))


if __name__ == "__main__":
    unittest.main()
