"""Send bounded invitation messages through configured SMTP without logging tokens."""

import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import settings
from app.core.errors import ApiError


def send_invitation(email: str, organization_name: str, token: str) -> None:
    """Deliver the confirmation link; the fragment keeps its token out of HTTP access logs."""
    if not settings.smtp_host:
        raise ApiError(503, "mail_unavailable", "Envio de convites não configurado")
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = email
    message["Subject"] = "Convite para o ProcessMind AI"
    link = f"{settings.web_origin.rstrip('/')}/invite#{token}"
    message.set_content(
        f"Você foi convidado para a organização {organization_name}.\n"
        f"Confirme seu e-mail e entre pelo link: {link}\n"
        "Este convite expira em 7 dias. Se não o solicitou, ignore esta mensagem.\n"
    )
    try:
        client: smtplib.SMTP
        if settings.smtp_mode == "ssl":
            client = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=5)
        else:
            client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=5)
        with client:
            if settings.smtp_mode == "starttls":
                client.starttls(context=ssl.create_default_context())
            if settings.smtp_username:
                client.login(settings.smtp_username, settings.smtp_password)
            client.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise ApiError(503, "mail_unavailable", "Não foi possível enviar o convite") from exc
