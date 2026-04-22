"""
工具抽象基础类型

灵感来源：Claude Code 的 Tool.ts
- 工具不只是函数，而是带元数据的策略对象
- 每个工具声明：做什么（description），需要什么（input_schema），
  能否并行（is_parallel_safe），被中断时怎么处理，输出上限多少
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class InterruptBehavior(str, Enum):
    CANCEL = "cancel"
    BLOCK = "block"


@dataclass
class ToolResult:
    """标准化工具执行结果"""
    tool_name: str
    success: bool
    output: Any = None
    error: Optional[str] = None
    output_chars: int = 0
    was_truncated: bool = False
    metadata: dict = field(default_factory=dict)

    def to_message_content(self, max_chars: int = 0) -> str:
        """Serialize for inclusion in LLM message history."""
        if self.error:
            return f"[TOOL_ERROR: {self.tool_name}] {self.error}"
        text = str(self.output) if self.output is not None else ""
        if max_chars and len(text) > max_chars:
            text = text[:max_chars] + f"\n... (truncated, {len(text)} total chars)"
        return f"[TOOL_RESULT: {self.tool_name}]\n{text}\n[/TOOL_RESULT]"


@dataclass
class ToolCall:
    """A parsed tool invocation request."""
    tool_name: str
    arguments: dict = field(default_factory=dict)
    call_id: str = ""


@dataclass
class ToolContext:
    """
    共享运行时上下文，传入每次工具调用

    类似 Claude Code 的 ToolUseContext：持有 abort 信号、缓存、消息列表等。
    """
    workflow_id: str = ""
    round: int = 0
    abort: bool = False
    shared_state: dict = field(default_factory=dict)


class ToolSpec(ABC):
    """
    工具规约基类

    子类必须实现 execute()。元数据字段用于：
    - description: 给 LLM 决定是否调用
    - input_schema: 参数校验
    - is_parallel_safe: 调度器判断可否并行
    - interrupt_behavior: 中断策略
    - max_output_chars: 输出截断上限
    """
    name: str = ""
    description: str = ""
    input_schema: dict = {}
    is_parallel_safe: bool = True
    is_read_only: bool = False
    interrupt_behavior: InterruptBehavior = InterruptBehavior.CANCEL
    max_output_chars: int = 10000
    timeout_seconds: int = 60

    @abstractmethod
    def execute(self, args: dict, context: ToolContext) -> ToolResult:
        """同步执行工具"""
        ...

    async def execute_async(self, args: dict, context: ToolContext) -> ToolResult:
        """异步执行（默认包装同步版本）"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.execute, args, context)

    def validate_input(self, args: dict) -> Optional[str]:
        """
        Validate input arguments. Returns error message or None if valid.
        Override for custom validation.
        """
        return None

    def to_llm_schema(self) -> dict:
        """Export as OpenAI function-calling schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema or {"type": "object", "properties": {}},
            },
        }
