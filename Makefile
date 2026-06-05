.PHONY: test demo-cli demo-cv demo-cli-check lint send-led-frame demo-mcu demo-mcu-check demo-operator demo-operator-check demo-r2-vision demo-r2-vision-check demo-dojo demo-dojo-check benchmark benchmark-check test-all

test:
	./tools/test.sh

demo-cli:
	python -m robocon_coop_comm.demo_cli

demo-cv:
	python -m robocon_coop_comm.demo_cv

demo-cli-check:
	./tools/demo_cli_check.sh

lint:
	ruff check .

send-led-frame:
	python tools/send_led_frame.py --msg-id 4 --seq 1 --brightness 200

demo-mcu:
	python -m robocon_coop_comm.demo_mcu_pipeline

demo-mcu-check:
	./tools/demo_mcu_pipeline_check.sh

demo-operator:
	python -m robocon_coop_comm.demo_operator_pipeline

demo-operator-check:
	./tools/demo_operator_pipeline_check.sh

demo-r2-vision:
	python -m robocon_coop_comm.demo_r2_vision_pipeline

demo-r2-vision-check:
	./tools/demo_r2_vision_pipeline_check.sh

demo-dojo:
	python -m robocon_coop_comm.demo_dojo_end_to_end

demo-dojo-check:
	./tools/demo_dojo_end_to_end_check.sh

benchmark:
	python -m robocon_coop_comm.demo_benchmark --iterations 100

benchmark-check:
	./tools/demo_benchmark_check.sh

test-all: test demo-cli-check demo-mcu-check demo-operator-check demo-r2-vision-check demo-dojo-check benchmark-check
