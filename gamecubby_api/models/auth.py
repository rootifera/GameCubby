"""
Auth-related request/response models for the API.
Keep routers lean by importing from here.

Usage in routers (next step):
    from models.auth import PasswordChangeRequest
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PasswordChangeRequest(BaseModel):
    """
    Request body for POST /auth/change-password
    """
    current_password: str
    new_password: str = Field(
        ...,
        min_length=6,
        description="New admin password (min length: 6 characters)",
    )


__all__ = [
    "PasswordChangeRequest",
]
