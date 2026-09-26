from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from .auth import current_user, router as auth_router
from .database import User, engine, get_db, init_database
from .model_config import resolve_user_model_config, router as model_config_router
from .persistence import router as persistence_router
from .vector_store import close_vector_store, router as semantic_router


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
DIST = FRONTEND / "dist"
LEGACY_CONFIG = Path(__file__).resolve().parent / "config.js"


def _legacy_config_value(name: str) -> str:
    """Read a legacy config value server-side without exposing config.js."""
    if not LEGACY_CONFIG.exists():
        return ""
    text = LEGACY_CONFIG.read_text(encoding="utf-8")
    match = re.search(rf"\b{re.escape(name)}\s*:\s*(['\"])(.*?)\1", text)
    return match.group(2).strip() if match else ""


def setting(name: str, fallback: str = "") -> str:
    return os.getenv(name, "").strip() or _legacy_config_value(name) or fallback


app = FastAPI(title="AI Knowledge Base API", version="1.0.0")
app.include_router(auth_router)
app.include_router(persistence_router)
app.include_router(semantic_router)
app.include_router(model_config_router)


@app.on_event("startup")
async def startup_database() -> None:
    init_database()


@app.on_event("shutdown")
async def shutdown_vector_database() -> None:
    close_vector_store()


@app.get("/api/health")
async def health() -> dict[str, Any]:
    key = setting("API_KEY")
    database_ok = False
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        database_ok = True
    except Exception:
        pass
    return {"ok": True, "apiConfigured": bool(key and key != "skxxx" and "占位" not in key), "databaseConfigured": database_ok, "vectorStore": "qdrant-local", "embeddingModel": "BAAI/bge-small-zh-v1.5"}


@app.post("/api/chat/completions")
async def chat_completions(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="请求格式无效")
    credential_source = str(payload.pop("credentialSource", "server"))
    provider = "builtin"
    if credential_source == "user":
        provider, base_url, configured_model, api_key = resolve_user_model_config(db, user.id)
        payload["model"] = configured_model
    else:
        api_key = setting("API_KEY")
        if not api_key or api_key == "skxxx" or "占位" in api_key:
            raise HTTPException(status_code=503, detail="请在服务端配置 API_KEY")
        base_url = setting("BASE_URL", "https://api.deepseek.com").rstrip("/")

    base_url = base_url.rstrip("/")
    upstream_url = base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if provider == "openrouter":
        headers.update({"HTTP-Referer": str(request.base_url).rstrip("/"), "X-Title": "AI Knowledge Base"})
    timeout = httpx.Timeout(connect=20.0, read=180.0, write=30.0, pool=20.0)

    if not payload.get("stream"):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(upstream_url, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"AI 服务连接失败：{exc}") from exc
        try:
            data = response.json()
        except ValueError:
            data = {"error": {"message": response.text or "AI 服务返回无效内容"}}
        return JSONResponse(data, status_code=response.status_code)

    client = httpx.AsyncClient(timeout=timeout)
    try:
        upstream = await client.send(
            client.build_request("POST", upstream_url, headers=headers, json=payload),
            stream=True,
        )
    except httpx.HTTPError as exc:
        await client.aclose()
        raise HTTPException(status_code=502, detail=f"AI 服务连接失败：{exc}") from exc

    if upstream.status_code >= 400:
        body = await upstream.aread()
        await upstream.aclose()
        await client.aclose()
        try:
            detail = json.loads(body.decode("utf-8", errors="replace"))
        except ValueError:
            detail = body.decode("utf-8", errors="replace")
        return JSONResponse(detail if isinstance(detail, dict) else {"error": {"message": detail}}, status_code=upstream.status_code)

    async def stream_body():
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(stream_body(), media_type=upstream.headers.get("content-type", "text/event-stream"))


@app.get("/")
@app.get("/index.html")
async def frontend_index():
    return FileResponse(FRONTEND / "index.html", media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-store"})


@app.get("/main.js")
async def frontend_script():
    script = DIST / "main.js"
    if not script.exists():
        raise HTTPException(status_code=503, detail="前端尚未构建，请先运行 npm run build")
    return FileResponse(script, media_type="text/javascript; charset=utf-8", headers={"Cache-Control": "no-store"})


@app.get("/config.js")
async def blocked_legacy_config():
    raise HTTPException(status_code=404, detail="Not found")
