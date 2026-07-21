# Screenshot AI Solver — スクリーンショット AI ソルバー

**Shift+G** で画面キャプチャ → OCR 認識 → AI 解答 → ポップアップ。**exe 一つで完結。**

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)
![License](https://img.shields.io/badge/License-MIT-green)

## ✨ 機能

- 🔥 **Shift+G** ワンキーで解答
- 🔍 RapidOCR 自動認識（中国語・英語）
- 🤖 AI 解答（簡潔出力、余計な説明なし）
- 🪟 モダンなライトテーマ UI
- 📋 ワンクリックで回答をコピー
- 📜 解答履歴（サイドバー内で閲覧）
- ⚙ サイドバー：ホーム / トークン / 履歴 / 設定 / プロバイダ
- 🔑 12 社の API プロバイダリンク内蔵
- 💰 日次トークン制限をカスタマイズ可能
- 🌍 中国語 / 英語 / 日本語
- 🖥️ システムトレイ対応

## 🚀 クイックスタート

### ダウンロード＆実行（exe）

1. `ScreenshotAISolver.exe` をダウンロード
2. ダブルクリック → `.env` テンプレート自動作成
3. `.env` を編集し API キーを入力
4. 再起動 → 完了

### ソースから実行

```bash
pip install -r requirements.txt
cp .env.example .env
# .env を編集して API キーを設定
python main.py
```

## ⚙ 設定 (.env)

```env
# DeepSeek（最安、中国から直結）
SCREENSHOT_AI_API_KEY=sk-your-key
SCREENSHOT_AI_BASE_URL=https://api.deepseek.com
SCREENSHOT_AI_MODEL=deepseek-chat

# OpenAI
SCREENSHOT_AI_API_KEY=sk-your-key
SCREENSHOT_AI_BASE_URL=https://api.openai.com/v1
SCREENSHOT_AI_MODEL=gpt-4o
```

| 変数 | 説明 | デフォルト |
|------|------|-----------|
| `SCREENSHOT_AI_API_KEY` | API キー（必須） | - |
| `SCREENSHOT_AI_BASE_URL` | API URL | `https://api.openai.com/v1` |
| `SCREENSHOT_AI_MODEL` | モデル名 | `gpt-4o` |

## 🎮 操作

| 操作 | 方法 |
|------|------|
| 解答 | `Shift+G` |
| 回答をコピー | ボタンクリック または `Ctrl+C` |
| 閉じる | `Esc` |
| トレイに最小化 | メインウィンドウを閉じる |
