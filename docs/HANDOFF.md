# 2026-10-30 — EVT-A dual-SPI offline build; field stages still unrun

- Repo `/home/paxon/ESP32Projects/LSM6DSV16X-GYtest`, worktree branch
  `feat/dual-spi-evt-a` from `8d4ec2b` (strict-runner HEAD). All changes are
  local; nothing pushed.
- **Hardware state changed since 2026-10-27:** the host now exposes
  `usb-Espressif_USB_JTAG_serial_debug_unit_98:88:E0:11:9F:08-if00` →
  `/dev/ttyACM1` (Espressif `303a:1001`), in addition to the Hikvision camera
  on `/dev/ttyACM0`. Use only the Espressif by-id for IMU work. Physical
  2/6/11 population, marking, continuity and 3V3 are still unverified here.
- Offline only: 36 unit tests OK; EVT-A dual image `c03efac4…` (216336 B) and
  legacy image `bbe42ff6…` (216320 B) built. No flash, readback, serial capture
  or hardware PASS was performed.
- Implemented EVT-A A02/A03 dual bus: SPI2 GPIO12/11/13 → sid1–6, SPI3
  GPIO18/21/47 → sid0,7–10. Each host owns its device handle, lock, CS-routing
  state and tx/err counters; no shared `s_bus_dev`/`s_routed_cs`. CS map is
  unchanged (`1,2,4,5,6,7,8,9,10,14,15`). Legacy single-bus stays buildable via
  `sdkconfig.legacy`.
- Firmware adds reset verification (WHO_AM_I 0x70, CTRL1 0x00, CTRL3 IF_INC),
  MCU-readout gap counting (limit `expected/10`) and additive `BUS`/`BUS_BIND`/
  `BUS_STATS` records. Frozen `UNIT_RESULT`/`SUMMARY`/`MATRIX_DONE` unchanged.
- `tools/run_tests.py` now validates the bus plan (profile, per-source binding,
  stats coverage, `err≤tx`, present-source traffic) on top of the strict
  readback/source-set/SUMMARY/MATRIX_DONE checks already on this branch.
- Evidence: `evidence/2026-10-30-offline/` (`tests.log`, `build.log`,
  `build-legacy.log`, `verification.json`). Older evidence untouched.
- Config + field plan: `docs/dual-spi-evt-a.md`.

**Next command (field, 2 sources only after physical confirmation):**

```bash
. ~/.espressif/v6.0.2/esp-idf/export.sh
PORT=/dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_98:88:E0:11:9F:08-if00
tools/mode.sh test && tools/build.sh
python3 tools/run_tests.py --port "$PORT" --expect 2
```

Stop on any failure; expand only 2 → 6 → 11 in separate passing stages. Do not
treat this offline build, or an old `--expect N` health PASS, as full-system
continuous-read / FIFO-native / sync acceptance.

---

# 2026-10-27 — strict runner committed; physical two-source stage unverified

- Repo `/home/paxon/ESP32Projects/LSM6DSV16X-GYtest`; branch `fix/strict-runner-20261026`.
  Runner/firmware/evidence commit `9fe42d3` is local and unpushed; `main` remains at baseline `ec600d9`.
- Latest host inventory: `/dev/serial/by-id` exposes only `usb-SN0002_2K_USB_Camera_...-if04`,
  which resolves to `/dev/ttyACM0` and identifies as the Hikvision camera CDC interface.
  There is no ESP32 test-board serial identity in this host; do not use this `/dev/ttyACM0` for IMU tests.
- The last direct user status said the 2-route soldering was unfinished, expected by 2026-10-27.
  No later physical confirmation, marking, continuity, or rail measurement is available. No 2/6/11 hardware
  test, flash, or hardware PASS was performed.
- Preserved all 61 files / 700505 bytes under `evidence/2026-10-26-preserved/`, SHA256 checked against
  temporary originals and saved copies. Offline runner/C tests: 24 passed. ESP-IDF v6.0.2 isolated TEST build passed;
  no device write occurred. `sdkconfig` DIAG state was preserved.
- Runner requires an explicit expected population, stops before reset/capture on readback errors,
  preserves raw serial bytes including disconnect mid-line, and rejects matrix inconsistencies.
  Firmware stops at first read error without retrying bad blocks; thresholds unchanged.

**Latest host device check (2026-10-27):** the only serial by-id is `usb-SN0002_2K_USB_Camera_...-if04`,
which maps to `/dev/ttyACM0` and is the Hikvision camera CDC interface. No test-board ESP32 path is present.
Do not run the commands below against `/dev/ttyACM0`.

**Next field step:** after the two-source board is physically complete, verify marking, continuity and 3V3,
then identify its own serial by-id and make one bounded `--expect 2` run with a new raw path. Stop on failure;
expand only through separate passing 6- and 11-source stages.

---

# Handoff — LSM6DSV16X multi-source bring-up (2026-10-24)

## Where things stand

- Repo: `/home/paxon/ESP32Projects/LSM6DSV16X-GYtest`;
  GitHub: <https://github.com/PaxonHuang/LSM6DSV16X-GYtest> (public, `main`).
  The vendored driver's original nested `.git` is kept outside the repo at
  `/home/paxon/ESP32Projects/.vendor-git-backup/lsm6dsv16x.git`.
- Board: ESP32-S3-DevKitC-1 N16R8 on `/dev/ttyACM0`, ESP-IDF v6.0.2.
- Bus: SPI2, mode 3, 1 MHz, SCLK=GPIO12, MOSI=GPIO11, MISO=GPIO13.
- CS table (11 sources): `1,2,4,5,6,7,8,9,10,14,15`.

### Proven working
- Single module on the GPIO2 position historically reported `26/26` at 1 MHz with the
  12-byte output-block read, retry and plausibility gate. This is not acceptance
  under the new first-error-stop policy.
- Both modules answer `WHO_AM_I=0x70` at modes 0/3 and 100/400/1000 kHz
  through a **direct one-device-per-CS** path.
- Config readback is correct on both: `CTRL1=0x06 CTRL2=0x06 CTRL3=0x44
  CTRL6=0x04 CTRL8=0x00`.
- CS isolation is real: forcing the non-selected CS low corrupts the read
  (expected contention); forcing it high restores valid data.
- Historical direct-path and CS0-reroute trials showed similar failures
  across several settings. This narrows the observed assembly boundary, but
  does **not** exclude all firmware/driver/timing causes; the old runner and
  retry-based sample gate could produce false confidence.

### Current blocker
On the breadboard, multi-byte reads of the **output block (0x22..0x2D)** are
unreliable even with one module connected. STATUS shows data-ready, but the
burst returns `80 00 00 …` (truncated after the first byte) or all zeros.
Historical single-byte reads returned data. The prior operator report records
2–5 Ω per wire and 10 Ω on the GPIO2 module ground; the measurement setup,
probe/contact resistance and waveforms are not independently established here.
These are leads for assembly inspection, not a determined electrical root cause. The breadboard/jumper setup has been disturbed
many times and is no longer a trustworthy baseline.

## Next action (plan A)

Build a **2-module soldered perfboard prototype** using
[`docs/perfboard-11-imu.md`](perfboard-11-imu.md) and the precise wiring
diagram [`docs/perfboard-11-imu-wiring.html`](perfboard-11-imu-wiring.html)
(open in a browser or print it: front component side + mirrored back-side CS
fan-out, 180×115 mm layout on a 200×150 mm board). Verify `--expect 2`, then
extend the same layout to 6, then 11. Do not go back to the breadboard for
multi-source work.

## Historical command templates — verify a dedicated test-board by-id before use

```bash
. ~/.espressif/v6.0.2/esp-idf/export.sh

tools/mode.sh test                 # health-test firmware
tools/build.sh                     # force a real recompile
python3 tools/run_tests.py --port /dev/ttyACM0 --expect 2

tools/mode.sh stream               # NDJSON stream for the panel
python3 tools/web_panel.py --port /dev/ttyACM0 --cli   # terminal dashboard
python3 tools/web_panel.py --port /dev/ttyACM0         # browser panel
```

Diagnostic builds (do not ship):

```bash
# pin/parameter sweep, direct per-CS devices, CS-short check
SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.pinsweep" idf.py reconfigure
# 1 MHz + per-sample dump
SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.diag" idf.py reconfigure
# burst length / BDU experiments
SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.burst" idf.py reconfigure
```

## Gotchas that already cost time

1. **Stale objects.** `idf.py build` has silently reused `main.c.obj`. Always
   use `tools/build.sh`, do not hide build output, and check the ELF mtime or
   `strings build/lsm6dsv16x_test.elf | grep "<new log text>"`.
2. **Kconfig bools are undefined when off.** Use `#ifdef CONFIG_X`, not
   `#if CONFIG_X`.
3. **Dynamic CS0 routing.** Release the previous pin with
   `esp_rom_gpio_connect_out_signal(pin, SIG_GPIO_OUT_IDX, …)` and keep CS0
   routed between transactions; re-routing every transaction adds a start
   glitch.
4. **Never drive GPIO19/20** (USB). The CS table avoids them.
5. **`CONFIG_FREERTOS_HZ=1000`** is required (`pdMS_TO_TICKS(8)` is 0 at 100).
6. **Flash readback** after every flash (`tools/run_tests.py` does it); esptool
   can report success with a truncated image.
7. **Serial reset.** Use esptool's reset sequence; holding RTS high parks the
   part in the ROM downloader.
8. **Do not lower the SPI clock to hide a wiring fault.** 10 kHz failed the
   same way as 1 MHz; fix the wiring.

## Key source locations

- `main/main.c` — transport, dynamic CS routing, health tests, stream, DIAG mode.
- `main/Kconfig.projbuild` — unit count, CS table, SPI kHz, BURST_LEN, BDU.
- `tools/run_tests.py` — flash → readback verify → reset → capture → per-source verdict.
- `tools/gen_perfboard_wiring.py` — regenerates the 11-source wiring HTML
  (2.54 mm grid, front + mirrored back-side SVG) after any layout edit.
- `tools/web_panel.py` — web + `--cli` dashboard, hot-plug events.
- `tools/capture.py` — raw serial capture with reset.
- `DEVELOPMENT_REPORT.md` — earlier single-source report (partly superseded by
  this handoff for multi-source behaviour).

## Evidence to preserve

Raw captures from this session are under
`/home/paxon/.claude/jobs/4db876a0/tmp/evidence/` (temporary). Copy the ones
needed into the repo before the job directory is cleaned up.
