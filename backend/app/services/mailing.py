from email.message import EmailMessage

import aiosmtplib

from app.core.config import get_settings


async def send_email(to: str, subject: str, body: str, html_body: str | None = None) -> None:
    """Sends mail through the tenant's own SMTP account (no third-party email API)."""
    settings = get_settings()

    message = EmailMessage()
    message["From"] = settings.smtp_username
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    await aiosmtplib.send(
        message,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        start_tls=True,
        username=settings.smtp_username,
        password=settings.smtp_app_password,
    )
