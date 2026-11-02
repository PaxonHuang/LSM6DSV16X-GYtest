# EVT-A 双 SPI 2 源面包板接线（sid0 腕部/B + sid1 拇近/A）

适用：市售标准面包板，主区两片 5 孔×30 行（上排 a–e、下排 f–j，中间隔断），
左右各一组纵向 25 孔电源轨（每列一整条，相邻列绝缘）。BOM 已齐：
2× GY-LSM6DSV16X、1× SN74HC125N、2× 10k、100nF、4.7–10µF、跳线。

## 0. 先纠正三个最容易错的地方

1. **GY 模块不能直接插进 5 孔行。** 模块是 6 针，一行只有 5 孔；硬插会跨到相邻行造成短路。模块必须放在板外（或板边），用 6 根跳线接进来。
2. **74HC125N 要跨中缝插。** 缺口朝上，pin1 在上排第 2 行的 e 列，pin14 在下排第 2 行的 f 列。上排第 2 行和下排第 2 行是**两个完全不同的网络**（pin1 与 pin14），不要当成同一行。
3. **每一横排 5 孔是同一个网络；相邻行绝缘。** 所以“接线”就是把该网络的器件/跳线插进同一行的任意空孔。电源轨每列是一整条；相邻列不是同一网络。

## 1. 坐标约定

- **上排**：中缝上方，列 a–e，行 1–30。
- **下排**：中缝下方，列 f–j，行 1–30。
- **左轨**：外侧列 = 3V3，内侧列 = GND。
- **右轨**：外侧列 = 3V3，内侧列 = GND。
- 左、右同名轨各用一根跳线连起来（左外↔右外，左内↔右内），这样两侧任取一孔都是同一电源网络。
- 行号从板子同一端数；建议 DevKit 放在板子同一侧，后面全部按“上排/下排第 N 行”执行。

## 2. U1 = SN74HC125N 引脚表（缺口朝上，跨中缝）

| 引脚 | 名称 | 2 源用途 | 接到 |
|---:|---|---|---|
| 1 | /1OE | sid0 的 CS 门控 | 上排第 2 行 |
| 2 | 1A | sid0 的 MISO 输入 | 上排第 3 行 |
| 3 | 1Y | sid0 的缓冲输出 | 上排第 4 行（B_MISO → GPIO47） |
| 4 | /2OE | sid1 的 CS 门控 | 上排第 5 行 |
| 5 | 2A | sid1 的 MISO 输入 | 上排第 6 行 |
| 6 | 2Y | sid1 的缓冲输出 | 上排第 7 行（A_MISO → GPIO13） |
| 7 | GND | 地 | GND 轨 |
| 8 | 3Y | 未用，悬空 | 下排第 8 行 |
| 9 | 3A | 未用，拉低 | 下排第 7 行 → GND |
| 10 | /3OE | 未用，拉高禁用 | 下排第 6 行 → 3V3 |
| 11 | 4Y | 未用，悬空 | 下排第 5 行 |
| 12 | 4A | 未用，拉低 | 下排第 4 行 → GND |
| 13 | /4OE | 未用，拉高禁用 | 下排第 3 行 → 3V3 |
| 14 | VCC | 3.3V | 3V3 轨 |

> 通道 1 给 sid0（总线 B），通道 2 给 sid1（总线 A）。这与工程包逐源表一致。
> 未用通道必须 /OE→3V3、A→GND、Y 悬空；不要让输入悬空。

## 3. 逐行分配表（核心）

“上 2”= 上排第 2 行；“下 9”= 下排第 9 行。同一行的 5 个孔全部同网络。

| 行 | 网络 | 这一行插什么 |
|---|---|---|
| 上 1 | 3V3 备用 | 跳线到左/右 3V3 轨（可选，方便取电） |
| 上 2 | **SID0_CS** | U1 pin1；模块 sid0 的 CS；GPIO1；10k RCS0 一端 |
| 上 3 | SID0_MISO | U1 pin2；模块 sid0 的 MISO/SDO |
| 上 4 | **B_MISO** | U1 pin3；GPIO47 |
| 上 5 | **SID1_CS** | U1 pin4；模块 sid1 的 CS；GPIO2；10k RCS1 一端 |
| 上 6 | SID1_MISO | U1 pin5；模块 sid1 的 MISO/SDO |
| 上 7 | **A_MISO** | U1 pin6；GPIO13 |
| 上 8 | GND | U1 pin7；跳线到 GND 轨 |
| 上 9 | **A_SCLK** | GPIO12；模块 sid1 的 SCL/SPC |
| 上 10 | **A_MOSI** | GPIO11；模块 sid1 的 MOSI/SDA/SDI |
| 上 11–30 | 空 | 留空 |
| 下 1 | GND | 跳线到 GND 轨；100nF 一端 |
| 下 2 | U1_VCC | U1 pin14；跳线到 3V3 轨；100nF 另一端 |
| 下 3 | 未用 /4OE | U1 pin13；跳线到 3V3 轨 |
| 下 4 | 未用 4A | U1 pin12；跳线到 GND 轨 |
| 下 5 | 未用 4Y | U1 pin11；悬空 |
| 下 6 | 未用 /3OE | U1 pin10；跳线到 3V3 轨 |
| 下 7 | 未用 3A | U1 pin9；跳线到 GND 轨 |
| 下 8 | 未用 3Y | U1 pin8；悬空 |
| 下 9 | **B_SCLK** | GPIO18；模块 sid0 的 SCL/SPC |
| 下 10 | **B_MOSI** | GPIO21；模块 sid0 的 MOSI/SDA/SDI |
| 下 11–30 | 空 | 留空 |

## 4. 两颗模块的 6 根线

> 按模块**丝印功能**接，不按物理第 1 脚顺序猜。SPI 模式下：
> SCL/SPC = SCLK，MOSI/SDA/SDI = MOSI，MISO/SDO = MISO，CS = CS。
> 只接 3.3V，绝不接 5V。先确认模块是否自带稳压/电平转换。

### sid0（腕部，总线 B，CS=GPIO1）

| 模块引脚 | 接到 |
|---|---|
| VCC | 3V3 轨 |
| GND | GND 轨 |
| SCL / SPC | 下 9（B_SCLK） |
| MOSI / SDA / SDI | 下 10（B_MOSI） |
| MISO / SDO | 上 3（U1 pin2 / 1A） |
| CS | 上 2（U1 pin1 / 1OE） |

### sid1（拇近，总线 A，CS=GPIO2）

| 模块引脚 | 接到 |
|---|---|
| VCC | 3V3 轨 |
| GND | GND 轨 |
| SCL / SPC | 上 9（A_SCLK） |
| MOSI / SDA / SDI | 上 10（A_MOSI） |
| MISO / SDO | 上 6（U1 pin5 / 2A） |
| CS | 上 5（U1 pin4 / 2OE） |

## 5. DevKitC-1 的 10 根线

| 信号 | GPIO | 接到 |
|---|---:|---|
| 3V3 | 3V3 | 3V3 轨 |
| GND | GND | GND 轨 |
| CS0 / sid0 | GPIO1 | 上 2 |
| CS1 / sid1 | GPIO2 | 上 5 |
| A_SCLK | GPIO12 | 上 9 |
| A_MOSI | GPIO11 | 上 10 |
| A_MISO | GPIO13 | 上 7 |
| B_SCLK | GPIO18 | 下 9 |
| B_MOSI | GPIO21 | 下 10 |
| B_MISO | GPIO47 | 上 4 |

> DevKitC-1 有 J1/J3 两排；以板子丝印的 GPIO 号为准。GPIO47 在部分版本位于 J3。

## 6. 电阻、电容

| 器件 | 接法 |
|---|---|
| RCS0 10k | 上 2 ↔ 3V3 轨（CS0 上拉，同时保证复位时 /1OE 为高） |
| RCS1 10k | 上 5 ↔ 3V3 轨（CS1 上拉，同时保证复位时 /2OE 为高） |
| CU1 100nF | 下 2（pin14 VCC）↔ 下 1（GND），尽量靠近 U1 |
| CGY0/CGY1 100nF | 每颗模块 VCC–GND 最近处；模块自带可先不加，建议加 |
| CB1 4.7–10µF | 3V3 轨 ↔ GND 轨，靠近 DevKit 进线 |

> 10k 上拉不能省。复位/启动瞬间 GPIO 可能是高阻，/OE 浮空会让缓冲器导通，
> 两条 MISO 可能同时被驱动。

## 7. 装配顺序（务必按顺序，不要一次全插）

1. **断电**。先只做电源：DevKit 3V3→3V3 轨，GND→GND 轨；左右同名轨各一根跳线。万用表断电档确认 3V3–GND 不短路；上电测轨间 3.3V。
2. **插 U1**，跨中缝，pin1 在上 2 的 e 列、pin14 在下 2 的 f 列。先接 pin7→GND、pin14→3V3、100nF、未用通道 3/4 的 /OE→3V3、A→GND、Y 悬空。上电测 pin14=3.3V、pin7=0V。
3. **只接 sid0（腕部/B）**：6 根模块线 + RCS0。上电测模块 VCC=3.3V。跑 `--expect 1`（只期望 sid0）。
4. **再加 sid1（拇近/A）**：6 根模块线 + RCS1。上电。跑 `--expect 2`。
5. 两源都 PASS 后，才考虑 6 路、11 路。失败就停，不跳阶段。

## 8. 软件验证

```bash
. ~/.espressif/v6.0.2/esp-idf/export.sh
PORT=/dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_98:88:E0:11:9F:08-if00

tools/mode.sh test
tools/build.sh

python3 tools/run_tests.py --port "$PORT" --expect 1   # 只 sid0（腕部/B）
python3 tools/run_tests.py --port "$PORT" --expect 2   # sid0 + sid1
```

- `--expect 1` 默认期望 sid0（0..0），也就是腕部/B。
- 只想单独测 sid1（拇近/A）用：`--expect-sources 1`。
- 判据：每源 `WHO_AM_I=0x70`；`UNIT_RESULT ... PASS`；`BUS_BIND` 显示
  sid0→B、sid1→A；`BUS_STATS A/B err=0`。
- 任何全 0/截断、CS 争用、复位循环、`err>0`：停车保留证据，不要降频或串电阻掩盖。

## 9. 最常见错误

1. 6 针模块硬插 5 孔行 → 跨行短路。
2. 把 5V 接到 GY VCC → 可能烧模块；只接 3.3V。
3. CS 的 10k 上拉漏掉 → /OE 在复位时浮空，MISO 争用。
4. MOSI/MISO 接反：丝印 SDA/SDI 是 MOSI，SDO 是 MISO，SCL/SPC 是 SCLK。
5. 模块 CS 只接了模块、没接 U1 的 /OE，或反过来 → 门控不工作。
6. 左右电源轨没连 → 一侧没电。
7. 把上排第 2 行和下排第 2 行当成同一网络 → 它们是 U1 的 pin1 和 pin14，完全不同。
8. 地线太长/太细 → 1 MHz 下容易坏帧；地线用粗线、尽量短、星形汇到 DevKit GND。

## 10. 配套图

- 逐行彩色接线图：`docs/breadboard-2-source-evt-a.html`（浏览器打开，可直接打印）。
- 本文：`docs/breadboard-2-source-evt-a.md`。
- 生成脚本：`tools/gen_breadboard_2src.py`（改行分配后重新生成）。
