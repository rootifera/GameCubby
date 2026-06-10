from pydantic import BaseModel, Field


class FirstRunRequest(BaseModel):
    admin_username: str = Field(..., min_length=3)
    admin_password: str = Field(..., min_length=6)
    igdb_client_id: str
    igdb_client_secret: str
    query_limit: int = 50
    public_downloads_enabled: bool = Field(False)
    file_storage_backend: str = Field("local")
    backup_storage_backend: str = Field("local")
    s3_bucket: str | None = None
    s3_region: str | None = None
    s3_endpoint_url: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_prefix: str | None = None
    s3_presigned_url_expires: int = 900
