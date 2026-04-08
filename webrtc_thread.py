import asyncio

from PyQt6.QtCore import QThread

from rtc_peer import MultiPeerManager
from signaling import TCPSignaling


THREAD_JOIN_TIMEOUT_MS = 3000


class WebRTCClientThread(QThread):
    def __init__(self, host, port, username, group_id, signal_emitter, device_preferences=None, transcript_callback=None):
        super().__init__()
        self.host = host
        self.port = port
        self.username = username
        self.group_id = group_id
        self.signal_emitter = signal_emitter
        self.device_preferences = device_preferences or {}
        self.transcript_callback = transcript_callback
        self.running = True

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._network_task())
        finally:
            pending = [task for task in asyncio.all_tasks(self.loop) if not task.done()]
            for task in pending:
                task.cancel()
            if pending:
                self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            self.loop.run_until_complete(self.loop.shutdown_asyncgens())
            self.loop.close()

    async def _network_task(self):
        self.signaling = TCPSignaling()
        try:
            await self.signaling.connect(self.host, self.port)
            self.peer_manager = MultiPeerManager(
                self.signaling,
                self.username,
                self.signal_emitter,
                self.device_preferences,
                transcript_callback=self.transcript_callback,
            )

            await self.signaling.send_data({
                "type": "join",
                "username": self.username,
                "group_id": self.group_id,
            })

            while self.running:
                message = await self.signaling.receive_data()
                if not message:
                    break

                msg_type = message.get("type")

                if msg_type == "new_peer":
                    await self.peer_manager.initiate_call_to(message["username"])
                elif msg_type == "offer":
                    await self.peer_manager.handle_incoming_offer(message["sender"], message["sdp"])
                elif msg_type == "answer":
                    await self.peer_manager.handle_incoming_answer(message["sender"], message["sdp"])
                elif msg_type == "candidate":
                    await self.peer_manager.handle_ice_candidate(message["sender"], message["candidate"])
                elif msg_type == "peer_left":
                    await self.peer_manager.handle_peer_left(message["username"])

        except Exception as e:
            print(f"WebRTC Thread disconnected: {e}")
        finally:
            if hasattr(self, "peer_manager"):
                await self.peer_manager.close_all()

    def stop(self):
        self.running = False

        if hasattr(self, "loop") and self.loop.is_running():
            if hasattr(self, "signaling"):
                self.loop.call_soon_threadsafe(self.signaling.close)

        self.quit()
        self.wait(THREAD_JOIN_TIMEOUT_MS)

    def set_cam_muted(self, is_muted):
        print(f"Camera bridge signal caught. Muted = {is_muted}")
        if hasattr(self, "peer_manager") and self.peer_manager:
            self.peer_manager.set_camera_muted(is_muted)
            print("Camera bridge passed to PeerManager.")
        else:
            print("Camera bridge failed: peer_manager does not exist.")

    def set_mic_muted(self, is_muted):
        print(f"Mic bridge signal caught. Muted = {is_muted}")
        if hasattr(self, "peer_manager") and self.peer_manager:
            self.peer_manager.set_microphone_muted(is_muted)
            print("Mic bridge passed to PeerManager.")
        else:
            print("Mic bridge failed: peer_manager does not exist.")
