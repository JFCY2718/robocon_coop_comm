.PHONY: test demo-cli demo-cv demo-cli-check lint send-led-frame

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
