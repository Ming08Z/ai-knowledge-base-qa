from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from pypdf import PdfReader


def clean_text(value: str) -> str:
    return re.sub(r"\n{4,}", "\n\n\n", str(value or "").replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")).strip()


def extract_document_text(path: Path, file_name: str) -> str:
    extension = Path(file_name).suffix.lower()
    if extension in {".txt", ".md"}:
        raw = path.read_bytes()
        for encoding in ("utf-8", "gb18030"):
            try:
                return clean_text(raw.decode(encoding))
            except UnicodeDecodeError:
                continue
        return clean_text(raw.decode("utf-8", errors="replace"))
    if extension == ".pdf":
        reader = PdfReader(str(path))
        pages = []
        for index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                pages.append(f"第 {index} 页\n{text}")
        return clean_text("\n\n".join(pages))
    if extension == ".docx":
        with zipfile.ZipFile(path) as archive:
            document = ElementTree.fromstring(archive.read("word/document.xml"))
        namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        paragraphs = []
        for paragraph in document.findall(".//w:p", namespace):
            line = "".join(node.text or "" for node in paragraph.findall(".//w:t", namespace))
            if line.strip():
                paragraphs.append(line)
        return clean_text("\n".join(paragraphs))
    raise ValueError(f"服务器暂不支持重新解析 {extension or '未知'} 格式")
