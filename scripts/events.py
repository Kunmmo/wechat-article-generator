#!/usr/bin/env python3
"""
结构化事件总线

替代 builtins.print 猴子补丁，提供类型化的工作流事件系统。
灵感来源：Claude Code 的 query loop 通过 async generator 向 UI 层
yield 类型化事件（assistant chunks, tool results, progress, tombstones）。

本模块实现一个轻量版：
- WorkflowEvent: 带类型标签的事件数据类
- EventBus: 发布-订阅模式，支持多个并发消费者
- 每个 WorkflowRunner 实例持有自己的 EventBus，无全局状态污染
"""

import logging
import queue
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

from log_config import get_logger

logger = get_logger(__name__)


class EventType(str, Enum):
    WORKFLOW_START = "workflow_start"
    WORKFLOW_END = "workflow_end"
    PHASE_START = "phase_start"
    PHASE_END = "phase_end"
    AGENT_CALL = "agent_call"
    AGENT_RESPONSE = "agent_response"
    TOOL_START = "tool_start"
    TOOL_RESULT = "tool_result"
    JUDGE_DECISION = "judge_decision"
    PROGRESS = "progress"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class WorkflowEvent:
    """类型化工作流事件"""
    type: EventType
    agent: str = ""
    round: int = 0
    phase: int = 0
    message: str = ""
    data: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["type"] = self.type.value
        return d

    @property
    def css_class(self) -> str:
        """Map event type to a CSS class for the web UI."""
        mapping = {
            EventType.WORKFLOW_START: "phase",
            EventType.WORKFLOW_END: "success",
            EventType.PHASE_START: "phase",
            EventType.PHASE_END: "success",
            EventType.AGENT_CALL: "",
            EventType.AGENT_RESPONSE: "success",
            EventType.TOOL_START: "",
            EventType.TOOL_RESULT: "success",
            EventType.JUDGE_DECISION: "phase",
            EventType.PROGRESS: "",
            EventType.WARNING: "warning",
            EventType.ERROR: "error",
        }
        return mapping.get(self.type, "")


# Sentinel values for stream control
_STREAM_DONE = "__STREAM_DONE__"
_STREAM_FAILED = "__STREAM_FAILED__"


class EventBus:
    """
    发布-订阅事件总线

    每个 WorkflowRunner 持有独立实例，解决并发安全问题。
    订阅者通过 queue.Queue 接收事件，适配 Flask SSE 的 generator 模式。
    """

    def __init__(self):
        self._subscribers: list[queue.Queue] = []
        self._lock = threading.Lock()
        self._history: list[WorkflowEvent] = []
        self._console_echo = True

    def subscribe(self) -> queue.Queue:
        """创建并返回一个新的订阅队列"""
        q: queue.Queue = queue.Queue()
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue):
        """移除订阅"""
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def emit(self, event: WorkflowEvent):
        """发布事件到所有订阅者"""
        self._history.append(event)
        if self._console_echo:
            _echo_to_console(event)
        with self._lock:
            for q in self._subscribers:
                q.put(event)

    def emit_done(self, result: Optional[dict] = None):
        """发送完成信号"""
        with self._lock:
            for q in self._subscribers:
                q.put((_STREAM_DONE, result))

    def emit_failed(self, error: str = ""):
        """发送失败信号"""
        with self._lock:
            for q in self._subscribers:
                q.put((_STREAM_FAILED, error))

    @property
    def history(self) -> list[WorkflowEvent]:
        return list(self._history)

    # ---- Convenience emitters ----

    def log(self, message: str, agent: str = "", round_: int = 0, phase: int = 0):
        """发出进度日志事件"""
        self.emit(WorkflowEvent(
            type=EventType.PROGRESS,
            agent=agent, round=round_, phase=phase, message=message,
        ))

    def phase_start(self, phase: int, total: int, agent: str, message: str, round_: int = 0):
        self.emit(WorkflowEvent(
            type=EventType.PHASE_START,
            agent=agent, round=round_, phase=phase,
            message=message,
            data={"total_phases": total},
        ))

    def phase_end(self, phase: int, agent: str, message: str, round_: int = 0):
        self.emit(WorkflowEvent(
            type=EventType.PHASE_END,
            agent=agent, round=round_, phase=phase, message=message,
        ))

    def agent_call(self, agent: str, model: str = "", round_: int = 0):
        self.emit(WorkflowEvent(
            type=EventType.AGENT_CALL,
            agent=agent, round=round_,
            message=f"Calling {agent}",
            data={"model": model},
        ))

    def agent_response(self, agent: str, char_count: int = 0, round_: int = 0):
        self.emit(WorkflowEvent(
            type=EventType.AGENT_RESPONSE,
            agent=agent, round=round_,
            message=f"{agent} responded ({char_count} chars)",
            data={"char_count": char_count},
        ))

    def warn(self, message: str, agent: str = ""):
        self.emit(WorkflowEvent(type=EventType.WARNING, agent=agent, message=message))

    def error(self, message: str, agent: str = ""):
        self.emit(WorkflowEvent(type=EventType.ERROR, agent=agent, message=message))

    def judge(self, decision: str, score: Optional[float] = None, round_: int = 0):
        self.emit(WorkflowEvent(
            type=EventType.JUDGE_DECISION,
            agent="central-judge", round=round_,
            message=f"Decision: {decision}",
            data={"decision": decision, "score": score},
        ))


def _echo_to_console(event: WorkflowEvent):
    """将事件回显到 logger（结构化日志 + 控制台）"""
    extra = {
        "event_type": event.type.value,
        "agent": event.agent,
        "round": event.round,
    }
    if event.type == EventType.PHASE_START:
        phase = event.phase
        total = event.data.get("total_phases", 6)
        logger.info(
            "Phase %d/%d: %s | Round %d | %s",
            phase, total, event.agent, event.round, event.message,
        )
    elif event.type == EventType.ERROR:
        logger.error("EVENT ERROR: %s", event.message)
    elif event.type == EventType.WARNING:
        logger.warning("EVENT WARN: %s", event.message)
    elif event.message:
        logger.info("%s", event.message)
