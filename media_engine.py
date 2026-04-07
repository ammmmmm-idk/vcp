import asyncio
import fractions
import queue

import cv2
import numpy as np
import sounddevice as sd
from PyQt6.QtGui import QImage
from aiortc import AudioStreamTrack, VideoStreamTrack
from aiortc.mediastreams import MediaStreamError
from av import AudioFrame, VideoFrame
from av.audio.resampler import AudioResampler


class CameraStreamTrack(VideoStreamTrack):
    def __init__(self, local_username, signal_emitter):
        super().__init__()
        self.kind = "video"
        self.local_username = local_username
        self.signal_emitter = signal_emitter
        self.is_muted = False
        self._running = True

        self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        self._latest_frame = None
        self._task = asyncio.create_task(self._camera_loop())

    async def _camera_loop(self):
        try:
            while self._running:
                ret, frame = self.cap.read()

                if self.is_muted or not ret:
                    frame = np.zeros((480, 640, 3), dtype=np.uint8)
                    text = f"{self.local_username} (Camera Off)"
                    font = cv2.FONT_HERSHEY_SIMPLEX
                    font_scale = 1
                    thickness = 2
                    color = (255, 255, 255)
                    text_size = cv2.getTextSize(text, font, font_scale, thickness)[0]
                    text_x = (640 - text_size[0]) // 2
                    text_y = (480 + text_size[1]) // 2
                    cv2.putText(frame, text, (text_x, text_y), font, font_scale, color, thickness, cv2.LINE_AA)

                rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb_image.shape
                bytes_per_line = ch * w
                qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()

                try:
                    self.signal_emitter.new_frame.emit(f"{self.local_username} (You)", qt_image)
                except RuntimeError:
                    pass

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
        if self.cap is not None and self.cap.isOpened():
            self.cap.release()
            self.cap = None
            print("Webcam safely released from memory.")

    def stop(self):
        self._running = False
        if hasattr(self, "_task"):
            self._task.cancel()
        self._release_camera()
        super().stop()


class MicrophoneStreamTrack(AudioStreamTrack):
    def __init__(self, sample_rate: int = 48000, channels: int = 1, block_size: int = 960):
        super().__init__()
        self.sample_rate = sample_rate
        self.channels = channels
        self.block_size = block_size
        self.is_muted = False
        self._running = True
        self._pts = 0
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue(maxsize=20)
        self._sentinel = object()
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
            blocksize=self.block_size,
            callback=self._audio_callback,
        )
        self._stream.start()

    def _audio_callback(self, indata, frames, time_info, status):
        if not self._running:
            return
        chunk = np.zeros_like(indata) if self.is_muted else indata.copy()
        try:
            self._loop.call_soon_threadsafe(self._enqueue_chunk, chunk)
        except RuntimeError:
            pass

    def _enqueue_chunk(self, chunk):
        if self._queue.full():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            self._queue.put_nowait(chunk)
        except asyncio.QueueFull:
            pass

    async def recv(self):
        chunk = await self._queue.get()
        if chunk is self._sentinel:
            raise MediaStreamError
        if chunk.ndim == 1:
            chunk = chunk.reshape(-1, 1)

        layout = "mono" if self.channels == 1 else "stereo"
        frame = AudioFrame.from_ndarray(chunk.T.copy(order="C"), format="s16", layout=layout)
        frame.sample_rate = self.sample_rate
        frame.pts = self._pts
        frame.time_base = fractions.Fraction(1, self.sample_rate)
        frame.duration = self.block_size
        self._pts += chunk.shape[0]
        return frame

    def stop(self):
        self._running = False
        try:
            self._loop.call_soon_threadsafe(self._enqueue_chunk, self._sentinel)
        except RuntimeError:
            pass
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        super().stop()


class AudioPlaybackBuffer:
    def __init__(self, sample_rate: int = 48000, channels: int = 1, block_size: int = 960):
        self.sample_rate = sample_rate
        self.channels = channels
        self.block_size = block_size
        self._queue = queue.Queue(maxsize=100)
        self._stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
            blocksize=self.block_size,
            callback=self._callback,
        )
        self._stream.start()

    def _callback(self, outdata, frames, time_info, status):
        try:
            data = self._queue.get_nowait()
        except queue.Empty:
            outdata.fill(0)
            return

        if data.shape[0] < frames:
            padded = np.zeros((frames, self.channels), dtype=np.int16)
            padded[: data.shape[0], : data.shape[1]] = data
            outdata[:] = padded
        else:
            outdata[:] = data[:frames]

    def write(self, samples: np.ndarray):
        if samples.ndim == 1:
            samples = samples.reshape(-1, 1)

        if samples.shape[1] != self.channels:
            if samples.shape[1] > self.channels:
                samples = samples[:, : self.channels]
            else:
                samples = np.repeat(samples, self.channels, axis=1)

        if samples.dtype != np.int16:
            samples = samples.astype(np.int16)

        if self._queue.full():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass

        try:
            self._queue.put_nowait(samples.copy(order="C"))
        except queue.Full:
            pass

    def stop(self):
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None


async def display_stream(track, target_username, signal_emitter):
    try:
        while True:
            frame = await track.recv()
            img = frame.to_ndarray(format="bgr24")

            rgb_image = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_image.shape
            bytes_per_line = ch * w
            qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()

            try:
                signal_emitter.new_frame.emit(target_username, qt_image)
            except RuntimeError:
                break

    except Exception as e:
        print(f"Video stream from {target_username} stopped: {e}")


async def display_audio_stream(track, target_username):
    player = AudioPlaybackBuffer(sample_rate=48000, channels=1, block_size=960)
    resampler = AudioResampler(format="s16", layout="mono", rate=48000)
    try:
        while True:
            frame = await track.recv()
            for resampled_frame in resampler.resample(frame):
                audio = resampled_frame.to_ndarray()
                if audio.ndim == 1:
                    audio = audio.reshape(1, -1)
                samples = audio.T.copy(order="C")
                player.write(samples)
    except Exception as e:
        print(f"Audio stream from {target_username} stopped: {e}")
    finally:
        player.stop()
