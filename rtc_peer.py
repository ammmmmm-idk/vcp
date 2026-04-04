# Save as: rtc_peer.py
import asyncio
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer
# FIX: Importing the REAL camera
from media_engine import CameraStreamTrack, display_stream
from protocol import filter_sdp_for_h264


class MultiPeerManager:
    # FIX: Added signal_emitter to the arguments
    def __init__(self, signaling, local_username, signal_emitter):
        self.signaling = signaling
        self.local_username = local_username
        self.signal_emitter = signal_emitter

        self.peers = {}

        # Turn on the real webcam and give it the UI bridge!
        self.local_video_track = CameraStreamTrack(self.local_username, self.signal_emitter)

        self.rtc_config = RTCConfiguration(
            iceServers=[RTCIceServer(urls="stun:stun.l.google.com:19302")]
        )

    async def create_peer_connection(self, target_username):
        pc = RTCPeerConnection(configuration=self.rtc_config)
        self.peers[target_username] = pc
        pc.addTrack(self.local_video_track)

        @pc.on("track")
        def on_track(track):
            if track.kind == "video":
                print(f"📡 Routing video from {target_username} to UI...")
                asyncio.ensure_future(display_stream(track, target_username, self.signal_emitter))

        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            print(f"Connection state with {target_username}: {pc.connectionState}")
            # If the network drops or they close their app, trigger the UI cleanup
            if pc.connectionState in ["closed", "failed", "disconnected"]:
                print(f"Peer {target_username} left! Removing their video frame.")

                # FIX: Catch the error if the UI was already deleted
                try:
                    self.signal_emitter.peer_disconnected.emit(target_username)
                except RuntimeError:
                    pass

                if target_username in self.peers:
                    del self.peers[target_username]

        @pc.on("icecandidate")
        async def on_icecandidate(candidate):
            if candidate:
                await self.signaling.send_data({
                    "type": "candidate",
                    "target": target_username,
                    "sender": self.local_username,
                    "candidate": {
                        "component": candidate.component,
                        "foundation": candidate.foundation,
                        "ip": candidate.ip,
                        "port": candidate.port,
                        "priority": candidate.priority,
                        "protocol": candidate.protocol,
                        "type": candidate.type,
                        "sdpMid": candidate.sdpMid,
                        "sdpMLineIndex": candidate.sdpMLineIndex
                    }
                })

        return pc

    async def initiate_call_to(self, target_username):
        print(f"Calling {target_username}...")
        pc = await self.create_peer_connection(target_username)
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)

        # Filter for H.264
        sdp = filter_sdp_for_h264(pc.localDescription.sdp)

        await self.signaling.send_data({
            "type": "offer",
            "target": target_username,
            "sender": self.local_username,
            "sdp": sdp
        })

    async def handle_incoming_offer(self, sender_username, sdp):
        print(f"Call received from {sender_username}! Answering...")
        pc = await self.create_peer_connection(sender_username)
        await pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type="offer"))
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        sdp = filter_sdp_for_h264(pc.localDescription.sdp)

        await self.signaling.send_data({
            "type": "answer",
            "target": sender_username,
            "sender": self.local_username,
            "sdp": sdp
        })

    async def handle_incoming_answer(self, sender_username, sdp):
        if sender_username in self.peers:
            pc = self.peers[sender_username]
            await pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type="answer"))

    async def handle_ice_candidate(self, sender_username, candidate_dict):
        if sender_username in self.peers:
            from aiortc import RTCIceCandidate
            candidate = RTCIceCandidate(
                component=candidate_dict['component'],
                foundation=candidate_dict['foundation'],
                ip=candidate_dict['ip'],
                port=candidate_dict['port'],
                priority=candidate_dict['priority'],
                protocol=candidate_dict['protocol'],
                type=candidate_dict['type'],
                sdpMid=candidate_dict.get('sdpMid'),
                sdpMLineIndex=candidate_dict.get('sdpMLineIndex')
            )
            await self.peers[sender_username].addIceCandidate(candidate)

    async def close_all(self):
        self.local_video_track.stop()
        for pc in self.peers.values():
            await pc.close()