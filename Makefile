.PHONY: test demo-cli demo-cv demo-cli-check lint

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
