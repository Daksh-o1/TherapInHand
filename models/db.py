from datetime import datetime, timezone
import json
import uuid

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from config import startup_diagnostics


db = SQLAlchemy()


def utcnow():
    return datetime.now(timezone.utc)


class Chat(db.Model):
    __tablename__ = "chats"
    __table_args__ = (
        db.Index("idx_chats_session_timestamp", "session_id", "timestamp"),
    )

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(128), nullable=False, index=True)
    user_message = db.Column(db.Text, nullable=False)
    bot_response = db.Column(db.Text, nullable=False)
    intent = db.Column(db.String(64), nullable=False, default="general_query")
    sentiment = db.Column(db.String(64), nullable=False, default="neutral")
    timestamp = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        index=True,
    )


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.String(64), primary_key=True)
    username = db.Column(db.String(120), nullable=False, unique=True, index=True)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    last_login = db.Column(db.DateTime(timezone=True), nullable=True)
    theme_name = db.Column(db.String(32), nullable=False, default="blue")
    theme_mode = db.Column(db.String(16), nullable=False, default="system")
    accent_color = db.Column(db.String(32), nullable=False, default="blue")
    gradient_theme = db.Column(db.String(32), nullable=False, default="ocean")
    is_guest = db.Column(db.Boolean, nullable=False, default=False)


class ChatSession(db.Model):
    __tablename__ = "chat_sessions"
    __table_args__ = (
        db.Index("idx_chat_sessions_user_updated", "user_id", "updated_at"),
    )

    id = db.Column(db.String(64), primary_key=True)
    user_id = db.Column(db.String(64), nullable=False, index=True)
    title = db.Column(db.String(160), nullable=False, default="New chat")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow, index=True)
    messages = db.relationship(
        "ChatMessage",
        back_populates="chat_session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.timestamp.asc(), ChatMessage.id.asc()",
    )


class ChatMessage(db.Model):
    __tablename__ = "chat_messages"
    __table_args__ = (
        db.Index("idx_chat_messages_chat_timestamp", "chat_id", "timestamp"),
        db.Index("idx_chat_messages_chat_sender", "chat_id", "sender"),
    )

    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.String(64), db.ForeignKey("chat_sessions.id"), nullable=False, index=True)
    sender = db.Column(db.String(16), nullable=False)
    message = db.Column(db.Text, nullable=False)
    intent = db.Column(db.String(64), nullable=True)
    sentiment = db.Column(db.String(64), nullable=True)
    metadata_json = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    chat_session = db.relationship("ChatSession", back_populates="messages")


def _table_columns(connection, table_name):
    inspector = inspect(connection)
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _ensure_column(connection, table_name, column_name, ddl):
    columns = _table_columns(connection, table_name)
    if column_name not in columns:
        connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {ddl}"))


def _ensure_index(connection, index_name, ddl):
    try:
        connection.execute(text(ddl))
    except Exception:
        return


def ensure_database_schema():
    engine = db.engine
    with engine.begin() as connection:
        if inspect(connection).has_table("users"):
            _ensure_column(connection, "users", "username", "username VARCHAR(120) NOT NULL DEFAULT 'friend'")
            _ensure_column(connection, "users", "password_hash", "password_hash VARCHAR(255) NOT NULL DEFAULT ''")
            _ensure_column(connection, "users", "created_at", "created_at DATETIME")
            _ensure_column(connection, "users", "last_login", "last_login DATETIME")
            _ensure_column(connection, "users", "theme_name", "theme_name VARCHAR(32) NOT NULL DEFAULT 'blue'")
            _ensure_column(connection, "users", "theme_mode", "theme_mode VARCHAR(16) NOT NULL DEFAULT 'system'")
            _ensure_column(connection, "users", "accent_color", "accent_color VARCHAR(32) NOT NULL DEFAULT 'blue'")
            _ensure_column(connection, "users", "gradient_theme", "gradient_theme VARCHAR(32) NOT NULL DEFAULT 'ocean'")
            _ensure_column(connection, "users", "is_guest", "is_guest BOOLEAN NOT NULL DEFAULT 0")
            _ensure_index(connection, "idx_users_email_unique", "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique ON users (email)")
            _ensure_index(connection, "idx_users_username_unique", "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username_unique ON users (username)")
        if inspect(connection).has_table("chat_messages"):
            _ensure_column(connection, "chat_messages", "metadata_json", "metadata_json TEXT")
            _ensure_index(
                connection,
                "idx_chat_messages_chat_sender",
                "CREATE INDEX IF NOT EXISTS idx_chat_messages_chat_sender ON chat_messages (chat_id, sender)",
            )
        if inspect(connection).has_table("chat_sessions"):
            _ensure_index(
                connection,
                "idx_chat_sessions_user_updated",
                "CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_updated ON chat_sessions (user_id, updated_at)",
            )


def init_database(app):
    database_uri = app.config.get("SQLALCHEMY_DATABASE_URI")
    if not database_uri:
        raise RuntimeError("SQLALCHEMY_DATABASE_URI is not configured")
    url = make_url(database_uri)
    database_scheme = url.drivername
    if url.drivername.startswith("sqlite") and url.database:
        from pathlib import Path
        db_path = Path(url.database)
        if not db_path.is_absolute():
            db_path = Path(app.root_path) / db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
    if "sqlalchemy" not in app.extensions:
        db.init_app(app)
    with app.app_context():
        try:
            db.create_all()
            ensure_database_schema()
            db.session.execute(text("SELECT 1"))
            app.logger.info("database_connected scheme=%s", database_scheme)
        except OperationalError:
            app.logger.exception("database_operational_error uri=%s", startup_diagnostics().get("database_uri"))
            raise
        except Exception:
            app.logger.exception("database_initialization_failed uri=%s", startup_diagnostics().get("database_uri"))
            raise


def save_chat_record(session_id, user_message, bot_response, intent, sentiment, timestamp=None):
    latest_row = (
        Chat.query
        .filter_by(session_id=session_id)
        .order_by(Chat.id.desc())
        .first()
    )
    if latest_row and (
        latest_row.user_message == user_message
        and latest_row.bot_response == bot_response
        and latest_row.intent == (intent or "general_query")
        and latest_row.sentiment == (sentiment or "neutral")
    ):
        return latest_row

    record = Chat(
        session_id=session_id,
        user_message=user_message,
        bot_response=bot_response,
        intent=intent or "general_query",
        sentiment=sentiment or "neutral",
        timestamp=timestamp or utcnow(),
    )
    db.session.add(record)
    db.session.commit()
    return record


def fetch_session_history(session_id, limit=80):
    rows = (
        Chat.query
        .filter_by(session_id=session_id)
        .order_by(Chat.id.asc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": row.id,
            "session_id": row.session_id,
            "user_message": row.user_message,
            "bot_response": row.bot_response,
            "intent": row.intent,
            "sentiment": row.sentiment,
            "timestamp": row.timestamp.isoformat() if row.timestamp else None,
        }
        for row in rows
    ]


def serialize_user(user):
    if not user:
        return None
    return {
        "id": user.id,
        "username": user.username,
        "name": user.username,
        "email": user.email,
        "theme_name": user.theme_name,
        "theme_mode": user.theme_mode,
        "accent_color": user.accent_color,
        "gradient_theme": user.gradient_theme,
        "is_guest": bool(user.is_guest),
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login": user.last_login.isoformat() if user.last_login else None,
    }


def serialize_chat_session(chat_session):
    return {
        "id": chat_session.id,
        "user_id": chat_session.user_id,
        "title": chat_session.title,
        "created_at": chat_session.created_at.isoformat() if chat_session.created_at else None,
        "updated_at": chat_session.updated_at.isoformat() if chat_session.updated_at else None,
    }


def serialize_chat_message(message):
    metadata = {}
    if message.metadata_json:
        try:
            metadata = json.loads(message.metadata_json)
        except (TypeError, ValueError, json.JSONDecodeError):
            metadata = {}
    return {
        "id": message.id,
        "chat_id": message.chat_id,
        "sender": message.sender,
        "message": message.message,
        "intent": message.intent,
        "sentiment": message.sentiment,
        "metadata_json": message.metadata_json,
        "metadata": metadata,
        "timestamp": message.timestamp.isoformat() if message.timestamp else None,
    }


def get_user_by_id(user_id):
    if not user_id:
        return None
    return User.query.filter_by(id=user_id).first()


def get_user_by_email(email):
    email = (email or "").strip().lower()
    if not email:
        return None
    return User.query.filter_by(email=email).first()


def get_user_by_username(username):
    username = (username or "").strip().lower()
    if not username:
        return None
    return User.query.filter(func.lower(User.username) == username).first()


def create_user(user_id, username, email, password_hash, theme_name="blue", theme_mode="system", accent_color="blue", gradient_theme="ocean", is_guest=False):
    user = User(
        id=user_id,
        username=(username or "friend").strip(),
        email=(email or "").strip().lower(),
        password_hash=password_hash or "",
        theme_name=theme_name,
        theme_mode=theme_mode,
        accent_color=accent_color,
        gradient_theme=gradient_theme,
        is_guest=bool(is_guest),
        created_at=utcnow(),
    )
    db.session.add(user)
    db.session.commit()
    return user


def update_user_profile(user_id, username=None, email=None, theme_name=None, theme_mode=None, accent_color=None, gradient_theme=None):
    user = get_user_by_id(user_id)
    if not user:
        return None
    if username is not None:
        user.username = username.strip()
    if email is not None:
        user.email = email.strip().lower()
    if theme_name is not None:
        user.theme_name = theme_name
    if theme_mode is not None:
        user.theme_mode = theme_mode
    if accent_color is not None:
        user.accent_color = accent_color
    if gradient_theme is not None:
        user.gradient_theme = gradient_theme
    db.session.commit()
    return user


def touch_user_login(user_id):
    user = get_user_by_id(user_id)
    if not user:
        return None
    user.last_login = utcnow()
    db.session.commit()
    return user


def create_chat_session(user_id, title="New chat", chat_id=None):
    chat_session = ChatSession(
        id=chat_id or uuid.uuid4().hex,
        user_id=user_id,
        title=(title or "New chat")[:160],
    )
    db.session.add(chat_session)
    db.session.commit()
    return chat_session


def get_chat_session(chat_id, user_id=None):
    if not chat_id:
        return None
    query = ChatSession.query.filter_by(id=chat_id)
    if user_id:
        query = query.filter_by(user_id=user_id)
    return query.first()


def list_chat_sessions(user_id, limit=120):
    return (
        ChatSession.query
        .filter_by(user_id=user_id)
        .order_by(ChatSession.updated_at.desc(), ChatSession.created_at.desc())
        .limit(limit)
        .all()
    )


def rename_chat_session(chat_id, user_id, title):
    chat_session = get_chat_session(chat_id, user_id=user_id)
    if not chat_session:
        return None
    chat_session.title = (title or "New chat")[:160]
    chat_session.updated_at = utcnow()
    db.session.commit()
    return chat_session


def delete_chat_session(chat_id, user_id):
    chat_session = get_chat_session(chat_id, user_id=user_id)
    if not chat_session:
        return False
    db.session.delete(chat_session)
    db.session.commit()
    return True


def fetch_chat_messages(chat_id, user_id=None, limit=400):
    chat_session = get_chat_session(chat_id, user_id=user_id)
    if not chat_session:
        return []
    rows = (
        ChatMessage.query
        .filter_by(chat_id=chat_id)
        .order_by(ChatMessage.timestamp.asc(), ChatMessage.id.asc())
        .limit(limit)
        .all()
    )
    return [serialize_chat_message(row) for row in rows]


def save_chat_exchange(chat_id, user_message, bot_response, intent=None, sentiment=None, metadata=None, timestamp=None):
    chat_session = get_chat_session(chat_id)
    if not chat_session:
        raise ValueError("Chat session not found")

    chat_timestamp = timestamp or utcnow()
    metadata_json = json.dumps(metadata or {}, ensure_ascii=False)
    user_row = ChatMessage(
        chat_id=chat_id,
        sender="user",
        message=user_message,
        intent=intent or "general_query",
        sentiment=sentiment or "neutral",
        metadata_json=metadata_json,
        timestamp=chat_timestamp,
    )
    bot_row = ChatMessage(
        chat_id=chat_id,
        sender="assistant",
        message=bot_response,
        intent=intent or "general_query",
        sentiment=sentiment or "neutral",
        metadata_json=metadata_json,
        timestamp=chat_timestamp,
    )
    chat_session.updated_at = chat_timestamp
    db.session.add(user_row)
    db.session.add(bot_row)
    db.session.commit()
    return user_row, bot_row
