"""
VCP File Transfer Client
=========================
Client-side file upload and download functionality.

Features:
- Chunked file transfer (8KB chunks)
- TLS-encrypted connection to file server
- Local file caching (VCP_Cache/)
- Progress tracking
- Filename validation

Connects to: port 8889 (TLS)
"""
import asyncio
import os
import ssl
import protocol
from attachment_security import validate_attachment_filename
from config import MAX_UPLOAD_FILE_SIZE, SERVER_HOST, FILE_PORT

# --- CONFIGURATION ---
HOST = SERVER_HOST
PORT = FILE_PORT
CACHE_DIR = "VCP_Cache"  # The hidden local folder for default downloads
CHUNK_SIZE = 8192  # 8 Kilobytes

# Ensure the local cache directory exists
os.makedirs(CACHE_DIR, exist_ok=True)


async def upload_file(file_path: str) -> bool:
    """Reads a local file in chunks and pushes it over raw TCP to the server."""
    if not os.path.exists(file_path):
        print(f"[-] File not found locally: {file_path}")
        return False

    filename = os.path.basename(file_path)
    filesize = os.path.getsize(file_path)
    writer = None

    is_valid, error_message = validate_attachment_filename(filename)
    if not is_valid:
        print(f"[-] Invalid file name: {error_message}")
        return False

    if filesize > MAX_UPLOAD_FILE_SIZE:
        print(f"[-] File too large: {filename}")
        return False

    try:
        # Create SSL context that doesn't verify self-signed certificates
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        reader, writer = await asyncio.open_connection(HOST, PORT, ssl=ssl_context)
        print(f"[*] Connected to File Server. Uploading: {filename}...")

        # 1. Send the Custom Header
        await protocol.send_file_header(writer, 'U', filename, filesize)

        # 2. Stream the file in 8KB chunks (RAM Shield)
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                writer.write(chunk)
                await writer.drain()

        print(f"[+] Upload strictly complete: {filename}")
        return True

    except Exception as e:
        print(f"[-] Network upload failed: {e}")
        return False

    finally:
        if writer:
            writer.close()
            await writer.wait_closed()


async def download_file(filename: str, destination: str = None) -> str:
    """
    Pulls a file from the server in chunks.
    If 'destination' is provided, it saves there.
    Otherwise, it saves to VCP_Cache.
    """
    safe_filename = os.path.basename(filename)
    is_valid, error_message = validate_attachment_filename(safe_filename)
    if not is_valid:
        print(f"[-] Invalid download file name: {error_message}")
        return None

    # Decide where we are saving this
    if destination:
        save_path = destination
    else:
        save_path = os.path.join(CACHE_DIR, safe_filename)

    # --- CACHE CHECK ---
    # We only skip the download if using the default cache and the file exists.
    # If the user chose a specific 'Save As' path, we download it fresh.
    if not destination and os.path.exists(save_path):
        print(f"[*] Cache Hit! We already have {safe_filename}. Skipping download.")
        return save_path

    writer = None
    try:
        # Create SSL context that doesn't verify self-signed certificates
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        reader, writer = await asyncio.open_connection(HOST, PORT, ssl=ssl_context)
        print(f"[*] Connected to File Server. Requesting: {safe_filename}...")

        # 1. Send a request to Download (Filesize is 0 because we don't know it yet)
        await protocol.send_file_header(writer, 'D', safe_filename, 0)

        # 2. Read the server's reply header
        action, incoming_name, actual_size, expected_hash = await protocol.receive_file_header(reader)

        if not action or action != 'D':
            print(f"[-] Server rejected download (File might not exist).")
            return None

        print(f"[*] Incoming file size: {actual_size} bytes. Downloading...")

        # 3. Download in chunks and save locally
        bytes_received = 0
        with open(save_path, 'wb') as f:
            while bytes_received < actual_size:
                bytes_left = actual_size - bytes_received
                read_size = min(CHUNK_SIZE, bytes_left)

                chunk = await reader.readexactly(read_size)
                f.write(chunk)
                bytes_received += len(chunk)

        actual_hash = protocol.get_file_hash(save_path)
        if actual_hash == expected_hash:
            print(f"✅ Verified: {filename}")
            return save_path
        else:
            print(f"❌ CORRUPTION DETECTED. Deleting: {filename}")
            os.remove(save_path)
            return None


    except asyncio.IncompleteReadError:
        print(f"[-] Server dropped connection mid-download.")
        if os.path.exists(save_path):
            os.remove(save_path)
        return None

    except Exception as e:
        print(f"[-] Network download failed: {e}")
        return None

    finally:
        if writer:
            writer.close()
            await writer.wait_closed()
