"""
上下文窗口管理器

三层压缩策略，灵感来源：
- Claude Code autoCompact.ts: 阈值计算 = effectiveWindow - buffer
- Claude Code compact.ts: LLM 摘要 + buildPostCompactMessages 重建
- Claude Code microCompact.ts: 仅对 COMPACTABLE 类型的工具结果做裁剪

设计约束：
1. 每层只在前一层不够时才触发（分级回收）
2. compact 后重新注入 post-compact attachments（工作流状态、Agent 提示等）
3. 断路器：连续 compact 失败 3 次后停止重试
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Optional, Callable

logger = logging.getLogger(__name__)

# Roles that can be compacted
COMPACTABLE_ROLES = {"tool_result", "assistant"}

# Tools whose outputs are safe to truncate during micro-compact
COMPACTABLE_TOOL_NAMES = {
    "web_search", "meme_retrieval", "evaluate_article",
    "image_generation",
}

CHARS_PER_TOKEN = 3.5


@dataclass
class Message:
    """
    对话消息

    role: "system" | "user" | "assistant" | "tool_result"
    """
    role: str
    content: str
    name: str = ""
    tool_call_id: str = ""
    metadata: dict = field(default_factory=dict)
    is_compact_boundary: bool = False

    @property
    def estimated_tokens(self) -> int:
        return max(1, int(len(self.content) / CHARS_PER_TOKEN))


@dataclass
class CompactMetadata:
    """State preserved across compactions."""
    original_message_count: int = 0
    compact_count: int = 0
    tokens_freed: int = 0
    preserved_state: dict = field(default_factory=dict)


class ContextManager:
    """
    三层上下文压缩管理器

    使用方法:
        cm = ContextManager(max_tokens=120000)
        messages = cm.compress_if_needed(messages)
    """

    def __init__(self,
                 max_tokens: int = 120000,
                 buffer_tokens: int = 13000,
                 micro_compact_keep_chars: int = 200,
                 micro_compact_age_threshold: int = 6,
                 summarizer: Optional[Callable[[list[Message]], str]] = None):
        self.max_tokens = max_tokens
        self.buffer_tokens = buffer_tokens
        self.compact_threshold = max_tokens - buffer_tokens
        self.micro_keep_chars = micro_compact_keep_chars
        self.micro_age_threshold = micro_compact_age_threshold
        self._summarizer = summarizer

        # Circuit breaker for auto-compact
        self._consecutive_failures = 0
        self._max_failures = 3
        self._metadata = CompactMetadata()

    def estimate_tokens(self, messages: list[Message]) -> int:
        """Estimate total token count for a message list."""
        return sum(m.estimated_tokens for m in messages)

    def compress_if_needed(self, messages: list[Message],
                           post_compact_attachments: Optional[list[Message]] = None,
                           ) -> list[Message]:
        """
        Apply graduated compression if token count approaches threshold.

        Layer 1: Micro-compact — trim old tool results in-place
        Layer 2: Auto-compact — LLM-summarize older turns, keep recent context
        """
        tokens = self.estimate_tokens(messages)

        if tokens < self.compact_threshold * 0.8:
            return messages

        logger.info(f"Context pressure: {tokens}/{self.compact_threshold} tokens, starting compression")

        # Layer 1: Micro-compact
        messages = self._micro_compact(messages)
        tokens = self.estimate_tokens(messages)

        if tokens < self.compact_threshold:
            logger.info(f"Micro-compact sufficient: {tokens} tokens remaining")
            return messages

        # Layer 2: Auto-compact (LLM summary)
        if self._consecutive_failures >= self._max_failures:
            logger.warning("Auto-compact circuit breaker open, skipping")
            return messages

        messages = self._auto_compact(messages, post_compact_attachments)
        return messages

    def _micro_compact(self, messages: list[Message]) -> list[Message]:
        """
        Layer 1: Trim old tool results to a preview.

        Only affects messages older than `micro_age_threshold` turns
        and with compactable tool names.

        灵感: Claude Code microCompact.ts — COMPACTABLE_TOOLS + time-based clearing
        """
        total = len(messages)
        if total <= self.micro_age_threshold:
            return messages

        cutoff = total - self.micro_age_threshold
        result = []

        for i, msg in enumerate(messages):
            if i < cutoff and self._is_compactable_message(msg):
                truncated = self._truncate_content(msg.content, self.micro_keep_chars)
                if len(truncated) < len(msg.content):
                    new_msg = Message(
                        role=msg.role,
                        content=truncated,
                        name=msg.name,
                        tool_call_id=msg.tool_call_id,
                        metadata={**msg.metadata, "micro_compacted": True},
                    )
                    result.append(new_msg)
                    continue
            result.append(msg)

        freed = self.estimate_tokens(messages) - self.estimate_tokens(result)
        if freed > 0:
            logger.info(f"Micro-compact freed ~{freed} tokens from {cutoff} old messages")
            self._metadata.tokens_freed += freed

        return result

    def _auto_compact(self, messages: list[Message],
                      attachments: Optional[list[Message]] = None) -> list[Message]:
        """
        Layer 2: LLM-summarize the first 70% of conversation, keep recent 30%.

        灵感: Claude Code compact.ts — compactConversation + buildPostCompactMessages
        """
        split_point = int(len(messages) * 0.7)
        if split_point < 2:
            return messages

        older = messages[:split_point]
        recent = messages[split_point:]

        summary_text = self._generate_summary(older)

        if summary_text is None:
            self._consecutive_failures += 1
            logger.warning(f"Auto-compact failed ({self._consecutive_failures}/{self._max_failures})")
            return messages

        self._consecutive_failures = 0
        self._metadata.compact_count += 1
        self._metadata.original_message_count = len(messages)

        # Build post-compact message sequence (mirrors buildPostCompactMessages)
        boundary = Message(
            role="system",
            content="[COMPACT_BOUNDARY] The conversation above has been summarized.",
            is_compact_boundary=True,
            metadata={
                "compact_count": self._metadata.compact_count,
                "original_messages": len(older),
            },
        )

        summary_msg = Message(
            role="user",
            content=f"[CONVERSATION_SUMMARY]\n{summary_text}\n[/CONVERSATION_SUMMARY]",
            metadata={"is_summary": True},
        )

        result = [boundary, summary_msg] + recent

        if attachments:
            result.extend(attachments)

        freed = self.estimate_tokens(messages) - self.estimate_tokens(result)
        logger.info(f"Auto-compact: {len(older)} messages → summary, freed ~{freed} tokens")
        self._metadata.tokens_freed += freed

        return result

    def _generate_summary(self, messages: list[Message]) -> Optional[str]:
        """Generate a text summary of a message list."""
        if self._summarizer:
            try:
                return self._summarizer(messages)
            except Exception as e:
                logger.error(f"Custom summarizer failed: {e}")
                return None

        # Fallback: extractive summary (no LLM call needed)
        return self._extractive_summary(messages)

    def _extractive_summary(self, messages: list[Message]) -> str:
        """Simple extractive summary: keep first/last line of each message."""
        parts = []
        for msg in messages:
            if msg.role == "system":
                continue
            lines = msg.content.strip().split('\n')
            if len(lines) <= 3:
                parts.append(f"[{msg.role}] {msg.content.strip()}")
            else:
                preview = lines[0] + " ... " + lines[-1]
                parts.append(f"[{msg.role}] {preview}")

        return "\n".join(parts[-20:])  # Keep last 20 entries max

    def _is_compactable_message(self, msg: Message) -> bool:
        """Check if a message's content can be safely truncated."""
        if msg.role == "system":
            return False
        if msg.is_compact_boundary:
            return False
        tool_name = msg.metadata.get("tool_name", msg.name)
        if tool_name and tool_name in COMPACTABLE_TOOL_NAMES:
            return True
        if msg.role == "tool_result":
            return True
        return False

    def _truncate_content(self, content: str, keep_chars: int) -> str:
        """Truncate content to a preview, preserving structure markers."""
        if len(content) <= keep_chars:
            return content

        # Try to preserve structured tags
        tag_match = re.match(r'(\[TOOL_RESULT:[^\]]*\]\n)', content)
        prefix = tag_match.group(1) if tag_match else ""

        remaining = keep_chars - len(prefix)
        if remaining <= 0:
            return content[:keep_chars] + "\n... (truncated)"

        body = content[len(prefix):]
        return prefix + body[:remaining] + f"\n... (truncated, {len(content)} total chars)"

    def set_summarizer(self, fn: Callable[[list[Message]], str]):
        """Set a custom summarizer function (e.g. LLM-based)."""
        self._summarizer = fn

    @property
    def metadata(self) -> CompactMetadata:
        return self._metadata
