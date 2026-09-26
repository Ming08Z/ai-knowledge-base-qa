from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .auth import current_user
from .database import Conversation, FileMetadata, KnowledgeFolder, QuizRecord, User, UserPreference, get_db
from .document_parser import extract_document_text
from .vector_store import delete_document, index_document


router = APIRouter(prefix="/api", tags=["persistence"])
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "backend" / "data"


def safe_payload(value, fallback):
    return value if isinstance(value, type(fallback)) else fallback


def item_id(item: object) -> str:
    if not isinstance(item, dict):
        return ""
    return str(item.get("id", "")).strip()[:80]


def safe_int(value: object, fallback: int = 0) -> int:
    try:
        return int(value or fallback)
    except (TypeError, ValueError, OverflowError):
        return fallback


@router.get("/state")
async def get_state(user: User = Depends(current_user), db: Session = Depends(get_db)):
    preference = db.get(UserPreference, user.id)
    folders = [dict(row.payload_json or {}, id=row.id, name=row.name, createdAt=row.created_at_ms) for row in db.query(KnowledgeFolder).filter(KnowledgeFolder.user_id == user.id).all()]
    conversations = [dict(row.payload_json or {}, id=row.id, title=row.title, createdAt=row.created_at_ms, updatedAt=row.updated_at_ms, messages=row.messages_json or []) for row in db.query(Conversation).filter(Conversation.user_id == user.id).order_by(Conversation.updated_at_ms.desc()).all()]
    quizzes = [dict(row.payload_json or {}, id=row.id) for row in db.query(QuizRecord).filter(QuizRecord.user_id == user.id).order_by(QuizRecord.date_text.desc()).all()]
    files = []
    for row in db.query(FileMetadata).filter(FileMetadata.user_id == user.id).all():
        item = dict(row.payload_json or {}, id=row.id, folderId=row.folder_id, name=row.name, size=row.size_bytes, mime=row.mime_type, createdAt=row.created_at_ms, status=row.status, error=row.error_text, parsedLength=row.parsed_length)
        if row.custom_summary:
            item["customSummary"] = row.custom_summary
        files.append(item)
    base = {"version": 1, "activeConversationId": None, "activeFolderId": None, "selectedFolderIds": [], "conversations": conversations, "folders": folders, "files": files, "quizHistory": quizzes, "customWrongQuestions": [], "wrongBookRemoved": {}, "uiFontSize": "medium", "uiTheme": "light", "uiModel": "deepseek-v4-flash", "uiLanguage": "zh"}
    base.update({key: value for key, value in (preference.preferences_json if preference else {}).items() if key in base})
    base.update({"conversations": conversations, "folders": folders, "files": files, "quizHistory": quizzes})
    return {"state": base}


@router.put("/state")
async def put_state(payload: dict, user: User = Depends(current_user), db: Session = Depends(get_db)):
    state = payload.get("state", payload)
    if not isinstance(state, dict):
        raise HTTPException(status_code=400, detail="状态格式无效")
    preferences = {key: state.get(key) for key in ("version", "activeConversationId", "activeFolderId", "selectedFolderIds", "customWrongQuestions", "wrongBookRemoved", "uiFontSize", "uiTheme", "uiModel", "uiLanguage")}
    preference = db.get(UserPreference, user.id) or UserPreference(user_id=user.id, preferences_json={})
    preference.preferences_json = preferences
    db.add(preference)

    db.query(KnowledgeFolder).filter(KnowledgeFolder.user_id == user.id).delete(synchronize_session=False)
    db.query(Conversation).filter(Conversation.user_id == user.id).delete(synchronize_session=False)
    db.query(QuizRecord).filter(QuizRecord.user_id == user.id).delete(synchronize_session=False)
    db.query(FileMetadata).filter(FileMetadata.user_id == user.id).delete(synchronize_session=False)

    seen: set[tuple[str, str]] = set()
    for collection_name, model_name in (("folders", "folder"), ("conversations", "conversation"), ("quizHistory", "quiz"), ("files", "file")):
        for item in safe_payload(state.get(collection_name), []):
            record_id = item_id(item)
            marker = (model_name, record_id)
            if not record_id or marker in seen:
                continue
            seen.add(marker)
            if model_name == "folder":
                db.add(KnowledgeFolder(id=record_id, user_id=user.id, name=str(item.get("name", "未命名文件夹"))[:255], created_at_ms=safe_int(item.get("createdAt")), payload_json=item))
            elif model_name == "conversation":
                db.add(Conversation(id=record_id, user_id=user.id, title=str(item.get("title", "新聊天"))[:255], created_at_ms=safe_int(item.get("createdAt")), updated_at_ms=safe_int(item.get("updatedAt")), messages_json=safe_payload(item.get("messages"), []), payload_json={key: value for key, value in item.items() if key != "messages"}))
            elif model_name == "quiz":
                db.add(QuizRecord(id=record_id, user_id=user.id, folder_name=str(item.get("folderName", ""))[:255], date_text=str(item.get("date", ""))[:64], accuracy=safe_int(item.get("accuracy")), payload_json=item))
            else:
                db.add(FileMetadata(id=record_id, user_id=user.id, folder_id=str(item.get("folderId", ""))[:80], name=str(item.get("name", "未命名文件"))[:512], size_bytes=safe_int(item.get("size")), mime_type=str(item.get("mime", ""))[:255], created_at_ms=safe_int(item.get("createdAt")), status=str(item.get("status", "parsing"))[:32], error_text=str(item.get("error", "")), parsed_length=safe_int(item.get("parsedLength")), custom_summary=item.get("customSummary"), storage_key=f"{user.id}/{record_id}", payload_json=item))
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"ok": True}


def file_directory(user_id: int, file_id: str) -> Path:
    if not file_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in file_id):
        raise HTTPException(status_code=400, detail="文件 ID 无效")
    return DATA_DIR / str(user_id) / file_id


@router.put("/files/{file_id}/payload")
async def put_file_payload(
    file_id: str,
    parsed_text: str = Form(""),
    parsed_text_file: UploadFile | None = File(None),
    folder_id: str = Form(""),
    file_name: str = Form(""),
    original: UploadFile | None = File(None),
    user: User = Depends(current_user),
):
    if parsed_text_file is not None:
        parsed_bytes = await parsed_text_file.read()
        parsed_text = parsed_bytes.decode("utf-8", errors="replace")
    folder = file_directory(user.id, file_id)
    folder.mkdir(parents=True, exist_ok=True)
    if original is not None:
        with (folder / "original.bin").open("wb") as output:
            while chunk := await original.read(1024 * 1024):
                output.write(chunk)
        (folder / "original-name.txt").write_text(original.filename or "file", encoding="utf-8")
        (folder / "mime.txt").write_text(original.content_type or "application/octet-stream", encoding="utf-8")
    parsed_path = folder / "parsed.txt"
    if parsed_text.strip() or not parsed_path.exists() or parsed_path.stat().st_size == 0:
        parsed_path.write_text(parsed_text or "", encoding="utf-8")
    else:
        parsed_text = parsed_path.read_text(encoding="utf-8", errors="replace")
    indexed_chunks = 0
    index_warning = ""
    if parsed_text.strip():
        try:
            indexed_chunks = await run_in_threadpool(
                index_document,
                user.id,
                file_id,
                str(folder_id)[:80],
                (file_name or original.filename if original else file_name) or file_id,
                parsed_text,
            )
        except Exception as exc:
            index_warning = str(exc)
    return {"ok": True, "parsedLength": len(parsed_text), "indexedChunks": indexed_chunks, "indexWarning": index_warning}


@router.post("/files/{file_id}/reparse")
async def reparse_file(file_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.query(FileMetadata).filter(FileMetadata.user_id == user.id, FileMetadata.id == file_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="找不到文件元数据")
    folder = file_directory(user.id, file_id)
    original = folder / "original.bin"
    if not original.exists():
        raise HTTPException(status_code=404, detail="找不到文件原件，请重新上传")
    try:
        parsed_text = await run_in_threadpool(extract_document_text, original, row.name)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"服务器重新解析失败：{exc}") from exc
    if len(parsed_text.strip()) < 8:
        raise HTTPException(status_code=422, detail="未能从文件中提取有效文本；扫描版 PDF 需要 OCR")
    (folder / "parsed.txt").write_text(parsed_text, encoding="utf-8")
    index_warning = ""
    indexed_chunks = 0
    try:
        indexed_chunks = await run_in_threadpool(index_document, user.id, file_id, row.folder_id, row.name, parsed_text)
    except Exception as exc:
        index_warning = str(exc)
    row.status = "success"
    row.error_text = ""
    row.parsed_length = len(parsed_text)
    row.payload_json = dict(row.payload_json or {}, status="success", error="", parsedLength=len(parsed_text))
    db.add(row)
    db.commit()
    return {"ok": True, "parsedLength": len(parsed_text), "indexedChunks": indexed_chunks, "indexWarning": index_warning}


@router.get("/files/{file_id}/payload")
async def get_file_payload(file_id: str, user: User = Depends(current_user)):
    folder = file_directory(user.id, file_id)
    original = folder / "original.bin"
    if not original.exists():
        raise HTTPException(status_code=404, detail="找不到文件数据")
    return {"id": file_id, "parsedText": (folder / "parsed.txt").read_text(encoding="utf-8") if (folder / "parsed.txt").exists() else "", "contentUrl": f"/api/files/{file_id}/content", "mime": (folder / "mime.txt").read_text(encoding="utf-8") if (folder / "mime.txt").exists() else "application/octet-stream"}


@router.get("/files/{file_id}/content")
async def get_file_content(file_id: str, user: User = Depends(current_user)):
    folder = file_directory(user.id, file_id)
    original = folder / "original.bin"
    if not original.exists():
        raise HTTPException(status_code=404, detail="找不到文件数据")
    name = (folder / "original-name.txt").read_text(encoding="utf-8") if (folder / "original-name.txt").exists() else file_id
    mime = (folder / "mime.txt").read_text(encoding="utf-8") if (folder / "mime.txt").exists() else "application/octet-stream"
    return FileResponse(
        original,
        filename=name,
        media_type=mime,
        headers={
            "Cache-Control": "private, max-age=3600",
            "Accept-Ranges": "bytes",
        },
    )


@router.delete("/files/{file_id}/payload")
async def delete_file_payload(file_id: str, user: User = Depends(current_user)):
    folder = file_directory(user.id, file_id)
    if folder.exists():
        shutil.rmtree(folder)
    try:
        await run_in_threadpool(delete_document, user.id, file_id)
    except Exception:
        pass
    return {"ok": True}
