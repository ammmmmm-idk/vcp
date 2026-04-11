"""
VCP Transcription Service
==========================
Audio transcription using Groq Whisper API.

Features:
- Real-time audio transcription
- WAV format conversion
- Multi-language support (auto-detect)
- Error handling

Model: Whisper large-v3
Input: WAV audio data
Output: Transcribed text
"""
import asyncio
import io
import os
import wave

import requests

from env_loader import load_env_file


GROQ_TRANSCRIPT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
DEFAULT_TRANSCRIPTION_MODEL = "whisper-large-v3-turbo"
DEFAULT_TRANSCRIPTION_LANGUAGE = "en"
REQUEST_TIMEOUT_SECONDS = 30
WAV_SAMPLE_WIDTH_BYTES = 2


def _transcription_config():
    load_env_file()
    return {
        "api_key": os.getenv("GROQ_API_KEY", "").strip(),
        "model": os.getenv("GROQ_TRANSCRIPTION_MODEL", DEFAULT_TRANSCRIPTION_MODEL).strip() or DEFAULT_TRANSCRIPTION_MODEL,
        "language": os.getenv("GROQ_TRANSCRIPTION_LANGUAGE", DEFAULT_TRANSCRIPTION_LANGUAGE).strip() or DEFAULT_TRANSCRIPTION_LANGUAGE,
    }


def pcm_to_wav_bytes(pcm_bytes: bytes, sample_rate: int, channels: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(WAV_SAMPLE_WIDTH_BYTES)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
    return buffer.getvalue()


def _transcribe_wav_bytes(wav_bytes: bytes) -> str:
    config = _transcription_config()
    api_key = config["api_key"]
    if not api_key:
        raise RuntimeError("Groq API key is missing. Set GROQ_API_KEY in .env.")

    response = requests.post(
        GROQ_TRANSCRIPT_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
        },
        data={
            "model": config["model"],
            "response_format": "json",
            "language": config["language"],
            "temperature": "0",
        },
        files={
            "file": ("call_audio.wav", wav_bytes, "audio/wav"),
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    return str(payload.get("text", "")).strip()


async def transcribe_wav_bytes(wav_bytes: bytes) -> str:
    return await asyncio.to_thread(_transcribe_wav_bytes, wav_bytes)
