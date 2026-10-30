# EVT-A Dual-SPI Bring-up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an independently-locked two-bus SPI profile (SPI2 for sid 1–6, SPI3 for sid 0 and 7–10) to the LSM6DSV16X test firmware, preserve the legacy single-bus baseline, harden host-side acceptance, and prove it offline before any field capture.

**Architecture:** Each `spi_host_device_t` owns its own `spi_device_handle_t`, `routed_cs`, and counters. `unit_transfer` selects the bus by source id under that bus's own `spi_device_acquire_bus` lock, so a probe on bus B cannot reroute bus A. The frozen output grammar (`UNIT_RESULT`/`SUMMARY`/`MATRIX_DONE`) is unchanged; additive `BUS`, `BUS_BIND`, and `BUS_STATS` records carry the binding and error-count evidence.

**Tech Stack:** ESP-IDF v6.0.2, ESP32-S3, ST `lsm6dsv16x-pid` v6.2.0 (vendored), Python 3 `unittest`, host `cc`.

**Spec:** `EgoGlove_IMU_Core_2_6_11_Engineering_Package/EgoGlove_IMU_Core_README.txt` and the embedded EVT-A A02/A03 contract summary in `EgoGlove_IMU_Core_breadboard_2_6_11.html` §05/§08 (remote `EgoGlove@research/demo2b-design-probe-20261015` was unreachable from this host; the package quotes it and pins `GYtest@ec600d9a`).

## Global Constraints

- CS map is frozen: sid0..10 → GPIO `1,2,4,5,6,7,8,9,10,14,15`.
- Never drive GPIO19/20. Bus B pins are GPIO18/21/47; bus A stays GPIO12/11/13.
- 1 MHz bring-up. Never lower the clock to hide a wiring fault.
- No series resistor may substitute for MISO isolation; MISO gating is the 74HC125 path.
- Do not reword `UNIT_RESULT`, `SUMMARY`, `MATRIX_DONE`.
- Distinguish MCU readout rate from sensor-native sampling in every claim.
- Default profile is EVT-A dual; legacy single-bus must stay buildable and recoverable.

## Review Focus

- A source bound to the wrong bus must fail acceptance, not silently pass.
- A missing/duplicate/malformed `BUS_BIND` or `BUS_STATS` record must fail acceptance.
- A bus with failed transfers must expose `err > 0`; a present source on a zero-traffic bus must fail.
- Legacy profile must initialize exactly one bus and never touch SPI3 pins.
- Reset must return WHO_AM_I=0x70 and control-register defaults before reconfiguration.
- Dropped MCU readout frames must be counted even when the mean rate looks acceptable.

---

### Task 1: Dual-bus transport in `main/main.c`

**Files:**
- Modify: `main/main.c`
- Modify: `main/Kconfig.projbuild`
- Test: `tests/test_bus_routing.py`

**Interfaces:**
- Produces: `typedef struct imu_bus_t` with `host`, pins, `dev`, `routed_cs`, `transactions`, `errors`, `initialized`; `static int bus_index_for_unit(int index)`; `static void cs_select(imu_bus_t *b, int cs)`.
- Produces: additive serial records `BUS profile=<evta-dual|legacy-single> units=<n>`, `BUS_BIND <sid> <A|B> cs=<gpio>`, `BUS_STATS <A|B> tx=<n> err=<n>`.

**Steps:**
- [ ] Add `CONFIG_BUS_PROFILE_*` choice (default EVT-A dual) and `IMU_B_SCLK/MOSI/MISO_GPIO` ints (18/21/47) to `Kconfig.projbuild`.
- [ ] Replace the global `s_bus_dev`/`s_routed_cs` with `s_buses[2]`; route CS through `spi_periph_signal[b->host].spics_out[0]`.
- [ ] `bus_init` validates CS/pin disjointness, initializes only used hosts, adds one anchor device per used bus.
- [ ] Add `bus_index_for_unit` (A: 1–6, B: 0 and 7–10; legacy: all A) and call it from `unit_bind`.
- [ ] Emit `BUS`, `BUS_BIND`, `BUS_STATS`; keep frozen lines byte-identical.
- [ ] Test: `tests/test_bus_routing.py` compiles `bus_index_for_unit` for both profiles and asserts dual mapping `{0:B,1:A,2:A,3:A,4:A,5:A,6:A,7:B,8:B,9:B,10:B}`, legacy all A, and that no shared `s_bus_dev`/`s_routed_cs` remains.

### Task 2: Per-source reset and MCU-readout gap checks

**Files:**
- Modify: `main/main.c`
- Test: `tests/test_sampling.py`

**Interfaces:**
- Produces: `static void test_reset(imu_unit_t *u, test_ctx_t *t)`.
- Extends `test_static_window` to count MCU-readout gaps and report `MCU_READOUT`.

**Steps:**
- [ ] `test_reset`: `sw_por`, wait 20 ms, verify WHO_AM_I=0x70, CTRL1=0x00, CTRL3 bit2 (IF_INC) set.
- [ ] Count `gaps` where inter-sample time > 1.5 × 1/120 s; check `gaps <= expected/10`; log `MCU_READOUT` with `gaps`/`max_gap_us`.
- [ ] Keep sticky first-error stop unchanged.

### Task 3: Host acceptance for bus evidence

**Files:**
- Modify: `tools/run_tests.py`
- Modify: `tests/test_run_tests.py`

**Interfaces:**
- Produces: `BUS_RE`, `BIND_RE`, `STATS_RE`; `validate_bus(log, units, summary) -> list[str]` folded into `validate_log`.

**Steps:**
- [ ] Require exactly one `BUS` record with a known profile.
- [ ] Require `BUS_BIND` for every configured sid, unique, and contract-correct for the profile.
- [ ] Require `BUS_STATS` exactly for the buses named by the binds; `err <= tx`; reject legacy with bus B.
- [ ] Reject a present source whose bus reports `tx == 0`.
- [ ] Update fixtures to include the `BUS_*` section; add wrong-bus, missing-bind, duplicate-stats, error>tx, and legacy-accept tests.

### Task 4: Offline verification, build, evidence, handoff

**Files:**
- Create: `evidence/2026-10-30-offline/tests.log`, `build.log`, `verification.json`
- Modify: `docs/HANDOFF.md`
- Create: `docs/dual-spi-evt-a.md` (config + field staged commands + acceptance limits)

**Steps:**
- [ ] `python3 -m unittest discover -s tests -v` → all pass, save log.
- [ ] `. ~/.espressif/v6.0.2/esp-idf/export.sh && tools/build.sh` in the worktree → image built, save log.
- [ ] Record SHA256 of the built image and the exact source commit in `verification.json`.
- [ ] Update `HANDOFF.md`: hardware now on `/dev/ttyACM1` (Espressif USB-JTAG), dual-bus config, offline PASS, field 2→6→11 commands, stop conditions.
- [ ] Commit on `feat/dual-spi-evt-a`; do not push.
