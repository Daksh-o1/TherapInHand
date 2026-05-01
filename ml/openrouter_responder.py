import json
import logging
import socket
import time
import urllib.error
import urllib.request

from config import (
    OPENROUTER_MODEL,
    openrouter_runtime_settings,
)


_LAST_ERROR = ""
_LAST_MODEL = ""
_LAST_STATUS_CODE = None
_LAST_REQUEST_URL = "https://openrouter.ai/api/v1/chat/completions"
LOGGER = logging.getLogger(__name__)
RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}


def openrouter_enabled() -> bool:
    settings = openrouter_runtime_settings()
    return bool(settings["enabled"])


def log_openrouter_startup_status():
    settings = openrouter_runtime_settings()
    LOGGER.info("[OpenRouter] Enabled: %s", settings["enabled"])
    LOGGER.info("[OpenRouter] API Key Found: %s", "Yes" if settings["api_key"] else "No")
    LOGGER.info("[OpenRouter] Model: %s", settings["model"])
    LOGGER.info("[OpenRouter] Timeout: %s", settings["timeout"])


def _build_messages(user_message: str, analysis: dict) -> list:
    intent = analysis.get("intent", "general_query")
    sentiment = analysis.get("sentiment", "neutral")
    topic = analysis.get("topic", "general")

    system_prompt = (
        "You are TherapInHand, a warm, professional wellbeing support chatbot. "
        "Reply in natural, supportive English. Keep answers concise, grounded, and practical. "
        "For stress, anxiety, loneliness, low mood, sleep trouble, overwhelm, or burnout, validate the feeling and offer 2 to 4 realistic next steps. "
        "For physical symptoms, give general self-care guidance and clear red flags for when a doctor is needed. "
        "Do not diagnose, prescribe, or claim to replace a clinician. "
        "If the user asks about therapy or professional support, encourage it without pressure. "
        "If there are self-harm or immediate danger cues, prioritize urgent human support."
    )
    context_prompt = (
        f"Classifier context: intent={intent}; sentiment={sentiment}; topic={topic}. "
        "Use this as context only. Trust the user message if it is clearer than the classifier."
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": context_prompt},
        {"role": "user", "content": user_message},
    ]


def generate_openrouter_response(user_message: str, analysis: dict):
    global _LAST_ERROR, _LAST_MODEL, _LAST_STATUS_CODE
    _LAST_ERROR = ""
    _LAST_STATUS_CODE = None

    if not openrouter_enabled():
        LOGGER.info("[AI] OpenRouter request skipped because integration is disabled.")
        return None

    settings = openrouter_runtime_settings()
    api_key = settings["api_key"]
    if not api_key:
        _LAST_ERROR = "OPENROUTER_API_KEY is not set"
        LOGGER.warning("[AI] Error: %s", _LAST_ERROR)
        return None

    model = settings["model"] or OPENROUTER_MODEL or "openrouter/auto"
    _LAST_MODEL = model
    payload = {
        "model": model,
        "messages": _build_messages(user_message, analysis),
        "max_tokens": settings["max_tokens"],
        "temperature": settings["temperature"],
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings["site_url"],
        "X-Title": settings["app_name"],
    }

    LOGGER.info("[AI] OpenRouter request triggered")
    LOGGER.info(
        "[AI] Request payload: url=%s model=%s timeout=%s max_retries=%s auth_header=%s body_keys=%s prompt_length=%s",
        _LAST_REQUEST_URL,
        model,
        settings["timeout"],
        settings["max_retries"],
        "present" if api_key else "missing",
        sorted(payload.keys()),
        len(str(user_message or "")),
    )

    attempts = max(1, int(settings.get("max_retries", 0)) + 1)
    data = None
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(
            _LAST_REQUEST_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=settings["timeout"]) as response:
                _LAST_STATUS_CODE = getattr(response, "status", None)
                LOGGER.info("[AI] Response received: status=%s attempt=%s", _LAST_STATUS_CODE, attempt)
                body = response.read().decode("utf-8")
                data = json.loads(body)
                break
        except urllib.error.HTTPError as exc:
            _LAST_STATUS_CODE = exc.code
            error_body = exc.read().decode("utf-8", errors="replace")
            _LAST_ERROR = f"OpenRouter HTTP {exc.code}: {error_body[:300]}"
            LOGGER.warning("[AI] Error: %s", _LAST_ERROR)
            if exc.code in {401, 403}:
                LOGGER.warning("[AI] Invalid auth or access issue while calling OpenRouter.")
                return None
            if exc.code not in RETRYABLE_STATUS_CODES or attempt >= attempts:
                return None
        except urllib.error.URLError as exc:
            _LAST_ERROR = f"OpenRouter URL error: {exc}"
            LOGGER.warning("[AI] Error: %s", _LAST_ERROR)
            if attempt >= attempts:
                return None
        except socket.timeout as exc:
            _LAST_ERROR = f"OpenRouter timeout after {settings['timeout']}s: {exc}"
            LOGGER.warning("[AI] Error: %s", _LAST_ERROR)
            if attempt >= attempts:
                return None
        except Exception as exc:
            _LAST_ERROR = f"OpenRouter request failed: {exc}"
            LOGGER.warning("[AI] Error: %s", _LAST_ERROR)
            return None

        backoff_seconds = max(0.0, float(settings.get("retry_backoff_seconds", 1.5))) * attempt
        LOGGER.info("[AI] Retrying OpenRouter request in %.2fs (attempt %s/%s)", backoff_seconds, attempt + 1, attempts)
        time.sleep(backoff_seconds)

    if data is None:
        return None

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        _LAST_ERROR = f"Unexpected OpenRouter response: {exc}"
        LOGGER.warning("[AI] Error: %s", _LAST_ERROR)
        return None

    cleaned = str(content).strip()
    LOGGER.info("[AI] Response received: content_length=%s", len(cleaned))
    return cleaned or None


def direct_openrouter_test(prompt="Reply with: OpenRouter connection successful."):
    return generate_openrouter_response(
        prompt,
        {
            "language": "en",
            "intent": "general_query",
            "sentiment": "neutral",
            "topic": "general",
        },
    )


def openrouter_status() -> dict:
    settings = openrouter_runtime_settings()
    return {
        "enabled": bool(settings["enabled"]),
        "configured": bool(settings["api_key"]),
        "model": settings["model"] or _LAST_MODEL or "openrouter/auto",
        "last_error": _LAST_ERROR,
        "last_status_code": _LAST_STATUS_CODE,
        "request_url": _LAST_REQUEST_URL,
        "timeout": settings["timeout"],
    }
