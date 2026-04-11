#!/usr/bin/env python3
"""
Generate self-signed SSL certificates for VCP servers
Run this once to create certificates before starting the servers
"""
import os
import subprocess
from pathlib import Path

CERTS_DIR = Path(__file__).parent / "certs"
DAYS_VALID = 365


def generate_certificates():
    """Generate self-signed SSL certificate and key"""
    CERTS_DIR.mkdir(exist_ok=True)

    cert_file = CERTS_DIR / "server.crt"
    key_file = CERTS_DIR / "server.key"

    if cert_file.exists() and key_file.exists():
        print(f"[OK] Certificates already exist in {CERTS_DIR}/")
        print(f"  - Certificate: {cert_file}")
        print(f"  - Private Key: {key_file}")
        return

    print(f"Generating self-signed SSL certificate...")
    print(f"Valid for {DAYS_VALID} days")

    # Generate private key and certificate in one command
    cmd = [
        "openssl", "req", "-x509",
        "-newkey", "rsa:2048",
        "-keyout", str(key_file),
        "-out", str(cert_file),
        "-days", str(DAYS_VALID),
        "-nodes",  # No password
        "-subj", "/C=IL/ST=State/L=City/O=VCP/CN=localhost"
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"[OK] Certificate generated successfully!")
        print(f"  - Certificate: {cert_file}")
        print(f"  - Private Key: {key_file}")
        print()
        print("NOTE: This is a self-signed certificate for development/testing only")
        print("Clients will need to ignore SSL verification warnings")
    except FileNotFoundError:
        print("ERROR: OpenSSL not found in PATH")
        print("Please install OpenSSL:")
        print("  Windows: Download from https://slproweb.com/products/Win32OpenSSL.html")
        print("  Linux: sudo apt-get install openssl")
        print("  macOS: brew install openssl")
        return False
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Failed to generate certificate")
        print(f"Command output: {e.stderr.decode()}")
        return False

    return True


if __name__ == "__main__":
    success = generate_certificates()
    if not success:
        exit(1)
