"""Email notifications: every finished voice check is emailed to its owner.

EMAIL_BACKEND=smtp sends through the SMTP server in .env (Brevo, Gmail, ...); EMAIL_BACKEND=outbox (the default)
saves each message as an .eml file in backend/data/outbox/ instead, which is handy without an SMTP account.
"""
import smtplib
import ssl
import time
from datetime import datetime
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr

from backend import settings
from voice_checker.texts import TEXTS

APP_URL = settings.FRONTEND_URL   # the Next.js app
FOOTER = ("VoiceDrift is a research prototype, not a medical device. Your recording was checked on your laptop and "
          "then deleted; this email only contains the result.")


def smtp_settings():
    """{"host", "port", "sender"} when emails go out over SMTP, or None when they are saved to the outbox."""
    if settings.EMAIL_BACKEND != "smtp" or not settings.SMTP_HOST:
        return None
    return {"host": settings.SMTP_HOST, "port": settings.SMTP_PORT,
            "sender": settings.EMAIL_FROM or f"VoiceDrift <{settings.SMTP_USERNAME}>"}


def connect(smtp):
    """An open, signed-in SMTP connection (TLS from the start on SMTP_SSL, else upgraded with STARTTLS)."""
    context = ssl.create_default_context()
    if settings.SMTP_SSL:
        server = smtplib.SMTP_SSL(smtp["host"], smtp["port"], timeout=20, context=context)
    else:
        server = smtplib.SMTP(smtp["host"], smtp["port"], timeout=20)
        if settings.SMTP_STARTTLS:
            server.starttls(context=context)
    if settings.SMTP_USERNAME:
        server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
    return server


def send(to, subject, body):
    """Send a plain-text email; returns "sent" or "outbox". Raises OSError / smtplib.SMTPException on failure."""
    smtp = smtp_settings()
    msg = EmailMessage()
    msg["Subject"], msg["To"] = subject, to
    msg["From"] = smtp["sender"] if smtp else "VoiceDrift <voicedrift@localhost>"
    domain = parseaddr(msg["From"])[1].rpartition("@")[2] or "voicedrift.local"
    msg["Date"], msg["Message-ID"] = formatdate(localtime=True), make_msgid(domain=domain)
    msg.set_content(body)
    if smtp is None:
        settings.OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
        (settings.OUTBOX_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 10**6}.eml").write_bytes(bytes(msg))
        return "outbox"
    with connect(smtp) as server:
        server.send_message(msg)
    return "sent"


def what_was_recorded(check):
    """'your reading of “The river market”' or 'your “aaah”'."""
    if check["mode"] == "vowel":
        return "your “aaah”"
    title = TEXTS.get(check["text_id"] or "", {}).get("title")
    return f"your reading of “{title}”" if title else "your reading"


def result_email(name, check):
    """(subject, body) for a finished check, flagged or not."""
    result = check["result"]
    when = datetime.fromtimestamp(check["created"]).strftime("%d %b %Y at %H:%M")
    subject = ("VoiceDrift: your voice check found something to look at" if result["flagged"]
               else "VoiceDrift: your voice check result is ready")
    body = (f"Hi {name},\n\n"
            f"Your laptop checked {what_was_recorded(check)}, sent from {check['device'] or 'your phone'} on {when}.\n\n"
            f"{result['headline']}.\n\n"
            f"{result['detail']}\n\n"
            f"See this result and all your checks in VoiceDrift: {APP_URL}/checks/{check['id']}\n\n"
            f"{FOOTER}\n")
    return subject, body


def test_email(name):
    """(subject, body) for the dashboard's "Send a test email" button."""
    return ("VoiceDrift: test email",
            f"Hi {name},\n\nThis is a test from your VoiceDrift dashboard. The results of your voice checks "
            f"will arrive like this one.\n\n{APP_URL}\n\n{FOOTER}\n")
