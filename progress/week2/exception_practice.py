import traceback

# ① 异常体系：AppError 基类（code/http_status/message 三个类属性 + detail 参数）
#    + NotFoundError(404) + ForbiddenError(403) 两个子类


class AppError(Exception):
    code: str = "APP_ERROR"
    http_status: int = 500
    message: str = "应用错误"

    def __init__(self, detail: str = ""):
        self.detail = detail
        super().__init__(self.message)


class NotFoundError(AppError):
    code: str = "NOT_FOUND"
    http_status: int = 404
    message: str = "资源不存在"


class ForbiddenError(AppError):
    code: str = "FORBIDDEN"
    http_status: int = 403
    message: str = "无权访问"


# ② service 函数：find_kb(store, kb_id, user_id)
#    store 是 dict，kb 不存在 → raise NotFoundError；
#    存在但 owner_id 不是 user_id → raise ForbiddenError（带上 kb_id 进 detail）
#    找到 → 返回那条记录
def find_kb(store, kb_id, user_id):
    kb = store.get(kb_id)
    if kb is None:
        raise NotFoundError()
    if kb["owner_id"] != user_id:
        raise ForbiddenError(detail=f"kb_id={kb_id}")
    return kb


# ③ 翻译函数：translate(err: Exception) -> tuple[int, dict]
#    AppError → (exc.http_status, {"code": exc.code, "message": exc.message})
#    其他异常 → (500, {"code": "INTERNAL", "message": "内部错误"})
#    ★ 关键：其他异常分支里要把原始异常 print 出来（排查 500 全靠它）
def translate(err: Exception) -> tuple[int, dict]:
    if isinstance(err, AppError):
        return (
            err.http_status,
            {"code": err.code, "message": err.message},
        )
    print(err)
    traceback.print_exc()
    return (500, {"code": "INTERNAL", "message": "内部错误"})


# ④ __main__ 里自测三种情况：正常 / 不存在 / 越权，打印三行结果
if __name__ == "__main__":
    store = {
        "kb1": {"kb_id": "kb1", "owner_id": "alice"},
        "kb2": {"kb_id": "kb2", "owner_id": "bob"},
    }

    # 正常
    try:
        result = find_kb(store, "kb1", "alice")
        print("正常:", result)
    except Exception as e:
        print("正常", translate(e))

    # 不存在
    try:
        find_kb(store, "kb999", "alice")
    except Exception as e:
        print("不存在：", translate(e))

    # 越权
    try:
        find_kb(store, "kb2", "alice")
    except Exception as e:
        print("越权：", translate(e))
