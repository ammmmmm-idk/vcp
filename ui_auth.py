# Save as: ui_auth.py

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QFrame, QLabel,
    QLineEdit, QPushButton, QStackedWidget, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from qasync import asyncSlot

import asyncio
import ssl
import protocol
from config import SERVER_HOST, CHAT_PORT


class AuthWidget(QWidget):
    # This signal acts as a bridge. When verified, it sends (username, email, saved_groups) back to Gui.py
    auth_successful = pyqtSignal(str, str, list, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.username = "User"
        self.pending_email = None
        self.pending_flow = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.auth_stack = QStackedWidget()
        layout.addWidget(self.auth_stack)

        self._setup_ui()

    def _setup_ui(self):
        # 1. Login Page
        login_page = QWidget()
        l_lay = QVBoxLayout(login_page)
        l_card = QFrame()
        l_card.setObjectName("AuthCard")
        lc_lay = QVBoxLayout(l_card)

        lc_lay.addWidget(QLabel("VCP", objectName="Title"), alignment=Qt.AlignmentFlag.AlignCenter)
        lc_lay.addWidget(QLabel("Login to your VCP account", objectName="Subtitle"),
                         alignment=Qt.AlignmentFlag.AlignCenter)

        self.login_user = QLineEdit()
        self.login_user.setPlaceholderText("Email Address")
        self.login_pass = QLineEdit()
        self.login_pass.setPlaceholderText("Password")
        self.login_pass.setEchoMode(QLineEdit.EchoMode.Password)

        l_btn = QPushButton("Login", objectName="PrimaryBtn")
        l_btn.clicked.connect(self._handle_login)

        goto_signup = QPushButton("Don't have an account? Sign Up", objectName="LinkBtn")
        goto_signup.clicked.connect(lambda: self.auth_stack.setCurrentIndex(1))

        lc_lay.addWidget(self.login_user)
        lc_lay.addWidget(self.login_pass)
        lc_lay.addWidget(l_btn)
        lc_lay.addWidget(goto_signup)
        l_lay.addStretch()
        l_lay.addWidget(l_card, alignment=Qt.AlignmentFlag.AlignCenter)
        l_lay.addStretch()

        # 2. Sign-Up Page
        signup_page = QWidget()
        s_lay = QVBoxLayout(signup_page)
        s_card = QFrame()
        s_card.setObjectName("AuthCard")
        sc_lay = QVBoxLayout(s_card)

        sc_lay.addWidget(QLabel("Join VCP", objectName="Title"), alignment=Qt.AlignmentFlag.AlignCenter)

        self.reg_name = QLineEdit()
        self.reg_name.setPlaceholderText("Full Name")
        self.reg_email = QLineEdit()
        self.reg_email.setPlaceholderText("Email Address")
        self.reg_pass = QLineEdit()
        self.reg_pass.setPlaceholderText("Create Password")
        self.reg_pass.setEchoMode(QLineEdit.EchoMode.Password)

        s_btn = QPushButton("Create Account", objectName="PrimaryBtn")
        s_btn.clicked.connect(self._handle_signup)

        goto_login = QPushButton("Already have an account? Login", objectName="LinkBtn")
        goto_login.clicked.connect(lambda: self.auth_stack.setCurrentIndex(0))

        sc_lay.addWidget(self.reg_name)
        sc_lay.addWidget(self.reg_email)
        sc_lay.addWidget(self.reg_pass)
        sc_lay.addWidget(s_btn)
        sc_lay.addWidget(goto_login)
        s_lay.addStretch()
        s_lay.addWidget(s_card, alignment=Qt.AlignmentFlag.AlignCenter)
        s_lay.addStretch()

        # 3. Verify Page
        verify_page = QWidget()
        v_lay = QVBoxLayout(verify_page)
        v_card = QFrame()
        v_card.setObjectName("AuthCard")
        vc_lay = QVBoxLayout(v_card)

        vc_lay.addWidget(QLabel("Verify Identity", objectName="Title"))
        vc_lay.addWidget(QLabel("Enter the code sent to your email", objectName="Subtitle"))

        self.code_in = QLineEdit()
        self.code_in.setPlaceholderText("000000")
        self.code_in.setAlignment(Qt.AlignmentFlag.AlignCenter)

        finish_btn = QPushButton("Verify Code", objectName="PrimaryBtn")
        finish_btn.clicked.connect(self._handle_verify)

        vc_lay.addWidget(self.code_in)
        vc_lay.addWidget(finish_btn)
        v_lay.addStretch()
        v_lay.addWidget(v_card, alignment=Qt.AlignmentFlag.AlignCenter)
        v_lay.addStretch()

        self.auth_stack.addWidget(login_page)
        self.auth_stack.addWidget(signup_page)
        self.auth_stack.addWidget(verify_page)

    @asyncSlot()
    async def _handle_signup(self):
        fullname = self.reg_name.text().strip()
        email = self.reg_email.text().strip().lower()
        password = self.reg_pass.text().strip()

        if not fullname or not email or not password:
            QMessageBox.warning(self, "Missing Fields", "Please fill in your full name, email, and password.")
            return
        response = await self._send_auth_request({
            "action": "signup",
            "fullname": fullname,
            "email": email,
            "password": password,
        })
        if not response:
            QMessageBox.critical(self, "Connection Error", "Could not reach the authentication server.")
            return
        if response.get("action") == "error":
            QMessageBox.warning(self, "Sign Up Failed", response.get("message", "Signup failed."))
            return

        self.auth_stack.setCurrentIndex(2)
        self.pending_email = email
        self.username = fullname
        self.pending_flow = "signup"

    @asyncSlot()
    async def _handle_login(self):
        email = self.login_user.text().strip().lower()
        password = self.login_pass.text().strip()

        if not email or not password:
            QMessageBox.warning(self, "Missing Fields", "Please enter your email and password.")
            return
        response = await self._send_auth_request({
            "action": "login",
            "email": email,
            "password": password,
        })
        if not response:
            QMessageBox.critical(self, "Connection Error", "Could not reach the authentication server.")
            return
        if response.get("action") == "error":
            QMessageBox.warning(self, "Login Failed", response.get("message", "Login failed."))
            return

        self.pending_email = email
        self.pending_flow = "login"
        self.auth_stack.setCurrentIndex(2)

    @asyncSlot()
    async def _handle_verify(self):
        code = self.code_in.text().strip()
        email = self.pending_email
        if not email:
            self.auth_stack.setCurrentIndex(0)
            return

        response = await self._send_auth_request({
            "action": "verify_auth_code",
            "email": email,
            "code": code,
        })
        if not response:
            QMessageBox.critical(self, "Connection Error", "Could not reach the authentication server.")
            return
        if response.get("action") == "error":
            QMessageBox.warning(self, "Verification Failed", response.get("message", "Verification failed."))
            return

        self.username = response.get("username", self.username)
        db_groups = response.get("groups", [])
        session_token = response.get("session_token", "")
        self.auth_successful.emit(self.username, email, db_groups, session_token)

    async def _send_auth_request(self, payload: dict):
        writer = None
        try:
            # Create SSL context that doesn't verify self-signed certificates
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            reader, writer = await asyncio.open_connection(
                SERVER_HOST, CHAT_PORT, ssl=ssl_context
            )
            await protocol.send_message(writer, payload)
            return await protocol.receive_message(reader)
        except Exception:
            return None
        finally:
            if writer:
                writer.close()
                await writer.wait_closed()
