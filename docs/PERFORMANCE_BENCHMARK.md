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
# 基本 benchmark（1 次 warmup + 100 次测量）
python -m robocon_coop_comm.demo_benchmark --iterations 100 --warmup-iterations 1

# 导出 Chrome Trace JSON
python -m robocon_coop_comm.demo_benchmark --iterations 20 --warmup-iterations 1 --trace-out /tmp/robocon_trace.json

# Makefile 快捷方式
make benchmark
make benchmark-trace
```

## 输出指标

### 冷启动 vs 热启动

| 指标 | 说明 |
|------|------|
| `cold_start_ms` | 首次 warmup 运行耗时（含 import、类初始化等冷启动开销） |
| `warm_avg_ms` | 正式测量阶段平均耗时（排除 warmup） |
| `warm_min_ms` | 正式测量阶段最短耗时 |
| `warm_max_ms` | 正式测量阶段最长耗时 |
| `warm_p95_ms` | 正式测量阶段 95 百分位延迟 |

### 兼容字段

| 指标 | 说明 |
|------|------|
| `avg_ms` | 正式测量平均耗时（同 warm_avg_ms） |
| `min_ms` | 正式测量最短耗时 |
| `max_ms` | 正式测量最长耗时 |
| `p95_ms` | 正式测量 95 百分位延迟 |
| `successful_iterations` | 正式测量成功次数 |

### warmup_iterations 的作用

- 首次运行 Python 时，import 和类初始化有较大冷启动开销；
- warmup 不计入正式统计，避免拉高 p95；
- `cold_start_ms` 记录首次 warmup 耗时，用于对比冷启动与稳态延迟。

## Chrome Trace 导出

```bash
python -m robocon_coop_comm.demo_benchmark --iterations 20 --warmup-iterations 1 --trace-out /tmp/robocon_trace.json
```

查看方法：
- Chrome 浏览器打开 `chrome://tracing`，Load 按钮加载 JSON 文件；
- 或使用 [Perfetto UI](https://ui.perfetto.dev/)。

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
