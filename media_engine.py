# Save as: media_engine.py
import asyncio
import cv2
import numpy as np
from PyQt6.QtGui import QImage
from aiortc import VideoStreamTrack
from av import VideoFrame


class CameraStreamTrack(VideoStreamTrack):
    """Captures frames independently and guarantees hardware release on crash."""

    def __init__(self, local_username, signal_emitter):
        super().__init__()
        self.kind = "video"
        self.local_username = local_username
        self.signal_emitter = signal_emitter

        # THE FIX: Remove the underscore here!
        self.is_muted = False

        self._running = True

        # Using DirectShow for the stable camera driver
        self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        self._latest_frame = None
        self._task = asyncio.create_task(self._camera_loop())

    async def _camera_loop(self):
        """Runs instantly, and safely cleans up hardware in the 'finally' block."""
        try:
            while self._running:
                # 1. ALWAYS read the camera so the hardware buffer stays empty
                ret, frame = self.cap.read()

                # 2. If muted, or if the camera glitched, overwrite it with a black box
                if self.is_muted or not ret:
                    frame = np.zeros((480, 640, 3), dtype=np.uint8)

                    # --- Paint the username on the black frame ---
                    text = f"{self.local_username} (Camera Off)"
                    font = cv2.FONT_HERSHEY_SIMPLEX
                    font_scale = 1
                    thickness = 2
                    color = (255, 255, 255)  # White text

                    # Calculate the center of the frame so it looks perfectly aligned
                    text_size = cv2.getTextSize(text, font, font_scale, thickness)[0]
                    text_x = (640 - text_size[0]) // 2
                    text_y = (480 + text_size[1]) // 2

                    # Draw it onto the frame!
                    cv2.putText(frame, text, (text_x, text_y), font, font_scale, color, thickness, cv2.LINE_AA)

                # 3. Convert to RGB for the Local PyQt UI
                rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb_image.shape
                bytes_per_line = ch * w

                from PyQt6.QtGui import QImage
                qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()

                # Send it to our own local UI
                try:
                    self.signal_emitter.new_frame.emit(f"{self.local_username} (You)", qt_image)
                except RuntimeError:
                    pass

                # 4. THE FIX: Just pass the raw frame to the background queue!
                # (Your recv() function will handle the WebRTC conversion automatically)
                self._latest_frame = frame

                await asyncio.sleep(1 / 15)

        except Exception as e:
            print(f"Camera loop error: {e}")
        finally:
            self._release_camera()

    async def recv(self):
        pts, time_base = await self.next_timestamp()

        while self._latest_frame is None and self._running:
            await asyncio.sleep(0.01)

        frame = self._latest_frame
        if frame is None:
            frame = np.zeros((480, 640, 3), dtype=np.uint8)

        new_frame = VideoFrame.from_ndarray(frame, format="bgr24")
        new_frame.pts = pts
        new_frame.time_base = time_base
        return new_frame

    def _release_camera(self):
        """Safely releases the physical webcam hardware."""
        if hasattr(self, 'cap') and self.cap is not None and self.cap.isOpened():
            self.cap.release()
            self.cap = None
            print("Webcam safely released from memory.")

    def stop(self):
        self._running = False
        if hasattr(self, '_task'):
            self._task.cancel()  # Force kill the zombie task!
        self._release_camera()
        super().stop()
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

    @property
    def is_muted(self):
        return self._is_muted

    @is_muted.setter
    def is_muted(self, value):
        print(f"🎥 CAMERA HARDWARE: Switch flipped! Muted = {value}")
        self._is_muted = value