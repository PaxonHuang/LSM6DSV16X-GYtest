# 新会话接力 Prompt（复制到 Claude Code）

> 用途：在**新会话**里继续 LSM6DSV16X 多源 IMU 的洞洞板方案 A。
> 先把下面整段贴给 Claude Code。

---

你在 `/home/paxon/ESP32Projects/LSM6DSV16X-GYtest` 继续 LSM6DSV16X 多源
IMU bring-up。先完整读这两份文档，再动手：

- `docs/HANDOFF.md` — 当前状态、已验证结论、命令、已踩过的坑
- `docs/perfboard-11-imu.md` — 洞洞板布局、BOM、接线表、装配/验收步骤

## 当前结论（不要重新推导）

- 固件、SPI 模式（0/3）、动态 CS0 路由、BDU、时钟（10 kHz–1 MHz）都已排除；
  面包板+跳线的共享总线电气质量不足，输出块多字节读取会被截断。
- 两颗模块身份/配置正常：`WHO_AM_I=0x70`、
  `CTRL1=0x06 CTRL2=0x06 CTRL3=0x44 CTRL6=0x04`。
- 用户已决定转**洞洞板焊接**：先 2 路原型，通过后 6 路、11 路。
- 不要回到面包板做多源测试；不要在固件里靠降频/放宽阈值绕过接线问题。

## 你的任务

1. 按 `docs/perfboard-11-imu.md` 指导用户焊 **2 路**原型（每路：MISO 串
   120 Ω、CS 10 kΩ 上拉、VCC–GND 100 nF；地线用粗线星形）。
2. 用户说接好后，运行：
   ```bash
   . ~/.espressif/v6.0.2/esp-idf/export.sh
   tools/mode.sh test
   tools/build.sh
   python3 tools/run_tests.py --port /dev/ttyACM0 --expect 2
   ```
3. 2 路通过后，断电扩到 6 路 → `--expect 6`；再扩到 11 路 →
   `--expect 11`。每阶段单独保存 `evidence/` 日志，失败就停，不跳阶段。
4. 每阶段通过后，用 `tools/mode.sh stream` + `tools/web_panel.py --cli`
   验证逐源在线状态和热插拔显示。
5. 全部通过后，清理临时文件、更新 `DEVELOPMENT_REPORT.md`，并按用户指示
   处理 git（当前目录还不是 git 仓库；`components/lsm6dsv16x/.git` 是
   vendored 驱动的嵌套仓库，提交前需决定删除还是做成 submodule）。

## 硬性规则

- 构建一律用 `tools/build.sh`；**不要隐藏构建输出**；用 ELF mtime 或
  `strings` 确认新代码真的进了镜像（曾因 stale object 浪费大量时间）。
- Kconfig bool 关闭时宏未定义，用 `#ifdef`，不要 `#if`。
- 绝不驱动 GPIO19/20（USB）；CS 表避开 0/3/45/46 和 flash/PSRAM 引脚。
- 需要物理操作时，给到针级步骤和预期证据；用户会配合。
- 没有证据不要宣称 6/11 路通过；轮询计数不等于同步/无损采样。

## 关键命令

```bash
tools/mode.sh test | stream
tools/build.sh
python3 tools/run_tests.py --port /dev/ttyACM0 --expect N
python3 tools/capture.py --port /dev/ttyACM0 --raw evidence/xxx.bin
python3 tools/web_panel.py --port /dev/ttyACM0 --cli
```
