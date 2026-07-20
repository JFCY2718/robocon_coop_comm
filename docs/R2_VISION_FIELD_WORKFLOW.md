# R2视觉现场工作流 / R2 Vision Field Workflow

本指南采用中英双语说明。命令块由两种语言共用，避免因重复命令产生差异。

This guide is bilingual. Command blocks are shared by both languages to avoid
differences between duplicated commands.

## 目的 / Purpose

本指南用于搭建R2光通信视觉链路，指导系统从手动固定ROI逐步升级到AprilTag
自动定位和六灯解码，同时保持固定物理bit顺序，并禁止视觉结果直接驱动执行器。

This is the operator and execution guide for the R2 camera side of the optical
link. It takes the system from a manually selected fixed ROI to automatic
AprilTag location and six-lamp decoding without changing the physical bit order
or allowing vision to drive an actuator directly.

The intended chain is:

```text
Hikrobot frame
  -> AprilTag ID 0 detection
  -> planar homography
  -> D0/D1/D2/D3/REF/PAR projected ROIs
  -> grayscale sampling
  -> REF/parity validation
  -> state 0..15
  -> temporal stability and freshness gates
  -> BeaconEvent
  -> R2MissionFSM plus local sensors
  -> dry-run ActionIntent
```

Fixed ROI remains the first hardware baseline and the default operating mode.
AprilTag mode is enabled explicitly only after the baseline passes.

## 固定物理模型 / Frozen physical model

板正面坐标系以板中心为`(0,0)`，X向右、Y向上，所有尺寸单位均为毫米。

Front-view board coordinates use the board centre as `(0, 0)`, X right and Y
up. All values are millimetres.

| 项目 / Item | 数值 / Value |
|---|---|
| Board face | 280 x 220 |
| AprilTag family and ID | tag36h11, ID 0 |
| AprilTag detection edge | 150 |
| AprilTag centre | (-55, 0) |
| D0, D1, D2 | (40,70), (80,70), (120,70) |
| D3, REF, PAR | (40,20), (80,20), (120,20) |
| Lamp face diameter | 22.40 |
| Default sampling radius | 7.28 |

The 150 mm value must be the black outer edge returned by AprilTag detection.
If it includes a white print border, measure the black edge and pass the real
value to `--tag-size`. The assumed physical layout is:

```text
top:    D0   D1   D2
bottom: D3   REF  PAR
```

The electrical mapping must match this layout and the fixed bit order before
protocol validation begins.

150 mm必须对应AprilTag检测返回的黑色外边缘。如果150 mm包含白色打印边框，必须
测量真实黑边，并通过`--tag-size`填写。开始协议验证前，实际接线必须与上面的布局
及固定bit顺序一致。

## 操作者必须完成的工作 / What the operator must do

以下操作必须由能够接触实物的人员完成：

1. 连接并给Hikrobot相机供电。
2. 安装适用于实际相机型号和Linux架构的MVS SDK。
3. 视觉验证期间断开电机、机械臂和夹爪的危险动力。
4. 按图纸尺寸安装AprilTag和六个指示灯。
5. 确认150 mm是被检测的黑色Tag边长。
6. 选择真实串口，并在发送前确认3.3 V UART和共地接线。
7. 人工观察ROI位置、曝光、眩光、焦点和信号丢失行为。
8. ROI文件、现场图片和日志只保留本地，不提交Git。

The operator is responsible for actions that require physical access:

1. Connect and power the Hikrobot camera.
2. Install the MVS SDK supplied for the actual camera and Linux architecture.
3. Keep motors, arm and gripper power isolated during vision validation.
4. Mount the tag and lamps using the drawing dimensions.
5. Confirm that 150 mm is the detected black tag edge.
6. Select the real serial device and confirm 3.3 V UART wiring before sending.
7. Observe ROI placement, exposure, glare, focus and loss behavior.
8. Keep ROI files, captured frames and logs local and uncommitted.

Software checks, help output, dry-runs, log analysis and repository audits may
be automated. Physical observations must be recorded by the operator and must
not be inferred from mock or replay output.

软件测试、帮助输出、dry-run、日志分析和仓库审计可以自动执行；实物观察结果必须
由操作者记录，不能根据mock或回放结果推断。

## 最短执行路径 / Quick start

1. 在Ubuntu中进入`~/rc/robocon_coop_comm`，切换并`ff-only`更新
   `feature/four-light-optical`。
2. 阅读本文件与`UBUNTU_HARDWARE_HANDOFF.md`，复制下一节的中文或英文执行任务。
3. 让执行会话自动完成仓库、Python、pytest、ruff、CLI和MVS环境检查。
4. 你连接Hikrobot相机、隔离危险执行器，并观察固定ROI基准。
5. 固定ROI稳定后切换AprilTag模式，确认六个动态圆始终落在对应灯面内部。
6. 连接已验证的Beacon串口，发送0到15状态，完成expected-vs-observed和故障测试。
7. 仅在以上实测通过后进入R2 dry-run；真实执行器仍保持断开。

1. On Ubuntu, enter `~/rc/robocon_coop_comm`, switch to
   `feature/four-light-optical`, and update it with `ff-only`.
2. Read this file and `UBUNTU_HARDWARE_HANDOFF.md`, then copy either execution
   task from the next section.
3. Let the execution session complete repository, Python, pytest, ruff, CLI and
   MVS environment checks.
4. Connect the Hikrobot camera, isolate dangerous actuators, and observe the
   fixed-ROI baseline.
5. After fixed ROI is stable, enable AprilTag mode and verify that every
   projected circle remains inside its assigned lamp face.
6. Connect the electrically validated Beacon serial link, send states 0 through
   15, and complete expected-vs-observed and failure tests.
7. Enter R2 dry-run only after those hardware tests pass; keep real actuators
   disconnected.

## 可复制的Ubuntu执行任务 / Copy-paste Ubuntu execution task

### 中文版本 / Chinese version

Copy the text below into a new Ubuntu execution session from the directory that
contains the three repositories:

```text
你现在执行 ROBOCON R2 视觉链路的 Ubuntu 实机验证。

先读取：
1. robocon_coop_comm/docs/UBUNTU_HARDWARE_HANDOFF.md
2. robocon_coop_comm/docs/R2_VISION_FIELD_WORKFLOW.md
3. 三个仓库各自的 docs/PROJECT_RULES.md、docs/ENGINEERING_REVIEW.md 和
   docs/TASK_TEMPLATES.md（存在时）。

先只检查，不修改：
- remote、branch、HEAD、tag、working tree；
- robocon_coop_comm 必须位于 feature/four-light-optical；
- Rscontrol2 必须位于 feature/beacon-uart-v2；
- robstride_driver_r2 必须位于 feature/four-light-state-machine；
- 保存现有未提交修改，不 reset、不覆盖；
- 只允许 ff-only 更新；
- 不 force push、不修改 main、不创建或移动 tag。

然后自动完成能在软件中完成的项目：
1. 建立或复用 Python 虚拟环境，安装 dev、vision、apriltag 和 pyserial 依赖；
2. 运行完整 pytest、ruff 和相关 CLI --help；
3. 检查 MVS SDK 环境、AprilTag依赖和相机枚举；
4. 先执行固定ROI模式，再执行AprilTag动态ROI模式；
5. 每一步输出实际命令、返回码和 BLOCKER/WARNING/OK；
6. 缺少相机、串口、接线、SDK或人工观察时必须停在对应步骤并明确请求操作；
7. 不得把mock、dry-run、离线图片或单元测试写成实机通过。

视觉验证顺序必须是：
固定ROI基准 -> Tag单独检测 -> 动态ROI覆盖 -> 16状态expected-vs-observed
-> 遮挡/掉线/错误REF/错误PAR -> R2 dry-run状态机。

固定顺序保持 D0,D1,D2,D3,REF,PAR。不得修改旧0xAA/0xBB/0xAB协议、
Rscontrol2 0xBC帧、F407 PA0到PA5映射或危险动作安全边界。

不要提交真实logs、frames、ROI、build、elf、bin、hex、map、o。
视觉结果只能形成BeaconEvent并经过稳定性、新鲜度、R2MissionFSM和本地传感器，
不得直接控制电机、机械臂或夹爪。

完成后报告：
- 三个仓库branch、HEAD和push状态；
- 固定ROI结果；
- AprilTag距离、角度、decision margin和动态ROI结果；
- 16状态匹配率、valid ratio、dominant ratio；
- Tag遮挡、REF错误、PAR错误、相机掉线和300ms超时结果；
- 本地未提交数据路径；
- BLOCKER/WARNING/OK；
- READY_FOR_R2_VISION_DRY_RUN=YES/NO；
- READY_FOR_DANGEROUS_ACTUATOR_CONNECTION=NO。

没有明确的软件缺陷时不要修改代码。若发现缺陷，只在个人功能分支进行最小修改，
运行完整测试后普通push；不要创建PR或影响其他仓库的main。
```

### English version / 英文版本

Copy this version when an English execution task is preferred:

```text
Perform the Ubuntu hardware validation of the ROBOCON R2 vision link.

Read first:
1. robocon_coop_comm/docs/UBUNTU_HARDWARE_HANDOFF.md
2. robocon_coop_comm/docs/R2_VISION_FIELD_WORKFLOW.md
3. docs/PROJECT_RULES.md, docs/ENGINEERING_REVIEW.md and docs/TASK_TEMPLATES.md
   in each repository when those files exist.

Inspect before modifying anything:
- remote, branch, HEAD, tags and working tree;
- robocon_coop_comm must use feature/four-light-optical;
- Rscontrol2 must use feature/beacon-uart-v2;
- robstride_driver_r2 must use feature/four-light-state-machine;
- preserve every existing uncommitted change; do not reset or overwrite it;
- permit only ff-only updates;
- do not force push, rewrite main, or create, move or delete tags.

Automatically complete everything that can be verified in software:
1. Create or reuse the Python environment and install dev, vision, apriltag and
   pyserial dependencies.
2. Run the full pytest suite, ruff and the relevant CLI help commands.
3. Check the MVS SDK environment, AprilTag dependency and camera enumeration.
4. Run fixed ROI mode before AprilTag dynamic ROI mode.
5. Report the exact command, exit status and BLOCKER/WARNING/OK at every step.
6. Stop and request the physical operation when a camera, serial device,
   wiring, SDK or visual observation is required.
7. Never report mocks, dry-runs, offline images or unit tests as hardware
   acceptance.

Use this validation order:
fixed ROI baseline -> tag-only detection -> dynamic ROI overlay -> 16-state
expected-vs-observed -> occlusion/disconnect/bad REF/bad PAR -> R2 dry-run FSM.

Keep the physical order D0,D1,D2,D3,REF,PAR. Do not modify the old
0xAA/0xBB/0xAB protocols, the Rscontrol2 0xBC frame, the F407 PA0 through PA5
mapping, or any dangerous-action safety boundary.

Do not commit real logs, frames, ROI files, build directories, elf, bin, hex,
map or object files. Vision may only produce BeaconEvent data that passes
stability, freshness, R2MissionFSM and local-sensor guards. It must never
directly control a motor, arm or gripper.

Report on completion:
- branch, HEAD and push status for all three repositories;
- fixed ROI result;
- AprilTag distances, angles, decision margins and dynamic ROI result;
- 16-state match rate, valid ratio and dominant ratio;
- tag occlusion, bad REF, bad PAR, camera disconnect and 300 ms timeout result;
- local uncommitted data paths;
- BLOCKER/WARNING/OK;
- READY_FOR_R2_VISION_DRY_RUN=YES/NO;
- READY_FOR_DANGEROUS_ACTUATOR_CONNECTION=NO.

Do not modify code unless there is a specific software defect. If a defect is
found, make the smallest change on the personal feature branch, run the full
test suite, and use a normal push. Do not open a pull request or affect another
repository's main branch.
```

## 阶段0：仓库与安全门 / Phase 0 - Repository and safety gate

先确认三个仓库的状态和功能分支。若存在无法解释的修改，停止并保留现场，不要reset。
机器人上电前必须隔离危险执行器，并确认相机测试不会发布硬件动作命令。

```bash
cd ~/rc

git -C robocon_coop_comm status -sb
git -C Rscontrol2 status -sb
git -C robstride_driver_r2 status -sb

git -C robocon_coop_comm switch feature/four-light-optical
git -C Rscontrol2 switch feature/beacon-uart-v2
git -C robstride_driver_r2 switch feature/four-light-state-machine

git -C robocon_coop_comm pull --ff-only
git -C Rscontrol2 pull --ff-only
git -C robstride_driver_r2 pull --ff-only
```

Stop if any working tree contains changes that are not understood. Preserve and
report them. Before powering the robot, isolate all dangerous actuators and
confirm that the camera test cannot publish hardware commands.

## 阶段1：Python与MVS环境 / Phase 1 - Python and MVS environment

建立独立Python环境、配置MVS动态库并完成软件基线。此阶段的通过只代表软件环境
正常，不代表相机和光通信实机验收通过。

```bash
cd ~/rc/robocon_coop_comm
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev,vision,apriltag]' pyserial

export MVCAM_COMMON_RUNENV=/opt/MVS/lib
export PYTHONPATH=/opt/MVS/Samples/64/Python/MvImport:$PYTHONPATH
export LD_LIBRARY_PATH=/opt/MVS/lib/64:/opt/MVS/bin:$LD_LIBRARY_PATH

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q
python -m ruff check .
python tools/hikrobot_6led_live.py --help
python tools/sixled_log_summary.py --help
python tools/sixled_expected_observed_check.py --help
python tools/send_beacon_uart_v2.py --help
python -m serial.tools.list_ports
```

The current camera provider selects the first enumerated Hikrobot device. If
more than one camera is connected, disconnect the unused cameras for this
validation or record a software improvement request for selection by serial
number. Do not assume which camera index was opened.

当前相机提供器会选择枚举到的第一台Hikrobot相机。如果连接了多台相机，应断开
无关设备完成本轮验证，或记录“按序列号选择相机”的软件改进任务，不能猜测打开了
哪一台相机。

## 阶段2：固定ROI基准 / Phase 2 - Fixed ROI baseline

固定ROI用于在不引入AprilTag几何的情况下验证采图、灯位顺序、曝光和阈值。若固定
ROI仍不稳定，不得继续动态ROI。

The fixed path proves camera acquisition, lamp order, exposure and threshold
without involving AprilTag geometry.

Calibrate by clicking exactly `D0,D1,D2,D3,REF,PAR`:

```bash
mkdir -p data/sixled/configs data/sixled/logs data/sixled/frames

python tools/hikrobot_6led_live.py \
  --roi-mode fixed \
  --save-roi data/sixled/configs/site_roi.json \
  --threshold 60 --exposure 8000 --gain 0 --timeout 5000 \
  --protocol --protocol-mode four-light
```

Window controls:

| 按键或动作 / Key or action | 结果 / Result |
|---|---|
| Left click | Add next LED centre in fixed order |
| `r` | Clear and select all six centres again |
| `s` | Save the six selected centres |
| `+` / `-` | Raise/lower threshold by five |
| `q` | Exit |

Run the saved baseline:

```bash
python tools/hikrobot_6led_live.py \
  --roi-mode fixed \
  --roi-file data/sixled/configs/site_roi.json \
  --threshold 60 --exposure 8000 --gain 0 --timeout 5000 \
  --protocol --protocol-mode four-light \
  --log data/sixled/logs/fixed_observed.csv
```

Required observations:

- every ROI is centred inside its lamp face;
- off and on brightness bands do not overlap at the chosen threshold;
- REF and parity failures are rejected;
- masks use the fixed physical order;
- exposure and gain stay manual and repeatable.

Do not continue to dynamic ROI if the fixed baseline is unstable.

必须观察：每个ROI位于灯面内部；亮灭亮度区间能够被阈值分开；REF和PAR错误被
拒绝；mask顺序正确；曝光和增益保持手动、可重复。

## 阶段3：AprilTag单独验证 / Phase 3 - AprilTag-only gate

先用一张离线现场图片检查Tag检测和投影圆位置，再打开实时相机。离线图片只能用于
诊断，不能作为实机连续运行验收。

First use an offline frame to inspect tag detection and projected circles
without opening the MVS SDK:

```bash
python tools/hikrobot_6led_live.py \
  --image /tmp/beacon_frame.png \
  --roi-mode apriltag \
  --tag-family tag36h11 --tag-id 0 --tag-size 0.150 \
  --tag-min-margin 30 --tag-max-hamming 0 \
  --roi-radius-scale 0.65 \
  --draw-tag --draw-dynamic-rois \
  --output-image /tmp/beacon_projection.png
```

Then run live detection:

```bash
python tools/hikrobot_6led_live.py \
  --roi-mode apriltag \
  --tag-family tag36h11 --tag-id 0 --tag-size 0.150 \
  --tag-min-margin 30 --tag-max-hamming 0 \
  --roi-radius-scale 0.65 --tag-lost-frames 5 \
  --threshold 60 --exposure 8000 --gain 0 --timeout 5000 \
  --draw-tag --draw-dynamic-rois \
  --protocol --protocol-mode four-light \
  --log data/sixled/logs/apriltag_observed.csv
```

No clicking is used in AprilTag mode. The six circular ROIs are calculated
from the detected tag corners and the frozen board dimensions. Verify at 1 m,
3 m and the expected maximum distance, then add translation, yaw and pitch.
Record tag pixel width, decision margin, frame latency and every invalid reason.

Cover the tag. The current frame must become invalid immediately. Old circles
may remain for at most five frames for drawing only; they are never actionable.

AprilTag模式不需要鼠标点击。六个圆形ROI根据当前Tag角点和固定板尺寸自动计算。
需要在1 m、3 m、预期最远距离及不同平移、偏航、俯仰角下记录Tag像素宽度、
decision margin、帧延迟和invalid reason。遮挡Tag时当前帧必须立即无效；旧圆最多
保留五帧仅供显示，永远不能作为有效事件。

## 阶段4：十六状态光通信验证 / Phase 4 - Sixteen-state optical validation

PC直连Beacon的电气验证通过后，在第二终端发送0到15的真实状态序列，并比较固定
ROI和AprilTag模式的观测结果。

Run the real V2 sender in a second terminal after the PC-to-Beacon electrical
test has passed:

```bash
cd ~/rc/robocon_coop_comm
source .venv/bin/activate

python tools/send_beacon_uart_v2.py \
  --port /dev/ttyUSB0 \
  --states 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15 \
  --hold-sec 3 --refresh-sec 0.05 \
  --expected-log /tmp/four_light_expected.csv
```

Compare the expected windows with the fixed and AprilTag observations:

```bash
python tools/sixled_expected_observed_check.py \
  --expected /tmp/four_light_expected.csv \
  --observed data/sixled/logs/apriltag_observed.csv \
  --settle-sec 0.5 \
  --min-dominant-ratio 0.90 \
  --min-valid-ratio 0.50
```

The listed ratios are an initial diagnostic gate, not the final competition
target. Preserve the per-state results and increase the target after the first
repeatable hardware dataset. Never commit the CSV files.

文档中的ratio阈值只是第一轮诊断门槛，不是最终比赛指标。取得第一组可重复数据后
再提高验收目标。真实CSV永远不提交Git。

## 阶段5：故障与安全验证 / Phase 5 - Failure and safety validation

每个故障条件必须单独测试并记录，不能只看画面上的ROI覆盖框。

Test and record each condition separately:

| 测试 / Test | 必须结果 / Required result |
|---|---|
| Tag covered or wrong ID | current vision result invalid |
| Tag margin below gate | invalid, no projected state accepted |
| REF off | `reference_off`, no state accepted |
| Incorrect PAR | `parity_error`, no state accepted |
| ROI outside image | invalid, not clamped to an unrelated region |
| Camera disconnected | no retained actionable state |
| Valid frames stop | HOLD/loss handling within the configured freshness limit |
| Persistent state repeats | no duplicate one-shot action |
| Low confidence or stale timestamp | rejected by R2 safety layer |

The 300 ms Beacon watchdog is an electrical output requirement. Measure the R2
vision freshness limit separately and configure it no longer than the value
approved for the mission safety design. A debug overlay is never evidence that
an event was accepted by the state machine.

300 ms Beacon看门狗是电气输出要求。R2视觉新鲜度必须单独测量，并配置为不超过
任务安全设计批准的数值。调试覆盖框不代表状态机已经接受了事件。

## 阶段6：R2 dry-run集成 / Phase 6 - R2 dry-run integration

只有固定ROI和AprilTag模式都通过十六状态实测后，才能接入R2 dry-run状态机：

Only after fixed ROI and AprilTag mode both pass the 16-state run:

1. Convert a valid four-light decode to `DecodedBeacon`.
2. Require consecutive consistent frames before accepting a change.
3. Add a monotonic capture timestamp and create `BeaconEvent`.
4. Apply validity, confidence and freshness gates.
5. Pass the event to `R2MissionFSM` together with real local R2 sensors.
6. Publish only dry-run `ActionIntent` output.
7. Keep motors, arm, gripper, MoveIt and real ROS2 actions disconnected.

Connecting intents to dangerous actuators is a separate safety-reviewed phase
and is not authorized by this workflow.

ActionIntent连接真实执行器属于单独的安全审查阶段，本工作流不授权该操作。

## 改进路线 / Improvement path

每次只改进一层，并始终保留固定ROI作为对照基准。

Improve one layer at a time and keep fixed ROI as the comparison baseline.

### 阶段A：当前确定性基准 / Stage A - Current deterministic baseline

当前方案使用手动曝光/增益、固定灰度阈值、圆形ROI均值、每帧AprilTag检测、
单应性投影及REF/PAR校验。它最容易诊断，应先完成测量再增加复杂度。

- manual exposure and gain;
- fixed grayscale threshold;
- mean brightness inside a circular ROI;
- AprilTag detection on every frame;
- homography from the current tag corners;
- REF and parity rejection.

This is the easiest version to diagnose and must be measured before adding
complexity.

### 阶段B：环境光鲁棒性 / Stage B - Illumination robustness

如果环境光导致亮灭区间重叠，改用“灯中心亮度减背景环亮度”的局部对比度，并增加
开灯/关灯双阈值和滞回。现场日志应保存中心值、背景值和判定值以便客观比较。

If on/off brightness bands overlap under ambient light, sample a background
ring around each lamp and classify using centre-minus-background contrast.
Add separate on/off thresholds with hysteresis. Keep the raw centre, background
and decision values in local logs so the change can be compared objectively.

### 阶段C：光学校准 / Stage C - Optical calibration

采集真实Hikrobot内参与畸变参数。当镜头畸变明显移动投影灯心时，在Tag检测前进行
去畸变。姿态估计为可选功能，状态解码仍以平面单应性为主。

Capture real Hikrobot intrinsics and distortion coefficients. Undistort before
tag detection when lens distortion visibly shifts the projected lamp centres.
Pose estimation is optional; planar homography remains the state-decoding path.

### 阶段D：运动与性能 / Stage D - Motion and performance

优化前先测量Tag检测延迟。若性能不足，可以在完整检测之间增加受限跟踪，但必须
周期性重新检测Tag、检查重投影误差，并在跟踪失败时立即失效；不能为保持帧率而继续
使用旧ROI作为有效输入。

Measure tag detection latency before optimizing. If it is too slow, consider a
bounded tracker between full detections, but require periodic fresh tag
detections, reprojection-error gates and immediate invalidation on tracking
failure. Never treat an old ROI as actionable merely to preserve frame rate.

### 阶段E：部署可靠性 / Stage E - Deployment reliability

部署阶段应增加按相机序列号选择、相机/Tag/ROI/协议/新鲜度健康状态、仅本地保存的
现场配置，以及固定ROI一键回退。独立链路通过前不增加真实动作连接。

- select the Hikrobot camera by serial number instead of the first device;
- store exposure, gain, threshold and geometry in a local site configuration;
- add structured health output for camera, tag, ROI, protocol and freshness;
- add a dry-run ROS2 wrapper only after the standalone pipeline passes;
- keep a one-command fallback to fixed ROI for diagnosis.

## 完成证据 / Completion evidence

填写以下中英通用报告字段，真实数据只保留本地：

Record the following without committing real data:

```text
camera model and serial:
MVS SDK version:
image width/height and frame rate:
exposure/gain/threshold:
measured black tag edge:
test distances and angles:
decision-margin range:
fixed ROI result:
AprilTag ROI result:
per-state valid/dominant ratios:
tag-loss result:
REF/PAR rejection result:
camera-disconnect result:
freshness/HOLD timing:
R2 dry-run result:
local log and frame paths:
BLOCKER:
WARNING:
OK:
READY_FOR_R2_VISION_DRY_RUN = YES/NO
READY_FOR_DANGEROUS_ACTUATOR_CONNECTION = NO
```
