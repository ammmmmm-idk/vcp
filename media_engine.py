# Save as: media_engine.py
import asyncio
import cv2
import numpy as np
from PyQt6.QtGui import QImage
from aiortc import VideoStreamTrack
from av import VideoFrame


# Inside media_engine.py

class CameraStreamTrack(VideoStreamTrack):
    """Captures frames from your physical webcam and feeds them to WebRTC and the UI."""

    # 1. FIX: Added local_username and signal_emitter to the arguments
    def __init__(self, local_username, signal_emitter):
        super().__init__()
        self.kind = "video"
        self.local_username = local_username
        self.signal_emitter = signal_emitter

        self.cap = cv2.VideoCapture(0)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        ret, frame = self.cap.read()

        if not ret:
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
        else:
            # 2. FIX: Paint our own camera directly to our local UI!
            rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_image.shape
            bytes_per_line = ch * w

            from PyQt6.QtGui import QImage
            qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()

            # Send the frame to the UI and label it "(You)"
            self.signal_emitter.new_frame.emit(f"{self.local_username} (You)", qt_image)

        # Send the exact same frame across the network
        new_frame = VideoFrame.from_ndarray(frame, format="bgr24")
        new_frame.pts = pts
        new_frame.time_base = time_base

        await asyncio.sleep(1 / 15)
        return new_frame

    def stop(self):
        if hasattr(self, 'cap') and self.cap.isOpened():
            self.cap.release()
            print("Webcam released.")


async def display_stream(track, target_username, signal_emitter):
    """Consumes remote video tracks and shoots them over to PyQt!"""
    try:
        while True:
            frame = await track.recv()
            img = frame.to_ndarray(format="bgr24")

            # Convert OpenCV BGR to PyQt RGB
            rgb_image = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_image.shape
            bytes_per_line = ch * w

            # THE CRITICAL COPY FUNCTION to prevent memory crashes
            qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()

            # Send to UI
            signal_emitter.new_frame.emit(target_username, qt_image)

    except Exception as e:
        print(f"Video stream from {target_username} stopped: {e}")