import uuid

from pydantic import BaseModel, EmailStr, field_validator

ALLOWED_ROLES = {"Admin", "Manager", "Approver"}


def _validate_roles(v: list[str]) -> list[str]:
    if not v:
        raise ValueError("at least one role is required")
    invalid = set(v) - ALLOWED_ROLES
    if invalid:
        raise ValueError(f"invalid roles: {sorted(invalid)}")
    return v


class UserCreateRequest(BaseModel):
    email: EmailStr
    password: str
    roles: list[str]
    location_id: uuid.UUID

    @field_validator("roles")
    @classmethod
    def validate_roles(cls, v: list[str]) -> list[str]:
        return _validate_roles(v)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        return v


class UserUpdateRequest(BaseModel):
    roles: list[str] | None = None
    location_id: uuid.UUID | None = None

    @field_validator("roles")
    @classmethod
    def validate_roles(cls, v: list[str] | None) -> list[str] | None:
        return _validate_roles(v) if v is not None else v


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    roles: list[str]
    location_name: str | None
    status: str


class LocationResponse(BaseModel):
    id: uuid.UUID
    name: str


class LocationCreateRequest(BaseModel):
    name: str
    address: str | None = None
    plant_type: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name is required")
        return v.strip()


class LocationUpdateRequest(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name is required")
        return v.strip()
