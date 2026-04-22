"""
工具抽象层

借鉴 Claude Code 的 Tool.ts / StreamingToolExecutor.ts 设计：
- ToolSpec: 带元数据的策略对象（不只是函数），声明并发安全性、超时、输出上限
- ToolResult: 标准化结果容器
- ToolContext: 共享运行时上下文
- ToolRegistry: 有序工具注册表
- ToolExecutor: 并行 / 串行混合执行器
"""

from .base import ToolSpec, ToolResult, ToolContext, ToolCall
from .registry import ToolRegistry
from .executor import ToolExecutor

__all__ = [
    "ToolSpec", "ToolResult", "ToolContext", "ToolCall",
    "ToolRegistry", "ToolExecutor",
]
