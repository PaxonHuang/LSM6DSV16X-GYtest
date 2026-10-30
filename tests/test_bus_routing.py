"""Offline dual-SPI contract checks: no ESP32 or serial port required."""
from pathlib import Path
import subprocess
import tempfile
import unittest

SRC = Path(__file__).parents[1] / 'main/main.c'


def function(source, name, kind="bool"):
    start = source.index('static ' + kind + ' ' + name + '(')
    brace = source.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


class BusRoutingTests(unittest.TestCase):
    def run_mapping(self, want, cflags=()):
        prefix = ('#include <stdbool.h>\n'
                  '#define IMU_BUS_A 0\n'
                  '#define IMU_BUS_B 1\n')
        body = function(SRC.read_text(), 'bus_index_for_unit', 'int')
        main = ('int main(void){int want[11]={' + ','.join(map(str, want)) + '};'
                'for(int i=0;i<11;i++)if(bus_index_for_unit(i)!=want[i])return 1;'
                'return 0;}')
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / 't.c').write_text(prefix + body + main)
            subprocess.run(['cc', '-std=c11', *cflags, str(p / 't.c'), '-o', str(p / 't')],
                           check=True, capture_output=True)
            result = subprocess.run([str(p / 't')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_evta_dual_mapping(self):
        # sid 1..6 -> bus A (SPI2); sid 0 and 7..10 -> bus B (SPI3).
        self.run_mapping([1, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1])

    def test_legacy_single_mapping(self):
        self.run_mapping([0] * 11, ('-DCONFIG_BUS_PROFILE_LEGACY_SINGLE',))

    def test_no_shared_global_bus_state(self):
        src = SRC.read_text()
        self.assertNotIn('s_bus_dev', src)
        self.assertNotIn('s_routed_cs', src)

    def test_two_hosts_and_three_pin_sets_present(self):
        src = SRC.read_text()
        self.assertIn('SPI3_HOST', src)
        self.assertIn('IMU_PIN_A_SCLK', src)
        self.assertIn('IMU_PIN_B_SCLK', src)
        self.assertIn('spi_periph_signal[bus->host].spics_out[0]', src)


if __name__ == '__main__':
    unittest.main()
