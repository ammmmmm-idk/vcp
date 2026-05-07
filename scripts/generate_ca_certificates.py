#!/usr/bin/env python3
"""
Generate CA and CA-signed server certificates for VCP
Run this once to create a complete certificate chain
"""
import subprocess
from pathlib import Path

CERTS_DIR = Path(__file__).parent.parent / "certs"
CA_VALID_DAYS = 3650  # 10 years
SERVER_VALID_DAYS = 365  # 1 year


def run_openssl_command(cmd, description):
    """Run an openssl command and handle errors"""
    print(f"[*] {description}...")
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"[OK] {description} completed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] {description} failed")
        print(f"Error: {e.stderr}")
        return False
    except FileNotFoundError:
        print("[ERROR] OpenSSL not found in PATH")
        print("Please install OpenSSL:")
        print("  Windows: Download from https://slproweb.com/products/Win32OpenSSL.html")
        print("  Linux: sudo apt-get install openssl")
        print("  macOS: brew install openssl")
        return False


def generate_ca_certificates():
    """Generate CA and CA-signed server certificates"""
    CERTS_DIR.mkdir(exist_ok=True)

    ca_key = CERTS_DIR / "rootCA.key"
    ca_cert = CERTS_DIR / "rootCA.crt"
    server_key = CERTS_DIR / "server.key"
    server_csr = CERTS_DIR / "server.csr"
    server_cert = CERTS_DIR / "server.crt"

    print("=" * 60)
    print("VCP Certificate Authority Setup")
    print("=" * 60)

    # Step 1: Generate CA private key
    if not ca_key.exists():
        cmd = [
            "openssl", "genrsa",
            "-out", str(ca_key),
            "2048"
        ]
        if not run_openssl_command(cmd, "Generating CA private key"):
            return False
    else:
        print(f"[OK] CA private key already exists: {ca_key}")

    # Step 2: Generate CA certificate
    if not ca_cert.exists():
        cmd = [
            "openssl", "req", "-x509", "-new", "-nodes",
            "-key", str(ca_key),
            "-sha256",
            "-days", str(CA_VALID_DAYS),
            "-out", str(ca_cert),
            "-subj", "/C=IL/ST=State/L=City/O=VCP/OU=IT/CN=VCP Root CA"
        ]
        if not run_openssl_command(cmd, f"Generating CA certificate (valid {CA_VALID_DAYS} days)"):
            return False
    else:
        print(f"[OK] CA certificate already exists: {ca_cert}")

    # Step 3: Generate server private key
    if not server_key.exists():
        cmd = [
            "openssl", "genrsa",
            "-out", str(server_key),
            "2048"
        ]
        if not run_openssl_command(cmd, "Generating server private key"):
            return False
    else:
        print(f"[OK] Server private key already exists: {server_key}")

    # Step 4: Generate server CSR
    cmd = [
        "openssl", "req", "-new",
        "-key", str(server_key),
        "-out", str(server_csr),
        "-subj", "/C=IL/ST=State/L=City/O=VCP/OU=IT/CN=localhost"
    ]
    if not run_openssl_command(cmd, "Generating server certificate signing request (CSR)"):
        return False

    # Step 5: Sign server certificate with CA
    cmd = [
        "openssl", "x509", "-req",
        "-in", str(server_csr),
        "-CA", str(ca_cert),
        "-CAkey", str(ca_key),
        "-CAcreateserial",
        "-out", str(server_cert),
        "-days", str(SERVER_VALID_DAYS),
        "-sha256"
    ]
    if not run_openssl_command(cmd, f"Signing server certificate with CA (valid {SERVER_VALID_DAYS} days)"):
        return False

    print()
    print("=" * 60)
    print("[SUCCESS] Certificate Authority setup completed!")
    print("=" * 60)
    print(f"CA Certificate: {ca_cert}")
    print(f"CA Key: {ca_key}")
    print(f"Server Certificate: {server_cert}")
    print(f"Server Key: {server_key}")
    print()
    print("Certificate Chain:")
    print(f"  Root CA (self-signed) -> Server Certificate (CA-signed)")
    print()
    print("Next steps:")
    print("  1. Servers will use: server.crt + server.key")
    print("  2. Clients will trust: rootCA.crt")
    print()

    return True


if __name__ == "__main__":
    success = generate_ca_certificates()
    if not success:
        exit(1)
