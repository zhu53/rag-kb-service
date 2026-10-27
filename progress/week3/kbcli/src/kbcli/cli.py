import argparse
import sys

from kbcli.caching import LRUCache
from kbcli.config import get_settings
from kbcli.errors import AppError
from kbcli.repositories.json_repo import JSONFileKBRepository
from kbcli.services import KBService


def build_service() -> KBService:
    """组装现场：配置 → repo → cache → service，依赖注入就这一行行构造。"""
    settings = get_settings()
    repo = JSONFileKBRepository(settings.data_file)
    return KBService(repo, LRUCache(capacity=128))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kbcli", description="命令行知识库")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_create = sub.add_parser("create", help="新建知识库")
    p_create.add_argument("name")
    p_create.add_argument("--owner", default="local")
    p_list = sub.add_parser("list", help="列出我的知识库")
    p_list.add_argument("--owner", default="local")
    p_show = sub.add_parser("show", help="查看单个知识库")
    p_show.add_argument("kb_id")
    p_show.add_argument("--owner", default="local")
    p_delete = sub.add_parser("delete", help="删除知识库")
    p_delete.add_argument("kb_id")
    p_delete.add_argument("--owner", default="local")

    args = parser.parse_args(argv)
    svc = build_service()
    try:
        if args.cmd == "create":
            kb = svc.create_kb(args.owner, args.name)
            print(f"已创建: {kb['id']} {kb['name']}")
        elif args.cmd == "list":
            for kb in svc.list_kbs(args.owner):
                print(kb["id"], kb["name"])
        elif args.cmd == "show":
            kb = svc.get_kb(args.owner, args.kb_id)
            print(kb["id"], kb["name"], f"owner={kb['owner_id']}")
        elif args.cmd == "delete":
            svc.delete_kb(args.owner, args.kb_id)
            print(f"已删除: {args.kb_id}")
        return 0
    except AppError as exc:
        print(f"错误: {exc.message}", file=sys.stderr)
        return 2
