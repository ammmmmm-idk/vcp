# Save as: ui_video.py
import numpy as np
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGridLayout
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QObject
from PyQt6.QtGui import QImage, QPixmap


class VideoSignals(QObject):
    # The bridge from WebRTC to PyQt
    new_frame = pyqtSignal(str, QImage)


class VideoWindow(QWidget):
    # 1. ADDED: Custom signal for when the window closes
    closed_signal = pyqtSignal()

    def __init__(self, room_name):
        super().__init__()
        self.setWindowTitle(f"Video Call - {room_name}")
        self.setMinimumSize(800, 600)
        self.setStyleSheet("background-color: #1A202C;")

        self.signals = VideoSignals()
        self.signals.new_frame.connect(self.update_video_feed)

        self.video_labels = {}
        self._setup_ui(room_name)

    def _setup_ui(self, room_name):
        layout = QVBoxLayout(self)

        header = QLabel(f"Secure P2P Call: {room_name}")
        header.setStyleSheet("color: #63B3ED; font-size: 18px; font-weight: bold;")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)

        self.grid_layout = QGridLayout()
        layout.addLayout(self.grid_layout)

        controls_layout = QHBoxLayout()
        controls_layout.addStretch()
        self.btn_hangup = QPushButton("☎ Hang Up")
        self.btn_hangup.setStyleSheet("background-color: #E53E3E; color: white; padding: 10px; border-radius: 5px;")

        # 2. ADDED: Make the Hang Up button trigger the window to close
        self.btn_hangup.clicked.connect(self.close)

        controls_layout.addWidget(self.btn_hangup)
        controls_layout.addStretch()
        layout.addLayout(controls_layout)

    def add_video_feed(self, username):
        container = QVBoxLayout()

        label = QLabel()
        label.setStyleSheet("background-color: #000000; border: 2px solid #2D3748; border-radius: 10px;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setMinimumSize(320, 240)

        name_label = QLabel(username)
        name_label.setStyleSheet("color: white; font-weight: bold;")
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

        scaled_image = qt_image.scaled(320, 240, Qt.AspectRatioMode.KeepAspectRatio)
        self.video_labels[username].setPixmap(QPixmap.fromImage(scaled_image))

    # 3. ADDED: Catch the physical "X" button and emit the signal
    def closeEvent(self, event):
        self.closed_signal.emit()
        super().closeEvent(event)