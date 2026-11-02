# EVT-A dual-SPI experiment configuration (2026-10-30)

Offline-ready configuration for the `EgoGlove EVT-A A02/A03` two-bus contract,
against `LSM6DSV16X-GYtest` base `8d4ec2b`. **No field run has been made.**

## Contract (frozen)

- CS map unchanged: sid0..10 → GPIO `1,2,4,5,6,7,8,9,10,14,15`.
- Bus A = SPI2, pins GPIO12 (SCLK) / GPIO11 (MOSI) / GPIO13 (MISO), owns sid **1..6**.
- Bus B = SPI3, pins GPIO18 (SCLK) / GPIO21 (MOSI) / GPIO47 (MISO), owns sid **0 and 7..10**.
- One CS low per bus; different buses have independent devices, locks and CS-routing state.
- MISO isolation is the 74HC125 path. A series resistor is **not** isolation.
- 1 MHz bring-up. Do not lower the clock to hide a wiring fault.
- The `UNIT_RESULT` / `SUMMARY` / `MATRIX_DONE` grammar is unchanged. Evidence is
  additive: `BUS`, `BUS_BIND`, `BUS_STATS`.

| sid | bus | CS GPIO | role |
|----|-----|---------|------|
| 0 | B | 1 | in stage 1–2 already on bus B |
| 1 | A | 2 | |
| 2 | A | 4 | |
| 3 | A | 5 | |
| 4 | A | 6 | |
| 5 | A | 7 | |
| 6 | A | 8 | |
| 7 | B | 9 | |
| 8 | B | 10 | |
| 9 | B | 14 | |
| 10 | B | 15 | |

## Profiles

Default (EVT-A dual):

```bash
tools/mode.sh test
tools/build.sh
# image prints: BUS profile=evta-dual units=11
```

Recoverable legacy single-bus baseline (all sources on SPI2):

```bash
SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.legacy" idf.py reconfigure
tools/build.sh
# image prints: BUS profile=legacy-single units=11
```

Do not flash a legacy image against EVT-A dual wiring and call it a dual-bus
result; bus B would be uninitialized and sid0/7..10 would not be reachable.

## What the firmware now checks per source

1. `WHO_AM_I = 0x70`.
2. Software power-on reset: identity still `0x70`, `CTRL1=0x00`, `CTRL3` IF_INC set.
3. CTRL9 register read/write/readback.
4. Configuration readback: `CTRL1=0x06`, `CTRL2=0x06`, `CTRL6 FS_G=4`.
5. Continuous 12-byte output block `0x22..0x2D`; first bad block parks the unit
   (sticky first-error stop, no retry into PASS).
6. 1 s static window: accelerometer/gyro MCU-readout counts, mean |a| ≈ 1 g,
   gyro bias/noise, and **MCU readout gaps** (inter-sample > 1.5 × 1/120 s,
   limit `expected/10`).
7. `BUS_STATS` exposes per-bus `tx`/`err` counters.

`MCU_READOUT ... (sensor native ODR not measured here)` is deliberate: these
counts are what the MCU actually read, not proof of the sensor's internal
sampling cadence. Native timing needs FIFO/timestamp analysis.

## Host acceptance

`tools/run_tests.py` now rejects, before any PASS:

- missing / duplicate / malformed `BUS`, `BUS_BIND`, `BUS_STATS`;
- unknown profile, or a source bound to the wrong bus for that profile;
- `BUS_BIND` not covering exactly the configured source set;
- `BUS_STATS` not covering exactly the buses named by the binds;
- `err > tx`, or a present source whose bus saw zero traffic;
- legacy profile with any source on bus B;
- the pre-existing strict checks (readback abort, exact expected present set,
  one SUMMARY + one MATRIX_DONE, consistent counts, no result after SUMMARY).

## Offline verification (2026-10-30)

- `python3 -m unittest discover -s tests -v` → `Ran 36 tests ... OK`.
- EVT-A build: 216336 bytes, sha256 `c03efac4…26d0`, contains `evta-dual`.
- Legacy build: 216320 bytes, sha256 `bbe42ff6…c93e`, contains `legacy-single`.
- STREAM build compiles with `f`/`late`/`mwus` frame fields (217952 B).
- DIAG build compiles; DIAG stays bus-A only by design (210752 B).
- Evidence: `evidence/2026-10-30-offline/{tests.log,build.log,build-legacy.log,build-stream.log,build-diag.log,verification.json}`.

## Field stages

Stage 2 was attempted on 2026-10-30: flash readback verified, both buses
transacted with `err=0`, but **0/11 sources answered** (bus A `0xFF`, bus B
`0x00`). That run used the old wiring; the 2-source breadboard guide had not
been applied.

**2026-11-02 stage 2 PASS** with the `breadboard-2-source-evt-a` wiring:
sid0 (B) and sid1 (A) both `34/34`, `WHO_AM_I=0x70`, `BUS_STATS` `err=0`, and a
60 s stream at 50 Hz with zero errors/gaps. Evidence in
`evidence/2026-11-02-field/`.

Stream evidence path:

```bash
tools/mode.sh stream && tools/build.sh
python3 tools/stream_capture.py --port "$PORT" --duration 60 \
    --out evidence/<date>/stream.jsonl --raw evidence/<date>/stream.raw
python3 tools/analyze_stream.py --input evidence/<date>/stream.jsonl \
    --window 10 --out evidence/<date>/stream-analysis.json
```

`analyze_stream.py` is deterministic: it reads only the capture file. Time
semantics stay separate — sensor sample time is `unknown`, MCU read time is
`u.mt`, MCU transmit time is `t`, host receive time is `host_ns`.

Stream mode uses the native USB-Serial/JTAG console (`sdkconfig.stream`).
The default UART0 mirror limits stdout to about 18 KB/s, which backpressures a
50 Hz NDJSON feed to ~17 Hz regardless of SPI rate.

Identify the test board by-id first; `/dev/ttyACM0` is the Espressif unit on
2026-11-02, but that assignment changed from 2026-10-30, so never hard-code it.

```bash
. ~/.espressif/v6.0.2/esp-idf/export.sh
PORT=/dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_98:88:E0:11:9F:08-if00

tools/mode.sh test
tools/build.sh
python3 tools/run_tests.py --port "$PORT" --expect 2    # sid 0 (B) + sid 1 (A)
# stop on any failure; only after a clean 2-source run:
python3 tools/run_tests.py --port "$PORT" --expect 6    # sid 0..5
# only after a clean 6-source run:
python3 tools/run_tests.py --port "$PORT" --expect 11   # sid 0..10
```

Per-source semantics in stream frames: `sq` is the accelerometer sample
sequence, `mt` the MCU read time (µs), `d` repeated payloads while DRDY was
set, `sk` frames with no fresh sample (output snapshot), `es`/`eb`/`ep`
STATUS-transfer / block-transfer / plausibility error counts. A parked source is
re-initialised at most once per second and announces `RECOVER <sid>`; TEST mode
keeps the first-error stop.

Save each raw capture under a new dated `evidence/` directory. `run_tests.py`
already allocates a new `capture-*.raw` and aborts on flash readback mismatch.

Stop conditions: any all-zero/truncated block, a CS contention signature, a
hot spot/odour, a reset loop, `BUS_STATS err>0`, or a source present on a bus
with zero traffic. Do not "fix" any of these by lowering the clock or removing
MISO isolation.

USB backpressure is measured separately in stream mode: each NDJSON frame now
carries `f` (frame index), `late` (writes slower than the publish period) and
`mwus` (max write duration, µs).

## Limits

- This is a bench wiring candidate, not a manufacturing release.
- 74HC125N DIP buffering here is not the final 6×SN74LV125A board with
  per-finger SCLK/MOSI gating, CS safety logic, protected power or reverse
  leakage conditions.
- A health PASS is not a full-system continuous-read, FIFO-native-timing or
  synchronization PASS.
