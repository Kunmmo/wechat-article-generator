"""
循环式查询引擎

灵感来源：Claude Code 的 query.ts — 核心 Agent Loop

while (not_done) {
    context_management()   // 管理有限资源
    model_call()           // 决策
    tool_execution()       // 行动
    result_collection()    // 观察
    continuation_check()   // 元决策：继续还是停止
}

本模块将 ContextManager、ToolExecutor、ModelRouter 整合为一个
循环式引擎，替代 run_workflow.py 中直接的 call_agent() 调用。
"""

from __future__ import annotations

import re
import json
import logging
from typing import Optional, Generator
from dataclasses import dataclass, field

from context.manager import ContextManager, Message
from tools.base import ToolCall, ToolResult, ToolContext
from tools.executor import ToolExecutor
from tools.registry import ToolRegistry
from events import EventBus, EventType, WorkflowEvent
import model_router

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    """Single query engine run result."""
    final_response: str
    messages: list[Message]
    tool_results: list[ToolResult] = field(default_factory=list)
    turns_used: int = 0
    total_tokens_estimated: int = 0
    stop_reason: str = ""


class QueryEngine:
    """
    循环式 Agent 查询引擎

    Integrates:
    - ContextManager for token budget and graduated compression
    - ToolExecutor for parallel/serial tool execution
    - ModelRouter (with retry + circuit breaker) for LLM calls
    - EventBus for typed progress events
    """

    def __init__(self,
                 context_manager: Optional[ContextManager] = None,
                 tool_executor: Optional[ToolExecutor] = None,
                 tool_registry: Optional[ToolRegistry] = None,
                 event_bus: Optional[EventBus] = None,
                 config: Optional[dict] = None):
        self.context = context_manager or ContextManager()
        self.registry = tool_registry
        self.executor = tool_executor
        self.bus = event_bus or EventBus()
        self.config = config

        if self.registry and not self.executor:
            self.executor = ToolExecutor(self.registry)

    def run(self,
            agent_name: str,
            user_prompt: str,
            system_prompt: str = "",
            messages: Optional[list[Message]] = None,
            max_turns: int = 1,
            temperature: float = 0.7,
            post_compact_attachments: Optional[list[Message]] = None,
            ) -> QueryResult:
        """
        Execute the agent loop.

        For simple one-shot calls (no tool use), set max_turns=1.
        For agentic tool-using loops, set max_turns > 1.

        Args:
            agent_name: Which agent/model to route to
            user_prompt: The user's message for this turn
            system_prompt: Agent system prompt
            messages: Existing conversation history (for multi-turn)
            max_turns: Maximum loop iterations
            temperature: LLM temperature
            post_compact_attachments: Messages to re-inject after compact

        Returns:
            QueryResult with final response and full message history
        """
        if messages is None:
            messages = []
            if system_prompt:
                messages.append(Message(role="system", content=system_prompt))

        messages.append(Message(role="user", content=user_prompt))

        all_tool_results: list[ToolResult] = []
        final_response = ""

        for turn in range(max_turns):
            # 1. Context compression
            messages = self.context.compress_if_needed(
                messages, post_compact_attachments
            )

            # 2. Call model
            self.bus.emit(WorkflowEvent(
                type=EventType.AGENT_CALL,
                agent=agent_name,
                message=f"Calling {agent_name} (turn {turn + 1}/{max_turns})",
                data={"turn": turn + 1, "max_turns": max_turns},
            ))

            try:
                response_text = model_router.call_agent(
                    agent_name, user_prompt=self._last_user_content(messages),
                    system_prompt=self._system_content(messages),
                    temperature=temperature,
                    config=self.config,
                )
            except Exception as e:
                self.bus.error(f"Model call failed: {e}", agent=agent_name)
                return QueryResult(
                    final_response="",
                    messages=messages,
                    tool_results=all_tool_results,
                    turns_used=turn + 1,
                    stop_reason=f"error: {e}",
                )

            messages.append(Message(role="assistant", content=response_text, name=agent_name))
            final_response = response_text

            self.bus.emit(WorkflowEvent(
                type=EventType.AGENT_RESPONSE,
                agent=agent_name,
                message=f"{agent_name} responded ({len(response_text)} chars)",
                data={"char_count": len(response_text), "turn": turn + 1},
            ))

            # 3. Parse tool calls from response
            tool_calls = self._extract_tool_calls(response_text)

            if not tool_calls:
                # No tools requested — check if we need a follow-up
                if not self._needs_follow_up(response_text, turn, max_turns):
                    return QueryResult(
                        final_response=final_response,
                        messages=messages,
                        tool_results=all_tool_results,
                        turns_used=turn + 1,
                        total_tokens_estimated=self.context.estimate_tokens(messages),
                        stop_reason="complete",
                    )
                continue

            # 4. Execute tools
            if self.executor:
                ctx = ToolContext(workflow_id="", round=turn)
                results = self.executor.execute_batch_sync(tool_calls, ctx)
                all_tool_results.extend(results)

                # 5. Append results to message history
                for result in results:
                    messages.append(Message(
                        role="tool_result",
                        content=result.to_message_content(max_chars=5000),
                        name=result.tool_name,
                        metadata={"tool_name": result.tool_name, "success": result.success},
                    ))

                    self.bus.emit(WorkflowEvent(
                        type=EventType.TOOL_RESULT,
                        message=f"Tool {result.tool_name}: {'ok' if result.success else 'FAILED'}",
                        data={"tool": result.tool_name, "success": result.success},
                    ))

            # 6. Check continuation
            if not self._needs_follow_up(response_text, turn, max_turns):
                break

        return QueryResult(
            final_response=final_response,
            messages=messages,
            tool_results=all_tool_results,
            turns_used=min(turn + 1, max_turns),
            total_tokens_estimated=self.context.estimate_tokens(messages),
            stop_reason="max_turns" if turn >= max_turns - 1 else "complete",
        )

    def _extract_tool_calls(self, response: str) -> list[ToolCall]:
        """
        Parse tool call requests from LLM response text.

        Supports two formats:
        1. [TOOL_CALL: name] {"arg": "val"} [/TOOL_CALL]
        2. Native function_call JSON (for OpenAI-style responses)
        """
        calls = []

        # Format 1: XML-like tags
        pattern = r'\[TOOL_CALL:\s*(\w+)\]\s*(.*?)\s*\[/TOOL_CALL\]'
        for match in re.finditer(pattern, response, re.DOTALL):
            tool_name = match.group(1)
            args_str = match.group(2).strip()
            try:
                args = json.loads(args_str) if args_str else {}
            except json.JSONDecodeError:
                args = {"raw": args_str}
            calls.append(ToolCall(tool_name=tool_name, arguments=args))

        return calls

    def _needs_follow_up(self, response: str, turn: int, max_turns: int) -> bool:
        """Determine if the agent loop should continue."""
        if turn >= max_turns - 1:
            return False

        # Continue if response contains tool calls
        if re.search(r'\[TOOL_CALL:', response):
            return True

        # Continue if response explicitly requests continuation
        if re.search(r'\[CONTINUE\]', response):
            return True

        return False

    def _last_user_content(self, messages: list[Message]) -> str:
        """Extract the last user message content."""
        for msg in reversed(messages):
            if msg.role == "user":
                return msg.content
        return ""

    def _system_content(self, messages: list[Message]) -> str:
        """Extract system prompt from messages."""
        for msg in messages:
            if msg.role == "system" and not msg.is_compact_boundary:
                return msg.content
        return ""


def create_engine(event_bus: Optional[EventBus] = None,
                  config: Optional[dict] = None,
                  max_tokens: int = 120000) -> QueryEngine:
    """Factory function to create a fully-configured QueryEngine."""
    from tools.registry import build_default_registry

    registry = build_default_registry()
    executor = ToolExecutor(registry)

    def llm_summarizer(messages: list[Message]) -> str:
        """Use a fast model to summarize conversation history."""
        text = "\n".join(f"[{m.role}] {m.content[:500]}" for m in messages if m.role != "system")
        prompt = (
            "Please provide a concise summary of the following multi-agent conversation. "
            "Preserve key decisions, scores, and content drafts.\n\n" + text
        )
        try:
            return model_router.call_agent(
                "central-judge", prompt,
                system_prompt="You are a conversation summarizer. Be concise.",
                temperature=0.3,
                config=config,
            )
        except Exception as e:
            logger.warning(f"LLM summarizer failed: {e}")
            return None

    context = ContextManager(max_tokens=max_tokens)
    context.set_summarizer(llm_summarizer)

    return QueryEngine(
        context_manager=context,
        tool_executor=executor,
        tool_registry=registry,
        event_bus=event_bus,
        config=config,
    )
