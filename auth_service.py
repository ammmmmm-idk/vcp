import time
import secrets
import asyncio
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from email_service import send_otp_email

# Initialize the Argon2 hasher
ph = PasswordHasher()

# In-memory dictionary to store OTPs and their expiration times
# Structure: { "email@test.com": {"otp": "123456", "expires_at": 1679000000.0} }
otp_store = {}

OTP_TIME_TO_LIVE = 300  # 5 minutes in seconds


def hash_password(password: str) -> str:
    """Hashes a plaintext password using Argon2."""
    return ph.hash(password)


def verify_password(hashed_password: str, plain_password: str) -> bool:
    """Verifies a password against its hash. Returns True if valid."""
    try:
        return ph.verify(hashed_password, plain_password)
    except VerifyMismatchError:
        return False


async def generate_and_send_otp(email: str) -> bool:
    secure_otp = "".join(str(secrets.randbelow(10)) for _ in range(6))

    otp_store[email] = {
        "otp": secure_otp,
        "expires_at": time.time() + OTP_TIME_TO_LIVE
    }

    # REPLACE the print simulator with the real service
    # We use asyncio.to_thread because sending email is a "blocking" network task
    success = await asyncio.to_thread(send_otp_email, email, secure_otp)
    return success


def validate_otp(email: str, user_provided_otp: str) -> tuple[bool, str]:
    """Validates the OTP. Returns (is_valid, message)."""
    record = otp_store.get(email)

    if not record:
        return False, "No OTP requested for this email."

    if time.time() > record["expires_at"]:
        del otp_store[email]  # Clean up expired OTP
        return False, "OTP has expired. Please request a new one."

    if record["otp"] != user_provided_otp:
        return False, "Invalid OTP."

    # Success! Clear the OTP so it cannot be reused
    del otp_store[email]
    return True, "Success"