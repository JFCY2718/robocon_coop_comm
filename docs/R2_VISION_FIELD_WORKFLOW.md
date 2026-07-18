# R2 Vision Field Workflow

## Purpose

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

## Frozen physical model

Front-view board coordinates use the board centre as `(0, 0)`, X right and Y
up. All values are millimetres.

| Item | Value |
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

## What the operator must do

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

## Copy-paste Ubuntu execution task

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

## Phase 0 - Repository and safety gate

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

## Phase 1 - Python and MVS environment

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

## Phase 2 - Fixed ROI baseline

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

| Key/action | Result |
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

## Phase 3 - AprilTag-only gate

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

## Phase 4 - Sixteen-state optical validation

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

## Phase 5 - Failure and safety validation

Test and record each condition separately:

| Test | Required result |
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

## Phase 6 - R2 dry-run integration

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

## Improvement path

Improve one layer at a time and keep fixed ROI as the comparison baseline.

### Stage A - Current deterministic baseline

- manual exposure and gain;
- fixed grayscale threshold;
- mean brightness inside a circular ROI;
- AprilTag detection on every frame;
- homography from the current tag corners;
- REF and parity rejection.

This is the easiest version to diagnose and must be measured before adding
complexity.

### Stage B - Illumination robustness

If on/off brightness bands overlap under ambient light, sample a background
ring around each lamp and classify using centre-minus-background contrast.
Add separate on/off thresholds with hysteresis. Keep the raw centre, background
and decision values in local logs so the change can be compared objectively.

### Stage C - Optical calibration

Capture real Hikrobot intrinsics and distortion coefficients. Undistort before
tag detection when lens distortion visibly shifts the projected lamp centres.
Pose estimation is optional; planar homography remains the state-decoding path.

### Stage D - Motion and performance

Measure tag detection latency before optimizing. If it is too slow, consider a
bounded tracker between full detections, but require periodic fresh tag
detections, reprojection-error gates and immediate invalidation on tracking
failure. Never treat an old ROI as actionable merely to preserve frame rate.

### Stage E - Deployment reliability

- select the Hikrobot camera by serial number instead of the first device;
- store exposure, gain, threshold and geometry in a local site configuration;
- add structured health output for camera, tag, ROI, protocol and freshness;
- add a dry-run ROS2 wrapper only after the standalone pipeline passes;
- keep a one-command fallback to fixed ROI for diagnosis.

## Completion evidence

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
