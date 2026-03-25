"""Email utilities for the Streamlit app."""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import streamlit as st

from state_config import APP_NAME, DOMAIN, MAILING_ADDRESS

APP_URL = f"https://{DOMAIN}"


def send_verification_email(to_email, token):
    """Send a verification email with a one-click confirm link.

    Uses st.secrets["email"]["sender"] and st.secrets["email"]["password"].
    Returns True on success, False on failure.
    """
    verify_url = f"{APP_URL}/?verify={token}"

    subject = f"{APP_NAME} \u2014 Confirm your alert subscription"
    body_html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;color:#333;max-width:600px;margin:0 auto;">
  <div style="background:#1e3a5f;color:white;padding:24px 30px;border-radius:8px 8px 0 0;">
    <h1 style="margin:0;font-size:20px;">Confirm Your {APP_NAME} Alert</h1>
  </div>
  <div style="padding:24px 30px;">
    <p>You (or someone using your email) signed up for exceedance alerts on {APP_NAME}.</p>
    <p>Click the button below to confirm your subscription:</p>
    <p style="text-align:center;margin:28px 0;">
      <a href="{verify_url}"
         style="background:#3a6b1a;color:white;padding:12px 32px;text-decoration:none;
                border-radius:6px;display:inline-block;font-weight:600;">
        Confirm Subscription
      </a>
    </p>
    <p style="color:#888;font-size:13px;">
      If you didn't sign up, you can safely ignore this email.
      This link expires in 48 hours.
    </p>
  </div>
  <hr style="border:none;border-top:1px solid #e0e0e0;margin:0;">
  <!-- Physical mailing address for CAN-SPAM compliance -->
  <div style="background:#f5f5f5;padding:20px 30px;text-align:center;
              font-size:12px;color:#888;border-radius:0 0 8px 8px;line-height:1.6;">
    <p style="margin:0;">
      This email was sent by <a href="{APP_URL}" style="color:#1e3a5f;text-decoration:none;">{APP_NAME}</a>
      ({DOMAIN}) because you subscribed to exceedance alerts.
    </p>
    <p style="margin:10px 0;color:#999;font-size:11px;">
      Exceedance data reflects values reported to EPA ECHO and may not reflect current
      facility status. This is not a compliance determination or legal advice.
      Verify independently before taking action.
    </p>
    <p style="margin:10px 0 0;font-size:11px;">
      &copy; 2026 {APP_NAME} &middot;
      <a href="{APP_URL}" style="color:#1e3a5f;text-decoration:none;">{DOMAIN}</a><br>
      {MAILING_ADDRESS}
    </p>
  </div>
</body>
</html>"""

    try:
        from utils.secrets import get_secret
        sender_email = get_secret("email", "sender")
        sender_password = get_secret("email", "password")

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{APP_NAME} <{sender_email}>"
        msg["To"] = to_email
        msg.attach(MIMEText(body_html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)

        return True
    except Exception as e:
        print(f"EMAIL ERROR: {e}")
        return False
