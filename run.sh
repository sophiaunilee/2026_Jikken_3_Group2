#!/bin/bash
# ルートフォルダ (2026_Jikken_3_Group2) からでもそのまま起動できるようにするラッパースクリプト
cd "$(dirname "$0")/project1" || exit 1
exec ./run.sh
