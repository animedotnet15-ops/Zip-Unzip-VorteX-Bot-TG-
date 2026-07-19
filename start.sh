#!/usr/bin/env bash
set -e
pip install -r requirements.txt --break-system-packages 2>/dev/null || pip install -r requirements.txt
python3 main.py
