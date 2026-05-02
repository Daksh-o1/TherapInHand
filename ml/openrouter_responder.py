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
_LAST_LATENCY_MS = None
_LAST_FALLBACK_REASON = ""
LOGGER = logging.getLogger(__name__)
RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
URL_OPEN = urllib.request.urlopen


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
    message_topic = analysis.get("message_topic", "general")
    response_style = analysis.get("response_style", "balanced")

    system_prompt = (
        "You are TherapInHand, a conversational support chatbot. "
        "Current user message has the highest priority, then topic continuity, then recent context, then older emotional memory. "
        "Reply in natural English and match the user's current mode instead of forcing therapy tone. "
        "Keep replies concise by default: casual chat in 1 to 2 sentences, normal medical replies in 2 to 4 short sentences, and more detail only when the user asks for it. "
        "Answer the user's main question first before extra context. If it is yes/no, say yes, no, or usually first. "
        "For jokes, greetings, gratitude, fun chat, or technical questions, answer normally and directly. "
        "For stress, anxiety, loneliness, low mood, sleep trouble, overwhelm, or burnout, validate briefly and offer practical next steps without repetitive therapy phrases. "
        "For vague symptoms, ask focused clarifying questions instead of sounding generic. "
        "For physical symptoms or medication requests, give safe general self-care or OTC guidance, include hydration or rest when relevant, and name urgent red flags only when relevant. "
        "Do not diagnose, prescribe, or claim to replace a clinician. "
        "Do not refuse routine OTC guidance when the user asks what helps a common symptom like fever, headache, or cold. "
        "Avoid phrases like 'I'm here with you', 'tell me more', 'that sounds difficult', or corporate-sounding filler unless clearly needed. "
        "If the user asks about therapy or professional support, encourage it without pressure. "
        "If there are self-harm or immediate danger cues, prioritize urgent human support."
    )
    context_prompt = (
        f"Classifier context: intent={intent}; sentiment={sentiment}; topic={topic}; message_topic={message_topic}; response_style={response_style}. "
        "Use this as context only. Trust the user message if it is clearer than the classifier."
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": context_prompt},
        {"role": "user", "content": user_message},
    ]


def _extract_text_content(content):
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
                parts.append(str(item.get("text")).strip())
            elif isinstance(item, str):
                parts.append(item.strip())
        return "\n".join(part for part in parts if part).strip()
    return ""


def _parse_openrouter_response(data):
    if not isinstance(data, dict):
        raise TypeError("response payload was not a JSON object")
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise KeyError("choices")
    first_choice = choices[0] or {}
    message = first_choice.get("message") if isinstance(first_choice, dict) else None
    content = ""
    if isinstance(message, dict):
        content = _extract_text_content(message.get("content"))
    if not content and isinstance(first_choice, dict):
        content = _extract_text_content(first_choice.get("text"))
    if not content:
        raise ValueError("empty_response")
    return content


def generate_openrouter_response(user_message: str, analysis: dict):
    global _LAST_ERROR, _LAST_MODEL, _LAST_STATUS_CODE, _LAST_LATENCY_MS, _LAST_FALLBACK_REASON
    _LAST_ERROR = ""
    _LAST_STATUS_CODE = None
    _LAST_LATENCY_MS = None
    _LAST_FALLBACK_REASON = ""

    if not openrouter_enabled():
        _LAST_FALLBACK_REASON = "disabled"
        LOGGER.info("[AI] OpenRouter request skipped because integration is disabled.")
        return None

    settings = openrouter_runtime_settings()
    api_key = settings["api_key"]
    if not api_key:
        _LAST_ERROR = "OPENROUTER_API_KEY is not set"
        _LAST_FALLBACK_REASON = "missing_api_key"
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
            started_at = time.perf_counter()
            with URL_OPEN(request, timeout=settings["timeout"]) as response:
                _LAST_STATUS_CODE = getattr(response, "status", None)
                _LAST_LATENCY_MS = round((time.perf_counter() - started_at) * 1000, 2)
                LOGGER.info("[AI] Response received: status=%s attempt=%s", _LAST_STATUS_CODE, attempt)
                body = response.read().decode("utf-8")
                data = json.loads(body)
                break
        except urllib.error.HTTPError as exc:
            _LAST_STATUS_CODE = exc.code
            error_body = exc.read().decode("utf-8", errors="replace")
            _LAST_ERROR = f"OpenRouter HTTP {exc.code}: {error_body[:300]}"
            _LAST_FALLBACK_REASON = f"http_{exc.code}"
            LOGGER.warning("[AI] Error: %s", _LAST_ERROR)
            if exc.code in {401, 403}:
                LOGGER.warning("[AI] Invalid auth or access issue while calling OpenRouter.")
                return None
            if exc.code not in RETRYABLE_STATUS_CODES or attempt >= attempts:
                return None
        except urllib.error.URLError as exc:
            _LAST_ERROR = f"OpenRouter URL error: {exc}"
            _LAST_FALLBACK_REASON = "url_error"
            LOGGER.warning("[AI] Error: %s", _LAST_ERROR)
            if attempt >= attempts:
                return None
        except socket.timeout as exc:
            _LAST_ERROR = f"OpenRouter timeout after {settings['timeout']}s: {exc}"
            _LAST_FALLBACK_REASON = "timeout"
            LOGGER.warning("[AI] Error: %s", _LAST_ERROR)
            if attempt >= attempts:
                return None
        except Exception as exc:
            _LAST_ERROR = f"OpenRouter request failed: {exc}"
            _LAST_FALLBACK_REASON = "request_exception"
            LOGGER.warning("[AI] Error: %s", _LAST_ERROR)
            return None

        backoff_seconds = max(0.0, float(settings.get("retry_backoff_seconds", 1.5))) * attempt
        LOGGER.info("[AI] Retrying OpenRouter request in %.2fs (attempt %s/%s)", backoff_seconds, attempt + 1, attempts)
        time.sleep(backoff_seconds)

    if data is None:
        _LAST_FALLBACK_REASON = _LAST_FALLBACK_REASON or "no_data"
        return None

    try:
        content = _parse_openrouter_response(data)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        _LAST_ERROR = f"Unexpected OpenRouter response: {exc}"
        _LAST_FALLBACK_REASON = "malformed_or_empty_response"
        LOGGER.warning("[AI] Error: %s", _LAST_ERROR)
        return None

    cleaned = str(content).strip()
    if not cleaned:
        _LAST_ERROR = "OpenRouter returned empty content"
        _LAST_FALLBACK_REASON = "empty_response"
        LOGGER.warning("[AI] Error: %s", _LAST_ERROR)
        return None
    LOGGER.info("[AI] Response received: content_length=%s latency_ms=%s", len(cleaned), _LAST_LATENCY_MS)
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
        "last_latency_ms": _LAST_LATENCY_MS,
        "last_fallback_reason": _LAST_FALLBACK_REASON,
        "request_url": _LAST_REQUEST_URL,
        "timeout": settings["timeout"],
    }
