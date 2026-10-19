from urllib.parse import urlparse

import boto3

from app.core.config import get_settings


def _client():
    settings = get_settings()
    return boto3.client("s3", region_name=settings.cognito_region)


def upload_file(path: str, content: bytes, content_type: str) -> str:
    settings = get_settings()
    if not settings.attachment_bucket:
        raise RuntimeError("ATTACHMENT_BUCKET is not configured")
    _client().put_object(
        Bucket=settings.attachment_bucket,
        Key=path,
        Body=content,
        ContentType=content_type or "application/octet-stream",
        ServerSideEncryption="AES256",
    )
    # Store a durable private object reference. Responses turn this into a
    # short-lived signed URL instead of making evidence files public.
    return f"s3://{settings.attachment_bucket}/{path}"


def resolve_file_url(file_url: str) -> str:
    if not file_url.startswith("s3://"):
        return file_url
    settings = get_settings()
    parsed = urlparse(file_url)
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": parsed.netloc, "Key": parsed.path.lstrip("/")},
        ExpiresIn=settings.attachment_url_ttl_seconds,
    )
