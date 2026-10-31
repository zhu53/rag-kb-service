"""手工变异测试：往源码里注入小改动，看测试套件能不能"杀死"它。

用法（在 kb-service 目录下）：
    .\.venv\Scripts\python.exe scripts\mutation_check.py

变异体存活 = 测试套件发现不了这个改动 = 这条路径的测试是摆设。
只要有存活，脚本就以退出码 1 结束，可以直接当门禁用。
脚本每次都会把源码还原，跑完可用 `git status --short` 确认工作区干净。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (文件, 原文, 变异后, 这个变异在模拟什么 bug)
MUTANTS: list[tuple[str, str, str, str]] = [
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


def main() -> int:
    print("基线：先确认原始代码是绿的 ……", end=" ", flush=True)
    if run_tests() != 0:
        print("红！源码本身有问题，先修好再变异。")
        return 2
    print("绿\n")

    killed = 0
    for path_str, old, new, label in MUTANTS:
        path = ROOT / path_str
        # 用 bytes 读写：Path.write_text 在 Windows 上会把 \n 翻译成 \r\n，还原时会污染行尾
        original = path.read_bytes().decode("utf-8")
        if original.count(old) != 1:
            print(f"[跳过] 找不到唯一匹配：{label}")
            continue
        try:
            path.write_bytes(original.replace(old, new).encode("utf-8"))
            code = run_tests()
        finally:
            path.write_bytes(original.encode("utf-8"))

        if code == 0:
            print(f"[存活] {label}  ← 测试套件没发现")
        else:
            killed += 1
            print(f"[杀死] {label}")

    total = len(MUTANTS)
    print(f"\n变异得分：{killed}/{total} = {killed / total:.0%}")
    if killed < total:
        print("存活的每一个，都是一条'写了但没起作用'的测试线索")
        return 1
    print("全部变异都被杀死：测试套件对这条路径是真的有杀伤力")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
