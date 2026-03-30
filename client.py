# Save as: client.py
import sys
import asyncio
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication
from qasync import QEventLoop

import protocol
from database import init_db
from Gui import VCPApp  # Import the View

import file_client
import os


class NetworkClient(QObject):
    # --- PyQt Signals (The Bridge to the GUI) ---
    message_received = pyqtSignal(dict)
    connection_status = pyqtSignal(str, str)
    user_list_received = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.reader = None
        self.writer = None
        self.listen_task = None

    # Update this method signature and join_payload in client.py
    async def connect_to_group(self, group_id: str, group_name: str, username: str, host: str = '192.168.50.33',
                               port: int = 8888):
        self.disconnect()

        try:
            self.reader, self.writer = await asyncio.open_connection(host, port)

            # Send BOTH the ID (for routing) and Name (for logging)
            join_payload = {
                "action": "join",
                "group_id": group_id,
                "group_name": group_name,
                "username": username
            }
            await protocol.send_message(self.writer, join_payload)

            self.connection_status.emit("success", f"Connected securely to {group_name}")
            self.listen_task = asyncio.create_task(self._listen_for_messages())
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        except ConnectionRefusedError:
            self.connection_status.emit("error", "Failed to connect: Backend server is offline.")
        except Exception as e:
            self.connection_status.emit("error", f"Connection error: {e}")

    async def _listen_for_messages(self):
        try:
            while True:
                payload = await protocol.receive_message(self.reader)
                if payload is None:
                    self.connection_status.emit("error", "Disconnected from server.")
                    break

                self.message_received.emit(payload)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.connection_status.emit("error", f"Network error: {e}")

    async def send_chat(self, sender: str, msg: str, color: str = "#F6AD55"):
        if self.writer:
            payload = {
                "action": "chat",
                "sender": sender,
                "msg": msg,
                "color": color
            }
            await protocol.send_message(self.writer, payload)

    async def send_file_notification(self, sender: str, filename: str):
        """Tells the main chat server that a file was successfully uploaded."""
        if self.writer:
            payload = {
                "action": "file",
                "sender": sender,
                "filename": filename
            }
            await protocol.send_message(self.writer, payload)

    async def send_rename(self, group_id: str, new_name: str):
        if self.writer:
            payload = {
                "action": "rename",
                "group_id": group_id,
                "new_name": new_name
            }
            await protocol.send_message(self.writer, payload)

    async def send_file(self, sender: str, file_path: str):
        """Uploads out-of-band to Port 8889."""
        success = await file_client.upload_file(file_path)
        if not success:
            self.connection_status.emit("error", "File upload failed.")

    async def _heartbeat_loop(self):
        """Sends a ping every 20s to prevent silent timeouts."""
        while self.writer:
            try:
                await asyncio.sleep(20)
                await protocol.send_ping(self.writer)
            except:
                self.connection_status.emit("error", "Connection Lost.")
                break

    def disconnect(self):
        if self.listen_task:
            self.listen_task.cancel()
        if self.writer:
            self.writer.close()


def main():
    """The true entry point of the VCP Client Application."""
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    # 1. Initialize the Database
    loop.run_until_complete(init_db())

    # 2. Spin up the Network Manager (Controller)
    net_client = NetworkClient()

    # 3. Spin up the GUI (View) and inject the Manager into it
    window = VCPApp(net_client=net_client)
    window.show()

    # 4. Hand over control to the async event loop
    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()