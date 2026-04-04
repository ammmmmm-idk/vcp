# Save as: ui_video.py
import numpy as np
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGridLayout
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QObject
from PyQt6.QtGui import QImage, QPixmap


class VideoSignals(QObject):
    # The bridge from WebRTC to PyQt
    new_frame = pyqtSignal(str, QImage)
    # NEW: True means muted/off, False means active/on
    cam_toggled = pyqtSignal(bool)


class VideoWindow(QWidget):
    # Custom signal for when the window closes
    closed_signal = pyqtSignal()

    def __init__(self, room_name):
        super().__init__()
        # 1. Name of the call is exactly the name of the window!
        self.setWindowTitle(room_name)
        self.setMinimumSize(900, 650)
        self.setStyleSheet("background-color: #1A202C;")  # Dark theme background

        self.signals = VideoSignals()
        self.signals.new_frame.connect(self.update_video_feed)

        self.video_labels = {}
        self._setup_ui()

    def _setup_ui(self):
        # Main layout for the whole window with zero margins so the toolbar touches the edges
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ==========================================
        # TOP: VIDEO GRID AREA
        # ==========================================
        video_container = QWidget()
        video_layout = QVBoxLayout(video_container)
        video_layout.setContentsMargins(10, 10, 10, 10)

        self.grid_layout = QGridLayout()
        video_layout.addLayout(self.grid_layout)

        # Add the video container to main layout and give it a stretch factor of 1
        # so it pushes the toolbar to the very bottom.
        main_layout.addWidget(video_container, stretch=1)

        # ==========================================
        # BOTTOM: TOOLBAR AREA
        # ==========================================
        toolbar_container = QWidget()
        toolbar_container.setStyleSheet("background-color: #2D3748; border-top: 2px solid #4A5568;")
        toolbar_layout = QHBoxLayout(toolbar_container)
        toolbar_layout.setContentsMargins(15, 15, 15, 15)
        toolbar_layout.setSpacing(20)

        # Create Buttons
        self.btn_mic = QPushButton("🎤 Mic: On")
        self.btn_cam = QPushButton("📷 Cam: On")
        self.btn_hangup = QPushButton("☎ Hang Up")

        # Styling for default toggles
        self.btn_style_on = """
            QPushButton {
                background-color: #4A5568; color: white; padding: 12px 24px;
                border-radius: 8px; font-weight: bold; font-size: 14px; border: none;
            }
            QPushButton:hover { background-color: #718096; }
        """
        self.btn_style_off = """
            QPushButton {
                background-color: #E53E3E; color: white; padding: 12px 24px;
                border-radius: 8px; font-weight: bold; font-size: 14px; border: none;
            }
            QPushButton:hover { background-color: #FC8181; }
        """

        # Apply initial styles
        self.btn_mic.setStyleSheet(self.btn_style_on)
        self.btn_cam.setStyleSheet(self.btn_style_on)
        self.btn_hangup.setStyleSheet(self.btn_style_off)

        # Make Mic and Cam act as toggles
        self.btn_mic.setCheckable(True)
        self.btn_cam.setCheckable(True)
        self.btn_mic.clicked.connect(self._toggle_mic)
        self.btn_cam.clicked.connect(self._toggle_cam)

        # Center the buttons in the toolbar using stretch space on both sides
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(self.btn_mic)
        toolbar_layout.addWidget(self.btn_cam)
        toolbar_layout.addWidget(self.btn_hangup)
        toolbar_layout.addStretch()

        # Add the toolbar to the bottom of the main layout
        main_layout.addWidget(toolbar_container)

        # Hang up triggers the window to close (which cascades to cleaning up network)
        self.btn_hangup.clicked.connect(self.close)

    # --- UI Toggle Logic ---
    def _toggle_mic(self, checked):
        if checked:
            self.btn_mic.setText("🔇 Mic: Off")
            self.btn_mic.setStyleSheet(self.btn_style_off)
        else:
            self.btn_mic.setText("🎤 Mic: On")
            self.btn_mic.setStyleSheet(self.btn_style_on)

    def _toggle_cam(self, checked):
        # NEW: Shout down to the background thread that the state changed!
        self.signals.cam_toggled.emit(checked)

        if checked:
            self.btn_cam.setText("🚫 Cam: Off")
            self.btn_cam.setStyleSheet(self.btn_style_off)
        else:
            self.btn_cam.setText("📷 Cam: On")
            self.btn_cam.setStyleSheet(self.btn_style_on)

    def add_video_feed(self, username):
        container = QVBoxLayout()

        label = QLabel()
        label.setStyleSheet("background-color: #000000; border: 2px solid #4A5568; border-radius: 10px;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setMinimumSize(320, 240)

        name_label = QLabel(username)
        name_label.setStyleSheet("color: white; font-weight: bold; font-size: 14px;")
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        container.addWidget(label)
        container.addWidget(name_label)

        self.video_labels[username] = label

        count = len(self.video_labels) - 1
        row = count // 2
        col = count % 2
        self.grid_layout.addLayout(container, row, col)

    @pyqtSlot(str, QImage)
    def update_video_feed(self, username, qt_image):
        if username not in self.video_labels:
            self.add_video_feed(username)

        scaled_image = qt_image.scaled(
            self.video_labels[username].size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.video_labels[username].setPixmap(QPixmap.fromImage(scaled_image))

    def closeEvent(self, event):
        """Override the standard window close 'X' to ensure we emit our network cleanup signal."""
        self.closed_signal.emit()
        super().closeEvent(event)