import aiosqlite
import os

DB_NAME = "vcp_local.db"


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
                group_name TEXT NOT NULL
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
                group_id TEXT NOT NULL,
                sender TEXT NOT NULL,
                msg TEXT NOT NULL,
                color TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)

        # Ensure the global lobby always exists
        await db.execute("INSERT OR IGNORE INTO groups (group_id, group_name) VALUES (?, ?)",
                         ("global-lobby-001", "Lobby"))
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


# --- GROUP PERSISTENCE FUNCTIONS ---
async def create_or_update_group(group_id: str, group_name: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO groups (group_id, group_name) VALUES (?, ?)", (group_id, group_name))
        await db.commit()


async def add_user_to_group(email: str, group_id: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO user_groups (user_email, group_id) VALUES (?, ?)", (email, group_id))
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


# --- MESSAGE PERSISTENCE FUNCTIONS ---
async def save_message(group_id: str, sender: str, msg: str, color: str, timestamp: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO messages (group_id, sender, msg, color, timestamp) VALUES (?, ?, ?, ?, ?)",
            (group_id, sender, msg, color, timestamp)
        )
        await db.commit()


async def get_recent_messages(group_id: str, limit: int = 50):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT sender, msg, color, timestamp FROM messages 
            WHERE group_id = ? 
            ORDER BY id DESC LIMIT ?
        """, (group_id, limit))
        rows = await cursor.fetchall()
        # Reverse to put them back in chronological order
        return [dict(row) for row in reversed(rows)]