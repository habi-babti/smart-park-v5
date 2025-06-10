# notifier.py

import smtplib
from email.message import EmailMessage
import re
import os
import pandas as pd
from datetime import datetime
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()

# email config
SMTP_USER = "babtich2@gmail.com"
SMTP_PASS = "kvcjgiarqwbtbbcl"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
LOG_FILE = "notifier_logs.csv"

# Twilio Configuration
TWILIO_SID = os.getenv('TWILIO_SID')
TWILIO_TOKEN = os.getenv('TWILIO_TOKEN')
TWILIO_PHONE = os.getenv('TWILIO_PHONE')


def log_notification(recipient, message, success, notif_type):
    os.makedirs("parking_data", exist_ok=True)
    log_path = os.path.join("parking_data", LOG_FILE)

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "type": notif_type,
        "recipient": recipient,
        "status": "success" if success else "failure",
        "message": message[:200]  # Truncate long messages
    }

    try:
        if not os.path.exists(log_path):
            pd.DataFrame([log_entry]).to_csv(log_path, index=False)
        else:
            pd.DataFrame([log_entry]).to_csv(log_path, mode='a', header=False, index=False)
    except Exception as e:
        print(f"⚠️ Failed to log notification: {e}")


def send_email_notification(to_email, message_body, subject="📢 SmartPark Notification"):
    try:
        msg = EmailMessage()
        msg.set_content(message_body)
        msg['Subject'] = subject
        msg['From'] = SMTP_USER
        msg['To'] = to_email

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)

        log_notification(to_email, message_body, True, "email")
        return True
    except Exception as e:
        print(f"❌ Email failed to {to_email}: {str(e)}")
        log_notification(to_email, message_body, False, "email")
        return False

def send_sms_notification(phone, message_body):
    try:
        # Skip if Twilio credentials aren't configured
        if not all([TWILIO_SID, TWILIO_TOKEN, TWILIO_PHONE]):
            print(f"📱 [SIMULATED] SMS to {phone}: {message_body}")
            log_notification(phone, message_body, True, "sms")
            return True

        client = Client(TWILIO_SID, TWILIO_TOKEN)
        message = client.messages.create(
            body=message_body,
            from_=TWILIO_PHONE,
            to=phone
        )
        log_notification(phone, message_body, True, "sms")
        return True
    except Exception as e:
        print(f"❌ SMS failed to {phone}: {str(e)}")
        log_notification(phone, message_body, False, "sms")
        return False


def notify_user(contact, message):
    contact = contact.strip()

    # Fixed regex patterns (removed extra backslashes)
    if re.match(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", contact):
        return send_email_notification(contact, message)
    elif re.match(r"^\+?\d{7,15}$", contact):
        return send_sms_notification(contact, message)
    else:
        print(f"⚠️ Invalid contact format: {contact}")
        return False