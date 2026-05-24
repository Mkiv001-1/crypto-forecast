"""
Universal AI client for all models via OpenRouter.
Single API key, OpenAI-compatible format.
All AI providers (claude, gpt-4o, deepseek, gemini, sonar-pro) are called
through https://openrouter.ai/api/v1/chat/completions
"""

import json
import logging
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class RateLimitError(Exception):
    """Raised when OpenRouter returns 429 and caller should back off or skip."""
    def __init__(self, model: str, retry_after: int = 30):
        self.model = model
        self.retry_after = retry_after
        super().__init__(f"Rate limited: {model} (retry after {retry_after}s)")


_APP_URL = "https://forecast-robot.local"


class AIClient:
    """Calls any OpenRouter-supported model with a single API key."""

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("OpenRouter API key is required")
        self.api_key = api_key
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": _APP_URL,
            "Content-Type": "application/json",
        })

    def call(
        self,
        model: str,
        user_prompt: str,
        system_prompt: str = "You are a professional algorithmic trader. Respond only with valid JSON.",
        temperature: float = 0.2,
        max_tokens: int = 2000,
        max_retries: int = 3,
        json_mode: bool = False,
    ) -> str:
        """
        Call a model via OpenRouter.
        Returns the assistant message content string.
        Raises on unrecoverable error after max_retries.
        """
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens":  max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        # Circuit-breaker guard
        try:
            from circuit_breaker import is_open
            if is_open():
                raise RuntimeError(f"circuit_breaker: OpenRouter OPEN — {model} call rejected")
        except ImportError:
            pass  # circuit_breaker not yet available

        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                logger.debug(f"[{model}] attempt {attempt}/{max_retries}")
                response = self._session.post(
                    _OPENROUTER_URL,
                    json=payload,
                    timeout=120,
                )
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                logger.debug(f"[{model}] OK, {len(content)} chars")
                try:
                    from circuit_breaker import record_success
                    record_success()
                except ImportError:
                    pass
                return content

            except requests.exceptions.Timeout as e:
                logger.warning(f"[{model}] timeout on attempt {attempt}: {e}")
                last_error = e
                try:
                    from circuit_breaker import record_failure
                    record_failure()
                except ImportError:
                    pass
                time.sleep(5 * attempt)

            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response is not None else 0
                body = {}
                try:
                    body = e.response.json()
                except Exception:
                    pass
                logger.error(f"[{model}] HTTP {status} on attempt {attempt}: {body}")
                last_error = e
                if status in (401, 402, 403, 404):
                    break  # non-retryable billing/auth errors — do NOT trip circuit breaker
                if status == 429:
                    retry_after = 30
                    try:
                        retry_after = int(
                            body.get("error", {}).get("metadata", {})
                            .get("retry_after_seconds", 30)
                        )
                    except Exception:
                        pass
                    logger.warning(f"[{model}] rate-limited (retry_after={retry_after}s) — skipping")
                    raise RateLimitError(model, retry_after)
                else:
                    try:
                        from circuit_breaker import record_failure
                        record_failure()
                    except ImportError:
                        pass
                    time.sleep(5 * attempt)

            except RateLimitError:
                raise  # propagate immediately — do not retry

            except Exception as e:
                logger.error(f"[{model}] error on attempt {attempt}: {e}")
                last_error = e
                try:
                    from circuit_breaker import record_failure
                    record_failure()
                except ImportError:
                    pass
                time.sleep(5 * attempt)

        raise RuntimeError(f"All {max_retries} attempts failed for model '{model}': {last_error}")


def get_ai_client(db_manager) -> Optional[AIClient]:
    """
    Create AIClient using the OpenRouter API key from the database config.
    Returns None if the key is not configured.
    """
    api_key = db_manager.get_config_value("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        logger.warning("OPENROUTER_API_KEY is not configured in DB config table")
        return None
    return AIClient(api_key)


def get_active_ai_models(db_manager) -> list:
    """
    Return list of active AI model dicts from providers table.
    Each dict: {name, model, temperature, max_tokens, rate_limit}
    If OPENROUTER_FREE_ONLY=true, appends :free suffix to model IDs.
    """
    try:
        free_only = db_manager.get_config_value("OPENROUTER_FREE_ONLY", "false").strip().lower() == "true"
        df = db_manager.read_sheet("Providers")
        if df.empty:
            return []
        ai_df = df[(df["type"] == "ai") & (df["active"].astype(int) == 1)]
        if ai_df.empty:
            return []
        result = []
        for _, row in ai_df.iterrows():
            model_id = str(row.get("model", ""))
            if free_only and model_id and not model_id.endswith(":free"):
                model_id = model_id + ":free"
            result.append({
                "name":        str(row.get("name", "")),
                "model":       model_id,
                "temperature": float(row.get("temperature", 0.2)),
                "max_tokens":  int(row.get("max_tokens", 2000)),
                "rate_limit":  int(row.get("rate_limit", 60)),
            })
        if free_only:
            logger.info(f"OPENROUTER_FREE_ONLY=true — using :free model variants")
        return result
    except Exception as e:
        logger.error(f"Error reading AI models: {e}")
        return []
