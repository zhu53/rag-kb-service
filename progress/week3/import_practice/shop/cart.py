"""购物车。"""

from shop.pricing import compute_total


class Cart:
    def __init__(self) -> None:
        self.items: list = []

    def add(self, name: str, price: int) -> None:
        self.items.append(type("Item", (), {"name": name, "price": price})())

    def total(self) -> int:
        return compute_total(self)

    def empty_cart():
        return Cart()
