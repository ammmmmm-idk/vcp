"""
VCP RTC Peer Connection
========================
WebRTC peer connection wrapper for video/audio calls.

Manages:
- aiortc RTCPeerConnection
- Media tracks (audio/video)
- Data channels
- Connection state

Integrates with: media_engine for A/V sources
"""
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
    def __init__(self, signaling, local_username, local_user_id, signal_emitter, device_preferences, transcript_callback=None):
        self.signaling = signaling
        self.local_username = local_username
        self.local_user_id = local_user_id
        self.signal_emitter = signal_emitter
        self.device_preferences = device_preferences or {}
        self.transcript_callback = transcript_callback
        self.peers = {}
        self.outbound_tracks = {}
        self.peer_display_names = {}

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

    def _resolve_display_name(self, peer_id):
        return self.peer_display_names.get(peer_id, peer_id)

    async def create_peer_connection(self, target_user_id):
        pc = RTCPeerConnection(configuration=self.rtc_config)
        self.peers[target_user_id] = pc

        outbound_tracks = []
        outbound_video_track = self.media_relay.subscribe(self.local_video_track)
        outbound_tracks.append(outbound_video_track)
        pc.addTrack(outbound_video_track)

        if self.local_audio_track is not None:
            outbound_audio_track = self.media_relay.subscribe(self.local_audio_track)
            outbound_tracks.append(outbound_audio_track)
            pc.addTrack(outbound_audio_track)

        self.outbound_tracks[target_user_id] = outbound_tracks

        @pc.on("track")
        def on_track(track):
            display_name = self._resolve_display_name(target_user_id)
            if track.kind == "video":
                print(f"Routing video from {display_name} to UI...")
                asyncio.ensure_future(display_stream(track, display_name, self.signal_emitter))
            elif track.kind == "audio":
                print(f"Routing audio from {display_name} to speakers...")
                asyncio.ensure_future(
                    display_audio_stream(
                        track,
                        display_name,
                        self.speaker_device,
                        self.transcript_callback,
                    )
                )

        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            display_name = self._resolve_display_name(target_user_id)
            print(f"Connection state with {display_name}: {pc.connectionState}")
            if pc.connectionState in ["closed", "failed", "disconnected"]:
                print(f"Peer {display_name} left! Removing their video frame.")
                try:
                    self.signal_emitter.peer_disconnected.emit(display_name)
                except RuntimeError:
                    pass
                await self._release_peer(target_user_id, close_pc=False)

        @pc.on("icecandidate")
        async def on_icecandidate(candidate):
            if target_user_id in self.peers:
                await self.signaling.send_data({
                    "type": "candidate",
                    "target": target_user_id,
                    "sender": self.local_user_id,
                    "sender_name": self.local_username,
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

    async def initiate_call_to(self, target_user_id, target_display_name=None):
        if not target_user_id:
            return
        if target_display_name:
            self.peer_display_names[target_user_id] = target_display_name
        if target_user_id in self.peers:
            return
        pc = await self.create_peer_connection(target_user_id)
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        sdp = filter_sdp_for_h264(pc.localDescription.sdp)
        await self.signaling.send_data({
            "type": "offer",
            "target": target_user_id,
            "sender": self.local_user_id,
            "sender_name": self.local_username,
            "sdp": sdp,
        })

    async def handle_incoming_offer(self, sender_user_id, sdp, sender_display_name=None):
        if not sender_user_id:
            return
        if sender_display_name:
            self.peer_display_names[sender_user_id] = sender_display_name
        if sender_user_id not in self.peers:
            pc = await self.create_peer_connection(sender_user_id)
        else:
            pc = self.peers[sender_user_id]
        await pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type="offer"))
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        sdp = filter_sdp_for_h264(pc.localDescription.sdp)
        await self.signaling.send_data({
            "type": "answer",
            "target": sender_user_id,
            "sender": self.local_user_id,
            "sender_name": self.local_username,
            "sdp": sdp,
        })

    async def handle_incoming_answer(self, sender_user_id, sdp, sender_display_name=None):
        if not sender_user_id:
            return
        if sender_display_name:
            self.peer_display_names[sender_user_id] = sender_display_name
        if sender_user_id in self.peers:
            await self.peers[sender_user_id].setRemoteDescription(
                RTCSessionDescription(sdp=sdp, type="answer")
            )

    async def handle_ice_candidate(self, sender_user_id, candidate_dict, sender_display_name=None):
        if not sender_user_id:
            return
        if sender_display_name:
            self.peer_display_names[sender_user_id] = sender_display_name
        if sender_user_id in self.peers:
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
            await self.peers[sender_user_id].addIceCandidate(candidate)

    async def handle_peer_left(self, sender_user_id):
        if not sender_user_id:
            return
        display_name = self._resolve_display_name(sender_user_id)
        await self._release_peer(sender_user_id, close_pc=True)
        try:
            self.signal_emitter.peer_disconnected.emit(display_name)
        except RuntimeError:
            pass

    async def close_all(self):
        for peer_id in list(self.peers.keys()):
            await self._release_peer(peer_id, close_pc=True)

        if self.local_video_track is not None:
            self.local_video_track.stop()
        if self.local_audio_track is not None:
            self.local_audio_track.stop()

    async def _release_peer(self, target_user_id, close_pc: bool):
        pc = self.peers.pop(target_user_id, None)
        outbound_tracks = self.outbound_tracks.pop(target_user_id, [])
        self.peer_display_names.pop(target_user_id, None)

        if close_pc and pc:
            await pc.close()

        for track in outbound_tracks:
            try:
                track.stop()
            except Exception:
                pass
