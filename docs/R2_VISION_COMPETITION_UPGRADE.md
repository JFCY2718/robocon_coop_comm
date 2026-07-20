# R2 六灯视觉竞赛增强方案

## 结论

当前推荐方案是单台 Hikrobot 全局快门相机、`tag36h11` ID 0、六颗常亮 LED，
通过 AprilTag 投影动态 ROI，再做局部背景扣除、REF 相对阈值、时间门控。它延续现有
硬件和协议，不引入 YOLO、双相机或闪烁编码，部署风险最低。

软件侧已经实现：

- 中心 70 分位数与背景环 50 分位数采样，减小 ROI 偏移、反光和局部遮挡影响。
- 每路 LED 增益校准、阈值滞回、饱和检测和不确定通道标记。
- AprilTag 每两帧完整检测一次，中间帧使用 LK 光流；失败立即回退完整检测。
- 单槽异步取流，只处理最新帧，不积压旧图像。
- 普通状态 3/5 投票；`INSERT_ALLOWED` 和 `TOP_RELEASE_ALLOWED` 必须连续 5 帧。
- 视觉事件默认 300 ms 过期，仍须通过 R2MissionFSM 和本地传感器才能产生动作意图。
- 相机自动曝光、自动增益关闭，显式使用 Mono8 和单调时钟时间戳。

以上均已通过软件测试，但不等于真实相机、灯板或整机验收。

## 推荐结构

优先使用 320 x 240 mm 哑光黑色背板，配置文件为：
`data/sixled/configs/competition_beacon_320x240.json`。

| 项目 | 推荐值 |
|---|---:|
| AprilTag 黑色检测边长 | 150 mm |
| Tag 中心 | `(-55, 0)` mm |
| D0/D1/D2 | `(40,70) / (80,70) / (120,70)` mm |
| D3/REF/PAR | `(40,20) / (80,20) / (120,20)` mm |
| 灯帽直径 | 22.4 mm |
| ROI 半径 | 灯帽半径的 0.65 倍 |
| Tag 周围连续白色静区 | 至少 20 mm，避免线缆和高光侵入 |

六颗灯应使用相同型号、恒流或稳定限流、相同扩散罩，并加短遮光筒减少斜视串光。
协议物理顺序固定为 `D0,D1,D2,D3,REF,PAR`，不可交换。

## 一键运行

安装软件依赖并配置 Hikrobot MVS SDK 后运行：

```bash
python3 tools/hikrobot_6led_live.py \
  --competition \
  --beacon-layout data/sixled/configs/competition_beacon_320x240.json \
  --draw-tag --draw-dynamic-rois \
  --log data/sixled/logs/competition.csv
```

`--competition` 当前展开为以下关键设置：

```text
AprilTag auto ROI, 2 threads, full detection every 2 frames + optical flow
adaptive REF threshold + background ring + percentile sampling
12% hysteresis, 50% saturation ceiling
latest-frame buffer, 5-frame window, ordinary 3/5 vote
INSERT_ALLOWED and TOP_RELEASE_ALLOWED: 5 consecutive frames
exposure 5000 us, gain 0, camera timeout 100 ms, signal age 300 ms
```

5000 µs 只是首轮起点。应在不饱和的前提下逐步降低曝光，以运动时 Tag 角点和 LED
边缘不拖影为准。不要用自动曝光或自动增益完成最终验收。

## LED 增益标定

先逐路只点亮一颗灯，在相同距离和曝光下记录背景扣除后的亮度中位数。以 REF 为基准：

```text
gain_i = median(REF_on) / median(LED_i_on)
```

将实际值写入本地 JSON，格式参考
`data/sixled/configs/led_gains.example.json`，运行时追加：

```bash
--led-gains /path/to/measured_led_gains.json
```

若某路增益明显超出 0.7 到 1.4，优先检查 LED、限流电阻、扩散罩和接线，不要仅靠软件
放大补偿硬件缺陷。

## 你需要完成的实体工作

1. 制作并固定 320 x 240 mm 哑光背板；测量并记录 Tag 的真实黑边长度。
2. 固定相机支架、镜头焦距和光圈；确保最大工作距离下 Tag 黑边仍有足够像素。
3. 逐路核对 PA0 到 PA5 与 `D0,D1,D2,D3,REF,PAR` 的对应关系。
4. 完成六路亮度测量并生成实际 LED 增益文件。
5. 在 1 m、1.5 m、3 m 和实际最大距离，正视、±30°、±45°分别采集日志。
6. 自动遍历 16 个协议状态，每状态至少 100 次切换；保留 expected 和 observed 日志。
7. 执行 Tag 遮挡、REF 断开、PAR 错误、相机断开和快速运动测试。
8. 在电机与危险执行器断开的条件下，最后才接 R2MissionFSM 做 dry-run。

真实日志、现场图片、ROI 和测量增益默认保留本地，不提交到 Git。

## 建议验收门槛

| 项目 | 进入 R2 dry-run 的门槛 |
|---|---|
| 16 状态静态匹配 | 每个测试工况 gated match ≥ 99.5% |
| 危险状态误接受 | 0 次 |
| REF/PAR 故障 | 100% 输出 invalid |
| Tag 遮挡 | 下一处理帧 invalid，300 ms 后绝不继续使用旧事件 |
| 图像新鲜度 | capture age P95 ≤ 100 ms |
| 视觉处理时延 | P95 ≤ 150 ms |
| 最大距离 | raw valid ≥ 95%，gated match ≥ 99% |

若门槛未满足，按顺序排查曝光和焦点、反光/遮光、Tag 尺寸和静区、灯位几何、每路增益，
最后才调整阈值和投票参数。未完成这些实测前：

```text
READY_FOR_R2_VISION_DRY_RUN=NO
READY_FOR_DANGEROUS_ACTUATOR_CONNECTION=NO
```
