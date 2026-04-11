"""
VCP Protocol Module
===================
Handles message serialization/deserialization for network communication.
Uses length-prefixed JSON protocol for reliable message framing over TCP.

Message format: [4-byte length][JSON payload]
Supports both regular messages and file transfer headers.
"""
import struct
import json
import asyncio
import hashlib

# --- UTILITIES ---
def get_file_hash(file_path):
    """Generates a SHA-256 hash to verify file integrity."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

# --- MESSAGE PROTOCOL ---
async def send_message(writer: asyncio.StreamWriter, payload: dict):
    payload_bytes = json.dumps(payload).encode('utf-8')
    header = struct.pack('!I', len(payload_bytes))
    writer.write(header + payload_bytes)
    await writer.drain()

async def receive_message(reader: asyncio.StreamReader) -> dict:
    try:
        header_bytes = await reader.readexactly(4)
        payload_length = struct.unpack('!I', header_bytes)[0]
        payload_bytes = await reader.readexactly(payload_length)
        return json.loads(payload_bytes.decode('utf-8'))
    except: return None

async def send_ping(writer: asyncio.StreamWriter):
    """Heartbeat: 'Are you there?'"""
    await send_message(writer, {"action": "ping"})

# --- FILE PROTOCOL (Header updated with Hash) ---
async def send_file_header(writer, action, filename, filesize, file_hash="0"*64):
    action_byte = action.encode('ascii')
    filename_bytes = filename.encode('utf-8')
    name_len = len(filename_bytes)
    hash_bytes = file_hash.encode('ascii') # 64 bytes

    header = struct.pack('!c H', action_byte, name_len)
    writer.write(header + filename_bytes + struct.pack('!Q', filesize) + hash_bytes)
    await writer.drain()

async def receive_file_header(reader: asyncio.StreamReader):
    action = (await reader.readexactly(1)).decode('ascii')
    name_len = struct.unpack('!H', await reader.readexactly(2))[0]
    filename = (await reader.readexactly(name_len)).decode('utf-8')
    filesize = struct.unpack('!Q', await reader.readexactly(8))[0]
    file_hash = (await reader.readexactly(64)).decode('ascii')
    return action, filename, filesize, file_hash


TCP_PORT = 8888
HEADER_SIZE = 4  # 4 bytes for the message length integer
H264_ONLY = True


def pack_message(data: dict) -> bytes:
    """Converts a dictionary to a length-prefixed JSON byte stream."""
    json_data = json.dumps(data).encode('utf-8')
    # 'I' is an unsigned int (4 bytes)
    header = struct.pack('!I', len(json_data))
    return header + json_data


def unpack_header(header_bytes: bytes) -> int:
    """Decodes the 4-byte header to get the payload length."""
    return struct.unpack('!I', header_bytes)[0]


def filter_sdp_for_h264(sdp_string: str) -> str:
    """
    Strips struct, non-H264 codecs from the SDP string to ensure
    the CPU-only encoder doesn't fall back to VP8/VP9.
    """
    if not H264_ONLY:
        return sdp_string

    lines = sdp_string.splitlines()
    filtered_lines = []
    # Simplified logic: Keep H264 payload types (typically 96-100+)
    # and standard WebRTC setup lines.
    for line in lines:
        if "m=video" in line:
            # Force the media line to only advertise H264
            filtered_lines.append("m=video 9 UDP/TLS/RTP/SAVPF 96")
        elif "rtpmap" in line and "H264" not in line and "video" in line:
            continue
        elif "fmtp" in line and "video" in line and "96" not in line:  # 96 is common H264 ID
            continue
        else:
            filtered_lines.append(line)

    return "\n".join(filtered_lines)