# ESP32-S3 (N16R8) 驱动 LSM6DSV16X 开发报告

> 面向「以后还要再做一遍」的你。全文按「现象 → 根因 → 修法」组织，
> 每条坑都给出可验证的证据，不含猜测。

---

## 0. 最终结果

```
config readback: CTRL1=0x06 CTRL2=0x06 STATUS=0x07
window 1.00 s: acc=117 gyro=117 (expected ~120) drdy xl=117 gy=117 none=884
UNIT_RESULT 0 PASS 23/23 raw=0x70 ok
```

Web 面板（three.js 3D 位姿 + 实时曲线）已在真实硬件上跑通：
50 Hz 推流、加速度模长 0.991 g、3D 立方体四元数与固件一致、控制台零错误。

| 项目 | 值 |
|---|---|
| 平台 | 江协 ESP32-S3-DevKitC-44 pin，N16R8（16 MB Flash / 8 MB PSRAM） |
| ESP-IDF | v6.0.2（`~/.espressif/v6.0.2/esp-idf`） |
| 传感器 | LSM6DSV16X（IMU + 6D 姿态 + 机器学习核心） |
| 总线 | SPI mode 3（CPOL=1, CPHA=1），全双工，1 MHz |
| 驱动 | ST 官方 `STMicroelectronics/lsm6dsv16x-pid` v6.2.0（commit `23a6e59`） |
| 接线 | GPIO12→SCLK、GPIO11→MOSI、GPIO13→MISO、GPIO1→CS、INT1 悬空 |
| 结果 | **23/23 项检查通过**，`WHO_AM_I=0x70` |
| 可视化 | three.js r169（本地 vendored）+ SSE，见 §6 |

实测数据（模块静置）：加速度模长 0.99 g，陀螺零偏 < 1 dps。

---

## 1. 项目结构

```
LSM6DSV16X-GYtest/
├── main/
│   ├── main.c                 # 测试固件（约 600 行）
│   ├── Kconfig.projbuild      # 单元数量、每颗的 CS 引脚
│   └── CMakeLists.txt
├── components/lsm6dsv16x/     # ST 官方驱动，原样 vendored 未改一行
├── tools/
│   ├── spi_frame_model.py     # 离线 SPI 时序模型（上位机可跑）
│   ├── run_tests.py           # 烧录→回读校验→复位→采集→解析
│   ├── web_panel.py           # 串口 → SSE 桥接 + 静态服务
│   ├── mode.sh                # 切换 test / stream 两种固件模式
│   └── build.sh               # 强制重编的构建脚本
├── web/
│   ├── index.html             # 面板结构
│   ├── style.css              # 调色板（已过 CVD 校验）
│   ├── app.js                 # three.js 场景 + SVG 曲线
│   └── vendor/three.module.js # three.js r169，MIT
├── sdkconfig.defaults
├── sdkconfig.stream           # stream 模式的配置叠加层
└── DEVELOPMENT_REPORT.md      # 本文
```

---

## 2. 排坑要点（按踩坑顺序）

### 坑 1：flash size 必须是 16 MB，否则 bootloader 拒绝启动

**现象**（最隐蔽的一个）：

```
E (55) esp_image: invalid segment length 0xffffffff
E (55) boot: Factory app partition is not bootable
E (56) boot: No bootable app partitions in the partition table
```

**根因**：ESP-IDF 默认 `ESPTOOLPY_FLASHSIZE` 是 **2 MB**，而 N16R8 实际是 16 MB。
ROM bootloader 按镜像头里声明的 2 MB 布局去定位 `factory` 分区，地址算错，
读出来全是 `0xFF`。

同一时刻还有一条被忽略的警告：

```
W (156) spi_flash: Detected size(16384k) larger than the size in the binary image header(2048k)
```

**修法**：

```
CONFIG_ESPTOOLPY_FLASHSIZE_16MB=y
CONFIG_ESPTOOLPY_FLASHFREQ_80M=y
```

**教训**：看到 `Detected size(...) larger than the size in the binary image header`
这条 warning 时不要忽略——它是启动失败的**先行指标**。

---

### 坑 2：ESP32-S3 的 SPI 半双工跑不起来，必须用全双工

**现象**：

```
E (291) spi_master: check_trans_valid(1134): SPI half duplex mode is not
supported when both MOSI and MISO phases are enabled.
```

**根因**：`SOC_SPI_HD_BOTH_INOUT_SUPPORTED` 只有 esp32 / esp32s2 定义，
**esp32s3 没有**。所以 S3 在半双工模式下无法同时驱动 MOSI 和 MISO 相。

IDF 源码里的判定（`esp_driver_spi/src/gpspi/spi_master.c`）：

```c
#if !SOC_SPI_HD_BOTH_INOUT_SUPPORTED
    SPI_CHECK(!is_half_duplex || !tx_enabled || !rx_enabled,
              "SPI half duplex mode is not supported when both MOSI and MISO phases are enabled.");
    SPI_CHECK(!is_half_duplex || !trans_desc->length || !trans_desc->rxlength,
              "SPI half duplex mode is not supported when both MOSI and MISO phases are enabled.");
#endif
```

**修法**：`.flags = 0`（全双工），**不要**加 `SPI_DEVICE_HALFDUPLEX`。

半双工下每个事务只能单向，那条 `rxlength`/`length` 置零的技巧（跳过一个相）
在 S3 上也不适用。

---

### 坑 3：全双工下 tx/rx 不能共用同一个 buffer

**现象**：单字节读（`WHO_AM_I`）正常，多字节读全是 `0x00`。

**根因**：全双工时 MOSI 正在移出的 dummy 字节会覆盖 MISO 刚收到的字节。

**修法**：分开的 tx / rx 缓冲区：

```c
uint8_t tx[1 + 16] = { cmd };
uint8_t rx[1 + 16] = { 0 };
/* ... */
memcpy(buf, &rx[1], len);   /* payload 偏移 1 字节 */
```

---

### 坑 4：CS 必须在「地址字节 + 数据字节」之间保持低电平

**现象**：读寄存器拿到全 0，但同一根线上换个帧格式又能读到值。

**根因**：LSM6DSV16X 把「地址字节 + 数据字节」当作**一个命令帧**。
如果拆成两个独立 SPI 事务，驱动会在两者之间抬起 CS，器件认为命令已结束，
第二段变成没有地址的野数据 → MISO 保持空闲电平（读回 `0x00`）。

**修法**：**一个事务**内发完地址 + dummy，接收 `len+1` 字节，取 `rx[1..len]`：

```c
spi_transaction_t t = {
    .length    = (size_t)(len + 1) * 8,
    .rxlength  = (size_t)(len + 1) * 8,
    .tx_buffer = tx,     /* tx[0]=addr, tx[1..]=dummy */
    .rx_buffer = rx,
};
```

ST 官方参考实现（`STMems_Standard_C_drivers/lsm6dsv16x_STdC/examples/
lsm6dsv16x_read_data_polling.c`）用两次 `HAL_SPI_Transmit/Receive`，
是因为 STM32 上 CS 是**软件控制**的，两次调用之间 CS 一直低。
ESP-IDF 驱动默认每事务切一次 CS，所以必须合并成一次事务。

---

### 坑 5：`CONFIG_FREERTOS_HZ=100` 时 `pdMS_TO_TICKS(8)` 等于 0

**现象**：「1 秒采样窗口」里只拿到 2~3 个样本，数据就绪标志几乎永远读不到。

**根因**：

```c
vTaskDelay(pdMS_TO_TICKS(1000 / 120));   // = pdMS_TO_TICKS(8)
```

tick 频率 100 Hz 时，`pdMS_TO_TICKS(8) = 8 * 100 / 1000 = 0`，
**`vTaskDelay(0)` 根本不延时**。循环以远高于 120 Hz 的速率空转，
每次都落在两个样本之间，就绪标志自然读不到。
（数据本身是好的——改成 `pdMS_TO_TICKS(50)` 后 40/40 次全部命中。）

**修法**：

```
CONFIG_FREERTOS_HZ=1000
```

并且**采样窗口应该用挂钟时间驱动**，不要用循环次数推算：

```c
int64_t start = esp_timer_get_time();
while (esp_timer_get_time() - start < 1000000) {   /* 1 s */
    ...
    vTaskDelay(pdMS_TO_TICKS(1));
}
int expected = (int)((elapsed_us * TEST_ODR_HZ) / 1000000);
```

---

### 坑 6：传感器出厂是 power-down 模式，ODR 写对了也不出数

**现象**：`xl_data_rate_set(ODR_120Hz)` 返回 0（成功），但读不到任何数据。

**根因**：ST 的 `lsm6dsv16x_xl_data_rate_set()` **只写 ODR 字段，不改工作模式**：

```c
ret = lsm6dsv16x_read_reg(ctx, LSM6DSV16X_CTRL1, (uint8_t *)&ctrl1, 1);
ctrl1.odr_xl = (uint8_t)val & 0x0Fu;
ret = lsm6dsv16x_write_reg(ctx, LSM6DSV16X_CTRL1, (uint8_t *)&ctrl1, 1);
```

器件默认 OP_MODE=power-down，ODR 字段写进去了也不产生样本。

**修法**：显式设工作模式。

```c
lsm6dsv16x_xl_mode_set(&ctx, LSM6DSV16X_XL_HIGH_PERFORMANCE_MD);
lsm6dsv16x_gy_mode_set(&ctx, LSM6DSV16X_GY_HIGH_PERFORMANCE_MD);
```

---

### 坑 7：位域打印会掩盖真实寄存器值（差点让我误判硬件坏了）

**现象**：追踪日志显示

```
CTRL1=0x00 CTRL2=0x00 STATUS=0x00
```

我据此判定「配置写入没生效」，排查了半小时。

**根因**：那行日志打印的是**位域**不是原始字节：

```c
ESP_LOGI(TAG, "CTRL1=0x%02X", ctrl1.op_mode_xl);   // op_mode_xl 是 [6:4] 位！
ESP_LOGI(TAG, "STATUS=0x%02X", st.xlda | (st.gda << 1));  // 只拼了 DRDY 位
```

CTRL1 实际是 `0x06`（ODR=120Hz），`op_mode_xl` 字段自然是 0。
STATUS 实际是 `0x07`，我只打印了 2 个 DRDY 位。

**修法**：打印**原始字节**。

```c
uint8_t ctrl1 = 0, ctrl2 = 0, st = 0;
lsm6dsv16x_read_reg(&ctx, LSM6DSV16X_CTRL1, &ctrl1, 1);
ESP_LOGI(TAG, "CTRL1=0x%02X", ctrl1);
```

**教训**：ST 驱动的结构体几乎全是位域，**日志一律打原始字节**。
这一条在 ST 驱动里尤其容易踩，因为位域名和寄存器语义长得像但完全不是一回事。

---

### 坑 8：ESP32-S3 的 USB-JTAG 复位时序（进下载模式 / 枚举失败）

这一条和传感器无关，但会让你以为传感器坏了。

**现象 A**：烧录后芯片不跑应用，只打印：

```
rst:0x15 (USB_UART_CHIP_RESET),boot:0x22 (DOWNLOAD(USB/UART0))
waiting for download
```

**根因**：ESP32-S3 的 USB-JTAG 桥接芯片把 **RTS 接到 GPIO0（BOOT）**、**DTR 接到 EN**。
复位时如果 RTS 保持高电平，GPIO0 被拉低 → 芯片进 ROM 下载模式。

**修法**：先放开 RTS，再脉冲 DTR；更可靠的是直接用 esptool 的复位序列：

```python
esptool.py --chip esp32s3 -p /dev/ttyACM0 \
           --before default-reset --after hard-reset chip-id
```

实测只有 esptool 这条路径能可靠让板子跑到应用。

**现象 B**：`/dev/ttyACM*` 时有时无，内核刷屏：

```
usb 1-8: device descriptor read/64, error -71
usb usb1-port8: unable to enumerate USB device
```

`-71` = EPROTO，出现在**读设备描述符**阶段 —— USB 电气层就不对，固件无关。

**根因**：USB 线只有电源没有数据芯，或接口供电不足。

**修法**：换数据线 + 换 USB 口（避开集线器）+ 必要时外部供电。
判断依据是「内核日志里有没有 `303a:1001` 这个 VID:PID」——
只要它出现过，USB 层就是好的；`-71` 只是枚举重试的噪声。

---

### 坑 9：增量构建复用旧目标文件，「代码改了但固件没变」

**现象**：改了代码，重新编译，重新烧录，行为完全没变；
串口里 `Compile time` 停在旧时间戳。

**根因**：ESP-IDF 的增量构建（ninja）比较 mtime，源文件改动没有触发重编。

**修法**：`tools/build.sh` 里强制删除目标文件，并打印镜像内嵌的编译时间：

```bash
rm -f build/esp-idf/main/CMakeFiles/__idf_main.dir/main.c.obj
idf.py build
strings build/lsm6dsv16x_test.bin | grep -E '^[0-9]{2}:[0-9]{2}:[0-9]{2}$'
```

**注意**：镜像里的时间戳来自 IDF 组件 `esp_app_format/esp_app_desc.c` 的
`__TIME__`，**只有该组件重编时才会更新**。所以时间戳不变不一定代表
你的代码没进去——要靠 `strings` 查你自己的日志字符串来确认：

```bash
strings build/lsm6dsv16x_test.elf | grep "你的新日志文本"
```

---

### 坑 10：面包板接线撑不住 10 MHz

**现象**：1 MHz 能读到 `WHO_AM_I=0x70`，5 MHz 就读回 `0x00`。

**根因**：杜邦线 + 面包板的信号完整性。

**修法**：bring-up 阶段固定 1 MHz。信号完整性排查**不要**靠猜接线，
用诊断扫描把「配置问题」和「接线问题」分开：

```
mode=3  1000kHz -> WHO_AM_I=0x70  <== MATCH
mode=3  5000kHz -> WHO_AM_I=0x00
```

**这类「参数扫描」是本文最有效的排障手段**：把模式、频率、帧格式、CS 极性
做成一张表，一次跑完，让数据自己指出哪个组合是通的。

---

### 坑 11：判断「某轴是否坏了」的判据写错了

**现象**：判「只有 1 个加速度轴有信号 → 该轴坏了」。

**根因**：模块平放时，水平轴本就是 ±0.02 g 量级，而我用了 0.15 g 阈值。
**每轴的绝对值说明不了任何事情**——真正该成立的是**矢量模长 ≈ 1 g**。

**修法**：

```c
/* 判据 1：模长接近 1 g */
check(t, mag >= 0.85f && mag <= 1.15f, "acc magnitude %.3f g", mag);

/* 判据 2：没有两个以上的轴恒为 0（真坏了的轴是精确 0，与姿态无关） */
int zero_axes = 0;
for (i) if (fabsf(acc[i]) < 0.001f) zero_axes++;
check(t, zero_axes < 2, "%d accel axes read exactly zero", zero_axes);
```

---

### 坑 12：多块模块不能共用 MISO

LSM6DSV16X 在 CS 拉高时会把 SDO 驱动为高（3-wire 行为）。
多颗共用 MISO 时，高阻/高电平会互相打架。

**修法**（本项目采用）：**一次只接一颗**，每颗用独立 CS 引脚，
`Kconfig.projbuild` 里配置 `UNIT_COUNT` 和各颗的 CS。
量产/批量测试时建议每颗加串联电阻或用总线开关隔离。

---

### 坑 13：烧录「成功」但镜像只写进去一部分

**现象**：`idf.py flash` 报告 `Hash of data verified`，启动却报：

```
E (55) esp_image: invalid segment length 0xffffffff
E (56) boot: No bootable app partitions in the partition table
```

和坑 1（flash size 配错）**症状完全相同**，极易误判。

**根因**：回读 flash 发现镜像只写到 `0x12180`（约 72 KB），其后全是 `0xFF`，
而实际镜像 212 KB。esptool 的哈希校验针对的是**它发出去的数据**，不是
**最终落在 flash 上的内容**——传输被截断时它仍可能报成功。

**修法**：烧录后**回读比对**。`tools/run_tests.py` 现在每次烧录都会执行：

```python
# 读回 0x10000 处的整段 app 镜像，与 build/ 里的 .bin 逐字节比较
esptool read-flash 0x10000 <size> build/verify/flash_verify.bin
```

不一致时直接报出**第一个不同字节的偏移**并中止，而不是让你去猜硬件。

手动排查时：

```bash
SZ=$(stat -c %s build/lsm6dsv16x_test.bin)
esptool.py --chip esp32s3 -p /dev/ttyACM0 read-flash 0x10000 $SZ /tmp/chk.bin
cmp /tmp/chk.bin build/lsm6dsv16x_test.bin   # 无输出 = 一致
```

**教训**：只要「镜像损坏」和「配置错误」症状一样，就先做一次逐字节回读比对，
再谈别的原因。这一条能省掉最难熬的那段时间。

---

### 坑 14：删掉 sdkconfig 会丢失 target

**现象**：

```
CMake Error at tools/cmake/targets.cmake:159:
  CMAKE_TOOLCHAIN_FILE 'toolchain-esp32s3' does not match currently
  selected IDF_TARGET 'esp32'.
FAILED: bootloader-prefix/src/bootloader-stamp/bootloader-configure
```

**根因**：`CONFIG_IDF_TARGET` 存在 `sdkconfig` 里。切换模式时删掉 `sdkconfig`
重新生成，目标就回落到默认的 **esp32**，而 build 目录里仍是 esp32s3 的工具链，
两者对不上。

**修法**：把目标钉在 `sdkconfig.defaults` 里：

```
CONFIG_IDF_TARGET="esp32s3"
```

这样任何一次重新生成 `sdkconfig` 都还是 esp32s3。

---

## 3. 关键代码（可直接复用）

### 3.1 SPI 传输层（全双工、单事务、payload 偏移 1）

```c
static int32_t imu_spi_read(void *handle, uint8_t reg, uint8_t *buf,
                            uint16_t len)
{
    imu_unit_t *u = (imu_unit_t *)handle;
    uint8_t     cmd = (uint8_t)(reg | SPI_READ_BIT);

    uint8_t tx[1 + 16] = { cmd };
    uint8_t rx[1 + 16] = { 0 };

    if (len > 16) {
        return -1;
    }
    for (uint16_t i = 0; i < len; i++) {
        tx[1 + i] = 0x00;   /* dummy 字节 */
    }

    spi_transaction_t t = {
        .length    = (size_t)(len + 1) * 8,
        .rxlength  = (size_t)(len + 1) * 8,
        .tx_buffer = tx,      /* 不能和 rx 共用 buffer */
        .rx_buffer = rx,
    };
    int32_t rc = (int32_t)spi_device_transmit(u->spi, &t);
    if (rc == 0) {
        memcpy(buf, &rx[1], len);   /* payload 偏移 1 字节 */
    }
    return rc;
}
```

写操作把 `tx[1..]` 换成实际数据即可，`rx_buffer` 传 `NULL`。

### 3.2 SPI 设备配置

```c
spi_device_interface_config_t dev = {
    .clock_speed_hz  = 1000000,   /* 面包板起步 1 MHz */
    .mode            = 3,          /* CPOL=1 CPHA=1 */
    .spics_io_num    = cs,         /* CS 交给 SPI 驱动管 */
    .cs_ena_pretrans = 1,
    .cs_ena_posttrans = 1,
    .queue_size      = 4,
    .flags           = 0,          /* 全双工：S3 半双工不可用 */
};
```

### 3.3 传感器初始化顺序（每一步都验证读回）

```c
lsm6dsv16x_sw_por(&ctx);                       /* 内部已含 30 ms 延时 */
vTaskDelay(pdMS_TO_TICKS(20));
lsm6dsv16x_block_data_update_set(&ctx, PROPERTY_ENABLE);
lsm6dsv16x_xl_full_scale_set(&ctx, LSM6DSV16X_2g);
lsm6dsv16x_gy_full_scale_set(&ctx, LSM6DSV16X_2000dps);
lsm6dsv16x_xl_mode_set(&ctx, LSM6DSV16X_XL_HIGH_PERFORMANCE_MD);  /* 必须 */
lsm6dsv16x_gy_mode_set(&ctx, LSM6DSV16X_GY_HIGH_PERFORMANCE_MD);  /* 必须 */
lsm6dsv16x_xl_data_rate_set(&ctx, LSM6DSV16X_ODR_AT_120Hz);
lsm6dsv16x_gy_data_rate_set(&ctx, LSM6DSV16X_ODR_AT_120Hz);
```

读回验证（**用原始字节**）：

```c
uint8_t c1 = 0, c2 = 0, st = 0;
lsm6dsv16x_read_reg(&ctx, LSM6DSV16X_CTRL1, &c1, 1);
lsm6dsv16x_read_reg(&ctx, LSM6DSV16X_CTRL2, &c2, 1);
lsm6dsv16x_read_reg(&ctx, LSM6DSV16X_STATUS_REG, &st, 1);
/* 期望: c1=0x06 c2=0x06 st=0x07 */
```

### 3.4 采样（XL / GY 就绪位独立判断）

```c
lsm6dsv16x_data_ready_t drdy = { 0 };
lsm6dsv16x_flag_data_ready_get(&ctx, &drdy);
if (drdy.drdy_xl) { /* 读加速度 */ }
if (drdy.drdy_gy) { /* 读陀螺 */ }
```

**不要**要求 `drdy_xl && drdy_gy` 同时成立——两个标志独立置位。

---

## 4. 自动化工具链

```bash
# 一次性环境准备
. ~/.espressif/v6.0.2/esp-idf/export.sh

# 构建（强制重编）
tools/build.sh

# 烧录 + 复位 + 采集 + 解析，退出码即结论
python3 tools/run_tests.py --port /dev/ttyACM0

# 离线验证 SPI 帧格式（不接硬件）
python3 tools/spi_frame_model.py

# 切换固件模式
tools/mode.sh stream          # Web 面板用的推流固件
tools/mode.sh test            # 23 项健康检查
tools/mode.sh                 # 查看当前模式

# Web 面板
python3 tools/web_panel.py --port /dev/ttyACM0
python3 tools/web_panel.py --simulate --units 11   # 无硬件预览
```

固件的输出契约（脚本据此解析，勿改措辞）：

```
UNIT_RESULT <index> <PASS|FAIL> <passed>/<total> raw=0x<xx> <detail>
MATRIX_DONE <n>
```

---

## 5. 检查项清单（23 项）

| 组 | 检查内容 |
|---|---|
| 身份 | `WHO_AM_I == 0x70` |
| 配置 | sw_por / BDU / 量程 / 模式 / ODR 写入均返回 0；CTRL1/CTRL2/STATUS 读回正确 |
| 寄存器读写 | 控制寄存器写→读回→还原 |
| 数据通路 | 加速度与陀螺各有样本；加速度模长 0.5~2.5 g；无两轴恒为 0 |
| 静态窗口 | 1 s 挂钟窗口内样本数 ≥ 期望值 80%；平均模长 0.85~1.15 g；每轴陀螺零偏 ≤ 3 dps；噪声 ≤ 1 dps |

阈值都留了余量（LSM6DSV16X 陀螺零偏典型 ±2.5 dps，噪声更小），
但足以把「接线错 / 供电不足 / 器件损坏」区分出来。

---

## 6. Web 调试面板（three.js 3D 实时位姿）

### 6.1 架构选择

| 方案 | 取舍 |
|---|---|
| **PC 侧桥接（采用）** | 串口 → SSE → 浏览器。复用已验证的 USB 链路，无需 WiFi 配网，three.js 本地 vendored 可离线，11 块模块共用一条串口 |
| ESP32 内嵌页面 | 需要把 1.3 MB 的 three.js 塞进文件系统分区 + 加 WiFi，调试面板阶段不划算 |

数据只单向流动，所以用 **SSE** 而不是 WebSocket——标准库即可，无额外依赖。

### 6.2 运行

```bash
# 1) 切到 stream 模式并烧录
. ~/.espressif/v6.0.2/esp-idf/export.sh
tools/mode.sh stream
idf.py build && idf.py -p /dev/ttyACM0 flash

# 2) 起面板
python3 tools/web_panel.py --port /dev/ttyACM0
# 打开 http://127.0.0.1:8000
```

没有硬件也能验证界面：

```bash
python3 tools/web_panel.py --simulate --units 11
```

### 6.3 数据格式（固件 → 桥接）

固件以 50 Hz 输出 NDJSON，从第一版就是**数组**，所以扩到 11 块不需要改协议：

```json
{"t":12656,"u":[{"i":0,
  "a":[-0.977,0.010,0.179],
  "g":[-0.070,0.210,-0.490],
  "q":[0.2512,0.5884,-0.2961,0.7092],
  "aq":1,"va":1,"vg":1}]}
```

| 字段 | 含义 |
|---|---|
| `t` | 毫秒时间戳 |
| `i` | 模块编号（对应 CS 引脚序号） |
| `a` / `g` | 加速度 (g) / 角速度 (dps) |
| `q` | 四元数 `[x, y, z, w]`，注意 **w 在最后**（three.js 的 `Quaternion(x,y,z,w)` 直接可用） |
| `aq` | 四元数是否有效 |
| `va` / `vg` | 加速度 / 角速度本帧是否新鲜——**无效时浏览器跳过而不是画 0** |

### 6.4 姿态来源：用芯片自己的融合引擎

LSM6DSV16X 内置 **SFLP**（Sensor Fusion Low Power），直接输出 6 轴游戏旋转
向量。项目采用它，而不是在上位机做 Madgwick：精度更好、ESP32 零负担、
不受浏览器帧率抖动影响。

读取路径（ST 官方 `lsm6dsv16x_sensor_fusion.c` 同款）：

```
fifo_sflp_batch_set(game_rotation = 1, gravity = 1)
sflp_data_rate_set(SFLP_60Hz)
sflp_game_rotation_set(ENABLE)
fifo_watermark_set(8) → fifo_mode_set(STREAM_MODE)
循环：fifo_status_get → fifo_out_raw_get → 按 tag 分派
```

**四元数只有 3 个分量**，是 FP16；第 4 个由单位长度反推：

```c
q[3] = sqrtf(1.0f - (q[0]*q[0] + q[1]*q[1] + q[2]*q[2]));
```

固件里自带 FP16 解码（`fp16_to_float`），不依赖 `npy_half_to_float`。

SFLP 未就绪时（`aq:0`），浏览器回退到陀螺积分，保证上电初期画面也会动。

### 6.5 界面

- **3D**：每块一个立方体 + XYZ 三色坐标轴；`>6` 块自动换行成网格，相机按
  布局自动对焦（实测 11 块时 `worstX=0.92`，全部在视锥内）；拖动旋转、滚轮缩放
- **读数**：加速度模长、角速度模长、Roll/Pitch/Yaw、实际数据率
- **曲线**：加速度与角速度各一张图，三轴分色（X/Y/Z），**不做双 Y 轴**
- **数据表**：一键切换全部模块的数值表（无障碍与核对用）

### 6.6 配色（已通过校验，不是凭感觉挑的）

三轴用经 CVD（色盲）校验的分类色板，浅/深色各自成套：

| 轴 | 浅色 | 深色 |
|---|---|---|
| X | `#2a78d6` | `#3987e5` |
| Y | `#eb6834` | `#d95926` |
| Z | `#1baf7a` | `#199e70` |

校验结果：浅色最差相邻 CVD ΔE 9.2、深色 9.4（阈值 ≥8），正常视觉 27.6 / 26.5
（阈值 ≥15）。浅色下 Z 轴对比度 2.74:1 低于 3:1，因此**每条线末端都有 X/Y/Z
直接标签**作为补偿——颜色从不是唯一的识别手段。

### 6.7 一个前端的坑

图表最初完全没有曲线：模拟器没发 `va`/`vg` 标志，前端 `if (u.va)` 判假就跳过了
所有样本。已改成 `u.va !== 0`（缺省视为有效），两边都修了。

另外 `WebGLRenderer` 需要 `preserveDrawingBuffer: true` 才能在合成后读回像素，
否则截图/自检拿到的是空白——曾因此误判「3D 没渲染」。

---

## 7. 下一步：11 块模块批量测试

固件和协议已经为多块留好接口（`CONFIG_UNIT_COUNT`、每块独立 CS、NDJSON 数组），
但**多块共用 MISO 在电气上需要额外处理**：

- LSM6DSV16X 在 CS 拉高时会把 SDO 驱动为高（3-wire 行为），多颗并挂会互相打架
- 可选方案：
  1. **每颗 MISO 串一个 100–220 Ω 电阻**（最省事，低速下够用）
  2. 用 74HC4051 之类的模拟开关在 MISO 上做选择
  3. 用 74HC138 译码 CS、配合 MISO 隔离
- 建议先用 2 块验证隔离方案，再扩到 11 块

`CONFIG_UNIT_COUNT` 目前上限是 4（`MAX_UNITS`），扩到 11 需要同时改
`main.c` 的 `MAX_UNITS` 和 `Kconfig.projbuild` 的 `range`。

---

## 附录 A：ST 官方资料位置

| 内容 | 位置 |
|---|---|
| 平台无关驱动 | `github.com/STMicroelectronics/lsm6dsv16x-pid`（v6.2.0，BSD-3-Clause） |
| 官方示例（含 SPI 时序） | `github.com/STMicroelectronics/STMems_Standard_C_drivers` → `lsm6dsv16x_STdC/examples/` |
| 自测例程 | 同上 `lsm6dsv16x_self_test.c` |
| 数据手册 | ST 官网 LSM6DSV16X PDF（寄存器表见 §2.2/§2.3） |

驱动以 `git clone --depth 1` 原样 vendored，未做任何修改，
仅补了一个 `idf_component_register()` 的 `CMakeLists.txt`。

## 附录 B：SPI 帧格式速查

| 位 | 含义 |
|---|---|
| bit 7 | 1 = 读，0 = 写 |
| bit 6 | IF_INC（地址自动递增），芯片默认已置位，本项目不动它 |
| bit 5..0 | 寄存器地址（0x00–0x7F） |

- **读**：`tx[0] = reg | 0x80`，再发 N 个 dummy，接收 N+1 字节，取 `rx[1..N]`
- **写**：`tx[0] = reg`，再发 N 个数据字节
- 全程 CS 为低，mode 3，1 MHz 起步

---

## 8. 多源 bring-up 更新（2026-10-24）

### 8.1 固件改造

- 单一硬件 CS0 + GPIO Matrix 动态路由到 1–11 路 CS；不再为每颗建
  `spi_device`（S3 每个 SPI 外设只有 3 个硬件 CS）。
- 关键修正：事务之间**保持 CS0 路由**，只在换源时用
  `SIG_GPIO_OUT_IDX` 释放上一颗。每个事务后重连矩阵会在下一帧起始产生
  毛刺，器件收不到命令，MISO 读回 `0xFF` 后全 0。
- 陀螺+加速度改为一次读 **12 字节连续块**（0x22–0x2D）；对截断帧用
  “加速度模长必须在 0.2–3 g”做有效性校验，最多 5 次重试。
- 支持热插拔：每源独立 `present` 状态，按 `WHO_AM_I` 周期探测，
  输出 `HOTPLUG <i> ADDED|REMOVED`。
- 固件探测全部 11 个 CS 位置，未接的报 `ABSENT`，同一镜像适配
  1/2/6/11 路，无需按阶段重编。

### 8.2 实测结论

- 两颗模块均能识别 `0x70`，配置回读 `CTRL1=0x06 CTRL2=0x06
  CTRL3=0x44 CTRL6=0x04`。
- 面包板+跳线下，输出块的多字节读取不稳定（单字节配置读取正常）。
  已排除固件、动态 CS 路由、BDU、SPI 模式（0/3）和时钟
  （10 kHz–1 MHz）因素。
- 实测线阻 2–5 Ω，GPIO2 模块 GND 达 10 Ω；共享 MISO 上还留有
  长跳线残桩。结论是**面包板共享总线的电气质量不足**，不是芯片或驱动
  不支持共享 MISO。
- 决定转洞洞板焊接原型：先 2 路，再 6 路、11 路。设计与 BOM 见
  [`docs/perfboard-11-imu.md`](docs/perfboard-11-imu.md)，接力说明见
  [`docs/HANDOFF.md`](docs/HANDOFF.md)。

### 8.3 工具

- `tools/run_tests.py --expect N`：按源判定，`ABSENT` 不算 FAIL。
- `tools/web_panel.py --cli`：终端仪表盘，逐源在线/离线、ID、读取率、
  错误数、热插拔事件；Web 面板同步支持离线源。
- `tools/capture.py`：带复位的原始串口采集，保留 raw 字节。
- 诊断模式 `RUN_MODE_DIAG`：逐 CS 直连扫描
  （mode 0/3 × 100/400/1000 kHz）、CS 短路交叉检查、12 字节块与
  单字节对照、生产路由路径复现。

### 8.4 对前文的修正

- 多颗共享 MISO 在电气上可行（数据手册：CS 拉高后 SDO 输出禁用时间
  ≤50 ns），但前提是地、串阻和走线合格；不能把“面包板失败”归因为
  芯片不支持共享。
- 早期“23/23”是单源历史结果；多源尚未通过，不能外推。
- 报告中关于 `pdMS_TO_TICKS(8)=0` 的因果表述保留为“可能的空转原因”，
  不是唯一根因（见 cleanroom REVIEW.md）。
