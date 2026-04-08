import aiosqlite
import os
import secrets
import time
import uuid

DB_NAME = "vcp_local.db"
AI_HISTORY_LIMIT = 24


async def init_db():
    """Initializes the database and creates all necessary tables."""
    async with aiosqlite.connect(DB_NAME) as db:
        # 1. Users Table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fullname TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
        """)
        # 2. Groups Table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                group_id TEXT PRIMARY KEY,
                group_name TEXT NOT NULL,
                owner_email TEXT
            )
        """)
        # 3. User Memberships (Who is in which group)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_groups (
                user_email TEXT NOT NULL,
                group_id TEXT NOT NULL,
                UNIQUE(user_email, group_id)
            )
        """)
        # 4. Message History Table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT,
                group_id TEXT NOT NULL,
                sender TEXT NOT NULL,
                msg TEXT NOT NULL,
                color TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_sessions (
                token TEXT PRIMARY KEY,
                user_email TEXT NOT NULL,
                expires_at REAL NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ai_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_email TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        cursor = await db.execute("PRAGMA table_info(messages)")
        existing_columns = {row[1] for row in await cursor.fetchall()}
        if "message_id" not in existing_columns:
            await db.execute("ALTER TABLE messages ADD COLUMN message_id TEXT")

        cursor = await db.execute("PRAGMA table_info(groups)")
        group_columns = {row[1] for row in await cursor.fetchall()}
        if "owner_email" not in group_columns:
            await db.execute("ALTER TABLE groups ADD COLUMN owner_email TEXT")

        await db.execute("""
            UPDATE messages
            SET message_id = printf('legacy-%d', id)
            WHERE message_id IS NULL OR message_id = ''
        """)

        # Ensure the global lobby always exists
        await db.execute("INSERT OR IGNORE INTO groups (group_id, group_name) VALUES (?, ?)",
                         ("global-lobby-001", "Lobby"))
        await db.execute("""
            UPDATE groups
            SET owner_email = (
                SELECT ug.user_email
                FROM user_groups ug
                WHERE ug.group_id = groups.group_id
                ORDER BY rowid ASC
                LIMIT 1
            )
            WHERE group_id != 'global-lobby-001'
              AND (owner_email IS NULL OR owner_email = '')
        """)
        await db.execute("DELETE FROM chat_sessions WHERE expires_at <= ?", (time.time(),))
        await db.commit()


# --- USER AUTH FUNCTIONS ---
async def create_user(fullname: str, email: str, password_hash: str) -> bool:
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("INSERT INTO users (fullname, email, password_hash) VALUES (?, ?, ?)",
                             (fullname, email, password_hash))
            await db.commit()
            return True
    except aiosqlite.IntegrityError:
        return False


async def get_user_by_email(email: str):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE email = ?", (email,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def create_chat_session(email: str, ttl_seconds: int = 3600) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = time.time() + ttl_seconds
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM chat_sessions WHERE user_email = ?", (email,))
        await db.execute(
            "INSERT INTO chat_sessions (token, user_email, expires_at) VALUES (?, ?, ?)",
            (token, email, expires_at)
        )
        await db.commit()
    return token


async def validate_chat_session(email: str, token: str) -> bool:
    now = time.time()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM chat_sessions WHERE expires_at <= ?", (now,))
        cursor = await db.execute(
            "SELECT 1 FROM chat_sessions WHERE user_email = ? AND token = ? LIMIT 1",
            (email, token)
        )
        row = await cursor.fetchone()
        await db.commit()
        return row is not None


# --- GROUP PERSISTENCE FUNCTIONS ---
async def create_or_update_group(group_id: str, group_name: str, owner_email: str | None = None):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT INTO groups (group_id, group_name, owner_email)
            VALUES (?, ?, ?)
            ON CONFLICT(group_id) DO UPDATE SET
                group_name = excluded.group_name,
                owner_email = COALESCE(groups.owner_email, excluded.owner_email)
        """, (group_id, group_name, owner_email))
        await db.commit()


async def add_user_to_group(email: str, group_id: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO user_groups (user_email, group_id) VALUES (?, ?)", (email, group_id))
        await db.commit()


async def remove_user_from_group(email: str, group_id: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM user_groups WHERE user_email = ? AND group_id = ?", (email, group_id))
        await db.commit()


async def get_user_groups(email: str):
    """Fetches the lobby + all groups the user has explicitly joined."""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT g.group_id, g.group_name 
            FROM groups g
            LEFT JOIN user_groups ug ON g.group_id = ug.group_id AND ug.user_email = ?
            WHERE ug.user_email = ? OR g.group_id = 'global-lobby-001'
        """, (email, email))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_group_name(group_id: str) -> str:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT group_name FROM groups WHERE group_id = ?", (group_id,))
        row = await cursor.fetchone()
        return row[0] if row else "Unknown Group"


async def group_exists(group_id: str) -> bool:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT 1 FROM groups WHERE group_id = ? LIMIT 1", (group_id,))
        row = await cursor.fetchone()
        return row is not None


async def is_group_owner(email: str, group_id: str) -> bool:
    if group_id == "global-lobby-001":
        return False

    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT owner_email FROM groups WHERE group_id = ?",
            (group_id,)
        )
        row = await cursor.fetchone()
        return bool(row and row[0] == email)


async def reassign_group_owner(group_id: str):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT user_email FROM user_groups WHERE group_id = ? ORDER BY rowid ASC LIMIT 1",
            (group_id,)
        )
        row = await cursor.fetchone()
        new_owner = row[0] if row else None
        await db.execute(
            "UPDATE groups SET owner_email = ? WHERE group_id = ?",
            (new_owner, group_id)
        )
        await db.commit()


async def user_has_group_access(email: str, group_id: str) -> bool:
    if group_id == "global-lobby-001":
        return True

    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT 1 FROM user_groups WHERE user_email = ? AND group_id = ? LIMIT 1",
            (email, group_id)
        )
        row = await cursor.fetchone()
        return row is not None


# --- MESSAGE PERSISTENCE FUNCTIONS ---
async def save_message(group_id: str, sender: str, msg: str, color: str, timestamp: str, message_id: str | None = None):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO messages (message_id, group_id, sender, msg, color, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (message_id or str(uuid.uuid4()), group_id, sender, msg, color, timestamp)
        )
        await db.commit()


async def get_recent_messages(group_id: str, limit: int = 50):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT message_id, sender, msg, color, timestamp FROM messages 
            WHERE group_id = ? 
            ORDER BY id DESC LIMIT ?
        """, (group_id, limit))
        rows = await cursor.fetchall()
        # Reverse to put them back in chronological order
        return [dict(row) for row in reversed(rows)]


async def save_ai_message(user_email: str, role: str, content: str, created_at: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO ai_messages (user_email, role, content, created_at) VALUES (?, ?, ?, ?)",
            (user_email, role, content, created_at),
        )
        await db.execute(
            """
            DELETE FROM ai_messages
            WHERE user_email = ?
              AND id NOT IN (
                  SELECT id
                  FROM ai_messages
                  WHERE user_email = ?
                  ORDER BY id DESC
                  LIMIT ?
              )
            """,
            (user_email, user_email, AI_HISTORY_LIMIT),
        )
        await db.commit()


async def get_recent_ai_messages(user_email: str, limit: int = AI_HISTORY_LIMIT):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT role, content, created_at
            FROM ai_messages
            WHERE user_email = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_email, limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in reversed(rows)]
