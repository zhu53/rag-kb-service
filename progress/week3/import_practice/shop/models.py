"""数据模型。"""

from dataclasses import dataclass


@dataclass
class Product:
    name: str
    price: int
