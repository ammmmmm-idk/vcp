# Save as: signaling.py
import asyncio
from protocol import send_message, receive_message

class TCPSignaling:
    def __init__(self):
        self.reader = None
        self.writer = None

    async def connect(self, host: str, port: int):
        """Connects to the central video switchboard."""
        self.reader, self.writer = await asyncio.open_connection(host, port)
        print(f"Connected to {host}:{port}")

    async def send_data(self, data: dict):
        """Uses your protocol.py to safely send JSON."""
        await send_message(self.writer, data)

    async def receive_data(self) -> dict:
        """Uses your protocol.py to safely receive JSON."""
        return await receive_message(self.reader)