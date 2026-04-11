"""
VCP Signaling Client
====================
Client-side WebRTC signaling for video/audio calls.

Wraps TCP connection to signaling server with protocol encoding/decoding.
Used by webrtc_thread for establishing peer connections.

Connects to: port 8890 (TLS)
"""
# Save as: signaling.py
import asyncio
import ssl
from protocol import send_message, receive_message

class TCPSignaling:
    def __init__(self):
        self.reader = None
        self.writer = None

    async def connect(self, host: str, port: int):
        """Connects to the central video switchboard."""
        # Create SSL context that doesn't verify self-signed certificates
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        self.reader, self.writer = await asyncio.open_connection(
            host, port, ssl=ssl_context
        )
        print(f"Connected to {host}:{port}")

    async def send_data(self, data: dict):
        """Uses your protocol.py to safely send JSON."""
        await send_message(self.writer, data)

    async def receive_data(self) -> dict:
        """Uses your protocol.py to safely receive JSON."""
        return await receive_message(self.reader)

    def close(self):
        """NEW: Snaps the network pipe shut to instantly wake up sleeping threads."""
        if self.writer:
            self.writer.close()