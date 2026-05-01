import secrets
from datetime import datetime, timedelta, timezone


CSRF_SESSION_KEY = "csrf_token"
AUTH_RATE_LIMIT_KEY = "auth_rate_limit"
AUTH_RATE_LIMIT_MAX = 8
AUTH_RATE_LIMIT_WINDOW_SECONDS = 300


def get_or_create_csrf_token(session_store):
    token = session_store.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(24)
        session_store[CSRF_SESSION_KEY] = token
        session_store.modified = True
    return token


def validate_csrf(session_store, request_obj):
    expected = get_or_create_csrf_token(session_store)
    provided = (
        request_obj.headers.get("X-CSRF-Token")
        or request_obj.form.get("csrf_token")
        or (request_obj.get_json(silent=True) or {}).get("csrf_token")
    )
    return bool(provided and secrets.compare_digest(str(provided), str(expected)))


def consume_auth_attempt(session_store):
    now = datetime.now(timezone.utc)
    raw_attempts = session_store.get(AUTH_RATE_LIMIT_KEY, [])
    recent_attempts = []
    for item in raw_attempts:
        try:
            attempt_at = datetime.fromisoformat(item)
        except (TypeError, ValueError):
            continue
        if now - attempt_at <= timedelta(seconds=AUTH_RATE_LIMIT_WINDOW_SECONDS):
            recent_attempts.append(item)
    recent_attempts.append(now.isoformat())
    session_store[AUTH_RATE_LIMIT_KEY] = recent_attempts
    session_store.modified = True
    return len(recent_attempts) <= AUTH_RATE_LIMIT_MAX


def reset_auth_attempts(session_store):
    session_store.pop(AUTH_RATE_LIMIT_KEY, None)
    session_store.modified = True
