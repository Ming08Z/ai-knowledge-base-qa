from __future__ import annotations

import os
import re
import threading
import unicodedata
import uuid
from pathlib import Path
from typing import Any

# Hugging Face's main endpoint is frequently unreachable on Windows networks in
# mainland China. Respect explicit user settings, otherwise use the compatible
# mirror and regular HTTP downloads instead of Xet storage.
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

from fastapi import APIRouter, Depends, HTTPException
from fastembed import TextEmbedding
from qdrant_client import QdrantClient, models
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .auth import current_user
from .database import FileMetadata, User, get_db


ROOT = Path(__file__).resolve().parents[1]
VECTOR_DIR = ROOT / "backend" / "vector_data"
COLLECTION_NAME = "knowledge_chunks"
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
INDEX_SCHEMA_VERSION = 2
router = APIRouter(prefix="/api/semantic", tags=["semantic-search"])

_client: QdrantClient | None = None
_embedder: TextEmbedding | None = None
_dimension: int | None = None
_lock = threading.RLock()


def _resources() -> tuple[QdrantClient, TextEmbedding, int]:
    """Lazily load Qdrant and the embedding model to keep server startup fast."""
    global _client, _embedder, _dimension
    with _lock:
        if _client is None:
            VECTOR_DIR.mkdir(parents=True, exist_ok=True)
            _client = QdrantClient(path=str(VECTOR_DIR))
        if _embedder is None:
            _embedder = TextEmbedding(model_name=EMBEDDING_MODEL)
        if _dimension is None:
            sample = next(iter(_embedder.embed(["向量维度检测"])))
            _dimension = len(sample)
        if not _client.collection_exists(COLLECTION_NAME):
            _client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=models.VectorParams(size=_dimension, distance=models.Distance.COSINE),
            )
        return _client, _embedder, _dimension


def close_vector_store() -> None:
    global _client
    with _lock:
        if _client is not None:
            _client.close()
            _client = None


def _document_filter(user_id: int, file_id: str) -> models.Filter:
    return models.Filter(
        must=[
            models.FieldCondition(key="user_id", match=models.MatchValue(value=user_id)),
            models.FieldCondition(key="file_id", match=models.MatchValue(value=file_id)),
        ]
    )


_PAGE_MARKER = re.compile(r"^第\s*\d+\s*页$")
_NUMBERED_HEADING = re.compile(r"^(?P<number>[1-9]\d?(?:\.\d+){0,2})\s+(?P<title>\S.*)$")
_TOC_ENTRY = re.compile(
    r"^(?P<number>[1-9]\d?(?:\.\d+){0,2})\s+(?P<title>.+?)\s+(?P<page>\d{1,4})$"
)


def _heading_key(value: str) -> str:
    """Compare headings while tolerating PDF casing, spacing and punctuation noise."""
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", normalized)


def _table_of_contents(lines: list[str]) -> dict[str, str]:
    """Extract a trustworthy numbered outline from the document's Contents pages."""
    starts = [index for index, line in enumerate(lines[:1200]) if line.strip().casefold() in {"contents", "目录"}]
    for start in starts:
        entries: dict[str, str] = {}
        pending = ""
        for raw_line in lines[start + 1 : start + 321]:
            line = re.sub(r"\s+", " ", raw_line.strip())
            if not line or _PAGE_MARKER.fullmatch(line) or ".indd" in line.casefold():
                continue
            if len(entries) >= 5 and line.casefold() in {"introduction", "前言", "序言"}:
                break

            numbered = _NUMBERED_HEADING.match(line)
            if numbered:
                pending = line
            elif pending:
                # PDF extraction can wrap a long table-of-contents title over two lines.
                pending = f"{pending} {line}"
            else:
                continue

            match = _TOC_ENTRY.match(pending)
            if not match:
                if len(pending) > 240:
                    pending = ""
                continue
            number = match.group("number")
            title = re.sub(r"\s+", " ", match.group("title")).strip(" .·")
            if title and len(title) <= 180:
                entries.setdefault(number, title)
            pending = ""

        major_count = sum("." not in number for number in entries)
        subsection_count = sum("." in number for number in entries)
        if len(entries) >= 6 and major_count >= 2 and subsection_count >= 2:
            return entries
    return {}


def _catalog_heading_at(lines: list[str], index: int, catalog: dict[str, str]) -> tuple[str, str, int] | None:
    """Return a catalog-backed heading and the number of physical lines it consumes."""
    first = re.sub(r"\s+", " ", lines[index].strip())
    match = _NUMBERED_HEADING.match(first)
    if not match or match.group("number") not in catalog:
        return None
    number = match.group("number")
    expected = catalog[number]
    candidate = match.group("title")
    for consumed in range(1, 4):
        if _heading_key(candidate) == _heading_key(expected):
            return number, expected, consumed
        next_index = index + consumed
        if next_index >= len(lines):
            break
        continuation = re.sub(r"\s+", " ", lines[next_index].strip())
        if (
            not continuation
            or _PAGE_MARKER.fullmatch(continuation)
            or _NUMBERED_HEADING.match(continuation)
            or ".indd" in continuation.casefold()
        ):
            break
        candidate = f"{candidate} {continuation}"
    return None


def _catalog_section_title(number: str, title: str, catalog: dict[str, str]) -> str:
    chapter_number = number.split(".", 1)[0]
    chapter_title = catalog.get(chapter_number, "").strip()
    chapter = f"第{chapter_number}章 {chapter_title}".strip()
    if number == chapter_number:
        return chapter
    return f"{chapter} · {number} {title}" if chapter_title else f"{number} {title}"


def _generic_heading(line: str) -> str | None:
    """Conservative fallback for documents without a usable table of contents."""
    stripped = re.sub(r"\s+", " ", line.strip())
    if not stripped or len(stripped) > 100:
        return None
    markdown = re.match(r"^#{1,6}\s+(.+)$", stripped)
    if markdown:
        return markdown.group(1).strip()
    if re.match(r"^(?:第[一二三四五六七八九十百0-9]+[章节篇]|Chapter\s+\d+\b)", stripped, re.I):
        return stripped
    # Requiring a dotted number avoids treating page numbers and ordinary list items as chapters.
    if re.match(r"^[1-9]\d?\.\d+(?:\.\d+)?\s+\S+", stripped) and not re.search(r"[。！？?!.:]$", stripped):
        return stripped
    return None


def _split_sections(text: str) -> list[tuple[str, str]]:
    clean_text = str(text or "").replace("\x00", "")
    lines = clean_text.splitlines()
    catalog = _table_of_contents(lines)
    sections: list[tuple[str, str]] = []
    title = "文档前言" if catalog else "相关内容"
    active_number = ""
    content: list[str] = []

    def flush() -> None:
        body = "\n".join(content).strip()
        if body:
            sections.append((title, body))
        content.clear()

    index = 0
    while index < len(lines):
        if catalog:
            heading = _catalog_heading_at(lines, index, catalog)
            if heading:
                number, heading_title, consumed = heading
                same_heading = number == active_number
                same_chapter_header = (
                    "." not in number
                    and active_number.startswith(f"{number}.")
                )
                # Repeated running headers must not reset the active subsection.
                if not same_heading and not same_chapter_header:
                    flush()
                    title = _catalog_section_title(number, heading_title, catalog)
                    active_number = number
                index += consumed
                continue
        else:
            heading_title = _generic_heading(lines[index])
            if heading_title:
                if heading_title != title:
                    flush()
                    title = heading_title
                index += 1
                continue
        content.append(lines[index])
        index += 1

    flush()
    return sections or [("相关内容", clean_text.strip())]


def _chunks(text: str, size: int = 700, overlap: int = 120) -> list[dict[str, str]]:
    chunks: list[dict[str, str]] = []
    step = max(1, size - overlap)
    for title, body in _split_sections(text):
        for start in range(0, len(body), step):
            excerpt = body[start : start + size].strip()
            if excerpt:
                chunks.append({"section": title or "相关片段", "excerpt": excerpt})
            if start + size >= len(body):
                break
    return chunks


def delete_document(user_id: int, file_id: str) -> None:
    client, _, _ = _resources()
    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=models.FilterSelector(filter=_document_filter(user_id, file_id)),
        wait=True,
    )


def index_document(user_id: int, file_id: str, folder_id: str, file_name: str, parsed_text: str) -> int:
    client, embedder, _ = _resources()
    document_chunks = _chunks(parsed_text)
    delete_document(user_id, file_id)
    if not document_chunks:
        return 0
    passages = [f"{chunk['section']}\n{chunk['excerpt']}" for chunk in document_chunks]
    vectors = list(embedder.embed(passages, batch_size=32))
    points = []
    for index, (chunk, vector) in enumerate(zip(document_chunks, vectors)):
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"ai-kb:{user_id}:{file_id}:{index}"))
        points.append(
            models.PointStruct(
                id=point_id,
                vector=vector.tolist(),
                payload={
                    "user_id": user_id,
                    "file_id": file_id,
                    "folder_id": folder_id,
                    "file_name": file_name,
                    "section": chunk["section"],
                    "excerpt": chunk["excerpt"],
                    "chunk_index": index,
                    "index_schema_version": INDEX_SCHEMA_VERSION,
                },
            )
        )
    for start in range(0, len(points), 64):
        client.upsert(collection_name=COLLECTION_NAME, points=points[start : start + 64], wait=True)
    return len(points)


def _is_indexed(user_id: int, file_id: str) -> bool:
    client, _, _ = _resources()
    points, _ = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=_document_filter(user_id, file_id),
        limit=1,
        with_payload=["index_schema_version"],
        with_vectors=False,
    )
    return bool(points and (points[0].payload or {}).get("index_schema_version") == INDEX_SCHEMA_VERSION)


def _ensure_folder_indexes(user: User, folder_ids: list[str], db: Session) -> None:
    rows = (
        db.query(FileMetadata)
        .filter(
            FileMetadata.user_id == user.id,
            FileMetadata.folder_id.in_(folder_ids),
            FileMetadata.status == "success",
        )
        .all()
    )
    for row in rows:
        if _is_indexed(user.id, row.id):
            continue
        parsed_file = ROOT / "backend" / "data" / str(user.id) / row.id / "parsed.txt"
        if parsed_file.exists():
            text = parsed_file.read_text(encoding="utf-8", errors="replace")
            if text.strip():
                index_document(user.id, row.id, row.folder_id, row.name, text)


def _query_terms(query: str) -> list[str]:
    words = re.findall(r"[a-zA-Z0-9_]{2,}|[\u4e00-\u9fff]{2,}", query.lower())
    stopwords = {"什么", "如何", "哪些", "是否", "这个", "一个", "请问", "介绍", "说明", "回答"}
    terms: set[str] = set()
    for word in words:
        if word in stopwords:
            continue
        terms.add(word)
        if re.fullmatch(r"[\u4e00-\u9fff]+", word) and len(word) > 4:
            terms.update(word[index : index + 2] for index in range(len(word) - 1))
    return sorted(terms, key=len, reverse=True)[:12]


def semantic_search(user_id: int, query: str, folder_ids: list[str], limit: int = 10) -> list[dict[str, Any]]:
    client, embedder, _ = _resources()
    query_vector = next(iter(embedder.query_embed(query))).tolist()
    result = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        query_filter=models.Filter(
            must=[
                models.FieldCondition(key="user_id", match=models.MatchValue(value=user_id)),
                models.FieldCondition(key="folder_id", match=models.MatchAny(any=folder_ids)),
            ]
        ),
        limit=max(1, min(limit, 20)),
        score_threshold=0.32,
        with_payload=True,
        with_vectors=False,
    )
    terms = _query_terms(query)
    sources: list[dict[str, Any]] = []
    for point in result.points:
        payload = point.payload or {}
        excerpt = str(payload.get("excerpt", ""))
        lower_excerpt = excerpt.lower()
        sources.append(
            {
                "fileId": str(payload.get("file_id", "")),
                "fileName": str(payload.get("file_name", "未命名文件")),
                "section": str(payload.get("section", "相关片段")),
                "excerpt": excerpt,
                "score": round(float(point.score), 5),
                "matchTerms": [term for term in terms if term.lower() in lower_excerpt],
            }
        )
    return sources


@router.post("/search")
async def search_knowledge(
    payload: dict,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    query = str(payload.get("query", "")).strip()
    folder_ids = [str(value)[:80] for value in payload.get("folderIds", []) if str(value).strip()]
    if not query:
        raise HTTPException(status_code=400, detail="检索内容不能为空")
    if not folder_ids:
        return {"sources": []}
    try:
        await run_in_threadpool(_ensure_folder_indexes, user, folder_ids, db)
        sources = await run_in_threadpool(semantic_search, user.id, query, folder_ids, int(payload.get("limit", 10)))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"语义检索暂时不可用：{exc}") from exc
    return {"sources": sources, "model": EMBEDDING_MODEL}


@router.post("/reindex")
async def reindex_knowledge(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    rows = db.query(FileMetadata).filter(FileMetadata.user_id == user.id, FileMetadata.status == "success").all()

    def rebuild() -> tuple[int, int, list[str]]:
        document_count = 0
        chunk_count = 0
        errors: list[str] = []
        for row in rows:
            parsed_file = ROOT / "backend" / "data" / str(user.id) / row.id / "parsed.txt"
            if not parsed_file.exists():
                errors.append(f"{row.name}：缺少解析文本")
                continue
            text = parsed_file.read_text(encoding="utf-8", errors="replace")
            if not text.strip():
                errors.append(f"{row.name}：解析文本为空")
                continue
            try:
                chunk_count += index_document(user.id, row.id, row.folder_id, row.name, text)
                document_count += 1
            except Exception as exc:
                errors.append(f"{row.name}：{exc}")
        return document_count, chunk_count, errors

    try:
        document_count, chunk_count, errors = await run_in_threadpool(rebuild)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"重建语义索引失败：{exc}") from exc
    return {
        "ok": not errors,
        "documents": document_count,
        "chunks": chunk_count,
        "errors": errors,
        "indexSchemaVersion": INDEX_SCHEMA_VERSION,
    }
