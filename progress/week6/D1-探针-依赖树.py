"""D1 探针：把一棵依赖树的"骨架"打出来（不需要起服务器）。

用法（在 kb-service 目录下）：
    Windows PowerShell:  & .\\.venv\\Scripts\\python.exe ..\\progress\\week6\\D1-探针-依赖树.py
    Git Bash / Linux :  ./.venv/Scripts/python.exe ../progress/week6/D1-探针-依赖树.py

它回答三个问题：
1. 一棵树到底有几个节点？          → 节点 = 一个 Depends，根是路由函数
2. Query 参数算不算节点？          → 不算，挂在所在节点的 query_params 里（0.150 起）
3. 谁是谁的子？                    → 看缩进
"""

from __future__ import annotations

from fastapi.dependencies.utils import get_dependant

from kb_service.api.deps import get_current_user_id
from kb_service.api.v1.knowledge_bases import list_kbs


def walk(dependant, depth: int = 0) -> None:
    call = dependant.call
    name = getattr(call, "__name__", type(call).__name__)
    slots = []
    if dependant.query_params:
        slots.append(f"query={[p.name for p in dependant.query_params]}")
    if dependant.path_params:
        slots.append(f"path={[p.name for p in dependant.path_params]}")
    if dependant.header_params:
        slots.append(f"header={[p.name for p in dependant.header_params]}")
    if dependant.body_params:
        slots.append(f"body={[p.name for p in dependant.body_params]}")
    suffix = ("  ← 自带参数槽: " + ", ".join(slots)) if slots else ""
    print("    " * depth + f"- {name}{suffix}")
    for child in dependant.dependencies:
        walk(child, depth + 1)


if __name__ == "__main__":
    print("=== list_kbs 的依赖树（根 = 路由函数）===")
    walk(get_dependant(path="/kbs", call=list_kbs))

    print("\n=== get_current_user_id 自己也是一棵子树 ===")
    walk(get_dependant(path="/kbs", call=get_current_user_id))

    print("\n=== 结论 ===")
    d = get_dependant(path="/kbs", call=list_kbs)
    print(f"list_kbs 的子依赖个数: {len(d.dependencies)}（只有 get_current_user_id）")
    print(f"list_kbs 自己的 query 参数: {[p.name for p in d.query_params]}（不算节点）")
