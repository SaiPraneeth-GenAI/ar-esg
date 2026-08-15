import uuid

from pydantic import BaseModel, EmailStr, field_validator

ALLOWED_ROLES = {"Admin", "Manager", "Approver"}


class UserCreateRequest(BaseModel):
    email: EmailStr
    password: str
    roles: list[str]
    location_id: uuid.UUID

    @field_validator("roles")
    @classmethod
    def validate_roles(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("at least one role is required")
        invalid = set(v) - ALLOWED_ROLES
        if invalid:
            raise ValueError(f"invalid roles: {sorted(invalid)}")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        return v


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    roles: list[str]
    location_name: str | None
    status: str


class LocationResponse(BaseModel):
    id: uuid.UUID
    name: str
