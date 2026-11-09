def not_blank(v: str) -> str:
    """strip 后为空则拒绝；非空则返回 strip 后的值。"""
    stripped = v.strip()
    if not stripped:
        raise ValueError("不能全是空白字符")
    return stripped
