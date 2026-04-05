import asyncio
import os
import protocol
from attachment_security import validate_attachment_filename
from config import FILE_PORT, MAX_UPLOAD_FILE_SIZE, SERVER_BIND_HOST
from logging_config import get_logger

# --- CONFIGURATION ---
HOST = SERVER_BIND_HOST
PORT = FILE_PORT
UPLOAD_DIR = "vcp_uploads"
CHUNK_SIZE = 8192  # 8 Kilobytes

# Ensure the upload directory exists before the server starts
os.makedirs(UPLOAD_DIR, exist_ok=True)

# The Connection Pool: Maximum 10 concurrent file transfers
transfer_limiter = None
logger = get_logger("vcp.file")


async def handle_file_transfer(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """Handles an individual file upload or download over raw TCP."""
    global transfer_limiter

    # Wait in line if there are already 10 active transfers
    async with transfer_limiter:
        peer = writer.get_extra_info('peername')
        logger.info("file_connection_open peer=%s", peer)

        try:
            # 1. Read the custom Phase 1 header
            action, filename, filesize, _file_hash = await protocol.receive_file_header(reader)

            if not action:
                logger.warning("file_invalid_header peer=%s", peer)
                return

            # Sanitize the filename to prevent directory traversal attacks
            safe_filename = os.path.basename(filename)
            is_valid, error_message = validate_attachment_filename(safe_filename)
            if not is_valid:
                logger.warning("file_rejected peer=%s filename=%s reason=%s", peer, filename, error_message)
                return
            file_path = os.path.join(UPLOAD_DIR, safe_filename)

            # ==========================================
            # HANDLE UPLOAD (Client -> Server)
            # ==========================================
            if action == 'U':
                if filesize > MAX_UPLOAD_FILE_SIZE:
                    logger.warning("file_rejected peer=%s filename=%s reason=oversized size=%s", peer, safe_filename, filesize)
                    return
                logger.info("file_upload_start peer=%s filename=%s size=%s", peer, safe_filename, filesize)
                bytes_received = 0

                with open(file_path, 'wb') as f:
                    while bytes_received < filesize:
                        # Calculate how much left to read (don't over-read the last chunk)
                        bytes_left = filesize - bytes_received
                        read_size = min(CHUNK_SIZE, bytes_left)

                        # Read the chunk from the TCP socket and write to disk
                        chunk = await reader.readexactly(read_size)
                        f.write(chunk)
                        bytes_received += len(chunk)

                logger.info("file_upload_complete peer=%s filename=%s size=%s", peer, safe_filename, filesize)

            # ==========================================
            # HANDLE DOWNLOAD (Server -> Client)
            # ==========================================
            elif action == 'D':
                if not os.path.exists(file_path):
                    logger.warning("file_download_missing peer=%s filename=%s", peer, safe_filename)
                    return

                actual_size = os.path.getsize(file_path)
                logger.info("file_download_start peer=%s filename=%s size=%s", peer, safe_filename, actual_size)

                file_hash = protocol.get_file_hash(file_path)

                # First, send a header back so the client knows exactly what is coming
                await protocol.send_file_header(writer, 'D', safe_filename, actual_size, file_hash)

                # Stream the file off the hard drive and into the TCP socket in chunks
                with open(file_path, 'rb') as f:
                    while True:
                        chunk = f.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        writer.write(chunk)
                        await writer.drain()  # Push the chunk out to the network

                logger.info("file_download_complete peer=%s filename=%s size=%s", peer, safe_filename, actual_size)

            else:
                logger.warning("file_unknown_action peer=%s action=%s", peer, action)

        except asyncio.IncompleteReadError:
            logger.warning("file_connection_dropped peer=%s", peer)
        except Exception as e:
            logger.exception("file_transfer_error peer=%s error=%s", peer, e)
        finally:
            writer.close()
            await writer.wait_closed()
            logger.info("file_connection_closed peer=%s", peer)


async def main():
    global transfer_limiter
    # Initialize the Semaphore inside the active asyncio loop
    transfer_limiter = asyncio.Semaphore(10)

    server = await asyncio.start_server(handle_file_transfer, HOST, PORT)
    logger.info("file_server_started host=%s port=%s upload_dir=%s limit=%s", HOST, PORT, os.path.abspath(UPLOAD_DIR), 10)
    print(f"🚀 VCP Raw TCP File Server is running on {HOST}:{PORT}")
    print(f"📁 Saving files to: {os.path.abspath(UPLOAD_DIR)}")
    print(f"🚦 Connection limit: 10 concurrent transfers")
    print("-" * 50)

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("file_server_shutdown")
        print("\n🛑 File Server gracefully shutting down.")
