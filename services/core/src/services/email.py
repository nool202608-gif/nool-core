"""Sends the "here are your credentials" email an admin explicitly reviews
and triggers (see api/routes/school_admin.py's send_credentials_email
endpoints) - there is no *automatic* email step anywhere else in this
codebase (see user_provisioning.py's docstring). Plain SMTP via stdlib
smtplib rather than a third-party API, so this needs zero new dependencies;
blank-safe for local dev, same pattern as firebase_project_id in settings.py.
"""

import smtplib
from email.message import EmailMessage

from shared.errors import ConflictError

from src.config.settings import get_settings


def send_email(*, to_email: str, subject: str, message: str) -> None:
    settings = get_settings()
    if not settings.smtp_host or not settings.smtp_from_email:
        raise ConflictError(
            "Email sending isn't configured for this environment yet - set SMTP_HOST and "
            "SMTP_FROM_EMAIL (and SMTP_USERNAME/SMTP_PASSWORD if your provider requires auth)."
        )

    email = EmailMessage()
    email["Subject"] = subject
    email["From"] = settings.smtp_from_email
    email["To"] = to_email
    email.set_content(message)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as client:
        client.starttls()
        if settings.smtp_username and settings.smtp_password:
            client.login(settings.smtp_username, settings.smtp_password)
        client.send_message(email)
