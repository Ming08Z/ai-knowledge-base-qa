from __future__ import annotations

import base64
import hashlib
import ipaddress
import os
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .auth import current_user
from .database import DATABASE_URL, User, UserModelConfig, get_db


router = APIRouter(prefix="/api/model-config", tags=["model-config"])

PROVIDERS = {
    "deepseek": {"label": "DeepSeek", "baseUrl": "https://api.deepseek.com", "model": "deepseek-chat"},
    "openai": {"label": "OpenAI", "baseUrl": "https://api.openai.com/v1", "model": "gpt-4.1-mini"},
    "qwen": {"label": "通义千问 / Qwen", "baseUrl": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus"},
    "moonshot": {"label": "Moonshot / Kimi", "baseUrl": "https://api.moonshot.cn/v1", "model": "moonshot-v1-8k"},
    "zhipu": {"label": "智谱 GLM", "baseUrl": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-4-flash"},
    "siliconflow": {"label": "SiliconFlow", "baseUrl": "https://api.siliconflow.cn/v1", "model": "deepseek-ai/DeepSeek-V3"},
    "openrouter": {"label": "OpenRouter", "baseUrl": "https://openrouter.ai/api/v1", "model": "openai/gpt-4o-mini"},
    "custom": {"label": "自定义兼容接口", "baseUrl": "", "model": ""},
}


def _cipher() -> Fernet:
    secret = os.getenv("MODEL_CONFIG_SECRET", "").strip() or os.getenv("API_KEY", "").strip() or DATABASE_URL
    key = base64.urlsafe_b64encode(hashlib.sha256(f"ai-kb-model-config:{secret}".encode("utf-8")).digest())
    return Fernet(key)


def encrypt_api_key(api_key: str) -> str:
    return _cipher().encrypt(api_key.encode("utf-8")).decode("ascii")


def decrypt_api_key(value: str) -> str:
    try:
        return _cipher().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeError) as exc:
        raise HTTPException(status_code=500, detail="API 密钥无法解密，请重新保存配置") from exc


def _safe_custom_base_url(value: str) -> str:
    url = str(value or "").strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise HTTPException(status_code=400, detail="自定义接口必须是有效的 HTTPS 公网地址")
    hostname = parsed.hostname.lower().rstrip(".")
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        raise HTTPException(status_code=400, detail="自定义接口不能使用本机或内网地址")
    try:
        address = ipaddress.ip_address(hostname)
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_multicast:
            raise HTTPException(status_code=400, detail="自定义接口不能使用本机或内网地址")
    except ValueError:
        pass
    return url


def normalized_config(payload: dict) -> tuple[str, str, str, bool]:
    provider = str(payload.get("provider", "openai")).strip().lower()
    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail="不支持该 API 提供商")
    preset = PROVIDERS[provider]
    base_url = preset["baseUrl"] if provider != "custom" else _safe_custom_base_url(payload.get("baseUrl", ""))
    model = str(payload.get("model", "")).strip() or preset["model"]
    if not model or len(model) > 255 or any(char in model for char in "\r\n\0"):
        raise HTTPException(status_code=400, detail="请填写有效的模型名称")
    return provider, base_url, model, bool(payload.get("enabled", True))


def public_config(record: UserModelConfig | None) -> dict:
    if not record:
        return {"configured": False, "enabled": False, "provider": "openai", "baseUrl": PROVIDERS["openai"]["baseUrl"], "model": PROVIDERS["openai"]["model"], "maskedKey": ""}
    return {
        "configured": bool(record.api_key_encrypted and record.model and record.base_url),
        "enabled": bool(record.enabled),
        "provider": record.provider,
        "providerLabel": PROVIDERS.get(record.provider, PROVIDERS["custom"])["label"],
        "baseUrl": record.base_url,
        "model": record.model,
        "maskedKey": "••••••••" if record.api_key_encrypted else "",
    }


@router.get("")
async def get_model_config(user: User = Depends(current_user), db: Session = Depends(get_db)):
    record = db.get(UserModelConfig, user.id)
    providers = [{"value": key, **value} for key, value in PROVIDERS.items()]
    return {"config": public_config(record), "providers": providers}


@router.put("")
async def put_model_config(payload: dict, user: User = Depends(current_user), db: Session = Depends(get_db)):
    provider, base_url, model, enabled = normalized_config(payload)
    record = db.get(UserModelConfig, user.id)
    api_key = str(payload.get("apiKey", "")).strip()
    if not record:
        if not api_key:
            raise HTTPException(status_code=400, detail="首次配置时必须填写 API Key")
        record = UserModelConfig(user_id=user.id)
    if api_key:
        if len(api_key) < 8 or len(api_key) > 4096 or any(char in api_key for char in "\r\n\0"):
            raise HTTPException(status_code=400, detail="API Key 格式无效")
        record.api_key_encrypted = encrypt_api_key(api_key)
    record.provider = provider
    record.base_url = base_url
    record.model = model
    record.enabled = enabled
    db.add(record)
    db.commit()
    db.refresh(record)
    return {"config": public_config(record)}


def resolve_user_model_config(db: Session, user_id: int) -> tuple[str, str, str, str]:
    record = db.get(UserModelConfig, user_id)
    if not record or not record.enabled or not record.api_key_encrypted:
        raise HTTPException(status_code=400, detail="尚未启用自定义 API 配置")
    provider, base_url, model, _enabled = normalized_config({"provider": record.provider, "baseUrl": record.base_url, "model": record.model, "enabled": record.enabled})
    return provider, base_url, model, decrypt_api_key(record.api_key_encrypted)
