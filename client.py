# Save as: client.py
import sys
import asyncio
import uuid
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication
from qasync import QEventLoop

import protocol
from Gui import VCPApp  # Import the View
import file_client
from config import SERVER_HOST, CHAT_PORT


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
        self.heartbeat_task = None
        self.auth_email = None
        self.session_token = None

    def set_auth_context(self, email: str, session_token: str):
        self.auth_email = email
        self.session_token = session_token

    # Update this method signature and join_payload in client.py
    async def connect_to_group(self, group_id: str, group_name: str, username: str, email: str, session_token: str,
                               host: str = SERVER_HOST,
                               port: int = CHAT_PORT):
        self.disconnect()

        try:
            self.reader, self.writer = await asyncio.open_connection(host, port)

            auth_payload = {
                "action": "auth",
                "email": email,
                "session_token": session_token
            }
            await protocol.send_message(self.writer, auth_payload)
            auth_response = await protocol.receive_message(self.reader)
            if not auth_response or auth_response.get("action") != "auth_ack":
                error_message = "Authentication with chat server failed."
                if auth_response and auth_response.get("action") == "error":
                    error_message = auth_response.get("message", error_message)
                self.connection_status.emit("error", error_message)
                self.disconnect()
                return

            # Send BOTH the ID (for routing) and Name (for logging)
            join_payload = {
                "action": "join",
                "group_id": group_id,
                "group_name": group_name
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
            message_id = str(uuid.uuid4())
            payload = {
                "action": "chat",
                "message_id": message_id,
                "sender": sender,
                "msg": msg,
                "color": color
            }
            try:
                await protocol.send_message(self.writer, payload)
                return message_id
            except Exception as e:
                self.connection_status.emit("error", f"Failed to send message: {e}")
                return None
        return None

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
        return success

    async def request_group_action(self, payload: dict, host: str = SERVER_HOST, port: int = CHAT_PORT):
        if not self.auth_email or not self.session_token:
            self.connection_status.emit("error", "Authentication context is missing.")
            return None

        writer = None
        try:
            reader, writer = await asyncio.open_connection(host, port)
            await protocol.send_message(writer, {
                "action": "auth",
                "email": self.auth_email,
                "session_token": self.session_token,
            })
            auth_response = await protocol.receive_message(reader)
            if not auth_response or auth_response.get("action") != "auth_ack":
                self.connection_status.emit("error", "Authentication with chat server failed.")
                return None

            await protocol.send_message(writer, payload)
            response = await protocol.receive_message(reader)
            if response and response.get("action") == "error":
                self.connection_status.emit("error", response.get("message", "Group action failed."))
            return response
        except Exception as e:
            self.connection_status.emit("error", f"Group action failed: {e}")
            return None
        finally:
            if writer:
                writer.close()
                await writer.wait_closed()

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
            self.listen_task = None
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            self.heartbeat_task = None
        if self.writer:
            self.writer.close()
            self.writer = None
        self.reader = None


def main():
    """The true entry point of the VCP Client Application."""
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    # 1. Spin up the Network Manager (Controller)
    net_client = NetworkClient()

    # 2. Spin up the GUI (View) and inject the Manager into it
    window = VCPApp(net_client=net_client)
    window.show()

    # 3. Hand over control to the async event loop
    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()
