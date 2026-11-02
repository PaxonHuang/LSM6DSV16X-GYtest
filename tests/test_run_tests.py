"""Offline fail-stop checks: no serial port or ESP-IDF required."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('runner', Path(__file__).parents[1]/'tools/run_tests.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def bus_factor(sid, profile='evta-dual'):
    return 'A' if (profile == 'legacy-single' or 1 <= sid <= 6) else 'B'


def bus_section(count, profile='evta-dual'):
    lines = [f'BUS profile={profile} units={count}']
    lines += [f'BUS_BIND {sid} {bus_factor(sid, profile)} cs={r.CS_MAP[sid]}'
              for sid in range(count)]
    lines += [f'BUS_STATS {b} tx=10 err=0'
              for b in sorted({bus_factor(s, profile) for s in range(count)})]
    return '\n'.join(lines) + '\n'


def good(count=2, profile='evta-dual'):
    units = ''.join(f'UNIT_RESULT {i} PASS 26/26 raw=0x70 ok\n'
                    for i in range(count))
    return (bus_section(count, profile) + units +
            f'SUMMARY present={count} absent=0 count={count}\n'
            f'MATRIX_DONE {count}\n')


GOOD = good()


class RunnerTests(unittest.TestCase):
    def run_log(self, log, extra=()):
        def capture(port,timeout,path):
            raw=log if isinstance(log,bytes) else log.encode('utf-8')
            Path(path).write_bytes(raw);return raw
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(r,'VERIFY_DIR',Path(tmp)), patch.object(r,'idf_env'), \
                 patch.object(r,'reset_board'), patch.object(r,'read_serial',side_effect=capture), \
                 patch.object(sys,'argv',['run_tests','--no-flash','--expect','2',*extra]):
                return r.main()

    def test_good_exact_population(self):
        self.assertEqual(self.run_log(GOOD),0)

    def test_duplicate_source_rejected(self):
        self.assertNotEqual(self.run_log(GOOD.replace('RESULT 1','RESULT 0')),0)

    def test_wrong_source_set_rejected(self):
        self.assertNotEqual(self.run_log(GOOD.replace('RESULT 0','RESULT 8').replace('RESULT 1','RESULT 9')),0)

    def test_inconsistent_summary_rejected(self):
        self.assertNotEqual(self.run_log(GOOD.replace('present=2','present=0')),0)

    def test_wrong_matrix_count_rejected(self):
        self.assertNotEqual(self.run_log(GOOD.replace('MATRIX_DONE 2','MATRIX_DONE 99')),0)

    def test_missing_summary_rejected(self):
        self.assertNotEqual(self.run_log(GOOD.replace('SUMMARY present=2 absent=0 count=2\n','')),0)

    def test_mixed_runs_rejected(self):
        self.assertNotEqual(self.run_log(GOOD+GOOD),0)

    def test_false_pass_checks_rejected(self):
        self.assertNotEqual(self.run_log(GOOD.replace('26/26','25/26',1)),0)

    def test_false_pass_identity_rejected(self):
        self.assertNotEqual(self.run_log(GOOD.replace('raw=0x70','raw=0x00',1)),0)

    def test_truncation_rejected(self):
        self.assertNotEqual(self.run_log(GOOD.replace('MATRIX_DONE 2\n','')),0)

    def test_no_results_still_preserves_raw(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw=Path(tmp)/'raw.log'
            self.assertNotEqual(self.run_log('boot failure\n',['--raw',str(raw)]),0)
            self.assertEqual(raw.read_text(),'boot failure\n')

    def test_noncontiguous_population_explicit(self):
        log = bus_section(3)
        log += 'UNIT_RESULT 0 PASS 26/26 raw=0x70 ok\n'
        log += 'UNIT_RESULT 1 ABSENT 0/0 raw=0x00 no_device\n'
        log += 'UNIT_RESULT 2 PASS 26/26 raw=0x70 ok\n'
        log += 'SUMMARY present=2 absent=1 count=3\nMATRIX_DONE 3\n'
        self.assertEqual(self.run_log(log,['--expect-sources','0,2']),0)

    def test_bytes_preserved_without_decode_loss(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw=Path(tmp)/'raw.bin'
            self.assertEqual(self.run_log(b'\xffboot\r\n'+GOOD.encode(),['--raw',str(raw)]),0)
            self.assertEqual(raw.read_bytes(),b'\xffboot\r\n'+GOOD.encode())

    def test_missing_absent_result_rejected(self):
        self.assertNotEqual(self.run_log(GOOD.replace('count=2','count=3').replace('MATRIX_DONE 2','MATRIX_DONE 3')),0)

    def test_malformed_done_suffix_rejected(self):
        self.assertNotEqual(self.run_log(GOOD.replace('MATRIX_DONE 2','MATRIX_DONE 2garbage')),0)

    def test_results_after_summary_rejected(self):
        log = ('BUS profile=evta-dual units=2\nBUS_BIND 0 B cs=1\nBUS_BIND 1 A cs=2\n'
               'BUS_STATS B tx=10 err=0\nBUS_STATS A tx=10 err=0\n'
               'SUMMARY present=2 absent=0 count=2\n'
               'UNIT_RESULT 0 PASS 26/26 raw=0x70 ok\n'
               'UNIT_RESULT 1 PASS 26/26 raw=0x70 ok\n'
               'MATRIX_DONE 2\n')
        self.assertNotEqual(self.run_log(log),0)

    def test_missing_bus_profile_rejected(self):
        self.assertNotEqual(self.run_log(GOOD.replace('BUS profile=evta-dual units=2\n','')),0)

    def test_unknown_bus_profile_rejected(self):
        self.assertNotEqual(self.run_log(GOOD.replace('profile=evta-dual','profile=mystery')),0)

    def test_wrong_bus_binding_rejected(self):
        self.assertNotEqual(self.run_log(GOOD.replace('BUS_BIND 1 A cs=2','BUS_BIND 1 B cs=2')),0)

    def test_wrong_cs_mapping_rejected(self):
        self.assertNotEqual(self.run_log(GOOD.replace('BUS_BIND 0 B cs=1','BUS_BIND 0 B cs=3')),0)

    def test_duplicate_cs_mapping_rejected(self):
        self.assertNotEqual(self.run_log(GOOD.replace('BUS_BIND 1 A cs=2','BUS_BIND 1 A cs=1')),0)

    def test_missing_bus_binding_rejected(self):
        self.assertNotEqual(self.run_log(GOOD.replace('BUS_BIND 1 A cs=2\n','')),0)

    def test_duplicate_bus_stats_rejected(self):
        self.assertNotEqual(self.run_log(GOOD+'BUS_STATS A tx=10 err=0\n'),0)

    def test_bus_error_over_transactions_rejected(self):
        self.assertNotEqual(self.run_log(GOOD.replace('BUS_STATS A tx=10 err=0','BUS_STATS A tx=2 err=3')),0)

    def test_legacy_profile_all_on_bus_a_accepted(self):
        self.assertEqual(self.run_log(good(2,'legacy-single')),0)

    def test_legacy_profile_with_bus_b_rejected(self):
        self.assertNotEqual(self.run_log(good(2,'legacy-single')+'BUS_STATS B tx=0 err=0\n'),0)

    def test_disconnect_preserves_partial_raw_bytes(self):
        from types import SimpleNamespace
        class Serial:
            def __init__(self,*a,**kw):self.n=0
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def setRTS(self,x):pass
            def setDTR(self,x):pass
            def read(self,size):
                data=b'\xffpartial\r\n'
                if self.n<len(data):
                    byte=data[self.n:self.n+1];self.n+=1;return byte
                raise OSError('disconnected')
        with tempfile.TemporaryDirectory() as tmp:
            raw=Path(tmp)/'raw.bin'
            with patch.dict(sys.modules,serial=SimpleNamespace(Serial=Serial)):
                with self.assertRaises(OSError):r.read_serial('/dev/test',1,raw)
            self.assertEqual(raw.read_bytes(),b'\xffpartial\r\n')

    def test_partial_line_disconnect_preserves_each_received_byte(self):
        import io
        from types import SimpleNamespace
        class Serial(io.RawIOBase):
            def __init__(self,*a,**kw):self.data=iter([b'a',b'b',b'c'])
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def setRTS(self,x):pass
            def setDTR(self,x):pass
            def read(self,size=1):
                try:return next(self.data)
                except StopIteration:raise OSError('disconnect mid-line')
        with tempfile.TemporaryDirectory() as tmp:
            raw=Path(tmp)/'raw.bin'
            with patch.dict(sys.modules,serial=SimpleNamespace(Serial=Serial)):
                with self.assertRaises(OSError):r.read_serial('/dev/test',1,raw)
            self.assertEqual(raw.read_bytes(),b'abc')

    def test_default_capture_always_allocates_new_raw_evidence(self):
        def capture(port,timeout,path):
            Path(path).write_bytes(GOOD.encode());return GOOD.encode()
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(r,'VERIFY_DIR',Path(tmp)),patch.object(r,'idf_env'), \
                 patch.object(r,'reset_board'),patch.object(r,'read_serial',side_effect=capture), \
                 patch.object(sys,'argv',['run_tests','--no-flash','--expect','2']):
                self.assertEqual(r.main(),0)
                files=list(Path(tmp).glob('capture-*.raw'))
                self.assertEqual(len(files),1)
                self.assertEqual(files[0].read_bytes(),GOOD.encode())

    def test_readback_failure_aborts_before_reset_or_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            image=Path(tmp)/'app.bin';image.write_bytes(b'abc')
            def process(cmd,**kw):
                return subprocess.CompletedProcess(cmd,1 if 'read-flash' in cmd else 0,stdout='',stderr='read failed')
            def forbidden(*a):raise AssertionError('reset/capture reached after failed readback')
            with patch.object(r,'VERIFY_DIR',Path(tmp)), patch.object(r,'APP_BIN',image), \
                 patch.object(r,'idf_env'), patch.object(r.subprocess,'run',side_effect=process), \
                 patch.object(r,'reset_board',side_effect=forbidden), patch.object(r,'read_serial',side_effect=forbidden), \
                 patch.object(sys,'argv',['run_tests','--expect','2']):
                with self.assertRaises(SystemExit):r.main()

    def test_previous_flash_readback_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            image=Path(tmp)/'app.bin';image.write_bytes(b'abc')
            old=Path(tmp)/'flash_verify.bin';old.write_bytes(b'failed-old-image')
            with patch.object(r,'VERIFY_DIR',Path(tmp)),patch.object(r,'APP_BIN',image), \
                 patch.object(r.subprocess,'run',return_value=subprocess.CompletedProcess([],1,stdout='',stderr='failure')):
                with self.assertRaises(SystemExit):r.verify_image('/dev/test')
            self.assertEqual(old.read_bytes(),b'failed-old-image')

    def test_short_readback_reports_first_missing_byte(self):
        with tempfile.TemporaryDirectory() as tmp:
            image=Path(tmp)/'app.bin';image.write_bytes(b'abcd')
            def readback(cmd,**kw):
                Path(cmd[-1]).write_bytes(b'ab')
                return subprocess.CompletedProcess([],0,stdout='',stderr='')
            with patch.object(r,'VERIFY_DIR',Path(tmp)),patch.object(r,'APP_BIN',image), \
                 patch.object(r.subprocess,'run',side_effect=readback):
                with self.assertRaisesRegex(SystemExit,'0x10002'):r.verify_image('/dev/test')

if __name__=='__main__':unittest.main()
