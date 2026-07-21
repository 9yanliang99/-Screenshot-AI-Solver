# Screenshot AI Solver

Press **Shift+G** to capture screen → OCR recognition → AI answer → popup. **One .exe, zero setup.**

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)
![License](https://img.shields.io/badge/License-MIT-green)

## ✨ Features

- 🔥 **Shift+G** one-key screenshot & solve
- 🔍 RapidOCR auto recognition (Chinese & English)
- 🤖 AI-powered answers (concise output, no fluff)
- 🪟 Modern light-themed UI 、
- 📋 One-click copy answer
- 📜 Answer history (inline in sidebar)
- ⚙ Sidebar layout: Home / Token / History / Settings / Providers
- 🔑 12 API provider links built in
- 💰 Customizable daily token limit
- 🌍 Chinese / English / Japanese
- 🖥️ System tray support

## 🚀 Quick Start

### Download & Run (exe)

1. Download `ScreenshotAISolver.exe`
2. Double-click → `.env` template auto-generated
3. Edit `.env`, paste your API key
4. Reopen → done

### From Source

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API key
python main.py
```

## ⚙ Configuration (.env)

```env
# DeepSeek (cheapest, China-friendly)
SCREENSHOT_AI_API_KEY=sk-your-key
SCREENSHOT_AI_BASE_URL=https://api.deepseek.com
SCREENSHOT_AI_MODEL=deepseek-chat

# OpenAI
SCREENSHOT_AI_API_KEY=sk-your-key
SCREENSHOT_AI_BASE_URL=https://api.openai.com/v1
SCREENSHOT_AI_MODEL=gpt-4o
```

| Variable | Description | Default |
|----------|-------------|---------|
| `SCREENSHOT_AI_API_KEY` | API Key (required) | - |
| `SCREENSHOT_AI_BASE_URL` | API Base URL | `https://api.openai.com/v1` |
| `SCREENSHOT_AI_MODEL` | Model name | `gpt-4o` |

## 🎮 Controls

| Action | How |
|--------|-----|
| Screenshot & Solve | `Shift+G` |
| Copy Answer | Click button or `Ctrl+C` |
| Close Popup | `Esc` |
| Minimize to Tray | Close main window |
