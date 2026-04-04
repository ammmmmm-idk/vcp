# Save as: media_engine.py
import asyncio
import cv2
import numpy as np
from PyQt6.QtGui import QImage
from aiortc import VideoStreamTrack
from av import VideoFrame


class CameraStreamTrack(VideoStreamTrack):
    """Captures frames independently so the local UI works instantly!"""

    def __init__(self, local_username, signal_emitter):
        super().__init__()
        self.kind = "video"
        self.local_username = local_username
        self.signal_emitter = signal_emitter

        self.cap = cv2.VideoCapture(0)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        self._latest_frame = None
        self._running = True

        # Start a background task that constantly reads the camera
        self._task = asyncio.create_task(self._camera_loop())

    async def _camera_loop(self):
        """Runs instantly, regardless of if someone else is in the call."""
        while self._running:
            ret, frame = self.cap.read()
            if not ret:
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
            else:
                rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb_image.shape
                bytes_per_line = ch * w
                from PyQt6.QtGui import QImage
                qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()

                # FIX: Prevent crash if the UI window was already closed!
                try:
                    self.signal_emitter.new_frame.emit(f"{self.local_username} (You)", qt_image)
                except RuntimeError:
                    self._running = False
                    break  # Stop the camera completely

            self._latest_frame = frame
            await asyncio.sleep(1 / 15)

    async def recv(self):
        """WebRTC network calls this to grab the frame."""
        pts, time_base = await self.next_timestamp()

        # Wait until the camera loop has captured at least one frame
        while self._latest_frame is None and self._running:
            await asyncio.sleep(0.01)

        frame = self._latest_frame
        if frame is None:
            frame = np.zeros((480, 640, 3), dtype=np.uint8)

        new_frame = VideoFrame.from_ndarray(frame, format="bgr24")
        new_frame.pts = pts
        new_frame.time_base = time_base
        return new_frame

    def stop(self):
        self._running = False
        if hasattr(self, 'cap') and self.cap.isOpened():
            self.cap.release()
            print("Webcam released.")
        super().stop()


async def display_stream(track, target_username, signal_emitter):
    """Consumes remote video tracks and shoots them over to PyQt!"""
    try:
        while True:
            frame = await track.recv()
            img = frame.to_ndarray(format="bgr24")

            rgb_image = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_image.shape
            bytes_per_line = ch * w

            from PyQt6.QtGui import QImage
            qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()

            # FIX: Prevent crash if the UI window was already closed!
            try:
                signal_emitter.new_frame.emit(target_username, qt_image)
            except RuntimeError:
                break  # Stop trying to paint the UI

    except Exception as e:
        print(f"Video stream from {target_username} stopped: {e}")