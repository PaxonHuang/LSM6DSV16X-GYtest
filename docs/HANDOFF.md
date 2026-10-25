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
- Single module on the GPIO2 position passed `26/26` at 1 MHz with the
  12-byte output-block read, retry and plausibility gate.
- Both modules answer `WHO_AM_I=0x70` at modes 0/3 and 100/400/1000 kHz
  through a **direct one-device-per-CS** path.
- Config readback is correct on both: `CTRL1=0x06 CTRL2=0x06 CTRL3=0x44
  CTRL6=0x04 CTRL8=0x00`.
- CS isolation is real: forcing the non-selected CS low corrupts the read
  (expected contention); forcing it high restores valid data.
- Firmware is **exonerated** for the current failures: direct path and the
  production CS0-reroute path show the same behaviour; BDU off, mode 0/3 and
  10 kHz/100 kHz/1 MHz all fail the same way.

### Current blocker
On the breadboard, multi-byte reads of the **output block (0x22..0x2D)** are
unreliable even with one module connected. STATUS shows data-ready, but the
burst returns `80 00 00 …` (truncated after the first byte) or all zeros.
Single-byte reads of the same registers return data. Measured wire resistances
are 2–5 Ω per line and **10 Ω on the GPIO2 module's GND**, which is enough to
make the shared bus marginal. The breadboard/jumper setup has been disturbed
many times and is no longer a trustworthy baseline.

## Next action (plan A)

Build a **2-module soldered perfboard prototype** using
[`docs/perfboard-11-imu.md`](perfboard-11-imu.md) and the precise wiring
diagram [`docs/perfboard-11-imu-wiring.html`](perfboard-11-imu-wiring.html)
(open in a browser or print it: front component side + mirrored back-side CS
fan-out, 180×115 mm layout on a 200×150 mm board). Verify `--expect 2`, then
extend the same layout to 6, then 11. Do not go back to the breadboard for
multi-source work.

## Commands

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
