# Performance Benchmark

## 目的

量化操作手请求到 R2 状态响应的软件链路延迟。

## Benchmark 链路

```
OperatorCommand
  ↓
R1 FSM
  ↓
LedMcuClient
  ↓
LedMcuSimulator
  ↓
VirtualBeaconFrameProvider
  ↓
BeaconDecoder
  ↓
BeaconStabilizer
  ↓
R2 FSM
```

## 运行命令

```bash
python -m robocon_coop_comm.demo_benchmark --iterations 100
./tools/demo_benchmark_check.sh
make benchmark
```

## 输出指标

| 指标 | 说明 |
|------|------|
| `avg_ms` | 平均单次完整 pipeline 耗时 |
| `min_ms` | 最快一次 |
| `max_ms` | 最慢一次 |
| `p95_ms` | 95 百分位延迟 |
| `successful_iterations` | 成功完成的迭代次数 |

## 性能目标

| 场景 | 目标 |
|------|------|
| 软件仿真平均延迟 | < 20 ms |
| 真实 LED + 摄像头 + 稳定 3 帧后事件延迟 | < 200 ms |

## 说明

- 当前是纯软件 benchmark；
- 后续接真实串口、真实 MCU、真实摄像头后，应继续复用 `TraceRecorder`；
- 这是**测量**链路，不是**控制**链路；
- 这不是 R1/R2 无线通信。
