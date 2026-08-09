from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Sequence

from app.services.llm.chat_service import LLMMessage


_CITATION_PATTERN = re.compile(r"\[来源(\d+)\]")


@dataclass(frozen=True)
class AnswerEvidenceValidation:
    valid: bool
    cited_ranks: tuple[int, ...]
    missing_required_ranks: tuple[int, ...]


class AnswerEvidenceGuard:
    """
    生成后的证据覆盖校验。

    Prompt 的 A 层规则被标记为 required source。模型若在答案中完全
    忽略这些来源，说明存在注意力稀释风险；系统会先进行一次受约束
    修复，仍失败则退回安全兜底，而不是把不完整业务结论直接返回。
    """

    def validate(
        self,
        content: str,
        *,
        required_source_ranks: Sequence[int],
    ) -> AnswerEvidenceValidation:
        cited = tuple(
            sorted(
                {
                    int(value)
                    for value in _CITATION_PATTERN.findall(
                        content
                    )
                    if int(value) > 0
                }
            )
        )
        required = tuple(
            sorted(
                {
                    int(value)
                    for value in required_source_ranks
                    if int(value) > 0
                }
            )
        )
        missing = tuple(
            rank for rank in required if rank not in cited
        )
        return AnswerEvidenceValidation(
            valid=not missing,
            cited_ranks=cited,
            missing_required_ranks=missing,
        )

    @staticmethod
    def build_repair_messages(
        *,
        original_messages: Sequence[LLMMessage],
        draft: str,
        missing_required_ranks: Sequence[int],
    ) -> tuple[LLMMessage, ...]:
        missing = ", ".join(
            f"[来源{rank}]"
            for rank in missing_required_ranks
        )
        instruction = (
            "上一个回答草稿遗漏了 A 层关键业务规则的证据引用："
            f"{missing}。请重新生成完整答案。\n"
            "要求：\n"
            "1. 必须遵守并覆盖这些 A 层规则；\n"
            "2. 涉及对应事实时必须引用上述来源；\n"
            "3. 不得增加知识库中不存在的新规则；\n"
            "4. 若证据互相冲突或仍不足，请只输出 "
            "[[NO_RELIABLE_ANSWER]]；\n"
            "5. 只输出修正后的最终客服回答，不输出检查过程。"
        )
        return tuple(original_messages) + (
            LLMMessage(role="assistant", content=draft),
            LLMMessage(role="user", content=instruction),
        )
