from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import chromadb
from chromadb.api.models.Collection import Collection


class ChromaStoreError(RuntimeError):
    """Chroma 操作失败。"""


@dataclass(frozen=True)
class SearchResult:
    """单条向量检索结果。"""

    id: str
    document: str
    metadata: dict[str, Any]
    distance: float
    similarity: float


class ChromaVectorStore:
    """基于 Chroma PersistentClient 的持久化向量存储。"""

    def __init__(
        self,
        *,
        persist_dir: str | Path,
        collection_name: str,
    ) -> None:
        path = Path(persist_dir).resolve()

        if not collection_name.strip():
            raise ValueError("collection_name 不能为空")

        path.mkdir(parents=True, exist_ok=True)

        try:
            self._client = chromadb.PersistentClient(
                path=str(path),
            )
            self._collection: Collection = (
                self._client.get_or_create_collection(
                    name=collection_name,
                    metadata={"hnsw:space": "cosine"},
                )
            )
        except Exception as exc:
            raise ChromaStoreError(
                f"初始化 Chroma 失败：{exc}"
            ) from exc

        self.persist_dir = path
        self.collection_name = collection_name

    @property
    def count(self) -> int:
        try:
            return self._collection.count()
        except Exception as exc:
            raise ChromaStoreError(
                f"读取 Chroma 数量失败：{exc}"
            ) from exc

    def upsert(
        self,
        *,
        ids: Sequence[str],
        embeddings: Sequence[Sequence[float]],
        documents: Sequence[str],
        metadatas: Sequence[dict[str, Any]],
    ) -> None:
        self._validate_batch(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

        try:
            self._collection.upsert(
                ids=list(ids),
                embeddings=[
                    list(vector)
                    for vector in embeddings
                ],
                documents=list(documents),
                metadatas=list(metadatas),
            )
        except Exception as exc:
            raise ChromaStoreError(
                f"写入 Chroma 失败：{exc}"
            ) from exc

    def get(
        self,
        ids: Sequence[str],
    ) -> dict[str, Any]:
        if not ids:
            raise ValueError("ids 不能为空")

        try:
            return self._collection.get(
                ids=list(ids),
                include=[
                    "documents",
                    "metadatas",
                    "embeddings",
                ],
            )
        except Exception as exc:
            raise ChromaStoreError(
                f"读取 Chroma 失败：{exc}"
            ) from exc

    def query(
        self,
        *,
        query_embedding: Sequence[float],
        top_k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        if not query_embedding:
            raise ValueError("query_embedding 不能为空")
        if top_k <= 0:
            raise ValueError("top_k 必须大于 0")

        query_kwargs: dict[str, Any] = {
            "query_embeddings": [list(query_embedding)],
            "n_results": top_k,
            "include": [
                "documents",
                "metadatas",
                "distances",
            ],
        }
        if where is not None:
            query_kwargs["where"] = where

        try:
            response = self._collection.query(
                **query_kwargs,
            )
        except Exception as exc:
            raise ChromaStoreError(
                f"查询 Chroma 失败：{exc}"
            ) from exc

        ids = self._first_row(response.get("ids"))
        documents = self._first_row(
            response.get("documents")
        )
        metadatas = self._first_row(
            response.get("metadatas")
        )
        distances = self._first_row(
            response.get("distances")
        )

        results: list[SearchResult] = []

        for item_id, document, metadata, distance in zip(
            ids,
            documents,
            metadatas,
            distances,
            strict=False,
        ):
            numeric_distance = float(distance)
            similarity = 1.0 - numeric_distance

            results.append(
                SearchResult(
                    id=str(item_id),
                    document=str(document or ""),
                    metadata=dict(metadata or {}),
                    distance=numeric_distance,
                    similarity=similarity,
                )
            )

        return results

    def delete(
        self,
        *,
        ids: Sequence[str] | None = None,
        where: dict[str, Any] | None = None,
    ) -> None:
        if not ids and where is None:
            raise ValueError(
                "delete 必须提供 ids 或 where"
            )

        kwargs: dict[str, Any] = {}
        if ids:
            kwargs["ids"] = list(ids)
        if where is not None:
            kwargs["where"] = where

        try:
            self._collection.delete(**kwargs)
        except Exception as exc:
            raise ChromaStoreError(
                f"删除 Chroma 数据失败：{exc}"
            ) from exc

    def reset_collection(self) -> None:
        """删除并重建当前集合，仅用于测试或维护。"""
        try:
            self._client.delete_collection(
                name=self.collection_name
            )
            self._collection = (
                self._client.get_or_create_collection(
                    name=self.collection_name,
                    metadata={"hnsw:space": "cosine"},
                )
            )
        except Exception as exc:
            raise ChromaStoreError(
                f"重建 Chroma 集合失败：{exc}"
            ) from exc

    @staticmethod
    def _first_row(value: Any) -> list[Any]:
        if (
            isinstance(value, list)
            and value
            and isinstance(value[0], list)
        ):
            return value[0]
        return []

    @staticmethod
    def _validate_batch(
        *,
        ids: Sequence[str],
        embeddings: Sequence[Sequence[float]],
        documents: Sequence[str],
        metadatas: Sequence[dict[str, Any]],
    ) -> None:
        sizes = {
            len(ids),
            len(embeddings),
            len(documents),
            len(metadatas),
        }

        if 0 in sizes:
            raise ValueError("Chroma 写入批次不能为空")
        if len(sizes) != 1:
            raise ValueError(
                "ids、embeddings、documents、metadatas 数量必须一致"
            )

        if len(set(ids)) != len(ids):
            raise ValueError("同一批次中的 id 不能重复")

        dimension: int | None = None

        for index, vector in enumerate(embeddings):
            if not vector:
                raise ValueError(
                    f"第 {index + 1} 个向量不能为空"
                )

            if dimension is None:
                dimension = len(vector)
            elif len(vector) != dimension:
                raise ValueError(
                    "同一批次中的向量维度必须一致"
                )

            for value in vector:
                if isinstance(value, bool) or not isinstance(
                    value,
                    (int, float),
                ):
                    raise ValueError(
                        f"第 {index + 1} 个向量包含非数值"
                    )
