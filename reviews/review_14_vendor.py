"""行情网关：把无类型的 vendor SDK 包一层，对外提供稳定的报价视图。

vendor SDK（第三方行情服务）没有类型标注，返回值在类型检查器眼里是 Any。
这一层负责把它收敛成项目内部的 Quote 结构，供上层接口直接使用。
"""

from __future__ import annotations

from typing import Any, TypedDict, cast

DEFAULT_PAGE_SIZE = 20


class Quote(TypedDict):
    """一行报价。"""

    symbol: str
    name: str
    price: float


class QuoteMeta(TypedDict, total=False):
    """快照元信息：ts 由 vendor 决定是否返回。"""

    ts: str
    source: str


class VendorSDK:
    """模拟第三方行情 SDK：真实项目里是 import 进来的包，这里用 Any 复现同一个边界。"""

    def __init__(self, rows: list[dict[str, Any]], meta: dict[str, Any]) -> None:
        self._rows = rows
        self._meta = meta

    def fetch(self) -> Any:
        """返回 {"code": 0, "data": [...]}，结构由 vendor 决定。"""
        return {"code": 0, "data": self._rows}

    def snapshot_meta(self) -> Any:
        return self._meta


def _as_text(value: Any) -> str:
    """vendor 的字段可能是 None 或数字，这里统一成展示文本。"""
    return cast(str, value)


class QuoteGateway:
    def __init__(self, sdk: VendorSDK, cfg: dict[str, Any] | None = None) -> None:
        self._sdk = sdk
        self.cfg: dict[str, Any] = cfg or {}

    @property
    def page_size(self) -> int:
        """每页条数。配置 0 表示不分页。"""
        raw = self.cfg.get("page_size")
        return int(raw) if raw else DEFAULT_PAGE_SIZE

    def load(self) -> list[Quote]:
        try:
            payload = self._sdk.fetch()
            rows = payload["data"]
            return [
                Quote(
                    symbol=_as_text(row["symbol"]),
                    name=_as_text(row.get("name")),
                    price=float(row["price"]),
                )
                for row in rows
            ]
        except Exception:
            return []

    def stamp(self) -> str:
        meta: QuoteMeta = self._sdk.snapshot_meta()
        return f"{meta['ts']} / {meta.get('source', 'unknown')}"


def render(quotes: list[Quote]) -> None:
    print(f"{'代码':<8}{'名称':<16}{'价格':>8}")
    for q in quotes:
        print(f"{q['symbol']:<8}{q['name']:<16}{q['price']:>8.2f}")


def main() -> None:
    sdk = VendorSDK(
        rows=[
            {"symbol": "AAPL", "name": "Apple Inc.", "price": 189.2},
            {"symbol": "MSFT", "name": "Microsoft Corp.", "price": 412.5},
            {"symbol": "TSLA", "name": "Tesla, Inc.", "price": 248.1},
        ],
        meta={"ts": "2026-11-02T13:00:00", "source": "vendor"},
    )
    gw = QuoteGateway(sdk, cfg={"page_size": 0, "currency": "USD"})

    print("配置：", gw.cfg)
    print(f"分页：{gw.page_size} 条/页")
    render(gw.load())
    print("快照：", gw.stamp())


if __name__ == "__main__":
    main()
