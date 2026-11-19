"""项目质量门禁：一条命令跑完全部检查，任何一步失败就以非零码退出。

用法（在 kb-service 目录下）：
    .\.venv\Scripts\python.exe scripts\check.py              # 常规门禁：格式 + 测试 + 覆盖率
    .\.venv\Scripts\python.exe scripts\check.py --mutation   # 额外跑变异检查（慢一些）

CI 里就是把这条命令原样跑一遍——本地能过、CI 就能跑通，不存在"我机器上是好的"。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # kb-service/
REPO = ROOT.parent  # 仓库根
COV_FLOOR = 95.0  # 覆盖率下限（百分比，精确比较，不四舍五入）
TARGETS = ["src", "tests", "scripts", "conftest.py"]
# 第四档题面：在仓库根 reviews/ 下，和项目代码分开。
# 只做 ruff 检查（风格必须干净，否则题面本身就有噪音），
# **不**进 pytest / 覆盖率 / mypy——它是练习题，不是交付物，不能抬高门禁指标。
REVIEWS = [str(REPO / "reviews")]


def step(name: str, cmd: list[str]) -> bool:
    print(f"\n=== {name} ===", flush=True)
    code = subprocess.run(cmd, cwd=ROOT).returncode
    print(f"[{'PASS' if code == 0 else 'FAIL'}] {name}", flush=True)
    return code == 0


def coverage_gate(floor: float) -> bool:
    """自己算覆盖率，不用 pytest-cov 的判定。

    2026-11-19 实测发现两道坑，都是"看起来在拦、其实没拦"：

    1. 本项目装的 pytest-cov 在 `pytest_terminal_summary` 里**只打印** FAIL 文案，
       从不设置 `session.exitstatus`（源码里搜不到 exitstatus）——所以
       `--cov-fail-under` 无论达标与否，pytest 都退 0。
    2. `coverage report --fail-under` 用**四舍五入后**的整数比较：
       94.75% round 成 95，等于没触发。

    这两条叠加的后果：覆盖率从 96% 掉到 60%，门禁照样全绿。
    所以这里绕开两者，直接读 `coverage json` 的精确浮点数自己比——
    **判据必须来自数据，不能来自工具的口头表态。**
    """
    print(f"\n=== 覆盖率门禁（精确 {floor}%）===", flush=True)
    out = ROOT / ".coverage.json"
    subprocess.run(
        [sys.executable, "-m", "coverage", "json", "-o", str(out), "-q"],
        cwd=ROOT,
        check=False,
    )
    try:
        total = float(json.loads(out.read_text(encoding="utf-8"))["totals"]["percent_covered"])
    except (OSError, KeyError, ValueError) as exc:  # 没有 .coverage 说明 pytest 没跑成
        print(f"[FAIL] 读不到覆盖率数据：{exc}")
        return False
    finally:
        out.unlink(missing_ok=True)

    ok = total >= floor
    print(f"[{'PASS' if ok else 'FAIL'}] 实际覆盖率 {total:.2f}%（下限 {floor}%）")
    return ok


def main() -> int:
    with_mutation = "--mutation" in sys.argv

    checks = [
        ("ruff check", [sys.executable, "-m", "ruff", "check", *TARGETS, *REVIEWS]),
        (
            "ruff format --check",
            [sys.executable, "-m", "ruff", "format", "--check", *TARGETS, *REVIEWS],
        ),
        ("mypy", [sys.executable, "-m", "mypy", *TARGETS]),
        (
            "pytest",
            [sys.executable, "-m", "pytest", "--cov", "--cov-report=term-missing"],
        ),
    ]

    failed: list[str] = []
    for name, cmd in checks:
        if not step(name, cmd):
            failed.append(name)

    # 覆盖率单独判：pytest-cov 的 --cov-fail-under 在本环境不设退出码（见函数注释）
    if not coverage_gate(COV_FLOOR):
        failed.append(f"覆盖率 <{COV_FLOOR}%")

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
