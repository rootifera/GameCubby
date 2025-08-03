from pydantic import BaseModel


class AppConfigEntry(BaseModel):
    key: str
    value: str

    class Config:
        from_attributes = True
