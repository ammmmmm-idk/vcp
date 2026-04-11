"""
Migration script to add encryption keys to existing groups.
Run this once to fix old groups that don't have encryption keys.
"""
import asyncio
import aiosqlite
from message_encryption import MessageEncryption
from db_encryption import encrypt_field

DB_NAME = "vcp_local.db"

async def migrate():
    async with aiosqlite.connect(DB_NAME) as db:
        # Find groups without encryption keys
        cursor = await db.execute(
            "SELECT group_id, group_name FROM groups WHERE encryption_key IS NULL OR encryption_key = ''"
        )
        groups = await cursor.fetchall()

        if not groups:
            print("[OK] All groups already have encryption keys!")
            return

        print(f"[INFO] Found {len(groups)} group(s) without encryption keys")

        for group_id, group_name in groups:
            # Generate new encryption key
            cipher = MessageEncryption()
            encryption_key = cipher.get_key_b64()

            # Encrypt the key before storing
            encrypted_key = encrypt_field(encryption_key)

            # Update the group
            await db.execute(
                "UPDATE groups SET encryption_key = ? WHERE group_id = ?",
                (encrypted_key, group_id)
            )
            print(f"[OK] Added encryption key to group: {group_name} ({group_id})")

        await db.commit()
        print(f"\n[SUCCESS] Migration complete! Added keys to {len(groups)} group(s)")

if __name__ == "__main__":
    print("=" * 60)
    print("VCP Encryption Key Migration")
    print("=" * 60)
    asyncio.run(migrate())
