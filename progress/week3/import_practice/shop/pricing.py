"""价格计算。"""


def compute_total(cart) -> int:
    """购物车总价（每件商品打 9 折）。"""
    return sum(item.price for item in cart.items) * 9 // 10
