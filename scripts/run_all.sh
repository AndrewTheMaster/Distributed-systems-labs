#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

mode="${1:-}"

echo "== build and tests =="
go build ./...
go test ./...

echo "== simulations =="
make sim

echo "== figures and tables =="
python3 scripts/analyze.py

if [ "$mode" = "--docker" ] || [ "$mode" = "--with-docker" ]; then
  echo "== docker (110 containers) =="
  make docker
  python3 scripts/analyze.py
fi

echo "== report =="
python3 scripts/build_report.py
