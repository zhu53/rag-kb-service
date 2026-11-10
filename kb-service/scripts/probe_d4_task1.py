"""D4 任务 1 自验探针：统一错误壳。

用法（kb-service 目录下，PowerShell）：
    & .\.venv\Scripts\python.exe scripts\probe_d4_task1.py

四条检查，全 PASS 才算任务 1 的错误壳部分过关：
  1. 无 token 访问业务接口 -> 401，且 body 是 {code, message, data} 单层壳
  2. 422（空 name）-> 同一个壳，code 是 int
  3. 业务接口正常路径 -> 200（保证没改坏）
  4. 不存在具体业务码/双层壳/ApiResponse 裸返回等回退
"""

import sys

from fastapi.testclient import TestClient

from kb_service.core.security import create_access_token
from kb_service.main import create_app

app = create_app()
with TestClient(app, raise_server_exceptions=False) as c:
    failures: list[str] = []

    # --- 1: 无 token -> 401 + 单层壳 ---
    r = c.get("/api/v1/kbs")
    body = r.json()
    ok1 = (
        r.status_code == 401
        and set(body) == {"code", "message", "data"}
        and isinstance(body["code"], int)
    )
    print(f"[1] 无 token -> {r.status_code} | body = {body}")
    if not ok1:
        failures.append("1: 应为 401 + {code,message,data} 单层壳 + code 为 int")
    # 深层键检查：壳里不允许再嵌一个 code
    if isinstance(body.get("data"), dict) and "code" in body["data"]:
        failures.append("1: 壳中套壳——data 里又出现了 code 字段")

    # --- 2: 422 -> 同一个壳，且语义完整 ---
    h = {"Authorization": "Bearer " + create_access_token("11111111-1111-4111-8111-111111111111")}
    r2 = c.post("/api/v1/kbs", json={"name": ""}, headers=h)
    body2 = r2.json()
    ok2 = (
        r2.status_code == 422
        and set(body2) == {"code", "message", "data"}
        and isinstance(body2["code"], int)
    )
    print(f"[2] 空 name -> {r2.status_code} | body = {body2}")
    if not ok2:
        failures.append("2: 应为 422 + 同一个壳 + code 为 int")
    if body2.get("message") == "ok":
        failures.append("2: 错误响应的 message 不能是 'ok'——客户端读不懂")
    if isinstance(body2.get("data"), dict):
        failures.append(
            "2: data 应是校验错误清单（loc/msg/type），不是请求体回声 "
            f"（现在是 {body2.get('data')!r}）"
        )

    # --- 5: 404 路径的业务码不能和 401 相同（抓 code 写死） ---
    r5 = c.get("/api/v1/kbs/11111111-1111-4111-8111-111111111111", headers=h)
    body5 = r5.json()
    print(f"[5] 查不存在的 kb -> {r5.status_code} | body = {body5}")
    if r5.status_code == 404 and body5.get("code") == body["code"]:
        failures.append(
            f"5: 404 的业务码 {body5.get('code')} 和 401 的 {body['code']} 相同"
            "——业务码失去了区分错误类型的意义"
        )

    # --- 3: 正常路径没被改坏 ---
    r3 = c.post("/api/v1/kbs", json={"name": "probe"}, headers=h)
    print(f"[3] 正常创建 -> {r3.status_code}")
    if r3.status_code != 201:
        failures.append(f"3: 正常创建应 201，实际 {r3.status_code}")

    # --- 4: 汇总 ---
    if failures:
        print("\nFAIL —— 问题清单：")
        for f in failures:
            print("  -", f)
        sys.exit(1)
    print("\n全部 PASS —— 错误壳统一完成，可以做任务 1 第 3 步（套 response_model）")
