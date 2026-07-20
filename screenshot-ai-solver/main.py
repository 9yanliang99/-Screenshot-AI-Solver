#!/usr/bin/env python3
"""
Screenshot AI Solver — 截图 AI 解题器
==========================================
Press Shift+G to capture → OCR extract text → AI answer → popup window

First run auto-downloads RapidOCR ONNX model (~20MB, one-time only).
API key configured via .env file or environment variables.

Usage:
    python main.py
"""

import os
import sys
import json
import socket
import threading
import logging
from pathlib import Path
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

# ── Windows DPI awareness (fix blurry UI on high-res displays) ──────
if sys.platform == "win32":
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(2)  # PerMonitorV2
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# ── Core dependencies ──────────────────────────────────────────────
import tempfile
import numpy as np
from PIL import Image, ImageGrab, ImageEnhance
from rapidocr_onnxruntime import RapidOCR
from openai import OpenAI
from pynput import keyboard
from dotenv import load_dotenv

# ── GUI ───────────────────────────────────────────────────────────
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

# ── System tray ────────────────────────────────────────────────────
try:
    import pystray
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False

# ── Logging ────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ScreenshotAI")


# ╔══════════════════════════════════════════════════════════════════╗
# ║                 I18N Translation Dictionary                     ║
# ╚══════════════════════════════════════════════════════════════════╝

I18N = {
    "zh": {
        # Welcome dialog
        "welcome.title": "🌍 欢迎",
        "welcome.question": "你来自哪里？",
        "welcome.desc": "这将决定界面语言和 OCR 模型下载源。\n之后可在设置中更改。",
        "welcome.china": "🇨🇳 中国 (China)",
        "welcome.us": "🇺🇸 United States",
        "welcome.uk": "🇬🇧 United Kingdom",
        "welcome.other": "🌍 其他地区 (Other Regions)",
        "welcome.japan": "🇯🇵 日本 (Japan)",

        # Indicator
        "indicator.ready": "Shift+G 待命",
        "indicator.loading_ocr": "加载OCR模型...",
        "indicator.preloading": "预加载OCR模型...",
        "indicator.select_region": "框选题目区域...",
        "indicator.model_failed": "模型加载失败，点击重试",

        # Answer window
        "answer.title": "🤖 AI 解答",
        "answer.recognized_text": "📷 识别到的文字",
        "answer.ai_answer": "💡 AI 解答",
        "answer.copy": "📋 复制答案",
        "answer.copied": "✅ 已复制!",
        "answer.close": "关闭 (Esc)",
        "answer.no_text": "(未识别到文字)",
        "answer.no_text_title": "⚠️ 未在选中区域识别到任何文字",
        "answer.no_text_body": (
            "可能的原因：\n"
            "  • 选中区域没有文字内容\n"
            "  • 文字太小或对比度太低\n"
            "  • 建议重新框选题目区域"
        ),

        # Settings
        "settings.title": "⚙ 设置",
        "settings.api_settings": "API 设置",
        "settings.base_url": "Base URL:",
        "settings.model": "Model:",
        "settings.api_key": "API Key:",
        "settings.not_set": "(未设置)",
        "settings.save": "💾 保存",
        "settings.saved": "配置已保存！",
        "settings.language": "语言 (Language):",

        # History
        "history.title": "📜 答题历史",
        "history.header": "📜 最近 20 条答题记录",
        "history.no_records": "(暂无记录)",
        "history.close": "关闭",

        # Region selector
        "region.hint": "拖拽框选题目区域  |  Esc 取消",

        # Dashboard
        "dashboard.title": "📊 Token 用量看板 — Screenshot AI Solver",
        "dashboard.today_usage": "今日用量",
        "dashboard.remaining": "剩余额度",
        "dashboard.daily_limit": "每日限额",
        "dashboard.usage_pct": "使用率",
        "dashboard.chart_title": "近 30 天 Token 用量趋势",
        "dashboard.chart_label": "Token 用量",
        "dashboard.chart_limit": "每日限额",
        "dashboard.empty": "暂无数据，去答几道题吧！",
        "dashboard.refresh_hint": "数据实时更新，每次答题后自动刷新",

        # Right-click menu
        "menu.dashboard": "📊 Token 用量",
        "menu.settings": "⚙ 设置",
        "menu.history": "📜 查看历史",
        "menu.home": "🏠 主页",
        "menu.providers": "🔑 API 厂商",
        "menu.exit": "❌ 退出",

        # Error / status
        "error.no_key_title": "未设置 API 密钥！",
        "error.no_key_detail": (
            "未设置 API 密钥！\n\n"
            "请通过以下任一方式设置:\n"
            "  1. 环境变量: export SCREENSHOT_AI_API_KEY=your-key\n"
            "  2. 在 .env 文件中写入:\n"
            "     SCREENSHOT_AI_API_KEY=your-key\n"
            "  3. 右键点击浮动指示器 → 设置 → 填入 API Key"
        ),
        "error.processing_detail": (
            "❌ 处理出错: {error}\n\n"
            "请检查:\n"
            "  • API 密钥是否正确设置\n"
            "  • 网络连接是否正常\n"
            "  • API Base URL 是否正确"
        ),

        # System prompt for AI
        "system_prompt": (
            "你是解题助手。用户提供屏幕上OCR识别出的题目文字。\n"
            "规则：\n"
            "- 直接给出最终答案，不要写解题步骤或分析过程\n"
            "- 选择题只输出正确选项字母\n"
            "- 数学题只输出最终数值或表达式\n"
            "- 简答题用一句话回答\n"
            "- 无题目则回复「无题目」\n"
            "用中文回答。"
        ),

        # Log messages
        "log.preloading": "后台预加载 RapidOCR 模型...",
        "log.ocr_loaded": "RapidOCR 模型加载完成",
        "log.preload_done": "OCR 模型预加载完成，可以随时解题",
        "log.preload_failed": "预加载失败: {error}",
        "log.hf_mirror": "检测到中国用户，使用 HF 镜像加速模型下载...",
        "log.screenshot": "📸 截图中...",
        "log.resized": "  图片缩放: {size} (加速OCR)",
        "log.screenshot_done": "  截图完成: {size}",
        "log.ocr_scanning": "🔍 OCR 识别中...",
        "log.ocr_no_text": "  未识别到任何文字",
        "log.ocr_result": "  识别到 {lines} 段文字, 共 {chars} 字符, 耗时 {time:.2f}s",
        "log.ocr_preview": "  内容预览: {preview}...",
        "log.ai_calling": "🤖 调用 AI API...",
        "log.ai_done": "  AI 回答: {chars} 字符",
        "log.hotkey": "🔥 热键 Shift+G 触发！",
        "log.skipped": "⏭ 上一轮尚未完成，跳过本次触发",
        "log.cancelled": "🚫 用户取消框选",
        "log.region_selected": "📐 选中区域: ({x1},{y1})-({x2},{y2}), 大小 {w}x{h}",
        "log.loading_ocr_model": "正在加载 RapidOCR 模型 (首次运行会自动下载 ONNX 模型，约 20MB)...",
        "log.api_configured": "✅ API 配置: {url} / {model}",
        "log.listening": "🎧 开始监听键盘... 按 Shift+G 截图解题",
        "log.quitting": "👋 正在退出...",
        "log.no_api_warning1": "⚠️  未设置 API 密钥！程序可以启动但无法答题。",
        "log.no_api_warning2": "   右键点击浮动指示器 → 设置 → 填入 API Key",
        "log.no_api_warning3": "   或编辑 .env 文件",
        "log.config_loaded": "📄 配置已从 {path} 加载 (语言: {lang})",

        # Token usage
        "token.limit_title": "💧 今日额度已用完",
        "token.limit_detail": (
            "今日 Token 额度已用完。\n\n"
            "已用: {used:,} tokens\n"
            "每日限额: {limit:,} tokens\n\n"
            "额度将在明天自动重置。\n"
            "可通过环境变量 SCREENSHOT_AI_DAILY_TOKEN_LIMIT 调整限额。"
        ),

        # Main window
        "main.api_configured": "API 密钥已配置",
        "main.api_not_configured": "API 密钥未配置",
        "main.api_placeholder": "输入 API 密钥...",
        "main.quick_actions": "快捷操作",
        "main.screenshot_solve": "截图解题 (Shift+G)",
        "main.view_dashboard": "查看完整看板",
        "main.status_model": "模型: {model}",
        "main.status_url": "接口: {url}",
        "main.status_language": "语言: {lang}",

        # Banner
        "banner": r"""
   _____                _                    _    ___   _____      _
  / ____|              | |                  | |  / _ \ |_   _|    (_)
 | (___   ___ _ __ ___ | |__   ___ _ __ ___ | |_| | | |  | | _ __  _
  \___ \ / __| '__/ _ \| '_ \ / _ \ '__/ _ \| __| | | |  | || '__|| |
  ____) | (__| | | (_) | |_) |  __/ | | (_) | |_| |_| | _| || |   | |
 |_____/ \___|_|  \___/|_.__/ \___|_|  \___/ \__|\___(_)___|_|   |_|

        截图 AI 解题器 v1.0  |  Shift+G 开始解题  |  右键浮动窗设置
""",
    },

    "en": {
        # Welcome dialog
        "welcome.title": "🌍 Welcome",
        "welcome.question": "Where are you from?",
        "welcome.desc": "This determines the interface language and OCR model download source.\nYou can change this later in Settings.",
        "welcome.china": "🇨🇳 中国 (China)",
        "welcome.us": "🇺🇸 United States",
        "welcome.uk": "🇬🇧 United Kingdom",
        "welcome.other": "🌍 Other Regions",
        "welcome.japan": "🇯🇵 日本 (Japan)",

        # Indicator
        "indicator.ready": "Shift+G Ready",
        "indicator.loading_ocr": "Loading OCR...",
        "indicator.preloading": "Preloading OCR...",
        "indicator.select_region": "Select question area...",
        "indicator.model_failed": "Model load failed, retry",

        # Answer window
        "answer.title": "🤖 AI Answer",
        "answer.recognized_text": "📷 Recognized Text",
        "answer.ai_answer": "💡 AI Answer",
        "answer.copy": "📋 Copy Answer",
        "answer.copied": "✅ Copied!",
        "answer.close": "Close (Esc)",
        "answer.no_text": "(No text recognized)",
        "answer.no_text_title": "⚠️ No text recognized in the selected area",
        "answer.no_text_body": (
            "Possible reasons:\n"
            "  • No text content in the selected area\n"
            "  • Text too small or low contrast\n"
            "  • Try reselecting the question area"
        ),

        # Settings
        "settings.title": "⚙ Settings",
        "settings.api_settings": "API Settings",
        "settings.base_url": "Base URL:",
        "settings.model": "Model:",
        "settings.api_key": "API Key:",
        "settings.not_set": "(Not set)",
        "settings.save": "💾 Save",
        "settings.saved": "Configuration saved!",
        "settings.language": "Language:",

        # History
        "history.title": "📜 Answer History",
        "history.header": "📜 Last 20 Answer Records",
        "history.no_records": "(No records yet)",
        "history.close": "Close",

        # Region selector
        "region.hint": "Drag to select question area  |  Esc to cancel",

        # Dashboard
        "dashboard.title": "📊 Token Usage Dashboard — Screenshot AI Solver",
        "dashboard.today_usage": "Today's Usage",
        "dashboard.remaining": "Remaining",
        "dashboard.daily_limit": "Daily Limit",
        "dashboard.usage_pct": "Usage Rate",
        "dashboard.chart_title": "Token Usage Trend (Last 30 Days)",
        "dashboard.chart_label": "Token Usage",
        "dashboard.chart_limit": "Daily Limit",
        "dashboard.empty": "No data yet. Go solve some questions!",
        "dashboard.refresh_hint": "Data updates in real-time after each answer.",

        # Right-click menu
        "menu.dashboard": "📊 Token Usage",
        "menu.settings": "⚙ Settings",
        "menu.history": "📜 History",
        "menu.home": "🏠 Home",
        "menu.providers": "🔑 API Providers",
        "menu.exit": "❌ Exit",

        # Error / status
        "error.no_key_title": "API Key Not Set!",
        "error.no_key_detail": (
            "API key not set!\n\n"
            "Please set it via one of:\n"
            "  1. Environment variable: export SCREENSHOT_AI_API_KEY=your-key\n"
            "  2. In the .env file:\n"
            "     SCREENSHOT_AI_API_KEY=your-key\n"
            "  3. Right-click indicator → Settings → Enter API Key"
        ),
        "error.processing_detail": (
            "❌ Error: {error}\n\n"
            "Please check:\n"
            "  • API key is correctly set\n"
            "  • Network connection is working\n"
            "  • API Base URL is correct"
        ),

        # System prompt for AI
        "system_prompt": (
            "You are a problem solver. The user provides OCR-extracted text from a screenshot.\n"
            "Rules:\n"
            "- Output ONLY the final answer — no steps, no analysis, no explanation\n"
            "- Multiple choice: output only the correct option letter\n"
            "- Math: output only the final number/expression\n"
            "- Short answer: one sentence max\n"
            "- If no question found, reply \"No question\"\n"
            "Answer in English."
        ),

        # Log messages
        "log.preloading": "Preloading RapidOCR model in background...",
        "log.ocr_loaded": "RapidOCR model loaded successfully",
        "log.preload_done": "OCR model preloaded, ready for use",
        "log.preload_failed": "Preload failed: {error}",
        "log.hf_mirror": "China region detected, using HF mirror for faster model download...",
        "log.screenshot": "📸 Taking screenshot...",
        "log.resized": "  Image resized: {size} (for faster OCR)",
        "log.screenshot_done": "  Screenshot done: {size}",
        "log.ocr_scanning": "🔍 Running OCR...",
        "log.ocr_no_text": "  No text recognized",
        "log.ocr_result": "  Recognized {lines} text blocks, {chars} chars total, took {time:.2f}s",
        "log.ocr_preview": "  Content preview: {preview}...",
        "log.ai_calling": "🤖 Calling AI API...",
        "log.ai_done": "  AI response: {chars} chars",
        "log.hotkey": "🔥 Hotkey Shift+G triggered!",
        "log.skipped": "⏭ Previous round not finished, skipping",
        "log.cancelled": "🚫 User cancelled selection",
        "log.region_selected": "📐 Selected region: ({x1},{y1})-({x2},{y2}), size {w}x{h}",
        "log.loading_ocr_model": "Loading RapidOCR model (first run auto-downloads ONNX model, ~20MB)...",
        "log.api_configured": "✅ API config: {url} / {model}",
        "log.listening": "🎧 Listening for keyboard... Press Shift+G to solve",
        "log.quitting": "👋 Quitting...",
        "log.no_api_warning1": "⚠️  API key not set! App can start but cannot answer questions.",
        "log.no_api_warning2": "   Right-click indicator → Settings → Enter API Key",
        "log.no_api_warning3": "   Or edit the .env file",
        "log.config_loaded": "📄 Config loaded from {path} (language: {lang})",

        # Token usage
        "token.limit_title": "💧 Daily Limit Reached",
        "token.limit_detail": (
            "Daily token limit reached.\n\n"
            "Used: {used:,} tokens\n"
            "Daily limit: {limit:,} tokens\n\n"
            "The limit will reset tomorrow.\n"
            "Adjust via env var SCREENSHOT_AI_DAILY_TOKEN_LIMIT."
        ),

        # Main window
        "main.api_configured": "API Key Configured",
        "main.api_not_configured": "API Key Not Configured",
        "main.api_placeholder": "Enter your API key...",
        "main.quick_actions": "Quick Actions",
        "main.screenshot_solve": "Screenshot Solve (Shift+G)",
        "main.view_dashboard": "View Full Dashboard",
        "main.status_model": "Model: {model}",
        "main.status_url": "Base URL: {url}",
        "main.status_language": "Language: {lang}",

        # Banner
        "banner": r"""
   _____                _                    _    ___   _____      _
  / ____|              | |                  | |  / _ \ |_   _|    (_)
 | (___   ___ _ __ ___ | |__   ___ _ __ ___ | |_| | | |  | | _ __  _
  \___ \ / __| '__/ _ \| '_ \ / _ \ '__/ _ \| __| | | |  | || '__|| |
  ____) | (__| | | (_) | |_) |  __/ | | (_) | |_| |_| | _| || |   | |
 |_____/ \___|_|  \___/|_.__/ \___|_|  \___/ \__|\___(_)___|_|   |_|

        Screenshot AI Solver v1.0  |  Shift+G to solve  |  Right-click for settings
""",
    },

    "ja": {
        # Welcome dialog
        "welcome.title": "🌍 ようこそ",
        "welcome.question": "お住まいの地域は？",
        "welcome.desc": "インターフェース言語とOCRモデルのダウンロード元を決定します。\n後で設定から変更できます。",
        "welcome.china": "🇨🇳 中国 (China)",
        "welcome.us": "🇺🇸 United States",
        "welcome.uk": "🇬🇧 United Kingdom",
        "welcome.japan": "🇯🇵 日本 (Japan)",
        "welcome.other": "🌍 その他の地域 (Other Regions)",

        # Indicator
        "indicator.ready": "Shift+G 待機中",
        "indicator.loading_ocr": "OCRモデル読み込み中...",
        "indicator.preloading": "OCRモデル事前読込中...",
        "indicator.select_region": "問題領域を選択...",
        "indicator.model_failed": "モデル読込失敗、クリックで再試行",

        # Answer window
        "answer.title": "🤖 AI 解答",
        "answer.recognized_text": "📷 認識されたテキスト",
        "answer.ai_answer": "💡 AI 解答",
        "answer.copy": "📋 回答をコピー",
        "answer.copied": "✅ コピーしました！",
        "answer.close": "閉じる (Esc)",
        "answer.no_text": "(テキストが認識されませんでした)",
        "answer.no_text_title": "⚠️ 選択領域にテキストが認識されませんでした",
        "answer.no_text_body": (
            "考えられる原因：\n"
            "  • 選択領域にテキストが含まれていない\n"
            "  • テキストが小さすぎる、またはコントラストが低い\n"
            "  • 問題領域を選択し直してください"
        ),

        # Settings
        "settings.title": "⚙ 設定",
        "settings.api_settings": "API 設定",
        "settings.base_url": "Base URL:",
        "settings.model": "Model:",
        "settings.api_key": "API Key:",
        "settings.not_set": "(未設定)",
        "settings.save": "💾 保存",
        "settings.saved": "設定を保存しました！",
        "settings.language": "言語 (Language):",

        # History
        "history.title": "📜 解答履歴",
        "history.header": "📜 最近20件の解答記録",
        "history.no_records": "(記録がありません)",
        "history.close": "閉じる",

        # Region selector
        "region.hint": "ドラッグで問題領域を選択  |  Esc でキャンセル",

        # Dashboard
        "dashboard.title": "📊 トークン使用量ダッシュボード — Screenshot AI Solver",
        "dashboard.today_usage": "今日の使用量",
        "dashboard.remaining": "残り",
        "dashboard.daily_limit": "1日の制限",
        "dashboard.usage_pct": "使用率",
        "dashboard.chart_title": "トークン使用量推移（過去30日間）",
        "dashboard.chart_label": "トークン使用量",
        "dashboard.chart_limit": "1日の制限",
        "dashboard.empty": "データがありません。問題を解いてみましょう！",
        "dashboard.refresh_hint": "データは解答後に自動更新されます。",

        # Right-click menu
        "menu.dashboard": "📊 トークン使用量",
        "menu.settings": "⚙ 設定",
        "menu.history": "📜 履歴を見る",
        "menu.home": "🏠 ホーム",
        "menu.providers": "🔑 API プロバイダ",
        "menu.exit": "❌ 終了",

        # Error / status
        "error.no_key_title": "APIキーが未設定です！",
        "error.no_key_detail": (
            "APIキーが未設定です！\n\n"
            "以下のいずれかの方法で設定してください:\n"
            "  1. 環境変数: export SCREENSHOT_AI_API_KEY=your-key\n"
            "  2. .env ファイルに記述:\n"
            "     SCREENSHOT_AI_API_KEY=your-key\n"
            "  3. フローティングインジケーターを右クリック → 設定 → APIキーを入力"
        ),
        "error.processing_detail": (
            "❌ エラー: {error}\n\n"
            "以下を確認してください:\n"
            "  • APIキーが正しく設定されているか\n"
            "  • ネットワーク接続が正常か\n"
            "  • API Base URL が正しいか"
        ),

        # System prompt for AI
        "system_prompt": (
            "あなたは解答アシスタントです。ユーザーはスクリーンショットからOCRで抽出された"
            "テキストを提供します。\n"
            "ルール：\n"
            "- 最終的な答えだけを出力し、解答手順や分析は一切書かない\n"
            "- 選択問題は正解の選択肢の文字だけを出力\n"
            "- 数学問題は最終的な数値や式だけを出力\n"
            "- 短文問題は一言で回答\n"
            "- 問題がない場合は「問題なし」と返信\n"
            "日本語で回答してください。"
        ),

        # Log messages
        "log.preloading": "RapidOCRモデルをバックグラウンドで事前読込中...",
        "log.ocr_loaded": "RapidOCRモデルの読み込みが完了しました",
        "log.preload_done": "OCRモデルの事前読込が完了しました。いつでも解答できます",
        "log.preload_failed": "事前読込に失敗しました: {error}",
        "log.hf_mirror": "中国地域を検出しました。HFミラーを使用してモデルをダウンロードします...",
        "log.screenshot": "📸 スクリーンショット撮影中...",
        "log.resized": "  画像をリサイズしました: {size} (OCR高速化)",
        "log.screenshot_done": "  スクリーンショット完了: {size}",
        "log.ocr_scanning": "🔍 OCR処理中...",
        "log.ocr_no_text": "  テキストが認識されませんでした",
        "log.ocr_result": "  {lines}ブロックのテキストを認識、合計{chars}文字、所要時間{time:.2f}秒",
        "log.ocr_preview": "  内容プレビュー: {preview}...",
        "log.ai_calling": "🤖 AI APIを呼び出し中...",
        "log.ai_done": "  AI回答: {chars}文字",
        "log.hotkey": "🔥 ホットキー Shift+G が押されました！",
        "log.skipped": "⏭ 前回の処理が完了していないため、スキップしました",
        "log.cancelled": "🚫 ユーザーが選択をキャンセルしました",
        "log.region_selected": "📐 選択領域: ({x1},{y1})-({x2},{y2}), サイズ {w}x{h}",
        "log.loading_ocr_model": "RapidOCRモデルを読み込み中 (初回実行時はONNXモデルを自動ダウンロード、約20MB)...",
        "log.api_configured": "✅ API設定: {url} / {model}",
        "log.listening": "🎧 キーボード待機中... Shift+Gでスクリーンショット解答",
        "log.quitting": "👋 終了中...",
        "log.no_api_warning1": "⚠️  APIキーが設定されていません！アプリは起動できますが解答できません。",
        "log.no_api_warning2": "   フローティングインジケーターを右クリック → 設定 → APIキーを入力",
        "log.no_api_warning3": "   または .env ファイルを編集",
        "log.config_loaded": "📄 設定を {path} から読み込みました (言語: {lang})",

        # Token usage
        "token.limit_title": "💧 本日の制限に達しました",
        "token.limit_detail": (
            "本日のトークン制限に達しました。\n\n"
            "使用済み: {used:,} トークン\n"
            "1日の制限: {limit:,} トークン\n\n"
            "制限は明日自動的にリセットされます。\n"
            "環境変数 SCREENSHOT_AI_DAILY_TOKEN_LIMIT で制限を調整できます。"
        ),

        # Main window
        "main.api_configured": "APIキー設定済み",
        "main.api_not_configured": "APIキー未設定",
        "main.api_placeholder": "APIキーを入力...",
        "main.quick_actions": "クイック操作",
        "main.screenshot_solve": "スクリーンショット解答 (Shift+G)",
        "main.view_dashboard": "ダッシュボードを開く",
        "main.status_model": "モデル: {model}",
        "main.status_url": "URL: {url}",
        "main.status_language": "言語: {lang}",

        # Banner
        "banner": r"""
   _____                _                    _    ___   _____      _
  / ____|              | |                  | |  / _ \ |_   _|    (_)
 | (___   ___ _ __ ___ | |__   ___ _ __ ___ | |_| | | |  | | _ __  _
  \___ \ / __| '__/ _ \| '_ \ / _ \ '__/ _ \| __| | | |  | || '__|| |
  ____) | (__| | | (_) | |_) |  __/ | | (_) | |_| |_| | _| || |   | |
 |_____/ \___|_|  \___/|_.__/ \___|_|  \___/ \__|\___(_)___|_|   |_|

        Screenshot AI Solver v1.0  |  Shift+Gで解答  |  右クリックで設定
""",
    },
}


# ╔══════════════════════════════════════════════════════════════════╗
# ║                    Configuration Manager                        ║
# ╚══════════════════════════════════════════════════════════════════╝


class Config:
    """Unified configuration manager.

    Load priority: environment variables > .env file > config.json file
    """

    CONFIG_DIR = Path.home() / ".screenshot-ai-solver"
    CONFIG_FILE = CONFIG_DIR / "config.json"

    DEFAULTS = {
        "api_base_url": "https://api.openai.com/v1",
        "model": "gpt-4o",
        "ocr_lang": "ch",  # ch=Chinese, en=English
        "max_image_width": 1920,
        "system_prompt": (
            "你是解题助手。用户提供屏幕上OCR识别出的题目文字。\n"
            "规则：\n"
            "- 直接给出最终答案，不要写解题步骤或分析过程\n"
            "- 选择题只输出正确选项字母\n"
            "- 数学题只输出最终数值或表达式\n"
            "- 简答题用一句话回答\n"
            "- 无题目则回复「无题目」\n"
            "用中文回答。"
        ),
        "api_timeout": 30,
        "daily_token_limit": 1_000_000,
        "language": "",  # "" = not yet chosen → show welcome dialog
        "use_hf_mirror": False,
    }

    def __init__(self):
        self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        # 1) Load from config.json (non-sensitive config)
        self.data = dict(self.DEFAULTS)
        if self.CONFIG_FILE.exists():
            try:
                with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
                    self.data.update(json.load(f))
            except json.JSONDecodeError:
                log.warning("config.json format error, using defaults")

        # 2) Load from .env file (won't override existing env vars)
        # When frozen (PyInstaller exe), look next to the exe, not __file__
        if getattr(sys, "frozen", False):
            self.app_dir = Path(sys.executable).parent
        else:
            self.app_dir = Path(__file__).parent
        env_file = self.app_dir / ".env"
        env_loaded = False

        # If .env doesn't exist but we have a bundled .env.example, copy it out
        if not env_file.exists() and getattr(sys, "frozen", False):
            bundled = Path(sys._MEIPASS) / ".env.example"
            if bundled.exists():
                try:
                    import shutil
                    shutil.copy(bundled, env_file)
                except Exception:
                    pass

        if env_file.exists():
            load_dotenv(str(env_file))
            env_loaded = True
        else:
            cwd_env = Path.cwd() / ".env"
            if cwd_env.exists():
                load_dotenv(str(cwd_env))
                env_loaded = True

        # Manually parse .env as fallback (PyInstaller + load_dotenv can be flaky)
        if not env_loaded or not os.environ.get("SCREENSHOT_AI_API_KEY"):
            for candidate in (self.app_dir / ".env", Path.cwd() / ".env"):
                try:
                    if candidate.exists():
                        for line in candidate.read_text(encoding="utf-8").splitlines():
                            line = line.strip()
                            if line and not line.startswith("#") and "=" in line:
                                k, v = line.split("=", 1)
                                k, v = k.strip(), v.strip().strip('"').strip("'")
                                if k and v and k not in os.environ:
                                    os.environ[k] = v
                except Exception:
                    pass

        # 3) Read from environment variables (highest priority)
        self.data["api_base_url"] = os.environ.get(
            "SCREENSHOT_AI_BASE_URL", self.data["api_base_url"]
        )
        self.data["model"] = os.environ.get(
            "SCREENSHOT_AI_MODEL", self.data["model"]
        )

    @property
    def api_key(self) -> str:
        """API key — only from environment variables, never written to file"""
        return os.environ.get("SCREENSHOT_AI_API_KEY", "")

    @property
    def api_base_url(self) -> str:
        return self.data["api_base_url"]

    @property
    def model(self) -> str:
        return self.data["model"]

    @property
    def language(self) -> str:
        """Current language: 'zh' or 'en'. Empty string means not yet chosen."""
        return self.data.get("language", "")

    @language.setter
    def language(self, value: str):
        self.data["language"] = value

    @property
    def use_hf_mirror(self) -> bool:
        return self.data.get("use_hf_mirror", False)

    @use_hf_mirror.setter
    def use_hf_mirror(self, value: bool):
        self.data["use_hf_mirror"] = value

    @property
    def daily_token_limit(self) -> int:
        return int(self.data.get("daily_token_limit", 1_000_000))

    @daily_token_limit.setter
    def daily_token_limit(self, value: int):
        self.data["daily_token_limit"] = int(value)

    def is_first_launch(self) -> bool:
        """Return True if the user hasn't chosen a language yet."""
        return not self.data.get("language", "")

    def save(self):
        """Save non-sensitive config to config.json"""
        self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(self.CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value

    def get(self, key, default=None):
        """Dict-like get with default fallback."""
        return self.data.get(key, default)


# ╔══════════════════════════════════════════════════════════════════╗
# ║                    Token Usage Tracker                         ║
# ╚══════════════════════════════════════════════════════════════════╝


class TokenLimitExceeded(RuntimeError):
    """Raised when the daily token limit has been reached."""
    pass


class TokenUsageTracker:
    """Track daily token usage with automatic date-based reset.

    Persisted to ~/.screenshot-ai-solver/token_usage.json
    Daily limit defaults to 2,000,000; override via env var
    SCREENSHOT_AI_DAILY_TOKEN_LIMIT.

    File format:
        {"history": [{"date": "2026-07-15", "used": 12345}, ...]}
    Keeps the last 60 days of history.
    """

    DEFAULT_DAILY_LIMIT = 1_000_000
    MAX_HISTORY_DAYS = 60

    def __init__(self, config_dir: Path, get_limit=None):
        self._config_dir = config_dir
        self._file = config_dir / "token_usage.json"
        self._data = self._load()
        self._migrate_if_needed()
        self._get_limit = get_limit  # callable that returns current limit

    def _load(self) -> dict:
        if self._file.exists():
            try:
                with open(self._file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, KeyError):
                pass
        return {"history": []}

    def _migrate_if_needed(self):
        """Migrate old {"date":"...","used":N} format to new history format."""
        if "date" in self._data:
            old_date = self._data.get("date", "")
            old_used = self._data.get("used", 0)
            self._data = {"history": []}
            if old_date and old_used > 0:
                self._data["history"].append({"date": old_date, "used": old_used})
            self._save()

    def _save(self):
        self._config_dir.mkdir(parents=True, exist_ok=True)
        # Prune old entries
        self._data["history"] = self._data["history"][-self.MAX_HISTORY_DAYS:]
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(self._data, f)

    # ── Public API ──────────────────────────────────────────

    @property
    def daily_limit(self) -> int:
        env_val = os.environ.get("SCREENSHOT_AI_DAILY_TOKEN_LIMIT")
        if env_val:
            return int(env_val)
        if self._get_limit:
            return self._get_limit()
        return self.DEFAULT_DAILY_LIMIT

    @property
    def used_today(self) -> int:
        today = datetime.now().strftime("%Y-%m-%d")
        history = self._data.get("history", [])
        if history and history[-1]["date"] == today:
            return history[-1]["used"]
        return 0

    @property
    def remaining(self) -> int:
        return max(0, self.daily_limit - self.used_today)

    @property
    def is_exceeded(self) -> bool:
        return self.used_today >= self.daily_limit

    def add(self, tokens: int):
        today = datetime.now().strftime("%Y-%m-%d")
        history = self._data.setdefault("history", [])
        if history and history[-1]["date"] == today:
            history[-1]["used"] += tokens
        else:
            history.append({"date": today, "used": tokens})
        self._save()

    def get_history(self, days: int = 30) -> list[dict]:
        """Return the last N days of usage history as [{"date":"...","used":N}, ...]."""
        return self._data.get("history", [])[-days:]


# ╔══════════════════════════════════════════════════════════════════╗
# ║                    Token API HTTP Server                       ║
# ╚══════════════════════════════════════════════════════════════════╝


class TokenAPIHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler that serves token usage data as JSON.

    Used by the dashboard HTML page for real-time polling.
    Set `tracker` on the class before starting the server.
    """

    tracker: "TokenUsageTracker | None" = None

    def do_GET(self):
        if self.path == "/api/token-usage":
            self._serve_json(self._get_data())
        elif self.path == "/api/ping":
            self._serve_json({"ok": True})
        else:
            self.send_error(404)

    def _serve_json(self, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _get_data(self) -> dict:
        t = self.tracker
        if t is None:
            return {"error": "tracker not ready"}
        history = t.get_history(30)
        return {
            "history": history,
            "used_today": t.used_today,
            "daily_limit": t.daily_limit,
            "remaining": t.remaining,
            "is_exceeded": t.is_exceeded,
        }

    def log_message(self, format, *args):
        pass  # suppress stdout logs


def _start_token_api(tracker: TokenUsageTracker) -> int:
    """Start the token API server in a daemon thread. Returns the bound port."""
    TokenAPIHandler.tracker = tracker

    # Find an available port
    for port in range(18765, 18775):
        try:
            server = HTTPServer(("127.0.0.1", port), TokenAPIHandler)
            server.timeout = 2
            t = threading.Thread(target=server.serve_forever, daemon=True)
            t.start()
            log.info(f"📡 Token API server started on http://127.0.0.1:{port}")
            return port
        except socket.error:
            continue

    log.warning("⚠️  Could not bind token API port (18765-18774)")
    return 0


# ╔══════════════════════════════════════════════════════════════════╗
# ║                    Welcome / Language Dialog                   ║
# ╚══════════════════════════════════════════════════════════════════╝


class WelcomeDialog:
    """First-launch language/location selector shown before the main app.

    Returns (language, use_hf_mirror) — both saved to config so the dialog
    only appears once.
    """

    def __init__(self, master: tk.Tk):
        self.result_lang = "en"
        self.result_hf_mirror = False
        self._done = False

        self.win = tk.Toplevel(master)
        self.win.title("Screenshot AI Solver")
        self.win.geometry("460x440")
        self.win.resizable(False, False)
        self.win.attributes("-topmost", True)
        self.win.configure(bg="#1e1e2e")

        # ── Header ──
        header = tk.Frame(self.win, bg="#2d2d44", height=48)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        tk.Label(
            header,
            text="🌍  Welcome  ·  欢迎",
            fg="#cdd6f4",
            bg="#2d2d44",
            font=("Segoe UI", 14, "bold"),
        ).pack(expand=True)

        # ── Question ──
        tk.Label(
            self.win,
            text="Where are you from?",
            fg="#cdd6f4",
            bg="#1e1e2e",
            font=("Segoe UI", 14, "bold"),
        ).pack(pady=(20, 4))

        tk.Label(
            self.win,
            text="你来自哪里？",
            fg="#a6adc8",
            bg="#1e1e2e",
            font=("微软雅黑", 12),
        ).pack(pady=(0, 16))

        # ── Option buttons ──
        options = [
            ("welcome.china", "zh", True),
            ("welcome.japan", "ja", False),
            ("welcome.us", "en", False),
            ("welcome.uk", "en", False),
            ("welcome.other", "en", False),
        ]

        self._buttons = []
        for i18n_key, lang, hf_mirror in options:
            display = I18N["zh"][i18n_key] if lang == "zh" else I18N["en"][i18n_key]

            btn = tk.Button(
                self.win,
                text=display,
                command=lambda l=lang, h=hf_mirror: self._choose(l, h),
                bg="#313244",
                fg="#cdd6f4",
                font=("Segoe UI", 12),
                relief="flat",
                cursor="hand2",
                padx=20,
                pady=10,
                activebackground="#45475a",
                activeforeground="#ffffff",
            )
            btn.pack(fill=tk.X, padx=40, pady=5)
            self._buttons.append(btn)

        # ── Description ──
        tk.Label(
            self.win,
            text=(
                "Your choice affects the interface language and\n"
                "OCR model download source (mirror for China)."
            ),
            fg="#6c7086",
            bg="#1e1e2e",
            font=("Segoe UI", 9),
            justify=tk.CENTER,
        ).pack(pady=(16, 0))

        # ── Center on screen ──
        self.win.update_idletasks()
        w, h = 460, 440
        x = (self.win.winfo_screenwidth() - w) // 2
        y = (self.win.winfo_screenheight() - h) // 2
        self.win.geometry(f"{w}x{h}+{x}+{y}")

        self.win.protocol("WM_DELETE_WINDOW", self._on_close)
        self.win.focus_force()

    def _choose(self, lang: str, hf_mirror: bool):
        self.result_lang = lang
        self.result_hf_mirror = hf_mirror
        self._done = True
        self.win.destroy()

    def _on_close(self):
        # User closed the window without choosing → default to English
        self.result_lang = "en"
        self.result_hf_mirror = False
        self._done = True
        self.win.destroy()


# ╔══════════════════════════════════════════════════════════════════╗
# ║                     Main Application Window                    ║
# ╚══════════════════════════════════════════════════════════════════╝


class MainWindow:
    """Application window — clawd-on-desk sidebar + light theme."""

    # ── Color palette (clawd light mode) ──────────────────────────
    BG         = "#f5f5f7"   # page background
    SURFACE    = "#ffffff"   # card / content surface
    SIDEBAR_BG = "#ececef"   # sidebar background
    BORDER     = "#d9d9dc"   # section border
    ACCENT     = "#d97757"   # warm orange accent
    ACCENT_DIM = "#c4684a"   # pressed / hover accent
    ACTIVE_BG  = "#ffffff"   # active sidebar item bg
    WARN       = "#d97706"   # warning amber
    DANGER     = "#dc2626"   # danger red
    TEXT_PRIME = "#18181b"   # primary text
    TEXT_SEC   = "#6b6b70"   # secondary text
    TEXT_TER   = "#9b9ba0"   # tertiary / dim
    ROW_BORDER = "#e5e5e8"   # inter-row rule

    def __init__(self, master: tk.Tk, app: "ScreenshotAISolver"):
        self.app = app
        self._t = app.t
        self.lang = app.lang
        self._config = app.config
        self._tracker = app._token_tracker
        self._api_port = app._api_port
        self._sidebar_items = {}  # key → (frame, label)
        self._active_panel = "home"

        self.win = tk.Toplevel(master)
        self.win.title("Screenshot AI Solver")
        self.win.geometry("720x520")
        self.win.minsize(640, 440)
        self.win.configure(bg=self.BG)
        self.win.attributes("-alpha", 0.0)

        self._build_sidebar()
        self._build_content_area()
        self._show_panel("home")
        self._center_window()
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)
        self.win.focus_force()

    def _on_close(self):
        self.win.withdraw()

    # ── Sidebar ──────────────────────────────────────────────────

    def _build_sidebar(self):
        self._sidebar_frame = tk.Frame(self.win, bg=self.SIDEBAR_BG, width=200)
        self._sidebar_frame.pack(side=tk.LEFT, fill=tk.Y)
        sidebar = self._sidebar_frame
        sidebar.pack_propagate(False)

        # App name at top
        tk.Label(
            sidebar, text="Screenshot\nAI Solver",
            fg=self.TEXT_PRIME, bg=self.SIDEBAR_BG,
            font=self.app._font(15, bold=True), justify=tk.LEFT,
        ).pack(anchor="w", padx=18, pady=(18, 14))

        tk.Label(
            sidebar, text="v1.0", fg=self.TEXT_TER, bg=self.SIDEBAR_BG,
            font=self.app._font(9),
        ).pack(anchor="w", padx=18, pady=(0, 10))

        # Separator
        tk.Frame(sidebar, bg=self.BORDER, height=1).pack(fill=tk.X, padx=14, pady=(0, 8))

        nav_items = [
            ("home",      "🏠", "menu.home",      "Home"),
            ("token",     "📊", "menu.dashboard", "Token Usage"),
            ("history",   "📜", "menu.history",   "History"),
            ("settings",  "⚙", "menu.settings",  "Settings"),
            ("providers", "🔑", "menu.providers", "API Providers"),
        ]

        for key, icon, i18n_key, fallback in nav_items:
            label_text = f"  {icon}  {self._t(i18n_key) if self._t(i18n_key) != i18n_key else fallback}"
            item_frame = tk.Frame(sidebar, bg=self.SIDEBAR_BG, cursor="hand2")
            item_frame.pack(fill=tk.X, padx=8, pady=1)

            lbl = tk.Label(
                item_frame, text=label_text,
                fg=self.TEXT_SEC, bg=self.SIDEBAR_BG,
                font=self.app._font(10),
                anchor="w", padx=10, pady=7,
                cursor="hand2",
            )
            lbl.pack(fill=tk.X)
            lbl.bind("<Button-1>", lambda e, k=key: self._show_panel(k))
            item_frame.bind("<Button-1>", lambda e, k=key: self._show_panel(k))

            self._sidebar_items[key] = (item_frame, lbl)

        # Bottom: footer in sidebar
        tk.Frame(sidebar, bg=self.BORDER, height=1).pack(
            fill=tk.X, padx=14, pady=(12, 8), side=tk.BOTTOM,
        )
        model_str = self._config.get("model", "gpt-4o")
        self._side_footer = tk.Label(
            sidebar, text=f"  {model_str}", fg=self.TEXT_TER, bg=self.SIDEBAR_BG,
            font=self.app._font(8), anchor="w",
        )
        self._side_footer.pack(fill=tk.X, padx=14, pady=(0, 8), side=tk.BOTTOM)

    def _set_active_sidebar(self, active_key):
        for key, (frame, lbl) in self._sidebar_items.items():
            if key == active_key:
                frame.configure(bg=self.ACTIVE_BG)
                lbl.configure(bg=self.ACTIVE_BG, fg=self.ACCENT,
                              font=self.app._font(10, bold=True))
            else:
                frame.configure(bg=self.SIDEBAR_BG)
                lbl.configure(bg=self.SIDEBAR_BG, fg=self.TEXT_SEC,
                              font=self.app._font(10))

    # ── Content area ─────────────────────────────────────────────

    def _build_content_area(self):
        self._content = tk.Frame(self.win, bg=self.BG)
        self._content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def _clear_content(self):
        for w in self._content.winfo_children():
            w.destroy()

    def _show_panel(self, key):
        self._active_panel = key
        self._set_active_sidebar(key)
        self._clear_content()

        if key == "home":
            self._panel_home()
        elif key == "token":
            self._panel_token()
        elif key == "history":
            self._panel_history()
        elif key == "settings":
            self._panel_settings()
        elif key == "providers":
            self._panel_providers()

    # ── Helpers ──────────────────────────────────────────────────

    def _section_title(self, parent, text):
        tk.Label(
            parent, text=text.upper(), fg=self.TEXT_TER, bg=self.BG,
            font=self.app._font(9, bold=True),
        ).pack(anchor="w", pady=(18, 8), padx=4)

    def _section_box(self, parent):
        outer = tk.Frame(parent, bg=self.BORDER)
        outer.pack(fill=tk.X, pady=(0, 10))
        inner = tk.Frame(outer, bg=self.SURFACE, padx=16, pady=12)
        inner.pack(fill=tk.X, padx=1, pady=1)
        return inner

    def _row(self, parent, label, value):
        row = tk.Frame(parent, bg=self.SURFACE, padx=4)
        row.pack(fill=tk.X)
        tk.Frame(row, bg=self.ROW_BORDER, height=1).pack(fill=tk.X, side=tk.BOTTOM)
        tk.Label(row, text=label, fg=self.TEXT_SEC, bg=self.SURFACE,
                 font=self.app._font(10)).pack(side=tk.LEFT, pady=6)
        tk.Label(row, text=value, fg=self.TEXT_PRIME, bg=self.SURFACE,
                 font=self.app._font(10, bold=True)).pack(side=tk.RIGHT, pady=6)

    def _btn(self, parent, text, command, accent=False):
        if accent:
            bg, fg = self.ACCENT, "#ffffff"
        else:
            bg, fg = "#e8e8eb", self.TEXT_PRIME
        btn = tk.Button(
            parent, text=text, command=command,
            bg=bg, fg=fg, font=self.app._font(10),
            relief="flat", cursor="hand2", padx=14, pady=5,
            activebackground=self.ACCENT, activeforeground="#ffffff",
        )
        return btn

    # ── Panel: Home ──────────────────────────────────────────────

    def _panel_home(self):
        content = self._content
        px = {"padx": 28}

        # Header
        tk.Label(content, text="Home", fg=self.TEXT_PRIME, bg=self.BG,
                 font=self.app._font(18, bold=True)).pack(anchor="w", pady=(24, 2), **px)
        tk.Label(content, text="Screenshot AI Solver dashboard",
                 fg=self.TEXT_SEC, bg=self.BG, font=self.app._font(10)).pack(anchor="w", pady=(0, 20), **px)

        # ── API Key ──
        self._section_title(content, self._t("settings.api_key"))
        card = self._section_box(content)
        row = tk.Frame(card, bg=self.SURFACE)
        row.pack(fill=tk.X)
        current = self._config.api_key
        self._api_entry = ttk.Entry(row, width=44)
        self._api_entry.insert(0, current[:8] + "****" if current else "")
        self._api_entry.pack(side=tk.LEFT, padx=(0, 8))
        tk.Button(row, text=self._t("settings.save"), command=self._save_api_key,
                  bg=self.ACCENT, fg="#ffffff", font=self.app._font(10, bold=True),
                  relief="flat", cursor="hand2", padx=14, pady=3).pack(side=tk.LEFT)
        status_row = tk.Frame(card, bg=self.SURFACE)
        status_row.pack(fill=tk.X, pady=(6, 0))
        self._status_dot = tk.Canvas(status_row, width=9, height=9, bg=self.SURFACE, highlightthickness=0)
        self._status_dot.pack(side=tk.LEFT, padx=(0, 6))
        self._dot_circle = self._status_dot.create_oval(0, 0, 9, 9, fill=self.ACCENT, outline="")
        self._api_status = tk.Label(status_row, text="", fg=self.TEXT_TER, bg=self.SURFACE, font=self.app._font(9))
        self._api_status.pack(side=tk.LEFT)
        self._refresh_api_status()

        # ── Token stats ──
        self._section_title(content, self._t("menu.dashboard"))
        card2 = self._section_box(content)
        used_val = self._tracker.used_today
        limit_val = self._tracker.daily_limit
        remain_val = max(0, limit_val - used_val)
        self._stat_labels = []
        for label, val in [
            (self._t("dashboard.today_usage"), f"{used_val:,}"),
            (self._t("dashboard.remaining"), f"{remain_val:,}"),
            (self._t("dashboard.daily_limit"), f"{limit_val:,}"),
        ]:
            r = tk.Frame(card2, bg=self.SURFACE, padx=4)
            r.pack(fill=tk.X)
            tk.Frame(r, bg=self.ROW_BORDER, height=1).pack(fill=tk.X, side=tk.BOTTOM)
            tk.Label(r, text=label, fg=self.TEXT_SEC, bg=self.SURFACE, font=self.app._font(10)).pack(side=tk.LEFT, pady=6)
            vl = tk.Label(r, text=val, fg=self.TEXT_PRIME, bg=self.SURFACE, font=self.app._font(10, bold=True))
            vl.pack(side=tk.RIGHT, pady=6)
            self._stat_labels.append(vl)

        # Progress bar
        bar_w, bar_h, r = 440, 18, 9
        self._bar_w, self._bar_h, self._bar_r = bar_w, bar_h, r
        self._progress_canvas = tk.Canvas(card2, width=bar_w, height=bar_h+4, bg=self.SURFACE, highlightthickness=0)
        self._progress_canvas.pack(pady=(10, 2))
        self._pbar_round_rect(0, 2, bar_w, bar_h+2, r, fill="#e5e5e8")
        self._progress_text = self._progress_canvas.create_text(bar_w//2, bar_h//2+1, text="", fill=self.TEXT_PRIME, font=("Segoe UI", 9, "bold"))
        self._update_progress_bar()

        # Screenshot button
        self._btn(content, "📸 " + self._t("main.screenshot_solve"), self._trigger_screenshot, accent=True).pack(anchor="w", pady=(14, 0), **px)

    # ── Panel: Token ─────────────────────────────────────────────

    def _panel_token(self):
        content = self._content
        px = {"padx": 28}

        tk.Label(content, text=self._t("menu.dashboard"), fg=self.TEXT_PRIME, bg=self.BG,
                 font=self.app._font(18, bold=True)).pack(anchor="w", pady=(24, 2), **px)
        tk.Label(content, text="Token usage and history",
                 fg=self.TEXT_SEC, bg=self.BG, font=self.app._font(10)).pack(anchor="w", pady=(0, 20), **px)

        self._section_title(content, "Usage Stats")
        card = self._section_box(content)
        used_val = self._tracker.used_today
        limit_val = self._tracker.daily_limit
        remain_val = max(0, limit_val - used_val)
        self._token_stat_labels = []
        for label, val in [
            (self._t("dashboard.today_usage"), f"{used_val:,}"),
            (self._t("dashboard.remaining"), f"{remain_val:,}"),
            (self._t("dashboard.daily_limit"), f"{limit_val:,}"),
        ]:
            self._row(card, label, val)

        bar_w, bar_h, r = 440, 20, 10
        self._bar_w2, self._bar_h2, self._bar_r2 = bar_w, bar_h, r
        self._progress_canvas2 = tk.Canvas(card, width=bar_w, height=bar_h+4, bg=self.SURFACE, highlightthickness=0)
        self._progress_canvas2.pack(pady=(10, 2))
        self._pbar_track2 = self._pbar_round_rect2(0, 2, bar_w, bar_h+2, r, fill="#e5e5e8")
        self._progress_text2 = self._progress_canvas2.create_text(bar_w//2, bar_h//2+1, text="", fill=self.TEXT_PRIME, font=("Segoe UI", 9, "bold"))
        self._update_progress_bar2()

        spark_h = 36
        self._spark_canvas = tk.Canvas(card, width=bar_w, height=spark_h, bg=self.SURFACE, highlightthickness=0)
        self._spark_canvas.pack(pady=(4, 2))
        self._build_sparkline2()

        self._btn(content, "↗ " + self._t("main.view_dashboard"), self.app._show_token_dashboard).pack(anchor="w", pady=(14, 0), **px)

    def _pbar_round_rect2(self, x1, y1, x2, y2, r, **kw):
        parts = []
        parts.append(self._progress_canvas2.create_oval(x1, y1, x1+2*r, y1+2*r, **kw))
        parts.append(self._progress_canvas2.create_oval(x2-2*r, y1, x2, y1+2*r, **kw))
        parts.append(self._progress_canvas2.create_oval(x1, y2-2*r, x1+2*r, y2, **kw))
        parts.append(self._progress_canvas2.create_oval(x2-2*r, y2-2*r, x2, y2, **kw))
        parts.append(self._progress_canvas2.create_rectangle(x1+r, y1, x2-r, y2, **kw))
        parts.append(self._progress_canvas2.create_rectangle(x1, y1+r, x2, y2-r, **kw))
        tag = f"rrect2_{x1}_{y1}"
        for pid in parts:
            self._progress_canvas2.itemconfig(pid, tags=(tag,))
        return tag

    def _update_progress_bar2(self):
        used = self._tracker.used_today
        limit = self._tracker.daily_limit
        pct = min(used/limit*100, 100) if limit > 0 else 0
        fill_w = int((self._bar_w2-2)*pct/100)
        if pct > 80: color = self.DANGER
        elif pct > 50: color = self.WARN
        else: color = self.ACCENT
        for tag in ("fill_pbar2",): self._progress_canvas2.delete(tag)
        if fill_w > 0:
            self._pbar_round_rect2(1, 3, fill_w+1, self._bar_h2+1, self._bar_r2-1, fill=color, outline="", tags="fill_pbar2")
        self._progress_canvas2.lift(self._progress_text2)
        self._progress_canvas2.itemconfig(self._progress_text2, text=f"{used:,} / {limit:,}  ({pct:.1f}%)")

    def _build_sparkline2(self):
        canvas = self._spark_canvas
        canvas.delete("spark2")
        history = self._tracker.get_history(7)
        if not history or len(history) < 2:
            canvas.create_text(220, 18, text="—", fill=self.TEXT_TER, font=("Segoe UI", 10), tags="spark2")
            return
        values = [d.get("tokens", 0) for d in history[-7:]]
        max_v = max(values) if max(values) > 0 else 1
        w, h = 440, 36; px, py = 8, 5; pw, ph = w-2*px, h-2*py
        points = []
        for i, v in enumerate(values):
            x = px + (i/(len(values)-1))*pw if len(values) > 1 else px+pw/2
            y = py + ph - (v/max_v)*ph
            points.extend([x, y])
        if len(points) >= 4:
            area_pts = [px, py+ph] + points + [points[-2], py+ph]
            canvas.create_polygon(area_pts, fill=self.ACCENT, stipple="gray25", outline="", tags="spark2")
            canvas.create_line(points, fill=self.ACCENT, width=2, smooth=True, tags="spark2")

    # ── Panel: History ───────────────────────────────────────────

    def _panel_history(self):
        content = self._content
        px = {"padx": 28}

        tk.Label(content, text=self._t("menu.history"), fg=self.TEXT_PRIME, bg=self.BG,
                 font=self.app._font(18, bold=True)).pack(anchor="w", pady=(24, 2), **px)
        tk.Label(content, text="Recently answered questions",
                 fg=self.TEXT_SEC, bg=self.BG, font=self.app._font(10)).pack(anchor="w", pady=(0, 20), **px)

        history_files = sorted(self.app._log_dir.glob("*.txt"), reverse=True)[:20]

        if not history_files:
            tk.Label(content, text=self._t("history.no_records"),
                     fg=self.TEXT_TER, bg=self.BG, font=self.app._font(11)).pack(**px, pady=40)
            return

        for fp in history_files:
            try:
                text_content = fp.read_text(encoding="utf-8")[:300]
                # Extract first line as title
                lines = text_content.split("\n")
                title = lines[0] if lines else fp.stem
                preview = "\n".join(lines[1:3]) if len(lines) > 1 else ""
            except Exception:
                title, preview = fp.stem, ""

            card = tk.Frame(content, bg=self.SURFACE, padx=14, pady=8, highlightthickness=1, highlightbackground=self.BORDER)
            card.pack(fill=tk.X, pady=(0, 6), **px)

            tk.Label(card, text=title[:60], fg=self.TEXT_PRIME, bg=self.SURFACE,
                     font=self.app._font(10, bold=True)).pack(anchor="w")
            if preview:
                tk.Label(card, text=preview[:100], fg=self.TEXT_TER, bg=self.SURFACE,
                         font=self.app._font(9)).pack(anchor="w", pady=(2, 0))

            # Click to view full
            card.bind("<Button-1>", lambda e, p=fp: self._view_history_file(p))
            for child in card.winfo_children():
                child.bind("<Button-1>", lambda e, p=fp: self._view_history_file(p))

    def _view_history_file(self, filepath):
        content = filepath.read_text(encoding="utf-8")
        AnswerWindow(self.win, "", content, self._t, self.lang)

    # ── Panel: Settings ──────────────────────────────────────────

    def _panel_settings(self):
        content = self._content
        px = {"padx": 28}

        tk.Label(content, text=self._t("menu.settings"), fg=self.TEXT_PRIME, bg=self.BG,
                 font=self.app._font(18, bold=True)).pack(anchor="w", pady=(24, 2), **px)
        tk.Label(content, text="Configure API and preferences",
                 fg=self.TEXT_SEC, bg=self.BG, font=self.app._font(10)).pack(anchor="w", pady=(0, 20), **px)

        # Base URL
        self._section_title(content, self._t("settings.api_settings"))
        card = self._section_box(content)

        # Base URL row
        r1 = tk.Frame(card, bg=self.SURFACE, padx=4)
        r1.pack(fill=tk.X)
        tk.Frame(r1, bg=self.ROW_BORDER, height=1).pack(fill=tk.X, side=tk.BOTTOM)
        tk.Label(r1, text=self._t("settings.base_url"), fg=self.TEXT_SEC, bg=self.SURFACE,
                 font=self.app._font(10)).pack(side=tk.LEFT, pady=6)
        url_entry = ttk.Entry(r1, width=38)
        url_entry.insert(0, str(self._config["api_base_url"]))
        url_entry.pack(side=tk.RIGHT, pady=4)

        # Model row
        r2 = tk.Frame(card, bg=self.SURFACE, padx=4)
        r2.pack(fill=tk.X)
        tk.Frame(r2, bg=self.ROW_BORDER, height=1).pack(fill=tk.X, side=tk.BOTTOM)
        tk.Label(r2, text=self._t("settings.model"), fg=self.TEXT_SEC, bg=self.SURFACE,
                 font=self.app._font(10)).pack(side=tk.LEFT, pady=6)
        model_entry = ttk.Entry(r2, width=38)
        model_entry.insert(0, str(self._config["model"]))
        model_entry.pack(side=tk.RIGHT, pady=4)

        # Token limit row
        r3 = tk.Frame(card, bg=self.SURFACE, padx=4)
        r3.pack(fill=tk.X)
        tk.Frame(r3, bg=self.ROW_BORDER, height=1).pack(fill=tk.X, side=tk.BOTTOM)
        tk.Label(r3, text="Token Limit:", fg=self.TEXT_SEC, bg=self.SURFACE,
                 font=self.app._font(10)).pack(side=tk.LEFT, pady=6)
        limit_entry = ttk.Entry(r3, width=38)
        limit_entry.insert(0, str(self._config.daily_token_limit))
        limit_entry.pack(side=tk.RIGHT, pady=4)

        # Language row
        r4 = tk.Frame(card, bg=self.SURFACE, padx=4)
        r4.pack(fill=tk.X)
        tk.Label(r4, text=self._t("settings.language"), fg=self.TEXT_SEC, bg=self.SURFACE,
                 font=self.app._font(10)).pack(side=tk.LEFT, pady=6)
        lang_var = tk.StringVar(value=self.lang)
        lang_combo = ttk.Combobox(r4, textvariable=lang_var, state="readonly", width=36,
                                   values=["zh (中文)", "en (English)", "ja (日本語)"])
        lang_combo.pack(side=tk.RIGHT, pady=4)

        def save_settings():
            self._config["api_base_url"] = url_entry.get()
            self._config["model"] = model_entry.get()
            try: self._config.daily_token_limit = int(limit_entry.get())
            except ValueError: pass
            chosen = lang_var.get()
            if "zh" in chosen: new_lang = "zh"
            elif "ja" in chosen: new_lang = "ja"
            else: new_lang = "en"
            lang_changed = new_lang != self.app.lang
            self.lang = new_lang
            self.app.lang = new_lang  # <-- CRITICAL: update app's language
            self._config.language = new_lang
            self._config.use_hf_mirror = (new_lang == "zh")
            if new_lang == "zh":
                os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
            else:
                os.environ.pop("HF_ENDPOINT", None)
            self._config.save()
            self.app._reset_client()
            if lang_changed:
                self.app._update_indicator_text()
                self.rebuild()
            else:
                self.refresh()
            messagebox.showinfo(self._t("settings.title"), self._t("settings.saved"), parent=self.win)

        self._btn(content, "💾 " + self._t("settings.save"), save_settings, accent=True).pack(anchor="w", pady=(14, 0), **px)

    # ── Panel: API Providers ────────────────────────────────────

    def _panel_providers(self):
        content = self._content
        px = {"padx": 28}

        tk.Label(content, text=self._t("menu.providers"), fg=self.TEXT_PRIME, bg=self.BG,
                 font=self.app._font(18, bold=True)).pack(anchor="w", pady=(24, 2), **px)
        tk.Label(content, text="Get your API key from one of these providers",
                 fg=self.TEXT_SEC, bg=self.BG, font=self.app._font(10)).pack(anchor="w", pady=(0, 20), **px)

        providers = [
            ("🌐", "OpenAI", "GPT-4o, GPT-4, o3 — most popular", "https://platform.openai.com"),
            ("🔍", "DeepSeek", "DeepSeek-V3, R1 — 超低价，国内友好", "https://platform.deepseek.com"),
            ("🧠", "Anthropic", "Claude Opus, Sonnet, Haiku", "https://console.anthropic.com"),
            ("💎", "Google AI", "Gemini 2.5 Pro, Flash — generous free tier", "https://aistudio.google.com"),
            ("⚡", "Groq", "Ultra-fast inference, free tier", "https://console.groq.com"),
            ("🌊", "SiliconFlow", "硅基流动 — 国内直连，多模型", "https://siliconflow.cn"),
            ("🧩", "Zhipu AI", "智谱 GLM-4 — 国产大模型", "https://open.bigmodel.cn"),
            ("🚀", "Moonshot", "月之暗面 Kimi — 长文本", "https://platform.moonshot.cn"),
            ("☁️", "Alibaba Cloud", "阿里通义千问 — DashScope", "https://dashscope.aliyun.com"),
            ("🔥", "Together AI", "Open-source models, cheap inference", "https://together.ai"),
            ("🦙", "Fireworks AI", "Fast open-source model inference", "https://fireworks.ai"),
            ("🔮", "Baidu AI", "百度千帆 ERNIE — 国内稳定", "https://qianfan.cloud.baidu.com"),
        ]

        for emoji, name, desc, url in providers:
            card = tk.Frame(content, bg=self.SURFACE, padx=14, pady=8,
                            highlightthickness=1, highlightbackground=self.BORDER)
            card.pack(fill=tk.X, pady=(0, 6), **px)

            left = tk.Frame(card, bg=self.SURFACE)
            left.pack(side=tk.LEFT, anchor="w")

            tk.Label(left, text=f"{emoji}  {name}", fg=self.TEXT_PRIME, bg=self.SURFACE,
                     font=self.app._font(10, bold=True)).pack(anchor="w")
            tk.Label(left, text=desc, fg=self.TEXT_TER, bg=self.SURFACE,
                     font=self.app._font(9)).pack(anchor="w")

            link_lbl = tk.Label(card, text="↗ " + url, fg=self.ACCENT, bg=self.SURFACE,
                                font=self.app._font(9), cursor="hand2")
            link_lbl.pack(side=tk.RIGHT, padx=(10, 0))
            link_lbl.bind("<Button-1>", lambda e, u=url: os.startfile(u) if os.name == "nt" else None)

    # ── Progress bar (home panel) ───────────────────────────────

    def _pbar_round_rect(self, x1, y1, x2, y2, r, **kw):
        parts = []
        parts.append(self._progress_canvas.create_oval(x1, y1, x1+2*r, y1+2*r, **kw))
        parts.append(self._progress_canvas.create_oval(x2-2*r, y1, x2, y1+2*r, **kw))
        parts.append(self._progress_canvas.create_oval(x1, y2-2*r, x1+2*r, y2, **kw))
        parts.append(self._progress_canvas.create_oval(x2-2*r, y2-2*r, x2, y2, **kw))
        parts.append(self._progress_canvas.create_rectangle(x1+r, y1, x2-r, y2, **kw))
        parts.append(self._progress_canvas.create_rectangle(x1, y1+r, x2, y2-r, **kw))
        tag = f"rrect_{x1}_{y1}"
        for pid in parts: self._progress_canvas.itemconfig(pid, tags=(tag,))
        return tag

    # ── Actions ──────────────────────────────────────────────────

    def _trigger_screenshot(self):
        self.win.iconify()
        self.win.after(300, self.app._start_selection)

    def _save_api_key(self):
        new_key = self._api_entry.get()
        if new_key and "****" not in new_key:
            os.environ["SCREENSHOT_AI_API_KEY"] = new_key
            self.app._reset_client()
        self._refresh_api_status()

    # ── Refresh ──────────────────────────────────────────────────

    def refresh(self):
        self._update_progress_bar()
        self._refresh_api_status()
        # Update stat labels on home panel
        used = self._tracker.used_today
        limit = self._tracker.daily_limit
        remain = max(0, limit - used)
        for lbl, val in zip(self._stat_labels, [f"{used:,}", f"{remain:,}", f"{limit:,}"]):
            if lbl and lbl.winfo_exists():
                lbl.config(text=val)

    def _refresh_api_status(self):
        if not hasattr(self, '_api_status') or not self._api_status.winfo_exists():
            return
        if self._config.api_key:
            self._status_dot.itemconfig(self._dot_circle, fill=self.ACCENT)
            self._api_status.config(text=self._t("main.api_configured"), fg=self.ACCENT)
        else:
            self._status_dot.itemconfig(self._dot_circle, fill=self.WARN)
            self._api_status.config(text=self._t("main.api_not_configured"), fg=self.WARN)

    def _update_progress_bar(self):
        if not hasattr(self, '_progress_canvas') or not self._progress_canvas.winfo_exists():
            return
        used = self._tracker.used_today
        limit = self._tracker.daily_limit
        pct = min(used/limit*100, 100) if limit > 0 else 0
        fill_w = int((self._bar_w-2)*pct/100)
        if pct > 80: color = self.DANGER
        elif pct > 50: color = self.WARN
        else: color = self.ACCENT
        for tag in ("fill_pbar",): self._progress_canvas.delete(tag)
        if fill_w > 0:
            self._pbar_round_rect(1, 3, fill_w+1, self._bar_h+1, self._bar_r-1, fill=color, outline="", tags="fill_pbar")
        self._progress_canvas.lift(self._progress_text)
        self._progress_canvas.itemconfig(self._progress_text, text=f"{used:,} / {limit:,}  ({pct:.1f}%)")

    def _center_window(self):
        self.win.update_idletasks()
        w, h = 720, 520
        x = (self.win.winfo_screenwidth() - w) // 2
        y = (self.win.winfo_screenheight() - h) // 2
        self.win.geometry(f"{w}x{h}+{x}+{y}")

    def rebuild(self):
        self.lang = self.app.lang
        current = self._active_panel
        # Destroy old sidebar frame
        if hasattr(self, '_sidebar_frame') and self._sidebar_frame.winfo_exists():
            self._sidebar_frame.destroy()
        self._sidebar_items.clear()
        # Destroy old content frame
        self._clear_content()
        if hasattr(self, '_content') and self._content.winfo_exists():
            self._content.destroy()
        # Rebuild everything
        self._build_sidebar()
        self._build_content_area()
        self._show_panel(current)


# ╔══════════════════════════════════════════════════════════════════╗
# ║                     Answer Popup Window                        ║
# ╚══════════════════════════════════════════════════════════════════╝


class AnswerWindow:
    """Answer popup — light theme matching main window."""

    BG       = "#f5f5f7"
    SURFACE  = "#ffffff"
    ACCENT   = "#d97757"
    TEXT_P   = "#18181b"
    TEXT_S   = "#6b6b70"
    TEXT_T   = "#9b9ba0"
    HEADER   = "#ececef"
    BORDER   = "#d9d9dc"

    def __init__(self, master: tk.Tk, question_text: str, answer: str,
                 t, lang: str):
        self._t = t

        font_val = "Meiryo" if lang == "ja" else ("Segoe UI" if lang == "en" else "微软雅黑")

        self.win = tk.Toplevel(master)
        self.win.title(self._t("answer.title"))
        self.win.geometry("700x520")
        self.win.minsize(400, 300)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=self.BG)

        # ── Title bar ──
        title_bar = tk.Frame(self.win, bg=self.HEADER, height=34)
        title_bar.pack(fill=tk.X)
        title_bar.pack_propagate(False)

        tk.Label(title_bar, text=f"  {self._t('answer.title')}",
                 fg=self.TEXT_P, bg=self.HEADER,
                 font=(font_val, 12, "bold")).pack(side=tk.LEFT, padx=10)

        close_lbl = tk.Label(title_bar, text="✕", fg=self.TEXT_S, bg=self.HEADER,
                             font=("Segoe UI", 14), cursor="hand2")
        close_lbl.pack(side=tk.RIGHT, padx=12)
        close_lbl.bind("<Button-1>", lambda e: self.win.destroy())

        title_bar.bind("<Button-1>", self._start_drag)
        title_bar.bind("<B1-Motion>", self._do_drag)
        self._drag_x = self._drag_y = 0

        # ── Content ──
        main = tk.Frame(self.win, bg=self.BG)
        main.pack(fill=tk.BOTH, expand=True, padx=16, pady=(8, 0))

        # Recognized text
        tk.Label(main, text=self._t("answer.recognized_text").upper(),
                 fg=self.TEXT_T, bg=self.BG,
                 font=(font_val, 9, "bold")).pack(anchor="w", pady=(0, 4))

        q_box = tk.Text(main, height=3, wrap=tk.WORD, fg=self.TEXT_P, bg=self.SURFACE,
                        font=(font_val, 10), relief="flat", padx=10, pady=8,
                        highlightthickness=1, highlightbackground=self.BORDER)
        q_preview = question_text[:300] + "..." if len(question_text) > 300 else question_text
        q_box.insert(tk.END, q_preview.strip() or self._t("answer.no_text"))
        q_box.config(state=tk.DISABLED)
        q_box.pack(fill=tk.X, pady=(0, 10))

        # AI answer
        tk.Label(main, text=self._t("answer.ai_answer").upper(),
                 fg=self.TEXT_T, bg=self.BG,
                 font=(font_val, 9, "bold")).pack(anchor="w", pady=(0, 4))

        self.a_text = scrolledtext.ScrolledText(
            main, wrap=tk.WORD, fg=self.TEXT_P, bg=self.SURFACE,
            font=(font_val, 12), relief="flat", padx=12, pady=12,
            highlightthickness=1, highlightbackground=self.BORDER,
        )
        self.a_text.insert(tk.END, answer)
        self.a_text.config(state=tk.DISABLED)
        self.a_text.pack(fill=tk.BOTH, expand=True)

        # ── Buttons ──
        btn_bar = tk.Frame(self.win, bg=self.BG, height=40)
        btn_bar.pack(fill=tk.X, padx=16, pady=(0, 12))
        btn_bar.pack_propagate(False)

        self.copy_btn = tk.Button(
            btn_bar, text=self._t("answer.copy"), command=self._copy_answer,
            bg=self.ACCENT, fg="#ffffff", font=(font_val, 10, "bold"),
            relief="flat", cursor="hand2", padx=16, pady=5,
        )
        self.copy_btn.pack(side=tk.LEFT, padx=(0, 8))

        tk.Button(btn_bar, text=self._t("answer.close"), command=self.win.destroy,
                  bg="#e8e8eb", fg=self.TEXT_P, font=(font_val, 10),
                  relief="flat", cursor="hand2", padx=16, pady=5).pack(side=tk.RIGHT)

        # ── Shortcuts ──
        self.win.bind("<Escape>", lambda e: self.win.destroy())
        self.win.bind("<Control-c>", lambda e: self._copy_answer())

        # Center
        self.win.update_idletasks()
        w, h = 700, 520
        x = (self.win.winfo_screenwidth() - w) // 2
        y = (self.win.winfo_screenheight() - h) // 2
        self.win.geometry(f"{w}x{h}+{x}+{y}")
        self.win.focus_force()

    def _start_drag(self, event):
        self._drag_x, self._drag_y = event.x, event.y

    def _do_drag(self, event):
        x = self.win.winfo_x() + (event.x - self._drag_x)
        y = self.win.winfo_y() + (event.y - self._drag_y)
        self.win.geometry(f"+{x}+{y}")

    def _copy_answer(self):
        text = self.a_text.get("1.0", tk.END).strip()
        self.win.clipboard_clear()
        self.win.clipboard_append(text)
        self.copy_btn.config(text=self._t("answer.copied"))
        self.win.after(2000, lambda: self.copy_btn.config(text=self._t("answer.copy")))


# ╔══════════════════════════════════════════════════════════════════╗
# ║                    Region Selector                             ║
# ╚══════════════════════════════════════════════════════════════════╝


class RegionSelector:
    """Fullscreen semi-transparent overlay with mouse drag selection.

    Usage:
        selector = RegionSelector(root, screenshot, hint_text)
        root.wait_window(selector.win)
        if selector.cancelled: return
        cropped = screenshot.crop(selector.region)
    """

    def __init__(self, master: tk.Tk, screenshot: Image.Image,
                 hint_text: str = "Drag to select  |  Esc to cancel"):
        self.screenshot = screenshot
        self.region = None
        self.cancelled = False

        # Fullscreen semi-transparent window
        self.win = tk.Toplevel(master)
        self.win.attributes("-fullscreen", True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.45)
        self.win.configure(cursor="cross", bg="black")

        # Get logical window dimensions → compute DPI scale ratio
        self.win.update_idletasks()
        win_w = self.win.winfo_width()
        win_h = self.win.winfo_height()
        pil_w, pil_h = screenshot.size
        self.scale_x = pil_w / max(win_w, 1)
        self.scale_y = pil_h / max(win_h, 1)

        # Resize screenshot to match window for display
        display = screenshot.resize((win_w, win_h), Image.LANCZOS)

        # Convert to tkinter PhotoImage (via temp file)
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp_path = tmp.name
        tmp.close()
        display.save(tmp_path)
        self._photo = tk.PhotoImage(file=tmp_path)
        os.unlink(tmp_path)

        # Canvas
        self.canvas = tk.Canvas(
            self.win, width=win_w, height=win_h,
            highlightthickness=0, bg="black",
        )
        self.canvas.pack()

        # Draw screenshot background
        self.canvas.create_image(0, 0, image=self._photo, anchor="nw")

        # Semi-transparent dark overlay
        self.canvas.create_rectangle(
            0, 0, win_w, win_h,
            fill="black", stipple="gray25", tags="dim",
        )

        # Hint text
        self.canvas.create_text(
            win_w // 2, win_h - 35,
            text=hint_text,
            fill="#cccccc", font=("Segoe UI", 13), tags="hint",
        )

        # Mouse state
        self._sx = 0
        self._sy = 0

        # Event bindings
        self.canvas.bind("<Button-1>", self._on_down)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_up)
        self.win.bind("<Escape>", self._on_cancel)

    def _on_down(self, event):
        self._sx, self._sy = event.x, event.y

    def _on_drag(self, event):
        self.canvas.delete("sel_rect", "cutout")
        x1, y1 = self._sx, self._sy
        x2, y2 = event.x, event.y
        # Dashed border
        self.canvas.create_rectangle(
            x1, y1, x2, y2,
            outline="#00ff00", width=2, dash=(6, 3),
            tags="sel_rect",
        )
        # Cutout overlay in selected region (makes screenshot clear)
        self.canvas.create_rectangle(
            x1, y1, x2, y2,
            fill="", outline="", stipple="",
            tags="cutout",
        )

    def _on_up(self, event):
        x1 = min(self._sx, event.x)
        y1 = min(self._sy, event.y)
        x2 = max(self._sx, event.x)
        y2 = max(self._sy, event.y)

        if x2 - x1 < 15 or y2 - y1 < 15:
            return  # Too small, ignore

        # Map back to original screenshot physical coordinates
        self.region = (
            int(x1 * self.scale_x),
            int(y1 * self.scale_y),
            int(x2 * self.scale_x),
            int(y2 * self.scale_y),
        )
        self.win.destroy()

    def _on_cancel(self, event=None):
        self.cancelled = True
        self.win.destroy()


# ╔══════════════════════════════════════════════════════════════════╗
# ║                    Main Application                            ║
# ╚══════════════════════════════════════════════════════════════════╝


class ScreenshotAISolver:
    """Screenshot AI Solver main application.

    ┌─────────────┐     ┌──────────┐     ┌───────────┐     ┌──────────┐
    │ Shift+G     │ ──▶ │Screenshot│ ──▶ │ OCR text  │ ──▶ │ AI solve │
    │ hotkey      │     │ Pillow   │     │ RapidOCR  │     │ OpenAI   │
    └─────────────┘     └──────────┘     └───────────┘     └──────────┘
    """

    def __init__(self):
        self.config = Config()
        self._ocr: RapidOCR | None = None
        self._client: OpenAI | None = None
        self._lock = threading.Lock()
        self._current_keys: set = set()

        # ── Language ──
        self.lang = self.config.language  # may be "" on first launch
        self._use_hf_mirror = self.config.use_hf_mirror

        # Initialize tkinter (main thread)
        self.root = tk.Tk()
        self.root.withdraw()  # Hide root, use Toplevel only

        # ── Show welcome dialog on first launch ──
        if self.config.is_first_launch():
            welcome = WelcomeDialog(self.root)
            self.root.wait_window(welcome.win)
            self.lang = welcome.result_lang
            self._use_hf_mirror = welcome.result_hf_mirror
            self.config.language = self.lang
            self.config.use_hf_mirror = self._use_hf_mirror
            self.config.save()

        # ── Apply HF mirror for China users ──
        if self._use_hf_mirror:
            os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
            log.info(self.t("log.hf_mirror"))

        # Create floating indicator
        self._create_indicator()

        # Token usage tracker
        self._token_tracker = TokenUsageTracker(
            self.config.CONFIG_DIR,
            get_limit=lambda: self.config.daily_token_limit,
        )
        self._api_port = _start_token_api(self._token_tracker)

        # Create main application window
        self._main_window = MainWindow(self.root, self)

        # History log directory
        self._log_dir = self.config.CONFIG_DIR / "history"
        self._log_dir.mkdir(parents=True, exist_ok=True)

    # ── Translation helper ─────────────────────────────────

    def t(self, key: str, **kwargs) -> str:
        """Look up a translated string in the current language.
        Falls back to English if the key is missing in the current language.
        """
        text = I18N.get(self.lang, I18N["en"]).get(key)
        if text is None:
            text = I18N["en"].get(key, key)
        if kwargs:
            try:
                return text.format(**kwargs)
            except KeyError:
                return text
        return text

    def _font(self, size: int = 10, bold: bool = False):
        """Return (font_name, size, [bold]) tuple for current language."""
        if self.lang == "ja":
            name = "Meiryo"
        elif self.lang == "en":
            name = "Segoe UI"
        else:
            name = "微软雅黑"
        return (name, size, "bold") if bold else (name, size)

    # ── Floating indicator ─────────────────────────────────

    def _create_indicator(self):
        """Top-right floating HUD indicator — modern rounded semi-transparent."""
        self.indicator = tk.Toplevel(self.root)
        self.indicator.title("")
        self.indicator.overrideredirect(True)
        self.indicator.attributes("-topmost", True)
        self.indicator.configure(bg="#0f0f14")
        self.indicator.attributes("-alpha", 0.92)

        # ── Canvas background (rounded rect) ──
        ind_w, ind_h = 180, 38
        self._ind_w, self._ind_h = ind_w, ind_h
        self._ind_canvas = tk.Canvas(
            self.indicator, width=ind_w, height=ind_h,
            bg="#0f0f14", highlightthickness=0,
        )
        self._ind_canvas.pack()

        # Rounded background (rectangle + corner circles)
        self._ind_bg_rect = self._ind_canvas.create_rectangle(
            7, 1, ind_w - 7, ind_h - 1, fill="#1a1a24", outline="", width=0,
        )
        self._ind_bg_mid = self._ind_canvas.create_rectangle(
            1, 7, ind_w - 1, ind_h - 7, fill="#1a1a24", outline="", width=0,
        )
        for cx, cy in [(7, 7), (ind_w - 7, 7), (7, ind_h - 7), (ind_w - 7, ind_h - 7)]:
            self._ind_canvas.create_oval(
                cx - 6, cy - 6, cx + 6, cy + 6, fill="#1a1a24", outline="", width=0,
            )
        # Border rect
        self._ind_canvas.create_rectangle(
            1, 1, ind_w - 1, ind_h - 1, fill="", outline="#2a2a3a", width=1,
        )

        # Status dot (Canvas circle)
        self._ind_dot = self._ind_canvas.create_oval(
            12, 10, 24, 22, fill="#a6e3a1", outline="",
        )

        # Status text
        ready_text = self.t("indicator.ready")
        self._ind_label = self._ind_canvas.create_text(
            36, ind_h // 2, text=ready_text, anchor="w",
            fill="#cdd6f4", font=self._font(10, bold=True),
        )

        # ── Hover expansion state ──
        self._ind_expanded = False
        self._ind_info_labels = []  # extra labels shown on hover

        # Right-click menu
        self.indicator.bind("<Button-3>", self._on_indicator_right_click)
        # Left-click drag
        self.indicator.bind("<Button-1>", self._start_drag_indicator)
        self.indicator.bind("<B1-Motion>", self._do_drag_indicator)
        # Hover
        self.indicator.bind("<Enter>", self._on_ind_enter)
        self.indicator.bind("<Leave>", self._on_ind_leave)

        self._ind_drag_x = 0
        self._ind_drag_y = 0

        # Position top-right
        self.indicator.update_idletasks()
        x = self.indicator.winfo_screenwidth() - ind_w - 16
        y = 16
        self.indicator.geometry(f"{ind_w}x{ind_h}+{x}+{y}")

    def _on_ind_enter(self, event):
        if self._ind_expanded:
            return
        self._ind_expanded = True
        # Show mini token stats
        used = self._token_tracker.used_today
        limit = self._token_tracker.daily_limit
        remain = max(0, limit - used)

        self._ind_canvas.itemconfig(self._ind_label, text="")
        # Expand window
        self.indicator.geometry(f"{self._ind_w}x58")
        stats_text = f"{used:,} / {limit:,}  |  {remain:,} left"
        self._ind_info = self._ind_canvas.create_text(
            self._ind_w // 2, 46, text=stats_text, anchor="center",
            fill="#6c7086", font=self._font(8),
        )

    def _on_ind_leave(self, event):
        if not self._ind_expanded:
            return
        self._ind_expanded = False
        self._ind_canvas.delete(self._ind_info)
        self.indicator.geometry(f"{self._ind_w}x{self._ind_h}")
        self._ind_canvas.itemconfig(
            self._ind_label, text=self.t("indicator.ready"),
        )

    def _start_drag_indicator(self, event):
        self._ind_drag_x = event.x
        self._ind_drag_y = event.y

    def _do_drag_indicator(self, event):
        x = self.indicator.winfo_x() + (event.x - self._ind_drag_x)
        y = self.indicator.winfo_y() + (event.y - self._ind_drag_y)
        self.indicator.geometry(f"+{x}+{y}")

    def _on_indicator_right_click(self, event):
        font_name = self._font(10)[0]
        menu = tk.Menu(self.root, tearoff=0, bg="#313244", fg="#cdd6f4",
                       activebackground="#45475a", font=(font_name, 10))
        menu.add_command(label=self.t("menu.home"), command=self._show_main_window)
        menu.add_command(label=self.t("menu.dashboard"), command=self._show_token_dashboard)
        menu.add_command(label=self.t("menu.settings"), command=self._show_settings)
        menu.add_command(label=self.t("menu.history"), command=self._show_history)
        menu.add_separator()
        menu.add_command(label=self.t("menu.exit"), command=self.quit)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    # ── Settings window ────────────────────────────────────

    def _show_settings(self):
        font_name = self._font(10)[0]
        win = tk.Toplevel(self.root)
        win.title(self.t("settings.title"))
        win.geometry("480x400")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.configure(bg="#1e1e2e")

        pad = {"padx": 14, "pady": (8, 2)}

        def make_row(label_text, default_val, row_idx, show=None):
            tk.Label(
                win, text=label_text, fg="#cdd6f4", bg="#1e1e2e",
                font=(font_name, 10),
            ).grid(row=row_idx, column=0, sticky="w", **pad)

            entry = ttk.Entry(win, width=48, show=show)
            entry.insert(0, str(default_val))
            entry.grid(row=row_idx, column=1, **pad)
            return entry

        # Section header
        tk.Label(
            win, text=self.t("settings.api_settings"),
            font=(font_name, 12, "bold"),
            background="#1e1e2e", foreground="#cdd6f4",
        ).grid(row=0, column=0, columnspan=2, pady=(14, 6))

        base_entry = make_row(self.t("settings.base_url"), self.config["api_base_url"], 1)
        model_entry = make_row(self.t("settings.model"), self.config["model"], 2)

        api_key_display = (
            self.config.api_key[:8] + "****"
            if self.config.api_key
            else self.t("settings.not_set")
        )
        key_entry = make_row(self.t("settings.api_key"), api_key_display, 3)

        # Language selector
        tk.Label(
            win, text=self.t("settings.language"), fg="#cdd6f4", bg="#1e1e2e",
            font=(font_name, 10),
        ).grid(row=4, column=0, sticky="w", **pad)

        lang_var = tk.StringVar(value=self.lang)
        lang_combo = ttk.Combobox(
            win, textvariable=lang_var, state="readonly", width=46,
            values=["zh (中文)", "en (English)", "ja (日本語)"],
        )
        lang_combo.grid(row=4, column=1, **pad)

        def save_and_close():
            self.config["api_base_url"] = base_entry.get()
            self.config["model"] = model_entry.get()
            new_key = key_entry.get()
            if new_key and "****" not in new_key:
                os.environ["SCREENSHOT_AI_API_KEY"] = new_key

            # Language
            chosen = lang_var.get()
            if "zh" in chosen:
                new_lang = "zh"
            elif "ja" in chosen:
                new_lang = "ja"
            else:
                new_lang = "en"
            lang_changed = new_lang != self.lang
            self.lang = new_lang
            self.config.language = new_lang
            self.config.use_hf_mirror = (new_lang == "zh")

            if new_lang == "zh":
                os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
            else:
                os.environ.pop("HF_ENDPOINT", None)

            self.config.save()
            self._reset_client()
            win.destroy()

            if lang_changed:
                self._update_indicator_text()
                # Rebuild main window with new language
                self._main_window.rebuild()
                messagebox.showinfo(
                    self.t("settings.title"),
                    self.t("settings.saved"),
                    parent=self.root,
                )
            else:
                messagebox.showinfo(self.t("settings.title"),
                                    self.t("settings.saved"), parent=self.root)

            # Refresh main window data
            self._main_window.refresh()

        # Token usage
        used = self._token_tracker.used_today
        limit = self._token_tracker.daily_limit
        remain = self._token_tracker.remaining
        usage_text = (
            f"Tokens: {used:,} / {limit:,}  |  "
            f"Remaining: {remain:,}"
        )
        tk.Label(
            win, text=usage_text, fg="#a6adc8", bg="#1e1e2e",
            font=(font_name, 9),
        ).grid(row=5, column=0, columnspan=2, pady=(12, 0))

        tk.Button(
            win, text=self.t("settings.save"), command=save_and_close,
            bg="#a6e3a1", fg="#1e1e2e", font=(font_name, 11, "bold"),
            relief="flat", cursor="hand2", padx=20, pady=4,
        ).grid(row=6, column=0, columnspan=2, pady=(12, 0))

        win.update_idletasks()
        x = (win.winfo_screenwidth() - 480) // 2
        y = (win.winfo_screenheight() - 400) // 2
        win.geometry(f"+{x}+{y}")

    def _update_indicator_text(self):
        """Refresh the indicator label after language change."""
        def _update():
            self._ind_canvas.itemconfig(
                self._ind_label,
                text=self.t("indicator.ready"),
                font=self._font(10, bold=True),
            )
        self.root.after(0, _update)

    # ── History ────────────────────────────────────────────

    def _show_history(self):
        """Show recent answer history."""
        font_name = self._font(10)[0]
        history_files = sorted(self._log_dir.glob("*.txt"), reverse=True)[:20]

        win = tk.Toplevel(self.root)
        win.title(self.t("history.title"))
        win.geometry("600x450")
        win.attributes("-topmost", True)
        win.configure(bg="#1e1e2e")

        header = tk.Label(
            win, text=self.t("history.header"), fg="#cdd6f4", bg="#1e1e2e",
            font=(font_name, 12, "bold"),
        )
        header.pack(pady=(12, 6))

        if not history_files:
            tk.Label(
                win, text=self.t("history.no_records"), fg="#6c7086", bg="#1e1e2e",
                font=(font_name, 10),
            ).pack(expand=True)
        else:
            list_frame = tk.Frame(win, bg="#1e1e2e")
            list_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

            for hf in history_files:
                fname = hf.stem  # e.g. "2026-07-14_15-30-22"
                btn = tk.Button(
                    list_frame, text=fname, anchor="w",
                    command=lambda p=hf: self._open_history_file(p),
                    bg="#313244", fg="#cdd6f4", font=("Consolas", 10),
                    relief="flat", cursor="hand2", padx=12, pady=4,
                    activebackground="#45475a",
                )
                btn.pack(fill=tk.X, pady=1)

        tk.Button(
            win, text=self.t("history.close"), command=win.destroy,
            bg="#45475a", fg="#cdd6f4", font=(font_name, 10),
            relief="flat", cursor="hand2", padx=16, pady=4,
        ).pack(pady=(0, 12))

        win.update_idletasks()
        x = (win.winfo_screenwidth() - 600) // 2
        y = (win.winfo_screenheight() - 450) // 2
        win.geometry(f"+{x}+{y}")

    def _open_history_file(self, filepath: Path):
        """Open a history file for viewing."""
        content = filepath.read_text(encoding="utf-8")
        AnswerWindow(self.root, "", content, self.t, self.lang)

    def _show_main_window(self):
        """Show (or restore) the main application window."""
        if hasattr(self, "_main_window") and self._main_window:
            self._main_window.win.deiconify()
            self._main_window.win.lift()
            self._main_window.win.focus_force()

    # ── Token Dashboard ────────────────────────────────────

    def _show_token_dashboard(self):
        """Generate an HTML dashboard with Chart.js and open in browser."""
        self._set_status("🟡", "...", "#f9e2af")
        try:
            html = self._generate_dashboard_html(self._api_port)
            tmp = tempfile.NamedTemporaryFile(
                suffix=".html", delete=False, mode="w", encoding="utf-8"
            )
            tmp.write(html)
            tmp.close()
            os.startfile(tmp.name)
            log.info("📊 Token dashboard opened in browser")
        except Exception as exc:
            log.error(f"Dashboard error: {exc}")
            messagebox.showerror(
                "Dashboard Error",
                f"Failed to open dashboard: {exc}",
                parent=self.root,
            )
        finally:
            self._set_status("🟢", self.t("indicator.ready"), "#a6e3a1")

    def _generate_dashboard_html(self, port: int) -> str:
        """Build the HTML dashboard page (polls API for live updates)."""
        api_url = f"http://127.0.0.1:{port}/api/token-usage"
        history = self._token_tracker.get_history(30)
        limit = self._token_tracker.daily_limit
        used = self._token_tracker.used_today
        remain = self._token_tracker.remaining
        pct = round(used / limit * 100, 1) if limit > 0 else 0

        # Build history arrays for Chart.js
        history_json = json.dumps(history)
        dates_json = json.dumps([h["date"] for h in history])
        used_json = json.dumps([h["used"] for h in history])
        limit_json = json.dumps([limit] * len(history))

        return f"""<!DOCTYPE html>
<html lang="{self.lang}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{self.t("dashboard.title")}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js">
</script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
  background: #0f0f1a;
  color: #cdd6f4;
  min-height: 100vh;
  overflow-x: hidden;
}}
.particles {{
  position: fixed; top: 0; left: 0; width: 100%; height: 100%;
  pointer-events: none; z-index: 0;
}}
.particle {{
  position: absolute;
  border-radius: 50%;
  background: rgba(166, 227, 161, 0.15);
  animation: floatUp linear infinite;
}}
@keyframes floatUp {{
  0% {{ transform: translateY(100vh) scale(0); opacity: 0; }}
  10% {{ opacity: 1; }}
  90% {{ opacity: 0.5; }}
  100% {{ transform: translateY(-10vh) scale(1.5); opacity: 0; }}
}}
.container {{
  position: relative; z-index: 1;
  max-width: 960px; margin: 0 auto; padding: 32px 20px;
}}
.header {{
  text-align: center; padding: 28px 0 20px;
  border-bottom: 1px solid #313244; margin-bottom: 28px;
}}
.header h1 {{
  font-size: 28px; font-weight: 700;
  background: linear-gradient(135deg, #a6e3a1, #89b4fa);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  background-clip: text;
}}
.header p {{ color: #6c7086; margin-top: 6px; font-size: 13px; }}
.stats {{
  display: grid; grid-template-columns: repeat(4, 1fr);
  gap: 16px; margin-bottom: 32px;
}}
.stat-card {{
  background: #1e1e2e; border-radius: 14px;
  padding: 22px 18px; text-align: center;
  border: 1px solid #313244;
  transition: all 0.3s ease;
  position: relative; overflow: hidden;
}}
.stat-card:hover {{
  transform: translateY(-3px);
  border-color: #a6e3a1;
  box-shadow: 0 8px 32px rgba(166, 227, 161, 0.12);
}}
.stat-card::before {{
  content: '';
  position: absolute; top: 0; left: 0;
  width: 100%; height: 3px;
  background: linear-gradient(90deg, #a6e3a1, #89b4fa, #f9e2af);
}}
.stat-card .label {{
  font-size: 12px; color: #6c7086;
  text-transform: uppercase; letter-spacing: 1.5px;
  margin-bottom: 10px;
}}
.stat-card .value {{
  font-size: 24px; font-weight: 700;
  background: linear-gradient(135deg, #cdd6f4, #a6e3a1);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  background-clip: text;
}}
.stat-card.warn .value {{
  background: linear-gradient(135deg, #fab387, #f38ba8);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  background-clip: text;
}}
.chart-container {{
  background: #1e1e2e; border-radius: 14px;
  padding: 28px 24px;
  border: 1px solid #313244;
  position: relative;
}}
.chart-container h2 {{
  font-size: 16px; font-weight: 600; margin-bottom: 20px;
  color: #a6adc8;
}}
.chart-wrapper {{
  position: relative; height: 360px;
}}
.chart-wrapper canvas {{ width: 100% !important; }}
.footer {{
  text-align: center; padding: 20px;
  color: #45475a; font-size: 12px;
}}
@media (max-width: 640px) {{
  .stats {{ grid-template-columns: repeat(2, 1fr); }}
}}
</style>
</head>
<body>
<div class="particles" id="particles"></div>
<div class="container">
  <div class="header">
    <h1>{self.t("dashboard.title")}</h1>
    <p>{self.t("dashboard.refresh_hint")}</p>
  </div>
  <div class="stats">
    <div class="stat-card {'warn' if pct > 80 else ''}">
      <div class="label">{self.t("dashboard.today_usage")}</div>
      <div class="value">{used:,}</div>
    </div>
    <div class="stat-card">
      <div class="label">{self.t("dashboard.remaining")}</div>
      <div class="value">{remain:,}</div>
    </div>
    <div class="stat-card">
      <div class="label">{self.t("dashboard.daily_limit")}</div>
      <div class="value">{limit:,}</div>
    </div>
    <div class="stat-card {'warn' if pct > 80 else ''}">
      <div class="label">{self.t("dashboard.usage_pct")}</div>
      <div class="value">{pct}%</div>
    </div>
  </div>
  <div class="chart-container">
    <h2>{self.t("dashboard.chart_title")}</h2>
    <div class="chart-wrapper">
      <canvas id="tokenChart"></canvas>
    </div>
  </div>
  <div class="footer">
    Screenshot AI Solver &copy; {datetime.now().year}
  </div>
</div>
<script>
// Particles
(function() {{
  var c = document.getElementById('particles');
  for (var i = 0; i < 30; i++) {{
    var p = document.createElement('div');
    p.className = 'particle';
    var s = Math.random() * 6 + 2;
    p.style.width = s + 'px';
    p.style.height = s + 'px';
    p.style.left = Math.random() * 100 + '%';
    p.style.animationDuration = (Math.random() * 12 + 8) + 's';
    p.style.animationDelay = (Math.random() * 10) + 's';
    c.appendChild(p);
  }}
}})();

// Chart
(function() {{
  var ctx = document.getElementById('tokenChart');
  var data = {history_json};
  var empty = data.length === 0;

  new Chart(ctx, {{
    type: 'line',
    data: {{
      labels: empty ? [''] : {dates_json},
      datasets: [
        {{
          label: '{self.t("dashboard.chart_label")}',
          data: empty ? [0] : {used_json},
          borderColor: '#a6e3a1',
          backgroundColor: function(ctx) {{
            var g = ctx.chart.ctx.createLinearGradient(0, 0, 0, 360);
            g.addColorStop(0, 'rgba(166,227,161,0.28)');
            g.addColorStop(1, 'rgba(166,227,161,0.02)');
            return g;
          }},
          borderWidth: 2.5,
          pointRadius: 4,
          pointBackgroundColor: '#a6e3a1',
          pointBorderColor: '#1e1e2e',
          pointBorderWidth: 2,
          pointHoverRadius: 8,
          pointHoverBackgroundColor: '#f9e2af',
          tension: 0.35,
          fill: true,
        }},
        {{
          label: '{self.t("dashboard.chart_limit")}',
          data: empty ? [0] : {limit_json},
          borderColor: '#f38ba8',
          borderWidth: 1.5,
          borderDash: [8, 4],
          pointRadius: 0,
          fill: false,
        }}
      ]
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      interaction: {{
        mode: 'index', intersect: false,
      }},
      plugins: {{
        legend: {{
          labels: {{
            color: '#a6adc8',
            font: {{ size: 13 }},
            usePointStyle: true,
            pointStyleWidth: 10,
            padding: 24,
          }}
        }},
        tooltip: {{
          backgroundColor: '#313244',
          titleColor: '#cdd6f4',
          bodyColor: '#a6adc8',
          borderColor: '#45475a',
          borderWidth: 1,
          padding: 12,
          displayColors: true,
          callbacks: {{
            label: function(ctx) {{
              return ctx.dataset.label + ': ' + ctx.parsed.y.toLocaleString() + ' tokens';
            }}
          }}
        }}
      }},
      scales: {{
        x: {{
          ticks: {{ color: '#6c7086', font: {{ size: 11 }} }},
          grid: {{ color: 'rgba(69,71,90,0.3)' }},
        }},
        y: {{
          beginAtZero: true,
          ticks: {{
            color: '#6c7086',
            font: {{ size: 11 }},
            callback: function(v) {{ return v >= 1e6 ? (v/1e6).toFixed(1)+'M' : v >= 1e3 ? (v/1e3).toFixed(0)+'K' : v; }}
          }},
          grid: {{ color: 'rgba(69,71,90,0.3)' }},
        }}
      }},
      animation: {{
        duration: 1500,
        easing: 'easeOutQuart',
      }}
    }}
  }});
}})();

// ── Live polling (every 10s) ──────────────────────────
var API_URL = '{api_url}';
var tokenChart = null;

// Get chart instance via Chart.js internal registry
(function() {{
  var charts = Object.values(Chart.instances || {{}});
  tokenChart = charts[0];
}})();

function formatNum(n) {{
  return n.toLocaleString();
}}

function updateStatCards(data) {{
  var pct = data.daily_limit > 0
    ? Math.round(data.used_today / data.daily_limit * 1000) / 10
    : 0;
  var cards = document.querySelectorAll('.stat-card');
  if (cards.length >= 4) {{
    cards[0].querySelector('.value').textContent = formatNum(data.used_today);
    cards[1].querySelector('.value').textContent = formatNum(data.remaining);
    cards[2].querySelector('.value').textContent = formatNum(data.daily_limit);
    cards[3].querySelector('.value').textContent = pct + '%';
    // Toggle warn class
    [cards[0], cards[3]].forEach(function(c) {{
      c.classList.toggle('warn', pct > 80);
    }});
  }}
}}

function updateChart(data) {{
  if (!tokenChart) return;
  var dates = data.history.map(function(h) {{ return h.date; }});
  var used  = data.history.map(function(h) {{ return h.used; }});
  var limitArr = data.history.map(function() {{ return data.daily_limit; }});

  tokenChart.data.labels = dates.length ? dates : [''];
  tokenChart.data.datasets[0].data = used.length ? used : [0];
  tokenChart.data.datasets[1].data = limitArr.length ? limitArr : [0];
  tokenChart.update('none');
}}

function fetchTokenData() {{
  fetch(API_URL)
    .then(function(r) {{ return r.json(); }})
    .then(function(data) {{
      if (data.error) return;
      updateStatCards(data);
      updateChart(data);
    }})
    .catch(function() {{ /* API not ready yet, retry next tick */ }});
}}

// Initial fetch + 10s polling
fetchTokenData();
setInterval(fetchTokenData, 10000);
</script>
</body>
</html>"""

    def _get_ocr_engine(self) -> RapidOCR:
        """Lazy-load OCR engine (auto-downloads ONNX model on first use)."""
        if self._ocr is None:
            self._set_status("⏳", self.t("indicator.loading_ocr"), "#f9e2af")
            log.info(self.t("log.loading_ocr_model"))
            self._ocr = RapidOCR()
            log.info(self.t("log.ocr_loaded"))
            self._set_status("🟢", self.t("indicator.ready"), "#a6e3a1")
        return self._ocr

    def _get_client(self) -> OpenAI:
        """Lazy-load OpenAI client."""
        if self._client is None:
            api_key = self.config.api_key
            if not api_key:
                raise RuntimeError(self.t("error.no_key_detail"))
            self._client = OpenAI(
                api_key=api_key,
                base_url=self.config.api_base_url,
                timeout=self.config["api_timeout"],
            )
        return self._client

    def _reset_client(self):
        """Reset client (called after config change)."""
        self._client = None
        self._ocr = None

    def _set_status(self, dot: str, text: str, color: str):
        """Update the floating indicator status (dot = emoji, color = text fill)."""
        def _update():
            self._ind_canvas.itemconfig(self._ind_label, text=text, fill=color)
        self.root.after(0, _update)

    def _preload_ocr(self):
        """Preload OCR model in background to avoid waiting on first Shift+G."""
        def _load():
            self._set_status("🟡", self.t("indicator.preloading"), "#f9e2af")
            log.info(self.t("log.preloading"))
            try:
                self._get_ocr_engine()
                log.info(self.t("log.preload_done"))
                self._set_status("🟢", self.t("indicator.ready"), "#a6e3a1")
            except Exception as e:
                log.error(self.t("log.preload_failed", error=e))
                self._set_status("🟠", self.t("indicator.model_failed"), "#fab387")
        threading.Thread(target=_load, daemon=True).start()

    def _take_screenshot(self) -> Image.Image:
        """Full-screen screenshot + preprocessing."""
        log.info(self.t("log.screenshot"))
        img = ImageGrab.grab(all_screens=True)

        # Scale down if too wide (for faster OCR)
        max_w = self.config["max_image_width"]
        if img.width > max_w:
            ratio = max_w / img.width
            new_size = (max_w, int(img.height * ratio))
            img = img.resize(new_size, Image.LANCZOS)
            log.info(self.t("log.resized", size=str(img.size)))

        # Grayscale + contrast enhancement
        img = img.convert("L")
        img = ImageEnhance.Contrast(img).enhance(1.8)
        img = ImageEnhance.Sharpness(img).enhance(1.3)

        log.info(self.t("log.screenshot_done", size=str(img.size)))
        return img

    def _extract_text(self, image: Image.Image) -> str:
        """OCR text extraction."""
        log.info(self.t("log.ocr_scanning"))
        ocr = self._get_ocr_engine()

        # RapidOCR accepts numpy array or PIL Image
        result, elapse = ocr(image)

        if not result:
            log.info(self.t("log.ocr_no_text"))
            return ""

        # result is list of [box, text, confidence]
        lines = []
        for item in result:
            text = item[1]   # text content
            conf = item[2]   # confidence
            if conf > 0.3:
                lines.append(text)

        full_text = "\n".join(lines)

        log.info(self.t("log.ocr_result",
                        lines=str(len(lines)),
                        chars=str(len(full_text)),
                        time=sum(elapse)))
        if full_text:
            preview = full_text[:100].replace("\n", " ⏎ ")
            log.info(self.t("log.ocr_preview", preview=preview))

        return full_text

    def _ask_ai(self, screen_text: str) -> str:
        """Call AI API for answer (with daily token limit check)."""
        # ── Check daily token limit ──
        if self._token_tracker.is_exceeded:
            raise TokenLimitExceeded(
                self.t("token.limit_detail",
                       used=self._token_tracker.used_today,
                       limit=self._token_tracker.daily_limit)
            )

        log.info(self.t("log.ai_calling"))
        log.info(
            f"  Tokens: {self._token_tracker.used_today:,} used / "
            f"{self._token_tracker.daily_limit:,} limit"
        )
        client = self._get_client()

        # Use the language-aware system prompt from I18N
        system_prompt = self.t("system_prompt")

        response = client.chat.completions.create(
            model=self.config["model"],
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",
                 "content": (
                     f"以下は画面から認識されたテキストです。中の問題を解いてください：\n\n{screen_text}"
                     if self.lang == "ja" else
                     f"Here is the text recognized from the screen. Please help me solve the questions within it:\n\n{screen_text}"
                     if self.lang == "en" else
                     f"以下是屏幕上识别到的文字内容，请帮我解答其中的题目：\n\n{screen_text}"
                 )},
            ],
            temperature=0.7,
            max_tokens=4096,
        )

        # ── Accumulate token usage ──
        if response.usage and response.usage.total_tokens:
            self._token_tracker.add(response.usage.total_tokens)
            log.info(f"  +{response.usage.total_tokens} tokens → "
                     f"{self._token_tracker.used_today:,} used today "
                     f"({self._token_tracker.remaining:,} remaining)")
            # Refresh main window token display
            self.root.after(0, self._main_window.refresh)

        answer = response.choices[0].message.content or "(AI returned nothing)"
        log.info(self.t("log.ai_done", chars=str(len(answer))))
        return answer

    def _save_history(self, question: str, answer: str):
        """Save Q&A record locally."""
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filepath = self._log_dir / f"{timestamp}.txt"
        if self.lang == "ja":
            content = (
                f"日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"{'='*50}\n"
                f"認識テキスト:\n{question}\n\n"
                f"{'='*50}\n"
                f"AI 解答:\n{answer}\n"
            )
        elif self.lang == "en":
            content = (
                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"{'='*50}\n"
                f"Recognized text:\n{question}\n\n"
                f"{'='*50}\n"
                f"AI Answer:\n{answer}\n"
            )
        else:
            content = (
                f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"{'='*50}\n"
                f"识别文字:\n{question}\n\n"
                f"{'='*50}\n"
                f"AI 解答:\n{answer}\n"
            )
        filepath.write_text(content, encoding="utf-8")

    def _ocr_and_ai(self, img: Image.Image):
        """OCR + AI answering workflow (runs in background thread)."""
        try:
            # OCR
            text = self._extract_text(img)

            if not text.strip():
                self.root.after(
                    0,
                    lambda: AnswerWindow(
                        self.root, "",
                        f"{self.t('answer.no_text_title')}\n\n"
                        f"{self.t('answer.no_text_body')}",
                        self.t, self.lang,
                    ),
                )
                return

            # AI
            answer = self._ask_ai(text)

            # Display
            self.root.after(
                0,
                lambda: AnswerWindow(self.root, text, answer, self.t, self.lang),
            )

            # Save history
            self._save_history(text, answer)

        except TokenLimitExceeded as exc:
            log.warning(f"Token limit: {exc}")
            self.root.after(
                0,
                lambda e=exc: AnswerWindow(
                    self.root, "",
                    self.t("token.limit_title") + "\n\n" + str(e),
                    self.t, self.lang,
                ),
            )
        except Exception as exc:
            log.error(f"Processing error: {exc}", exc_info=True)
            self.root.after(
                0,
                lambda e=exc: AnswerWindow(
                    self.root, "",
                    self.t("error.processing_detail", error=str(e)),
                    self.t, self.lang,
                ),
            )
        finally:
            self._lock.release()
            self._set_status("🟢", self.t("indicator.ready"), "#a6e3a1")

    def _start_selection(self):
        """Enter region selection mode → screenshot → background OCR+AI (main thread)."""
        # Prevent double-trigger
        if not self._lock.acquire(blocking=False):
            log.info(self.t("log.skipped"))
            return

        try:
            self._set_status("🔴", self.t("indicator.select_region"), "#f38ba8")

            # Screenshot full screen
            img = self._take_screenshot()

            # Enter region selection
            selector = RegionSelector(self.root, img,
                                      hint_text=self.t("region.hint"))
            self.root.wait_window(selector.win)

            if selector.cancelled:
                log.info(self.t("log.cancelled"))
                return

            x1, y1, x2, y2 = selector.region
            log.info(self.t("log.region_selected",
                            x1=str(x1), y1=str(y1),
                            x2=str(x2), y2=str(y2),
                            w=str(x2 - x1), h=str(y2 - y1)))

            # Crop selected region
            cropped = img.crop(selector.region)

            # Start background thread for OCR + AI
            threading.Thread(target=self._ocr_and_ai, args=(cropped,), daemon=True).start()

        except Exception as exc:
            log.error(f"Selection error: {exc}", exc_info=True)
            self._lock.release()
            self._set_status("🟢", self.t("indicator.ready"), "#a6e3a1")

    # ── Keyboard listener ──────────────────────────────────

    def _on_press(self, key):
        """Key press event."""
        try:
            # Track modifier keys
            if key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
                self._current_keys.add("shift")
            elif hasattr(key, "char") and key.char:
                ch = key.char.lower()
                if ch == "g":
                    self._current_keys.add("g")

            # Detect Shift+G combo
            if "shift" in self._current_keys and "g" in self._current_keys:
                self._current_keys.clear()  # Prevent repeated triggers
                log.info(self.t("log.hotkey"))
                self.root.after(0, self._start_selection)

        except Exception as exc:
            log.error(f"Keyboard event error: {exc}")

    def _on_release(self, key):
        """Key release event."""
        try:
            if key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
                self._current_keys.discard("shift")
            elif hasattr(key, "char") and key.char:
                ch = key.char.lower()
                if ch == "g":
                    self._current_keys.discard("g")
        except Exception:
            pass

    # ── Lifecycle ──────────────────────────────────────────

    def _make_tray_image(self):
        """Generate a 32x32 tray icon."""
        img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle([1, 1, 30, 30], radius=8, fill="#a6e3a1")
        draw.text((16, 16), "AI", fill="#1e1e2e", anchor="mm",
                  font_size=12, font_family="Arial")
        return img

    def _start_tray(self):
        """Start system tray icon in a background thread."""
        if not HAS_TRAY:
            return
        icon = pystray.Icon(
            "ScreenshotAISolver",
            self._make_tray_image(),
            "Screenshot AI Solver",
            menu=pystray.Menu(
                pystray.MenuItem(
                    self.t("menu.home"),
                    lambda: self.root.after(0, self._show_main_window),
                    default=True,
                ),
                pystray.MenuItem(
                    self.t("menu.settings"),
                    lambda: self.root.after(0, self._show_settings),
                ),
                pystray.MenuItem(
                    self.t("menu.dashboard"),
                    lambda: self.root.after(0, self._show_token_dashboard),
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    self.t("menu.exit"),
                    lambda: self.root.after(0, self.quit),
                ),
            ),
        )
        self._tray_icon = icon
        threading.Thread(target=icon.run, daemon=True).start()

    def run(self):
        """Launch the application."""
        # Startup checks
        if not self.config.api_key:
            env_path = self.config.app_dir / ".env"
            log.warning(self.t("log.no_api_warning1"))
            log.warning(f"   Expected .env at: {env_path}")
            log.warning(self.t("log.no_api_warning2"))
            log.warning(self.t("log.no_api_warning3"))
        else:
            log.info(self.t("log.api_configured",
                            url=self.config.api_base_url,
                            model=self.config.model))

        log.info(self.t("log.config_loaded",
                        path=str(self.config.CONFIG_DIR),
                        lang=self.lang))

        log.info(self.t("log.listening"))
        log.info(
            f"📊 Daily tokens: {self._token_tracker.used_today:,} used / "
            f"{self._token_tracker.daily_limit:,} limit "
            f"({self._token_tracker.remaining:,} remaining)"
        )

        # Start system tray
        self._start_tray()

        # Preload OCR model in background
        self._preload_ocr()

        # Fade in main window
        self.root.after(50, lambda: self._animate_fade_in(self._main_window.win))

        # Start keyboard listener (background thread)
        self.listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self.listener.start()

        # Enter tkinter main loop (main thread)
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.quit()

    def _animate_fade_in(self, win, start=0.0, step=0.06, final=1.0):
        """Smooth window fade-in animation."""
        win.attributes("-alpha", start)
        if start < final:
            win.after(16, lambda: self._animate_fade_in(win, start + step, step, final))

    def quit(self):
        """Graceful shutdown."""
        log.info(self.t("log.quitting"))
        if hasattr(self, "listener") and self.listener.is_alive():
            self.listener.stop()
        if HAS_TRAY and hasattr(self, "_tray_icon"):
            self._tray_icon.stop()
        self.root.quit()
        self.root.destroy()
        sys.exit(0)


# ╔══════════════════════════════════════════════════════════════════╗
# ║                         Entry Point                            ║
# ╚══════════════════════════════════════════════════════════════════╝

if __name__ == "__main__":
    # Print banner (always show both for brand recognition)
    print(r"""
   _____                _                    _    ___   _____      _
  / ____|              | |                  | |  / _ \ |_   _|    (_)
 | (___   ___ _ __ ___ | |__   ___ _ __ ___ | |_| | | |  | | _ __  _
  \___ \ / __| '__/ _ \| '_ \ / _ \ '__/ _ \| __| | | |  | || '__|| |
  ____) | (__| | | (_) | |_) |  __/ | | (_) | |_| |_| | _| || |   | |
 |_____/ \___|_|  \___/|_.__/ \___|_|  \___/ \__|\___(_)___|_|   |_|

    Screenshot AI Solver v1.0  |  Shift+G to solve  |  Right-click for settings
""")
    app = ScreenshotAISolver()
    try:
        app.run()
    except KeyboardInterrupt:
        app.quit()
