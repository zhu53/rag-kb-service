import functools


def retry(times: int):  # 第 1 层：收参数
    def decorator(fn):  # 第 2 层：收函数
        @functools.wraps(fn)  # 忘了它 FastAPI 会 422——别忘了
        def wrapper(*args, **kwargs):  # 第 3 层：每次调用
            # 失败重试，共尝试 times 次；全失败 → raise 最后一个异常
            last_ex: Exception | None = None
            for _ in range(times):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:  # noqa: BLE001 -- 重试器的职责就是兜住一切异常
                    last_ex = e
            raise last_ex

        return wrapper

    return decorator
