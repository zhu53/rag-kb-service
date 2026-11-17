"""读取 SHOW ENGINE INNODB STATUS 里的 LATEST DETECTED DEADLOCK 段。

跑法（在 kb-service 目录）：
    ./.venv/Scripts/python.exe ../progress/week7/probes/read_deadlock.py

注意：InnoDB 只保留最近一次死锁的日志，实例重启后清空。
"""
from __future__ import annotations

import re

import pymysql


def main() -> None:
    c = pymysql.connect(host="127.0.0.1", port=3307, user="root", password="",
                        charset="utf8mb4")
    cur = c.cursor()
    cur.execute("SHOW ENGINE INNODB STATUS")
    text = cur.fetchone()[2]
    c.close()

    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if "LATEST DETECTED DEADLOCK" in ln), None)
    if start is None:
        print("(当前没有 LATEST DETECTED DEADLOCK——还没发生过死锁，或实例重启过)")
        return
    # 跳过标题后的分隔线，收集到下一条分隔线为止
    j = start + 1
    if j < len(lines) and set(lines[j].strip()) == {"-"}:
        j += 1
    end = next((k for k in range(j, len(lines)) if set(lines[k].strip()) == {"-"}), len(lines))
    section = "\n".join(lines[start:end])
    print(section)
    print()
    stamp = re.search(r"^\*+\n(\d{4}-\d{2}-\d{2} .*)", section, re.M)
    if stamp:
        print(f"死锁发生时间: {stamp.group(1)}")


if __name__ == "__main__":
    main()
