# 2026_Jikken_3_Group2

Project1が最終結果で、Project2が正確度をより中心にしたシステムです。

以下のコードでProject1を立ち上げることができます。

ubuntuの場合、以下を実行して、環境が整えているかを確認します。

```
sudo apt update && sudo apt install -y julius sox libsox-fmt-all alsa-utils python3-venv python3-pip
```

Mac/ubuntuの実行

```
./run.sh
```

## Windows
実行の前、Python 3.10以上のバージョンやgit、SoXのインストールが必要になります。

### Pythonのインストール
まずPython install managerをダウンロードしてください。
次、Command Promptに以下のコードを実行してください。
```
py install 3.13
```

### SoXのインストール
Command Promptに以下のコードを実行してください。
```
winget install --id ChrisBagwell.SoX -e
```

インストールが終わったら、run.batを管理者モードで実行してください。
