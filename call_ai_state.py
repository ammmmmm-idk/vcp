from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime


TRANSCRIPT_MAX_ENTRIES_PER_ROOM = 100
TRANSCRIPT_CONTEXT_LIMIT = 40


@dataclass
class TranscriptEntry:
    speaker: str
    text: str
    timestamp: str


class CallTranscriptStore:
    def __init__(self, max_entries_per_room: int = TRANSCRIPT_MAX_ENTRIES_PER_ROOM):
        self.max_entries_per_room = max_entries_per_room
        self._entries_by_room = defaultdict(lambda: deque(maxlen=self.max_entries_per_room))

    def append_entry(self, room_id: str, speaker: str, text: str, timestamp: str | None = None):
        cleaned_text = text.strip()
        if not room_id or not speaker or not cleaned_text:
            return

        entry_timestamp = timestamp or datetime.now().isoformat(timespec="seconds")
        self._entries_by_room[room_id].append(
            TranscriptEntry(
                speaker=speaker,
                text=cleaned_text,
                timestamp=entry_timestamp,
            )
        )

    def get_recent_entries(self, room_id: str, limit: int = TRANSCRIPT_CONTEXT_LIMIT) -> list[TranscriptEntry]:
        if not room_id:
            return []
        entries = self._entries_by_room.get(room_id)
        if not entries:
            return []
        return list(entries)[-limit:]

    def format_recent_context(self, room_id: str, limit: int = TRANSCRIPT_CONTEXT_LIMIT) -> str:
        lines = []
        for entry in self.get_recent_entries(room_id, limit=limit):
            lines.append(f"[{entry.timestamp}] {entry.speaker}: {entry.text}")
        return "\n".join(lines)

    def clear_room(self, room_id: str):
        self._entries_by_room.pop(room_id, None)
