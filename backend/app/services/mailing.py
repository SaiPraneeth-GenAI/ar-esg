import httpx

from app.core.config import get_settings


class MailingError(Exception):
    pass


async def send_email(to: str, subject: str, html_body: str, text_body: str | None = None) -> None:
    """Sends transactional email via Resend's API.

    Replaces the original SMTP-based engine: Microsoft has been retiring
    Basic Auth for SMTP client submission on 365/Exchange Online, which made
    raw SMTP a hard block for any Microsoft-hosted mailbox -- not an
    occasional failure. Enviqo now sends from its own address/domain rather
    than through any given tenant's mailbox, which is also the right model
    for a reusable product rather than something reconfigured per tenant.

    PRE-LAUNCH TODO: currently sends from Resend's shared sandbox domain
    (onboarding@resend.dev), which is fine for a demo but restricts
    deliverability (e.g. sandbox mode only reliably delivers to the
    account's own verified address). Before real production use with a
    paying tenant, verify Enviqo's own sending domain in Resend (SPF/DKIM/
    DMARC) and update EMAIL_FROM accordingly.
    """
    settings = get_settings()
    if not settings.email_provider_api_key:
        raise MailingError("EMAIL_PROVIDER_API_KEY is not configured")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {settings.email_provider_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": settings.email_from,
                "to": [to],
                "subject": subject,
                "html": html_body,
                "text": text_body or "",
            },
            timeout=15,
        )
    if resp.status_code >= 400:
        raise MailingError(f"Resend API error {resp.status_code}: {resp.text}")
