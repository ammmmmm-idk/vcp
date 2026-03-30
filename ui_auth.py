# Save as: ui_auth.py

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QFrame, QLabel,
    QLineEdit, QPushButton, QStackedWidget
)
from PyQt6.QtCore import Qt, pyqtSignal
from qasync import asyncSlot

# Database and Auth logic is now completely contained here
from database import create_user, get_user_by_email, get_user_groups
from auth_service import hash_password, verify_password, generate_and_send_otp, validate_otp


class AuthWidget(QWidget):
    # This signal acts as a bridge. When verified, it sends (username, email, saved_groups) back to Gui.py
    auth_successful = pyqtSignal(str, str, list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.username = "User"
        self.pending_email = None

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

        if not fullname or not email or not password: return
        hashed_pw = hash_password(password)
        success = await create_user(fullname, email, hashed_pw)

        if not success:
            print("Error: Email already registered!")
            return

        self.pending_email = email
        self.username = fullname
        await generate_and_send_otp(email)
        self.auth_stack.setCurrentIndex(2)

    @asyncSlot()
    async def _handle_login(self):
        email = self.login_user.text().strip().lower()
        password = self.login_pass.text().strip()

        if not email or not password: return
        user = await get_user_by_email(email)

        if user and verify_password(user["password_hash"], password):
            self.pending_email = email
            self.username = user["fullname"]
            await generate_and_send_otp(email)
            self.auth_stack.setCurrentIndex(2)
        else:
            print("Error: Invalid email or password.")

    @asyncSlot()
    async def _handle_verify(self):
        code = self.code_in.text().strip()
        email = self.pending_email
        if not email:
            self.auth_stack.setCurrentIndex(0)
            return

        is_valid, msg = validate_otp(email, code)
        if is_valid:
            print("Authentication Successful!")
            # Load user's saved groups from the DB
            db_groups = await get_user_groups(email)
            # EMIT THE SIGNAL TO THE MAIN APP!
            self.auth_successful.emit(self.username, email, db_groups)
        else:
            print(f"Verification Failed: {msg}")