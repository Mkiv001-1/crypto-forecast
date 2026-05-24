"""Shared GUI constants (formerly defined in gui_main.py)."""

from scripts.core.market_regime import ALL_METHODS

METHODS = ALL_METHODS

STATUSES = ["NEW", "EVALUATED", "ERROR"]

METHOD_LABELS = {
    "momentum_trend": "📈 Momentum Trend",
    "price_action": "🕯 Price Action",
    "relative_strength": "💪 Relative Strength",
    "volatility": "⚡ Volatility Breakout",
    "mean_reversion": "↩ Mean Reversion",
    "volume_breakout": "📦 Volume Breakout",
}

# Aliases used by tab modules split from gui_main
_METHOD_LABELS = METHOD_LABELS

TASK_STATUS_COLORS = {
    "ok": "#c8e6c9",
    "success": "#c8e6c9",
    "error": "#ffcdd2",
    "failed": "#ffcdd2",
    "running": "#fff9c4",
    "": "#ffffff",
}

_TASK_STATUS_COLORS = TASK_STATUS_COLORS

HB_OK = "✅"
HB_ERR = "❌"
_HB_OK = HB_OK
_HB_ERR = HB_ERR

# Default OpenRouter model slugs for provider combo boxes (until catalog is refreshed)
OPENROUTER_MODELS = [
    "anthropic/claude-sonnet-4",
    "anthropic/claude-3.5-sonnet",
    "anthropic/claude-3.5-haiku",
    "anthropic/claude-3-opus",
    "openai/gpt-4.1",
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "openai/o3",
    "openai/o3-mini",
    "openai/o4-mini",
    "deepseek/deepseek-chat-v3-0324",
    "deepseek/deepseek-chat",
    "deepseek/deepseek-r1",
    "deepseek/deepseek-r1-distill-llama-70b",
    "google/gemini-2.5-pro-preview",
    "google/gemini-2.5-flash-preview",
    "google/gemini-2.0-flash-001",
    "perplexity/sonar-pro",
    "perplexity/sonar",
    "perplexity/sonar-reasoning-pro",
    "meta-llama/llama-4-maverick",
    "meta-llama/llama-3.3-70b-instruct",
    "mistralai/mistral-large-2411",
    "mistralai/mistral-small-3.1-24b-instruct",
    "x-ai/grok-3-mini-beta",
    "x-ai/grok-2-1212",
    "qwen/qwen-2.5-72b-instruct",
    "qwen/qwq-32b",
]

_OPENROUTER_MODELS = OPENROUTER_MODELS
