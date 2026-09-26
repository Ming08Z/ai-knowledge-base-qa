from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    DATABASE_URL = "mysql+pymysql://ai_kb_user:change_me@127.0.0.1:3306/ai_knowledge_base?charset=utf8mb4"

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=1800, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
BIGINT = BigInteger().with_variant(Integer, "sqlite")


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    user: Mapped[User] = relationship()


class UserPreference(Base):
    __tablename__ = "user_preferences"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    preferences_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class UserModelConfig(Base):
    __tablename__ = "user_model_configs"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="openai")
    base_url: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    model: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class KnowledgeFolder(Base):
    __tablename__ = "knowledge_folders"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=0)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    __table_args__ = (Index("ix_folder_user_name", "user_id", "name"),)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=0)
    updated_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=0, index=True)
    messages_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class QuizRecord(Base):
    __tablename__ = "quiz_records"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    folder_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    date_text: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    accuracy: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class FileMetadata(Base):
    __tablename__ = "file_metadata"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    folder_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BIGINT, nullable=False, default=0)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="parsing")
    error_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    parsed_length: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    custom_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_database() -> None:
    Base.metadata.create_all(bind=engine)
