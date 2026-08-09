from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz

ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf"}


class DocumentParseError(ValueError):
    """文档读取或解析失败。"""


class UnsupportedDocumentTypeError(DocumentParseError):
    """文件扩展名不在允许范围内。"""


@dataclass(frozen=True)
class ParsedDocument:
    """统一的文档解析结果。"""

    source_path: Path
    file_name: str
    extension: str
    text: str
    char_count: int
    page_count: int | None


def _normalize_text(text: str) -> str:
    """统一换行并去除首尾无意义空白。"""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.strip()


def _read_utf8_text(path: Path) -> str:
    """读取 UTF-8 / UTF-8 BOM 文本文件。"""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DocumentParseError(
            f"{path.name} 不是有效的 UTF-8 文本文件"
        ) from exc
    except OSError as exc:
        raise DocumentParseError(
            f"无法读取文档：{path.name}"
        ) from exc

    normalized = _normalize_text(text)
    if not normalized:
        raise DocumentParseError(
            f"文档内容为空：{path.name}"
        )
    return normalized


def _read_pdf(path: Path) -> tuple[str, int]:
    """使用 PyMuPDF 提取 PDF 文本。"""
    try:
        document = fitz.open(path)
    except Exception as exc:
        raise DocumentParseError(
            f"无法打开 PDF：{path.name}"
        ) from exc

    try:
        page_count = document.page_count
        pages: list[str] = []

        for page_index in range(page_count):
            page_text = document.load_page(page_index).get_text("text")
            normalized_page = _normalize_text(page_text)
            if normalized_page:
                pages.append(normalized_page)

        text = _normalize_text("\n\n".join(pages))
        if not text:
            raise DocumentParseError(
                f"PDF 中未提取到可用文本：{path.name}"
            )

        return text, page_count
    finally:
        document.close()


def parse_document(
    file_path: str | Path,
    *,
    max_size_mb: int = 20,
) -> ParsedDocument:
    """
    解析 TXT、Markdown 或 PDF。

    本函数只负责本地文件解析：
    - 不写 MySQL
    - 不写 Chroma
    - 不进行分块
    """
    path = Path(file_path).resolve()

    if not path.exists():
        raise DocumentParseError(
            f"文件不存在：{path}"
        )
    if not path.is_file():
        raise DocumentParseError(
            f"目标不是文件：{path}"
        )

    extension = path.suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise UnsupportedDocumentTypeError(
            f"不支持的文档类型：{extension or '无扩展名'}"
        )

    if max_size_mb <= 0:
        raise ValueError("max_size_mb 必须大于 0")

    file_size = path.stat().st_size
    max_size_bytes = max_size_mb * 1024 * 1024
    if file_size > max_size_bytes:
        raise DocumentParseError(
            f"文件超过 {max_size_mb} MB 限制：{path.name}"
        )

    if extension in {".txt", ".md"}:
        text = _read_utf8_text(path)
        page_count: int | None = None
    else:
        text, page_count = _read_pdf(path)

    return ParsedDocument(
        source_path=path,
        file_name=path.name,
        extension=extension,
        text=text,
        char_count=len(text),
        page_count=page_count,
    )
