"""Send email executor with SMTP support, timeout, and audit logging."""

import email.mime.base
import email.mime.multipart
import email.mime.text
import json
import logging
import os
import signal
import smtplib
import sqlite3
import uuid

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30
_MAX_TIMEOUT = 60


class SendEmailError(Exception):
    """Raised when email validation or sending fails."""


def _get_db_path():
    """Resolve coordination.db path from env or default fallback."""
    return os.environ.get(
        "OPENCLAWD_DB_PATH",
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "orchestrator-dashboard",
            "orchestrator-dashboard",
            "coordination.db",
        ),
    )


def _log_audit(tool_name, arguments, result):
    """Log tool call to the audit_log table."""
    try:
        db_path = _get_db_path()
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            "INSERT INTO audit_log (agent_name, tool_name, arguments, result) VALUES (?, ?, ?, ?)",
            ("send_email_executor", tool_name, json.dumps(arguments), json.dumps(result)),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("Failed to write audit log: %s", e)


def _load_smtp_config():
    """Load SMTP configuration from openclawd.config.yaml notifications.email section."""
    try:
        import sys
        # Add agent-dispatch to path for config import
        agent_dispatch_dir = os.path.join(
            os.path.dirname(__file__), "..", "..", "agent-dispatch"
        )
        parent_dir = os.path.dirname(agent_dispatch_dir)
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)

        from importlib import import_module
        config_mod = import_module("agent-dispatch.config")
        config = config_mod.load_config()
    except Exception:
        config = {}

    notifications = config.get("notifications", {})
    email_config = notifications.get("email", {})
    return email_config


def _timeout_handler(signum, frame):
    """Signal handler for timeout enforcement."""
    raise SendEmailError("Email sending timed out")


def execute(to, subject, body, attachments=None):
    """Send an email via SMTP with config from openclawd.config.yaml.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Email body content (plain text or HTML).
        attachments: Optional list of file paths to attach.

    Returns:
        Dict with 'success' (bool) and 'message_id' (string or None).

    Raises:
        SendEmailError: If email validation or sending fails.
    """
    if not to or not to.strip():
        raise SendEmailError("Recipient address must not be empty")
    if not subject:
        raise SendEmailError("Subject must not be empty")
    if not body:
        raise SendEmailError("Body must not be empty")

    if attachments is None:
        attachments = []

    # Load SMTP config
    smtp_config = _load_smtp_config()
    smtp_host = smtp_config.get("smtp_host", "smtp.gmail.com")
    smtp_port = smtp_config.get("smtp_port", 587)
    from_address = smtp_config.get("from_address", "")
    username_env = smtp_config.get("username_env", "SMTP_USERNAME")
    password_env = smtp_config.get("password_env", "SMTP_PASSWORD")

    username = os.environ.get(username_env, "")
    password = os.environ.get(password_env, "")

    if not from_address:
        from_address = username

    # Set timeout via signal
    old_handler = None
    if hasattr(signal, "SIGALRM"):
        old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(_DEFAULT_TIMEOUT)

    try:
        # Build email message
        if attachments:
            msg = email.mime.multipart.MIMEMultipart()
            msg.attach(email.mime.text.MIMEText(body, "html" if "<html" in body.lower() else "plain"))

            for filepath in attachments:
                if not os.path.isfile(filepath):
                    logger.warning("Attachment file not found, skipping: %s", filepath)
                    continue
                with open(filepath, "rb") as f:
                    part = email.mime.base.MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                import email.encoders
                email.encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f"attachment; filename={os.path.basename(filepath)}",
                )
                msg.attach(part)
        else:
            msg = email.mime.text.MIMEText(body, "html" if "<html" in body.lower() else "plain")

        msg["Subject"] = subject
        msg["From"] = from_address
        msg["To"] = to

        # Generate message ID
        message_id = f"<{uuid.uuid4()}@openclawd>"
        msg["Message-ID"] = message_id

        # Connect and send
        server = smtplib.SMTP(smtp_host, smtp_port, timeout=_DEFAULT_TIMEOUT)
        try:
            server.ehlo()
            if smtp_port == 587:
                server.starttls()
                server.ehlo()
            if username and password:
                server.login(username, password)
            server.sendmail(from_address, [to], msg.as_string())
        finally:
            server.quit()

        result = {"success": True, "message_id": message_id}

        _log_audit(
            "send_email",
            {"to": to, "subject": subject, "attachments_count": len(attachments)},
            result,
        )

        return result

    except SendEmailError:
        raise
    except smtplib.SMTPException as e:
        raise SendEmailError(f"SMTP error: {e}") from e
    except Exception as e:
        raise SendEmailError(f"Failed to send email: {e}") from e
    finally:
        if hasattr(signal, "SIGALRM"):
            signal.alarm(0)
            if old_handler is not None:
                signal.signal(signal.SIGALRM, old_handler)
