# Save as: Gui.py
from PyQt6.QtWidgets import QMainWindow, QStackedWidget
from styles import VCPStyles
from ui_auth import AuthWidget
from ui_portal import PortalWidget


class VCPApp(QMainWindow):
    def __init__(self, net_client):
        super().__init__()
        self.setWindowTitle("VCP - Video Calling Portal")
        self.setMinimumSize(1200, 800)

        # Load the global CSS rules
        self.setStyleSheet(VCPStyles.AUTH_STYLE + VCPStyles.PORTAL_STYLE + VCPStyles.MODAL_STYLE)

        self.main_stack = QStackedWidget()
        self.setCentralWidget(self.main_stack)

        # --- THE TWO MAIN SCREENS ---

        # 1. Auth Screen (Index 0)
        self.auth_widget = AuthWidget()
        self.auth_widget.auth_successful.connect(self._on_auth_success)
        self.main_stack.addWidget(self.auth_widget)

        # 2. Portal Screen (Index 1)
        self.portal_widget = PortalWidget(net_client, parent=self)
        self.main_stack.addWidget(self.portal_widget)

    def _on_auth_success(self, username, email, db_groups, session_token):
        """When Login finishes, pass user info to the Portal and switch screens!"""

        # Give the Portal the database data it needs to setup the UI
        self.portal_widget.initialize_user(username, email, db_groups, session_token)

        # Flip the page to the Main Dashboard
        self.main_stack.setCurrentIndex(1)
