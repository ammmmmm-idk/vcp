import asyncio
import subprocess
import sys
from datetime import datetime
from typing import Dict
import protocol
import database

# Track connections only (No more history memory!)
groups: Dict[str, Dict[asyncio.StreamWriter, str]] = {}

async def broadcast_user_list(group_id):
    """Tells everyone in the room who is currently online."""
    if group_id in groups:
        usernames = list(groups[group_id].values())
        payload = {"action": "user_list", "users": usernames}
        for writer in list(groups[group_id].keys()):
            try:
                await protocol.send_message(writer, payload)
            except: pass

def get_timestamp():
    return datetime.now().strftime("%H:%M")


async def broadcast(group_id: str, payload: dict, sender_writer: asyncio.StreamWriter = None):
    if group_id not in groups:
        return

    if "timestamp" not in payload:
        payload["timestamp"] = get_timestamp()

    # --- FIX 1: Save both chats AND files to the persistent Database ---
    action = payload.get("action")
    sender = payload.get("sender")

    if sender != "System":
        if action == "chat":
            await database.save_message(
                group_id, sender, payload.get("msg"),
                payload.get("color", "#E2E8F0"), payload["timestamp"]
            )
        elif action == "file":
            # We save the file event using a special text tag
            filename = payload.get("filename")
            await database.save_message(
                group_id, sender, f"__FILE__:{filename}",
                payload.get("color", "#E2E8F0"), payload["timestamp"]
            )
    # -------------------------------------------------------------------

    for writer in list(groups[group_id].keys()):
        if writer != sender_writer:
            try:
                await protocol.send_message(writer, payload)
            except Exception:
                pass


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    current_group_id = None

    try:
        while True:
            payload = await protocol.receive_message(reader)
            if payload is None:
                break

            action = payload.get("action")

            if action == "join":
                current_group_id = payload.get("group_id")
                client_group_name = payload.get("group_name", "Unknown Group")
                username = payload.get("username", "Unknown User")

                if current_group_id not in groups:
                    groups[current_group_id] = {}

                groups[current_group_id][writer] = username
                await broadcast_user_list(current_group_id)

                # Fetch official name and last 50 messages from the Database
                await database.create_or_update_group(current_group_id, client_group_name)
                official_name = await database.get_group_name(current_group_id)
                recent_messages = await database.get_recent_messages(current_group_id, limit=50)

                history_payload = {
                    "action": "history",
                    "group_name": official_name,
                    "messages": recent_messages
                }
                await protocol.send_message(writer, history_payload)

            elif action == "chat" and current_group_id:
                payload["timestamp"] = get_timestamp()
                await broadcast(current_group_id, payload, sender_writer=writer)

            elif action == "file" and current_group_id:
                payload["timestamp"] = get_timestamp()
                # We use sender_writer=None so the sender gets the broadcast too,
                # which triggers their UI to draw the image / download button!
                await broadcast(current_group_id, payload, sender_writer=None)

            elif action == "rename" and current_group_id:
                new_name = payload.get("new_name")
                await database.create_or_update_group(current_group_id, new_name)
                rename_payload = {"action": "rename", "group_id": current_group_id, "new_name": new_name}
                await broadcast(current_group_id, rename_payload, sender_writer=writer)

            elif action == "ping":
                pass


    except Exception as e:

        pass

    finally:

        # 1. Remove user from the group dictionary

        if current_group_id in groups and writer in groups[current_group_id]:
            del groups[current_group_id][writer]
            await broadcast_user_list(current_group_id)

        try:

            writer.close()

            await writer.wait_closed()

        except Exception:

            pass  # The client already killed the socket, we don't care!


async def main():
    # --- NEW: Boot up the File Server in the background ---
    print("🚀 Launching File Server on Port 8889...")
    subprocess.Popen([sys.executable, "file_server.py"])
    # ------------------------------------------------------

    # --- NEWER: Boot up the Video Signaling Server ---
    print("🎥 Launching Video Server on Port 8890...")
    subprocess.Popen([sys.executable, "video_server.py"])
    # ------------------------------------------------------

    await database.init_db()  # Ensure tables exist before server boots

    # Start the main Chat Server
    server = await asyncio.start_server(handle_client, '0.0.0.0', 8888)
    print("🟢 Main Chat Server is running on Port 8888...")

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())