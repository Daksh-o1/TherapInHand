import random
import logging

from ml.openrouter_responder import generate_openrouter_response, openrouter_enabled


SESSION_CHAT_HISTORY_KEY = "chat_history"
SESSION_MAX_HISTORY = 10
SESSION_TEXT_LIMIT = 120
PAUSED_TOPICS_KEY = "paused_topics"
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
    "whats up", "hello", "hi", "hey", "hello there", "hi there", "play a game", "lets talk casually",
    "let's talk casually", "good morning", "tell me something funny"
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
FOLLOW_UP_QUERY_MARKERS = [
    "can you explain more", "explain more", "elaborate", "why", "how", "what do you mean",
    "tell me more", "how does that happen", "what causes that", "can you elaborate",
    "could you explain", "more about that", "what about", "and what about",
    "what medicine helps", "what medication helps", "what can i take", "what should i take",
]
MEDICATION_QUERY_MARKERS = [
    "medicine", "medication", "tablet", "pill", "paracetamol", "ibuprofen",
    "what helps", "what can i take", "what should i take", "otc",
]
EMOTIONAL_CONTINUATION_MARKERS = [
    "why does it feel", "why does it feel heavy", "why am i feeling", "it feels heavy",
    "why is it like that", "why is that", "what does that mean",
]
RESUME_TOPIC_MARKERS = [
    "back to", "okay back to", "let's get back to", "lets get back to",
    "return to", "resume", "continue with",
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
            "category": item.get("category", "ai_fallback"),
            "subtopic": item.get("subtopic"),
            "entities": item.get("entities", {}),
        })
    return cleaned


def get_recent_user_messages(session_store, limit=3):
    history = get_session_chat_history(session_store)
    return [item.get("user", "") for item in history if item.get("user")][-limit:]


def detect_follow_up_query(text):
    lowered = (text or "").strip().lower()
    return any(marker in lowered for marker in FOLLOW_UP_QUERY_MARKERS)


def detect_medication_follow_up(text):
    lowered = (text or "").strip().lower()
    return any(marker in lowered for marker in MEDICATION_QUERY_MARKERS)


def detect_emotional_continuation(text):
    lowered = (text or "").strip().lower()
    return any(marker in lowered for marker in EMOTIONAL_CONTINUATION_MARKERS)


def get_active_conversation_context(session_store):
    history = get_session_chat_history(session_store)
    for item in reversed(history):
        if item.get("category") == "crisis":
            return item
        if item.get("topic") != "general" or item.get("category") in {
            "physical_symptom", "mental_emotional", "positive_emotion", "casual_conversation"
        }:
            return item
    return history[-1] if history else {}


def get_last_non_casual_context(session_store):
    history = get_session_chat_history(session_store)
    for item in reversed(history):
        if item.get("category") in {"physical_symptom", "mental_emotional", "positive_emotion", "crisis"}:
            return item
    return {}


def detect_resume_topic_request(text):
    lowered = (text or "").strip().lower()
    return any(marker in lowered for marker in RESUME_TOPIC_MARKERS)


def detect_casual_interruption(text):
    lowered = (text or "").strip().lower()
    return any(marker in lowered for marker in CONVERSATIONAL_QUERY_MARKERS)


def push_paused_topic(session_store, context):
    if not context:
        return
    paused = session_store.get(PAUSED_TOPICS_KEY, [])
    if not isinstance(paused, list):
        paused = []
    compact = {
        "intent": context.get("intent", "general_query"),
        "topic": context.get("topic", "general"),
        "category": context.get("category", "ai_fallback"),
        "subtopic": context.get("subtopic"),
        "entities": context.get("entities", {}),
    }
    paused = [item for item in paused if not (
        item.get("topic") == compact["topic"]
        and item.get("category") == compact["category"]
        and item.get("subtopic") == compact["subtopic"]
    )]
    paused.append(compact)
    session_store[PAUSED_TOPICS_KEY] = paused[-5:]
    session_store.modified = True


def get_paused_topic(session_store):
    paused = session_store.get(PAUSED_TOPICS_KEY, [])
    if not isinstance(paused, list) or not paused:
        return {}
    return paused[-1]


def update_session_chat_history(session_store, user_message, bot_response, meta=None):
    history = get_session_chat_history(session_store)
    entry = {
        "user": _trim_text(user_message),
        "bot": _trim_text(bot_response),
        "intent": (meta or {}).get("intent", "general_query"),
        "sentiment": (meta or {}).get("sentiment", "neutral"),
        "topic": (meta or {}).get("topic", "general"),
        "category": (meta or {}).get("category", "ai_fallback"),
        "subtopic": (meta or {}).get("subtopic"),
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
