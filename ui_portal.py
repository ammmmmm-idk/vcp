# Save as: ui_portal.py
import os
import asyncio
import html
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from urllib.parse import urlparse, parse_qs, quote, unquote

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QTextBrowser, QFileDialog, QApplication, QListWidget, QSplitter, QMessageBox
)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QCursor, QDesktopServices
from qasync import asyncSlot

import file_client
from call_ai_state import CallTranscriptStore
import database
from ai_service import generate_call_summary, generate_chat_reply
from attachment_security import validate_attachment_filename
from media_engine import (
    enumerate_audio_input_devices,
    enumerate_audio_output_devices,
    enumerate_camera_devices,
)
from ui_dialogs import FilterSelectionDialog, CreateGroupDialog, GroupManagementDialog
from webrtc_thread import WebRTCClientThread
from ui_video import DeviceSelectionDialog, NO_DEVICE_VALUE, VideoWindow
from config import MAX_GROUP_NAME_LENGTH, MAX_UPLOAD_FILE_SIZE, SERVER_HOST, VIDEO_SIGNALING_PORT



class PortalWidget(QWidget):
    def __init__(self, net_client, parent=None):
        super().__init__(parent)
        self.net_client = net_client
        self.net_client.message_received.connect(self._handle_network_message)
        self.net_client.connection_status.connect(self._handle_network_status)

        self.username = "User"
        self.pending_email = None
        self.session_token = None

        self.group_buttons = {}
        self.groups_data = {"global-lobby-001": "Lobby"}
        self.active_group_id = None
        self.active_group_name = "Lobby"
        self.pending_messages = {}
        self._connecting_group_id = None
        self.current_video_device_preferences = None
        self.device_selection_dialog = None
        self.ai_history = []
        self.ai_request_in_flight = False
        self.ai_default_placeholder = "Ask Groq AI..."
        self.call_transcript_store = CallTranscriptStore()
        self.current_call_room_id = None
        self._ai_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="AI-Request")

        self._setup_ui()

    AI_ROOM_ID = "Groq AI"
    AI_TRIGGER_PREFIX = "@ai"
    GROUP_AI_CONTEXT_LIMIT = 12
    CALL_SUMMARY_TRIGGER_PATTERNS = (
        "summarize the call",
        "summarise the call",
        "call summary",
        "summary of the call",
    )

    def initialize_user(self, username, email, db_groups, session_token):
        self.username = username
        self.pending_email = email
        self.session_token = session_token
        self.net_client.set_auth_context(email, session_token)
        for row in db_groups:
            gid = row["group_id"]
            gname = row["group_name"]
            if gid not in self.groups_data:
                self.groups_data[gid] = gname
                self._add_group_btn_ui(gid, gname)
        asyncio.create_task(self._load_ai_history())
        self._switch_group("global-lobby-001", force=True)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # The QSplitter makes everything customizable by the user!
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # ==========================================
        # 1. Group Switcher Sidebar (LEFT)
        # ==========================================
        self.switcher = QFrame()
        self.switcher.setStyleSheet("background-color: #2D3748; border-right: 1px solid #4A5568;")
        self.switch_layout = QVBoxLayout(self.switcher)
        self.switch_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.ai_btn = QPushButton("🤖 Groq AI")
        self.ai_btn.setFixedHeight(40)
        self.ai_btn.setStyleSheet(
            "text-align: left; padding-left: 10px; font-weight: bold; color: #9F7AEA; background: transparent; border: none;")
        self.ai_btn.clicked.connect(lambda: self._switch_group("Groq AI"))
        self.group_buttons["Groq AI"] = self.ai_btn
        self.switch_layout.addWidget(self.ai_btn)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #4A5568; margin: 5px 10px;")
        self.switch_layout.addWidget(line)

        for gid, gname in self.groups_data.items():
            self._add_group_btn_ui(gid, gname)

        self.add_btn = QPushButton("+ New Group")
        self.add_btn.setFixedHeight(40)
        self.add_btn.setStyleSheet(
            "text-align: left; padding-left: 10px; font-weight: bold; color: #63B3ED; background: transparent; border: none;")
        self.add_btn.setToolTip("Create or Join Group")
        self.add_btn.clicked.connect(self._open_create_group)
        self.switch_layout.addWidget(self.add_btn)

        # ==========================================
        # 2. Main Chat Area (CENTER)
        # ==========================================
        chat_area = QFrame()
        chat_area.setStyleSheet("background-color: #1A202C;")
        c_lay = QVBoxLayout(chat_area)
        c_lay.setContentsMargins(20, 20, 20, 20)

        # --- Header Bar ---
        header_bar = QWidget()
        h_lay = QHBoxLayout(header_bar)
        h_lay.setContentsMargins(0, 0, 0, 0)

        self.chat_header = QLabel("GROUP CHAT", styleSheet="font-size: 20px; font-weight:bold; color:#63B3ED;")

        btn_invite = QPushButton("Copy Invite")
        btn_invite.setObjectName("ControlBtn")
        btn_invite.clicked.connect(self._copy_link)

        btn_manage = QPushButton("Manage Group")
        btn_manage.setObjectName("ControlBtn")
        btn_manage.clicked.connect(self._open_group_mgmt)

        self.btn_join_video = QPushButton("📞 Join Video Call")
        self.btn_join_video.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_join_video.setStyleSheet("""
            QPushButton {
                background-color: #48BB78; 
                color: white; 
                font-weight: bold; 
                font-size: 14px;
                padding: 10px 20px; 
                border-radius: 5px;
            }
            QPushButton:hover { background-color: #38A169; }
        """)
        self.btn_join_video.clicked.connect(self.launch_video_call)

        h_lay.addWidget(self.chat_header)
        h_lay.addStretch()
        h_lay.addWidget(btn_invite)
        h_lay.addWidget(btn_manage)
        h_lay.addSpacing(10)
        h_lay.addWidget(self.btn_join_video)

        c_lay.addWidget(header_bar)

        # --- Chat History ---
        self.chat_display = QTextBrowser()
        self.chat_display.setObjectName("ChatDisplay")
        self.chat_display.setOpenLinks(False)
        self.chat_display.setOpenExternalLinks(False)
        self.chat_display.anchorClicked.connect(self._handle_chat_link)
        c_lay.addWidget(self.chat_display)

        # --- Input Area ---
        input_container = QWidget()
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(0, 10, 0, 0)

        self.attach_btn = QPushButton("📎")
        self.attach_btn.setObjectName("AttachBtn")
        self.attach_btn.setFixedSize(45, 45)
        self.attach_btn.clicked.connect(self._open_file_dialog)
        input_layout.addWidget(self.attach_btn)

        self.chat_input = QLineEdit()
        self.chat_input.setFixedHeight(45)
        self.chat_input.setPlaceholderText("Enter message...")
        self.chat_input.returnPressed.connect(self._send_text_msg)
        input_layout.addWidget(self.chat_input)

        self.send_btn = QPushButton("➤")
        self.send_btn.setObjectName("SendBtn")
        self.send_btn.setFixedSize(45, 45)
        self.send_btn.clicked.connect(self._send_text_msg)
        input_layout.addWidget(self.send_btn)

        c_lay.addWidget(input_container)

        # ==========================================
        # 3. Online Users Sidebar (RIGHT)
        # ==========================================
        users_area = QFrame()
        users_area.setStyleSheet("background-color: #2D3748; border-left: 1px solid #4A5568;")
        u_lay = QVBoxLayout(users_area)

        u_title = QLabel("Online Users",
                         styleSheet="font-size: 14px; font-weight:bold; color:#48BB78; padding-bottom: 5px;")

        self.user_list_widget = QListWidget()
        self.user_list_widget.setStyleSheet("""
            QListWidget {
                background-color: transparent; 
                color: #A0AEC0; 
                border: none; 
                font-size: 13px;
            }
            QListWidget::item { padding: 5px; }
        """)
        self.user_list_widget.addItem("⏳ Loading...")

        u_lay.addWidget(u_title)
        u_lay.addWidget(self.user_list_widget)

        # --- Assemble the Splitter ---
        self.main_splitter.addWidget(self.switcher)
        self.main_splitter.addWidget(chat_area)
        self.main_splitter.addWidget(users_area)

        # Set default proportions: roughly 1/6 (Groups), 4/6 (Chat), 1/6 (Users)
        self.main_splitter.setSizes([200, 800, 200])

        layout.addWidget(self.main_splitter)

    def _start_video_call(self):
        if self.active_group_id == "Groq AI": return
        print(f"Opening Video Window for Room: {self.active_group_name} ({self.active_group_id})")

        # Instantiate and show the new window!
        # We save it as self.video_window so Python's garbage collector doesn't destroy it instantly
        self.video_window = VideoWindow(self.active_group_name)
        self.video_window.show()

    def _handle_network_message(self, payload: dict):
        action = payload.get("action")
        if action == "history":
            official_name = payload.get("group_name")
            if official_name and self.active_group_id != "Groq AI":
                self._apply_rename(self.active_group_id, official_name)

            self.chat_display.clear()
            for msg_data in payload.get("messages", []):
                msg_text = msg_data["msg"]
                if msg_text.startswith("__FILE__:"):
                    filename = msg_text.split(":", 1)[1]
                    # Show file immediately without async download for proper ordering
                    self._show_file_message_sync(
                        msg_data["sender"], filename,
                        msg_data.get("color", "#E2E8F0"), msg_data.get("timestamp", "")
                    )
                else:
                    self._add_chat_msg(msg_data["sender"], msg_text, msg_data.get("color", "#E2E8F0"),
                                       msg_data.get("timestamp", ""))

        elif action == "chat":
            self._add_chat_msg(payload["sender"], payload["msg"], payload.get("color", "#E2E8F0"),
                               payload.get("timestamp", ""))

        elif action == "message_ack":
            self._handle_message_ack(payload.get("message_id"), payload.get("timestamp", ""))

        elif action == "error":
            self._show_error(payload.get("message", "Unknown server error."), popup=True)

        elif action == "rename":
            group_id = payload.get("group_id")
            new_name = payload.get("new_name")
            if group_id and new_name:
                self._apply_rename(group_id, new_name)

        elif action == "file":
            filename = payload.get("filename")
            asyncio.create_task(
                self._handle_file_message(payload.get("sender"), filename, payload.get("color", "#E2E8F0"),
                                          payload.get("timestamp", "")))

        if action == "user_list":
            usernames = payload.get("users", [])
            self.user_list_widget.clear()
            self.user_list_widget.addItems(usernames)

    def _handle_network_status(self, status_type: str, msg: str):
        if status_type == "success":
            self._connecting_group_id = None
            return
        if status_type == "error":
            self._connecting_group_id = None
            if self.active_group_id == "Groq AI" and msg in {"Disconnected from server.", "Connection Lost."}:
                return
            self._mark_pending_messages_failed(msg)
            self._show_error(msg)

    def _apply_rename(self, group_id, new_name):
        self.groups_data[group_id] = new_name
        if self.active_group_id == group_id:
            self.active_group_name = new_name
            self._update_sidebar_ui()
        if group_id in self.group_buttons:
            btn = self.group_buttons[group_id]
            btn.setText(new_name)  # <-- Changed to show FULL name
            btn.setToolTip(new_name)

    def _add_group_btn_ui(self, group_id, group_name):
        btn = QPushButton(group_name)  # <-- Changed to show FULL name
        btn.setFixedHeight(40)
        # Inline styling so they look like list items instead of boxed buttons
        btn.setStyleSheet("""
            QPushButton {
                text-align: left; 
                padding-left: 10px; 
                color: #E2E8F0; 
                background: transparent; 
                border: none;
            }
            QPushButton:hover { background-color: #4A5568; border-radius: 4px;}
            QPushButton[active="true"] { background-color: #3182CE; font-weight: bold; border-radius: 4px;}
        """)
        btn.setToolTip(group_name)
        btn.clicked.connect(lambda _, gid=group_id: self._switch_group(gid))
        self.group_buttons[group_id] = btn

        count = self.switch_layout.count()
        if hasattr(self, 'add_btn') and self.add_btn:
            self.switch_layout.insertWidget(count - 1, btn)
        else:
            self.switch_layout.addWidget(btn)

    def _open_create_group(self):
        diag = CreateGroupDialog(self)
        if diag.exec():
            text = diag.name_in.text().strip()
            if text:
                if not text.startswith("http") and len(text) > MAX_GROUP_NAME_LENGTH:
                    self._show_error(
                        f"Group name is too long. Maximum length is {MAX_GROUP_NAME_LENGTH} characters.",
                        popup=True
                    )
                    return
                asyncio.create_task(self._safe_async_group_action(text))
            else:
                self._show_error("Enter a group name or paste an invite link.", popup=True)

    async def _safe_async_group_action(self, text: str):
        try:
            if text.startswith("http"):
                parsed = urlparse(text)
                group_id = parsed.path.split("/")[-1]
                query_params = parse_qs(parsed.query)
                group_name = unquote(query_params.get("name", ["Shared Group"])[0])
                if len(group_name) > MAX_GROUP_NAME_LENGTH:
                    self._show_error(
                        f"Group name is too long. Maximum length is {MAX_GROUP_NAME_LENGTH} characters.",
                        popup=True
                    )
                    return

                response = await self.net_client.request_group_action({
                    "action": "join_group",
                    "group_id": group_id,
                })
                if response and response.get("action") == "group_joined":
                    joined_group = response.get("group", {})
                    joined_id = joined_group.get("group_id", group_id)
                    joined_name = joined_group.get("group_name", group_name)
                    if joined_id and joined_id not in self.groups_data:
                        self.groups_data[joined_id] = joined_name
                        self._add_group_btn_ui(joined_id, joined_name)
                    self._switch_group(joined_id)
            else:
                response = await self.net_client.request_group_action({
                    "action": "create_group",
                    "group_name": text,
                })
                if response and response.get("action") == "group_created":
                    created_group = response.get("group", {})
                    new_id = created_group.get("group_id")
                    new_name = created_group.get("group_name", text)
                    if new_id and new_id not in self.groups_data:
                        self.groups_data[new_id] = new_name
                        self._add_group_btn_ui(new_id, new_name)
                    if new_id:
                        self._switch_group(new_id)
        except Exception as e:
            self._show_error(f"Failed to create or join group: {e}")
            import traceback
            print("\n🚨 ERROR WHILE CREATING GROUP:")
            traceback.print_exc()

    def _get_invite_link(self):
        safe_name = quote(self.active_group_name)
        return f"https://vcp.app/join/{self.active_group_id}?name={safe_name}"

    def _open_group_mgmt(self):
        if self.active_group_id == "Groq AI": return
        if self.active_group_id == "global-lobby-001":
            QMessageBox.information(self, "Lobby", "The Lobby is the default room and cannot be left.")
            return
        diag = GroupManagementDialog(self.active_group_name, self._get_invite_link(), self)
        diag.group_renamed.connect(self._rename_active_group)
        diag.group_left.connect(self._leave_active_group)
        diag.exec()

    def _rename_active_group(self, new_name):
        new_name = new_name.strip()
        if not new_name:
            self._show_error("Group name cannot be empty.", popup=True)
            return
        if len(new_name) > MAX_GROUP_NAME_LENGTH:
            self._show_error(
                f"Group name is too long. Maximum length is {MAX_GROUP_NAME_LENGTH} characters.",
                popup=True
            )
            return
        asyncio.create_task(self.net_client.send_rename(self.active_group_id, new_name))

    def _copy_link(self):
        if self.active_group_id != "Groq AI":
            QApplication.clipboard().setText(self._get_invite_link())
            print("Link copied to clipboard silently.")

    def _switch_group(self, group_id, force=False):
        if not force and (self.active_group_id == group_id or self._connecting_group_id == group_id):
            return

        # Clear old transcript when switching groups
        if self.current_call_room_id and self.current_call_room_id != group_id:
            self.call_transcript_store.clear_room(self.current_call_room_id)
            self.current_call_room_id = None

        self.active_group_id = group_id
        self.active_group_name = self.groups_data.get(group_id, "Unknown") if group_id != self.AI_ROOM_ID else "Groq AI"

        for btn in self.group_buttons.values():
            btn.setProperty("active", False)
            btn.setStyle(btn.style())

        if group_id in self.group_buttons:
            self.group_buttons[group_id].setProperty("active", True)
            self.group_buttons[group_id].setStyle(self.group_buttons[group_id].style())

        self.chat_display.clear()
        self._update_sidebar_ui()

        if group_id != self.AI_ROOM_ID:
            self.btn_join_video.show()
            self._connecting_group_id = group_id
            asyncio.create_task(self.net_client.connect_to_group(
                group_id, self.active_group_name, self.username, self.pending_email, self.session_token
            ))
        else:
            self.btn_join_video.hide()
            self._connecting_group_id = None
            self.net_client.disconnect()
            self._render_ai_history()

    def _update_sidebar_ui(self):
        if self.active_group_id == self.AI_ROOM_ID:
            self.chat_header.setText("GROQ AI ASSISTANT")
            self.chat_input.setPlaceholderText(self.ai_default_placeholder)
        else:
            self.chat_header.setText(f"GROUP CHAT: {self.active_group_name}")
            self.chat_input.setPlaceholderText("Enter message...")

    def _set_ai_busy(self, is_busy: bool):
        self.ai_request_in_flight = is_busy
        if self.active_group_id == self.AI_ROOM_ID:
            self.chat_input.setDisabled(is_busy)
            self.send_btn.setDisabled(is_busy)
            if is_busy:
                self.chat_input.setPlaceholderText("Groq AI is thinking...")
            else:
                self.chat_input.setPlaceholderText(self.ai_default_placeholder)

    async def _load_ai_history(self):
        if not self.pending_email:
            return
        await database.init_db()
        rows = await database.get_recent_ai_messages(self.pending_email)
        self.ai_history = [{"role": row["role"], "content": row["content"]} for row in rows]
        if self.active_group_id == "Groq AI":
            self._render_ai_history()

    def _render_ai_history(self):
        if self.active_group_id != self.AI_ROOM_ID:
            return

        self.chat_display.clear()
        for entry in self.ai_history:
            role = entry.get("role")
            content = entry.get("content", "")
            if role == "user":
                self._add_chat_msg(self.username, content, "#63B3ED")
            elif role == "assistant":
                self._add_chat_msg("Groq", content, "#9F7AEA")

    async def _build_group_ai_history(self, group_id: str):
        if group_id in (None, self.AI_ROOM_ID):
            return []

        rows = await database.get_recent_messages(group_id, limit=self.GROUP_AI_CONTEXT_LIMIT)
        # Yield to event loop after database query
        await asyncio.sleep(0)

        history = []
        for row in rows:
            sender = row.get("sender", "User")
            message_text = row.get("msg", "")

            # Handle file messages
            if message_text.startswith("__FILE__:"):
                filename = message_text.split(":", 1)[1]
                message_text = f"[Sent file: {filename}]"

            if sender == "Groq":
                history.append({"role": "assistant", "content": message_text})
            else:
                history.append({"role": "user", "content": f"{sender}: {message_text}"})

        # Yield before returning to allow event loop switching
        await asyncio.sleep(0)
        return history

    def _extract_ai_prompt(self, message_text: str) -> str:
        normalized_text = message_text.strip()
        if not normalized_text.lower().startswith(self.AI_TRIGGER_PREFIX):
            return ""

        prompt_text = normalized_text[len(self.AI_TRIGGER_PREFIX):].lstrip(" ,:;-")
        return prompt_text.strip()

    def _is_call_summary_request(self, prompt_text: str) -> bool:
        normalized_prompt = prompt_text.lower()
        return any(pattern in normalized_prompt for pattern in self.CALL_SUMMARY_TRIGGER_PATTERNS)

    async def _handle_group_ai_request(self, group_id: str, prompt_text: str):
        self._set_ai_busy(True)
        try:
            # Run AI generation in a dedicated thread pool to avoid blocking event loop
            loop = asyncio.get_event_loop()

            if self._is_call_summary_request(prompt_text):
                transcript_context = self.call_transcript_store.format_recent_context(group_id)
                if not transcript_context:
                    self._show_error("There is no call transcript available yet for this room.", popup=True)
                    return

                # Run blocking AI call in executor thread
                import functools
                ai_reply = await loop.run_in_executor(
                    self._ai_executor,
                    functools.partial(self._sync_generate_call_summary, transcript_context)
                )
            else:
                ai_history = await self._build_group_ai_history(group_id)

                # Run blocking AI call in executor thread
                import functools
                ai_reply = await loop.run_in_executor(
                    self._ai_executor,
                    functools.partial(self._sync_generate_chat_reply, ai_history, prompt_text)
                )

            ai_message_id = await self.net_client.send_assistant_chat(group_id, ai_reply, "#9F7AEA")
            if not ai_message_id:
                self._show_error("Groq AI failed to post its reply to the group.", popup=True)
        except Exception as error:
            self._show_error(f"Groq AI request failed: {error}", popup=True)
        finally:
            self._set_ai_busy(False)

    def _sync_generate_call_summary(self, transcript_context):
        """Synchronous wrapper for generate_call_summary - runs in executor thread"""
        import asyncio
        return asyncio.run(generate_call_summary(transcript_context))

    def _sync_generate_chat_reply(self, ai_history, prompt_text):
        """Synchronous wrapper for generate_chat_reply - runs in executor thread"""
        import asyncio
        return asyncio.run(generate_chat_reply(ai_history, prompt_text))

    def _open_file_dialog(self):
        """Non-async version to avoid event loop conflicts"""
        # Synchronous dialog call
        fname, _ = QFileDialog.getOpenFileName(self, "Select File", "", "All Files (*)")
        if fname:
            filename = os.path.basename(fname)
            is_valid, error_message = validate_attachment_filename(filename)
            if not is_valid:
                self._show_error(f"{error_message} The file will not be sent.", popup=True)
                return
            if os.path.getsize(fname) > MAX_UPLOAD_FILE_SIZE:
                self._show_error(
                    f"File is too large, so it will not be sent. Maximum size is {MAX_UPLOAD_FILE_SIZE // (1024 * 1024)} MB.",
                    popup=True
                )
                return

            # Schedule the actual upload as a separate async task
            asyncio.create_task(self._execute_upload(fname, filename))

    async def _execute_upload(self, fpath: str, filename: str):
        """Actually perform the upload (async part)"""
        upload_success = await self.net_client.send_file(self.username, fpath)

        if not upload_success:
            self._add_chat_msg("System", f"❌ {filename} upload failed.", "#E53E3E",
                               datetime.now().strftime("%H:%M"))
            return

        # On success, just send the file notification (shows download link)
        await self.net_client.send_file_notification(self.username, filename)

    def _show_file_message_sync(self, sender: str, filename: str, color: str, timestamp: str):
        """Synchronous version for history loading - shows placeholder for images, link for others"""
        ext = os.path.splitext(filename)[1].lower()
        safe_filename = html.escape(filename)
        display_time = self._format_timestamp(timestamp)
        time_str = f"<span style='color:#718096; font-size:10px;'>[{display_time}]</span> " if display_time else ""
        safe_sender = html.escape(str(sender))

        # For images, show placeholder immediately and schedule download
        if ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp']:
            placeholder_id = f"img-placeholder-{hash(filename + timestamp)}"
            placeholder_html = f'''<div style='margin:5px;' id='{placeholder_id}'>
            <span style='color:#718096; font-size:10px;'>{time_str}</span> <b style='color:{color};'>{safe_sender}:</b>
            <div style="background-color:#2D3748; padding:10px; border-radius:5px; margin-top:5px; display:inline-block;">
                <i>🖼️ Loading image: {safe_filename}...</i>
            </div></div><p style='background-color:transparent;'></p>'''
            self.chat_display.append(placeholder_html)
            # Schedule async download to replace placeholder
            asyncio.create_task(self._download_and_display_image(sender, filename, color, timestamp, placeholder_id))
            return

        # For non-images, show download link immediately
        icon = "🎥 Video" if ext in ['.mp4', '.mov', '.avi', '.mkv'] else "📄 File"
        file_html = f'''<div style='margin:5px;'>
        <span style='color:#718096; font-size:10px;'>{time_str}</span> <b style='color:{color};'>{safe_sender}:</b>
        <div style="background-color:#2D3748; padding:10px; border-radius:5px; margin-top:5px; display:inline-block;">
            <b>{icon}:</b> {safe_filename}<br>
            <a href="download://{filename}" style="color:#48BB78; text-decoration:none; font-weight:bold;">⬇️ Click here to Download & Open</a>
        </div></div><p style='background-color:transparent;'></p>'''
        self.chat_display.append(file_html)
        # Auto-scroll to bottom
        self.chat_display.verticalScrollBar().setValue(self.chat_display.verticalScrollBar().maximum())

    async def _download_and_display_image(self, sender: str, filename: str, color: str, timestamp: str, placeholder_id: str):
        """Download image and replace placeholder with actual image"""
        safe_filename = html.escape(filename)
        local_path = await file_client.download_file(filename)

        if local_path:
            display_time = self._format_timestamp(timestamp)
            time_str = f"<span style='color:#718096; font-size:10px;'>[{display_time}]</span> " if display_time else ""
            safe_sender = html.escape(str(sender))
            file_uri = QUrl.fromLocalFile(local_path).toString()

            # Replace placeholder with actual image
            html_content = self.chat_display.toHtml()
            import re

            # QTextBrowser structure from debug output:
            # <p><a name="id"></a>timestamp sender: </p>
            # <p style="background-color:#2d3748">🖼️ Loading image: filename...</p>
            # <p style="background-color:transparent"></p>

            # More flexible pattern - account for any whitespace and style ordering
            placeholder_pattern = (
                f'<p[^>]*>\\s*<a\\s+name="{re.escape(placeholder_id)}"[^>]*></a>.*?</p>\\s*'  # First paragraph
                f'<p\\s+[^>]*background-color\\s*:\\s*#2d3748[^>]*>.*?</p>\\s*'  # Loading message (flexible whitespace)
                f'<p\\s+[^>]*background-color\\s*:\\s*transparent[^>]*></p>'  # Reset paragraph
            )

            image_html = f'''<p style="margin-top:5px; margin-bottom:5px; margin-left:5px; margin-right:5px;">
            <span style="font-size:10px; color:#718096;">{time_str}</span><span style="font-weight:700; color:{color};">{safe_sender}:</span>
            <br/><img src="{file_uri}" width="200" style="border-radius: 8px;"/><br/><i>{safe_filename}</i>
            </p><p style="background-color:transparent;"></p>'''

            new_html = re.sub(placeholder_pattern, image_html, html_content, flags=re.DOTALL | re.IGNORECASE)

            if new_html == html_content:
                # Fallback: Try simpler pattern without the reset paragraph
                simpler_pattern = (
                    f'<p[^>]*>\\s*<a\\s+name="{re.escape(placeholder_id)}"[^>]*></a>.*?</p>\\s*'
                    f'<p\\s+[^>]*background-color\\s*:\\s*#2d3748[^>]*>.*?</p>'
                )
                new_html = re.sub(simpler_pattern, image_html.replace('<p style="background-color:transparent;"></p>', ''),
                                 html_content, flags=re.DOTALL | re.IGNORECASE)

            if new_html != html_content:
                self.chat_display.setHtml(new_html)
                self.chat_display.verticalScrollBar().setValue(self.chat_display.verticalScrollBar().maximum())
            else:
                print(f"Warning: Failed to replace placeholder {placeholder_id} for image {filename}")

    async def _handle_file_message(self, sender: str, filename: str, color: str, timestamp: str):
        """Async version for live incoming files - downloads images"""
        ext = os.path.splitext(filename)[1].lower()
        safe_filename = html.escape(filename)
        if ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp']:
            local_path = await file_client.download_file(filename)
            if local_path:
                file_uri = QUrl.fromLocalFile(local_path).toString()
                html_msg = f'<br><img src="{file_uri}" width="200" style="border-radius: 8px;"><br><i>{safe_filename}</i>'
                self._add_raw_html(sender, html_msg, color, timestamp)
            else:
                self._add_chat_msg(sender, f"❌ [Failed to load image: {filename}]", "red", timestamp)
        else:
            # For non-image files, just show the download link
            self._show_file_message_sync(sender, filename, color, timestamp)

    def _manual_download_task(self, filename: str):
        """Non-async version to avoid event loop conflicts"""
        filename = os.path.basename(filename)
        downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        default_path = os.path.join(downloads_dir, filename).replace("\\", "/")
        ext = os.path.splitext(filename)[1]

        # Synchronous dialog call - this is fine, it returns immediately when user chooses
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Save File As...", default_path,
            f"Files (*{ext});;All Files (*)",
            options=QFileDialog.Option.DontUseNativeDialog
        )

        if save_path:
            # Schedule the actual download as a separate async task
            asyncio.create_task(self._execute_download(filename, save_path))

    async def _execute_download(self, filename: str, save_path: str):
        """Actually perform the download (async part)"""
        local_time = datetime.now().strftime("%H:%M")
        success = await file_client.download_file(filename, destination=save_path)

        if success:
            # On success, just open the file - no system message
            QDesktopServices.openUrl(QUrl.fromLocalFile(save_path))
        else:
            # Only show message on failure
            self._add_chat_msg("System", f"❌ Download failed: {filename}", "#E53E3E", local_time)

    def _handle_chat_link(self, url: QUrl):
        pos = self.chat_display.mapFromGlobal(QCursor.pos())
        raw_link = self.chat_display.anchorAt(pos) or url.toString()

        if "download://" in raw_link:
            filename = unquote(raw_link.split("download://")[-1]).lstrip('/')
            if filename: self._manual_download_task(filename)
        elif "video://" in raw_link:
            self._play_video(unquote(raw_link.split("video://")[-1]).lstrip('/'))
        else:
            QDesktopServices.openUrl(QUrl(raw_link))

    def _play_video(self, video_path):
        if os.path.exists(video_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(video_path)))
        else:
            self._add_chat_msg("System", f"❌ Error: Video file not found at {video_path}", "red")

    @asyncSlot()
    async def _send_text_msg(self):
        txt = self.chat_input.text().strip()
        if txt:
            local_time = datetime.now().strftime("%H:%M")
            self.chat_input.clear()
            if self.active_group_id == self.AI_ROOM_ID:
                if self.ai_request_in_flight:
                    self._show_error("Groq AI is still answering the previous request.", popup=True)
                    return
                self._set_ai_busy(True)
                self._add_chat_msg(self.username, txt, "#63B3ED", local_time)
                try:
                    ai_reply = await generate_chat_reply(self.ai_history, txt)
                    self.ai_history.append({"role": "user", "content": txt})
                    self.ai_history.append({"role": "assistant", "content": ai_reply})
                    timestamp = datetime.now().isoformat(timespec="seconds")
                    await database.save_ai_message(self.pending_email, "user", txt, timestamp)
                    await database.save_ai_message(self.pending_email, "assistant", ai_reply, timestamp)
                    self._add_chat_msg("Groq", ai_reply, "#9F7AEA", datetime.now().strftime("%H:%M"))
                except Exception as e:
                    self._show_error(f"Groq AI request failed: {e}", popup=True)
                finally:
                    self._set_ai_busy(False)
            else:
                message_id = await self.net_client.send_chat(sender=self.username, msg=txt)
                if message_id:
                    self.pending_messages[message_id] = {
                        "group_id": self.active_group_id,
                        "msg": txt
                    }
                    self._add_chat_msg(self.username, txt, "#63B3ED", local_time)
                    ai_prompt = self._extract_ai_prompt(txt)
                    if ai_prompt:
                        if self.ai_request_in_flight:
                            self._show_error("Groq AI is still answering the previous request.", popup=True)
                            return
                        target_group_id = self.active_group_id
                        asyncio.create_task(self._handle_group_ai_request(target_group_id, ai_prompt))
                else:
                    self._add_chat_msg("System Error", f"Failed to send: {txt}", "#E53E3E", local_time)

    def _add_chat_msg(self, sender, msg, color, timestamp=""):
        display_time = self._format_timestamp(timestamp)
        time_str = f"<span style='color:#718096; font-size:10px;'>[{display_time}]</span> " if display_time else ""
        safe_sender = html.escape(str(sender))
        safe_msg = html.escape(str(msg))
        # Use div instead of p for consistency with file messages
        self.chat_display.append(f"<div style='margin:5px;'>{time_str}<b style='color:{color};'>{safe_sender}:</b> {safe_msg}</div>")
        # Auto-scroll to bottom
        self.chat_display.verticalScrollBar().setValue(self.chat_display.verticalScrollBar().maximum())

    def _add_raw_html(self, sender, html_content, color, timestamp=""):
        display_time = self._format_timestamp(timestamp)
        time_str = f"<span style='color:#718096; font-size:10px;'>[{display_time}]</span> " if display_time else ""
        safe_sender = html.escape(str(sender))
        # Use div for consistency
        self.chat_display.append(f"<div style='margin:5px;'>{time_str}<b style='color:{color};'>{safe_sender}:</b></div>")
        self.chat_display.insertHtml(html_content)
        self.chat_display.append("<br>")

    def _remove_last_system_message(self, element_id: str):
        """Remove a system message by its HTML element ID using JavaScript-like manipulation"""
        try:
            html_content = self.chat_display.toHtml()
            # Find and remove the span with the given ID
            import re
            pattern = f'<span id="{re.escape(element_id)}"[^>]*>.*?</span><br>'
            html_content = re.sub(pattern, '', html_content, flags=re.DOTALL)
            self.chat_display.setHtml(html_content)
            # Scroll to bottom after modification
            self.chat_display.verticalScrollBar().setValue(self.chat_display.verticalScrollBar().maximum())
        except Exception:
            pass  # If removal fails, message stays visible (not critical)

    def _handle_message_ack(self, message_id, timestamp):
        if not message_id:
            return
        self.pending_messages.pop(message_id, None)

    def _mark_pending_messages_failed(self, error_message):
        current_group_id = self.active_group_id
        failed_ids = [
            message_id for message_id, data in self.pending_messages.items()
            if data["group_id"] == current_group_id
        ]
        for message_id in failed_ids:
            data = self.pending_messages.pop(message_id)
            self._add_chat_msg("System", f"Delivery failed: {data['msg']}", "#E53E3E", datetime.now().isoformat(timespec="seconds"))

    def _show_error(self, message, popup=False):
        if message:
            self._add_chat_msg("System Error", message, "#E53E3E", datetime.now().isoformat(timespec="seconds"))
            if popup:
                QMessageBox.warning(self, "Error", message)

    def _format_timestamp(self, timestamp):
        if not timestamp:
            return ""
        try:
            return datetime.fromisoformat(timestamp).strftime("%H:%M")
        except ValueError:
            return timestamp

    def launch_video_call(self):
        """Triggered when the user clicks 'Join Video Call'"""
        # --- Prevent joining multiple calls at once ---
        if hasattr(self, 'webrtc_thread') and self.webrtc_thread is not None:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                "Active Call",
                "You are already in an active video call! Please hang up before joining another room."
            )
            return

        print(f"🚀 Launching Video Call for room: {self.active_group_id}")

        # 1. Pop open the Video Grid UI
        self.video_window = VideoWindow(self.active_group_name)
        self.video_window.show()

        # 2. Spin up the WebRTC Engine in the background
        self.webrtc_thread = WebRTCClientThread(
            host=SERVER_HOST,
            port=VIDEO_SIGNALING_PORT,
            username=self.username,
            group_id=self.active_group_id,
            signal_emitter=self.video_window.signals
        )

        # ---------------------------------------------------------
        # THE FIX: Wire the UI to the Thread before it starts!
        # ---------------------------------------------------------
        self.video_window.signals.cam_toggled.connect(
            lambda is_muted: self.webrtc_thread.set_cam_muted(is_muted)
        )
        self.video_window.signals.mic_toggled.connect(
            lambda is_muted: self.webrtc_thread.set_mic_muted(is_muted)
        )

        # 3. Start the background thread
        self.webrtc_thread.start()

        # 4. Listen for the window closing
        self.video_window.closed_signal.connect(self._stop_video_call)

    def _stop_video_call(self):
        """Cleans up the network thread when the window is closed."""
        print("Window closed! Shutting down network thread...")
        if hasattr(self, 'webrtc_thread') and self.webrtc_thread is not None:
            self.webrtc_thread.stop()
            self.webrtc_thread = None # Clears it out so we can start a new call later!
        # Don't clear current_call_room_id - keep transcript available for summaries after call ends

    def _open_video_window(self):
        print(f"Opening Video Window for Room: {self.active_group_name}")
        self.current_call_room_id = self.active_group_id

        self.video_window = VideoWindow(self.active_group_name)
        self.video_window.show()

        self.webrtc_thread = WebRTCClientThread(
            host=SERVER_HOST,
            port=VIDEO_SIGNALING_PORT,
            username=self.username,
            group_id=self.active_group_id,
            signal_emitter=self.video_window.signals,
            transcript_callback=self.video_window.signals.transcript_chunk.emit,
        )
        self._attach_video_window_handlers()

        self.webrtc_thread.start()
        self.video_window.closed_signal.connect(self._stop_video_call)

    def _leave_active_group(self):
        asyncio.create_task(self._leave_group_async())

    def launch_video_call(self):
        """Triggered when the user clicks 'Join Video Call'"""
        if hasattr(self, 'webrtc_thread') and self.webrtc_thread is not None:
            QMessageBox.warning(
                self,
                "Active Call",
                "You are already in an active video call! Please hang up before joining another room."
            )
            return

        print(f"Launching Video Call for room: {self.active_group_id}")
        self.current_call_room_id = self.active_group_id

        camera_devices = enumerate_camera_devices()
        microphone_devices = enumerate_audio_input_devices()
        speaker_devices = enumerate_audio_output_devices()
        device_preferences = {
            "camera_device": None,
            "microphone_device": None,
            "speaker_device": None,
        }
        self.current_video_device_preferences = device_preferences.copy()
        has_camera = bool(camera_devices)
        has_microphone = bool(microphone_devices)
        has_speakers = bool(speaker_devices)

        if not has_camera and not has_microphone and not has_speakers:
            QMessageBox.warning(
                self,
                "No Devices",
                "No usable camera, microphone, or speakers are available for the call."
            )
            return

        missing_features = []
        if not has_camera:
            missing_features.append("camera")
        if not has_microphone:
            missing_features.append("microphone")
        if not has_speakers:
            missing_features.append("speakers")
        if missing_features:
            QMessageBox.information(
                self,
                "Partial Call",
                "Starting the call without: " + ", ".join(missing_features) + ". Use Devices during the call to change hardware."
            )

        self.video_window = VideoWindow(
            self.active_group_name,
            has_camera=has_camera,
            has_microphone=has_microphone,
            has_speakers=has_speakers,
        )
        self.video_window.show()

        self.webrtc_thread = WebRTCClientThread(
            host=SERVER_HOST,
            port=VIDEO_SIGNALING_PORT,
            username=self.username,
            group_id=self.active_group_id,
            signal_emitter=self.video_window.signals,
            device_preferences=device_preferences,
            transcript_callback=self.video_window.signals.transcript_chunk.emit,
        )
        self._attach_video_window_handlers()

        self.webrtc_thread.start()
        self.video_window.closed_signal.connect(self._stop_video_call)

    async def _leave_group_async(self):
        group_id = self.active_group_id
        if group_id in (None, "Groq AI", "global-lobby-001"):
            return

        response = await self.net_client.request_group_action({
            "action": "leave_group",
            "group_id": group_id,
        })
        if not response or response.get("action") != "group_left":
            return

        btn = self.group_buttons.pop(group_id, None)
        if btn is not None:
            btn.deleteLater()

        self.groups_data.pop(group_id, None)
        self._switch_group("global-lobby-001", force=True)
        self._add_chat_msg("System", "You left the group.", "#A0AEC0", datetime.now().strftime("%H:%M"))

    def _change_video_devices(self):
        if not hasattr(self, "video_window") or self.video_window is None:
            return

        if self.device_selection_dialog is not None and self.device_selection_dialog.isVisible():
            self.device_selection_dialog.raise_()
            self.device_selection_dialog.activateWindow()
            return

        camera_devices = enumerate_camera_devices()
        microphone_devices = enumerate_audio_input_devices()
        speaker_devices = enumerate_audio_output_devices()
        selection_dialog = DeviceSelectionDialog(camera_devices, microphone_devices, speaker_devices, self.video_window)
        selection_dialog.setWindowModality(Qt.WindowModality.NonModal)
        if self.current_video_device_preferences:
            self._set_device_dialog_defaults(selection_dialog, self.current_video_device_preferences)

        selection_dialog.accepted.connect(lambda: self._apply_video_device_changes(selection_dialog))
        selection_dialog.rejected.connect(self._clear_device_dialog_reference)
        selection_dialog.finished.connect(lambda _: selection_dialog.deleteLater())
        self.device_selection_dialog = selection_dialog
        selection_dialog.show()

    def _apply_video_device_changes(self, selection_dialog):
        if selection_dialog is None:
            return

        camera_devices = enumerate_camera_devices()
        microphone_devices = enumerate_audio_input_devices()
        speaker_devices = enumerate_audio_output_devices()
        device_preferences = selection_dialog.selected_devices()
        has_camera = device_preferences["camera_device"] != NO_DEVICE_VALUE and bool(camera_devices)
        has_microphone = device_preferences["microphone_device"] != NO_DEVICE_VALUE and bool(microphone_devices)
        has_speakers = device_preferences["speaker_device"] != NO_DEVICE_VALUE and bool(speaker_devices)

        if not has_camera and not has_microphone and not has_speakers:
            QMessageBox.warning(
                self,
                "No Devices",
                "No usable camera, microphone, or speakers are available for the call."
            )
            return

        missing_features = []
        if not has_camera:
            missing_features.append("camera")
        if not has_microphone:
            missing_features.append("microphone")
        if not has_speakers:
            missing_features.append("speakers")
        if missing_features:
            QMessageBox.information(
                self,
                "Partial Call",
                "Applying call settings without: " + ", ".join(missing_features) + "."
            )

        self.current_video_device_preferences = device_preferences.copy()
        self.video_window.update_device_availability(
            has_camera=has_camera,
            has_microphone=has_microphone,
            has_speakers=has_speakers,
        )
        self.video_window.reset_call_view()

        if hasattr(self, "webrtc_thread") and self.webrtc_thread is not None:
            self.webrtc_thread.stop()

        self.webrtc_thread = WebRTCClientThread(
            host=SERVER_HOST,
            port=VIDEO_SIGNALING_PORT,
            username=self.username,
            group_id=self.active_group_id,
            signal_emitter=self.video_window.signals,
            device_preferences=device_preferences,
            transcript_callback=self.video_window.signals.transcript_chunk.emit,
        )
        self.webrtc_thread.start()
        self._clear_device_dialog_reference()

    def _set_device_dialog_defaults(self, selection_dialog, device_preferences):
        self._set_combo_to_value(selection_dialog.camera_combo, device_preferences.get("camera_device"))
        self._set_combo_to_value(selection_dialog.microphone_combo, device_preferences.get("microphone_device"))
        self._set_combo_to_value(selection_dialog.speaker_combo, device_preferences.get("speaker_device"))

    @staticmethod
    def _set_combo_to_value(combo_box, value):
        if value is None:
            value = "__auto__"
        index = combo_box.findData(value)
        if index >= 0:
            combo_box.setCurrentIndex(index)

    def _clear_device_dialog_reference(self):
        self.device_selection_dialog = None

    def _attach_video_window_handlers(self):
        if getattr(self.video_window, "_handlers_attached", False):
            return

        self.video_window.signals.cam_toggled.connect(self._forward_cam_toggle)
        self.video_window.signals.mic_toggled.connect(self._forward_mic_toggle)
        self.video_window.signals.devices_requested.connect(self._change_video_devices)
        self.video_window.signals.transcript_chunk.connect(self._handle_call_transcript_chunk)
        self.video_window._handlers_attached = True

    def _forward_cam_toggle(self, is_muted):
        if hasattr(self, "webrtc_thread") and self.webrtc_thread is not None:
            self.webrtc_thread.set_cam_muted(is_muted)

    def _forward_mic_toggle(self, is_muted):
        if hasattr(self, "webrtc_thread") and self.webrtc_thread is not None:
            self.webrtc_thread.set_mic_muted(is_muted)

    def _handle_call_transcript_chunk(self, speaker: str, text: str, timestamp: str):
        print(f"Transcription chunk received: speaker={speaker}, text={text}, room={self.current_call_room_id}")
        if self.current_call_room_id:
            self.call_transcript_store.append_entry(self.current_call_room_id, speaker, text, timestamp)
            print(f"Transcript stored for room {self.current_call_room_id}")
