# Save as: ui_video.py
import math
import numpy as np
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGridLayout, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QObject
from PyQt6.QtGui import QImage, QPixmap


class VideoSignals(QObject):
    # The bridge from WebRTC to PyQt
    new_frame = pyqtSignal(str, QImage)
    # NEW: True means muted/off, False means active/on
    mic_toggled = pyqtSignal(bool)
    cam_toggled = pyqtSignal(bool)
    peer_disconnected = pyqtSignal(str)


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
        self.signals.peer_disconnected.connect(self.remove_video_feed)

        self.video_labels = {}
        self.video_containers = {}
        self.video_order = []
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
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(12)
        video_layout.addLayout(self.grid_layout, 1)

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
        self.signals.mic_toggled.emit(checked)
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
        if username in self.video_containers:
            return

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(8)
        container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        container.setMinimumSize(0, 0)

        label = QLabel()
        label.setStyleSheet("background-color: #000000; border: 2px solid #4A5568; border-radius: 10px;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setMinimumSize(0, 0)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        name_label = QLabel(username)
        name_label.setStyleSheet("color: white; font-weight: bold; font-size: 14px;")
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        container_layout.addWidget(label, 1)
        container_layout.addWidget(name_label)

        self.video_labels[username] = label
        self.video_containers[username] = container
        self.video_order.append(username)
        self._relayout_video_grid()

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

    @pyqtSlot(str)
    def remove_video_feed(self, username):
        label = self.video_labels.pop(username, None)
        container = self.video_containers.pop(username, None)
        if username in self.video_order:
            self.video_order.remove(username)
        if label is not None:
            label.clear()
        if container is not None:
            self.grid_layout.removeWidget(container)
            container.setParent(None)
            container.deleteLater()
        self._relayout_video_grid()

    def _relayout_video_grid(self):
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

        count = len(self.video_order)
        if count == 0:
            return

        columns = math.ceil(math.sqrt(count))
        rows = math.ceil(count / columns)

        for row in range(rows):
            self.grid_layout.setRowStretch(row, 1)
        for col in range(columns):
            self.grid_layout.setColumnStretch(col, 1)

        for index, username in enumerate(self.video_order):
            container = self.video_containers.get(username)
            if container is None:
                continue
            row = index // columns
            col = index % columns
            self.grid_layout.addWidget(container, row, col)

    def closeEvent(self, event):
        """Override the standard window close 'X' to ensure we emit our network cleanup signal."""
        self.closed_signal.emit()
        super().closeEvent(event)
