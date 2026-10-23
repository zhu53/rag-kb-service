import functools
import time

def timer(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = fn(*args, **kwargs)
        end_time = time.perf_counter()
        cost = end_time - start_time
        print(f"[{fn.__name__}] 耗时 {cost:.4f}s")
        return result
    return wrapper


@timer
def slow():
    time.sleep(0.1)
    return "done"

if __name__ == "__main__":
    print(slow())   # 期望：打印耗时 + 返回 done
