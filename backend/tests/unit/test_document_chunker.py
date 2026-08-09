from pathlib import Path

import pytest

from app.services.knowledge.document_chunker import (
    DocumentChunkingError,
    chunk_document,
    chunk_text,
)
from app.services.knowledge.document_parser import ParsedDocument


def test_short_text_produces_single_chunk() -> None:
    chunks = chunk_text(
        "退款申请审核通过后会原路退回。",
        chunk_size=100,
        overlap=20,
    )

    assert len(chunks) == 1
    assert chunks[0].index == 0
    assert chunks[0].text == "退款申请审核通过后会原路退回。"
    assert chunks[0].start_char == 0
    assert chunks[0].end_char == len(
        "退款申请审核通过后会原路退回。"
    )


def test_long_text_never_exceeds_chunk_size_without_whitespace_padding() -> None:
    text = "A" * 350

    chunks = chunk_text(
        text,
        chunk_size=100,
        overlap=20,
    )

    assert len(chunks) > 1
    assert all(chunk.char_count <= 100 for chunk in chunks)


def test_hard_split_preserves_expected_overlap() -> None:
    text = "ABCDEFGHIJKLMNOPQRSTUVWXYZ" * 4

    chunks = chunk_text(
        text,
        chunk_size=40,
        overlap=10,
    )

    assert len(chunks) >= 2
    assert chunks[0].text[-10:] == chunks[1].text[:10]


def test_prefers_paragraph_boundary() -> None:
    first = "第一段内容" * 12
    second = "第二段内容" * 12
    text = first + "\n\n" + second

    chunks = chunk_text(
        text,
        chunk_size=len(first) + 20,
        overlap=10,
    )

    assert len(chunks) >= 2
    assert chunks[0].end_char == len(first) + 2


def test_prefers_chinese_sentence_boundary() -> None:
    text = (
        "退款申请提交后会进入审核流程。"
        "审核通过后通常会原路退回。"
        "到账时间以支付渠道为准。"
        "如有异常请联系人工客服。"
    )

    chunks = chunk_text(
        text,
        chunk_size=36,
        overlap=8,
    )

    assert len(chunks) >= 2
    assert chunks[0].text.endswith(("。", "！", "？"))


def test_chunk_offsets_advance_and_cover_document() -> None:
    text = "0123456789" * 40

    chunks = chunk_text(
        text,
        chunk_size=80,
        overlap=16,
    )

    assert chunks[0].start_char == 0
    assert chunks[-1].end_char == len(text)

    for previous, current in zip(chunks, chunks[1:]):
        assert current.start_char > previous.start_char
        assert current.start_char < previous.end_char


def test_chunk_indices_are_contiguous() -> None:
    chunks = chunk_text(
        "知识库内容。" * 100,
        chunk_size=90,
        overlap=15,
    )

    assert [chunk.index for chunk in chunks] == list(
        range(len(chunks))
    )


@pytest.mark.parametrize(
    ("chunk_size", "overlap", "message"),
    [
        (0, 0, "chunk_size 必须大于 0"),
        (-1, 0, "chunk_size 必须大于 0"),
        (100, -1, "overlap 不能小于 0"),
        (100, 100, "overlap 必须小于 chunk_size"),
        (100, 120, "overlap 必须小于 chunk_size"),
    ],
)
def test_invalid_chunking_options_are_rejected(
    chunk_size: int,
    overlap: int,
    message: str,
) -> None:
    with pytest.raises(DocumentChunkingError, match=message):
        chunk_text(
            "有效文本",
            chunk_size=chunk_size,
            overlap=overlap,
        )


@pytest.mark.parametrize("text", ["", " ", "\n\n"])
def test_empty_text_is_rejected(text: str) -> None:
    with pytest.raises(
        DocumentChunkingError,
        match="不能为空",
    ):
        chunk_text(text)


def test_non_string_text_is_rejected() -> None:
    with pytest.raises(
        DocumentChunkingError,
        match="必须是字符串",
    ):
        chunk_text(None)  # type: ignore[arg-type]


def test_chunk_document_carries_source_metadata() -> None:
    parsed = ParsedDocument(
        source_path=Path("D:/example/退换货政策.md"),
        file_name="退换货政策.md",
        extension=".md",
        text="商品签收后七天内可以根据规则申请退货。" * 30,
        char_count=630,
        page_count=None,
    )

    chunks = chunk_document(
        parsed,
        chunk_size=120,
        overlap=20,
    )

    assert len(chunks) > 1
    assert all(
        chunk.source_name == "退换货政策.md"
        for chunk in chunks
    )
    assert all(
        chunk.source_extension == ".md"
        for chunk in chunks
    )
