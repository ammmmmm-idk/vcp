# Save as: webrtc_thread.py
import asyncio
from PyQt6.QtCore import QThread
from signaling import TCPSignaling
from rtc_peer import MultiPeerManager


class WebRTCClientThread(QThread):
    # FIX: Added group_id to the initialization!
    def __init__(self, host, port, username, group_id, signal_emitter):
        super().__init__()
        self.host = host
        self.port = port
        self.username = username
        self.group_id = group_id
        self.signal_emitter = signal_emitter
        self.running = True

    def run(self):
        """This runs in a completely separate CPU thread from the UI."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._network_task())

    async def _network_task(self):
        # 1. FIX: Save signaling to self so we can access it later!
        self.signaling = TCPSignaling()
        try:
            await self.signaling.connect(self.host, self.port)

            # Initialize our multi-person P2P engine and give it the UI bridge
            self.peer_manager = MultiPeerManager(self.signaling, self.username, self.signal_emitter)

            # Tell the central server we joined
            await self.signaling.send_data({
                "type": "join",
                "username": self.username,
                "group_id": self.group_id
            })

            # Listen for routing data forever
            while self.running:
                message = await self.signaling.receive_data()
                if not message:
                    break

                msg_type = message.get('type')

                if msg_type == 'new_peer':
                    await self.peer_manager.initiate_call_to(message['username'])
                elif msg_type == 'offer':
                    await self.peer_manager.handle_incoming_offer(message['sender'], message['sdp'])
                elif msg_type == 'answer':
                    await self.peer_manager.handle_incoming_answer(message['sender'], message['sdp'])
                elif msg_type == 'candidate':
                    await self.peer_manager.handle_ice_candidate(message['sender'], message['candidate'])
                elif msg_type == 'peer_left':
                    await self.peer_manager.handle_peer_left(message['username'])

        except Exception as e:
            print(f"WebRTC Thread disconnected: {e}")
        finally:
            if hasattr(self, 'peer_manager'):
                await self.peer_manager.close_all()

    def stop(self):
        self.running = False

        # Only execute thread cleanup if the loop is still active
        if hasattr(self, 'loop') and self.loop.is_running():
            if hasattr(self, 'peer_manager'):
                import asyncio
                asyncio.run_coroutine_threadsafe(self.peer_manager.close_all(), self.loop)

            # FIX: Safely schedule the network socket to close inside the background loop
            if hasattr(self, 'signaling'):
                self.loop.call_soon_threadsafe(self.signaling.close)

        self.quit()

    def set_cam_muted(self, is_muted):
        print(f"🧵 THREAD BRIDGE: Caught signal! Muted = {is_muted}")
        if hasattr(self, 'peer_manager') and self.peer_manager:
            self.peer_manager.set_camera_muted(is_muted)
            print("✅ THREAD BRIDGE: Passed to PeerManager.")
        else:
            print("❌ THREAD BRIDGE FAILED: peer_manager does not exist!")
