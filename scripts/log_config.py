"""
集中式日志配置

为整个项目提供统一的日志系统：
- Console handler: 人类可读格式，输出到 stderr
- File handler: JSON Lines 格式，输出到 logs/ 目录
  AI 编程智能体（Cursor / Claude Code / CC）可直接 grep/parse 进行 bug 排查
- Log level 通过 LOG_LEVEL 环境变量控制（默认 INFO）
- RotatingFileHandler: 单文件 10MB 上限，保留 5 个备份
"""

import json
import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path

LOG_DIR = Path(__file__).parent.parent / "logs"

_initialized_loggers: set[str] = set()


class _JsonFormatter(logging.Formatter):
    """JSON Lines 格式化器，方便 AI agent 解析日志。"""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            "ts": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "file": f"{record.filename}:{record.lineno}",
            "func": record.funcName,
        }
        if record.exc_info and record.exc_info[1] is not None:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def setup_logging(name: str = "wechat-gen") -> logging.Logger:
    """
    初始化并返回 logger。

    幂等：对同一 name 多次调用不会重复添加 handler。

    Args:
        name: logger 名称，子模块用 getLogger(__name__) 自动继承。

    Returns:
        配置好的 logging.Logger 实例
    """
    logger = logging.getLogger(name)

    if name in _initialized_loggers:
        return logger
    _initialized_loggers.add(name)

    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logger.setLevel(getattr(logging, level, logging.INFO))

    # Console: human-readable, to stderr
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.DEBUG)
    console.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)-5s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    ))
    logger.addHandler(console)

    # File: JSON Lines for AI agent parsing
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = LOG_DIR / f"workflow_{datetime.now():%Y%m%d}.jsonl"
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(_JsonFormatter())
        logger.addHandler(file_handler)
    except OSError:
        logger.warning("Failed to create log file handler, file logging disabled")

    return logger


def get_logger(module_name: str) -> logging.Logger:
    """
    获取子模块 logger。

    用法：在每个 .py 文件顶部调用
        from log_config import get_logger
        logger = get_logger(__name__)

    子 logger 自动继承 setup_logging() 配置的 handler。
    """
    return logging.getLogger(f"wechat-gen.{module_name}")
