from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import mimetypes
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.config import get_settings
from app.models.knowledge import KnowledgeChunk
from app.repositories.knowledge_repository import KnowledgeRepository
from app.services.knowledge.document_embedding_pipeline import (
    EmbeddedDocument,
    process_and_embed_document,
)
from app.services.llm.embedding_service import EmbeddingService
from app.services.vector.chroma_store import (
    ChromaVectorStore,
    SearchResult,
)


class KnowledgeIngestionError(RuntimeError):
    """知识文档入库流程失败。"""


@dataclass(frozen=True)
class KnowledgeIngestionResult:
    knowledge_base_id: int
    document_id: int
    original_name: str
    stored_name: str
    chunk_count: int
    vector_ids: tuple[str, ...]
    embedding_dimension: int
    status: str


@dataclass(frozen=True)
class KnowledgeSearchHit:
    vector_id: str
    knowledge_base_id: int
    document_id: int
    document_name: str
    chunk_index: int
    content: str
    similarity: float
    distance: float
    metadata: dict[str, Any]
    chunk_id: int | None = None
    priority: int = 0


@dataclass(frozen=True)
class KnowledgeRouteCandidate:
    """自动路由阶段的一条知识库候选。"""

    knowledge_base_id: int
    score: float
    top_similarity: float
    matched_chunks: int


@dataclass(frozen=True)
class KnowledgeRoutingResult:
    """一次多知识库自动路由 + 最终检索结果。"""

    knowledge_base_id: int | None
    route_score: float | None
    candidates: tuple[KnowledgeRouteCandidate, ...]
    hits: tuple[KnowledgeSearchHit, ...]


class KnowledgeIngestionService:
    """
    MySQL + Chroma 双写知识库服务。

    MySQL 保存业务元数据和 Chunk 正文；Chroma 保存向量。
    双写中任意一侧失败时执行补偿，避免出现“数据库已就绪但向量缺失”
    或“向量存在但数据库没有关联记录”的半完成状态。
    """

    def __init__(
        self,
        *,
        repository: KnowledgeRepository,
        vector_store: ChromaVectorStore,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        self.repository = repository
        self.vector_store = vector_store
        self.embedding_service = embedding_service or EmbeddingService()
        self.settings = get_settings()

    def ingest_document(
        self,
        file_path: str | Path,
        *,
        knowledge_base_id: int,
        original_name: str | None = None,
        stored_name: str | None = None,
        uploaded_by: int | None = None,
        priority: int = 0,
    ) -> KnowledgeIngestionResult:
        path = Path(file_path).resolve()
        self._validate_source_file(path)
        self.repository.get_active_base(knowledge_base_id)

        resolved_original_name = original_name or path.name
        resolved_stored_name = stored_name or (
            f"{uuid4().hex}{path.suffix.lower()}"
        )
        file_hash = self._hash_file(path)
        mime_type = self._guess_mime_type(path.suffix.lower())

        document = self.repository.create_processing_document(
            knowledge_base_id=knowledge_base_id,
            original_name=resolved_original_name,
            stored_name=resolved_stored_name,
            file_extension=path.suffix.lower(),
            mime_type=mime_type,
            file_size_bytes=path.stat().st_size,
            sha256=file_hash,
            uploaded_by=uploaded_by,
        )
        self.repository.commit()

        vector_ids: list[str] = []

        try:
            embedded = process_and_embed_document(
                path,
                max_size_mb=self.settings.max_upload_size_mb,
                chunk_size=self.settings.chunk_size,
                overlap=self.settings.chunk_overlap,
                embedding_service=self.embedding_service,
            )

            vector_ids = self._build_vector_ids(
                knowledge_base_id=knowledge_base_id,
                document_id=document.id,
                content_version=document.content_version,
                embedded=embedded,
            )

            self.vector_store.upsert(
                ids=vector_ids,
                embeddings=[
                    item.embedding for item in embedded.chunks
                ],
                documents=[
                    item.chunk.text for item in embedded.chunks
                ],
                metadatas=[
                    self._build_vector_metadata(
                        knowledge_base_id=knowledge_base_id,
                        document_id=document.id,
                        original_name=resolved_original_name,
                        content_version=document.content_version,
                        chunk=item.chunk,
                    )
                    for item in embedded.chunks
                ],
            )

            mysql_chunks = [
                KnowledgeChunk(
                    knowledge_base_id=knowledge_base_id,
                    document_id=document.id,
                    chunk_index=item.chunk.index,
                    vector_id=vector_id,
                    content_hash=self._hash_text(item.chunk.text),
                    content_text=item.chunk.text,
                    char_count=item.chunk.char_count,
                    token_estimate=None,
                    priority=priority,
                    metadata_json={
                        "source_name": resolved_original_name,
                        "source_extension": path.suffix.lower(),
                        "start_char": item.chunk.start_char,
                        "end_char": item.chunk.end_char,
                        "content_version": document.content_version,
                    },
                )
                for item, vector_id in zip(
                    embedded.chunks,
                    vector_ids,
                    strict=True,
                )
            ]

            self.repository.add_chunks(mysql_chunks)
            self.repository.mark_document_ready(
                document,
                chunk_count=embedded.chunk_count,
            )
            self.repository.commit()

            return KnowledgeIngestionResult(
                knowledge_base_id=knowledge_base_id,
                document_id=document.id,
                original_name=resolved_original_name,
                stored_name=resolved_stored_name,
                chunk_count=embedded.chunk_count,
                vector_ids=tuple(vector_ids),
                embedding_dimension=embedded.embedding_dimension,
                status="ready",
            )
        except Exception as exc:
            self.repository.rollback()

            if vector_ids:
                try:
                    self.vector_store.delete(ids=vector_ids)
                except Exception:
                    pass

            try:
                self.repository.mark_document_failed(
                    document.id,
                    error_message=f"{type(exc).__name__}: {exc}",
                )
                self.repository.commit()
            except Exception:
                self.repository.rollback()

            raise KnowledgeIngestionError(
                f"文档入库失败：{resolved_original_name}：{exc}"
            ) from exc

    def search(
        self,
        query: str,
        *,
        knowledge_base_id: int,
        top_k: int | None = None,
        similarity_threshold: float | None = None,
    ) -> list[KnowledgeSearchHit]:
        """在显式指定的单个知识库内检索。"""
        normalized_query = self._normalize_search_query(query)
        self.repository.get_active_base(knowledge_base_id)

        resolved_top_k, threshold = self._resolve_search_options(
            top_k=top_k,
            similarity_threshold=similarity_threshold,
        )
        query_embedding = self.embedding_service.embed_text(
            normalized_query
        )

        return self._search_with_embedding(
            query_embedding=query_embedding,
            top_k=resolved_top_k,
            similarity_threshold=threshold,
            knowledge_base_id=knowledge_base_id,
        )


    def search_any(
        self,
        query: str,
        *,
        top_k: int | None = None,
        similarity_threshold: float | None = None,
    ) -> list[KnowledgeSearchHit]:
        """
        跨全部有效知识库检索。

        保留该方法用于兼容已有调用；未绑定知识库的正式问答流程
        使用 route_and_search()，先选知识库再在库内执行最终 Top-K。
        """
        normalized_query = self._normalize_search_query(query)
        resolved_top_k, threshold = self._resolve_search_options(
            top_k=top_k,
            similarity_threshold=similarity_threshold,
        )
        query_embedding = self.embedding_service.embed_text(
            normalized_query
        )

        return self._search_with_embedding(
            query_embedding=query_embedding,
            top_k=resolved_top_k,
            similarity_threshold=threshold,
            knowledge_base_id=None,
        )

    def route_and_search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        similarity_threshold: float | None = None,
        route_probe_top_k: int | None = None,
        route_similarity_threshold: float | None = None,
    ) -> KnowledgeRoutingResult:
        """
        自动选择最相关知识库，再只在该知识库中执行最终检索。

        设计目标：
        1. Query Embedding 只计算一次；
        2. 第一轮 Chroma Probe 跨全部知识库获取候选；
        3. 按知识库聚合 Top-3 相似度，降低单个偶然高分 Chunk 的误路由；
        4. 第二轮用同一个 query embedding 只检索获胜知识库；
        5. 最终回答的全部来源天然来自同一知识库，避免业务规则串库。
        """
        normalized_query = self._normalize_search_query(query)
        resolved_top_k, retrieval_threshold = (
            self._resolve_search_options(
                top_k=top_k,
                similarity_threshold=similarity_threshold,
            )
        )

        probe_top_k = (
            self.settings.rag_route_probe_top_k
            if route_probe_top_k is None
            else route_probe_top_k
        )
        route_threshold = (
            self.settings.rag_route_similarity_threshold
            if route_similarity_threshold is None
            else route_similarity_threshold
        )

        if probe_top_k <= 0:
            raise ValueError("route_probe_top_k 必须大于 0")
        if not 0.0 <= route_threshold <= 1.0:
            raise ValueError(
                "route_similarity_threshold 必须在 0 到 1 之间"
            )

        query_embedding = self.embedding_service.embed_text(
            normalized_query
        )

        probe_results = self.vector_store.query(
            query_embedding=query_embedding,
            top_k=probe_top_k,
        )
        probe_hits = self._results_to_hits(
            [
                item
                for item in probe_results
                if item.similarity >= route_threshold
            ]
        )

        candidates = self._build_route_candidates(probe_hits)
        if not candidates:
            return KnowledgeRoutingResult(
                knowledge_base_id=None,
                route_score=None,
                candidates=(),
                hits=(),
            )

        # 优先使用知识库管理页维护的 routing_description。
        # 例如：
        #   退款库：退款、到账、原路退回
        #   物流库：物流、配送、快递、签收
        #
        # 只有当前问题显式命中路由关键词时才提升该知识库；
        # 未命中任何路由关键词时仍完全沿用原向量路由评分。
        candidates = self._prioritize_route_metadata(
            normalized_query,
            candidates,
        )

        selected = candidates[0]

        final_hits = self._search_with_embedding(
            query_embedding=query_embedding,
            top_k=resolved_top_k,
            similarity_threshold=retrieval_threshold,
            knowledge_base_id=selected.knowledge_base_id,
        )

        return KnowledgeRoutingResult(
            knowledge_base_id=selected.knowledge_base_id,
            route_score=selected.score,
            candidates=tuple(candidates),
            hits=tuple(final_hits),
        )

    def _prioritize_route_metadata(
        self,
        query: str,
        candidates: list[KnowledgeRouteCandidate],
    ) -> list[KnowledgeRouteCandidate]:
        """
        用知识库 routing_description 修正“业务相近但知识库不同”的误路由。

        设计原则：
        1. routing_description 是管理员显式配置的路由元数据，优先级高于
           单个 Chunk 的偶然相似度；
        2. 只在 query 确实包含至少一个业务路由关键词时生效；
        3. 没有任何关键词命中时，保持原有纯向量排序；
        4. 最终回答仍必须通过该知识库内的正式 similarity_threshold，
           所以路由命中不会绕过 RAG 的安全阈值。
        """
        if not candidates:
            return candidates

        profiles = self.repository.get_active_bases_by_ids(
            [
                item.knowledge_base_id
                for item in candidates
            ]
        )

        match_counts: dict[int, int] = {}
        for candidate in candidates:
            knowledge_base = profiles.get(
                candidate.knowledge_base_id
            )
            routing_description = (
                getattr(
                    knowledge_base,
                    "routing_description",
                    None,
                )
                if knowledge_base is not None
                else None
            )
            match_counts[candidate.knowledge_base_id] = (
                self._routing_keyword_match_count(
                    query,
                    routing_description,
                )
            )

        if not any(match_counts.values()):
            return candidates

        return sorted(
            candidates,
            key=lambda item: (
                match_counts.get(
                    item.knowledge_base_id,
                    0,
                ),
                item.score,
                item.top_similarity,
                item.matched_chunks,
                -item.knowledge_base_id,
            ),
            reverse=True,
        )

    @staticmethod
    def _routing_keyword_match_count(
        query: str,
        routing_description: str | None,
    ) -> int:
        if not routing_description:
            return 0

        normalized_query = re.sub(
            r"\s+",
            "",
            query.strip().casefold(),
        )
        if not normalized_query:
            return 0

        # routing_description 采用：
        # “物流、配送、快递、签收” 这类人工维护关键词列表。
        raw_terms = re.split(
            r"[,，、;；|/\\\\\\s]+",
            routing_description.casefold(),
        )

        # 过滤过于宽泛、几乎每个客服知识库都会出现的词，避免错误提权。
        generic_terms = {
            "客服",
            "人工客服",
            "政策",
            "知识库",
            "服务",
            "问题",
            "处理",
            "说明",
        }

        matched: set[str] = set()
        for raw_term in raw_terms:
            term = re.sub(r"\s+", "", raw_term).strip()
            if len(term) < 2:
                continue
            if term in generic_terms:
                continue
            if term in normalized_query:
                matched.add(term)

        return len(matched)

    @staticmethod
    def _build_route_candidates(
        hits: list[KnowledgeSearchHit],
    ) -> list[KnowledgeRouteCandidate]:
        grouped: dict[int, list[KnowledgeSearchHit]] = {}

        for hit in hits:
            grouped.setdefault(
                hit.knowledge_base_id,
                [],
            ).append(hit)

        candidates: list[KnowledgeRouteCandidate] = []

        # 对每个知识库最多看前三个高相似度 Chunk：
        # 70% / 20% / 10%，不足三条时按现有权重重新归一化。
        base_weights = (0.7, 0.2, 0.1)

        for knowledge_base_id, items in grouped.items():
            ranked = sorted(
                items,
                key=lambda item: (
                    item.similarity,
                    item.priority,
                    -item.chunk_index,
                ),
                reverse=True,
            )
            top_items = ranked[:3]
            weights = base_weights[: len(top_items)]
            weight_sum = sum(weights)

            weighted_similarity = sum(
                item.similarity * weight
                for item, weight in zip(
                    top_items,
                    weights,
                    strict=True,
                )
            ) / weight_sum

            # 多条相互印证的 Chunk 比单条偶然高相似度更可信；
            # 支持度只做轻量修正，不覆盖语义相似度本身。
            support_factor = 0.92 + (
                0.04 * min(len(top_items) - 1, 2)
            )
            score = weighted_similarity * support_factor

            candidates.append(
                KnowledgeRouteCandidate(
                    knowledge_base_id=knowledge_base_id,
                    score=score,
                    top_similarity=top_items[0].similarity,
                    matched_chunks=len(items),
                )
            )

        candidates.sort(
            key=lambda item: (
                item.score,
                item.top_similarity,
                item.matched_chunks,
                -item.knowledge_base_id,
            ),
            reverse=True,
        )
        return candidates

    def _search_with_embedding(
        self,
        *,
        query_embedding: list[float],
        top_k: int,
        similarity_threshold: float,
        knowledge_base_id: int | None,
    ) -> list[KnowledgeSearchHit]:
        where = (
            {"knowledge_base_id": knowledge_base_id}
            if knowledge_base_id is not None
            else None
        )
        vector_results = self.vector_store.query(
            query_embedding=query_embedding,
            top_k=top_k,
            where=where,
        )

        return self._results_to_hits(
            [
                item
                for item in vector_results
                if item.similarity >= similarity_threshold
            ]
        )

    def _results_to_hits(
        self,
        vector_results: list[SearchResult],
    ) -> list[KnowledgeSearchHit]:
        if not vector_results:
            return []

        records = (
            self.repository.get_retrievable_chunks_by_vector_ids(
                [item.id for item in vector_results]
            )
        )

        hits: list[KnowledgeSearchHit] = []
        for result in vector_results:
            record = records.get(result.id)
            if record is None:
                continue

            chunk, document = record
            hits.append(
                KnowledgeSearchHit(
                    vector_id=result.id,
                    knowledge_base_id=chunk.knowledge_base_id,
                    document_id=document.id,
                    document_name=document.original_name,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content_text,
                    similarity=result.similarity,
                    distance=result.distance,
                    metadata=dict(result.metadata),
                    chunk_id=chunk.id,
                    priority=int(chunk.priority or 0),
                )
            )

        return hits

    def _resolve_search_options(
        self,
        *,
        top_k: int | None,
        similarity_threshold: float | None,
    ) -> tuple[int, float]:
        resolved_top_k = top_k or self.settings.rag_top_k
        threshold = (
            self.settings.rag_similarity_threshold
            if similarity_threshold is None
            else similarity_threshold
        )

        if resolved_top_k <= 0:
            raise ValueError("top_k 必须大于 0")
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(
                "similarity_threshold 必须在 0 到 1 之间"
            )

        return resolved_top_k, threshold

    @staticmethod
    def _normalize_search_query(query: str) -> str:
        normalized = query.strip()
        if not normalized:
            raise ValueError("检索问题不能为空")
        return normalized

    def delete_document(self, document_id: int) -> None:
        document = self.repository.get_document_for_delete(document_id)
        chunks = self.repository.get_document_chunks(document_id)
        vector_ids = [chunk.vector_id for chunk in chunks]

        backup: dict[str, Any] | None = None
        if vector_ids:
            backup = self.vector_store.get(vector_ids)
            self.vector_store.delete(ids=vector_ids)

        try:
            self.repository.soft_delete_document(document)
            self.repository.commit()
        except Exception:
            self.repository.rollback()
            if backup is not None:
                self._restore_chroma_backup(backup)
            raise

    def _restore_chroma_backup(self, backup: dict[str, Any]) -> None:
        ids = list(backup.get("ids") or [])
        documents = list(backup.get("documents") or [])
        metadatas = list(backup.get("metadatas") or [])
        embeddings = backup.get("embeddings")

        if embeddings is None:
            raise KnowledgeIngestionError(
                "Chroma 删除补偿失败：备份缺少 embeddings"
            )
        embeddings_list = list(embeddings)

        if not ids:
            return

        self.vector_store.upsert(
            ids=ids,
            embeddings=embeddings_list,
            documents=documents,
            metadatas=metadatas,
        )

    def _validate_source_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            raise ValueError(f"文件不存在：{path}")

        extension = path.suffix.lower()
        if extension not in self.settings.allowed_document_extensions:
            raise ValueError(f"不支持的文档类型：{extension or '无扩展名'}")

        max_bytes = self.settings.max_upload_size_mb * 1024 * 1024
        if path.stat().st_size > max_bytes:
            raise ValueError(
                f"文件超过 {self.settings.max_upload_size_mb} MB 限制"
            )

    @staticmethod
    def _build_vector_ids(
        *,
        knowledge_base_id: int,
        document_id: int,
        content_version: int,
        embedded: EmbeddedDocument,
    ) -> list[str]:
        return [
            (
                f"kb{knowledge_base_id}:doc{document_id}:"
                f"v{content_version}:chunk{item.chunk.index}"
            )
            for item in embedded.chunks
        ]

    @staticmethod
    def _build_vector_metadata(
        *,
        knowledge_base_id: int,
        document_id: int,
        original_name: str,
        content_version: int,
        chunk: Any,
    ) -> dict[str, str | int]:
        return {
            "knowledge_base_id": knowledge_base_id,
            "document_id": document_id,
            "file_name": original_name,
            "chunk_index": chunk.index,
            "content_version": content_version,
            "start_char": chunk.start_char,
            "end_char": chunk.end_char,
        }

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _hash_text(text: str) -> str:
        return sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _guess_mime_type(extension: str) -> str | None:
        explicit = {
            ".txt": "text/plain",
            ".md": "text/markdown",
            ".pdf": "application/pdf",
        }
        return explicit.get(extension) or mimetypes.types_map.get(extension)
