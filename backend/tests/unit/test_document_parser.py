from pathlib import Path

import fitz
import pytest

from app.services.knowledge.document_parser import (
    DocumentParseError,
    UnsupportedDocumentTypeError,
    parse_document,
)


def test_parse_txt_document(tmp_path: Path) -> None:
    path = tmp_path / "客服说明.txt"
    path.write_text(
        "退款申请审核通过后，退款通常在三个工作日内原路退回。\n",
        encoding="utf-8",
    )

    result = parse_document(path)

    assert result.extension == ".txt"
    assert result.file_name == "客服说明.txt"
    assert "三个工作日" in result.text
    assert result.char_count == len(result.text)
    assert result.page_count is None


def test_parse_utf8_bom_txt_document(tmp_path: Path) -> None:
    path = tmp_path / "bom.txt"
    path.write_text(
        "支持 UTF-8 BOM。",
        encoding="utf-8-sig",
    )

    result = parse_document(path)

    assert result.text == "支持 UTF-8 BOM。"


def test_parse_markdown_document(tmp_path: Path) -> None:
    path = tmp_path / "退换货政策.md"
    path.write_text(
        "# 退换货政策\n\n"
        "商品签收后 7 天内，符合条件时可以申请退货。\n",
        encoding="utf-8",
    )

    result = parse_document(path)

    assert result.extension == ".md"
    assert "# 退换货政策" in result.text
    assert "7 天内" in result.text


def test_parse_pdf_document(tmp_path: Path) -> None:
    path = tmp_path / "产品说明.pdf"

    document = fitz.open()
    page_one = document.new_page()
    page_one.insert_text(
        (72, 72),
        "AI Customer Service Product Guide",
    )
    page_two = document.new_page()
    page_two.insert_text(
        (72, 72),
        "Refund requests are reviewed before processing.",
    )
    document.save(path)
    document.close()

    result = parse_document(path)

    assert result.extension == ".pdf"
    assert result.page_count == 2
    assert "AI Customer Service Product Guide" in result.text
    assert "Refund requests are reviewed" in result.text


def test_empty_text_document_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "empty.txt"
    path.write_text("   \n\n", encoding="utf-8")

    with pytest.raises(
        DocumentParseError,
        match="文档内容为空",
    ):
        parse_document(path)


def test_binary_non_utf8_txt_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "broken.txt"
    path.write_bytes(b"\xff\xfe\xfa\xfb")

    with pytest.raises(
        DocumentParseError,
        match="不是有效的 UTF-8",
    ):
        parse_document(path)


def test_unsupported_extension_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "data.docx"
    path.write_text("not supported", encoding="utf-8")

    with pytest.raises(
        UnsupportedDocumentTypeError,
        match="不支持的文档类型",
    ):
        parse_document(path)


def test_missing_file_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "missing.pdf"

    with pytest.raises(
        DocumentParseError,
        match="文件不存在",
    ):
        parse_document(path)


def test_file_size_limit_is_enforced(tmp_path: Path) -> None:
    path = tmp_path / "large.txt"
    path.write_text("a" * 2048, encoding="utf-8")

    with pytest.raises(
        DocumentParseError,
        match="文件超过",
    ):
        parse_document(path, max_size_mb=0.001)


def test_pdf_without_extractable_text_is_rejected(
    tmp_path: Path,
) -> None:
    path = tmp_path / "blank.pdf"

    document = fitz.open()
    document.new_page()
    document.save(path)
    document.close()

    with pytest.raises(
        DocumentParseError,
        match="未提取到可用文本",
    ):
        parse_document(path)
