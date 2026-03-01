#!/usr/bin/env bash
set -e
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
echo "Virtualenv criado e dependências instaladas. Ative com: source .venv/bin/activate"
