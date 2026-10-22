"""logging_setup.py —— 项目统一的 JSON 日志配置

用法：
    from logging_setup import get_logger, set_trace_id, setup_logging

    setup_logging()
    log = get_logger(__name__)
    set_trace_id("req-8f3a")
    log.info("收到请求", extra={"path": "/api/v1/kbs", "method": "GET"})

设计说明：
    - trace_id 用 ContextVar 存，异步场景下每个请求互不干扰
    - formatter 输出单行 JSON，方便日志采集器按行解析
    - 除 logging 保留字段外，extra 里传入的自定义字段全部平铺到 JSON 顶层
"""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

trace_id_ctx: ContextVar[str] = ContextVar("trace_id", default="-")

_RESERVED = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
    }
)


def set_trace_id(trace_id: str) -> None:
    """给当前上下文打上请求编号，供 formatter 读取。"""
    trace_id_ctx.set(trace_id)


def get_trace_id() -> str:
    """读取当前上下文的请求编号，未设置时返回 "-"。"""
    return trace_id_ctx.get()


class JsonFormatter(logging.Formatter):
    """把 LogRecord 序列化成一行 JSON。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "time": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "trace_id": get_trace_id(),
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: int = logging.INFO) -> None:
    """把 JSON handler 安装到 root logger。"""
    root = logging.getLogger()
    root.setLevel(level)
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """取一个按模块命名的 logger。"""
    return logging.getLogger(name)


def _demo() -> None:
    setup_logging()
    log = get_logger("kb_service")
    set_trace_id("req-8f3a")
    log.info("收到请求", extra={"path": "/api/v1/kbs", "method": "GET"})
    try:
        _ = {"kb": 1}["doc"]
    except KeyError:
        log.exception("读取知识库失败")


if __name__ == "__main__":
    _demo()
