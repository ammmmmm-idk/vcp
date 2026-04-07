import asyncio

from aiortc import RTCConfiguration, RTCIceServer, RTCSessionDescription, RTCPeerConnection
from aiortc.contrib.media import MediaRelay

from media_engine import (
    CameraStreamTrack,
    MicrophoneStreamTrack,
    display_audio_stream,
    display_stream,
    resolve_audio_input_device,
    resolve_audio_output_device,
    resolve_camera_device,
)
from protocol import filter_sdp_for_h264


DEFAULT_STUN_SERVER_URL = "stun:stun.l.google.com:19302"


class MultiPeerManager:
    def __init__(self, signaling, local_username, signal_emitter, device_preferences):
        self.signaling = signaling
        self.local_username = local_username
        self.signal_emitter = signal_emitter
        self.device_preferences = device_preferences or {}
        self.peers = {}
        self.outbound_tracks = {}

        self.camera_device = resolve_camera_device(self.device_preferences.get("camera_device"))
        self.microphone_device = resolve_audio_input_device(self.device_preferences.get("microphone_device"))
        self.speaker_device = resolve_audio_output_device(self.device_preferences.get("speaker_device"))

        self.local_video_track = CameraStreamTrack(
            self.local_username,
            self.signal_emitter,
            self.camera_device,
        )
        self.local_audio_track = None
        if self.microphone_device is not None:
            try:
                self.local_audio_track = MicrophoneStreamTrack(input_device=self.microphone_device)
            except Exception as exc:
                self.signal_emitter.error_message.emit(
                    f"Microphone unavailable. Starting call without outgoing audio. ({exc})"
                )

        self.media_relay = MediaRelay()
        self.rtc_config = RTCConfiguration(
            iceServers=[RTCIceServer(urls=DEFAULT_STUN_SERVER_URL)]
        )

    def set_camera_muted(self, is_muted):
        if self.local_video_track is not None:
            self.local_video_track.is_muted = is_muted

    def set_microphone_muted(self, is_muted):
        if self.local_audio_track is not None:
            self.local_audio_track.is_muted = is_muted

    async def create_peer_connection(self, target_username):
        pc = RTCPeerConnection(configuration=self.rtc_config)
        self.peers[target_username] = pc

        outbound_tracks = []
        outbound_video_track = self.media_relay.subscribe(self.local_video_track)
        outbound_tracks.append(outbound_video_track)
        pc.addTrack(outbound_video_track)

        if self.local_audio_track is not None:
            outbound_audio_track = self.media_relay.subscribe(self.local_audio_track)
            outbound_tracks.append(outbound_audio_track)
            pc.addTrack(outbound_audio_track)

        self.outbound_tracks[target_username] = outbound_tracks

        @pc.on("track")
        def on_track(track):
            if track.kind == "video":
                print(f"Routing video from {target_username} to UI...")
                asyncio.ensure_future(display_stream(track, target_username, self.signal_emitter))
            elif track.kind == "audio":
                print(f"Routing audio from {target_username} to speakers...")
                asyncio.ensure_future(display_audio_stream(track, target_username, self.speaker_device))

        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            print(f"Connection state with {target_username}: {pc.connectionState}")
            if pc.connectionState in ["closed", "failed", "disconnected"]:
                print(f"Peer {target_username} left! Removing their video frame.")
                try:
                    self.signal_emitter.peer_disconnected.emit(target_username)
                except RuntimeError:
                    pass
                await self._release_peer(target_username, close_pc=False)

        @pc.on("icecandidate")
        async def on_icecandidate(candidate):
            if target_username in self.peers:
                await self.signaling.send_data({
                    "type": "candidate",
                    "target": target_username,
                    "sender": self.local_username,
                    "candidate": {
                        "sdpMid": candidate.sdpMid,
                        "sdpMLineIndex": candidate.sdpMLineIndex,
                        "foundation": candidate.foundation,
                        "component": candidate.component,
                        "protocol": candidate.protocol,
                        "ip": candidate.ip,
                        "port": candidate.port,
                        "priority": candidate.priority,
                        "type": candidate.type,
                    },
                })

        return pc

    async def initiate_call_to(self, target_username):
        if target_username in self.peers:
            return
        pc = await self.create_peer_connection(target_username)
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        sdp = filter_sdp_for_h264(pc.localDescription.sdp)
        await self.signaling.send_data({
            "type": "offer",
            "target": target_username,
            "sender": self.local_username,
            "sdp": sdp,
        })

    async def handle_incoming_offer(self, sender_username, sdp):
        if sender_username not in self.peers:
            pc = await self.create_peer_connection(sender_username)
        else:
            pc = self.peers[sender_username]
        await pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type="offer"))
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        sdp = filter_sdp_for_h264(pc.localDescription.sdp)
        await self.signaling.send_data({
            "type": "answer",
            "target": sender_username,
            "sender": self.local_username,
            "sdp": sdp,
        })

    async def handle_incoming_answer(self, sender_username, sdp):
        if sender_username in self.peers:
            await self.peers[sender_username].setRemoteDescription(
                RTCSessionDescription(sdp=sdp, type="answer")
            )

    async def handle_ice_candidate(self, sender_username, candidate_dict):
        if sender_username in self.peers:
            from aiortc import RTCIceCandidate

            candidate = RTCIceCandidate(
                component=candidate_dict["component"],
                foundation=candidate_dict["foundation"],
                ip=candidate_dict["ip"],
                port=candidate_dict["port"],
                priority=candidate_dict["priority"],
                protocol=candidate_dict["protocol"],
                type=candidate_dict["type"],
                sdpMid=candidate_dict.get("sdpMid"),
                sdpMLineIndex=candidate_dict.get("sdpMLineIndex"),
            )
            await self.peers[sender_username].addIceCandidate(candidate)

    async def handle_peer_left(self, sender_username):
        await self._release_peer(sender_username, close_pc=True)
        try:
            self.signal_emitter.peer_disconnected.emit(sender_username)
        except RuntimeError:
            pass

    async def close_all(self):
        for username in list(self.peers.keys()):
            await self._release_peer(username, close_pc=True)

        if self.local_video_track is not None:
            self.local_video_track.stop()
        if self.local_audio_track is not None:
            self.local_audio_track.stop()

    async def _release_peer(self, target_username, close_pc: bool):
        pc = self.peers.pop(target_username, None)
        outbound_tracks = self.outbound_tracks.pop(target_username, [])

        if close_pc and pc:
            await pc.close()

        for track in outbound_tracks:
            try:
                track.stop()
            except Exception:
                pass
