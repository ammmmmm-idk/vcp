# Save as: video_server.py
import asyncio
from protocol import receive_message, send_message

# Dictionary to hold active video connections:
# Format: { "group_id": { "username": writer_object } }
video_rooms = {}


async def handle_video_signaling(reader, writer):
    username = None
    group_id = None

    try:
        while True:
            # Reusing your existing protocol decoder!
            msg = await receive_message(reader)
            if not msg:
                break

            msg_type = msg.get("type")

            # 1. User joins the video call
            if msg_type == "join":
                username = msg["username"]
                group_id = msg["group_id"]

                if group_id not in video_rooms:
                    video_rooms[group_id] = {}

                # Tell everyone currently in the room to call the new person
                for other_user, other_writer in video_rooms[group_id].items():
                    try:
                        await send_message(other_writer, {
                            "type": "new_peer",
                            "username": username
                        })
                    except:
                        pass

                # Add the new user to the room registry
                video_rooms[group_id][username] = writer

            # 2. Route WebRTC data directly to the intended target
            elif msg_type in ["offer", "answer", "candidate"]:
                target_user = msg.get("target")

                if group_id in video_rooms and target_user in video_rooms[group_id]:
                    target_writer = video_rooms[group_id][target_user]
                    try:
                        # Forward the exact message to the target
                        await send_message(target_writer, msg)
                    except Exception as e:
                        print(f"Failed to route {msg_type} to {target_user}: {e}")

    except Exception as e:
        print(f"Video signaling error: {e}")
    finally:
        # Cleanup when a user hangs up or disconnects
        if group_id and username in video_rooms.get(group_id, {}):
            del video_rooms[group_id][username]
            # If room is empty, delete the room
            if not video_rooms[group_id]:
                del video_rooms[group_id]
        writer.close()


async def main():
    print("🎥 Launching Video Signaling Server on Port 8890...")
    server = await asyncio.start_server(handle_video_signaling, '0.0.0.0', 8890)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())