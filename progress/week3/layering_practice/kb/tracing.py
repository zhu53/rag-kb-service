"""trace_id 上下文 + 日志注入。业务层只管 logger.info，盖章在这里自动完成。"""

import logging
import uuid
from contextvars import ContextVar

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="-")


def new_trace_id() -> str:
    """生成 8 位短 id。全链路唯一性够用，人眼好认。"""
    return uuid.uuid4().hex[:8]


class TraceIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # ① 从 ContextVar 读出当前 trace_id，挂到 record.trace_id 上
        # ② 记得 return True（返回 False = 把这条日志扔掉！）
        record.trace_id = trace_id_var.get()  # 读出来直接挂 record 上
        return True


def setup_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-5s [%(trace_id)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    handler.addFilter(TraceIdFilter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
