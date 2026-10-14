#!/bin/bash
# macOS 双击运行：改完 source/ 下的真源（cards.md / rules.md / new-rule.md / props.md / original/*）后跑一次，首页和打印页就都更新了
cd "$(dirname "$0")" || exit 1

PY="$(command -v python3)"
if [ -z "$PY" ]; then
  PY="/Users/alpha/.workbuddy/binaries/python/versions/3.13.12/bin/python3"
fi

"$PY" tools/build.py
echo ""
read -n 1 -s -r -p "按任意键关闭…"
echo ""
