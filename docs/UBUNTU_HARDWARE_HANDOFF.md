# Ubuntu Hardware Handoff

## Copy-paste start task

```text
你现在接手 ROBOCON R1/R2 四灯光通信项目的 Ubuntu 实机阶段。

先完整阅读本文件，然后读取三个仓库各自的项目规则、工程审查清单和任务模板。
先检查 remote、branch、HEAD、tag、working tree，不要立即改代码。

目标链路：
R1 受保护状态机 -> F407 专用 UART -> STM32F103 Beacon 板
-> D0/D1/D2/D3/REF/PAR -> Hikrobot 相机 -> R2 解码/稳定器/看门狗
-> R2MissionFSM 本地传感器保护 -> ActionIntent。

固定物理顺序为 D0,D1,D2,D3,REF,PAR，对应 bit0..bit5。
四个数据灯表达 0..15 的持续状态；REF 是有效标志；PAR 是 D0..D3 异或。
重复状态不得重复触发一次性动作。视觉输出不得直接驱动电机、机械臂或夹爪。

严格按本文件 Phase 0 到 Phase 7 顺序推进。每个 Phase 完成后记录命令、输出、
设备端口、接线、观察结果和 BLOCKER/WARNING/OK。mock、dry-run、单元测试和回放
不得写成实机通过。

不得 force push，不得改写 main，不得移动或删除 tag。只在列出的功能分支工作。
不得提交真实 logs、frames、ROI、build、elf、bin、hex、map、o。
不得修改旧 0xAA/0xBB/0xAB、Rscontrol2 0xBC 帧或固定 ROI 默认模式。

关键停止点：在没有确认 F407 空闲 UART 及真实 TX/RX 引脚前，不要修改 CubeMX、
usart.c 或 main.c，不要复用 USART1 和 USART6。先汇报候选引脚和冲突检查，等待确认。
```

## Frozen implementation baseline

| Repository | Branch | Minimum implementation commit |
|---|---|---|
| `JFCY2718/robocon_coop_comm` | `feature/four-light-optical` | `a2b0137f4d31f4c237e8d2c44b8849453d2106ee` |
| `JFCY2718/Rscontrol2` | `feature/beacon-uart-v2` | `5eeb1e6918965edfb4714dd0d64a05b176da7e74` |
| `JFCY2718/robstride_driver_r2` | `feature/four-light-state-machine` | `ecf2f189f4a8444e93aae84e54deefd31bef39b0` |

The handoff document itself is committed after the implementation hashes above,
so the checked-out branch HEAD may be newer. Verify each implementation commit
is an ancestor with `git merge-base --is-ancestor <commit> HEAD`. These are
personal-repository feature branches. Do not open or merge a pull request and
do not push to another team's default branch.

## Remaining work overview

### BLOCKER

1. Confirm an unused F407 UART and its physical TX/RX pins from the real R1
   controller schematic and wiring. USART1 is the host link and USART6 is the
   receiver link; neither is available for Beacon.
2. Compile the F407 and F103 firmware with the ARM toolchain. Windows validation
   did not include a firmware build.
3. Flash and verify the STM32F103 V2 receiver, six physical outputs, ACK and
   300 ms all-off watchdog.
4. Bind the confirmed F407 UART with `R1Coop_BindBeaconUart(&huartX)`, then prove
   R1-to-Beacon ACK and timeout behavior on hardware.
5. Complete a real Hikrobot 16-state expected-vs-observed run.

### WARNING

1. `send_beacon_uart_v2.py` currently sends one state only. Before the 16-state
   camera run, add a tested sequence mode that can hold states 0..15 and write
   an expected CSV compatible with `sixled_expected_observed_check.py`.
2. The F103 firmware is bare-metal. During the first build/review, verify vector
   placement, startup assumptions, `.bss` initialization, SysTick at 1 ms and
   CRC golden vectors before flashing.
3. The R2 `MissionExecutor` remains dry-run only. Do not connect real actuators
   during optical-link validation.
4. ROI, threshold, exposure and gain are local hardware calibration data and
   must not be committed.

### OK

1. Windows software baseline: vision repository 682 tests passed.
2. R2 cooperation package: 42 tests passed.
3. Four-light golden masks and UART CRC vectors have automated tests.
4. Old F407 `0xAA/0xBB/0xAB` and host `0xBC` protocols remain unchanged.
5. Cooperation features remain disabled or dry-run by default.

## Phase 0 - Safety and repository verification

Before power is applied:

- Lift drive wheels or isolate motor power.
- Keep arm, gripper and other dangerous actuators disabled.
- Use a current-limited supply.
- Use 3.3 V UART logic and a common ground.
- Never connect 24 V lamp power to an MCU GPIO or UART pin.
- Verify the external lamp driver polarity separately.

Checkout:

```bash
mkdir -p ~/rc
cd ~/rc

git clone https://github.com/JFCY2718/robocon_coop_comm.git
git clone https://github.com/JFCY2718/Rscontrol2.git
git clone https://github.com/JFCY2718/robstride_driver_r2.git

git -C robocon_coop_comm switch feature/four-light-optical
git -C Rscontrol2 switch feature/beacon-uart-v2
git -C robstride_driver_r2 switch feature/four-light-state-machine

git -C robocon_coop_comm pull --ff-only
git -C Rscontrol2 pull --ff-only
git -C robstride_driver_r2 pull --ff-only

git -C robocon_coop_comm rev-parse HEAD
git -C Rscontrol2 rev-parse HEAD
git -C robstride_driver_r2 rev-parse HEAD

git -C robocon_coop_comm merge-base --is-ancestor a2b0137f4d31f4c237e8d2c44b8849453d2106ee HEAD
git -C Rscontrol2 merge-base --is-ancestor 5eeb1e6918965edfb4714dd0d64a05b176da7e74 HEAD
git -C robstride_driver_r2 merge-base --is-ancestor ecf2f189f4a8444e93aae84e54deefd31bef39b0 HEAD

git -C robocon_coop_comm status -sb
git -C Rscontrol2 status -sb
git -C robstride_driver_r2 status -sb
```

If an existing checkout has local changes, preserve them and inspect the diff;
do not reset or overwrite them.

## Phase 1 - Ubuntu software baseline

Example packages for Ubuntu 22.04/24.04:

```bash
sudo apt update
sudo apt install -y git python3-venv python3-pip cmake ninja-build \
  gcc-arm-none-eabi binutils-arm-none-eabi openocd

cd ~/rc/robocon_coop_comm
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev,vision,apriltag]' pyserial

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q
python tools/hikrobot_6led_live.py --help
python tools/sixled_log_summary.py --help
python tools/sixled_expected_observed_check.py --help
python tools/send_beacon_uart_v2.py --help
python tools/send_beacon_uart_v2.py --dry-run --state INSERT_ALLOWED --count 1

cd ~/rc/robstride_driver_r2/el_a3_ros/robocon_coop_r2
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q
```

Expected baseline is 682 vision/cooperation tests and 42 R2 package tests.
Dependency or operating-system differences must be reported separately from
code failures.

## Phase 2 - Build the STM32F103 Beacon firmware

Keep build products outside the repository:

```bash
mkdir -p /tmp/robocon-beacon-build
cd ~/rc/robocon_coop_comm/firmware/stm32f103_beacon_baremetal

arm-none-eabi-gcc -mcpu=cortex-m3 -mthumb -Os -ffreestanding \
  -fdata-sections -ffunction-sections -nostdlib -nostartfiles \
  -Wl,--gc-sections -Wl,-T,stm32f103c8.ld \
  -Wl,-Map,/tmp/robocon-beacon-build/beacon.map \
  main.c -o /tmp/robocon-beacon-build/beacon.elf

arm-none-eabi-objcopy -O ihex \
  /tmp/robocon-beacon-build/beacon.elf \
  /tmp/robocon-beacon-build/beacon.hex

arm-none-eabi-size /tmp/robocon-beacon-build/beacon.elf
```

Before flashing, inspect the vector table and startup behavior. If `.bss` is not
reliably initialized, implement a minimal reset handler with tests/review before
continuing.

Flash only after confirming the exact board and SWD connection:

```bash
openocd -f interface/stlink.cfg -f target/stm32f1x.cfg \
  -c 'program /tmp/robocon-beacon-build/beacon.hex verify reset exit'
```

## Phase 3 - Direct PC-to-Beacon electrical validation

Use the Ubuntu PC/USB-UART first, without the F407:

```bash
cd ~/rc/robocon_coop_comm
source .venv/bin/activate
python -m serial.tools.list_ports

python tools/send_beacon_uart_v2.py \
  --port /dev/ttyUSB0 --state IDLE --count 20
python tools/send_beacon_uart_v2.py \
  --port /dev/ttyUSB0 --state PROTOCOL_TEST --count 20
```

Record:

- actual port name and USB-UART voltage;
- every ACK status and whether counter/state match;
- physical GPIO/lamp mask for states 0 and 15;
- all-off result within 300 ms after valid frames stop;
- behavior for bad CRC, bad version and state greater than 15.

Do not connect 24 V loads until six GPIO-level outputs and driver polarity have
been verified with a meter or logic analyzer.

## Phase 4 - Add V2 sequence and expected-log support

Extend `tools/send_beacon_uart_v2.py` minimally:

- accept an ordered state list, defaulting to 0 through 15 only when requested;
- hold each state for a configurable duration while refreshing at 50 ms;
- keep validating every ACK;
- write `start_ts`, `end_ts`, encoded `bitmask`, state value and label to an
  expected CSV compatible with `sixled_expected_observed_check.py`;
- add unit tests and CLI help tests;
- keep single-state behavior backward compatible.

Run the full 682-test suite again after this change. Commit only source, tests
and documentation; never commit the generated expected CSV.

## Phase 5 - Select and bind the F407 dedicated UART

This phase must stop for physical pin confirmation.

1. Inspect `Rscontrol2.ioc`, the controller schematic, connector pinout and all
   current GPIO/CAN/PWM/SWD assignments.
2. Produce a short candidate table: UART instance, TX pin, RX pin, alternate
   function, connector, voltage, and every detected conflict.
3. Exclude USART1, USART6, PA0 through PA5, PA13 and PA14.
4. Obtain explicit confirmation of the chosen pins.
5. Only then update CubeMX/startup UART initialization, interrupt handler and
   call `R1Coop_BindBeaconUart(&huartX)` after UART initialization.
6. Keep cooperation disabled by default until hardware checks pass.

Build outside the repository:

```bash
cmake -S ~/rc/Rscontrol2 -B /tmp/rscontrol2-build -G Ninja \
  -DCMAKE_BUILD_TYPE=Debug \
  -DCMAKE_TOOLCHAIN_FILE=~/rc/Rscontrol2/cmake/gcc-arm-none-eabi.cmake
cmake --build /tmp/rscontrol2-build
```

Review the diff to confirm the legacy `0xAA`, `0xBB`, `0xAB`, host `0xBC`, CAN,
chassis and arm paths did not change.

## Phase 6 - Hikrobot optical validation

Configure the vendor MVS SDK in each terminal:

```bash
export MVCAM_COMMON_RUNENV=/opt/MVS/lib
export PYTHONPATH=/opt/MVS/Samples/64/Python/MvImport:$PYTHONPATH
export LD_LIBRARY_PATH=/opt/MVS/lib/64:/opt/MVS/bin:$LD_LIBRARY_PATH
```

First confirm camera discovery and a stable image. Preserve fixed ROI as the
default. Calibrate in this exact order:

```text
D0, D1, D2, D3, REF, PAR
```

Example local calibration and observation commands:

```bash
cd ~/rc/robocon_coop_comm
source .venv/bin/activate

python tools/hikrobot_6led_live.py \
  --save-roi data/sixled/configs/breadboard_roi.json \
  --threshold 40 --exposure 12000 --gain 0 --timeout 5000

python tools/hikrobot_6led_live.py \
  --roi-file data/sixled/configs/breadboard_roi.json \
  --threshold 40 --exposure 12000 --gain 0 --timeout 5000 \
  --protocol --protocol-mode four-light \
  --log data/sixled/logs/four_light_observed.csv
```

Run the V2 sequence sender in a second terminal and then compare:

```bash
python tools/sixled_expected_observed_check.py \
  --expected data/sixled/logs/four_light_expected.csv \
  --observed data/sixled/logs/four_light_observed.csv \
  --settle-sec 0.5 --min-dominant-ratio 0.90 --min-valid-ratio 0.50
```

Required evidence:

- all 16 states match the golden masks;
- invalid REF and wrong PAR are rejected;
- valid-frame ratio and dominant-mask ratio per state;
- near/far, ambient-light and viewing-angle boundaries;
- communication loss enters invalid/HOLD instead of retaining a dangerous cue;
- logs and ROI remain local and uncommitted.

Test fixed ROI first. AprilTag dynamic ROI is a separate comparison and must
not replace or break fixed ROI.

## Phase 7 - R2 dry-run integration

Only after Phase 6 passes:

1. Feed real decoded `BeaconEvent` values into the R2 cooperation package.
2. Keep `MissionExecutor` dry-run and actuators disconnected.
3. Verify repeated persistent states do not retrigger actions.
4. Verify stale/invalid/low-confidence/parity-failed frames enter HOLD.
5. Verify ESTOP > ABORT > HOLD > ERROR > normal mission states.
6. Verify every action intent still requires real local R2 sensor guards.

Connecting `ActionIntent` to real ROS2 controllers, MoveIt, motors or the
gripper is a new safety-reviewed phase and is outside this handoff.

## Completion report

For every changed repository report:

```text
remote:
branch:
commit:
tag: none unless explicitly requested
push status:
modified files:
software tests:
firmware build:
hardware and wiring:
real ACK/watchdog result:
camera expected-vs-observed result:
artifact scan:
BLOCKER:
WARNING:
OK:
READY_FOR_R1_BEACON_R2_DRY_RUN = YES/NO
READY_FOR_DANGEROUS_ACTUATOR_CONNECTION = NO
```
