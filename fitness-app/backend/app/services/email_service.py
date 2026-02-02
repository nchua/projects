"""
Email service for sending transactional emails via SendGrid
"""
import os
import logging
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content

logger = logging.getLogger(__name__)

SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
SENDGRID_FROM_EMAIL = os.environ.get("SENDGRID_FROM_EMAIL", "noreply@arise-fitness.app")


def send_password_reset_email(to_email: str, code: str) -> bool:
    """
    Send a password reset email with a 6-digit code

    Args:
        to_email: Recipient email address
        code: 6-digit reset code

    Returns:
        True if email was sent successfully, False otherwise
    """
    if not SENDGRID_API_KEY:
        logger.error("SENDGRID_API_KEY not configured")
        return False

    # Create Solo Leveling themed email content
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #0a0a0f;">
        <div style="max-width: 600px; margin: 0 auto; padding: 40px 20px;">
            <!-- Header -->
            <div style="text-align: center; margin-bottom: 40px;">
                <p style="margin: 0 0 8px 0; font-size: 12px; color: #00e5ff; letter-spacing: 2px; font-family: monospace;">[ SYSTEM ]</p>
                <h1 style="margin: 0; font-size: 36px; color: #ffffff; letter-spacing: 6px; text-shadow: 0 0 20px rgba(0, 229, 255, 0.5);">ARISE</h1>
            </div>

            <!-- Main Content -->
            <div style="background-color: #12121a; border: 1px solid #2a2a3a; border-radius: 4px; padding: 32px;">
                <h2 style="margin: 0 0 16px 0; font-size: 18px; color: #ffffff; font-weight: 600;">Password Reset Request</h2>

                <p style="margin: 0 0 24px 0; font-size: 14px; color: #a0a0b0; line-height: 1.6;">
                    A password reset was requested for your ARISE account. Use the code below to reset your password.
                </p>

                <!-- Code Box -->
                <div style="background-color: #0a0a0f; border: 2px solid #00e5ff; border-radius: 4px; padding: 24px; text-align: center; margin-bottom: 24px;">
                    <p style="margin: 0 0 8px 0; font-size: 12px; color: #a0a0b0; letter-spacing: 1px;">YOUR RESET CODE</p>
                    <p style="margin: 0; font-size: 36px; color: #00e5ff; font-family: monospace; letter-spacing: 8px; font-weight: bold;">{code}</p>
                </div>

                <p style="margin: 0 0 16px 0; font-size: 13px; color: #707080; line-height: 1.6;">
                    This code expires in <strong style="color: #ffffff;">15 minutes</strong>.
                </p>

                <p style="margin: 0; font-size: 13px; color: #707080; line-height: 1.6;">
                    If you didn't request this reset, you can safely ignore this email. Your password will not be changed.
                </p>
            </div>

            <!-- Footer -->
            <div style="text-align: center; margin-top: 32px;">
                <p style="margin: 0; font-size: 12px; color: #505060;">
                    ARISE Fitness - Become the Hunter
                </p>
            </div>
        </div>
    </body>
    </html>
    """

    plain_text = f"""
    ARISE - Password Reset

    A password reset was requested for your account.

    Your reset code: {code}

    This code expires in 15 minutes.

    If you didn't request this reset, you can safely ignore this email.

    ARISE Fitness - Become the Hunter
    """

    message = Mail(
        from_email=Email(SENDGRID_FROM_EMAIL, "ARISE Fitness"),
        to_emails=To(to_email),
        subject="[ARISE] Password Reset Code",
        plain_text_content=Content("text/plain", plain_text),
        html_content=Content("text/html", html_content)
    )

    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        logger.info(f"Password reset email sent to {to_email}, status: {response.status_code}")
        return response.status_code in (200, 202)
    except Exception as e:
        logger.error(f"Failed to send password reset email to {to_email}: {e}")
        return False
