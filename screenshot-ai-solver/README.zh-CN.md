# Screenshot AI Solver — 截图 AI 解题器

按 **Shift+G** 截屏 → OCR 识别 → AI 答题 → 弹出答案。**一个 exe 搞定一切。**

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)
![License](https://img.shields.io/badge/License-MIT-green)

## ✨ 功能

- 🔥 **Shift+G** 一键截屏解题
- 🔍 RapidOCR 自动识别（中英文）
- 🤖 AI 自动解答（只输出答案，无废话）
- 🪟 白色现代风格 UI（clawd-on-desk 同款设计）
- 📋 一键复制答案
- 📜 答题历史（侧边栏内直接查看）
- ⚙ 侧边栏布局：主页 / Token 用量 / 历史 / 设置 / API 厂商
- 🔑 内置 12 家 API 厂商链接，帮用户找 Key
- 💰 自定义每日 Token 限额
- 🌍 中 / 英 / 日 三语
- 🖥️ 系统托盘支持

## 🚀 快速开始

### 下载即用（exe）

1. 下载 `ScreenshotAISolver.exe`
2. 双击运行 → 自动生成 `.env` 模板
3. 编辑 `.env`，填入 API Key
4. 重新打开 → 完成

### 源码运行

```bash
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env 填入 Key
python main.py
```

## ⚙ .env 配置

```env
# DeepSeek（推荐：便宜、国内直连）
SCREENSHOT_AI_API_KEY=sk-your-key
SCREENSHOT_AI_BASE_URL=https://api.deepseek.com
SCREENSHOT_AI_MODEL=deepseek-chat

# OpenAI
SCREENSHOT_AI_API_KEY=sk-your-key
SCREENSHOT_AI_BASE_URL=https://api.openai.com/v1
SCREENSHOT_AI_MODEL=gpt-4o
```

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `SCREENSHOT_AI_API_KEY` | API 密钥（必填） | - |
| `SCREENSHOT_AI_BASE_URL` | API 地址 | `https://api.openai.com/v1` |
| `SCREENSHOT_AI_MODEL` | 模型名 | `gpt-4o` |

## 🎮 操作

| 操作 | 方式 |
|------|------|
| 截图解题 | `Shift+G` |
| 复制答案 | 点击按钮或 `Ctrl+C` |
| 关闭弹窗 | `Esc` |
| 最小化到托盘 | 关闭主窗口 |

## 📄 许可

MIT License
