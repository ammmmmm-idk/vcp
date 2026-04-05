import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from env_loader import load_env_file


def _smtp_config():
    load_env_file()
    return {
        "server": os.getenv("VCP_SMTP_SERVER", "smtp.gmail.com"),
        "port": int(os.getenv("VCP_SMTP_PORT", "587")),
        "email": os.getenv("VCP_SENDER_EMAIL", ""),
        "password": os.getenv("VCP_SENDER_PASSWORD", ""),
    }


def send_otp_email(target_email: str, otp_code: str):
    """Sends a real email containing the 6-digit OTP."""
    try:
        smtp_config = _smtp_config()
        sender_email = smtp_config["email"]
        sender_password = smtp_config["password"]

        if not sender_email or not sender_password:
            print("[-] Missing SMTP credentials. Fill VCP_SENDER_EMAIL and VCP_SENDER_PASSWORD in .env.")
            return False

        # 1. Create the email container
        message = MIMEMultipart()
        message["From"] = f"VCP Security <{sender_email}>"
        message["To"] = target_email
        message["Subject"] = "Your VCP Verification Code"

        # 2. Design the Email Body (HTML looks more professional)
        html_body = f"""
        <html>
            <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px;">
                <div style="background-color: #ffffff; padding: 40px; border-radius: 10px; text-align: center;">
                    <h2 style="color: #2d3748;">VCP Verification</h2>
                    <p style="color: #4a5568;">Use the code below to complete your login. It expires in 5 minutes.</p>
                    <div style="font-size: 32px; font-weight: bold; color: #48bb78; letter-spacing: 5px; margin: 20px 0;">
                        {otp_code}
                    </div>
                    <p style="color: #718096; font-size: 12px;">If you didn't request this, please ignore this email.</p>
                </div>
            </body>
        </html>
        """
        message.attach(MIMEText(html_body, "html"))

        # 3. Connect to Server and Send
        with smtplib.SMTP(smtp_config["server"], smtp_config["port"]) as server:
            server.starttls()  # Secure the connection
            server.login(sender_email, sender_password)
            server.send_message(message)

        print(f"[+] Email successfully sent to {target_email}")
        return True

    except Exception as e:
        print(f"[-] Failed to send email: {e}")
        return False
