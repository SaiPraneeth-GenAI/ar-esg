import json
import uuid

import boto3
from botocore.exceptions import ClientError

from app.core.config import get_settings


class CognitoAdminError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _client():
    settings = get_settings()
    return boto3.client("cognito-idp", region_name=settings.cognito_region)


def _attributes(email: str, user_id: str, tenant_id: str, roles: list[str]) -> list[dict[str, str]]:
    return [
        {"Name": "email", "Value": email},
        {"Name": "email_verified", "Value": "true"},
        {"Name": "custom:user_id", "Value": user_id},
        {"Name": "custom:tenant_id", "Value": tenant_id},
        {"Name": "custom:roles", "Value": json.dumps(roles, separators=(",", ":"))},
    ]


def _raise(exc: ClientError) -> None:
    error = exc.response.get("Error", {})
    code = error.get("Code", "CognitoError")
    status_code = 409 if code in {"UsernameExistsException", "AliasExistsException"} else 502
    raise CognitoAdminError(status_code, error.get("Message", code)) from exc


def create_auth_user(email: str, password: str, app_metadata: dict, user_id: str | None = None) -> dict:
    settings = get_settings()
    app_user_id = user_id or str(uuid.uuid4())
    try:
        response = _client().admin_create_user(
            UserPoolId=settings.cognito_user_pool_id,
            Username=email,
            UserAttributes=_attributes(
                email,
                app_user_id,
                str(app_metadata["tenant_id"]),
                list(app_metadata.get("roles", [])),
            ),
            TemporaryPassword=password,
            MessageAction="SUPPRESS",
        )
        _client().admin_set_user_password(
            UserPoolId=settings.cognito_user_pool_id,
            Username=email,
            Password=password,
            Permanent=True,
        )
    except ClientError as exc:
        _raise(exc)
    subject = next(
        (item["Value"] for item in response["User"].get("Attributes", []) if item["Name"] == "sub"),
        None,
    )
    return {"id": app_user_id, "auth_subject": subject}


def update_auth_user_app_metadata(username: str, app_metadata: dict, user_id: str) -> None:
    settings = get_settings()
    try:
        _client().admin_update_user_attributes(
            UserPoolId=settings.cognito_user_pool_id,
            Username=username,
            UserAttributes=_attributes(
                username,
                user_id,
                str(app_metadata["tenant_id"]),
                list(app_metadata.get("roles", [])),
            ),
        )
    except ClientError as exc:
        _raise(exc)


def delete_auth_user(username: str) -> None:
    settings = get_settings()
    try:
        _client().admin_delete_user(UserPoolId=settings.cognito_user_pool_id, Username=username)
    except _client().exceptions.UserNotFoundException:
        return
    except ClientError as exc:
        _raise(exc)
