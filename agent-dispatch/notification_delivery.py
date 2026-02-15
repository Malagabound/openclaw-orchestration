"""
OpenClawd Agent Dispatch System - Notification Delivery

US-075: Webhook notification delivery via HTTP POST with retry cascade.
US-076: Email notification delivery via SMTP with retry cascade.
US-077: Desktop notification delivery via macOS osascript.
US-078: Urgency-based notification routing with cascade.
"""

import json
import logging
import smtplib
import subprocess
import sys
import time
import urllib.request
import urllib.error
from email.mime.text import MIMEText
from typing import Any, Dict, Optional

from .structured_logging import get_logger, log_dispatch_event

logger = get_logger("notification_delivery")

# Retry backoff intervals in seconds
WEBHOOK_RETRY_BACKOFFS = [1, 5, 30]
WEBHOOK_TIMEOUT_SECONDS = 10


def send_webhook(url: str, notification_dict: Dict[str, Any]) -> bool:
    """Post a notification as JSON to a webhook URL with retry cascade.

    Makes HTTP POST with the notification as JSON body, retrying up to 3 times
    with exponential backoff (1s, 5s, 30s) on failure.

    Args:
        url: The webhook endpoint URL.
        notification_dict: Notification data to send as JSON body.

    Returns:
        True if delivery succeeded, False after all retries exhausted.
    """
    payload = json.dumps(notification_dict).encode("utf-8")
    max_attempts = len(WEBHOOK_RETRY_BACKOFFS) + 1  # 1 initial + 3 retries

    for attempt in range(max_attempts):
        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=WEBHOOK_TIMEOUT_SECONDS) as resp:
                status = resp.getcode()

            log_dispatch_event(
                logger,
                logging.INFO,
                f"Webhook delivered successfully (attempt {attempt + 1}/{max_attempts}, status {status})",
                extra={"url": url, "attempt": attempt + 1, "status": status},
            )
            return True

        except Exception as exc:
            log_dispatch_event(
                logger,
                logging.WARNING,
                f"Webhook delivery failed (attempt {attempt + 1}/{max_attempts}): {exc}",
                extra={"url": url, "attempt": attempt + 1, "error": str(exc)},
            )

            # If more retries remain, sleep with backoff
            if attempt < len(WEBHOOK_RETRY_BACKOFFS):
                backoff = WEBHOOK_RETRY_BACKOFFS[attempt]
                time.sleep(backoff)

    log_dispatch_event(
        logger,
        logging.ERROR,
        f"Webhook delivery failed after {max_attempts} attempts",
        extra={"url": url, "total_attempts": max_attempts},
    )
    return False


# Retry backoff intervals for email delivery (seconds)
EMAIL_RETRY_BACKOFFS = [1, 5, 30]
EMAIL_TIMEOUT_SECONDS = 10


def send_email_notification(
    to: str,
    subject: str,
    body: str,
    config: Dict[str, Any],
) -> bool:
    """Send an email notification via SMTP with retry cascade.

    Reads SMTP configuration from config['notifications']['email'], connects
    to the SMTP server, and sends the email. Retries up to 3 times with
    backoff (1s, 5s, 30s) on failure.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Email body text.
        config: Configuration dict containing notifications.email section
                with keys: smtp_host, smtp_port, from_addr, to.

    Returns:
        True if email was sent successfully, False after all retries exhausted.
    """
    email_config = config.get("notifications", {}).get("email", {})
    smtp_host = email_config.get("smtp_host", "localhost")
    smtp_port = email_config.get("smtp_port", 25)
    from_addr = email_config.get("from", "openclawd@localhost")

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to

    max_attempts = len(EMAIL_RETRY_BACKOFFS) + 1  # 1 initial + 3 retries

    for attempt in range(max_attempts):
        try:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=EMAIL_TIMEOUT_SECONDS) as server:
                server.sendmail(from_addr, [to], msg.as_string())

            log_dispatch_event(
                logger,
                logging.INFO,
                f"Email delivered successfully (attempt {attempt + 1}/{max_attempts})",
                extra={
                    "to": to,
                    "subject": subject,
                    "attempt": attempt + 1,
                    "smtp_host": smtp_host,
                },
            )
            return True

        except Exception as exc:
            log_dispatch_event(
                logger,
                logging.WARNING,
                f"Email delivery failed (attempt {attempt + 1}/{max_attempts}): {exc}",
                extra={
                    "to": to,
                    "subject": subject,
                    "attempt": attempt + 1,
                    "smtp_host": smtp_host,
                    "error": str(exc),
                },
            )

            # If more retries remain, sleep with backoff
            if attempt < len(EMAIL_RETRY_BACKOFFS):
                backoff = EMAIL_RETRY_BACKOFFS[attempt]
                time.sleep(backoff)

    log_dispatch_event(
        logger,
        logging.ERROR,
        f"Email delivery failed after {max_attempts} attempts",
        extra={
            "to": to,
            "subject": subject,
            "total_attempts": max_attempts,
            "smtp_host": smtp_host,
        },
    )
    return False


def send_desktop_notification(title: str, message: str) -> bool:
    """Send a desktop notification via macOS osascript.

    Spawns a subprocess running osascript with an AppleScript display
    notification command. Only works on macOS (sys.platform == 'darwin').

    Args:
        title: The notification title.
        message: The notification body text.

    Returns:
        True if the notification was sent successfully, False otherwise.
    """
    if sys.platform != "darwin":
        log_dispatch_event(
            logger,
            logging.WARNING,
            f"Desktop notification skipped: unsupported platform '{sys.platform}'",
            extra={"platform": sys.platform, "title": title},
        )
        return False

    applescript = f'display notification "{message}" with title "{title}"'

    try:
        log_dispatch_event(
            logger,
            logging.INFO,
            "Attempting desktop notification delivery",
            extra={"title": title, "message": message},
        )

        result = subprocess.run(
            ["osascript", "-e", applescript],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            log_dispatch_event(
                logger,
                logging.INFO,
                "Desktop notification delivered successfully",
                extra={"title": title},
            )
            return True

        log_dispatch_event(
            logger,
            logging.WARNING,
            f"Desktop notification failed: osascript returned {result.returncode}",
            extra={
                "title": title,
                "returncode": result.returncode,
                "stderr": result.stderr.strip(),
            },
        )
        return False

    except subprocess.TimeoutExpired:
        log_dispatch_event(
            logger,
            logging.WARNING,
            "Desktop notification timed out",
            extra={"title": title, "timeout_seconds": 10},
        )
        return False

    except Exception as exc:
        log_dispatch_event(
            logger,
            logging.ERROR,
            f"Desktop notification error: {exc}",
            extra={"title": title, "error": str(exc)},
        )
        return False


# ── Default delivery rules by urgency ────────────────────────────
# Used when config doesn't specify delivery_rules for an urgency level.
DEFAULT_DELIVERY_RULES: Dict[str, list] = {
    "urgent": ["webhook", "email", "desktop"],
    "critical": ["webhook", "email", "desktop"],
    "high": ["webhook", "desktop"],
    "normal": ["webhook"],
    "low": [],
}


def deliver_notification(
    notification_dict: Dict[str, Any],
    urgency: str,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """Route a notification to channels based on urgency with cascade.

    Reads delivery rules from config['notifications']['delivery_rules'][urgency]
    to determine which channels to try. Cascades to the next channel if the
    current one fails after its built-in retries.

    For 'urgent'/'critical': tries webhook, email, desktop in order.
    For 'high': tries webhook, desktop.
    For 'normal': tries webhook only.
    For 'low': no delivery (DB record only).

    Notification failures never raise exceptions - they are caught and logged.

    Args:
        notification_dict: Notification data dict (must contain 'title' and
                          'message' keys for email/desktop delivery).
        urgency: Urgency level string ('urgent', 'critical', 'high',
                'normal', 'low').
        config: Configuration dict, optionally containing
                config['notifications']['delivery_rules'][urgency]['channels'].

    Returns:
        Dict with 'status' ('delivered' or 'failed') and 'delivered_channels'
        (list of channel names that succeeded).
    """
    try:
        # Read channels from config, fall back to defaults
        rules = config.get("notifications", {}).get("delivery_rules", {})
        urgency_rule = rules.get(urgency, {})

        if isinstance(urgency_rule, dict):
            channels = urgency_rule.get("channels", None)
        else:
            channels = None

        # Fall back to defaults if not in config
        if channels is None:
            channels = DEFAULT_DELIVERY_RULES.get(urgency, [])

        # For 'low' or empty channels: DB record only, no delivery needed
        if not channels:
            log_dispatch_event(
                logger,
                logging.DEBUG,
                f"Notification with urgency '{urgency}': DB record only (no channels)",
                extra={"urgency": urgency},
            )
            return {"status": "delivered", "delivered_channels": []}

        delivered_channels: list = []
        title = notification_dict.get("title", "OpenClawd Notification")
        message = notification_dict.get("message", "")

        for channel in channels:
            try:
                success = False

                if channel == "webhook":
                    webhook_url = (
                        config.get("notifications", {})
                        .get("webhook", {})
                        .get("url", "")
                    )
                    if webhook_url:
                        success = send_webhook(webhook_url, notification_dict)
                    else:
                        log_dispatch_event(
                            logger,
                            logging.WARNING,
                            "Webhook channel skipped: no URL configured",
                            extra={"urgency": urgency},
                        )

                elif channel == "email":
                    email_cfg = config.get("notifications", {}).get("email", {})
                    to_addresses = email_cfg.get("to_addresses", [])
                    if to_addresses:
                        # Send to first configured address
                        success = send_email_notification(
                            to=to_addresses[0],
                            subject=title,
                            body=message,
                            config=config,
                        )
                    else:
                        log_dispatch_event(
                            logger,
                            logging.WARNING,
                            "Email channel skipped: no to_addresses configured",
                            extra={"urgency": urgency},
                        )

                elif channel == "desktop":
                    success = send_desktop_notification(title, message)

                else:
                    log_dispatch_event(
                        logger,
                        logging.WARNING,
                        f"Unknown notification channel '{channel}', skipping",
                        extra={"channel": channel, "urgency": urgency},
                    )

                if success:
                    delivered_channels.append(channel)

            except Exception as channel_exc:
                log_dispatch_event(
                    logger,
                    logging.WARNING,
                    f"Channel '{channel}' raised unexpected error: {channel_exc}",
                    extra={
                        "channel": channel,
                        "urgency": urgency,
                        "error": str(channel_exc),
                    },
                )
                # Cascade: continue to next channel

        if delivered_channels:
            log_dispatch_event(
                logger,
                logging.INFO,
                f"Notification delivered via: {', '.join(delivered_channels)}",
                extra={
                    "urgency": urgency,
                    "delivered_channels": delivered_channels,
                },
            )
            return {"status": "delivered", "delivered_channels": delivered_channels}

        log_dispatch_event(
            logger,
            logging.ERROR,
            f"All notification channels failed for urgency '{urgency}'",
            extra={"urgency": urgency, "channels_attempted": channels},
        )
        return {"status": "failed", "delivered_channels": []}

    except Exception as exc:
        # Notification failures must never block dispatch operations
        log_dispatch_event(
            logger,
            logging.ERROR,
            f"deliver_notification error (non-blocking): {exc}",
            extra={"urgency": urgency, "error": str(exc)},
        )
        return {"status": "failed", "delivered_channels": []}
