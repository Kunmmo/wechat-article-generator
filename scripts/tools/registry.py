"""
工具注册表

灵感来源：Claude Code 的 tools.ts
- getAllBaseTools(): 列举所有内置工具
- assembleToolPool(): 排序 + 去重 + MCP 合并
- 有序保证 prompt cache 稳定性
"""

from __future__ import annotations

from typing import Optional
from .base import ToolSpec


class ToolRegistry:
    """
    有序工具注册表

    注册顺序影响 LLM function-calling schema 的顺序，
    进而影响 prompt cache 命中率（参考 Claude Code assembleToolPool 注释）。
    """

    def __init__(self):
        self._tools: dict[str, ToolSpec] = {}
        self._order: list[str] = []

    def register(self, tool: ToolSpec):
        """注册一个工具（重复名称会覆盖）"""
        if tool.name not in self._tools:
            self._order.append(tool.name)
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[ToolSpec]:
        return self._tools.get(name)

    def list_tools(self) -> list[ToolSpec]:
        """按注册顺序返回所有工具"""
        return [self._tools[n] for n in self._order if n in self._tools]

    def list_names(self) -> list[str]:
        return list(self._order)

    def to_llm_schemas(self) -> list[dict]:
        """导出所有工具的 function-calling schema"""
        return [t.to_llm_schema() for t in self.list_tools()]

    def filter_by(self, read_only: Optional[bool] = None,
                  parallel_safe: Optional[bool] = None) -> list[ToolSpec]:
        """按属性过滤工具"""
        result = []
        for t in self.list_tools():
            if read_only is not None and t.is_read_only != read_only:
                continue
            if parallel_safe is not None and t.is_parallel_safe != parallel_safe:
                continue
            result.append(t)
        return result

    def __len__(self):
        return len(self._tools)

    def __contains__(self, name: str):
        return name in self._tools


def build_default_registry() -> ToolRegistry:
    """构建默认工具注册表，包含所有内置工具"""
    from .implementations import (
        MemeRetrievalTool,
        ImageGenerationTool,
        EvaluationTool,
        WebSearchTool,
        AgentCallTool,
    )

    registry = ToolRegistry()
    registry.register(WebSearchTool())
    registry.register(MemeRetrievalTool())
    registry.register(ImageGenerationTool())
    registry.register(EvaluationTool())
    registry.register(AgentCallTool())
    return registry
