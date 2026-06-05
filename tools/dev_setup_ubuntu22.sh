#!/usr/bin/env bash
set -euo pipefail

sudo apt update
sudo apt install -y python3 python3-venv python3-pip git

python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev,vision]"
pytest -q

echo "Development environment ready."
