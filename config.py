import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"


DEFAULT_SQLITE_PATH = Path("therapinhand.sqlite3")

BASE_LOG_DIR = BASE_DIR / "logs"

os.makedirs(BASE_LOG_DIR, exist_ok=True)

_ENV_LOADED = False


def load_environment() -> bool:
    global _ENV_LOADED
    if _ENV_LOADED:
        return bool(ENV_FILE.exists())
    load_dotenv(ENV_FILE, override=False)
    _ENV_LOADED = True
    return bool(ENV_FILE.exists())


load_environment()


def env_str(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value is None:
        return default
    value = str(value).strip()
    return value if value else default


def env_int(name: str, default: int) -> int:
    try:
        return int(env_str(name, str(default)))
    except (TypeError, ValueError):
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(env_str(name, str(default)))
    except (TypeError, ValueError):
        return default


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def env_list(name: str, default=None) -> list[str]:
    if default is None:
        default = []
    value = os.environ.get(name)
    if value is None:
        return list(default)
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _normalize_filesystem_path(value: str | Path) -> Path:
    raw = str(value or "").strip().replace("\\", "/")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = BASE_DIR / path
    return path.resolve()


def _sqlite_database_uri(path_value: str | Path) -> str:
    raw_path = Path(str(path_value or "").strip().replace("\\", "/"))
    resolved_path = _normalize_filesystem_path(raw_path)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    if raw_path.is_absolute():
        return f"sqlite:///{resolved_path.as_posix()}"
    relative_posix = raw_path.as_posix().lstrip("./")
    return f"sqlite:///{relative_posix or DEFAULT_SQLITE_PATH.as_posix()}"


def _normalized_database_url(value: str) -> str:
    url = (value or "").strip()
    if not url:
        return _sqlite_database_uri(DEFAULT_SQLITE_PATH)
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("sqlite:///"):
        sqlite_target = url[len("sqlite:///"):]
        if sqlite_target == ":memory:":
            return "sqlite:///:memory:"
        return _sqlite_database_uri(sqlite_target)
    if url.startswith("sqlite://"):
        sqlite_target = url[len("sqlite://"):]
        if sqlite_target == "/:memory:":
            return "sqlite:///:memory:"
        return _sqlite_database_uri(sqlite_target.lstrip("/"))
    return url


def _default_secure_cookies() -> bool:
    return env_str("FLASK_ENV", "development").strip().lower() == "production"


def _engine_options(database_uri: str) -> dict:
    options = {"pool_pre_ping": True}
    if database_uri.startswith("sqlite:///") or database_uri == "sqlite:///:memory:":
        options["connect_args"] = {
            "check_same_thread": False,
            "timeout": env_int("SQLITE_TIMEOUT_SECONDS", 30),
        }
    else:
        options.update({
            "pool_recycle": env_int("DB_POOL_RECYCLE_SECONDS", 1800),
            "pool_size": env_int("DB_POOL_SIZE", 5),
            "max_overflow": env_int("DB_MAX_OVERFLOW", 10),
            "pool_timeout": env_int("DB_POOL_TIMEOUT_SECONDS", 30),
        })
    return options


def _masked_database_url(database_uri: str) -> str:
    if not database_uri:
        return ""
    try:
        parsed = urlsplit(database_uri)
        if parsed.password:
            netloc = parsed.netloc.replace(f":{parsed.password}@", ":***@")
            return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
    except Exception:
        return database_uri
    return database_uri


def ensure_runtime_directories() -> None:
    BASE_LOG_DIR.mkdir(parents=True, exist_ok=True)
    _normalize_filesystem_path(DEFAULT_SQLITE_PATH).parent.mkdir(parents=True, exist_ok=True)


ensure_runtime_directories()


class BaseConfig:
    APP_NAME = "TherapInHand"
    APP_ENV = env_str("FLASK_ENV", "development").strip().lower()
    DEBUG = env_bool("DEBUG", default=False)
    TESTING = env_bool("TESTING", default=False)

    SECRET_KEY = env_str("FLASK_SECRET_KEY", "therapinhand-dev-secret-change-me")
    SQLALCHEMY_DATABASE_URI = _normalized_database_url(env_str("DATABASE_URL", ""))
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = _engine_options(SQLALCHEMY_DATABASE_URI)

    SESSION_COOKIE_NAME = env_str("SESSION_COOKIE_NAME", "therapinhand_session")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = env_str("SESSION_COOKIE_SAMESITE", "Lax")
    SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", default=_default_secure_cookies())
    SESSION_REFRESH_EACH_REQUEST = env_bool("SESSION_REFRESH_EACH_REQUEST", default=True)
    PERMANENT_SESSION_LIFETIME = env_int("SESSION_LIFETIME_SECONDS", 604800)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = env_str("REMEMBER_COOKIE_SAMESITE", "Lax")
    REMEMBER_COOKIE_SECURE = env_bool("REMEMBER_COOKIE_SECURE", default=_default_secure_cookies())
    REMEMBER_COOKIE_DURATION = env_int("REMEMBER_COOKIE_DURATION_SECONDS", 2592000)

    PREFERRED_URL_SCHEME = env_str("PREFERRED_URL_SCHEME", "https" if _default_secure_cookies() else "http")
    MAX_CONTENT_LENGTH = env_int("MAX_CONTENT_LENGTH", 1048576)

    SERVER_NAME = env_str("SERVER_NAME", "") or None
    TRUSTED_HOSTS = env_list("TRUSTED_HOSTS", [])
    ENABLE_PROXY_FIX = env_bool("ENABLE_PROXY_FIX", default=True)
    PROXY_FIX_X_FOR = env_int("PROXY_FIX_X_FOR", 1)
    PROXY_FIX_X_PROTO = env_int("PROXY_FIX_X_PROTO", 1)
    PROXY_FIX_X_HOST = env_int("PROXY_FIX_X_HOST", 1)
    PROXY_FIX_X_PORT = env_int("PROXY_FIX_X_PORT", 1)
    PROXY_FIX_X_PREFIX = env_int("PROXY_FIX_X_PREFIX", 1)

    ENABLE_CORS = env_bool("ENABLE_CORS", default=True)
    CORS_ORIGINS = env_list("CORS_ORIGINS", ["http://localhost:5000", "http://127.0.0.1:5000"])

    LOG_LEVEL = env_str("LOG_LEVEL", "INFO").upper()
    LOG_DIR = str(BASE_LOG_DIR)
    LOG_FILE = env_str("LOG_FILE", str(BASE_LOG_DIR / "therapinhand.log"))
    LOG_MAX_BYTES = env_int("LOG_MAX_BYTES", 1048576)
    LOG_BACKUP_COUNT = env_int("LOG_BACKUP_COUNT", 5)

    ADMIN_KEY = env_str("ADMIN_KEY", "therapinhand-retrain")
    PORT = env_int("PORT", 5000)
    LEGACY_CHAT_DB_ENABLED = env_bool("LEGACY_CHAT_DB_ENABLED", default=False)

    OPENROUTER_API_KEY = env_str("OPENROUTER_API_KEY", "")
    USE_OPENROUTER_CHAT = env_bool("USE_OPENROUTER_CHAT", default=bool(OPENROUTER_API_KEY))
    OPENROUTER_MODEL = env_str("OPENROUTER_MODEL", "openrouter/auto")
    OPENROUTER_MAX_TOKENS = env_int("OPENROUTER_MAX_TOKENS", 240)
    OPENROUTER_TEMPERATURE = env_float("OPENROUTER_TEMPERATURE", 0.55)
    OPENROUTER_SITE_URL = env_str("OPENROUTER_SITE_URL", "http://localhost:5000")
    OPENROUTER_APP_NAME = env_str("OPENROUTER_APP_NAME", "TherapInHand")
    OPENROUTER_TIMEOUT = env_int("OPENROUTER_TIMEOUT", 45)
    OPENROUTER_MAX_RETRIES = env_int("OPENROUTER_MAX_RETRIES", 2)
    OPENROUTER_RETRY_BACKOFF_SECONDS = env_float("OPENROUTER_RETRY_BACKOFF_SECONDS", 1.5)
    STARTUP_DIAGNOSTICS = env_bool("STARTUP_DIAGNOSTICS", default=True)


class DevelopmentConfig(BaseConfig):
    DEBUG = env_bool("DEBUG", default=True)
    SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", default=False)
    REMEMBER_COOKIE_SECURE = env_bool("REMEMBER_COOKIE_SECURE", default=False)
    PREFERRED_URL_SCHEME = env_str("PREFERRED_URL_SCHEME", "http")


class ProductionConfig(BaseConfig):
    DEBUG = False
    SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", default=True)
    REMEMBER_COOKIE_SECURE = env_bool("REMEMBER_COOKIE_SECURE", default=True)
    PREFERRED_URL_SCHEME = env_str("PREFERRED_URL_SCHEME", "https")


def get_config_class():
    env_name = env_str("FLASK_ENV", "development").strip().lower()
    if env_name == "production":
        return ProductionConfig
    return DevelopmentConfig


def openrouter_runtime_settings() -> dict:
    load_environment()
    api_key = env_str("OPENROUTER_API_KEY", "")
    return {
        "enabled": env_bool("USE_OPENROUTER_CHAT", default=bool(api_key)),
        "api_key": api_key,
        "model": env_str("OPENROUTER_MODEL", "openrouter/auto"),
        "max_tokens": env_int("OPENROUTER_MAX_TOKENS", 240),
        "temperature": env_float("OPENROUTER_TEMPERATURE", 0.55),
        "site_url": env_str("OPENROUTER_SITE_URL", "http://localhost:5000"),
        "app_name": env_str("OPENROUTER_APP_NAME", "TherapInHand"),
        "timeout": env_int("OPENROUTER_TIMEOUT", 45),
        "max_retries": env_int("OPENROUTER_MAX_RETRIES", 2),
        "retry_backoff_seconds": env_float("OPENROUTER_RETRY_BACKOFF_SECONDS", 1.5),
    }


def startup_diagnostics() -> dict:
    config_class = get_config_class()
    return {
        "environment": config_class.APP_ENV,
        "debug": bool(config_class.DEBUG),
        "port": int(config_class.PORT),
        "database_uri": _masked_database_url(config_class.SQLALCHEMY_DATABASE_URI),
        "database_scheme": config_class.SQLALCHEMY_DATABASE_URI.split("://", 1)[0],
        "openrouter_enabled": bool(config_class.USE_OPENROUTER_CHAT),
        "trusted_hosts": list(config_class.TRUSTED_HOSTS),
    }


CURRENT_CONFIG = get_config_class()
FLASK_SECRET_KEY = CURRENT_CONFIG.SECRET_KEY
DATABASE_URL = CURRENT_CONFIG.SQLALCHEMY_DATABASE_URI
ADMIN_KEY = CURRENT_CONFIG.ADMIN_KEY
OPENROUTER_API_KEY = CURRENT_CONFIG.OPENROUTER_API_KEY
USE_OPENROUTER_CHAT = CURRENT_CONFIG.USE_OPENROUTER_CHAT
OPENROUTER_MODEL = CURRENT_CONFIG.OPENROUTER_MODEL
OPENROUTER_MAX_TOKENS = CURRENT_CONFIG.OPENROUTER_MAX_TOKENS
OPENROUTER_TEMPERATURE = CURRENT_CONFIG.OPENROUTER_TEMPERATURE
OPENROUTER_SITE_URL = CURRENT_CONFIG.OPENROUTER_SITE_URL
OPENROUTER_APP_NAME = CURRENT_CONFIG.OPENROUTER_APP_NAME
OPENROUTER_TIMEOUT = CURRENT_CONFIG.OPENROUTER_TIMEOUT
PORT = CURRENT_CONFIG.PORT
