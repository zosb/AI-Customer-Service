from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Protocol, Sequence


class KnowledgeEvidenceHit(Protocol):
    vector_id: str
    knowledge_base_id: int
    document_id: int
    document_name: str
    chunk_index: int
    content: str
    similarity: float
    distance: float
    chunk_id: int | None
    priority: int


_RULE_CUES: tuple[str, ...] = (
    "必须",
    "不得",
    "禁止",
    "只能",
    "仅限",
    "至少",
    "最多",
    "不超过",
    "应当",
    "需要",
    "如果",
    "若",
    "否则",
    "除非",
    "例外",
)

_HARD_RULE_CUES: tuple[str, ...] = (
    "必须",
    "不得",
    "禁止",
    "只能",
    "仅限",
    "至少",
    "最多",
    "不超过",
    "应当",
    "如果",
    "若",
    "否则",
    "除非",
    "例外",
)


@dataclass(frozen=True)
class GuardedEvidence:
    hit: KnowledgeEvidenceHit
    content: str
    tier: str
    required: bool
    score: float
    rule_sentence_count: int


@dataclass(frozen=True)
class EvidencePlan:
    evidence: tuple[GuardedEvidence, ...]
    input_hits: int
    deduplicated_hits: int
    selected_sources: int
    dropped_hits: int
    required_sources: int
    selected_content_chars: int


class LargeContextGuard:
    """
    大规模检索结果的确定性上下文治理器。

    它不再把几十个 Chunk 原样塞给 LLM，而是先完成：
    1. 近重复 Chunk 去重；
    2. 同文档 Chunk 数量上限；
    3. 规则句 / 问题相关句抽取；
    4. 高优先级规则进入 A 层；
    5. 直接证据进入 B 层；
    6. 按来源数量与字符预算截断。

    这里刻意使用确定性规则，而不是再调用一个 LLM 摘要器，避免在
    "摘要阶段"本身引入新的幻觉和额外模型依赖。
    """

    def __init__(
        self,
        *,
        max_context_chars: int,
        max_sources: int,
        max_chunks_per_document: int,
        critical_priority: int,
        critical_source_limit: int,
        rule_sentences_per_source: int,
        support_sentences_per_source: int,
    ) -> None:
        self.max_context_chars = max_context_chars
        self.max_sources = max_sources
        self.max_chunks_per_document = max_chunks_per_document
        self.critical_priority = critical_priority
        self.critical_source_limit = critical_source_limit
        self.rule_sentences_per_source = rule_sentences_per_source
        self.support_sentences_per_source = (
            support_sentences_per_source
        )

        positive_values = {
            "max_context_chars": max_context_chars,
            "max_sources": max_sources,
            "max_chunks_per_document": max_chunks_per_document,
            "critical_source_limit": critical_source_limit,
            "rule_sentences_per_source": rule_sentences_per_source,
            "support_sentences_per_source": (
                support_sentences_per_source
            ),
        }
        for name, value in positive_values.items():
            if value <= 0:
                raise ValueError(f"{name} 必须大于 0")
        if critical_priority < 0:
            raise ValueError("critical_priority 不能小于 0")

    def plan(
        self,
        *,
        question: str,
        hits: Sequence[KnowledgeEvidenceHit],
    ) -> EvidencePlan:
        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("用户问题不能为空")
        if not hits:
            raise ValueError("hits 不能为空")

        deduplicated = self._deduplicate_hits(hits)
        capped = self._cap_per_document(deduplicated)
        query_terms = self._query_terms(normalized_question)

        candidates = [
            self._build_candidate(
                hit=hit,
                query_terms=query_terms,
            )
            for hit in capped
        ]
        candidates = [
            item for item in candidates if item.content.strip()
        ]

        if not candidates:
            return EvidencePlan(
                evidence=(),
                input_hits=len(hits),
                deduplicated_hits=len(deduplicated),
                selected_sources=0,
                dropped_hits=len(hits),
                required_sources=0,
                selected_content_chars=0,
            )

        # A 层先进入 Prompt，确保强制规则不会因为后面大量高相似度
        # 普通材料而被挤出上下文窗口。
        critical = sorted(
            (item for item in candidates if item.required),
            key=self._candidate_sort_key,
            reverse=True,
        )[: self.critical_source_limit]

        critical_keys = {
            self._hit_identity(item.hit)
            for item in critical
        }
        supporting_items: list[GuardedEvidence] = []
        for item in candidates:
            if self._hit_identity(item.hit) in critical_keys:
                continue
            # required source 过多本身也会制造新的注意力负担。
            # 超出 critical_source_limit 的规则保留为 B 层补充，
            # 但不再要求模型逐条强制覆盖。
            if item.required:
                item = GuardedEvidence(
                    hit=item.hit,
                    content=item.content,
                    tier="B",
                    required=False,
                    score=item.score,
                    rule_sentence_count=item.rule_sentence_count,
                )
            supporting_items.append(item)

        supporting = sorted(
            supporting_items,
            key=self._candidate_sort_key,
            reverse=True,
        )

        ordered = critical + supporting
        if not critical and ordered:
            # 没有显式强制规则时，至少要求最终回答引用最相关证据，
            # 防止模型在有检索结果时仍给出完全无来源的业务结论。
            first = ordered[0]
            ordered[0] = GuardedEvidence(
                hit=first.hit,
                content=first.content,
                tier="A",
                required=True,
                score=first.score,
                rule_sentence_count=first.rule_sentence_count,
            )

        selected: list[GuardedEvidence] = []
        used_chars = 0

        for item in ordered:
            if len(selected) >= self.max_sources:
                break

            remaining = self.max_context_chars - used_chars
            if remaining <= 0:
                break

            clipped = self._clip_text(item.content, remaining)
            if not clipped:
                continue

            selected_item = GuardedEvidence(
                hit=item.hit,
                content=clipped,
                tier=item.tier,
                required=item.required,
                score=item.score,
                rule_sentence_count=item.rule_sentence_count,
            )
            selected.append(selected_item)
            used_chars += len(clipped)

        return EvidencePlan(
            evidence=tuple(selected),
            input_hits=len(hits),
            deduplicated_hits=len(deduplicated),
            selected_sources=len(selected),
            dropped_hits=max(0, len(hits) - len(selected)),
            required_sources=sum(
                1 for item in selected if item.required
            ),
            selected_content_chars=used_chars,
        )

    def _build_candidate(
        self,
        *,
        hit: KnowledgeEvidenceHit,
        query_terms: set[str],
    ) -> GuardedEvidence:
        sentences = self._split_sentences(hit.content)
        if not sentences:
            return GuardedEvidence(
                hit=hit,
                content="",
                tier="B",
                required=False,
                score=float(hit.similarity),
                rule_sentence_count=0,
            )

        scored: list[tuple[float, str, bool, int]] = []
        for index, sentence in enumerate(sentences):
            normalized = sentence.strip()
            if not normalized:
                continue

            overlap = self._query_overlap(
                normalized,
                query_terms,
            )
            cue_count = sum(
                1 for cue in _RULE_CUES if cue in normalized
            )
            hard_rule = any(
                cue in normalized for cue in _HARD_RULE_CUES
            )

            sentence_score = (
                float(hit.priority) * 12.0
                + float(hit.similarity) * 10.0
                + min(overlap, 8) * 3.0
                + cue_count * 5.0
                - index * 0.01
            )
            scored.append(
                (
                    sentence_score,
                    normalized,
                    hard_rule,
                    overlap,
                )
            )

        if not scored:
            return GuardedEvidence(
                hit=hit,
                content="",
                tier="B",
                required=False,
                score=float(hit.similarity),
                rule_sentence_count=0,
            )

        rule_sentences = sorted(
            (item for item in scored if item[2]),
            key=lambda item: item[0],
            reverse=True,
        )[: self.rule_sentences_per_source]

        selected_texts = [item[1] for item in rule_sentences]
        selected_keys = {
            self._normalize_content(item) for item in selected_texts
        }

        support_sentences = sorted(
            (
                item
                for item in scored
                if self._normalize_content(item[1])
                not in selected_keys
            ),
            key=lambda item: item[0],
            reverse=True,
        )[: self.support_sentences_per_source]
        selected_texts.extend(item[1] for item in support_sentences)

        required = (
            int(hit.priority) >= self.critical_priority
            or any(
                item[2] and item[3] > 0
                for item in scored
            )
        )
        tier = "A" if required else "B"

        return GuardedEvidence(
            hit=hit,
            content=" ".join(selected_texts).strip(),
            tier=tier,
            required=required,
            score=max(item[0] for item in scored),
            rule_sentence_count=len(rule_sentences),
        )

    def _deduplicate_hits(
        self,
        hits: Sequence[KnowledgeEvidenceHit],
    ) -> list[KnowledgeEvidenceHit]:
        best: dict[str, KnowledgeEvidenceHit] = {}

        for hit in hits:
            key = self._normalize_content(hit.content)
            if not key:
                continue

            current = best.get(key)
            if current is None:
                best[key] = hit
                continue

            if self._hit_sort_key(hit) > self._hit_sort_key(
                current
            ):
                best[key] = hit

        return sorted(
            best.values(),
            key=self._hit_sort_key,
            reverse=True,
        )

    def _cap_per_document(
        self,
        hits: Sequence[KnowledgeEvidenceHit],
    ) -> list[KnowledgeEvidenceHit]:
        result: list[KnowledgeSearchHit] = []
        counts: dict[int, int] = {}

        for hit in hits:
            count = counts.get(hit.document_id, 0)
            if count >= self.max_chunks_per_document:
                continue
            counts[hit.document_id] = count + 1
            result.append(hit)

        return result

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        normalized = re.sub(r"\s+", " ", text.strip())
        if not normalized:
            return []

        parts = re.split(
            r"(?<=[。！？；!?;])\s*|\n+",
            normalized,
        )
        return [item.strip() for item in parts if item.strip()]

    @staticmethod
    def _query_terms(question: str) -> set[str]:
        lowered = question.casefold()
        terms = {
            item
            for item in re.findall(r"[a-z0-9_]{2,}", lowered)
        }
        chinese = "".join(
            re.findall(r"[\u4e00-\u9fff]", lowered)
        )
        for size in (2, 3, 4):
            for index in range(0, max(0, len(chinese) - size + 1)):
                terms.add(chinese[index : index + size])
        return terms

    @staticmethod
    def _query_overlap(
        sentence: str,
        terms: set[str],
    ) -> int:
        lowered = sentence.casefold()
        return sum(1 for term in terms if term in lowered)

    @staticmethod
    def _normalize_content(text: str) -> str:
        return re.sub(
            r"[\W_]+",
            "",
            text.casefold(),
            flags=re.UNICODE,
        )

    @staticmethod
    def _clip_text(text: str, limit: int) -> str:
        if limit <= 0:
            return ""
        if len(text) <= limit:
            return text.strip()

        clipped = text[:limit].rstrip()
        # 尽量在完整句号附近截断，避免把一条业务规则截成半句。
        sentence_end = max(
            clipped.rfind("。"),
            clipped.rfind("！"),
            clipped.rfind("？"),
            clipped.rfind("；"),
        )
        if sentence_end >= max(10, limit // 2):
            clipped = clipped[: sentence_end + 1]
        return clipped.strip()

    @staticmethod
    def _hit_sort_key(
        hit: KnowledgeEvidenceHit,
    ) -> tuple[int, float, int]:
        return (
            int(getattr(hit, "priority", 0) or 0),
            float(hit.similarity),
            -int(hit.chunk_index),
        )

    @staticmethod
    def _candidate_sort_key(
        item: GuardedEvidence,
    ) -> tuple[int, float, float, int]:
        return (
            int(item.required),
            float(item.hit.priority),
            float(item.score),
            -int(item.hit.chunk_index),
        )

    @staticmethod
    def _hit_identity(
        hit: KnowledgeEvidenceHit,
    ) -> tuple[int, int, str]:
        return (
            int(hit.document_id),
            int(hit.chunk_index),
            str(hit.vector_id),
        )
