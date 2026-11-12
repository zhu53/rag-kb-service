"""手工变异测试：往源码里注入小改动，看测试套件能不能"杀死"它。

用法（在 kb-service 目录下）：
    .\.venv\Scripts\python.exe scripts\mutation_check.py

两段，语义不同：

  MUTANTS     真 bug 的等价改动，**应该被测试杀死**。有存活 = 退出码 1，可当门禁用。
  BLIND_SPOTS 刻意注入"测试门分不清"的改动。它们存活是**预期**——这段跑的是
              "测试门的盲区在哪"，只报告，不影响退出码。

D6 的五类注入里，只有"依赖循环"没法用字符串替换表达（要真实 import 环），
用 `progress/week6/D6-探针-五类注入.py` §1 的探针验证：路由注册时就 RecursionError。

脚本每次都会把源码还原，跑完可用 `git status --short` 确认工作区干净。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (文件, 原文, 变异后, 这个变异在模拟什么 bug)
MUTANTS: list[tuple[str, str, str, str]] = [
    # ---- 业务逻辑（W5 已有）----
    (
        "src/kb_service/services/doc_service.py",
        "offset = (page - 1) * size",
        "offset = page * size",
        "分页偏移少减 1（第二页开始全错）",
    ),
    (
        "src/kb_service/services/doc_service.py",
        'incr_doc_count(row["kb_id"], -1)',
        'incr_doc_count(row["kb_id"], 1)',
        "删除文档时计数方向反了",
    ),
    (
        "src/kb_service/services/doc_service.py",
        "if chunk_size <= 0:",
        "if chunk_size < 0:",
        "边界从 <= 放宽成 <（零长度不再拦）",
    ),
    (
        "src/kb_service/services/doc_service.py",
        "if overlap >= chunk_size:",
        "if overlap > chunk_size:",
        "边界漏掉等号（overlap == chunk_size 会死循环风险）",
    ),
    (
        "src/kb_service/services/doc_service.py",
        "        if chunk:",
        "        if True:",
        "空块不再过滤（切出空字符串也塞进结果）",
    ),
    # ---- 第 4 类：response_model 撒谎 ----
    (
        "src/kb_service/schemas/kb.py",
        "    doc_count: int = 0\n",
        "",
        "KBOut 少声明 doc_count（handler 还在返回它，字段静默消失）",
    ),
    (
        "src/kb_service/schemas/kb.py",
        "    doc_count: int = 0\n",
        '    doc_count: str = "0"\n',
        "KBOut 把 doc_count 声明成 str（出参类型对不上 → 500）",
    ),
    # ---- 第 5 类：校验放宽 ----
    (
        "src/kb_service/schemas/common.py",
        "size: int = Field(default=20, ge=1, le=100)",
        "size: int = Field(default=20, ge=1)",
        "PageParams.size 删掉上限 le=100（大分页请求放行）",
    ),
    # ---- 第 3 类：middleware 顺序（此项目唯一可自动化的形态：整个不装）----
    (
        "src/kb_service/main.py",
        "    app.add_middleware(TraceMiddleware)\n",
        "",
        "TraceMiddleware 完全不装（trace_id / 耗时日志全丢）",
    ),
]


# 预期存活：测试门抓不住，只能靠 review / 静态检查 / 门禁脚本兜住的改动
BLIND_SPOTS: list[tuple[str, str, str, str]] = [
    # ---- 第 2 类：缓存误用 ----
    (
        "src/kb_service/api/v1/knowledge_bases.py",
        "    kb_id: UUID,\n    user_id: UUID = Depends(get_current_user_id),\n"
        ") -> ApiResponse[KBOut]:",
        "    kb_id: UUID,\n    user_id: UUID = Depends(get_current_user_id),\n"
        "    _dup: UUID = Depends(get_current_user_id, use_cache=False),\n"
        ") -> ApiResponse[KBOut]:",
        "依赖缓存误用：同一请求里验两次 token（use_cache=False）",
    ),
    # ---- 第 3 类：middleware 顺序 / 重复注册 ----
    (
        "src/kb_service/main.py",
        "    app.add_middleware(TraceMiddleware)\n",
        "    app.add_middleware(TraceMiddleware)\n    app.add_middleware(TraceMiddleware)\n",
        "TraceMiddleware 装了两层（响应头仍在，测试分不清一层还是两层）",
    ),
    # ---- 第 5 类：校验收窄的一道，另一道兜着 ----
    (
        "src/kb_service/schemas/kb.py",
        'Field(min_length=1, max_length=100, description="知识库名称")',
        'Field(max_length=100, description="知识库名称")',
        "KbName 删 min_length=1（AfterValidator(not_blank) 仍兜住空串）",
    ),
    (
        "src/kb_service/schemas/doc.py",
        "Field(min_length=1, max_length=20000)",
        "Field(min_length=1)",
        "DocContent 删 max_length=20000（没有超大正文的边界测试）",
    ),
]


def run_tests() -> int:
    """跑一遍测试，返回退出码。--no-cov 让每次跑快一点。"""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-x", "-q", "--no-cov", "-p", "no:cacheprovider"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return proc.returncode


def mutate_and_test(path_str: str, old: str, new: str, label: str) -> int | None:
    """注入 → 跑测试 → 无论成败都还原。找不到唯一匹配时返回 None。"""
    path = ROOT / path_str
    # 用 bytes 读写：Path.write_text 在 Windows 上会把 \n 翻译成 \r\n，还原时会污染行尾
    original = path.read_bytes().decode("utf-8")
    if original.count(old) != 1:
        print(f"[跳过] 找不到唯一匹配：{label}")
        return None
    try:
        path.write_bytes(original.replace(old, new).encode("utf-8"))
        return run_tests()
    finally:
        path.write_bytes(original.encode("utf-8"))


def run_group(title: str, mutants: list[tuple[str, str, str, str]], expect_kill: bool) -> list[str]:
    """跑一组变异体，返回"结果与预期不符"的标签列表。"""
    print(f"\n== {title} ==")
    mismatched: list[str] = []
    for path_str, old, new, label in mutants:
        code = mutate_and_test(path_str, old, new, label)
        if code is None:
            continue
        killed = code != 0
        if expect_kill:
            print(f"[{'杀死' if killed else '存活'}] {label}")
            if not killed:
                mismatched.append(label)
        else:
            print(f"[{'被杀死' if killed else '存活·已确认'}] {label}")
            if killed:
                mismatched.append(label)
    return mismatched


def main() -> int:
    print("基线：先确认原始代码是绿的 ……", end=" ", flush=True)
    if run_tests() != 0:
        print("红！源码本身有问题，先修好再变异。")
        return 2
    print("绿")

    survived = run_group("第一段：门禁变异（应该全被杀）", MUTANTS, expect_kill=True)
    blind = run_group("第二段：盲区探针（预期存活）", BLIND_SPOTS, expect_kill=False)

    total = len(MUTANTS)
    killed = total - len(survived)
    print(f"\n变异得分：{killed}/{total} = {killed / total:.0%}")
    print(f"盲区确认：{len(BLIND_SPOTS) - len(blind)}/{len(BLIND_SPOTS)} 类改动测试门无感知")

    if survived:
        print("有真 bug 级变异存活（测试门有洞）：" + "；".join(survived))
    if blind:
        print("有盲区探针被杀死（盲区已不存在，可从清单移除）：" + "；".join(blind))
    return 1 if (survived or blind) else 0


if __name__ == "__main__":
    raise SystemExit(main())
