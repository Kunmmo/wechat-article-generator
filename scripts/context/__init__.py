"""
上下文窗口管理

借鉴 Claude Code 的三层压缩机制：
- MicroCompact: 裁剪旧工具结果（轻量）
- AutoCompact: 阈值触发 LLM 摘要（中量）
- FullCompact: 完整重写 + 后置附件（重量）
"""

from .manager import ContextManager, Message

__all__ = ["ContextManager", "Message"]
