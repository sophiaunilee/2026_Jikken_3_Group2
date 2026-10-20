#!/bin/bash

# mac の場合 (brew 前提)
# dialogue-demo に追加で必要な ASR / TTS ツールを導入
# 前提: Homebrew, SoX, LIBSVM は setup-mac.sh で導入済み
brew install julius
brew install open-jtalk
brew install nkf