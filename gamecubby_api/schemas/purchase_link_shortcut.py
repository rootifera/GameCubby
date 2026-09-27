from pydantic import BaseModel, Field


class PurchaseLinkShortcutCreate(BaseModel):
    label: str = Field(max_length=100)
    sort_order: int = 0


class PurchaseLinkShortcutUpdate(BaseModel):
    label: str | None = Field(default=None, max_length=100)
    sort_order: int | None = None


class PurchaseLinkShortcut(BaseModel):
    id: int
    label: str
    sort_order: int

    class Config:
        from_attributes = True


class PurchaseLinkShortcutReorderItem(BaseModel):
    id: int = Field(gt=0)
    sort_order: int


class PurchaseLinkShortcutReorderRequest(BaseModel):
    items: list[PurchaseLinkShortcutReorderItem] = Field(min_length=1)
