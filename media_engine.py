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


VIDEO_DEVICE_INDEX = 0
VIDEO_BACKEND = cv2.CAP_DSHOW
VIDEO_FRAME_WIDTH = 640
VIDEO_FRAME_HEIGHT = 480
VIDEO_FRAME_CHANNELS = 3
VIDEO_TARGET_FPS = 25
VIDEO_FRAME_DELAY_SECONDS = 1 / VIDEO_TARGET_FPS
VIDEO_FRAME_SHAPE = (VIDEO_FRAME_HEIGHT, VIDEO_FRAME_WIDTH, VIDEO_FRAME_CHANNELS)
VIDEO_FONT = cv2.FONT_HERSHEY_SIMPLEX
VIDEO_FONT_SCALE = 1
VIDEO_FONT_THICKNESS = 2
VIDEO_FONT_COLOR = (255, 255, 255)
VIDEO_PIXEL_FORMAT = "bgr24"
VIDEO_UI_PIXEL_FORMAT = QImage.Format.Format_RGB888
VIDEO_FALLBACK_LABEL_SUFFIX = " (Camera Off)"
VIDEO_LOCAL_LABEL_SUFFIX = " (You)"
VIDEO_WAIT_FOR_FRAME_SECONDS = 0.01

AUDIO_SAMPLE_RATE = 48_000
AUDIO_CHANNEL_COUNT = 1
AUDIO_BLOCK_SIZE = 960
AUDIO_SAMPLE_DTYPE = "int16"
AUDIO_LAYOUT_MONO = "mono"
AUDIO_TIME_BASE = fractions.Fraction(1, AUDIO_SAMPLE_RATE)
AUDIO_INPUT_QUEUE_SIZE = 20
AUDIO_OUTPUT_QUEUE_SIZE = 100
AUDIO_OUTPUT_RESAMPLE_FORMAT = "s16"
AUDIO_DEVICE_LATENCY = "low"


def build_blank_video_frame(local_username: str) -> np.ndarray:
    frame = np.zeros(VIDEO_FRAME_SHAPE, dtype=np.uint8)
    text = f"{local_username}{VIDEO_FALLBACK_LABEL_SUFFIX}"
    text_size = cv2.getTextSize(text, VIDEO_FONT, VIDEO_FONT_SCALE, VIDEO_FONT_THICKNESS)[0]
    text_x = (VIDEO_FRAME_WIDTH - text_size[0]) // 2
    text_y = (VIDEO_FRAME_HEIGHT + text_size[1]) // 2
    cv2.putText(
        frame,
        text,
        (text_x, text_y),
        VIDEO_FONT,
        VIDEO_FONT_SCALE,
        VIDEO_FONT_COLOR,
        VIDEO_FONT_THICKNESS,
        cv2.LINE_AA,
    )
    return frame


class CameraStreamTrack(VideoStreamTrack):
    def __init__(self, local_username, signal_emitter):
        super().__init__()
        self.kind = "video"
        self.local_username = local_username
        self.signal_emitter = signal_emitter
        self.is_muted = False
        self._running = True

        self.cap = cv2.VideoCapture(VIDEO_DEVICE_INDEX, VIDEO_BACKEND)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, VIDEO_FRAME_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, VIDEO_FRAME_HEIGHT)
        self.cap.set(cv2.CAP_PROP_FPS, VIDEO_TARGET_FPS)

        self._latest_frame = None
        self._task = asyncio.create_task(self._camera_loop())

    async def _camera_loop(self):
        try:
            while self._running:
                ret, frame = self.cap.read()

                if self.is_muted or not ret:
                    frame = build_blank_video_frame(self.local_username)

                rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                height, width, channels = rgb_image.shape
                bytes_per_line = channels * width
                qt_image = QImage(
                    rgb_image.data,
                    width,
                    height,
                    bytes_per_line,
                    VIDEO_UI_PIXEL_FORMAT,
                ).copy()

                try:
                    self.signal_emitter.new_frame.emit(f"{self.local_username}{VIDEO_LOCAL_LABEL_SUFFIX}", qt_image)
                except RuntimeError:
                    pass

                self._latest_frame = frame
                await asyncio.sleep(VIDEO_FRAME_DELAY_SECONDS)

        except Exception as e:
            print(f"Camera loop error: {e}")
        finally:
            self._release_camera()

    async def recv(self):
        pts, time_base = await self.next_timestamp()

        while self._latest_frame is None and self._running:
            await asyncio.sleep(VIDEO_WAIT_FOR_FRAME_SECONDS)

        frame = self._latest_frame
        if frame is None:
            frame = np.zeros(VIDEO_FRAME_SHAPE, dtype=np.uint8)

        new_frame = VideoFrame.from_ndarray(frame, format=VIDEO_PIXEL_FORMAT)
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
    def __init__(
        self,
        sample_rate: int = AUDIO_SAMPLE_RATE,
        channels: int = AUDIO_CHANNEL_COUNT,
        block_size: int = AUDIO_BLOCK_SIZE,
    ):
        super().__init__()
        self.sample_rate = sample_rate
        self.channels = channels
        self.block_size = block_size
        self.is_muted = False
        self._running = True
        self._pts = 0
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue(maxsize=AUDIO_INPUT_QUEUE_SIZE)
        self._sentinel = object()
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=AUDIO_SAMPLE_DTYPE,
            blocksize=self.block_size,
            latency=AUDIO_DEVICE_LATENCY,
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

        frame = AudioFrame.from_ndarray(
            chunk.T.copy(order="C"),
            format=AUDIO_OUTPUT_RESAMPLE_FORMAT,
            layout=AUDIO_LAYOUT_MONO if self.channels == AUDIO_CHANNEL_COUNT else "stereo",
        )
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
    def __init__(
        self,
        sample_rate: int = AUDIO_SAMPLE_RATE,
        channels: int = AUDIO_CHANNEL_COUNT,
        block_size: int = AUDIO_BLOCK_SIZE,
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.block_size = block_size
        self._queue = queue.Queue(maxsize=AUDIO_OUTPUT_QUEUE_SIZE)
        self._stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=AUDIO_SAMPLE_DTYPE,
            blocksize=self.block_size,
            latency=AUDIO_DEVICE_LATENCY,
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
            return

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
            img = frame.to_ndarray(format=VIDEO_PIXEL_FORMAT)

            rgb_image = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            height, width, channels = rgb_image.shape
            bytes_per_line = channels * width
            qt_image = QImage(
                rgb_image.data,
                width,
                height,
                bytes_per_line,
                VIDEO_UI_PIXEL_FORMAT,
            ).copy()

            try:
                signal_emitter.new_frame.emit(target_username, qt_image)
            except RuntimeError:
                break

    except Exception as e:
        print(f"Video stream from {target_username} stopped: {e}")


async def display_audio_stream(track, target_username):
    player = AudioPlaybackBuffer(
        sample_rate=AUDIO_SAMPLE_RATE,
        channels=AUDIO_CHANNEL_COUNT,
        block_size=AUDIO_BLOCK_SIZE,
    )
    resampler = AudioResampler(
        format=AUDIO_OUTPUT_RESAMPLE_FORMAT,
        layout=AUDIO_LAYOUT_MONO,
        rate=AUDIO_SAMPLE_RATE,
    )
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
