from pydantic import BaseModel, Field


class FirstRunRequest(BaseModel):
    admin_username: str = Field(..., min_length=3)
    admin_password: str = Field(..., min_length=6)
    igdb_client_id: str
    igdb_client_secret: str
    query_limit: int = 50
    public_downloads_enabled: bool = Field(False)