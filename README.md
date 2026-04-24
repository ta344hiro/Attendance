# Attendance

Ubuntu タブレット上での利用を想定した、IC カード式の出退勤管理アプリです。  
Flet による全画面 UI をベースに、カードリーダーによる出勤・退勤記録、音声案内、Mattermost 通知、気温表示、雨雲レーダー表示を一体化しています。

研究室・職場内での常設運用を想定して作成しており、実際の運用環境での使用を前提に改善を重ねています。  
カード読み取り、CSV 記録、音声案内、気象情報表示をまとめて扱えるようにし、利用者が迷わず操作できることを重視しました。

## 主な機能

- IC カードの UID を読み取り、出勤 (`IN`) / 退勤 (`OUT`) を記録
- 出退勤ログをアプリ上で閲覧可能
- 出退勤ログをローカルに保存
- 出退勤時に日本語音声で案内
- 退勤時、直近 1 時間の雨予報に応じて傘の持ち出しを案内
- Mattermost への出退勤通知
- 画面上に現在時刻・日付・気温・雨雲レーダーを表示
- 雨雲レーダーのズーム切り替え
- 読み取り待機中のキャンセル

## 想定利用環境

- Ubuntu 実機
- Python 3.10 以上
- FeliCa / PC/SC 対応カードリーダー
- Open JTalk による日本語音声再生が可能な環境

## 使用技術

- Python
- Flet
- pyscard
- requests
- Pillow
- Open JTalk
- PC/SC (`pcscd`)
- Mattermost Incoming Webhook
- 気象庁 Nowcast / AMeDAS

## セットアップ

### 1. リポジトリの取得

```bash
git clone git@github.com:ta344hiro/Attendance.git
cd Attendance
```

### 2. システムパッケージのインストール

```bash
sudo apt update
sudo apt install -y \
  python3 python3-pip python3-venv \
  open-jtalk open-jtalk-mecab-naist-jdic \
  alsa-utils \
  pcscd pcsc-tools libccid libpcsclite-dev \
  python3-dev swig unzip
```

### 3. Open JTalk 用音声ファイルの配置

このアプリでは Open JTalk の音声ファイルとして以下を使用します。

- `/usr/share/hts-voice/mei/mei_normal.htsvoice`

`open_jtalk` 本体と辞書だけではこの音声ファイルは入らないため、別途配置してください。

```bash
cd /tmp
wget https://sourceforge.net/projects/mmdagent/files/MMDAgent_Example/MMDAgent_Example-1.8/MMDAgent_Example-1.8.zip/download -O MMDAgent_Example-1.8.zip
unzip MMDAgent_Example-1.8.zip

sudo mkdir -p /usr/share/hts-voice
sudo cp -r /tmp/MMDAgent_Example-1.8/Voice/mei /usr/share/hts-voice/
```

配置確認:

```bash
ls /usr/share/hts-voice/mei/mei_normal.htsvoice
ls /var/lib/mecab/dic/open-jtalk/naist-jdic
```

### 4. Python パッケージのインストール

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 5. 動作確認

Python 依存が揃っているか確認します。

```bash
python3 -c "import flet, requests, PIL, smartcard; print('ok')"
```

音声の単体確認:

```bash
echo "こんにちは" > /tmp/test.txt
open_jtalk \
  -x /var/lib/mecab/dic/open-jtalk/naist-jdic \
  -m /usr/share/hts-voice/mei/mei_normal.htsvoice \
  -ow /tmp/test.wav \
  /tmp/test.txt
aplay /tmp/test.wav
```

カードリーダー確認:

```bash
systemctl status pcscd --no-pager
pcsc_scan
```

## 設定

### Mattermost 通知

Mattermost の Incoming Webhook URL を設定してください。  
公開リポジトリに秘密情報を含めないため、Webhook URL はローカル環境でのみ設定する運用を推奨します。

例:

```bash
echo 'export MATTERMOST_WEBHOOK_URL="実際のWebhook URL"' >> ~/.bashrc
source ~/.bashrc
```

### カード ID とユーザー名の対応

カード UID とユーザー名の対応表は、公開リポジトリに直接含めず、ローカル専用設定として管理することを推奨します。

例:

- `config.py` は公開用の設定を保持
- `config_local.py` はローカル専用設定として保持
- `config_local.py` は `.gitignore` に追加し、Git 管理対象外にする
- 実名・実カード ID を公開リポジトリに含めない
- 未登録カードはアプリ上で `未登録ユーザー` として扱う

## 起動方法

```bash
source .venv/bin/activate
python3 app.py
```

## ログ保存先

出退勤ログはローカルに保存され、アプリ上の「ログを見る」ボタンから閲覧できます。

保存ファイル:

- `logs/attendance.csv`
- `logs/last_tap.txt`

`attendance.csv` には以下の情報を保存します。

- 日時 (`timestamp`)
- ユーザー名 (`user_name`)
- 区分 (`action`)

未登録カードの場合、ユーザー名は `未登録ユーザー` として記録されます。

## ディレクトリ構成

```text
.
├── app.py
├── attendance_announcer.py
├── attendance_service.py
├── card_reader.py
├── config.py
├── handlers.py
│   ├── attendance.csv
│   └── last_tap.txt
├── mattermost.py
├── nowcast_renderer.py
├── state.py
├── tasks.py
├── ui.py
├── ui_types.py
├── voice.py
├── weather_service.py
├── requirements.txt
└── README.md
```

## 画面概要

- 左側
  - タイトル
  - 現在の状態表示
  - 出勤 / 退勤ボタン
  - キャンセルボタン
  - ログを見るボタン
  - 現在時刻・日付・気温
- 右側
  - 雨雲レーダー
  - ズーム切り替え

## 工夫した点

- 出退勤記録だけでなく、利用者が迷わないように音声案内と画面状態表示を組み合わせたこと
- 退勤時に雨予報を確認し、傘の持ち出しを促すようにしたこと
- 研究室・職場内での共有を想定し、Mattermost へ通知できるようにしたこと
- タブレット常設運用を意識し、全画面表示のシンプルな UI にしたこと
- CSV を内部保存に用いつつ、アプリ上でログを閲覧できるようにしたこと

## 注意事項

- 本アプリは Ubuntu 実機での運用を前提としています。
- Open JTalk の音声ファイルは別途配置が必要です。
- カード UID、Webhook URL、ユーザー情報などの機密情報は公開リポジトリに含めないでください。
- ログファイルは `logs/` 配下にローカル保存されるため、Git 管理対象に含めないでください。
- カードリーダーや音声出力の動作確認は、実運用端末で行うことを推奨します。
