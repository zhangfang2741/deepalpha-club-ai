"""因子类别枚举表（运营可增行，不可删行）。"""

from sqlmodel import Field, SQLModel


class FactorCategory(SQLModel, table=True):
    """因子类别枚举表。"""

    __tablename__ = "factor_categories"

    name: str = Field(primary_key=True, max_length=30)
    label: str = Field(..., max_length=40)  # "动量" / "均值回归" 等显示名
    icon: str | None = Field(default=None, max_length=20)
    sort_order: int = Field(default=0)