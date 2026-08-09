import httpx
import pytest

from app.services.llm.embedding_service import (
    EmbeddingService,
    EmbeddingServiceError,
)


def build_service(
    handler: httpx.MockTransport,
    *,
    dimension: int = 4,
) -> EmbeddingService:
    client = httpx.Client(transport=handler)

    return EmbeddingService(
        base_url="http://127.0.0.1:11434",
        model="test-embedding-model",
        dimension=dimension,
        timeout_seconds=10,
        client=client,
    )


def test_embed_single_text_returns_vector() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "embeddings": [[0.1, 0.2, 0.3, 0.4]],
            },
        )
    )
    service = build_service(transport)

    vector = service.embed_text("退款政策")

    assert vector == [0.1, 0.2, 0.3, 0.4]


def test_embed_multiple_texts_returns_vectors() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = request.read().decode("utf-8")
        return httpx.Response(
            200,
            json={
                "embeddings": [
                    [1, 2, 3, 4],
                    [5, 6, 7, 8],
                ],
            },
        )

    service = build_service(httpx.MockTransport(handler))

    vectors = service.embed_texts(
        ["退款政策", "配送时效"],
    )

    assert vectors == [
        [1.0, 2.0, 3.0, 4.0],
        [5.0, 6.0, 7.0, 8.0],
    ]
    assert captured["url"] == (
        "http://127.0.0.1:11434/api/embed"
    )
    assert '"model":"test-embedding-model"' in str(
        captured["payload"]
    )


@pytest.mark.parametrize(
    "texts",
    [
        [],
        [""],
        ["   "],
    ],
)
def test_empty_inputs_are_rejected(
    texts: list[str],
) -> None:
    service = build_service(
        httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"embeddings": []},
            )
        )
    )

    with pytest.raises(ValueError):
        service.embed_texts(texts)


def test_direct_string_input_is_rejected() -> None:
    service = build_service(
        httpx.MockTransport(
            lambda request: httpx.Response(200)
        )
    )

    with pytest.raises(
        ValueError,
        match="不能直接传字符串",
    ):
        service.embed_texts("退款政策")  # type: ignore[arg-type]


def test_non_string_item_is_rejected() -> None:
    service = build_service(
        httpx.MockTransport(
            lambda request: httpx.Response(200)
        )
    )

    with pytest.raises(
        ValueError,
        match="必须是字符串",
    ):
        service.embed_texts(
            ["正常文本", 123],  # type: ignore[list-item]
        )


def test_http_error_is_converted_to_service_error() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            404,
            json={"error": "model not found"},
        )
    )
    service = build_service(transport)

    with pytest.raises(
        EmbeddingServiceError,
        match="HTTP 404 - model not found",
    ):
        service.embed_text("测试")


def test_timeout_is_converted_to_service_error() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        raise httpx.ReadTimeout(
            "timeout",
            request=request,
        )

    service = build_service(
        httpx.MockTransport(handler)
    )

    with pytest.raises(
        EmbeddingServiceError,
        match="请求超时",
    ):
        service.embed_text("测试")


def test_invalid_json_is_rejected() -> None:
    service = build_service(
        httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                content=b"not-json",
                headers={
                    "content-type": "application/json",
                },
            )
        )
    )

    with pytest.raises(
        EmbeddingServiceError,
        match="无效 JSON",
    ):
        service.embed_text("测试")


def test_missing_embeddings_is_rejected() -> None:
    service = build_service(
        httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"model": "test"},
            )
        )
    )

    with pytest.raises(
        EmbeddingServiceError,
        match="缺少 embeddings",
    ):
        service.embed_text("测试")


def test_embedding_count_mismatch_is_rejected() -> None:
    service = build_service(
        httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "embeddings": [
                        [1, 2, 3, 4],
                    ],
                },
            )
        )
    )

    with pytest.raises(
        EmbeddingServiceError,
        match="数量与输入文本数量不一致",
    ):
        service.embed_texts(
            ["第一条", "第二条"],
        )


def test_wrong_embedding_dimension_is_rejected() -> None:
    service = build_service(
        httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "embeddings": [[1, 2, 3]],
                },
            )
        ),
        dimension=4,
    )

    with pytest.raises(
        EmbeddingServiceError,
        match="预期 4，实际 3",
    ):
        service.embed_text("测试")


def test_non_numeric_embedding_value_is_rejected() -> None:
    service = build_service(
        httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "embeddings": [
                        [1, 2, "bad", 4],
                    ],
                },
            )
        )
    )

    with pytest.raises(
        EmbeddingServiceError,
        match="包含非数值",
    ):
        service.embed_text("测试")


@pytest.mark.parametrize(
    ("dimension", "timeout_seconds", "message"),
    [
        (0, 10, "维度必须大于 0"),
        (4, 0, "超时时间必须大于 0"),
    ],
)
def test_invalid_configuration_is_rejected(
    dimension: int,
    timeout_seconds: float,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        EmbeddingService(
            base_url="http://127.0.0.1:11434",
            model="test-model",
            dimension=dimension,
            timeout_seconds=timeout_seconds,
        )
