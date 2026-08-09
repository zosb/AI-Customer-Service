from pathlib import Path

import fitz

from app.services.knowledge.document_pipeline import process_document


def test_txt_parse_and_chunk_pipeline(tmp_path: Path) -> None:
    path = tmp_path / "退款说明.txt"
    text = (
        "退款申请提交后会进入审核流程。"
        "审核通过后，退款通常会在三个工作日内原路退回。"
        "具体到账时间以支付渠道为准。"
    ) * 30
    path.write_text(text, encoding="utf-8")

    result = process_document(
        path,
        chunk_size=120,
        overlap=20,
    )

    assert result.document.extension == ".txt"
    assert result.document.file_name == "退款说明.txt"
    assert result.chunk_count > 1
    assert all(chunk.char_count <= 120 for chunk in result.chunks)
    assert all(
        chunk.source_name == "退款说明.txt"
        for chunk in result.chunks
    )
    assert all(
        chunk.source_extension == ".txt"
        for chunk in result.chunks
    )


def test_markdown_parse_and_chunk_pipeline(tmp_path: Path) -> None:
    path = tmp_path / "售后政策.md"
    text = (
        "# 售后政策\n\n"
        "## 退货\n"
        "商品符合条件时可以申请退货。\n\n"
        "## 退款\n"
        "退款审核完成后按原支付方式退回。\n"
    ) * 20
    path.write_text(text, encoding="utf-8")

    result = process_document(
        path,
        chunk_size=150,
        overlap=25,
    )

    assert result.document.extension == ".md"
    assert "# 售后政策" in result.document.text
    assert result.chunk_count > 1
    assert result.chunks[0].index == 0
    assert result.chunks[-1].end_char == len(result.document.text)


def test_pdf_parse_and_chunk_pipeline(tmp_path: Path) -> None:
    path = tmp_path / "product-guide.pdf"

    document = fitz.open()
    for page_number in range(1, 4):
        page = document.new_page()
        page.insert_text(
            (72, 72),
            (
                f"Product Guide Page {page_number}. "
                "AI customer service supports knowledge retrieval, "
                "refund policy questions, and source references. "
            )
            * 4,
        )
    document.save(path)
    document.close()

    result = process_document(
        path,
        chunk_size=180,
        overlap=30,
    )

    assert result.document.extension == ".pdf"
    assert result.document.page_count == 3
    assert result.chunk_count > 1
    assert all(
        chunk.source_name == "product-guide.pdf"
        for chunk in result.chunks
    )
    assert "Product Guide Page 1" in result.document.text
    assert "Product Guide Page 3" in result.document.text


def test_pipeline_chunks_have_contiguous_indices_and_valid_offsets(
    tmp_path: Path,
) -> None:
    path = tmp_path / "knowledge.txt"
    path.write_text(
        "知识库测试内容。" * 200,
        encoding="utf-8",
    )

    result = process_document(
        path,
        chunk_size=100,
        overlap=20,
    )

    assert [chunk.index for chunk in result.chunks] == list(
        range(result.chunk_count)
    )

    for chunk in result.chunks:
        assert 0 <= chunk.start_char < chunk.end_char
        assert chunk.end_char <= len(result.document.text)
        assert chunk.char_count == len(chunk.text)

    for previous, current in zip(
        result.chunks,
        result.chunks[1:],
    ):
        assert current.start_char > previous.start_char
        assert current.start_char < previous.end_char
