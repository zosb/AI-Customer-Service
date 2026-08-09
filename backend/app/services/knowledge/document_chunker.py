from __future__ import annotations

from dataclasses import dataclass

from app.services.knowledge.document_parser import ParsedDocument


class DocumentChunkingError(ValueError):
    """文档分块参数或文本内容无效。"""


@dataclass(frozen=True)
class DocumentChunk:
    """单个知识片段。"""

    index: int
    text: str
    char_count: int
    start_char: int
    end_char: int
    source_name: str | None = None
    source_extension: str | None = None


_BREAK_SEPARATORS: tuple[str, ...] = (
    "\n\n",
    "\n",
    "。",
    "！",
    "？",
    "；",
    ". ",
    "! ",
    "? ",
    "; ",
)


def _validate_chunking_options(
    chunk_size: int,
    overlap: int,
) -> None:
    if chunk_size <= 0:
        raise DocumentChunkingError("chunk_size 必须大于 0")
    if overlap < 0:
        raise DocumentChunkingError("overlap 不能小于 0")
    if overlap >= chunk_size:
        raise DocumentChunkingError(
            "overlap 必须小于 chunk_size"
        )


def _find_preferred_end(
    text: str,
    start: int,
    hard_end: int,
    chunk_size: int,
    overlap: int,
) -> int:
    """
    在最大长度以内优先寻找段落、换行或句末位置。

    为避免产生过短片段，只在当前窗口后 60% 区域寻找自然边界。
    """
    if hard_end >= len(text):
        return len(text)

    min_content_length = max(
        int(chunk_size * 0.6),
        overlap + 1,
    )
    search_start = min(
        start + min_content_length,
        hard_end,
    )

    best_end = -1

    for separator in _BREAK_SEPARATORS:
        position = text.rfind(
            separator,
            search_start,
            hard_end,
        )
        if position == -1:
            continue

        candidate_end = position + len(separator)
        if candidate_end > best_end:
            best_end = candidate_end

    if best_end > start:
        return best_end

    return hard_end


def chunk_text(
    text: str,
    *,
    chunk_size: int = 800,
    overlap: int = 120,
) -> list[DocumentChunk]:
    """
    将文本切成具有固定最大长度和重叠区域的片段。

    规则：
    - 默认最大 800 字符；
    - 默认相邻片段重叠 120 字符；
    - 优先在段落、换行和句末切分；
    - 找不到自然边界时按最大长度硬切；
    - 保留原始字符位置，便于后续来源定位。
    """
    _validate_chunking_options(chunk_size, overlap)

    if not isinstance(text, str):
        raise DocumentChunkingError("待分块内容必须是字符串")

    if not text.strip():
        raise DocumentChunkingError("待分块文本不能为空")

    chunks: list[DocumentChunk] = []
    start = 0
    text_length = len(text)

    while start < text_length:
        hard_end = min(start + chunk_size, text_length)
        end = _find_preferred_end(
            text,
            start,
            hard_end,
            chunk_size,
            overlap,
        )

        raw_chunk = text[start:end]
        cleaned_chunk = raw_chunk.strip()

        if cleaned_chunk:
            chunks.append(
                DocumentChunk(
                    index=len(chunks),
                    text=cleaned_chunk,
                    char_count=len(cleaned_chunk),
                    start_char=start,
                    end_char=end,
                )
            )

        if end >= text_length:
            break

        next_start = end - overlap

        # 防止边界选择导致游标停滞。
        if next_start <= start:
            next_start = start + 1

        start = next_start

    if not chunks:
        raise DocumentChunkingError("文档分块后没有有效内容")

    return chunks


def chunk_document(
    document: ParsedDocument,
    *,
    chunk_size: int = 800,
    overlap: int = 120,
) -> list[DocumentChunk]:
    """对 ParsedDocument 分块并补充来源信息。"""
    chunks = chunk_text(
        document.text,
        chunk_size=chunk_size,
        overlap=overlap,
    )

    return [
        DocumentChunk(
            index=chunk.index,
            text=chunk.text,
            char_count=chunk.char_count,
            start_char=chunk.start_char,
            end_char=chunk.end_char,
            source_name=document.file_name,
            source_extension=document.extension,
        )
        for chunk in chunks
    ]
