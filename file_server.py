import asyncio
import os
import protocol

# --- CONFIGURATION ---
HOST = '127.0.0.1'
PORT = 8889
UPLOAD_DIR = "vcp_uploads"
CHUNK_SIZE = 8192  # 8 Kilobytes

# Ensure the upload directory exists before the server starts
os.makedirs(UPLOAD_DIR, exist_ok=True)

# The Connection Pool: Maximum 10 concurrent file transfers
transfer_limiter = None


async def handle_file_transfer(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """Handles an individual file upload or download over raw TCP."""
    global transfer_limiter

    # Wait in line if there are already 10 active transfers
    async with transfer_limiter:
        peer = writer.get_extra_info('peername')
        print(f"[+] Incoming file connection from {peer}")

        try:
            # 1. Read the custom Phase 1 header
            action, filename, filesize = await protocol.receive_file_header(reader)

            if not action:
                print("[-] Invalid header received. Closing connection.")
                return

            # Sanitize the filename to prevent directory traversal attacks
            safe_filename = os.path.basename(filename)
            file_path = os.path.join(UPLOAD_DIR, safe_filename)

            # ==========================================
            # HANDLE UPLOAD (Client -> Server)
            # ==========================================
            if action == 'U':
                print(f"[*] Receiving Upload: {safe_filename} ({filesize} bytes)")
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

                print(f"[+] Successfully saved {safe_filename}")

            # ==========================================
            # HANDLE DOWNLOAD (Server -> Client)
            # ==========================================
            elif action == 'D':
                if not os.path.exists(file_path):
                    print(f"[-] Requested file not found: {safe_filename}")
                    return

                actual_size = os.path.getsize(file_path)
                print(f"[*] Sending Download: {safe_filename} ({actual_size} bytes)")

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

                print(f"[+] Successfully sent {safe_filename}")

            else:
                print(f"[-] Unknown action: {action}")

        except asyncio.IncompleteReadError:
            print("[-] Connection dropped mid-transfer.")
        except Exception as e:
            print(f"[-] Error handling file transfer: {e}")
        finally:
            writer.close()
            await writer.wait_closed()
            print(f"[-] Connection closed for {peer}")


async def main():
    global transfer_limiter
    # Initialize the Semaphore inside the active asyncio loop
    transfer_limiter = asyncio.Semaphore(10)

    server = await asyncio.start_server(handle_file_transfer, HOST, PORT)
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
        print("\n🛑 File Server gracefully shutting down.")