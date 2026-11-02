# EVT-A 双 SPI 6 源面包板接线（sid 0,1,2,3,4,7）

在 2 源（sid0/B + sid1/A）已验证通过的基础上扩展。**断电操作**，不要带电插拔。

## 0. BOM 差额

6 源需要 **6 个独立 MISO 门**，现有 1 片 SN74HC125N 只有 4 通道，因此：

- **再加 1 片 SN74HC125N**（U2）。11 源阶段需要第 3 片。
- 4 个新模块各 1 个 10 kΩ CS 上拉、1 个 100 nF（模块自带可省）。
- 不允许把两颗模块的 MISO 接到同一个门输入。

## 1. 现有 U1 的通道 3、4 从“禁用”改为“启用”

| U1 引脚 | 现在 | 改为 | 用途 |
|---:|---|---|---|
| 10 /3OE | 3V3 | **CS2 (GPIO4)** | sid2 门控 |
| 9 3A | GND | **sid2 MISO/SDO** | sid2 输入 |
| 8 3Y | 悬空 | **A_MISO 网络 (GPIO13)** | sid2 输出 |
| 13 /4OE | 3V3 | **CS3 (GPIO5)** | sid3 门控 |
| 12 4A | GND | **sid3 MISO/SDO** | sid3 输入 |
| 11 4Y | 悬空 | **A_MISO 网络 (GPIO13)** | sid3 输出 |

U1 通道 1/2（sid0/sid1）保持不动。多个 3Y/4Y 并到同一 A_MISO 是允许的：
同一时刻只有一个 /OE 为低。

## 2. 新增 U2（SN74HC125N，缺口朝上）

| 引脚 | 连接 | 用途 |
|---:|---|---|
| 1 /1OE | **CS4 (GPIO6)** | sid4 门控 |
| 2 1A | **sid4 MISO/SDO** | sid4 输入 |
| 3 1Y | **A_MISO (GPIO13)** | sid4 输出 |
| 4 /2OE | **CS7 (GPIO9)** | sid7 门控 |
| 5 2A | **sid7 MISO/SDO** | sid7 输入 |
| 6 2Y | **B_MISO (GPIO47)** | sid7 输出 |
| 7 GND | GND 轨 | |
| 8 3Y | 悬空 | 未用 |
| 9 3A | GND 轨 | 未用拉低 |
| 10 /3OE | 3V3 轨 | 未用禁用 |
| 11 4Y | 悬空 | 未用 |
| 12 4A | GND 轨 | 未用拉低 |
| 13 /4OE | 3V3 轨 | 未用禁用 |
| 14 VCC | 3V3 轨，100 nF 到 GND | |

## 3. 四颗新模块

| sid | 总线 | CS GPIO | SCLK | MOSI | MISO 接到 |
|---:|---|---:|---:|---:|---|
| 2 | A | 4 | GPIO12 | GPIO11 | U1 pin9 (3A) |
| 3 | A | 5 | GPIO12 | GPIO11 | U1 pin12 (4A) |
| 4 | A | 6 | GPIO12 | GPIO11 | U2 pin2 (1A) |
| 7 | B | 9 | GPIO18 | GPIO21 | U2 pin5 (2A) |

每颗模块：VCC→3V3、GND→GND、CS→上表 GPIO 且 10 kΩ 上拉到 3V3、
SCL/SPC→SCLK、MOSI/SDA/SDI→MOSI、MISO/SDO→对应门输入。

## 4. 断电测量检查单（上电前逐项打勾）

1. USB 已拔掉。
2. 3V3 轨与 GND 轨之间不短路（万用表二极管/电阻档）。
3. 6 颗模块的 VCC 都在 3V3 轨，GND 都在 GND 轨；没有 5V。
4. 每个 CS 到对应 GPIO 通，且各有一个 10 kΩ 到 3V3。
5. 每个模块 MISO 只进一个门输入；没有两颗 MISO 共用一个 3A/4A/1A/2A。
6. U1、U2 的 pin7=GND、pin14=3V3，各有一个 100 nF。
7. 未用门：/OE→3V3、A→GND、Y 悬空；没有悬空输入。
8. 3Y/4Y 等门输出只汇到对应总线 MISO（A=GPIO13，B=GPIO47），不跨总线。

上电后先测 6 颗模块 VCC 均为 3.3 V，再跑软件。

## 5. 软件命令

```bash
. ~/.espressif/v6.0.2/esp-idf/export.sh
PORT=/dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_98:88:E0:11:9F:08-if00

tools/mode.sh test && tools/build.sh
python3 tools/run_tests.py --port "$PORT" --expect-sources 0,1,2,3,4,7 \
    --raw evidence/2026-11-02-field/stage3.raw
```

判据：6 源各 `UNIT_RESULT ... PASS`、`WHO_AM_I=0x70`、`BUS_BIND` 为
0→B、1/2/3/4→A、7→B，`BUS_STATS A/B err=0`。sid5/6/8/9/10 应为 ABSENT。

通过后再做 60 s 流测试：

```bash
tools/mode.sh stream && tools/build.sh
python3 tools/stream_capture.py --port "$PORT" --duration 60 \
    --out evidence/2026-11-02-field/stream-6src.jsonl \
    --raw evidence/2026-11-02-field/stream-6src.raw
python3 tools/analyze_stream.py --input evidence/2026-11-02-field/stream-6src.jsonl \
    --window 10 --out evidence/2026-11-02-field/stream-6src-analysis.json
```

任何失败先停，保留原始日志；不要降频、不要串电阻代替隔离、不要跳过 6 源直接上 11 源。
