import smtplib
import ssl
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.utils import formatdate


def _build_message(from_addr, subject, body_text, attachments):
    if attachments:
        msg = MIMEMultipart()
        msg.attach(MIMEText(body_text, "plain"))
        for att in attachments:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(att["data"])
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f'attachment; filename="{att["filename"]}"',
            )
            msg.attach(part)
    else:
        msg = MIMEText(body_text, "plain")

    msg["Subject"] = subject
    msg["From"] = from_addr
    # Set a "To" header pointing at the sender address itself so recipients
    # see a normal-looking header instead of none — actual delivery still
    # goes to each subscriber individually via the envelope recipient list
    # below (BCC-style), so subscribers never see each other's addresses.
    msg["To"] = from_addr
    msg["Date"] = formatdate(localtime=True)
    return msg


def _send_sync(smtp_config, subject, body_text, recipient_emails, attachments=None):
    """Runs in a background thread. Never raises — a mail server problem
    should never surface as an error to whoever just posted an update."""
    if not recipient_emails:
        return

    host = smtp_config.get("host")
    if not host:
        # SMTP not configured yet — treat email as optional infrastructure
        # and skip sending, but log it so this isn't a silent no-op that's
        # impossible to distinguish from "it tried and failed."
        print("[mailer] SMTP_HOST is not set — skipping send. Configure SMTP_HOST/PORT/USERNAME/PASSWORD in .env to enable email.")
        return

    port = smtp_config.get("port") or 587
    username = smtp_config.get("username")
    password = smtp_config.get("password")
    from_addr = smtp_config.get("from_addr") or username
    use_tls = smtp_config.get("use_tls", True)

    msg = _build_message(from_addr, subject, body_text, attachments)

    try:
        context = ssl.create_default_context()
        if use_tls:
            server = smtplib.SMTP(host, port, timeout=10)
            server.starttls(context=context)
        else:
            server = smtplib.SMTP_SSL(host, port, timeout=10, context=context)
        try:
            if username and password:
                server.login(username, password)
            server.sendmail(from_addr, recipient_emails, msg.as_string())
            att_note = f" with {len(attachments)} attachment(s)" if attachments else ""
            print(f"[mailer] Sent notification{att_note} to {len(recipient_emails)} recipient(s): {recipient_emails}")
        finally:
            # If login/sendmail already failed and left the connection dead,
            # quit() itself will raise ("please run connect() first") — and
            # since exceptions raised in a finally block replace whatever
            # exception was already in flight, that would silently swallow
            # the REAL error message. Swallow quit()'s own failure instead,
            # so the actual login/sendmail error is what gets reported below.
            try:
                server.quit()
            except Exception:
                pass
    except Exception as e:
        # Best-effort delivery. Log to stdout (captured by `docker compose logs`)
        # rather than raising — the post itself already succeeded and is live
        # on the board regardless of whether the notification email goes out.
        print(f"[mailer] Failed to send notification email: {e}")


def send_post_notification_async(smtp_config, subject, body_text, recipient_emails, attachments=None):
    """Fire-and-forget: hands the SMTP send off to a background thread so
    posting an update never waits on, or fails because of, the mail server."""
    thread = threading.Thread(
        target=_send_sync,
        args=(smtp_config, subject, body_text, recipient_emails, attachments),
        daemon=True,
    )
    thread.start()
