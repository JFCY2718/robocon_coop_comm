# CLAUDE.md

ROBOCON 2026「武林探秘」R1/R2 协作通信项目。

## 核心约束

1. 不实现 R1/R2 无线通信。
2. 武馆装配阶段不实现接触式通信。
3. 操作手指令不能直接控制 R2，不能直接点亮 LED。
4. 操作手指令必须通过 R1MissionFSM guard。
5. R2 将视觉消息视为事件线索，必须检查本地传感器后才行动。
6. 不得在真实相机 + STM32 日志验证之前宣称 M3 完成。
7. Mock/单元测试结果不是真实相机结果。
8. 视觉消息不能绕过本地安全条件。
9. FSM 输出只能是 ActionIntent（决策意图），不直接驱动硬件。

## 常用命令

```bash
source .venv/bin/activate
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q          # 556 tests
python -m robocon_coop_comm.demo_fsm_safety                     # FSM 安全仿真
python -m robocon_coop_comm.demo_cli                            # CLI 闭环演示
python tools/hikrobot_6led_live.py --help                       # 六灯实时工具
python tools/sixled_log_summary.py --help                       # 六灯日志分析
```

## FSM 优先级链

```text
ESTOP > ABORT > HOLD > ERROR > RETRY > normal mission event
```

## 关键文件

- `robocon_coop_comm/r1_fsm.py` — R1 任务状态机
- `robocon_coop_comm/r2_fsm.py` — R2 任务状态机（含 confidence/staleness guard）
- `robocon_coop_comm/beacon_types.py` — BeaconEvent, ActionIntent
- `test/test_r1_fsm.py` — R1 FSM 46 tests
- `test/test_r2_fsm.py` — R2 FSM 151 tests
- `docs/FSM_SAFETY_DESIGN.md` — FSM 安全设计
