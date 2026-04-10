"""
Message encryption module using AES-256 in GCM mode for authenticated encryption.
Each message is encrypted with a unique nonce for security.
"""
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import base64


class MessageEncryption:
    """Handles AES-256-GCM encryption/decryption for chat messages"""

    def __init__(self, key: bytes = None):
        """
        Initialize with a 256-bit (32-byte) encryption key.
        If no key provided, generates a new random key.
        """
        if key is None:
            key = AESGCM.generate_key(bit_length=256)
        elif len(key) != 32:
            raise ValueError("Key must be exactly 32 bytes for AES-256")

        self.cipher = AESGCM(key)
        self.key = key

    def encrypt(self, plaintext: str) -> dict:
        """
        Encrypts a plaintext message.
        Returns dict with base64-encoded nonce and ciphertext.
        """
        # Generate a random 12-byte nonce (96 bits, recommended for GCM)
        nonce = os.urandom(12)

        # Encrypt the message (GCM provides authentication automatically)
        plaintext_bytes = plaintext.encode('utf-8')
        ciphertext = self.cipher.encrypt(nonce, plaintext_bytes, None)

        # Return as base64 for JSON transmission
        return {
            "nonce": base64.b64encode(nonce).decode('ascii'),
            "ciphertext": base64.b64encode(ciphertext).decode('ascii')
        }

    def decrypt(self, nonce_b64: str, ciphertext_b64: str) -> str:
        """
        Decrypts an encrypted message.
        Raises exception if authentication fails (tampered message).
        """
        nonce = base64.b64decode(nonce_b64)
        ciphertext = base64.b64decode(ciphertext_b64)

        # Decrypt and verify authenticity
        plaintext_bytes = self.cipher.decrypt(nonce, ciphertext, None)
        return plaintext_bytes.decode('utf-8')

    def get_key_b64(self) -> str:
        """Returns the encryption key as base64 string for storage/transmission"""
        return base64.b64encode(self.key).decode('ascii')

    @staticmethod
    def from_key_b64(key_b64: str) -> 'MessageEncryption':
        """Creates a MessageEncryption instance from a base64-encoded key"""
        key = base64.b64decode(key_b64)
        return MessageEncryption(key)
