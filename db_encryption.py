"""
Database field encryption using AES-256-GCM for data at rest.
Uses a master key stored in the certs directory.
"""
import os
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pathlib import Path


# Master key file location
KEY_FILE = Path(__file__).parent / "certs" / "db_master.key"


def get_or_create_master_key() -> bytes:
    """Get existing master key or generate a new one"""
    if KEY_FILE.exists():
        with open(KEY_FILE, 'rb') as f:
            return f.read()

    # Generate new 256-bit key
    key = AESGCM.generate_key(bit_length=256)

    # Ensure certs directory exists
    KEY_FILE.parent.mkdir(exist_ok=True)

    # Save key securely (in production, use HSM or key management service)
    with open(KEY_FILE, 'wb') as f:
        f.write(key)

    # Secure file permissions on Unix systems
    if hasattr(os, 'chmod'):
        os.chmod(KEY_FILE, 0o600)

    return key


# Initialize cipher with master key
_master_key = get_or_create_master_key()
_cipher = AESGCM(_master_key)


def encrypt_field(plaintext: str) -> str:
    """
    Encrypts a database field value.
    Returns base64-encoded: nonce||ciphertext
    """
    if not plaintext:
        return ""

    nonce = os.urandom(12)
    plaintext_bytes = plaintext.encode('utf-8')
    ciphertext = _cipher.encrypt(nonce, plaintext_bytes, None)

    # Combine nonce + ciphertext and encode as base64
    combined = nonce + ciphertext
    return base64.b64encode(combined).decode('ascii')


def decrypt_field(encrypted: str) -> str:
    """
    Decrypts a database field value.
    Expects base64-encoded: nonce||ciphertext
    """
    if not encrypted:
        return ""

    try:
        combined = base64.b64decode(encrypted)
        nonce = combined[:12]
        ciphertext = combined[12:]

        plaintext_bytes = _cipher.decrypt(nonce, ciphertext, None)
        return plaintext_bytes.decode('utf-8')
    except Exception:
        # If decryption fails, return empty (data may not be encrypted yet)
        return ""
