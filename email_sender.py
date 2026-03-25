import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import streamlit as st

from state_config import APP_NAME, DOMAIN, MAILING_ADDRESS

def send_email(to_email, subject, body):
    """Send email using Gmail SMTP"""
    try:
        # Get credentials via get_secret (Streamlit secrets → env var fallback)
        from utils.secrets import get_secret
        sender_email = get_secret("email", "sender")
        sender_password = get_secret("email", "password")
        
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = to_email
        msg['Subject'] = subject
        
        msg.attach(MIMEText(body, 'html'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False

def send_exceedance_alert(to_email, facility_name, permit_num, exceedances):
    """Send formatted exceedance alert"""
    subject = f"⚠️ {APP_NAME} Alert: {facility_name} Exceedances"
    
    body = f"""
    <h2>New Exceedances Detected</h2>
    <p><strong>Facility:</strong> {facility_name}</p>
    <p><strong>Permit:</strong> {permit_num}</p>
    <p><strong>Exceedances Found:</strong> {len(exceedances)}</p>

    <hr>
    <p>Log into <a href="https://{DOMAIN}">{APP_NAME}</a> to view full details.</p>
    <div style="margin-top:20px;padding-top:16px;border-top:1px solid #e0e0e0;text-align:center;
                font-size:12px;color:#888;line-height:1.6;">
      <p style="margin:0;">
        This alert was sent by {APP_NAME} ({DOMAIN}) because you subscribed to exceedance alerts.
      </p>
      <p style="margin:10px 0;color:#999;font-size:11px;">
        Exceedance data reflects values reported to EPA ECHO and may not reflect current
        facility status. This is not a compliance determination or legal advice.
        Verify independently before taking action.
      </p>
      <p style="margin:10px 0 0;font-size:11px;">
        &copy; 2026 {APP_NAME} &middot; {DOMAIN}<br>
        {MAILING_ADDRESS}
      </p>
    </div>
    """
    
    return send_email(to_email, subject, body)
