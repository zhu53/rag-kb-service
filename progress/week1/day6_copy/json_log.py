"""json_log.py —— Day6 任务 B：ContextVar + JSON 日志"""

from __future__ import annotations

import asyncio
import json
import logging
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from uuid import uuid4

# ---------- B1：上下文 ----------
trace_id_ctx: ContextVar[str] = ContextVar("trace_id", default="-")

# 在这写 set / get 的小工具
def set_trace_id(trace_id: str) -> Token:
    return trace_id_ctx.set(trace_id)

def reset_trace_id(token: Token) -> None:
    trace_id_ctx.reset(token)

def get_trace_id() -> str:
    return trace_id_ctx.get()

# ---------- B2：格式化 ----------
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        created = datetime.fromtimestamp(record.created, tz=UTC)
        log_dict = {
            "time": created.isoformat(),
            "trace_id": trace_id_ctx.get(),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            log_dict["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_dict, ensure_ascii=False)


# ---------- B3：安装 ----------
def setup_logging(level: int = logging.INFO) -> None:
    # TODO: 拿 root → clear handlers → 加 StreamHandler(JsonFormatter)
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)


# ---------- B4：模拟一次请求 ----------
async def handle_request(path: str) -> None:
    trace_id = uuid4().hex[:8]
    token = set_trace_id(trace_id)
    try:
        logging.info(f"收到请求: {trace_id}")
        await asyncio.sleep(0.1)
        logging.info(f"请求完成: {trace_id}")
    finally:
        reset_trace_id(token)

# ---------- B5：并发自测 ----------
async def main() -> None:
    setup_logging()
    await asyncio.gather(
        handle_request("/api/users"),
        handle_request("/api/orders"),
        handle_request("/api/products"),
    )


if __name__ == "__main__":
    asyncio.run(main())
