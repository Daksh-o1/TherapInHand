import random
import logging

from ml.openrouter_responder import generate_openrouter_response, openrouter_enabled


SESSION_CHAT_HISTORY_KEY = "chat_history"
SESSION_MAX_HISTORY = 10
SESSION_TEXT_LIMIT = 120
UNSAFE_AI_MARKERS = [
    "kill yourself",
    "end your life",
    "hurt yourself",
    "self-harm",
    "nobody can help you",
    "you should die",
]
LOGGER = logging.getLogger(__name__)
CONVERSATIONAL_QUERY_MARKERS = [
    "tell me a joke", "joke", "make me laugh", "who are you", "what are you",
    "what can you do", "tell me about yourself", "chat with me", "talk to me",
    "say something fun", "say something interesting", "how are you", "what's up",
    "whats up", "hello there", "hi there"
]
NON_MEDICAL_QUERY_MARKERS = [
    "movie", "music", "song", "sports", "cricket", "football", "weather",
    "coding", "python", "javascript", "math", "recipe", "news", "politics",
]
MEDICAL_QUERY_MARKERS = [
    "fever", "cough", "cold", "flu", "headache", "migraine", "dizziness",
    "nausea", "stomach", "pain", "malaria", "jaundice", "dengue", "typhoid",
    "stress", "anxiety", "panic", "sad", "sleep", "therapy", "doctor", "symptom",
]


def _trim_text(text, limit=SESSION_TEXT_LIMIT):
    text = " ".join(str(text or "").split())
    return text[:limit].strip()


def get_session_chat_history(session_store):
    history = session_store.get(SESSION_CHAT_HISTORY_KEY, [])
    if not isinstance(history, list):
        return []
    cleaned = []
    for item in history[-SESSION_MAX_HISTORY:]:
        if not isinstance(item, dict):
            continue
        cleaned.append({
            "user": _trim_text(item.get("user", "")),
            "bot": _trim_text(item.get("bot", "")),
            "intent": item.get("intent", "general_query"),
            "sentiment": item.get("sentiment", "neutral"),
            "topic": item.get("topic", "general"),
            "entities": item.get("entities", {}),
        })
    return cleaned


def get_recent_user_messages(session_store, limit=3):
    history = get_session_chat_history(session_store)
    return [item.get("user", "") for item in history if item.get("user")][-limit:]


def update_session_chat_history(session_store, user_message, bot_response, meta=None):
    history = get_session_chat_history(session_store)
    entry = {
        "user": _trim_text(user_message),
        "bot": _trim_text(bot_response),
        "intent": (meta or {}).get("intent", "general_query"),
        "sentiment": (meta or {}).get("sentiment", "neutral"),
        "topic": (meta or {}).get("topic", "general"),
        "entities": (meta or {}).get("entities", {}),
    }
    if history and history[-1] == entry:
        session_store[SESSION_CHAT_HISTORY_KEY] = history[-SESSION_MAX_HISTORY:]
        session_store.modified = True
        return
    session_store[SESSION_CHAT_HISTORY_KEY] = (history + [entry])[-SESSION_MAX_HISTORY:]
    session_store.modified = True


def repeated_intent_count(session_store, intent):
    history = get_session_chat_history(session_store)
    count = 0
    for item in reversed(history):
        if item.get("intent") == intent:
            count += 1
        else:
            break
    return count


def repeated_topic_count(session_store, topic, limit=6):
    if not topic or topic == "general":
        return 0
    history = get_session_chat_history(session_store)[-limit:]
    return sum(1 for item in history if item.get("topic") == topic)


def is_complex_question(text):
    text = (text or "").strip()
    lowered = text.lower()
    complexity_markers = [
        "why", "how exactly", "difference between", "compare", "should i", "explain",
        "what does it mean", "is it normal", "can you analyze", "tell me in detail",
    ]
    return len(text.split()) >= 22 or sum(marker in lowered for marker in complexity_markers) >= 1


def _is_casual_ai_candidate(intent, text):
    lowered = (text or "").strip().lower()
    if intent in {"greeting", "casual_checkin", "gratitude", "goodbye"}:
        return True
    casual_markers = [
        "joke", "funny", "make me laugh", "tell me something fun",
        "chat with me", "talk to me", "say something", "bored",
        "what's up", "whats up", "how are you"
    ]
    return any(marker in lowered for marker in casual_markers)


def is_conversational_query(intent, topic, text, keyword_match=None):
    lowered = (text or "").strip().lower()
    keyword_match = keyword_match or {}
    if intent in {"greeting", "casual_checkin", "gratitude", "goodbye"}:
        return True
    if any(marker in lowered for marker in CONVERSATIONAL_QUERY_MARKERS):
        return True
    if topic == "general" and not keyword_match.get("matched") and not any(marker in lowered for marker in MEDICAL_QUERY_MARKERS):
        return True
    return False


def is_non_medical_query(text):
    lowered = (text or "").strip().lower()
    return any(marker in lowered for marker in NON_MEDICAL_QUERY_MARKERS) and not any(
        marker in lowered for marker in MEDICAL_QUERY_MARKERS
    )


def ai_fallback_reason(intent, keyword_match, lang, text, session_store, topic="general"):
    if lang != "en":
        return ""
    if not openrouter_enabled():
        return ""
    if is_conversational_query(intent, topic, text, keyword_match):
        return "conversational_query"
    if is_non_medical_query(text):
        return "non_medical_query"
    if intent == "general_query":
        return "general_query"
    if not keyword_match.get("matched"):
        return "no_keyword_match"
    if is_complex_question(text):
        return "complex_question"
    if repeated_intent_count(session_store, intent) > 2:
        return "repeated_intent"
    return ""


def should_use_ai_fallback(intent, keyword_match, lang, text, session_store):
    reason = ai_fallback_reason(intent, keyword_match, lang, text, session_store)
    if reason:
        LOGGER.info("[OpenRouterRouting] AI fallback triggered: reason=%s intent=%s", reason, intent)
        return True
    return False


def _contextual_user_message(user_message, recent_messages):
    if not recent_messages:
        return user_message
    context_lines = "\n".join(f"- {message}" for message in recent_messages)
    return (
        "Recent user context:\n"
        f"{context_lines}\n\n"
        "Current user message:\n"
        f"{user_message}"
    )


def _split_response_parts(text):
    parts = [part.strip() for part in (text or "").split("\n\n") if part.strip()]
    return parts or ([text.strip()] if text and text.strip() else [])


def _is_safe_ai_response(text):
    lowered = (text or "").lower()
    return not any(marker in lowered for marker in UNSAFE_AI_MARKERS)


def _blend_rule_and_ai(rule_response, ai_response):
    if not ai_response:
        return rule_response
    if not rule_response:
        return ai_response

    rule_parts = _split_response_parts(rule_response)
    ai_parts = _split_response_parts(ai_response)

    opener = rule_parts[0] if rule_parts else ""
    closer = rule_parts[-1] if len(rule_parts) > 1 else ""
    ai_body = "\n\n".join(ai_parts[:2]).strip()

    if opener and ai_body and ai_body.lower().startswith(opener.lower()):
        opener = ""
    if closer and ai_body and ai_body.lower().endswith(closer.lower()):
        closer = ""

    blend_mode = random.choice(["rule_ai", "ai_rule"])
    if blend_mode == "ai_rule":
        parts = [ai_body, closer]
    else:
        parts = [opener, ai_body, closer]
    deduped = []
    seen = set()
    for part in parts:
        normalized = part.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(part.strip())
    final_response = "\n\n".join(deduped)
    LOGGER.info(
        "[AI] Response blending: rule_response=%r ai_response=%r final_response=%r",
        rule_response[:240] if rule_response else "",
        ai_response[:240] if ai_response else "",
        final_response[:240] if final_response else "",
    )
    return final_response


def _response_style_hint(analysis):
    intent = analysis.get("intent", "general_query")
    topic = analysis.get("topic", "general")
    sentiment = analysis.get("sentiment", "neutral")
    if intent in {"greeting", "casual_checkin", "gratitude", "goodbye"}:
        return "casual_conversational"
    if intent == "general_query" and topic == "general":
        return "light_conversational"
    if sentiment == "very_negative" or intent == "emergency":
        return "brief_grounded"
    if intent in {"symptom_report", "solution_request", "emotional_support"}:
        return "varied_supportive"
    return "short_supportive"


def generate_hybrid_response(user_message, analysis, session_store, rule_response=""):
    recent_messages = get_recent_user_messages(session_store, limit=3)
    LOGGER.info(
        "[AI] Hybrid generation start: intent=%s topic=%s lang=%s",
        analysis.get("intent", "general_query"),
        analysis.get("topic", "general"),
        analysis.get("language", "en"),
    )
    ai_response = generate_openrouter_response(
        _contextual_user_message(user_message, recent_messages),
        {
            "language": analysis.get("language", "en"),
            "intent": analysis.get("intent", "general_query"),
            "sentiment": analysis.get("sentiment", "neutral"),
            "topic": analysis.get("topic", "general"),
            "response_style": _response_style_hint(analysis),
        },
    )
    if not ai_response:
        LOGGER.info("[OpenRouterFallback] Using rule response because OpenRouter returned no reply.")
        return rule_response
    if not _is_safe_ai_response(ai_response):
        LOGGER.warning("[OpenRouterFallback] Using rule response because AI output failed safety checks.")
        return rule_response
    final_response = _blend_rule_and_ai(rule_response, ai_response)
    LOGGER.info("[AI] Final hybrid response selected.")
    return final_response
