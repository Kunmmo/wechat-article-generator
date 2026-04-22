"""
工具执行器

灵感来源：Claude Code 的 StreamingToolExecutor.ts
- 并发安全的工具可并行运行
- 非安全工具（如 AgentCall）阻塞队列
- 支持超时和取消
- Bash 出错时通过 sibling abort 取消同批任务（简化版）
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from .base import ToolSpec, ToolCall, ToolResult, ToolContext
from .registry import ToolRegistry

logger = logging.getLogger(__name__)


class ToolExecutor:
    """
    混合并行/串行工具执行器

    安全工具（is_parallel_safe=True）通过 asyncio.gather 并发执行。
    非安全工具按顺序串行执行。同批中如果有非安全工具，
    非安全工具在所有安全工具完成后再执行。
    """

    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    async def execute_batch(self, calls: list[ToolCall],
                            context: ToolContext) -> list[ToolResult]:
        """
        Execute a batch of tool calls with parallel/serial partitioning.

        Returns results in the same order as input calls.
        """
        if not calls:
            return []

        safe_calls = []
        unsafe_calls = []
        for call in calls:
            tool = self.registry.get(call.tool_name)
            if tool and tool.is_parallel_safe:
                safe_calls.append(call)
            else:
                unsafe_calls.append(call)

        results_map: dict[int, ToolResult] = {}

        # Phase 1: Run all safe tools concurrently
        if safe_calls:
            safe_indices = [calls.index(c) for c in safe_calls]
            safe_results = await asyncio.gather(
                *[self._execute_one(c, context) for c in safe_calls],
                return_exceptions=True,
            )
            for idx, result in zip(safe_indices, safe_results):
                if isinstance(result, Exception):
                    call = calls[idx]
                    results_map[idx] = ToolResult(
                        tool_name=call.tool_name, success=False,
                        error=str(result),
                    )
                else:
                    results_map[idx] = result

        # Phase 2: Run unsafe tools sequentially
        for call in unsafe_calls:
            if context.abort:
                idx = calls.index(call)
                results_map[idx] = ToolResult(
                    tool_name=call.tool_name, success=False,
                    error="Aborted",
                )
                continue

            idx = calls.index(call)
            try:
                results_map[idx] = await self._execute_one(call, context)
            except Exception as e:
                results_map[idx] = ToolResult(
                    tool_name=call.tool_name, success=False,
                    error=str(e),
                )

        return [results_map[i] for i in range(len(calls))]

    async def _execute_one(self, call: ToolCall, context: ToolContext) -> ToolResult:
        """Execute a single tool call with timeout."""
        tool = self.registry.get(call.tool_name)
        if not tool:
            return ToolResult(
                tool_name=call.tool_name, success=False,
                error=f"Unknown tool: {call.tool_name}",
            )

        validation_error = tool.validate_input(call.arguments)
        if validation_error:
            return ToolResult(
                tool_name=call.tool_name, success=False,
                error=f"Input validation failed: {validation_error}",
            )

        try:
            result = await asyncio.wait_for(
                tool.execute_async(call.arguments, context),
                timeout=tool.timeout_seconds,
            )
            # Truncate output if needed
            if result.output and tool.max_output_chars:
                text = str(result.output)
                if len(text) > tool.max_output_chars:
                    result.output = text[:tool.max_output_chars]
                    result.was_truncated = True
                    result.output_chars = len(text)
            return result
        except asyncio.TimeoutError:
            return ToolResult(
                tool_name=call.tool_name, success=False,
                error=f"Timeout after {tool.timeout_seconds}s",
            )

    def execute_batch_sync(self, calls: list[ToolCall],
                           context: ToolContext) -> list[ToolResult]:
        """Synchronous wrapper for execute_batch."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, self.execute_batch(calls, context))
                return future.result()
        else:
            return asyncio.run(self.execute_batch(calls, context))
