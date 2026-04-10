import asyncio
from collections import defaultdict, deque
import subprocess
import sys
from datetime import datetime
from typing import Dict
import time
import uuid
import secrets
import ssl
from pathlib import Path
import protocol
import database
from auth_service import (
    generate_and_send_otp,
    hash_password,
    validate_otp,
    verify_password,
)
from logging_config import get_logger
from config import (
    CHAT_PORT,
    MAX_FILENAME_LENGTH,
    MAX_GROUP_NAME_LENGTH,
    MAX_MESSAGE_LENGTH,
    SERVER_BIND_HOST,
)
from validators import (
    validate_email,
    validate_group_name,
    validate_message,
    validate_username,
    sanitize_ai_prompt,
    validate_password_strength,
)
from message_encryption import MessageEncryption
from protocol_validator import validate_message_schema

# Track connections only (No more history memory!)
groups: Dict[str, Dict[asyncio.StreamWriter, str]] = {}
action_timestamps = defaultdict(deque)
logger = get_logger("vcp.chat")
RATE_LIMIT_WINDOW_SECONDS = 10
RATE_LIMIT_ACTIONS = 8
pending_signups: Dict[str, dict] = {}
pending_logins: Dict[str, dict] = {}
authenticated_connections: Dict[str, asyncio.StreamWriter] = {}


async def send_error(writer: asyncio.StreamWriter, message: str):
    peer = writer.get_extra_info("peername")
    logger.warning("chat_error_sent peer=%s message=%s", peer, message)
    await protocol.send_message(writer, {"action": "error", "message": message})


def is_rate_limited(writer: asyncio.StreamWriter) -> bool:
    now = time.monotonic()
    timestamps = action_timestamps[writer]
    while timestamps and now - timestamps[0] > RATE_LIMIT_WINDOW_SECONDS:
        timestamps.popleft()

    if len(timestamps) >= RATE_LIMIT_ACTIONS:
        peer = writer.get_extra_info("peername")
        logger.warning("rate_limit_hit peer=%s window=%s limit=%s", peer, RATE_LIMIT_WINDOW_SECONDS, RATE_LIMIT_ACTIONS)
        return True

    timestamps.append(now)
    return False

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
    return datetime.now().isoformat(timespec="seconds")


async def broadcast(group_id: str, payload: dict, sender_writer: asyncio.StreamWriter = None):
    if group_id not in groups:
        return

    if "timestamp" not in payload:
        payload["timestamp"] = get_timestamp()

    if "message_id" not in payload and payload.get("action") in {"chat", "file"}:
        payload["message_id"] = str(uuid.uuid4())

    # --- FIX 1: Save both chats AND files to the persistent Database ---
    action = payload.get("action")
    sender = payload.get("sender")
    message_id = payload.get("message_id")

    if sender != "System":
        if action == "chat":
            await database.save_message(
                group_id, sender, payload.get("msg"),
                payload.get("color", "#E2E8F0"), payload["timestamp"], message_id=message_id
            )
        elif action == "file":
            # We save the file event using a special text tag
            filename = payload.get("filename")
            await database.save_message(
                group_id, sender, f"__FILE__:{filename}",
                payload.get("color", "#E2E8F0"), payload["timestamp"], message_id=message_id
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
    authenticated_user = None
    peer = writer.get_extra_info("peername")
    logger.info("chat_connection_open peer=%s", peer)

    try:
        while True:
            payload = await protocol.receive_message(reader)
            if payload is None:
                break

            # Validate message schema
            is_valid, schema_error = validate_message_schema(payload)
            if not is_valid:
                logger.warning("protocol_violation peer=%s error=%s", peer, schema_error)
                await send_error(writer, f"Protocol error: {schema_error}")
                continue

            action = payload.get("action")

            if action == "signup":
                fullname = payload.get("fullname", "").strip()
                email = payload.get("email", "").strip().lower()
                password = payload.get("password", "").strip()

                if not fullname or not email or not password:
                    await send_error(writer, "Signup requires full name, email, and password.")
                    continue

                # Validate username
                valid_name, name_error = validate_username(fullname)
                if not valid_name:
                    await send_error(writer, name_error)
                    continue

                # Validate email format
                valid_email, email_error = validate_email(email)
                if not valid_email:
                    await send_error(writer, email_error)
                    continue

                # Validate password strength
                valid_password, password_error = validate_password_strength(password)
                if not valid_password:
                    await send_error(writer, password_error)
                    continue

                existing_user = await database.get_user_by_email(email)
                if existing_user:
                    await send_error(writer, "That email is already registered.")
                    continue

                hashed_password = hash_password(password)
                otp_sent = await generate_and_send_otp(email)
                if not otp_sent:
                    await send_error(writer, "Failed to send verification code.")
                    continue

                pending_signups[email] = {
                    "fullname": fullname,
                    "password_hash": hashed_password,
                }
                pending_logins.pop(email, None)
                logger.info("signup_started peer=%s email=%s", peer, email)
                await protocol.send_message(writer, {"action": "signup_ack"})

            elif action == "login":
                email = payload.get("email", "").strip().lower()
                password = payload.get("password", "").strip()

                if not email or not password:
                    await send_error(writer, "Login requires email and password.")
                    continue

                user = await database.get_user_by_email(email)
                if not user or not verify_password(user["password_hash"], password):
                    await send_error(writer, "Invalid email or password.")
                    continue

                otp_sent = await generate_and_send_otp(email)
                if not otp_sent:
                    await send_error(writer, "Failed to send verification code.")
                    continue

                pending_logins[email] = {
                    "fullname": user["fullname"],
                }
                pending_signups.pop(email, None)
                logger.info("login_started peer=%s email=%s", peer, email)
                await protocol.send_message(writer, {"action": "login_ack"})

            elif action == "verify_auth_code":
                email = payload.get("email", "").strip().lower()
                code = payload.get("code", "").strip()

                if not email or not code:
                    await send_error(writer, "Verification requires email and code.")
                    continue

                is_valid, message = validate_otp(email, code)
                if not is_valid:
                    await send_error(writer, message)
                    continue

                if email in pending_signups:
                    signup_data = pending_signups.pop(email)
                    created = await database.create_user(email=email, fullname=signup_data["fullname"], password_hash=signup_data["password_hash"])
                    if not created:
                        await send_error(writer, "That email is already registered.")
                        continue
                    fullname = signup_data["fullname"]
                    logger.info("signup_completed peer=%s email=%s", peer, email)
                elif email in pending_logins:
                    fullname = pending_logins.pop(email)["fullname"]
                    logger.info("login_completed peer=%s email=%s", peer, email)
                else:
                    await send_error(writer, "No pending authentication request for this email.")
                    continue

                db_groups = await database.get_user_groups(email)
                session_token = await database.create_chat_session(email)
                await protocol.send_message(writer, {
                    "action": "auth_success",
                    "username": fullname,
                    "email": email,
                    "groups": db_groups,
                    "session_token": session_token,
                })

            elif action == "auth":
                email = payload.get("email", "").strip().lower()
                session_token = payload.get("session_token", "").strip()
                is_auxiliary_auth = bool(payload.get("auxiliary"))
                if not email:
                    await send_error(writer, "Authentication request is missing email.")
                    continue
                if not session_token:
                    await send_error(writer, "Authentication request is missing session token.")
                    continue

                user = await database.get_user_by_email(email)
                if not user:
                    logger.warning("auth_failed peer=%s email=%s reason=unknown_user", peer, email)
                    await send_error(writer, "Unknown user.")
                    continue
                if not await database.validate_chat_session(email, session_token):
                    logger.warning("auth_failed peer=%s email=%s reason=invalid_session", peer, email)
                    await send_error(writer, "Invalid or expired session.")
                    continue

                authenticated_user = {
                    "email": user["email"],
                    "fullname": user["fullname"]
                }
                if not is_auxiliary_auth:
                    existing_writer = authenticated_connections.get(authenticated_user["email"])
                    if existing_writer and existing_writer is not writer:
                        try:
                            await protocol.send_message(existing_writer, {
                                "action": "error",
                                "message": "This account was logged in from another session."
                            })
                        except Exception:
                            pass
                        try:
                            existing_writer.close()
                        except Exception:
                            pass
                    authenticated_connections[authenticated_user["email"]] = writer
                logger.info("auth_success peer=%s email=%s fullname=%s", peer, authenticated_user["email"], authenticated_user["fullname"])
                await protocol.send_message(writer, {
                    "action": "auth_ack",
                    "email": authenticated_user["email"],
                    "fullname": authenticated_user["fullname"]
                })

            elif action == "join":
                if not authenticated_user:
                    await send_error(writer, "Authenticate before joining a room.")
                    continue
                current_group_id = payload.get("group_id")
                client_group_name = payload.get("group_name", "Unknown Group")
                username = authenticated_user["fullname"]
                user_email = authenticated_user["email"]

                if not current_group_id:
                    await send_error(writer, "Join request is missing room.")
                    continue
                if client_group_name and len(client_group_name.strip()) > MAX_GROUP_NAME_LENGTH:
                    logger.warning("join_denied peer=%s email=%s room=%s reason=group_name_too_long", peer, user_email, current_group_id)
                    await send_error(writer, "Group name is too long.")
                    current_group_id = None
                    continue

                if not await database.user_has_group_access(user_email, current_group_id):
                    logger.warning("join_denied peer=%s email=%s room=%s reason=not_member", peer, user_email, current_group_id)
                    await send_error(writer, "You are not a member of that group.")
                    current_group_id = None
                    continue

                if current_group_id not in groups:
                    groups[current_group_id] = {}

                groups[current_group_id][writer] = username
                logger.info("room_join peer=%s email=%s room=%s", peer, user_email, current_group_id)
                await broadcast_user_list(current_group_id)

                # Fetch official name and last 50 messages from the Database
                await database.create_or_update_group(current_group_id, client_group_name)
                official_name = await database.get_group_name(current_group_id)
                recent_messages = await database.get_recent_messages(current_group_id, limit=50)
                encryption_key = await database.get_group_encryption_key(current_group_id)

                history_payload = {
                    "action": "history",
                    "group_name": official_name,
                    "messages": recent_messages,
                    "encryption_key": encryption_key
                }
                await protocol.send_message(writer, history_payload)

            elif action == "create_group":
                if not authenticated_user:
                    await send_error(writer, "Authenticate before creating a group.")
                    continue
                group_name = payload.get("group_name", "").strip()

                # Validate group name
                valid_group, group_error = validate_group_name(group_name)
                if not valid_group:
                    await send_error(writer, group_error)
                    continue

                group_id = str(uuid.uuid4())
                # Generate encryption key for the group
                cipher = MessageEncryption()
                encryption_key = cipher.get_key_b64()
                await database.create_or_update_group(group_id, group_name, owner_email=authenticated_user["email"], encryption_key=encryption_key)
                await database.add_user_to_group(authenticated_user["email"], group_id)
                logger.info("group_created peer=%s email=%s room=%s", peer, authenticated_user["email"], group_id)
                await protocol.send_message(writer, {
                    "action": "group_created",
                    "group": {
                        "group_id": group_id,
                        "group_name": group_name,
                        "encryption_key": encryption_key
                    }
                })

            elif action == "join_group":
                if not authenticated_user:
                    await send_error(writer, "Authenticate before joining a group.")
                    continue
                group_id = payload.get("group_id", "").strip()
                if not group_id:
                    await send_error(writer, "Group join request is missing room.")
                    continue
                if not await database.group_exists(group_id):
                    await send_error(writer, "That group does not exist.")
                    continue

                await database.add_user_to_group(authenticated_user["email"], group_id)
                group_name = await database.get_group_name(group_id)
                logger.info("group_joined peer=%s email=%s room=%s", peer, authenticated_user["email"], group_id)
                await protocol.send_message(writer, {
                    "action": "group_joined",
                    "group": {
                        "group_id": group_id,
                        "group_name": group_name,
                    }
                })

            elif action == "leave_group":
                if not authenticated_user:
                    await send_error(writer, "Authenticate before leaving a group.")
                    continue
                group_id = payload.get("group_id", "").strip()
                if not group_id or group_id == "global-lobby-001":
                    await send_error(writer, "That group cannot be left.")
                    continue
                if not await database.user_has_group_access(authenticated_user["email"], group_id):
                    await send_error(writer, "You are not a member of that group.")
                    continue

                await database.remove_user_from_group(authenticated_user["email"], group_id)
                await database.reassign_group_owner(group_id)

                if current_group_id == group_id and group_id in groups and writer in groups[group_id]:
                    del groups[group_id][writer]
                    current_group_id = None
                    await broadcast_user_list(group_id)

                logger.info("group_left peer=%s email=%s room=%s", peer, authenticated_user["email"], group_id)
                await protocol.send_message(writer, {
                    "action": "group_left",
                    "group_id": group_id,
                })

            elif action == "chat" and current_group_id:
                if not authenticated_user:
                    await send_error(writer, "Authenticate before sending messages.")
                    continue
                if not await database.user_has_group_access(authenticated_user["email"], current_group_id):
                    logger.warning("chat_denied peer=%s email=%s room=%s reason=no_access", peer, authenticated_user["email"], current_group_id)
                    await send_error(writer, "You no longer have access to this group.")
                    continue

                # Handle encrypted messages
                if payload.get("encrypted"):
                    encryption_key = await database.get_group_encryption_key(current_group_id)
                    if encryption_key:
                        try:
                            cipher = MessageEncryption.from_key_b64(encryption_key)
                            message_text = cipher.decrypt(
                                payload["nonce"],
                                payload["ciphertext"]
                            )
                        except Exception:
                            logger.warning("chat_denied peer=%s email=%s room=%s reason=decryption_failed", peer, authenticated_user["email"], current_group_id)
                            await send_error(writer, "Message decryption failed")
                            continue
                    else:
                        logger.warning("chat_denied peer=%s email=%s room=%s reason=no_encryption_key", peer, authenticated_user["email"], current_group_id)
                        await send_error(writer, "Group encryption key not found")
                        continue
                else:
                    message_text = payload.get("msg", "")

                # Validate message
                valid_msg, msg_error = validate_message(message_text)
                if not valid_msg:
                    logger.warning("chat_denied peer=%s email=%s room=%s reason=invalid_message", peer, authenticated_user["email"], current_group_id)
                    await send_error(writer, msg_error)
                    continue
                if is_rate_limited(writer):
                    await send_error(writer, "You are sending messages too quickly. Please slow down.")
                    continue
                payload["sender"] = authenticated_user["fullname"]
                payload["msg"] = message_text
                payload["message_id"] = payload.get("message_id") or str(uuid.uuid4())
                payload["timestamp"] = get_timestamp()
                logger.info("chat_sent peer=%s email=%s room=%s message_id=%s", peer, authenticated_user["email"], current_group_id, payload["message_id"])
                await broadcast(current_group_id, payload, sender_writer=writer)
                await protocol.send_message(writer, {
                    "action": "message_ack",
                    "message_id": payload["message_id"],
                    "timestamp": payload["timestamp"]
                })

            elif action == "assistant_chat":
                if not authenticated_user:
                    await send_error(writer, "Authenticate before sending assistant messages.")
                    continue

                group_id = payload.get("group_id", "").strip()
                message_text = payload.get("msg", "")
                if not group_id:
                    await send_error(writer, "Assistant message is missing room.")
                    continue
                if not await database.user_has_group_access(authenticated_user["email"], group_id):
                    logger.warning(
                        "assistant_chat_denied peer=%s email=%s room=%s reason=no_access",
                        peer,
                        authenticated_user["email"],
                        group_id,
                    )
                    await send_error(writer, "You no longer have access to that group.")
                    continue

                # Validate and sanitize AI prompt
                is_safe, sanitized_or_error = sanitize_ai_prompt(message_text)
                if not is_safe:
                    logger.warning("assistant_chat_denied peer=%s email=%s room=%s reason=unsafe_prompt", peer, authenticated_user["email"], group_id)
                    await send_error(writer, sanitized_or_error)
                    continue
                message_text = sanitized_or_error

                assistant_payload = {
                    "action": "chat",
                    "message_id": payload.get("message_id") or str(uuid.uuid4()),
                    "sender": payload.get("sender", "Groq"),
                    "msg": message_text,
                    "color": payload.get("color", "#9F7AEA"),
                    "timestamp": get_timestamp(),
                }
                logger.info(
                    "assistant_chat_sent peer=%s email=%s room=%s message_id=%s",
                    peer,
                    authenticated_user["email"],
                    group_id,
                    assistant_payload["message_id"],
                )
                await broadcast(group_id, assistant_payload, sender_writer=None)
                await protocol.send_message(writer, {
                    "action": "assistant_chat_ack",
                    "group_id": group_id,
                    "message_id": assistant_payload["message_id"],
                    "timestamp": assistant_payload["timestamp"],
                })

            elif action == "file" and current_group_id:
                if not authenticated_user:
                    await send_error(writer, "Authenticate before sending files.")
                    continue
                if not await database.user_has_group_access(authenticated_user["email"], current_group_id):
                    logger.warning("file_denied peer=%s email=%s room=%s reason=no_access", peer, authenticated_user["email"], current_group_id)
                    await send_error(writer, "You no longer have access to this group.")
                    continue
                filename = payload.get("filename", "")
                if not filename:
                    await send_error(writer, "File notification is missing a filename.")
                    continue
                if len(filename) > MAX_FILENAME_LENGTH:
                    logger.warning("file_denied peer=%s email=%s room=%s reason=filename_too_long", peer, authenticated_user["email"], current_group_id)
                    await send_error(writer, "Filename is too long.")
                    continue
                if is_rate_limited(writer):
                    await send_error(writer, "You are sending actions too quickly. Please slow down.")
                    continue
                payload["sender"] = authenticated_user["fullname"]
                payload["filename"] = filename
                payload["message_id"] = payload.get("message_id") or str(uuid.uuid4())
                payload["timestamp"] = get_timestamp()
                logger.info("file_announced peer=%s email=%s room=%s filename=%s message_id=%s", peer, authenticated_user["email"], current_group_id, filename, payload["message_id"])
                # We use sender_writer=None so the sender gets the broadcast too,
                # which triggers their UI to draw the image / download button!
                await broadcast(current_group_id, payload, sender_writer=None)

            elif action == "rename" and current_group_id:
                if not authenticated_user:
                    await send_error(writer, "Authenticate before renaming a group.")
                    continue
                if not await database.user_has_group_access(authenticated_user["email"], current_group_id):
                    logger.warning("rename_denied peer=%s email=%s room=%s reason=no_access", peer, authenticated_user["email"], current_group_id)
                    await send_error(writer, "You no longer have access to this group.")
                    continue
                new_name = payload.get("new_name", "").strip()
                if not new_name:
                    await send_error(writer, "Group name cannot be empty.")
                    continue
                if len(new_name) > MAX_GROUP_NAME_LENGTH:
                    logger.warning("rename_denied peer=%s email=%s room=%s reason=name_too_long", peer, authenticated_user["email"], current_group_id)
                    await send_error(writer, f"Group name is too long. Maximum length is {MAX_GROUP_NAME_LENGTH} characters.")
                    continue
                if not await database.is_group_owner(authenticated_user["email"], current_group_id):
                    logger.warning("rename_denied peer=%s email=%s room=%s reason=not_owner", peer, authenticated_user["email"], current_group_id)
                    await send_error(writer, "Only the group owner can rename this group.")
                    continue
                if is_rate_limited(writer):
                    await send_error(writer, "You are sending actions too quickly. Please slow down.")
                    continue
                await database.create_or_update_group(current_group_id, new_name)
                logger.info("room_renamed peer=%s email=%s room=%s new_name=%s", peer, authenticated_user["email"], current_group_id, new_name)
                rename_payload = {"action": "rename", "group_id": current_group_id, "new_name": new_name}
                await broadcast(current_group_id, rename_payload, sender_writer=None)

            elif action == "ping":
                pass


    except Exception as e:
        logger.exception("chat_connection_error peer=%s error=%s", peer, e)

    finally:

        # 1. Remove user from the group dictionary

        if current_group_id in groups and writer in groups[current_group_id]:
            del groups[current_group_id][writer]
            logger.info("room_leave peer=%s room=%s", peer, current_group_id)
            await broadcast_user_list(current_group_id)
        action_timestamps.pop(writer, None)
        if authenticated_user and authenticated_connections.get(authenticated_user["email"]) is writer:
            authenticated_connections.pop(authenticated_user["email"], None)

        try:

            writer.close()

            await writer.wait_closed()
            logger.info("chat_connection_closed peer=%s", peer)

        except Exception:
            logger.debug("chat_connection_close_failed peer=%s", peer)


async def main():
    # --- NEW: Boot up the File Server in the background ---
    print("[FILE] Launching File Server on Port 8889...")
    subprocess.Popen([sys.executable, "file_server.py"])
    # ------------------------------------------------------

    # --- NEWER: Boot up the Video Signaling Server ---
    print("[VIDEO] Launching Video Server on Port 8890...")
    subprocess.Popen([sys.executable, "video_server.py"])
    # ------------------------------------------------------

    await database.init_db()  # Ensure tables exist before server boots

    # Create SSL context for TLS encryption
    ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    cert_dir = Path(__file__).parent / "certs"
    ssl_context.load_cert_chain(
        certfile=cert_dir / "server.crt",
        keyfile=cert_dir / "server.key"
    )

    # Start the main Chat Server with TLS
    server = await asyncio.start_server(
        handle_client,
        SERVER_BIND_HOST,
        CHAT_PORT,
        ssl=ssl_context
    )
    print("[OK] Main Chat Server is running on Port 8888 (TLS enabled)...")

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
