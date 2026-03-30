import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- CONFIGURATION ---
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "v1deoca11proj3ct@gmail.com"  # Replace with your email
SENDER_PASSWORD = "bovx ynah dcwm eipt"  # Replace with your App Password


def send_otp_email(target_email: str, otp_code: str):
    """Sends a real email containing the 6-digit OTP."""
    try:
        # 1. Create the email container
        message = MIMEMultipart()
        message["From"] = f"VCP Security <{SENDER_EMAIL}>"
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
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()  # Secure the connection
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(message)

        print(f"[+] Email successfully sent to {target_email}")
        return True

    except Exception as e:
        print(f"[-] Failed to send email: {e}")
        return False