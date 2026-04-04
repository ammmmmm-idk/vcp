# Save as: ui_portal.py
import os
import asyncio
from datetime import datetime
from urllib.parse import urlparse, parse_qs, quote, unquote

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QTextBrowser, QFileDialog, QApplication, QListWidget, QSplitter, QMessageBox
)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QCursor, QDesktopServices
from qasync import asyncSlot

from database import create_or_update_group, add_user_to_group
import file_client
from ui_dialogs import FilterSelectionDialog, CreateGroupDialog, GroupManagementDialog
from webrtc_thread import WebRTCClientThread
from ui_video import VideoWindow



class PortalWidget(QWidget):
    def __init__(self, net_client, parent=None):
        super().__init__(parent)
        self.net_client = net_client
        self.net_client.message_received.connect(self._handle_network_message)
        self.net_client.connection_status.connect(self._handle_network_status)

        self.username = "User"
        self.pending_email = None

        self.group_buttons = {}
        self.groups_data = {"global-lobby-001": "Lobby"}
        self.active_group_id = "global-lobby-001"
        self.active_group_name = "Lobby"

        self._setup_ui()

    def initialize_user(self, username, email, db_groups):
        self.username = username
        self.pending_email = email
        for row in db_groups:
            gid = row["group_id"]
            gname = row["group_name"]
            if gid not in self.groups_data:
                self.groups_data[gid] = gname
                self._add_group_btn_ui(gid, gname)
        self._switch_group("global-lobby-001")

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
                    asyncio.create_task(self._handle_file_message(
                        msg_data["sender"], filename,
                        msg_data.get("color", "#E2E8F0"), msg_data.get("timestamp", "")
                    ))
                else:
                    self._add_chat_msg(msg_data["sender"], msg_text, msg_data.get("color", "#E2E8F0"),
                                       msg_data.get("timestamp", ""))

        elif action == "chat":
            self._add_chat_msg(payload["sender"], payload["msg"], payload.get("color", "#E2E8F0"),
                               payload.get("timestamp", ""))

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
        if status_type == "error":
            self._add_chat_msg("System Error", msg, "#E53E3E")

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
                asyncio.create_task(self._safe_async_group_action(text))

    async def _safe_async_group_action(self, text: str):
        try:
            if text.startswith("http"):
                parsed = urlparse(text)
                group_id = parsed.path.split("/")[-1]
                query_params = parse_qs(parsed.query)
                group_name = unquote(query_params.get("name", ["Shared Group"])[0])

                if group_id and group_id not in self.groups_data:
                    self.groups_data[group_id] = group_name
                    self._add_group_btn_ui(group_id, group_name)
                    await create_or_update_group(group_id, group_name)
                    await add_user_to_group(self.pending_email, group_id)

                self._switch_group(group_id)
            else:
                import uuid
                new_id = str(uuid.uuid4())
                self.groups_data[new_id] = text
                self._add_group_btn_ui(new_id, text)
                await create_or_update_group(new_id, text)
                await add_user_to_group(self.pending_email, new_id)
                self._switch_group(new_id)
        except Exception as e:
            import traceback
            print("\n🚨 ERROR WHILE CREATING GROUP:")
            traceback.print_exc()

    def _get_invite_link(self):
        safe_name = quote(self.active_group_name)
        return f"https://vcp.app/join/{self.active_group_id}?name={safe_name}"

    def _open_group_mgmt(self):
        if self.active_group_id == "Groq AI": return
        diag = GroupManagementDialog(self.active_group_name, self._get_invite_link(), self)
        diag.group_renamed.connect(self._rename_active_group)
        diag.exec()

    def _rename_active_group(self, new_name):
        asyncio.create_task(self.net_client.send_rename(self.active_group_id, new_name))
        self._apply_rename(self.active_group_id, new_name)

    def _copy_link(self):
        if self.active_group_id != "Groq AI":
            QApplication.clipboard().setText(self._get_invite_link())
            print("Link copied to clipboard silently.")

    def _switch_group(self, group_id):
        if self.active_group_id == group_id: return

        self.active_group_id = group_id
        self.active_group_name = self.groups_data.get(group_id, "Unknown") if group_id != "Groq AI" else "Groq AI"

        for btn in self.group_buttons.values():
            btn.setProperty("active", False)
            btn.setStyle(btn.style())

        if group_id in self.group_buttons:
            self.group_buttons[group_id].setProperty("active", True)
            self.group_buttons[group_id].setStyle(self.group_buttons[group_id].style())

        self.chat_display.clear()
        self._update_sidebar_ui()

        if group_id != "Groq AI":
            self.btn_join_video.show()
            asyncio.create_task(self.net_client.connect_to_group(group_id, self.active_group_name, self.username))
        else:
            self.btn_join_video.hide()

    def _update_sidebar_ui(self):
        if self.active_group_id == "Groq AI":
            self.chat_header.setText("GROQ AI ASSISTANT")
            self.chat_input.setPlaceholderText("Ask Groq AI...")
        else:
            self.chat_header.setText(f"GROUP CHAT: {self.active_group_name}")
            self.chat_input.setPlaceholderText("Enter message...")

    @asyncSlot()
    async def _open_file_dialog(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Select File", "", "All Files (*)")
        if fname:
            local_time = datetime.now().strftime("%H:%M")
            filename = os.path.basename(fname)
            self._add_chat_msg("System", f"⏳ Uploading {filename}...", "#A0AEC0", local_time)
            await self.net_client.send_file(self.username, fname)
            await self.net_client.send_file_notification(self.username, filename)
            self._add_chat_msg("System", f"✅ {filename} uploaded successfully!", "#48BB78",
                               datetime.now().strftime("%H:%M"))

    async def _handle_file_message(self, sender: str, filename: str, color: str, timestamp: str):
        ext = os.path.splitext(filename)[1].lower()
        if ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp']:
            local_path = await file_client.download_file(filename)
            if local_path:
                file_uri = QUrl.fromLocalFile(local_path).toString()
                html_msg = f'<br><img src="{file_uri}" width="200" style="border-radius: 8px;"><br><i>{filename}</i>'
                self._add_raw_html(sender, html_msg, color, timestamp)
            else:
                self._add_chat_msg(sender, f"❌ [Failed to load image: {filename}]", "red", timestamp)
        else:
            icon = "🎥 Video" if ext in ['.mp4', '.mov', '.avi', '.mkv'] else "📄 File"
            file_html = f'''
            <div style="background-color:#2D3748; padding:10px; border-radius:5px; margin-top:5px; display:inline-block;">
                <b>{icon}:</b> {filename}<br>
                <a href="download://{filename}" style="color:#48BB78; text-decoration:none; font-weight:bold;">⬇️ Click here to Download & Open</a>
            </div>'''
            self._add_raw_html(sender, file_html, color, timestamp)

    async def _manual_download_task(self, filename: str):
        filename = os.path.basename(filename)
        downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        default_path = os.path.join(downloads_dir, filename).replace("\\", "/")
        ext = os.path.splitext(filename)[1]

        save_path, _ = QFileDialog.getSaveFileName(self, "Save File As...", default_path,
                                                   f"Files (*{ext});;All Files (*)",
                                                   options=QFileDialog.Option.DontUseNativeDialog)
        if save_path:
            local_time = datetime.now().strftime("%H:%M")
            self._add_chat_msg("System", f"⏳ מוריד: {filename}...", "#A0AEC0", local_time)
            success = await file_client.download_file(filename, destination=save_path)
            if success:
                self._add_chat_msg("System", f"✅ נשמר בהצלחה!", "#48BB78", local_time)
                QDesktopServices.openUrl(QUrl.fromLocalFile(save_path))

    def _handle_chat_link(self, url: QUrl):
        pos = self.chat_display.mapFromGlobal(QCursor.pos())
        raw_link = self.chat_display.anchorAt(pos) or url.toString()

        if "download://" in raw_link:
            filename = unquote(raw_link.split("download://")[-1]).lstrip('/')
            if filename: asyncio.create_task(self._manual_download_task(filename))
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
            self._add_chat_msg(self.username, txt, "#63B3ED", local_time)
            self.chat_input.clear()
            if self.active_group_id == "Groq AI":
                self._add_chat_msg("Groq", f"I received: '{txt}'", "#9F7AEA", local_time)
            else:
                await self.net_client.send_chat(sender=self.username, msg=txt)

    def _add_chat_msg(self, sender, msg, color, timestamp=""):
        time_str = f"<span style='color:#718096; font-size:10px;'>[{timestamp}]</span> " if timestamp else ""
        self.chat_display.append(f"<p style='margin:5px;'>{time_str}<b style='color:{color};'>{sender}:</b> {msg}</p>")

    def _add_raw_html(self, sender, html_content, color, timestamp=""):
        time_str = f"<span style='color:#718096; font-size:10px;'>[{timestamp}]</span> " if timestamp else ""
        self.chat_display.append(f"<p style='margin:5px;'>{time_str}<b style='color:{color};'>{sender}:</b></p>")
        self.chat_display.insertHtml(html_content)
        self.chat_display.append("<br>")

    def launch_video_call(self):
        """Triggered when the user clicks 'Join Video Call'"""
        # --- NEW: Prevent joining multiple calls at once ---
        if hasattr(self, 'webrtc_thread') and self.webrtc_thread is not None:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                "Active Call",
                "You are already in an active video call! Please hang up before joining another room."
            )
            return  # Stop here! Don't open a new window or start a new thread.
        # ---------------------------------------------------

        print(f"🚀 Launching Video Call for room: {self.active_group_id}")

        # 1. Pop open the Video Grid UI
        self.video_window = VideoWindow(self.active_group_name)
        self.video_window.show()

        # 2. Spin up the WebRTC Engine in the background
        self.webrtc_thread = WebRTCClientThread(
            host='127.0.0.1',  # <-- Restored to 127.0.0.1 (Change to your actual IPv4 if on 2 PCs!)
            port=8890,
            username=self.username,
            group_id=self.active_group_id,
            signal_emitter=self.video_window.signals
        )

        # 3. ACTUALLY START THE THREAD!
        self.webrtc_thread.start()

        # 4. Listen for the window closing (via the 'X' or Hang Up button)
        self.video_window.closed_signal.connect(self._stop_video_call)

    def _stop_video_call(self):
        """Cleans up the network thread when the window is closed."""
        print("Window closed! Shutting down network thread...")
        if hasattr(self, 'webrtc_thread') and self.webrtc_thread is not None:
            self.webrtc_thread.stop()
            self.webrtc_thread = None # Clears it out so we can start a new call later!

    def _open_video_window(self):
        # --- NEW: Prevent joining multiple calls at once ---
        if hasattr(self, 'webrtc_thread') and self.webrtc_thread is not None:
            QMessageBox.warning(
                self,
                "Active Call",
                "You are already in an active video call! Please hang up before joining another room."
            )
            return  # Stop here! Don't open a new window.
        # ---------------------------------------------------

        print(f"Opening Video Window for Room: {self.active_group_name} ({self.active_group_id})")

        # 1. Pop open the UI
        self.video_window = VideoWindow(self.active_group_name)
        self.video_window.show()

        # 2. Spin up the WebRTC Engine in the background
        self.webrtc_thread = WebRTCClientThread(
            host='127.0.0.1',  # CHANGE THIS TO 192.168.X.X IF TESTING ON 2 COMPUTERS!
            port=8890,  # The new Video Signaling Port!
            username=self.username,
            group_id=self.active_group_id,
            signal_emitter=self.video_window.signals
        )

        # 3. ACTUALLY START THE THREAD!
        self.webrtc_thread.start()

        # 4. Listen for the window closing (via the 'X' or Hang Up button)
        self.video_window.closed_signal.connect(self._stop_video_call)