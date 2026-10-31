"""项目质量门禁：一条命令跑完全部检查，任何一步失败就以非零码退出。

用法（在 kb-service 目录下）：
    .\.venv\Scripts\python.exe scripts\check.py              # 常规门禁：格式 + 测试 + 覆盖率
    .\.venv\Scripts\python.exe scripts\check.py --mutation   # 额外跑变异检查（慢一些）

CI 里就是把这条命令原样跑一遍——本地能过、CI 就能跑通，不存在"我机器上是好的"。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COV_FLOOR = 95  # 覆盖率下限（百分比）
TARGETS = ["src", "tests", "scripts"]


def step(name: str, cmd: list[str]) -> bool:
    print(f"\n=== {name} ===", flush=True)
    code = subprocess.run(cmd, cwd=ROOT).returncode
    print(f"[{'PASS' if code == 0 else 'FAIL'}] {name}", flush=True)
    return code == 0


def main() -> int:
    with_mutation = "--mutation" in sys.argv

    checks = [
        ("ruff check", [sys.executable, "-m", "ruff", "check", *TARGETS]),
        ("ruff format --check", [sys.executable, "-m", "ruff", "format", "--check", *TARGETS]),
        (
            f"pytest + 覆盖率门禁 ({COV_FLOOR}%)",
            [
                sys.executable,
                "-m",
                "pytest",
                "--cov",
                "--cov-report=term-missing",
                f"--cov-fail-under={COV_FLOOR}",
            ],
        ),
    ]

    failed: list[str] = []
    for name, cmd in checks:
        if not step(name, cmd):
            failed.append(name)

    if with_mutation and not step("变异检查", [sys.executable, "scripts/mutation_check.py"]):
        failed.append("变异检查")

    print("\n" + "=" * 46, flush=True)
    if failed:
        print(f"门禁未通过：{', '.join(failed)}")
        return 1
    print("门禁全绿，可以提交")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
