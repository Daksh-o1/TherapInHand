from flask import Flask, abort, request, jsonify, render_template, session, redirect, url_for
from flask_cors import CORS
from flask_login import LoginManager, current_user as login_current_user, login_required, login_user, logout_user
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
from datetime import datetime, timezone
import logging
from logging.handlers import RotatingFileHandler
import json
import os
import re
import uuid
from config import ADMIN_KEY, PORT, get_config_class, load_environment, startup_diagnostics

# Import keyword maps from the keywords package
from keywords import (
    SENTIMENT_MAP_EN, INTENT_MAP_EN, INTENT_PATTERNS_EN, TOPIC_MAP_EN,
    SENTIMENT_MAP_HI, INTENT_MAP_HI, INTENT_PATTERNS_HI, TOPIC_MAP_HI,
)


# ── ML models (lazy-loaded on first request) ──────────────────
# Models train automatically on first run if models/ dir is empty.
from ml.intent_model import predict_intent_with_confidence
from ml.sentiment_model import predict_sentiment_with_confidence
from ml.openrouter_responder import direct_openrouter_test, log_openrouter_startup_status, openrouter_enabled, openrouter_status
from chat_db import init_chat_db, save_chat_message, fetch_chat_history
from models import (
    create_chat_session,
    create_user,
    delete_chat_session,
    fetch_chat_messages,
    fetch_session_history,
    get_chat_session,
    get_user_by_email,
    get_user_by_id,
    get_user_by_username,
    init_database,
    list_chat_sessions,
    rename_chat_session,
    save_chat_exchange,
    save_chat_record,
    serialize_chat_session,
    serialize_user,
    touch_user_login,
    update_user_profile,
)
from rule_responder import (
    RULE_LANGUAGE_KEY,
    detect_health_subtopic,
    extract_context_entities,
    friendly_fallback_message,
    generate_response,
)
from services.auth import consume_auth_attempt, get_or_create_csrf_token, reset_auth_attempts, validate_csrf
from services.ai_handler import (
    ai_fallback_reason,
    classify_message_topic,
    detect_casual_interruption,
    detect_emotional_continuation,
    detect_follow_up_query,
    detect_medication_follow_up,
    detect_resume_topic_request,
    detect_topic_switch,
    generate_hybrid_response,
    get_active_conversation_context,
    get_conversation_state,
    get_last_non_casual_context,
    get_paused_topic,
    is_conversational_query,
    push_paused_topic,
    repeated_intent_count,
    repeated_topic_count,
    should_reset_context,
    should_use_ai_fallback,
    update_session_chat_history,
)

load_environment()
app = Flask(__name__)
app.config.from_object(get_config_class())
app.secret_key = app.config["SECRET_KEY"]
if app.config.get("ENABLE_PROXY_FIX"):
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=app.config.get("PROXY_FIX_X_FOR", 1),
        x_proto=app.config.get("PROXY_FIX_X_PROTO", 1),
        x_host=app.config.get("PROXY_FIX_X_HOST", 1),
        x_port=app.config.get("PROXY_FIX_X_PORT", 1),
        x_prefix=app.config.get("PROXY_FIX_X_PREFIX", 1),
    )
if app.config.get("ENABLE_CORS"):
    CORS(app, supports_credentials=True, origins=app.config.get("CORS_ORIGINS") or "*")
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login_page"


def configure_logging(flask_app):
    os.makedirs(flask_app.config["LOG_DIR"], exist_ok=True)
    level = getattr(logging, str(flask_app.config.get("LOG_LEVEL", "INFO")).upper(), logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    has_console_handler = any(isinstance(handler, logging.StreamHandler) for handler in root_logger.handlers)
    has_file_handler = any(
        isinstance(handler, RotatingFileHandler) and getattr(handler, "baseFilename", None) == os.path.abspath(flask_app.config["LOG_FILE"])
        for handler in root_logger.handlers
    )
    if not has_file_handler:
        file_handler = RotatingFileHandler(
            flask_app.config["LOG_FILE"],
            maxBytes=flask_app.config["LOG_MAX_BYTES"],
            backupCount=flask_app.config["LOG_BACKUP_COUNT"],
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    if not has_console_handler:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
    flask_app.logger.setLevel(level)


configure_logging(app)
log_openrouter_startup_status()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STORAGE_PATH = os.path.join(BASE_DIR, "data", "app_storage.json")
CHAT_DB_PATH = os.path.join(BASE_DIR, "data", "chat_history.db")
SOLID_THEMES = {
    "blue": "Blue",
    "green": "Green",
    "purple": "Purple",
    "black": "Black",
    "orange": "Orange",
    "red": "Red",
}
GRADIENT_THEMES = {
    "ocean": "Ocean",
    "sunset": "Sunset",
    "midnight": "Midnight",
    "lavender": "Lavender",
    "forest": "Forest",
    "neon": "Neon",
}
APPEARANCE_MODES = {
    "light": "Light",
    "dark": "Dark",
    "system": "System",
}
THEMES = {
    "solids": SOLID_THEMES,
    "gradients": GRADIENT_THEMES,
    "modes": APPEARANCE_MODES,
}
LEGACY_THEME_MAP = {
    "sage": {"theme_name": "green", "accent_color": "green", "gradient_theme": "forest", "theme_mode": "system"},
    "ocean": {"theme_name": "blue", "accent_color": "blue", "gradient_theme": "ocean", "theme_mode": "system"},
    "sunrise": {"theme_name": "orange", "accent_color": "orange", "gradient_theme": "sunset", "theme_mode": "light"},
    "lavender": {"theme_name": "purple", "accent_color": "purple", "gradient_theme": "lavender", "theme_mode": "system"},
    "sand": {"theme_name": "orange", "accent_color": "orange", "gradient_theme": "sunset", "theme_mode": "light"},
    "night": {"theme_name": "black", "accent_color": "black", "gradient_theme": "midnight", "theme_mode": "dark"},
}
CASUAL_INTENTS = {"greeting", "gratitude", "goodbye", "casual_checkin"}
RULE_BASED_INTENTS = {"emergency", "solution_request", "symptom_report", "emotional_support", "general_query"} | CASUAL_INTENTS
RECENT_CLIENT_IDS_KEY = "recent_client_message_ids"
RECENT_CLIENT_IDS_LIMIT = 20

LEGACY_CHAT_DB_ENABLED = bool(app.config.get("LEGACY_CHAT_DB_ENABLED"))
if LEGACY_CHAT_DB_ENABLED:
    init_chat_db(CHAT_DB_PATH)
init_database(app)
if app.config.get("STARTUP_DIAGNOSTICS", True):
    diagnostics = startup_diagnostics()
    app.logger.info(
        "startup_complete env=%s debug=%s port=%s database_uri=%s legacy_chat_db=%s openrouter_enabled=%s",
        diagnostics["environment"],
        diagnostics["debug"],
        diagnostics["port"],
        diagnostics["database_uri"],
        LEGACY_CHAT_DB_ENABLED,
        diagnostics["openrouter_enabled"],
    )


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _default_storage():
    return {"users": {}, "chat_history": {}}


def load_storage():
    os.makedirs(os.path.dirname(STORAGE_PATH), exist_ok=True)
    if not os.path.exists(STORAGE_PATH):
        save_storage(_default_storage())
    try:
        with open(STORAGE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        data = _default_storage()
    data.setdefault("users", {})
    data.setdefault("chat_history", {})
    return data


def save_storage(data):
    os.makedirs(os.path.dirname(STORAGE_PATH), exist_ok=True)
    tmp_path = STORAGE_PATH + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, STORAGE_PATH)
    except PermissionError:
        with open(STORAGE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


@login_manager.user_loader
def load_logged_in_user(user_id):
    return get_user_by_id(user_id)


@app.before_request
def enforce_request_safety():
    trusted_hosts = app.config.get("TRUSTED_HOSTS") or []
    if trusted_hosts:
        host = request.host.split(":", 1)[0].lower()
        normalized = {item.split(":", 1)[0].strip().lower() for item in trusted_hosts if str(item).strip()}
        if host not in normalized:
            app.logger.warning("blocked_untrusted_host host=%s path=%s", request.host, request.path)
            abort(400)
    session.permanent = True


@app.after_request
def apply_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Cache-Control", "no-store" if request.path.startswith("/api/") else "no-cache")
    if request.is_secure:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


@app.context_processor
def inject_template_state():
    return {
        "current_user_data": current_user_data(),
        "csrf_token": get_or_create_csrf_token(session),
    }


def is_authenticated_user():
    return bool(getattr(login_current_user, "is_authenticated", False))


def current_user_data():
    if not is_authenticated_user():
        return None
    return serialize_user(login_current_user)


def active_identity():
    user = current_user_data()
    if user:
        return user
    guest_user_id = session.get("guest_user_id")
    if not guest_user_id:
        guest_user_id = f"guest-{uuid.uuid4().hex}"
        session["guest_user_id"] = guest_user_id
        session.modified = True
    return {
        "id": guest_user_id,
        "username": "Guest",
        "name": "Guest",
        "email": "",
        "theme_name": None,
        "theme_mode": None,
        "accent_color": None,
        "gradient_theme": None,
        "is_guest": True,
    }


def default_theme_preferences():
    return {
        "theme_name": "blue",
        "theme_mode": "system",
        "accent_color": "blue",
        "gradient_theme": "ocean",
    }


def resolve_theme_preferences(user_record):
    defaults = default_theme_preferences()
    legacy_theme = user_record.get("theme")
    if legacy_theme in LEGACY_THEME_MAP:
        defaults.update(LEGACY_THEME_MAP[legacy_theme])
    if user_record.get("theme_name") in SOLID_THEMES:
        defaults["theme_name"] = user_record["theme_name"]
    if user_record.get("theme_mode") in APPEARANCE_MODES:
        defaults["theme_mode"] = user_record["theme_mode"]
    if user_record.get("accent_color") in SOLID_THEMES:
        defaults["accent_color"] = user_record["accent_color"]
    if user_record.get("gradient_theme") in GRADIENT_THEMES:
        defaults["gradient_theme"] = user_record["gradient_theme"]
    return defaults


def theme_payload_from_request(data_in):
    legacy_theme = _safe_text(data_in.get("theme"), default="", limit=32)
    defaults = LEGACY_THEME_MAP.get(legacy_theme, default_theme_preferences())
    theme_name = _safe_text(data_in.get("theme_name"), default=defaults["theme_name"], limit=32)
    theme_mode = _safe_text(data_in.get("theme_mode"), default=defaults["theme_mode"], limit=16)
    accent_color = _safe_text(data_in.get("accent_color"), default=theme_name, limit=32)
    gradient_theme = _safe_text(data_in.get("gradient_theme"), default=defaults["gradient_theme"], limit=32)
    if theme_name not in SOLID_THEMES:
        theme_name = defaults["theme_name"]
    if theme_mode not in APPEARANCE_MODES:
        theme_mode = defaults["theme_mode"]
    if accent_color not in SOLID_THEMES:
        accent_color = theme_name
    if gradient_theme not in GRADIENT_THEMES:
        gradient_theme = defaults["gradient_theme"]
    return {
        "theme_name": theme_name,
        "theme_mode": theme_mode,
        "accent_color": accent_color,
        "gradient_theme": gradient_theme,
    }


def get_actor_id():
    return active_identity()["id"]


def clear_chat_session_state():
    session.pop("chat_session_id", None)
    session.pop("chat_history", None)
    session.pop(RECENT_CLIENT_IDS_KEY, None)
    session.pop("response_cache", None)
    session.modified = True


def clear_guest_session_state():
    session.pop("guest_user_id", None)
    clear_chat_session_state()


def require_csrf():
    if not validate_csrf(session, request):
        return jsonify({"error": "invalid_csrf"}), 400
    return None


def generate_chat_title(message):
    words = re.sub(r"\s+", " ", (message or "").strip()).split(" ")
    title = " ".join(words[:8]).strip()
    if not title:
        return "New chat"
    return title[:80]


def get_chat_session_id():
    actor_id = get_actor_id()
    chat_session_id = session.get("chat_session_id")
    existing_session = get_chat_session(chat_session_id, user_id=actor_id) if chat_session_id else None
    if existing_session:
        return existing_session.id

    latest_sessions = list_chat_sessions(actor_id, limit=1)
    if latest_sessions:
        chat_session_id = latest_sessions[0].id
    else:
        chat_session_id = uuid.uuid4().hex
        create_chat_session(actor_id, chat_id=chat_session_id)
    session["chat_session_id"] = chat_session_id
    session.modified = True
    return chat_session_id


def build_chat_history_rows(chat_id):
    actor_id = get_actor_id()
    messages = fetch_chat_messages(chat_id, user_id=actor_id)
    rows = []
    pair = {}
    for item in messages:
        sender = item.get("sender")
        if sender == "user":
            if pair.get("user_message") or pair.get("bot_response"):
                rows.append(pair)
            pair = {
                "id": item.get("id"),
                "chat_id": chat_id,
                "user_message": item.get("message", ""),
                "intent": item.get("intent"),
                "sentiment": item.get("sentiment"),
                "timestamp": item.get("timestamp"),
            }
        elif sender == "assistant":
            if not pair:
                pair = {
                    "id": item.get("id"),
                    "chat_id": chat_id,
                    "timestamp": item.get("timestamp"),
                }
            pair["bot_response"] = item.get("message", "")
            pair["intent"] = pair.get("intent") or item.get("intent")
            pair["sentiment"] = pair.get("sentiment") or item.get("sentiment")
            rows.append(pair)
            pair = {}
    if pair:
        rows.append(pair)
    return rows


def remember_client_message_id(client_message_id):
    if not client_message_id:
        return
    recent_ids = session.get(RECENT_CLIENT_IDS_KEY, [])
    if not isinstance(recent_ids, list):
        recent_ids = []
    session[RECENT_CLIENT_IDS_KEY] = (recent_ids + [client_message_id])[-RECENT_CLIENT_IDS_LIMIT:]
    session.modified = True


def has_recent_client_message_id(client_message_id):
    if not client_message_id:
        return False
    recent_ids = session.get(RECENT_CLIENT_IDS_KEY, [])
    return isinstance(recent_ids, list) and client_message_id in recent_ids


def forget_client_message_id(client_message_id):
    if not client_message_id:
        return
    recent_ids = session.get(RECENT_CLIENT_IDS_KEY, [])
    if not isinstance(recent_ids, list):
        return
    session[RECENT_CLIENT_IDS_KEY] = [item for item in recent_ids if item != client_message_id][-RECENT_CLIENT_IDS_LIMIT:]
    session.modified = True


def _safe_text(value, default="", limit=4000):
    if value is None:
        return default
    return str(value).strip()[:limit]


def _safe_email(value):
    email = _safe_text(value, default="", limit=255).lower()
    if re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", email):
        return email
    return ""


def _safe_username(value):
    username = _safe_text(value, default="", limit=120)
    if not re.fullmatch(r"[A-Za-z0-9 _.\-]{2,120}", username):
        return ""
    return username


def _hash_password(password):
    return generate_password_hash(password, method="scrypt")


def _wants_json_response():
    if request.path.startswith("/api/"):
        return True
    if request.path in {"/chat", "/health", "/retrain", "/guest", "/logout", "/login", "/register", "/profile"} and request.method != "GET":
        return True
    best = request.accept_mimetypes.best
    return best == "application/json"


def require_login(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_authenticated_user():
            return jsonify({"error": "login_required"}), 401
        return view(*args, **kwargs)
    return wrapped


def find_history_entry_by_client_message_id(history, client_message_id):
    if not client_message_id:
        return None
    for entry in reversed(history):
        if entry.get("client_message_id") == client_message_id:
            return entry
    return None


def append_chat_history(user_message, bot_response, meta, client_message_id=None):
    history = session.get("response_cache", [])
    if not isinstance(history, list):
        history = []
    existing_entry = find_history_entry_by_client_message_id(history, client_message_id)
    if existing_entry:
        app.logger.info(
            "chat_history_duplicate_skipped actor_id=%s client_message_id=%s",
            get_actor_id(),
            client_message_id,
        )
        return existing_entry
    message_pair_id = uuid.uuid4().hex
    entry = {
        "id": message_pair_id,
        "client_message_id": client_message_id,
        "created_at": _now_iso(),
        "user_message_id": f"{message_pair_id}-user",
        "assistant_message_id": f"{message_pair_id}-assistant",
        "user": user_message,
        "bot": bot_response,
        "meta": meta,
    }
    history.append(entry)
    session["response_cache"] = history[-40:]
    session.modified = True
    return entry


def serialize_history(history):
    serialized = []
    seen_pairs = set()
    seen_message_ids = set()
    for item in history[-40:]:
        pair_id = item.get("id") or uuid.uuid4().hex
        if pair_id in seen_pairs:
            continue
        user_message_id = item.get("user_message_id") or f"{pair_id}-user"
        assistant_message_id = item.get("assistant_message_id") or f"{pair_id}-assistant"
        if user_message_id in seen_message_ids or assistant_message_id in seen_message_ids:
            continue
        seen_pairs.add(pair_id)
        seen_message_ids.add(user_message_id)
        seen_message_ids.add(assistant_message_id)
        serialized.append({
            "id": pair_id,
            "client_message_id": item.get("client_message_id"),
            "created_at": item.get("created_at"),
            "user": {
                "id": user_message_id,
                "role": "user",
                "text": item.get("user", ""),
            },
            "assistant": {
                "id": assistant_message_id,
                "role": "assistant",
                "text": item.get("bot", ""),
            },
            "meta": item.get("meta", {}),
        })
    return serialized

# ══════════════════════════════════════════════════════════════
#  DETECTION FUNCTIONS
# ══════════════════════════════════════════════════════════════

def _kw_match(keyword, text):
    """Match keyword in text using word boundaries for single words,
    plain substring for multi-word phrases."""
    if ' ' in keyword:
        return keyword in text
    return bool(re.search(r'\b' + re.escape(keyword) + r'\b', text))


def detect_language(text):
    """Detect if the text contains Hindi (Devanagari or common Roman Hindi)."""
    devanagari = any('\u0900' <= c <= '\u097F' for c in text)
    if devanagari:
        return "hi"
    roman_hindi_words = [
        "kya", "hoon", "hai", "nahi", "mujhe", "mera", "meri", "bahut",
        "aur", "toh", "bhi", "kuch", "abhi", "aaj", "kal", "theek",
        "achha", "pareshan", "thaka", "thaki", "udas", "dard", "neend",
        "tanav", "chinta", "ghabrahat", "madad", "batao", "karun",
        "kaise", "kese", "kaisa", "kaisi", "kyu", "kyun", "q", "qki",
        "haan", "han", "hn", "ha", "nhi", "mat", "mt", "bta", "btao",
        "btana", "btaana", "krna", "kro", "karna", "karu", "kru",
        "hu", "hun", "h", "tha", "thi", "raha", "rahi", "rha", "rhi",
        "lag", "lg", "lagta", "lgta", "lagti", "lgti", "mann", "man",
        "dimag", "dimaag", "sar", "pet", "gala", "seena", "saans",
        "sanse", "bukhar", "jukam", "khansi", "ulti", "dast"
    ]
    text_lower = text.lower()
    if sum(1 for w in roman_hindi_words if _kw_match(w, text_lower)) >= 2:
        return "hi"
    short_hinglish_phrases = [
        "kya karu", "kya karun", "kese karu", "kaise karu", "kyu ho raha",
        "bta do", "bata do", "help kro", "madad chahiye", "mujhe bta",
    ]
    if any(phrase in text_lower for phrase in short_hinglish_phrases):
        return "hi"
    return "en"


def has_devanagari(text):
    return any('\u0900' <= c <= '\u097F' for c in text)


def prefers_hinglish(text):
    text_lower = text.lower()
    if has_devanagari(text):
        return False
    hinglish_markers = [
        "kya", "kaise", "kese", "kyu", "kyun", "bta", "btao", "batao",
        "nhi", "hn", "haan", "han", "hu", "hun", "hoon", "karu", "karun",
        "kru", "kro", "raha", "rahi", "rha", "rhi", "lag raha", "feel",
        "mujhe", "mera", "meri", "dimag", "mann", "thik", "theek",
    ]
    return sum(1 for marker in hinglish_markers if _kw_match(marker, text_lower)) >= 2


def detect_sentiment(text, lang):
    text_lower = text.lower()
    smap = SENTIMENT_MAP_HI if lang == "hi" else SENTIMENT_MAP_EN
    for kw in smap["very_negative"]:
        if _kw_match(kw, text_lower):
            return "very_negative"
    neg = sum(1 for kw in smap["negative"] if _kw_match(kw, text_lower))
    pos = sum(1 for kw in smap["positive"] if _kw_match(kw, text_lower))
    if neg > pos:
        return "negative"
    if pos > neg:
        return "positive"
    return "neutral"


def detect_intent(text, lang):
    text_lower = text.lower()
    patterns = INTENT_PATTERNS_HI if lang == "hi" else INTENT_PATTERNS_EN
    for pattern in sorted(patterns, key=lambda item: item.get("priority", 0), reverse=True):
        for kw in pattern.get("keywords", []):
            if _kw_match(kw, text_lower):
                return pattern["intent"]
    return "general_query"


def match_keyword_intent(text, lang):
    text_lower = text.lower()
    patterns = INTENT_PATTERNS_HI if lang == "hi" else INTENT_PATTERNS_EN
    for pattern in sorted(patterns, key=lambda item: item.get("priority", 0), reverse=True):
        matched = [kw for kw in pattern.get("keywords", []) if _kw_match(kw, text_lower)]
        if matched:
            return {
                "matched": True,
                "intent": pattern["intent"],
                "matched_keywords": matched,
            }
    return {
        "matched": False,
        "intent": "general_query",
        "matched_keywords": [],
    }


EMOTIONAL_KEYWORD_GROUPS = {
    "sad": ["sad", "unhappy", "low", "down", "udas", "dukhi"],
    "depression": ["depression", "depressed", "hopeless", "empty", "numb", "heartbreak"],
    "anxiety": ["anxious", "panic", "overthinking", "stressed", "stress", "anxiety", "emotionally exhausted", "emotional exhaustion"],
    "loneliness": ["lonely", "isolated", "nobody", "alone", "akela", "akeli"],
}
POSITIVE_EMOTION_KEYWORDS = [
    "happy", "excited", "relieved", "peaceful", "motivated",
    "hopeful", "grateful", "confident", "feeling better",
    "better now", "proud",
]
CRISIS_ROUTE_KEYWORDS = [
    "i want to die", "want to die", "kill myself", "end my life",
    "suicidal", "self harm", "self-harm", "hurt myself",
]
CASUAL_ROUTE_KEYWORDS = [
    "hello", "hi", "hey", "how are you", "what's up", "whats up",
]
EMOTIONAL_SUBTOPIC_BY_KEYWORD = {
    "sad": "sadness",
    "unhappy": "sadness",
    "low": "sadness",
    "down": "sadness",
    "depression": "depression",
    "depressed": "depression",
    "hopeless": "hopelessness",
    "empty": "depression",
    "numb": "depression",
    "heartbreak": "heartbreak",
    "anxious": "anxiety",
    "anxiety": "anxiety",
    "panic": "anxiety",
    "overthinking": "overthinking",
    "stressed": "stress",
    "stress": "stress",
    "emotionally exhausted": "emotional_exhaustion",
    "emotional exhaustion": "emotional_exhaustion",
    "lonely": "loneliness",
    "alone": "loneliness",
}

EMOTIONAL_INTENT_PRIORITY = {
    "emergency": 1,
    "emotional_support": 2,
    "disease_detection": 3,
    "symptom_report": 4,
    "casual_checkin": 5,
    "general_query": 6,
}


def summarize_entity_reasoning(entities):
    reasons = []
    if entities.get("symptom") and (entities.get("cause") or entities.get("supplement")):
        reasons.append("symptom_with_context")
    elif entities.get("symptom"):
        reasons.append("symptom_only")
    if entities.get("medicine"):
        reasons.append("medicine_context")
    if entities.get("severity"):
        reasons.append("severity_context")
    if entities.get("duration"):
        reasons.append("duration_context")
    if entities.get("emotional_context"):
        reasons.append("emotional_context")
    return ",".join(reasons) if reasons else "none"


def detect_emotional_keywords(text):
    text_lower = text.lower()
    matches = []
    for group, keywords in EMOTIONAL_KEYWORD_GROUPS.items():
        matched = [kw for kw in keywords if _kw_match(kw, text_lower)]
        if matched:
            matches.extend(matched)
    seen = set()
    ordered = []
    for item in matches:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def detect_positive_emotion_keywords(text):
    text_lower = text.lower()
    return [item for item in POSITIVE_EMOTION_KEYWORDS if _kw_match(item, text_lower)]


def detect_emotional_subtopic(text, emotional_matches=None):
    text_lower = text.lower()
    for item in emotional_matches or []:
        if item in EMOTIONAL_SUBTOPIC_BY_KEYWORD:
            return EMOTIONAL_SUBTOPIC_BY_KEYWORD[item]
    for keyword, subtopic in EMOTIONAL_SUBTOPIC_BY_KEYWORD.items():
        if _kw_match(keyword, text_lower):
            return subtopic
    return ""


def _merge_entity_maps(primary, secondary):
    merged = {}
    for source in [primary or {}, secondary or {}]:
        for key, values in source.items():
            bucket = merged.setdefault(key, [])
            for value in values or []:
                if value not in bucket:
                    bucket.append(value)
    return merged


def detect_priority_route(text, lang, keyword_match=None):
    keyword_match = keyword_match or {"matched": False, "matched_keywords": [], "intent": "general_query"}
    text_lower = text.lower()
    emotional_matches = detect_emotional_keywords(text)
    positive_matches = detect_positive_emotion_keywords(text)
    emotional_subtopic = detect_emotional_subtopic(text, emotional_matches)
    effective_lang = "hinglish" if lang == "hi" and prefers_hinglish(text) else lang
    detected_topic = detect_topic(text, lang)
    health_subtopic = detect_health_subtopic(text, effective_lang)
    extracted_entities = extract_context_entities(text, effective_lang)
    physical_conditions = detect_physical_conditions(text, lang)
    health_kind = health_subtopic.get("kind") if health_subtopic else ""
    has_physical_signal = bool(
        physical_conditions
        or (health_subtopic and health_kind in {"symptom", "disease"})
        or detected_topic == "physical_discomfort"
    )
    has_emotional_signal = bool(emotional_matches)
    mental_phrase_priority = any(
        _kw_match(item, text_lower)
        for item in ["sad", "depressed", "depression", "lonely", "anxious", "stress", "hopeless", "overthinking", "heartbreak", "emotionally exhausted", "udas", "dukhi"]
    )

    if keyword_match.get("intent") == "emergency" or any(_kw_match(item, text_lower) for item in CRISIS_ROUTE_KEYWORDS):
        return {
            "intent": "emergency",
            "priority": EMOTIONAL_INTENT_PRIORITY["emergency"],
            "matched_keywords": keyword_match.get("matched_keywords", []),
            "override_reason": "emergency_priority",
            "health_subtopic": health_subtopic,
            "emotional_matches": emotional_matches,
            "entities": extracted_entities,
            "category": "crisis",
            "subtopic": "crisis",
            "confidence": 1.0,
            "dataset_match": "crisis_keywords",
            "fallback_reason": "",
        }

    if positive_matches:
        return {
            "intent": "general_query",
            "priority": 2,
            "matched_keywords": positive_matches,
            "override_reason": "positive_emotion_priority",
            "health_subtopic": None,
            "emotional_matches": emotional_matches,
            "entities": extracted_entities,
            "category": "positive_emotion",
            "subtopic": positive_matches[0],
            "confidence": 0.98,
            "dataset_match": "positive_emotion_keywords",
            "fallback_reason": "",
        }

    if has_emotional_signal and (not has_physical_signal or mental_phrase_priority):
        return {
            "intent": "emotional_support",
            "priority": EMOTIONAL_INTENT_PRIORITY["emotional_support"],
            "matched_keywords": emotional_matches,
            "override_reason": "emotional_priority_over_physical",
            "health_subtopic": health_subtopic,
            "emotional_matches": emotional_matches,
            "entities": extracted_entities,
            "category": "mental_emotional",
            "subtopic": emotional_subtopic or "general",
            "confidence": 0.96,
            "dataset_match": "mental_health_keywords",
            "fallback_reason": "",
        }

    if health_subtopic and health_subtopic.get("kind") == "disease":
        return {
            "intent": "symptom_report",
            "priority": EMOTIONAL_INTENT_PRIORITY["disease_detection"],
            "matched_keywords": keyword_match.get("matched_keywords", []),
            "override_reason": "disease_priority",
            "health_subtopic": health_subtopic,
            "emotional_matches": emotional_matches,
            "entities": extracted_entities,
            "category": "physical_symptom",
            "subtopic": health_subtopic.get("name", "physical_discomfort"),
            "confidence": 0.92,
            "dataset_match": health_subtopic.get("name", "disease"),
            "fallback_reason": "",
        }

    if has_physical_signal:
        return {
            "intent": "symptom_report",
            "priority": EMOTIONAL_INTENT_PRIORITY["symptom_report"],
            "matched_keywords": keyword_match.get("matched_keywords", []),
            "override_reason": "symptom_priority",
            "health_subtopic": health_subtopic,
            "emotional_matches": emotional_matches,
            "entities": extracted_entities,
            "category": "physical_symptom",
            "subtopic": (health_subtopic or {}).get("name") or (physical_conditions[0] if physical_conditions else detected_topic or "physical_discomfort"),
            "confidence": 0.9,
            "dataset_match": (health_subtopic or {}).get("name") or ",".join(physical_conditions[:2]) or "physical_signal",
            "fallback_reason": "",
        }

    if keyword_match.get("intent") in CASUAL_INTENTS or any(_kw_match(item, text_lower) for item in CASUAL_ROUTE_KEYWORDS):
        return {
            "intent": keyword_match.get("intent") if keyword_match.get("intent") in CASUAL_INTENTS else "casual_checkin",
            "priority": EMOTIONAL_INTENT_PRIORITY["casual_checkin"],
            "matched_keywords": keyword_match.get("matched_keywords", []) or [item for item in CASUAL_ROUTE_KEYWORDS if _kw_match(item, text_lower)],
            "override_reason": "casual_priority",
            "health_subtopic": health_subtopic,
            "emotional_matches": emotional_matches,
            "entities": extracted_entities,
            "category": "casual_conversation",
            "subtopic": "casual_checkin",
            "confidence": 0.88,
            "dataset_match": "casual_intent",
            "fallback_reason": "",
        }

    return {
        "intent": keyword_match.get("intent", "general_query"),
        "priority": EMOTIONAL_INTENT_PRIORITY["general_query"],
        "matched_keywords": keyword_match.get("matched_keywords", []),
        "override_reason": "",
        "health_subtopic": health_subtopic,
        "emotional_matches": emotional_matches,
        "entities": extracted_entities,
        "category": "ai_fallback",
        "subtopic": "general",
        "confidence": 0.4,
        "dataset_match": "none",
        "fallback_reason": "no_specific_route_match",
    }


def detect_topic(text, lang):
    text_lower = text.lower()
    tmap = TOPIC_MAP_HI if lang == "hi" else TOPIC_MAP_EN
    scores = {topic: sum(1 for kw in kws if _kw_match(kw, text_lower)) for topic, kws in tmap.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "general"


# ══════════════════════════════════════════════════════════════
#  ML DETECTION — replaces keyword-based detect_intent / detect_sentiment
#  for English text.  Hindi falls back to keyword matchers above.
# ══════════════════════════════════════════════════════════════

def detect_intent_ml(text: str, lang: str):
    """
    Hybrid intent detection:
      - English → TF-IDF + Logistic Regression (ML model)
      - Hindi   → keyword-based fallback (original detect_intent)

    Why hybrid?
    ML training data is English-only.  For Hindi (roman or Devanagari)
    the keyword maps in keywords/hindi.py remain the best signal.
    """
    if lang == "hi":
        return detect_intent(text, lang), 1.0   # keyword fallback for Hindi
    return predict_intent_with_confidence(text)


def detect_sentiment_ml(text: str, lang: str):
    """
    Hybrid sentiment detection:
      - English → TF-IDF + Naive Bayes (ML model)
      - Hindi   → keyword-based fallback (original detect_sentiment)
    """
    if lang == "hi":
        return detect_sentiment(text, lang), 1.0  # keyword fallback for Hindi
    return predict_sentiment_with_confidence(text)


def fallback_en():
    options = [
        "I'm not fully sure I understood that, but I'm still here with you.",
        "I may be missing part of what you mean, but we can try again.",
        "I didn't quite catch that clearly, though I still want to help.",
    ]
    return random.choice(options)


def fallback_hi():
    options = [
        "Mujhe baat poori tarah samajh nahi aayi, lekin main yahin hoon.",
        "Shayad main aapki baat ka ek hissa miss kar raha hoon, par hum dobara try kar sakte hain.",
        "Main isse clearly pakad nahi paaya, lekin main help karna chahta hoon.",
    ]
    return random.choice(options)


def fallback_hinglish():
    options = [
        "Mujhe baat abhi poori clear nahi hui, but main yahin hoon.",
        "Shayad main tumhari baat ka ek part miss kar raha hoon, phir bhi hum try kar sakte hain.",
        "Main isse clearly samajh nahi paaya, but I still want to help.",
    ]
    return random.choice(options)


def should_use_fallback(text, lang, intent, intent_confidence, sentiment_confidence, topic):
    if lang == "hi":
        return False
    if intent in CASUAL_INTENTS:
        return False
    if openrouter_enabled() and is_conversational_query(intent, topic, text, {"matched": False}):
        return False

    out_of_scope_keywords = [
        "weather", "temperature", "sports", "match", "cricket", "football",
        "movie", "song", "music", "bitcoin", "stock", "coding", "python",
        "javascript", "homework", "math", "recipe", "flight", "hotel",
        "tokyo", "news", "politics", "translate", "joke",
    ]
    text_lower = text.lower()
    if openrouter_enabled() and any(_kw_match(keyword, text_lower) for keyword in out_of_scope_keywords):
        return False
    if openrouter_enabled() and intent == "general_query" and topic == "general":
        return False

    if any(_kw_match(keyword, text_lower) for keyword in out_of_scope_keywords):
        return True

    if len(text.split()) <= 2 and intent == "general_query" and topic == "general":
        return True

    if intent == "general_query" and topic == "general" and intent_confidence < 0.55:
        return True

    if topic == "general" and intent_confidence < 0.45 and sentiment_confidence < 0.45:
        return True

    return False


def detect_physical_conditions(text, lang):
    text_lower = text.lower()
    if lang == "hi":
        condition_keywords = {
            "malaria": ["malaria"],
            "jaundice": ["jaundice", "peeliya", "peelia"],
            "dengue": ["dengue"],
            "typhoid": ["typhoid"],
            "flu": ["flu", "influenza"],
            "fever": ["bukhar", "fever", "bukhar hai", "temperature"],
            "cold": ["sardi", "jukam", "naak band", "cold", "nose blocked"],
            "cough": ["khansi", "khasi", "cough"],
            "sore_throat": ["gala dard", "gala kharab", "gale me dard", "throat pain"],
            "headache": ["sar dard", "sir dard", "headache", "migraine"],
            "stomach_issue": ["pet dard", "pet me dard", "ulti", "dast", "loose motion", "stomach pain"],
            "dizziness": ["chakkar", "sar ghoom", "chakkar aa raha", "dizzy"],
            "fatigue": ["kamzori", "kamjori", "thaka", "thaki", "weak", "weakness", "thak gya"],
            "dehydration": ["dehydration", "paani ki kami", "dry mouth", "kam paani"],
        }
    else:
        condition_keywords = {
            "malaria": ["malaria", "malarial fever"],
            "jaundice": ["jaundice", "yellow eyes", "yellow skin"],
            "dengue": ["dengue"],
            "typhoid": ["typhoid", "enteric fever"],
            "flu": ["flu", "influenza"],
            "fever": ["fever", "temperature", "chills", "high temp"],
            "cold": ["cold", "runny nose", "blocked nose", "stuffy nose", "sneezing", "flu"],
            "cough": ["cough", "dry cough", "wet cough"],
            "sore_throat": ["sore throat", "throat pain", "throat is sore", "gala hurts"],
            "headache": ["headache", "head hurts", "migraine"],
            "stomach_issue": ["stomach pain", "nausea", "vomiting", "diarrhea", "loose motion", "cramps"],
            "dizziness": ["dizzy", "dizziness", "lightheaded", "faint"],
            "fatigue": ["fatigue", "weak", "weakness", "drained", "no energy"],
            "dehydration": ["dehydration", "dehydrated", "dry mouth", "low fluids", "not drinking enough"],
        }

    matches = []
    for condition, keywords in condition_keywords.items():
        if any(_kw_match(keyword, text_lower) for keyword in keywords):
            matches.append(condition)
    return matches


def physical_response_en(text, request_mode="symptom"):
    conditions = detect_physical_conditions(text, "en")
    primary = conditions[0] if conditions else "general"

    if primary == "fever":
        return (
            "A fever usually means your body is responding to an infection, so it is worth monitoring it carefully.\n\n"
            "What to do now:\n"
            "- Confirm the temperature with a thermometer if you can.\n"
            "- Rest and drink plenty of water or oral fluids.\n"
            "- If you need relief, paracetamol (acetaminophen) may help reduce fever and body aches when taken exactly as the label directs. Avoid it if a clinician has told you not to use it, or if you have an allergy or significant liver disease.\n"
            "- Wear light clothing and avoid dehydration.\n\n"
            "Please contact a doctor if the fever is very high, lasts more than 2 to 3 days, keeps getting worse, or comes with shortness of breath, confusion, severe weakness, chest pain, or repeated vomiting.\n\n"
            "If you want, tell me your temperature and any other symptoms, and I can guide the next steps more clearly."
        )

    if primary == "cold":
        return (
            "This sounds more like a cold or flu-type illness than a stress response.\n\n"
            "What usually helps:\n"
            "- Rest and drink enough fluids.\n"
            "- Warm liquids, steam inhalation, or saline nasal drops can help with congestion.\n"
            "- Paracetamol (acetaminophen) may help with fever, body aches, or throat discomfort if you can take it safely and follow the label.\n"
            "- Try to monitor whether symptoms are improving over the next couple of days.\n\n"
            "Please see a doctor if you develop breathing difficulty, chest pain, dehydration, a very high fever, or symptoms that are not improving."
        )

    if primary == "cough":
        return (
            "A cough can happen with a cold, throat irritation, or another respiratory infection.\n\n"
            "What may help:\n"
            "- Sip warm fluids frequently.\n"
            "- Rest your throat and avoid smoke or dust.\n"
            "- If you also have fever or body aches, paracetamol (acetaminophen) may help if it is safe for you and used exactly as directed on the label.\n\n"
            "Please seek medical care if the cough is causing breathing trouble, chest pain, wheezing, coughing up blood, or lasts longer than expected."
        )

    if primary == "sore_throat":
        return (
            "A sore throat is often caused by a viral infection, irritation, or a cold.\n\n"
            "Try this:\n"
            "- Drink warm fluids and stay hydrated.\n"
            "- Soft foods can be easier to tolerate.\n"
            "- Paracetamol (acetaminophen) may help with pain or fever if you can take it safely and follow the label directions.\n\n"
            "Please speak with a doctor if swallowing becomes difficult, you have breathing trouble, the fever is high, or the pain is getting worse."
        )

    if primary == "headache":
        return (
            "Headache can happen with fever, dehydration, stress, or lack of sleep, so it helps to check the surrounding symptoms.\n\n"
            "You can try:\n"
            "- Rest in a quiet place.\n"
            "- Drink water slowly.\n"
            "- If the headache is mild to moderate, paracetamol (acetaminophen) may help if it is safe for you and taken exactly as directed on the label.\n\n"
            "Please get medical advice urgently if the headache is sudden and severe, comes with confusion, weakness, high fever, stiff neck, or repeated vomiting."
        )

    if primary == "stomach_issue":
        return (
            "Stomach symptoms are important to manage early so you do not get dehydrated.\n\n"
            "What to do now:\n"
            "- Sip water or oral rehydration solution in small amounts.\n"
            "- Eat light foods only if you feel able.\n"
            "- Rest and avoid oily or heavy foods for now.\n\n"
            "Please contact a doctor if you cannot keep fluids down, have severe abdominal pain, blood in vomit or stool, signs of dehydration, or symptoms that keep worsening."
        )

    if primary == "dizziness":
        return (
            "Dizziness can happen from dehydration, fever, low food intake, anxiety, or illness, so it should be taken seriously if it persists.\n\n"
            "Try this right away:\n"
            "- Sit or lie down safely.\n"
            "- Drink fluids slowly.\n"
            "- Stand up gradually and avoid sudden movement.\n\n"
            "Please seek medical care if you faint, have chest pain, trouble breathing, severe weakness, or persistent dizziness."
        )

    if primary == "fatigue":
        return (
            "Ongoing weakness or fatigue can happen with infection, poor sleep, dehydration, or emotional strain.\n\n"
            "For now:\n"
            "- Rest as much as possible.\n"
            "- Drink fluids and try light food if you can tolerate it.\n"
            "- If you also have fever or body aches, managing the fever and hydration becomes more important.\n\n"
            "Please consult a doctor if the weakness is severe, keeps getting worse, or is paired with fever, breathing problems, or poor intake."
        )

    if request_mode == "solution":
        return (
            "I can help with practical next steps if you tell me the symptom clearly, for example: fever, cold, cough, sore throat, headache, stomach pain, vomiting, dizziness, or weakness.\n\n"
            "Once I know the symptom, I can give a more direct home-care response and tell you when a doctor visit is important."
        )

    return (
        "I understand this is a physical health concern. Please tell me the main symptom clearly, such as fever, cold, cough, sore throat, headache, stomach pain, dizziness, or weakness.\n\n"
        "Once you describe the symptom, I can respond with more specific self-care advice and medical warning signs."
    )


def analyze_emotional_state_en(text):
    text_lower = text.lower()
    patterns = {
        "overwhelmed": ["overwhelmed", "too much", "cannot handle", "can't handle", "falling apart"],
        "stress": ["stress", "stressed", "pressure", "burnout", "overworked", "deadline"],
        "anxiety": ["anxious", "anxiety", "panic", "nervous", "heart racing", "overthinking", "worried"],
        "loneliness": ["alone", "lonely", "nobody understands", "no one understands", "isolated"],
        "sadness": ["sad", "down", "low", "crying", "empty", "hopeless", "broken"],
        "fatigue": ["exhausted", "drained", "tired", "worn out", "no energy"],
        "self_doubt": ["worthless", "failure", "not enough", "useless", "hate myself"],
        "sleep": ["cannot sleep", "can't sleep", "cant sleep", "insomnia", "not sleeping", "sleeping badly", "mind wont stop", "mind won't stop"],
    }
    matches = []
    for name, keywords in patterns.items():
        if any(_kw_match(keyword, text_lower) for keyword in keywords):
            matches.append(name)
    return matches


def detect_crisis_language_en(text):
    text_lower = text.lower()
    crisis_keywords = [
        "want to die", "kill myself", "end my life", "hurt myself",
        "suicidal", "self harm", "do not want to live", "don't want to live",
        "not safe with myself", "harm myself",
    ]
    return any(_kw_match(keyword, text_lower) for keyword in crisis_keywords)


def detect_support_question_en(text):
    text_lower = text.lower()
    support_keywords = [
        "specialist", "therapist", "therapy", "counselor", "counsellor",
        "psychologist", "psychiatrist", "mental health professional",
        "doctor", "professional help", "should i check", "should i see someone",
        "should i get help", "should i talk to someone",
    ]
    return any(_kw_match(keyword, text_lower) for keyword in support_keywords)


def specialist_response_en(text):
    has_physical = bool(detect_physical_conditions(text, "en"))
    has_emotional = bool(analyze_emotional_state_en(text))

    if has_physical:
        return (
            "If this is mainly a physical symptom, seeing a doctor is a good idea when the symptom is severe, keeps getting worse, lasts longer than expected, or starts affecting breathing, hydration, or daily functioning.\n\n"
            "If you want, tell me the exact symptom and I can help you judge whether home care is enough or a doctor visit makes more sense."
        )

    if has_emotional or "stress" in text.lower() or "anx" in text.lower():
        return (
            "Yes, checking with a mental health professional can be a really good step, especially if the stress has been building up, keeps coming back, or is affecting your sleep, work, appetite, focus, or relationships.\n\n"
            "A simple way to think about it:\n"
            "- A counselor or therapist is a good choice if you want support, coping tools, and someone to talk through things with.\n"
            "- A psychiatrist can help if symptoms feel severe, you think medication might be needed, or daily functioning is getting much harder.\n\n"
            "You do not need to wait until things become extreme before asking for help. Reaching out early is actually a strong move."
        )

    return (
        "Yes, it can be a good idea to check with a specialist if this has been bothering you for a while or is starting to affect daily life.\n\n"
        "If this is about stress, anxiety, low mood, sleep trouble, or feeling emotionally overwhelmed, a counselor, therapist, or psychologist would usually be the best first step.\n"
        "If this is mainly a physical symptom, then a doctor is the better place to start.\n\n"
        "You do not need to be at your worst before asking for help. If you want, tell me what is going on and I can help you decide which kind of support fits best."
    )


def emotional_response_en(text, sentiment, topic):
    states = analyze_emotional_state_en(text)

    if detect_crisis_language_en(text):
        return (
            "What you just shared sounds really heavy, and I am glad you said it out loud.\n\n"
            "You do not need to carry this by yourself right now.\n"
            "- Please message or call someone you trust immediately.\n"
            "- If you feel unsafe or might harm yourself, contact emergency help or a crisis service now.\n"
            "- Stay near another person if you can.\n\n"
            "If you want, send me one short line: 'I am safe' or 'I am not safe,' and I will respond accordingly."
        )

    if "overwhelmed" in states or topic == "stress":
        return (
            "That sounds like a lot to hold at once, and it makes sense that you feel stressed.\n\n"
            "Let us make this smaller for the next 10 minutes:\n"
            "- Put all the pressure aside except one thing that truly needs attention first.\n"
            "- Take 5 slow breaths: in for 4 seconds, out for 6 seconds.\n"
            "- Do one tiny action only, like replying to one message, drinking water, or writing the first step down.\n\n"
            "You do not need to solve your whole life tonight. You just need one manageable next step."
        )

    if "anxiety" in states or topic == "anxiety":
        return (
            "I can hear the tension in that, and anxiety really can make everything feel louder and more urgent than it is.\n\n"
            "Try this with me right now:\n"
            "- Exhale fully first.\n"
            "- Breathe in for 4 seconds and out for 6 seconds, five times.\n"
            "- Look around and name 3 things you can see and 2 things you can touch.\n"
            "- Do not argue with every thought right now; just let the thoughts pass and come back to your breathing.\n\n"
            "If you want, I can also help you sort whether this is stress, panic, or overthinking."
        )

    if "loneliness" in states:
        return (
            "Feeling alone can make everything heavier, and I am sorry it feels like that right now.\n\n"
            "A gentle next step could be:\n"
            "- Send one simple message to someone safe, even just 'Can we talk later?'\n"
            "- Stay around other people if being alone is making things worse.\n"
            "- Do one grounding thing near you, like tea, a shower, music, or sitting by a window.\n\n"
            "You are not weak for needing connection. Most people do when things get hard."
        )

    if "sadness" in states:
        return (
            "That sounds painful, and I am really sorry you are carrying it right now.\n\n"
            "When your mood feels low, try not to force a big fix. Start smaller:\n"
            "- Drink some water.\n"
            "- Sit somewhere with light or fresh air for a few minutes.\n"
            "- Do one kind thing for yourself, even if it feels tiny.\n\n"
            "If this low feeling has been building for days or weeks, talking with a trusted person or counselor would be a strong next step, not a failure."
        )

    if "fatigue" in states or topic == "fatigue":
        return (
            "It sounds like you are emotionally worn down, not just physically tired.\n\n"
            "For now, I would treat this like overload:\n"
            "- Pause for a few minutes without trying to be productive.\n"
            "- Drink water and eat something light if you have not eaten.\n"
            "- Pick one thing you can postpone today.\n\n"
            "Rest is not laziness when your mind feels stretched thin."
        )

    if "sleep" in states:
        return (
            "Poor sleep can make stress, sadness, and anxiety feel much harder to manage.\n\n"
            "For tonight, keep it simple:\n"
            "- Put the phone away for a bit if you can.\n"
            "- Dim the lights.\n"
            "- Slow your breathing and stop trying to force sleep.\n\n"
            "If you want, I can give you a short bedtime calming routine."
        )

    if "self_doubt" in states:
        return (
            "That kind of self-talk can be brutal, and I am sorry it is hitting you like this.\n\n"
            "When your mind is attacking you, do not treat those thoughts as facts.\n"
            "- Pause before agreeing with them.\n"
            "- Ask: what would I say to a friend who said this about themselves?\n"
            "- Focus on one stabilizing action right now, not on proving your worth.\n\n"
            "You do not need to earn care before receiving it."
        )

    return (
        "I am here with you, and whatever is going on, you do not have to untangle it perfectly for me.\n\n"
        "A good next step is to tell me one of these clearly:\n"
        "- what you are feeling most right now\n"
        "- what happened today\n"
        "- what kind of help you want first\n\n"
        "I will try to respond in a practical and supportive way."
    )

# ══════════════════════════════════════════════════════════════
#  RESPONSES — English
# ══════════════════════════════════════════════════════════════

def emergency_en():
    return (
        "💛 I hear you, and I'm really glad you reached out.\n\n"
        "What you're feeling right now matters deeply — you are not alone in this.\n\n"
        "Please reach out to someone you trust right now — a family member, close friend, or a mental health crisis line.\n\n"
        "🇮🇳 **iCall (India):** 9152987821\n"
        "🌍 **Crisis Text Line:** Text HOME to 741741\n\n"
        "You deserve support. Please don't face this alone. 🙏"
    )


def solution_en(topic):
    solutions = {
        "anxiety": (
            "That restless, on-edge feeling is really draining — and very manageable. 💙\n\n"
            "Here's what can help right now:\n\n"
            "• **Box breathing:** Inhale 4 sec → hold 4 → exhale 4 → hold 4. Repeat 4×.\n"
            "• **Ground yourself:** Name 5 things you see, 4 you can touch, 3 you hear.\n"
            "• **Cold water:** Splash cold water on your face — it activates your calm reflex.\n"
            "• **Limit caffeine** for the rest of today.\n\n"
            "Would you like a longer calming routine?"
        ),
        "fatigue": (
            "Running on empty is exhausting — let's get you some energy back. 🌿\n\n"
            "Try these right now:\n\n"
            "• **Micro-rest:** Close your eyes for 5–10 minutes.\n"
            "• **Hydrate:** Drink a full glass of water.\n"
            "• **Light movement:** A slow 5-minute walk resets your energy.\n"
            "• **Tonight:** Screens off 30 min before bed.\n\n"
            "Would you like a simple wind-down routine?"
        ),
        "stress": (
            "Stress builds up quietly — good thing there are ways to release it. 🌸\n\n"
            "Start with these:\n\n"
            "• **Brain dump:** Write everything stressing you on paper.\n"
            "• **Prioritize:** Circle just ONE thing to handle today.\n"
            "• **Slow breath:** 4 seconds in, 6 seconds out.\n"
            "• **Step away:** A 10-minute break away from screens helps.\n\n"
            "Want help organizing what's on your plate?"
        ),
        "physical_discomfort": (
            "Physical discomfort can feel alarming — here's some gentle guidance. 🩵\n\n"
            "• **Sit or lie down** in a comfortable position.\n"
            "• **Slow your breathing** — it helps with tightness and dizziness.\n"
            "• **Sip water** slowly if you feel nauseous.\n"
            "• **Note the symptoms** — duration, intensity, what helps.\n\n"
            "⚠️ *If symptoms are severe or worsening — please seek medical attention. This is not a diagnosis.*"
        ),
        "general": (
            "It sounds like things have been hard lately. Here's a gentle reset: 💚\n\n"
            "• **Breathe:** 4 in, hold 2, 6 out. Do this 5 times.\n"
            "• **Move your body:** Even stretching for 2 minutes helps.\n"
            "• **Connect:** Reach out to one person today.\n"
            "• **Be kind to yourself:** You're doing the best you can.\n\n"
            "Want more specific support? Tell me what's going on."
        )
    }
    return solutions.get(topic, solutions["general"])


def symptom_en(topic):
    responses = {
        "anxiety": (
            "I hear you — those feelings in your body can feel really frightening. 💙\n\n"
            "What you're describing can be associated with anxiety — racing heart, shaking, tight chest.\n\n"
            "• Try slow breathing: 4 seconds in, 6 seconds out.\n"
            "• Hold something cold — it helps calm the nervous system.\n"
            "• Remember: these sensations are uncomfortable but not dangerous.\n\n"
            "⚠️ *Not a medical diagnosis. If symptoms persist, please consult a healthcare provider.*\n\n"
            "Would you like some calming techniques?"
        ),
        "physical_discomfort": (
            "I'm sorry you're feeling this way physically. 🩵\n\n"
            "These symptoms can be associated with stress or anxiety — but only a doctor can properly evaluate them.\n\n"
            "• Sit or lie in a comfortable position.\n"
            "• Breathe slowly and steadily.\n"
            "• Sip water if you feel nauseous.\n\n"
            "⚠️ *Please seek medical attention if symptoms are severe or sudden. This is not a diagnosis.*"
        ),
        "fatigue": (
            "Persistent tiredness is your body asking for attention. 🌿\n\n"
            "Ongoing fatigue can be associated with poor sleep, stress, or emotional exhaustion.\n\n"
            "• Rest if you can — even 10 minutes helps.\n"
            "• Drink water and eat something light.\n"
            "• Avoid screens before sleep tonight.\n\n"
            "⚠️ *If fatigue is severe or lasts weeks, check with a doctor.*"
        ),
        "general": (
            "Thank you for sharing what you're feeling. 💚\n\n"
            "What you're describing may be connected to stress or emotional tension affecting the body.\n\n"
            "• Take a slow breath and give yourself a moment.\n"
            "• Note when symptoms started and what helps.\n\n"
            "⚠️ *For any physical symptoms, please consult a healthcare professional.*"
        )
    }
    return responses.get(topic, responses["general"])


def solution_en(topic, text=""):
    solutions = {
        "anxiety": (
            "That restless, on-edge feeling is really draining, but there are practical ways to settle it.\n\n"
            "Try this now:\n"
            "- Box breathing: inhale for 4 seconds, hold for 4, exhale for 4, hold for 4.\n"
            "- Ground yourself by naming 5 things you see, 4 you can touch, and 3 you hear.\n"
            "- Reduce caffeine for the rest of the day.\n\n"
            "If you want, I can also give you a short calming routine for the next 10 minutes."
        ),
        "fatigue": (
            "Persistent tiredness usually improves best with rest, hydration, and a low-pressure routine.\n\n"
            "A good starting plan is:\n"
            "- Rest for a few minutes without screens.\n"
            "- Drink a full glass of water.\n"
            "- Have something light to eat if you have not eaten.\n"
            "- Try to keep tonight's sleep routine simple and early.\n\n"
            "If the fatigue is severe, prolonged, or comes with fever or breathlessness, a doctor review is important."
        ),
        "stress": (
            "Stress responds better to small, clear steps than to trying to fix everything at once.\n\n"
            "Try this approach:\n"
            "- Write down what is bothering you.\n"
            "- Choose one urgent task only.\n"
            "- Slow your breathing: in for 4 seconds, out for 6 seconds.\n"
            "- Step away from screens for 10 minutes if possible.\n\n"
            "If you want, I can help you break the stress into one immediate next step."
        ),
        "physical_discomfort": physical_response_en(text, request_mode="solution"),
        "general": (
            "I can help better if you say whether this is mainly emotional distress, stress, anxiety, or a physical symptom such as fever, cold, cough, headache, stomach pain, dizziness, or weakness.\n\n"
            "Once you tell me the main problem clearly, I can give a more direct response."
        ),
    }
    return solutions.get(topic, solutions["general"])


def symptom_en(topic, text=""):
    responses = {
        "anxiety": (
            "Physical anxiety symptoms can feel intense, but they often settle when your breathing and body tension come down.\n\n"
            "Try this now:\n"
            "- Breathe in for 4 seconds and out for 6 seconds.\n"
            "- Sit down and loosen your shoulders and jaw.\n"
            "- Hold something cool or cold if that helps ground you.\n\n"
            "Please seek urgent medical help if you have severe chest pain, fainting, or trouble breathing."
        ),
        "physical_discomfort": physical_response_en(text, request_mode="symptom"),
        "fatigue": (
            "Tiredness can happen with illness, poor sleep, stress, dehydration, or low intake, so it helps to monitor the pattern.\n\n"
            "For now:\n"
            "- Rest.\n"
            "- Drink fluids.\n"
            "- Try light food if you feel able.\n\n"
            "If the fatigue is severe, prolonged, or linked with fever, breathing trouble, or worsening weakness, please speak with a doctor."
        ),
        "general": (
            "Thanks for sharing that. If this is a physical symptom, tell me the main issue directly, such as fever, cold, cough, sore throat, headache, stomach pain, vomiting, dizziness, or weakness.\n\n"
            "Then I can give a more specific and useful response."
        ),
    }
    return responses.get(topic, responses["general"])


def general_en(text=""):
    if detect_support_question_en(text):
        return specialist_response_en(text)
    if analyze_emotional_state_en(text):
        return emotional_response_en(text, "neutral", "general")
    if detect_physical_conditions(text, "en"):
        return physical_response_en(text, request_mode="symptom")
    return (
        "I am here and listening.\n\n"
        "You can tell me:\n"
        "- how you are feeling emotionally\n"
        "- any symptoms you are having\n"
        "- what kind of help you want right now\n\n"
        "There is no perfect way to start. Just say what is going on."
    )


def emotional_en(topic, sentiment):
    openers = {
        "very_negative": "What you're going through sounds incredibly heavy, and I want you to know — you're not alone. 💛",
        "negative": "I hear you, and what you're feeling is completely valid. 💙",
        "neutral": "I'm here with you. 💚",
        "positive": "I'm glad you reached out, even on better days. 🌸"
    }
    opener = openers.get(sentiment, openers["neutral"])
    support = {
        "anxiety": (
            f"{opener}\n\n"
            "Anxiety can make everything feel more intense than it is.\n\n"
            "• Remind yourself: *this feeling will pass.*\n"
            "• Try 4-6 breathing (4 in, 6 out) for 2 minutes.\n"
            "• Write down one worry and one reason it might be okay.\n\n"
            "You're stronger than your anxiety. 🌿"
        ),
        "stress": (
            f"{opener}\n\n"
            "Stress piles on quietly until everything feels too much.\n\n"
            "• You don't have to solve everything today.\n"
            "• Pick one small thing to do, let the rest wait.\n"
            "• It's okay to step away and breathe.\n\n"
            "You're carrying a lot — be gentle with yourself. 🌸"
        ),
        "fatigue": (
            f"{opener}\n\n"
            "Emotional exhaustion deserves the same care as physical tiredness.\n\n"
            "• It's okay to slow down.\n"
            "• Rest without guilt — recovery is productive.\n"
            "• Don't compare your energy to others right now.\n\n"
            "You're allowed to take a break. 💛"
        ),
        "general": (
            f"{opener}\n\n"
            "Whatever you're carrying right now, you don't have to carry it alone.\n\n"
            "• Feelings are valid messengers, not permanent states.\n"
            "• One breath at a time is enough for now.\n"
            "• You reached out, and that takes courage.\n\n"
            "I'm here. What would help most right now? 💚"
        )
    }
    return support.get(topic, support["general"])


#  RESPONSES — Hindi
# ══════════════════════════════════════════════════════════════

def emergency_hi():
    return (
        "💛 मैं आपकी बात सुन रहा हूं, और मुझे खुशी है कि आपने यहाँ आकर बात की।\n\n"
        "अभी आप जो महसूस कर रहे हैं वो बहुत ज़रूरी है — आप अकेले नहीं हैं।\n\n"
        "कृपया अभी किसी भरोसेमंद इंसान से मिलें — परिवार, दोस्त, या हेल्पलाइन।\n\n"
        "🇮🇳 **iCall (India):** 9152987821\n"
        "📞 **Vandrevala Foundation:** 1860-2662-345 (24/7)\n\n"
        "आप अकेले मत रहिए। मदद लेना ताकत की निशानी है। 🙏"
    )


def solution_hi(topic):
    solutions = {
        "anxiety": (
            "यह बेचैनी और घबराहट बहुत थका देती है — लेकिन इसे ठीक किया जा सकता है। 💙\n\n"
            "अभी यह करें:\n\n"
            "• **Box breathing:** 4 सेकंड सांस लें → 4 रोकें → 4 छोड़ें → 4 रोकें। 4 बार दोहराएं。\n"
            "• **5-4-3:** 5 चीज़ें देखें, 4 छुएं, 3 सुनें — यह दिमाग को वर्तमान में लाता है।\n"
            "• **ठंडा पानी:** चेहरे पर ठंडा पानी छिड़कें — तुरंत राहत मिलती है।\n"
            "• **चाय/कॉफी कम करें** आज के लिए।\n\n"
            "क्या आप एक लंबी शांत करने की दिनचर्या चाहते हैं?"
        ),
        "fatigue": (
            "थकान महसूस हो रही है — चलिए थोड़ी ऊर्जा वापस लाते हैं। 🌿\n\n"
            "अभी यह करें:\n\n"
            "• **5-10 मिनट आंखें बंद करें** — नींद नहीं भी आई तो भी फ़र्क पड़ता है।\n"
            "• **पानी पिएं** — थकान का एक बड़ा कारण पानी की कमी है।\n"
            "• **हल्की चहलकदमी** — 5 मिनट की वॉक भी ऊर्जा देती है।\n"
            "• **रात को:** सोने से 30 मिनट पहले फोन बंद करें।\n\n"
            "क्या आप एक नींद सुधारने की दिनचर्या चाहते हैं?"
        ),
        "stress": (
            "तनाव चुपचाप बढ़ता है — लेकिन इसे कम करने के तरीके हैं। 🌸\n\n"
            "इनसे शुरू करें:\n\n"
            "• **Brain Dump:** जो भी परेशान कर रहा है, कागज़ पर लिख डालें।\n"
            "• **एक काम चुनें:** आज सिर्फ एक ज़रूरी काम करें, बाकी कल।\n"
            "• **धीमी सांस:** 4 सेकंड नाक से लें, 6 सेकंड मुंह से छोड़ें।\n"
            "• **10 मिनट का ब्रेक:** स्क्रीन से दूर, बस बैठें।\n\n"
            "क्या आप अपनी जिम्मेदारियों को व्यवस्थित करने में मदद चाहते हैं?"
        ),
        "physical_discomfort": (
            "शारीरिक तकलीफ डरावनी लग सकती है — यह करें अभी। 🩵\n\n"
            "• **आराम से बैठें या लेटें।**\n"
            "• **धीमी सांस लें** — तेज़ सांस सीने की जकड़न बढ़ाती है।\n"
            "• **धीरे-धीरे पानी पिएं** — मतली में राहत मिलती है।\n"
            "• **लक्षण नोट करें** — कब से है, कितना तेज़ है।\n\n"
            "⚠️ *अगर लक्षण गंभीर या अचानक हैं — तुरंत डॉक्टर से मिलें।*"
        ),
        "general": (
            "लगता है कुछ मुश्किल चल रहा है। यह छोटा सा रीसेट ट्राई करें: 💚\n\n"
            "• **सांस लें:** 4 अंदर, 2 रोकें, 6 बाहर। 5 बार।\n"
            "• **थोड़ा हिलें:** 2 मिनट स्ट्रेचिंग भी मदद करती है।\n"
            "• **किसी से बात करें:** एक मैसेज भी काफी है।\n"
            "• **खुद पर दयालु रहें:** आप पूरी कोशिश कर रहे हैं।\n\n"
            "और क्या हो रहा है? मुझे बताएं।"
        )
    }
    return solutions.get(topic, solutions["general"])


def symptom_hi(topic):
    responses = {
        "anxiety": (
            "आपकी बात सुन रहा हूं — शरीर में ये बदलाव डरावने लगते हैं। 💙\n\n"
            "आप जो बता रहे हैं वो anxiety से जुड़ा हो सकता है।\n\n"
            "• अभी धीमी सांस लें: 4 सेकंड अंदर, 6 सेकंड बाहर।\n"
            "• कुछ ठंडा पकड़ें — nervous system को शांत करता है।\n"
            "• याद रखें: ये sensations असुविधाजनक हैं, खतरनाक नहीं।\n\n"
            "⚠️ *यह कोई मेडिकल निदान नहीं है। लक्षण लंबे समय तक रहें तो डॉक्टर से मिलें।*"
        ),
        "physical_discomfort": (
            "आप जो महसूस कर रहे हैं उसके लिए दुख है। 🩵\n\n"
            "ये लक्षण तनाव या anxiety से जुड़े हो सकते हैं।\n\n"
            "• आरामदायक स्थिति में बैठें।\n"
            "• धीमी, गहरी सांस लें।\n"
            "• मतली हो तो धीरे-धीरे पानी पिएं।\n\n"
            "⚠️ *लक्षण गंभीर या अचानक हों तो तुरंत मेडिकल मदद लें।*"
        ),
        "fatigue": (
            "लगातार थकान शरीर की आवाज़ है। 🌿\n\n"
            "लंबे समय की थकान खराब नींद, तनाव या emotional exhaustion से जुड़ी हो सकती है।\n\n"
            "• अभी थोड़ा आराम करें — 10 मिनट भी काफी है।\n"
            "• पानी पिएं और कुछ हल्का खाएं।\n"
            "• आज रात सोने से पहले स्क्रीन बंद करें।\n\n"
            "⚠️ *अगर थकान हफ्तों से है, तो डॉक्टर से मिलें।*"
        ),
        "general": (
            "बताने के लिए शुक्रिया। 💚\n\n"
            "आप जो महसूस कर रहे हैं वो तनाव या emotional tension से जुड़ा हो सकता है।\n\n"
            "• धीमी सांस लें और खुद को थोड़ा समय दें।\n"
            "• नोट करें — कब से है, क्या बेहतर करता है।\n\n"
            "⚠️ *किसी भी शारीरिक लक्षण के लिए healthcare professional से मिलें।*"
        )
    }
    return responses.get(topic, responses["general"])


def emotional_hi(topic, sentiment):
    openers = {
        "very_negative": "जो आप झेल रहे हैं वो बहुत भारी है — आप अकेले नहीं हैं। 💛",
        "negative": "आपकी बात सुन रहा हूं, और आप जो महसूस कर रहे हैं वो बिल्कुल सही है। 💙",
        "neutral": "मैं यहाँ हूं। 💚",
        "positive": "अच्छे दिनों में भी बात करना ज़रूरी है। 🌸"
    }
    opener = openers.get(sentiment, openers["neutral"])
    support = {
        "anxiety": (
            f"{opener}\n\n"
            "Anxiety सब कुछ ज़्यादा intense बना देती है।\n\n"
            "• खुद को याद दिलाएं: *यह भावना गुज़र जाएगी।*\n"
            "• 4-6 breathing ट्राई करें (4 अंदर, 6 बाहर) — 2 मिनट।\n"
            "• एक चिंता लिखें और एक कारण लिखें कि शायद वो ठीक हो जाए।\n\n"
            "आप अपनी anxiety से ज़्यादा मज़बूत हैं। 🌿"
        ),
        "stress": (
            f"{opener}\n\n"
            "तनाव चुपचाप बढ़ता है जब तक सब कुछ भारी नहीं लगने लगता।\n\n"
            "• आज सब कुछ solve करना ज़रूरी नहीं।\n"
            "• एक छोटी चीज़ चुनें और बाकी को कल के लिए छोड़ दें।\n"
            "• सांस लेना और रुकना भी ज़रूरी है।\n\n"
            "आप बहुत कुछ उठा रहे हैं — खुद पर थोड़ी दया करें। 🌸"
        ),
        "fatigue": (
            f"{opener}\n\n"
            "Emotional exhaustion physical थकान जितनी ही असली है।\n\n"
            "• धीमे होना ठीक है।\n"
            "• बिना guilt के आराम करें — recover करना भी productive है।\n"
            "• दूसरों से अपनी energy compare मत करें अभी।\n\n"
            "आपको break लेने का पूरा हक़ है। 💛"
        ),
        "general": (
            f"{opener}\n\n"
            "जो भी बोझ है अभी, उसे अकेले मत उठाइए।\n\n"
            "• भावनाएं संदेश हैं, permanent नहीं।\n"
            "• अभी एक सांस काफी है।\n"
            "• आपने यहाँ आकर बात की — यह हिम्मत की बात है।\n\n"
            "मैं यहाँ हूं। अभी क्या सबसे ज़्यादा मदद करेगा? 💚"
        )
    }
    return support.get(topic, support["general"])


def general_hi():
    return (
        "मैं यहाँ हूं और सुन रहा हूं। 💚\n\n"
        "आप मुझे बता सकते हैं:\n\n"
        "• आप emotionally कैसा महसूस कर रहे हैं\n"
        "• कोई शारीरिक लक्षण जो हो रहे हैं\n"
        "• अभी किस चीज़ में मदद चाहिए\n\n"
        "शुरू करने का कोई सही या गलत तरीका नहीं है। क्या बात है?"
    )

# ══════════════════════════════════════════════════════════════
#  MAIN BUILD RESPONSE
# ══════════════════════════════════════════════════════════════

def emergency_hinglish():
    return (
        "Jo aap keh rahe ho woh bahut serious lag raha hai, aur main glad hoon ki aapne likha.\n\n"
        "Abhi please akela mat raho.\n"
        "- Kisi trusted person ko turant call ya message karo.\n"
        "- Agar khud ko harm karne ka risk lag raha hai, emergency support abhi contact karo.\n"
        "- Ho sake to kisi ke paas baith jao.\n\n"
        "India mein iCall: 9152987821\n"
        "Reply kar sako to bas itna likho: 'main safe hoon' ya 'main safe nahi hoon'."
    )


def solution_hinglish(topic):
    solutions = {
        "anxiety": (
            "Ye ghabrahat aur uneasy feeling heavy lag sakti hai, but thoda calm laaya ja sakta hai.\n\n"
            "Abhi ye try karo:\n"
            "- 4 second saans andar lo, 6 second bahar chhodo, 5 rounds.\n"
            "- 5 cheezein dekho, 4 touch karo, 3 sounds notice karo.\n"
            "- Thoda thanda paani piyo ya face wash karo.\n\n"
            "Chaho to main 2 minute ka quick calming routine bhi de sakta hoon."
        ),
        "fatigue": (
            "Agar body aur mind dono drained lag rahe hain, to abhi target sirf thoda stable hona hona chahiye.\n\n"
            "Start yahan se:\n"
            "- 5-10 minute bina screen ke rest karo.\n"
            "- Paani piyo.\n"
            "- Kuch halka kha lo agar kaafi der se nahi khaya.\n"
            "- Aaj ke liye pace thoda slow rakho.\n\n"
            "Agar weakness zyada hai ya fever ke saath hai, doctor se check karna better rahega."
        ),
        "stress": (
            "Lag raha hai dimag pe load zyada ho gaya hai. Chalo isse thoda chhota karte hain.\n\n"
            "Ye karo:\n"
            "- Jo jo tension hai sab ek jagah likh do.\n"
            "- Sirf ek kaam choose karo jo abhi sabse important hai.\n"
            "- 10 minute ka short break lo.\n"
            "- Khud se bas next step pucho, poora solution nahi.\n\n"
            "Agar chaho to jo tension hai woh ek line mein bhejo, main usse organize karne mein help karunga."
        ),
        "physical_discomfort": (
            "Agar body symptoms ho rahe hain to pe pehle observe karna aur basic care karna useful hota hai.\n\n"
            "Abhi:\n"
            "- Rest karo.\n"
            "- Paani ya warm fluids lo.\n"
            "- Exact symptom batao: fever, cold, cough, headache, pet dard, ya dizziness.\n\n"
            "Phir main zyada direct guidance de paunga."
        ),
        "general": (
            "Main help kar sakta hoon, bas mujhe thoda clear batao ki problem zyada emotional hai ya physical.\n\n"
            "Example:\n"
            "- 'bahut anxious feel ho raha hai'\n"
            "- 'mujhe bukhar hai kya karu'\n"
            "- 'sleep nahi aa rahi'\n\n"
            "Uske baad main proper next step dunga."
        ),
    }
    return solutions.get(topic, solutions["general"])


def symptom_hinglish(topic, text=""):
    conditions = detect_physical_conditions(text, "hi")
    primary = conditions[0] if conditions else topic
    symptom_responses = {
        "fever": (
            "Bukhar body ke infection response ki wajah se ho sakta hai, isliye thoda monitor karna zaroori hai.\n\n"
            "Abhi kya karo:\n"
            "- Temperature check karo agar thermometer hai.\n"
            "- Rest karo aur fluids zyada lo.\n"
            "- Agar allowed ho to label ke hisaab se paracetamol li ja sakti hai.\n\n"
            "Agar bukhar bahut high ho, 2-3 din se zyada rahe, ya saans, confusion, severe weakness ke saath ho to doctor se jaldi baat karo."
        ),
        "cold": (
            "Ye cold ya flu type symptoms lag rahe hain.\n\n"
            "Thoda relief ke liye:\n"
            "- Rest karo.\n"
            "- Warm water ya steam helpful ho sakta hai.\n"
            "- Hydration maintain rakho.\n\n"
            "Agar breathing problem ho, fever high ho, ya symptoms improve na karein to doctor se consult karo."
        ),
        "cough": (
            "Khansi cold, throat irritation, ya infection se ho sakti hai.\n\n"
            "Abhi ye try karo:\n"
            "- Warm fluids lo.\n"
            "- Dhool ya smoke se door raho.\n"
            "- Throat ko rest do.\n\n"
            "Agar saans mein dikkat ho, chest pain ho, ya khansi bahut lambi chale to medical advice lo."
        ),
        "sore_throat": (
            "Gale ka dard viral infection ya irritation ki wajah se ho sakta hai.\n\n"
            "- Warm water ya garam liquids lo.\n"
            "- Soft food lo.\n"
            "- Rest aur hydration pe focus karo.\n\n"
            "Agar nigalne mein problem ho, breathing issue ho, ya fever high ho to doctor se check karo."
        ),
        "headache": (
            "Headache dehydration, stress, fever, ya sleep issue se bhi ho sakta hai.\n\n"
            "Abhi:\n"
            "- Quiet jagah mein rest karo.\n"
            "- Paani piyo.\n"
            "- Screen thodi der ke liye avoid karo.\n\n"
            "Agar headache sudden aur bahut severe ho, ya vomiting, confusion, high fever ke saath ho to urgent care lo."
        ),
        "stomach_issue": (
            "Pet ka issue ho to dehydration se bachna sabse important hai.\n\n"
            "- Thoda thoda paani ya ORS lo.\n"
            "- Heavy ya oily food avoid karo.\n"
            "- Rest karo.\n\n"
            "Agar pain severe ho, fluid ruk na raha ho, ya symptoms worsen ho rahe ho to doctor se consult karo."
        ),
        "dizziness": (
            "Chakkar dehydration, weakness, anxiety, ya illness ki wajah se ho sakta hai.\n\n"
            "- Seedha baith jao ya let jao.\n"
            "- Dheere dheere paani piyo.\n"
            "- Achaanak mat uthho.\n\n"
            "Agar fainting, chest pain, breathing issue, ya lagataar dizziness ho to doctor se check karao."
        ),
        "fatigue": (
            "Agar weakness ya thakan lagataar hai, to body aur mind dono ko rest chahiye ho sakta hai.\n\n"
            "- Rest karo.\n"
            "- Fluids aur halka food lo.\n"
            "- Sleep ko priority do.\n\n"
            "Agar weakness zyada ho, fever ke saath ho, ya worse hoti ja rahi ho to doctor ko dikhao."
        ),
    }
    return symptom_responses.get(
        primary,
        "Aap exact symptom thoda clear likho, jaise fever, cold, cough, headache, pet dard, vomiting, chakkar, ya weakness.\n\nPhir main proper home-care aur warning signs bata dunga."
    )


def emotional_hinglish(topic, sentiment):
    opener = {
        "very_negative": "Jo aap feel kar rahe ho woh bahut heavy hai, aur aapko ise akela handle nahi karna chahiye.",
        "negative": "Main samajh raha hoon ki ye phase aapke liye easy nahi hai.",
        "neutral": "Main yahin hoon, aap aaraam se bol sakte ho.",
        "positive": "Achha hai ki aap baat kar rahe ho.",
    }.get(sentiment, "Main yahin hoon, aap aaraam se bol sakte ho.")
    support = {
        "anxiety": (
            f"{opener}\n\n"
            "Agar anxiety ya panic jaisa feel ho raha hai, to pehle body ko signal do ki abhi thoda safe ho.\n"
            "- Slow breathing karo: 4 in, 6 out.\n"
            "- Jo thought aa raha hai usse bas note karo, usse fight mat karo.\n"
            "- Pair zameen par feel karo aur room mein 3 cheezein notice karo.\n\n"
            "Ye feeling hamesha isi intensity par nahi rahegi."
        ),
        "stress": (
            f"{opener}\n\n"
            "Stress jab zyada ho jata hai to sab kuch ek saath toot padta hua lagta hai.\n"
            "- Sirf ek next step choose karo.\n"
            "- Paani piyo aur 5 minute break lo.\n"
            "- Jo urgent nahi hai use abhi side par rakho.\n\n"
            "Aapko abhi sab solve nahi karna, bas thoda stable hona hai."
        ),
        "fatigue": (
            f"{opener}\n\n"
            "Ye sirf laziness wali baat nahi lag rahi, ye overload ya exhaustion jaisa lag raha hai.\n"
            "- Thoda rest lo bina guilt ke.\n"
            "- Light food aur water lo.\n"
            "- Aaj expectations thodi kam rakho.\n\n"
            "Recovery bhi kaam ka hissa hoti hai."
        ),
        "general": (
            f"{opener}\n\n"
            "Aap jo feel kar rahe ho woh share karna hi ek strong step hai.\n"
            "Mujhe ek line mein bata do:\n"
            "- sabse heavy kya lag raha hai\n"
            "- body symptom zyada hai ya emotional load\n"
            "- abhi kis type ki help chahiye\n\n"
            "Main wahan se aapke saath step by step chalunga."
        ),
    }
    return support.get(topic, support["general"])


def general_hinglish():
    return (
        "Main yahin hoon aur sun raha hoon.\n\n"
        "Aap simple tareeke se likh sakte ho:\n"
        "- emotionally kaisa feel ho raha hai\n"
        "- body mein kya symptom ho raha hai\n"
        "- abhi kis cheez mein help chahiye\n\n"
        "Perfect likhne ki zaroorat nahi hai. Jaise mann kare waise bolo."
    )


def build_response(intent, sentiment, topic, lang, text=""):
    use_hinglish = lang == "hi" and prefers_hinglish(text)
    session[RULE_LANGUAGE_KEY] = "hinglish" if use_hinglish else lang
    session.modified = True

    if lang == "hi":
        if use_hinglish:
            if intent in RULE_BASED_INTENTS:
                return generate_response(intent, topic, sentiment, session, text=text)
            return general_hinglish()
        if intent in RULE_BASED_INTENTS:
            return generate_response(intent, topic, sentiment, session, text=text)
        return general_hi()
    else:
        if intent in RULE_BASED_INTENTS:
            return generate_response(intent, topic, sentiment, session, text=text)
        return general_en(text)


def resolve_turn_analysis(user_message, lang, session_store):
    keyword_match = match_keyword_intent(user_message, lang)
    sentiment, sentiment_confidence = detect_sentiment_ml(user_message, lang)
    intent, intent_confidence = detect_intent_ml(user_message, lang)
    topic = detect_topic(user_message, lang)
    priority_route = detect_priority_route(user_message, lang, keyword_match)
    detected_subtopic = priority_route.get("health_subtopic")
    route_subtopic = priority_route.get("subtopic") or (detected_subtopic["name"] if detected_subtopic else None)
    resolved_intent = priority_route.get("intent") or (keyword_match["intent"] if keyword_match.get("matched") else intent)
    detected_category = priority_route.get("category", "ai_fallback")
    matched_keywords = priority_route.get("matched_keywords") or keyword_match.get("matched_keywords", [])
    extracted_entities = priority_route.get("entities") or {}
    previous_context = get_active_conversation_context(session_store)
    conversation_state = get_conversation_state(session_store)
    resumable_context = get_last_non_casual_context(session_store)
    paused_context = get_paused_topic(session_store)
    previous_intent = previous_context.get("intent") if previous_context else None
    follow_up_detected = detect_follow_up_query(user_message)
    medication_follow_up = detect_medication_follow_up(user_message)
    emotional_continuation = detect_emotional_continuation(user_message)
    casual_interruption = detect_casual_interruption(user_message)
    explicit_topic_switch = detect_topic_switch(user_message)
    message_topic = classify_message_topic(user_message)
    resume_requested = detect_resume_topic_request(user_message)
    context_applied = False
    context_reason = ""
    topic_switch_detected, topic_switch_reason = should_reset_context(
        message_topic,
        previous_context=previous_context,
        current_category=detected_category,
        follow_up_detected=follow_up_detected,
        resume_requested=resume_requested,
    )

    if detected_category == "physical_symptom" and medication_follow_up:
        resolved_intent = "solution_request"

    if casual_interruption:
        if resumable_context and resumable_context.get("category") in {"physical_symptom", "mental_emotional", "positive_emotion"}:
            push_paused_topic(session_store, resumable_context)
        if detected_category == "ai_fallback":
            detected_category = "casual_conversation"
            resolved_intent = "casual_checkin"
            topic = "general"
            route_subtopic = "casual_checkin"
        entity_reasoning = summarize_entity_reasoning(extracted_entities)
        return {
            "keyword_match": keyword_match,
            "sentiment": sentiment,
            "sentiment_confidence": sentiment_confidence,
            "intent": intent,
            "intent_confidence": intent_confidence,
            "topic": topic,
            "priority_route": priority_route,
            "detected_subtopic": detected_subtopic,
            "resolved_intent": resolved_intent,
            "detected_category": detected_category,
            "route_subtopic": route_subtopic,
            "matched_keywords": matched_keywords,
            "extracted_entities": extracted_entities,
            "entity_reasoning": entity_reasoning,
            "previous_context": previous_context,
            "previous_intent": previous_intent,
            "conversation_state": conversation_state,
            "follow_up_detected": False,
            "medication_follow_up": False,
            "emotional_continuation": False,
            "casual_interruption": True,
            "message_topic": message_topic,
            "topic_switch_detected": True,
            "resume_requested": False,
            "context_applied": False,
            "context_reason": "casual_interruption",
            "topic_switch_reason": "casual_interruption",
        }

    if resume_requested and paused_context:
        previous_context = paused_context
        previous_intent = paused_context.get("intent")
        follow_up_detected = True
        context_applied = True
        context_reason = "resume_paused_topic"
        if paused_context.get("category") == "physical_symptom":
            resolved_intent = "symptom_report"
            detected_category = "physical_symptom"
        elif paused_context.get("category") == "mental_emotional":
            resolved_intent = "emotional_support"
            detected_category = "mental_emotional"
        elif paused_context.get("category") == "positive_emotion":
            resolved_intent = "general_query"
            detected_category = "positive_emotion"
        topic = paused_context.get("topic", topic)
        route_subtopic = paused_context.get("subtopic") or route_subtopic
        extracted_entities = _merge_entity_maps(paused_context.get("entities", {}), extracted_entities)

    if topic_switch_detected and not resume_requested:
        if resumable_context and resumable_context.get("category") in {"physical_symptom", "mental_emotional", "positive_emotion"}:
            push_paused_topic(session_store, resumable_context)
        previous_context = {}
        previous_intent = None
        if detected_category == "ai_fallback" and message_topic in {"casual_greeting", "gratitude", "goodbye", "joke_fun"}:
            detected_category = "casual_conversation"
            resolved_intent = "casual_checkin" if message_topic != "gratitude" else "gratitude"
            topic = "general"
            route_subtopic = "joke" if message_topic == "joke_fun" else "casual_checkin"

    if previous_context:
        previous_category = previous_context.get("category", "ai_fallback")
        previous_topic = previous_context.get("topic", "general")
        previous_subtopic = previous_context.get("subtopic")
        if previous_category == "crisis" and (follow_up_detected or len(user_message.split()) <= 12):
            resolved_intent = "emergency"
            detected_category = "crisis"
            topic = previous_topic if previous_topic and previous_topic != "general" else topic
            route_subtopic = previous_subtopic or route_subtopic or "crisis"
            context_applied = True
            context_reason = "crisis_context"
        elif follow_up_detected and previous_category in {"physical_symptom", "mental_emotional", "casual_conversation", "positive_emotion"}:
            detected_category = previous_category
            topic = previous_topic if previous_topic and previous_topic != "general" else topic
            route_subtopic = previous_subtopic or route_subtopic
            if previous_category == "physical_symptom":
                resolved_intent = "solution_request" if medication_follow_up else "symptom_report"
            elif previous_category == "mental_emotional":
                resolved_intent = "emotional_support"
            elif previous_category == "casual_conversation":
                resolved_intent = "casual_checkin"
                topic = "general"
            elif previous_category == "positive_emotion":
                resolved_intent = "general_query"
                topic = "general"
            extracted_entities = _merge_entity_maps(previous_context.get("entities", {}), extracted_entities)
            matched_keywords = matched_keywords or ([previous_subtopic] if previous_subtopic else [])
            context_applied = True
            context_reason = "follow_up_context"
        elif previous_category == "mental_emotional" and emotional_continuation and detected_category == "ai_fallback":
            resolved_intent = "emotional_support"
            detected_category = "mental_emotional"
            topic = previous_topic if previous_topic and previous_topic != "general" else topic
            route_subtopic = previous_subtopic or route_subtopic or "general"
            extracted_entities = _merge_entity_maps(previous_context.get("entities", {}), extracted_entities)
            context_applied = True
            context_reason = "emotional_continuation"
        elif previous_category in {"physical_symptom", "mental_emotional"} and detected_category == "ai_fallback" and not topic_switch_detected:
            resolved_intent = previous_context.get("intent", resolved_intent)
            detected_category = previous_category
            topic = previous_topic if previous_topic and previous_topic != "general" else topic
            route_subtopic = previous_subtopic or route_subtopic
            extracted_entities = _merge_entity_maps(previous_context.get("entities", {}), extracted_entities)
            matched_keywords = matched_keywords or ([previous_subtopic] if previous_subtopic else [])
            context_applied = True
            context_reason = "active_topic_context"

    entity_reasoning = summarize_entity_reasoning(extracted_entities)
    return {
        "keyword_match": keyword_match,
        "sentiment": sentiment,
        "sentiment_confidence": sentiment_confidence,
        "intent": intent,
        "intent_confidence": intent_confidence,
        "topic": topic,
        "priority_route": priority_route,
        "detected_subtopic": detected_subtopic,
        "resolved_intent": resolved_intent,
        "detected_category": detected_category,
        "route_subtopic": route_subtopic,
        "matched_keywords": matched_keywords,
        "extracted_entities": extracted_entities,
        "entity_reasoning": entity_reasoning,
        "previous_context": previous_context,
        "previous_intent": previous_intent,
        "conversation_state": conversation_state,
        "follow_up_detected": follow_up_detected,
        "medication_follow_up": medication_follow_up,
        "emotional_continuation": emotional_continuation,
        "casual_interruption": casual_interruption,
        "message_topic": message_topic,
        "topic_switch_detected": topic_switch_detected or explicit_topic_switch,
        "resume_requested": resume_requested,
        "context_applied": context_applied,
        "context_reason": context_reason,
        "topic_switch_reason": topic_switch_reason,
    }


def build_response_with_optional_llm(intent, sentiment, topic, lang, text="", keyword_match=None):
    keyword_match = keyword_match or {"matched": False, "intent": intent}
    resolved_intent = intent
    rule_response = build_response(resolved_intent, sentiment, topic, lang, text)
    ai_reason = ai_fallback_reason(resolved_intent, keyword_match, lang, text, session, topic=topic)
    logging.info(
        "ai_routing_check intent=%s topic=%s keyword_match=%s ai_reason=%s llm_enabled=%s",
        resolved_intent,
        topic,
        keyword_match.get("matched", False),
        ai_reason or "none",
        openrouter_enabled(),
    )

    if resolved_intent == "emergency":
        return rule_response

    if ai_reason:
        logging.info(
            "ai_routing_triggered reason=%s intent=%s topic=%s",
            ai_reason,
            resolved_intent,
            topic,
        )
        llm_response = generate_hybrid_response(
            text,
            {
                "language": lang,
                "intent": resolved_intent,
                "sentiment": sentiment,
                "topic": topic,
                "message_topic": classify_message_topic(text),
            },
            session,
            rule_response=rule_response,
        )
        if llm_response:
            return llm_response

    if not ai_reason and should_use_ai_fallback(resolved_intent, keyword_match, lang, text, session):
        llm_response = generate_hybrid_response(
            text,
            {
                "language": lang,
                "intent": resolved_intent,
                "sentiment": sentiment,
                "topic": topic,
                "message_topic": classify_message_topic(text),
            },
            session,
            rule_response=rule_response,
        )
        if llm_response:
            return llm_response
    elif not ai_reason:
        logging.info(
            "ai_routing_skipped intent=%s topic=%s reason=no_ai_fallback_condition",
            resolved_intent,
            topic,
        )

    return rule_response

# ══════════════════════════════════════════════════════════════
#  PAGE ROUTES (serve HTML via Flask templates)
# ══════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template(
        "home.html",
        user=current_user_data(),
        themes=THEMES,
        active_page="home",
        theme_defaults=default_theme_preferences(),
    )


@app.route("/about")
def about_page():
    return render_template(
        "about.html",
        user=current_user_data(),
        themes=THEMES,
        active_page="about",
        theme_defaults=default_theme_preferences(),
    )


@app.route("/chat", methods=["GET"])
def chat_page():
    active_chat_id = get_chat_session_id()
    return render_template(
        "chat.html",
        user=current_user_data(),
        themes=THEMES,
        active_page="chat",
        chat_session_id=active_chat_id,
        theme_defaults=default_theme_preferences(),
    )


@app.route("/chat-page")
def legacy_chat_page():
    return redirect(url_for("chat_page"))


@app.route("/login", methods=["GET"])
def login_page():
    if is_authenticated_user():
        return redirect(url_for("chat_page"))
    return render_template(
        "login.html",
        user=current_user_data(),
        themes=THEMES,
        active_page="login",
        theme_defaults=default_theme_preferences(),
    )


@app.route("/register", methods=["GET"])
def register_page():
    if is_authenticated_user():
        return redirect(url_for("chat_page"))
    return render_template(
        "register.html",
        user=current_user_data(),
        themes=THEMES,
        active_page="register",
        theme_defaults=default_theme_preferences(),
    )


@app.route("/profile", methods=["GET"])
def profile_page():
    return render_template(
        "profile.html",
        user=current_user_data(),
        themes=THEMES,
        active_page="profile",
        theme_defaults=default_theme_preferences(),
    )


@app.route("/profile", methods=["PATCH"])
@login_required
def profile_update():
    csrf_error = require_csrf()
    if csrf_error:
        return csrf_error
    data_in = request.get_json(silent=True) or {}
    username = _safe_username(data_in.get("username", login_current_user.username)) or login_current_user.username
    email = _safe_email(data_in.get("email", login_current_user.email)) or login_current_user.email
    prefs = theme_payload_from_request(data_in)
    existing_email = get_user_by_email(email)
    if existing_email and existing_email.id != login_current_user.id:
        return jsonify({"error": "That email is already in use."}), 409
    existing_username = get_user_by_username(username)
    if existing_username and existing_username.id != login_current_user.id:
        return jsonify({"error": "That username is already in use."}), 409
    user = update_user_profile(
        login_current_user.id,
        username=username,
        email=email,
        **prefs,
    )
    return jsonify({"user": serialize_user(user)})


@app.route("/api/session", methods=["GET"])
def api_session():
    return jsonify({
        "user": current_user_data(),
        "viewer": active_identity(),
        "themes": THEMES,
        "theme_defaults": default_theme_preferences(),
        "active_chat_id": session.get("chat_session_id"),
        "csrf_token": get_or_create_csrf_token(session),
    })


@app.route("/register", methods=["POST"])
@app.route("/api/register", methods=["POST"])
def api_register():
    csrf_error = require_csrf()
    if csrf_error:
        return csrf_error
    if not consume_auth_attempt(session):
        return jsonify({"error": "Too many attempts. Please wait a few minutes."}), 429
    data_in = request.get_json(silent=True) or {}
    username = _safe_username(data_in.get("username", data_in.get("name", "")))
    email = _safe_email(data_in.get("email", ""))
    password = data_in.get("password", "")
    if len(username) < 2:
        return jsonify({"error": "Please enter a username."}), 400
    if not email:
        return jsonify({"error": "Please enter a valid email."}), 400
    if len(password) < 6:
        return jsonify({"error": "Use at least 6 characters for your password."}), 400
    if get_user_by_email(email):
        return jsonify({"error": "An account with this email already exists."}), 409
    if get_user_by_username(username):
        return jsonify({"error": "That username is already taken."}), 409
    user_id = uuid.uuid4().hex
    user = create_user(
        user_id=user_id,
        username=username,
        email=email,
        password_hash=_hash_password(password),
        **default_theme_preferences(),
    )
    app.logger.info("auth_register_success user_id=%s email=%s", user.id, user.email)
    clear_guest_session_state()
    login_user(user, remember=bool(data_in.get("remember_me")))
    touch_user_login(user.id)
    reset_auth_attempts(session)
    return jsonify({"user": serialize_user(user)})


@app.route("/login", methods=["POST"])
@app.route("/api/login", methods=["POST"])
def api_login():
    csrf_error = require_csrf()
    if csrf_error:
        return csrf_error
    if not consume_auth_attempt(session):
        return jsonify({"error": "Too many attempts. Please wait a few minutes."}), 429
    data_in = request.get_json(silent=True) or {}
    email = _safe_email(data_in.get("email", ""))
    password = data_in.get("password", "")
    if not email or not password:
        return jsonify({"error": "Please enter both email and password."}), 400
    user = get_user_by_email(email)
    if not user or user.is_guest or not user.password_hash or not check_password_hash(user.password_hash, password):
        app.logger.warning("auth_login_failed email=%s", email or "missing")
        return jsonify({"error": "Invalid email or password."}), 401
    clear_guest_session_state()
    login_user(user, remember=bool(data_in.get("remember_me")))
    touch_user_login(user.id)
    reset_auth_attempts(session)
    session.permanent = True
    app.logger.info("auth_login_success user_id=%s", user.id)
    return jsonify({"user": serialize_user(user)})


@app.route("/logout", methods=["POST"])
@app.route("/api/logout", methods=["POST"])
def api_logout():
    csrf_error = require_csrf()
    if csrf_error:
        return csrf_error
    if is_authenticated_user():
        app.logger.info("auth_logout user_id=%s", login_current_user.id)
        logout_user()
    session.pop("user_id", None)
    clear_guest_session_state()
    get_actor_id()
    return jsonify({"ok": True, "guest": active_identity()})


@app.route("/guest", methods=["POST"])
def continue_as_guest():
    csrf_error = require_csrf()
    if csrf_error:
        return csrf_error
    if is_authenticated_user():
        app.logger.info("auth_guest_switch_from_user user_id=%s", login_current_user.id)
        logout_user()
    session.pop("user_id", None)
    clear_guest_session_state()
    return jsonify({"guest": active_identity()})


@app.route("/api/theme", methods=["POST"])
def api_theme():
    csrf_error = require_csrf()
    if csrf_error:
        return csrf_error
    theme_data = request.get_json(silent=True) or {}
    prefs = theme_payload_from_request(theme_data)
    if not is_authenticated_user():
        return jsonify({"ok": True, "local_only": True, "guest": active_identity()})
    user = update_user_profile(login_current_user.id, **prefs)
    return jsonify({"user": serialize_user(user)})


@app.route("/api/history", methods=["GET"])
def api_history():
    chat_id = get_chat_session_id()
    history = build_chat_history_rows(chat_id)
    return jsonify({"chat_id": chat_id, "history": history})


@app.route("/history", methods=["GET"])
def session_history():
    session_id = get_chat_session_id()
    history = build_chat_history_rows(session_id)
    if not history and LEGACY_CHAT_DB_ENABLED:
        history = fetch_session_history(session_id) or fetch_chat_history(CHAT_DB_PATH, session_id)
    return jsonify({"session_id": session_id, "chat_id": session_id, "history": history})


@app.route("/api/history", methods=["DELETE"])
def api_clear_history():
    csrf_error = require_csrf()
    if csrf_error:
        return csrf_error
    actor_id = get_actor_id()
    for chat_session in list_chat_sessions(actor_id, limit=500):
        delete_chat_session(chat_session.id, actor_id)
    clear_chat_session_state()
    fresh_chat = create_chat_session(actor_id, chat_id=uuid.uuid4().hex)
    session["chat_session_id"] = fresh_chat.id
    session["chat_history"] = []
    session["response_cache"] = []
    session.modified = True
    return jsonify({"history": [], "active_chat_id": fresh_chat.id})


@app.route("/chats", methods=["GET"])
def api_chats():
    actor_id = get_actor_id()
    active_chat_id = get_chat_session_id()
    chats = [serialize_chat_session(chat) for chat in list_chat_sessions(actor_id)]
    return jsonify({"chats": chats, "active_chat_id": active_chat_id, "viewer": active_identity()})


@app.route("/chat/new", methods=["POST"])
def api_chat_new():
    csrf_error = require_csrf()
    if csrf_error:
        return csrf_error
    actor_id = get_actor_id()
    chat_session = create_chat_session(actor_id, chat_id=uuid.uuid4().hex)
    session["chat_session_id"] = chat_session.id
    session.modified = True
    return jsonify({"chat": serialize_chat_session(chat_session), "active_chat_id": chat_session.id}), 201


@app.route("/chat/<chat_id>", methods=["GET"])
def api_chat_detail(chat_id):
    actor_id = get_actor_id()
    chat_session = get_chat_session(chat_id, user_id=actor_id)
    if not chat_session:
        return jsonify({"error": "Chat not found."}), 404
    session["chat_session_id"] = chat_session.id
    session.modified = True
    return jsonify({
        "chat": serialize_chat_session(chat_session),
        "messages": fetch_chat_messages(chat_id, user_id=actor_id),
        "history": build_chat_history_rows(chat_id),
    })


@app.route("/chat/<chat_id>", methods=["DELETE"])
def api_chat_delete(chat_id):
    csrf_error = require_csrf()
    if csrf_error:
        return csrf_error
    actor_id = get_actor_id()
    deleted = delete_chat_session(chat_id, actor_id)
    if not deleted:
        return jsonify({"error": "Chat not found."}), 404
    remaining = list_chat_sessions(actor_id, limit=1)
    if remaining:
        session["chat_session_id"] = remaining[0].id
    else:
        new_chat = create_chat_session(actor_id, chat_id=uuid.uuid4().hex)
        session["chat_session_id"] = new_chat.id
        remaining = [new_chat]
    session.modified = True
    return jsonify({
        "ok": True,
        "active_chat_id": remaining[0].id,
        "chat": serialize_chat_session(remaining[0]),
    })


@app.route("/chat/<chat_id>/rename", methods=["PATCH"])
def api_chat_rename(chat_id):
    csrf_error = require_csrf()
    if csrf_error:
        return csrf_error
    actor_id = get_actor_id()
    title = _safe_text((request.get_json(silent=True) or {}).get("title", ""), default="", limit=160)
    if len(title) < 1:
        return jsonify({"error": "Please enter a title."}), 400
    chat_session = rename_chat_session(chat_id, actor_id, title)
    if not chat_session:
        return jsonify({"error": "Chat not found."}), 404
    return jsonify({"chat": serialize_chat_session(chat_session)})


@app.route("/api/llm-status", methods=["GET"])
def api_llm_status():
    return jsonify(openrouter_status())

# ══════════════════════════════════════════════════════════════
#  API ENDPOINTS
# ══════════════════════════════════════════════════════════════

@app.route("/chat", methods=["POST"])
@app.route("/api/chat", methods=["POST"])
def chat():
    csrf_error = require_csrf()
    if csrf_error:
        return csrf_error
    data = request.get_json(silent=True) or {}
    user_message = _safe_text(data.get("message", ""), default="")
    forced_lang = _safe_text(data.get("language", None), default=None, limit=10) if data.get("language", None) is not None else None
    client_message_id = _safe_text(data.get("client_message_id", ""), default="", limit=128)
    requested_chat_id = _safe_text(data.get("chat_id", ""), default="", limit=64)
    user = current_user_data()

    if not user_message:
        return jsonify({"response": "I didn't catch that. Can you tell me what's on your mind?"})

    if client_message_id:
        history = session.get("response_cache", [])
        existing_entry = find_history_entry_by_client_message_id(history, client_message_id)
        if existing_entry:
            app.logger.info(
                "chat_request_duplicate_returned actor_id=%s client_message_id=%s",
                get_actor_id(),
                client_message_id,
            )
            return jsonify({
                "response": existing_entry.get("bot", ""),
                "language": forced_lang if forced_lang in ("en", "hi") else detect_language(existing_entry.get("user", user_message)),
                "meta": existing_entry.get("meta", {}),
                "message_id": existing_entry.get("assistant_message_id"),
                "user_message_id": existing_entry.get("user_message_id"),
                "client_message_id": existing_entry.get("client_message_id"),
                "duplicate": True,
            })

    if has_recent_client_message_id(client_message_id):
        return jsonify({
            "response": "I am still working with your latest message.",
            "duplicate": True,
        }), 202

    remember_client_message_id(client_message_id)
    try:
        app.logger.info(
            "chat_request_received actor_id=%s client_message_id=%s message_length=%s",
            user["id"] if user else get_actor_id(),
            client_message_id or "none",
            len(user_message),
        )

        lang = forced_lang if forced_lang in ("en", "hi") else detect_language(user_message)
        analysis = resolve_turn_analysis(user_message, lang, session)
        keyword_match = analysis["keyword_match"]
        sentiment = analysis["sentiment"]
        sentiment_confidence = analysis["sentiment_confidence"]
        intent = analysis["intent"]
        intent_confidence = analysis["intent_confidence"]
        topic = analysis["topic"]
        priority_route = analysis["priority_route"]
        detected_subtopic = analysis["detected_subtopic"]
        resolved_intent = analysis["resolved_intent"]
        detected_category = analysis["detected_category"]
        matched_keywords = analysis["matched_keywords"]
        extracted_entities = analysis["extracted_entities"]
        entity_reasoning = analysis["entity_reasoning"]
        route_subtopic = analysis["route_subtopic"]
        previous_context = analysis["previous_context"]
        repeat_intent_hits = repeated_intent_count(session, resolved_intent)
        repeat_topic_hits = repeated_topic_count(session, topic)
        ai_reason = ai_fallback_reason(resolved_intent, keyword_match, lang, user_message, session, topic=topic)

        fallback_used = should_use_fallback(
            user_message,
            lang,
            resolved_intent,
            intent_confidence,
            sentiment_confidence,
            topic,
        )
        if analysis["context_applied"]:
            fallback_used = False
        if ai_reason:
            fallback_used = False

        logging.info(
            "routing_decision category=%s intent=%s previous_intent=%s topic=%s subtopic=%s context_topic=%s follow_up_detected=%s casual_interruption=%s resume_requested=%s message_topic=%s topic_switch_detected=%s context_applied=%s context_reason=%s intent_confidence=%.4f sentiment_confidence=%.4f matched_keywords=%s entities=%s reasoning=%s override_reason=%s dataset_match=%s ai_reason=%s fallback=%s fallback_reason=%s",
            detected_category,
            resolved_intent,
            analysis["previous_intent"] or "none",
            topic,
            route_subtopic or (detected_subtopic["name"] if detected_subtopic else "none"),
            previous_context.get("topic", "none") if previous_context else "none",
            analysis["follow_up_detected"],
            analysis["casual_interruption"],
            analysis["resume_requested"],
            analysis["message_topic"],
            analysis["topic_switch_detected"],
            analysis["context_applied"],
            analysis["context_reason"] or "none",
            intent_confidence,
            sentiment_confidence,
            matched_keywords[:6],
            extracted_entities,
            entity_reasoning,
            priority_route.get("override_reason") or "none",
            priority_route.get("dataset_match") or "none",
            ai_reason or "none",
            fallback_used,
            priority_route.get("fallback_reason") or "none",
        )

        if fallback_used:
            if lang == "hi":
                response = friendly_fallback_message("hinglish" if prefers_hinglish(user_message) else "hi", user_text=user_message)
            else:
                response = friendly_fallback_message(lang, user_text=user_message)
        else:
            response = build_response_with_optional_llm(
                resolved_intent,
                sentiment,
                topic,
                lang,
                user_message,
                keyword_match=keyword_match,
            )

        actor_id = get_actor_id()
        chat_session_id = requested_chat_id or get_chat_session_id()
        existing_chat = get_chat_session(chat_session_id, user_id=actor_id)
        if not existing_chat:
            existing_chat = create_chat_session(actor_id, chat_id=chat_session_id)
        session["chat_session_id"] = existing_chat.id
        session.modified = True

        meta = {
            "sentiment": sentiment,
            "intent": resolved_intent,
            "topic": topic,
            "category": detected_category,
            "subtopic": route_subtopic or (detected_subtopic["name"] if detected_subtopic else None),
            "entities": extracted_entities,
            "entity_reasoning": entity_reasoning,
            "intent_confidence": round(intent_confidence, 4),
            "sentiment_confidence": round(sentiment_confidence, 4),
            "fallback_used": fallback_used,
            "fallback_reason": priority_route.get("fallback_reason") or ("legacy_fallback_rules" if fallback_used else None),
            "response_source": "context_continuation" if analysis["context_applied"] else ("friendly_fallback" if fallback_used else "standard_pipeline"),
            "ml_used": lang == "en",
            "keyword_match": keyword_match.get("matched", False),
            "matched_keywords": matched_keywords[:6],
            "priority_override_reason": priority_route.get("override_reason") or None,
            "dataset_match": priority_route.get("dataset_match") or None,
            "llm_enabled": openrouter_enabled(),
            "llm_loaded": openrouter_status().get("configured", False),
            "llm_provider": "openrouter",
            "ai_usage": bool(ai_reason),
            "ai_reason": ai_reason or None,
            "follow_up_detected": analysis["follow_up_detected"],
            "casual_interruption": analysis["casual_interruption"],
            "message_topic": analysis["message_topic"],
            "topic_switch_detected": analysis["topic_switch_detected"],
            "topic_switch_reason": analysis["topic_switch_reason"] or None,
            "resume_requested": analysis["resume_requested"],
            "context_applied": analysis["context_applied"],
            "context_reason": analysis["context_reason"] or None,
            "previous_intent": analysis["previous_intent"],
            "context_topic": previous_context.get("topic") if previous_context else None,
            "repeat_intent_hits": repeat_intent_hits,
            "repeat_topic_hits": repeat_topic_hits,
        }
        stored_entry = append_chat_history(
            user_message,
            response,
            meta,
            client_message_id=client_message_id or None,
        )
        if LEGACY_CHAT_DB_ENABLED:
            legacy_history = fetch_chat_history(CHAT_DB_PATH, chat_session_id, limit=1)
            latest_legacy = legacy_history[-1] if legacy_history else None
            if not latest_legacy or latest_legacy.get("user_message") != user_message or latest_legacy.get("bot_response") != response:
                save_chat_message(
                    CHAT_DB_PATH,
                    chat_session_id,
                    user_message,
                    response,
                    _now_iso(),
                )
        save_chat_record(
            chat_session_id,
            user_message,
            response,
            resolved_intent,
            sentiment,
        )
        save_chat_exchange(
            chat_session_id,
            user_message,
            response,
            resolved_intent,
            sentiment,
            metadata=meta,
        )
        if existing_chat.title == "New chat":
            rename_chat_session(chat_session_id, actor_id, generate_chat_title(user_message))
        update_session_chat_history(session, user_message, response, meta)

        app.logger.info(
            "chat_request_completed actor_id=%s client_message_id=%s stored=%s",
            user["id"] if user else get_actor_id(),
            client_message_id or "none",
            bool(stored_entry),
        )

        return jsonify({
            "response": response,
            "language": lang,
            "meta": meta,
            "session_id": chat_session_id,
            "chat_id": chat_session_id,
            "message_id": stored_entry.get("assistant_message_id") if stored_entry else uuid.uuid4().hex,
            "user_message_id": stored_entry.get("user_message_id") if stored_entry else (client_message_id or uuid.uuid4().hex),
            "client_message_id": client_message_id or None,
            "duplicate": False,
        })
    except Exception:
        app.logger.exception("chat_request_failed response_generation_error=true")
        return jsonify({
            "response": "I'm here with you. Tell me a little more about what's going on.",
            "duplicate": False,
        }), 500
    finally:
        forget_client_message_id(client_message_id)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/debug/openrouter-test", methods=["GET"])
def debug_openrouter_test():
    key = request.headers.get("X-Admin-Key", "")
    if not app.config.get("DEBUG") and key != ADMIN_KEY:
        return jsonify({"error": "unauthorized"}), 403
    prompt = "Reply with: OpenRouter connection successful."
    app.logger.info("debug_openrouter_test_started")
    raw_response = direct_openrouter_test(prompt)
    status = openrouter_status()
    return jsonify({
        "prompt": prompt,
        "raw_response": raw_response,
        "llm_status": status,
        "success": bool(raw_response),
    })


@app.route("/retrain", methods=["POST"])
def retrain_models():
    """Utility endpoint: force re-training both ML models.
    Useful after adding new rows to the CSV datasets.
    Call with:  POST /retrain  (header: X-Admin-Key)
    """
    key = request.headers.get("X-Admin-Key", "")
    if key != ADMIN_KEY:
        return jsonify({"error": "unauthorized"}), 403
    from ml.intent_model    import retrain as retrain_intent
    from ml.sentiment_model import retrain as retrain_sentiment
    retrain_intent()
    retrain_sentiment()
    return jsonify({"status": "retrained", "message": "Both ML models retrained successfully."})


@app.errorhandler(400)
def handle_bad_request(error):
    if _wants_json_response():
        return jsonify({"error": "bad_request"}), 400
    return render_template("400.html", active_page=""), 400


@app.errorhandler(404)
def handle_not_found(error):
    if _wants_json_response():
        return jsonify({"error": "not_found"}), 404
    return render_template("404.html", active_page=""), 404


@app.errorhandler(500)
def handle_server_error(error):
    app.logger.exception("unhandled_server_error")
    if _wants_json_response():
        return jsonify({"error": "server_error"}), 500
    return render_template("500.html", active_page=""), 500


@app.errorhandler(Exception)
def handle_uncaught_error(error):
    if isinstance(error, HTTPException):
        return error
    app.logger.exception("uncaught_exception")
    if _wants_json_response():
        return jsonify({"error": "server_error"}), 500
    return render_template("500.html", active_page=""), 500


def create_app():
    return app


application = app


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=app.config.get("DEBUG", False), port=PORT)
