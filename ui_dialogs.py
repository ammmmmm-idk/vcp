# Save as: ui_dialogs.py
import os
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QDialog, QGridLayout, QWidget, QSlider, QStyle, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QUrl
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

from styles import VCPStyles

class VideoPlayerWindow(QDialog):
    def __init__(self, video_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Playing: {os.path.basename(video_path)}")
        self.setMinimumSize(600, 400)
        self.setStyleSheet("background-color: black; color: white;")

        layout = QVBoxLayout(self)
        self.video_widget = QVideoWidget()
        layout.addWidget(self.video_widget)

        controls_layout = QHBoxLayout()
        self.play_btn = QPushButton()
        self.play_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))
        self.play_btn.setFixedSize(30, 30)
        self.play_btn.setStyleSheet("background-color: #2D3748; border-radius: 5px;")
        self.play_btn.clicked.connect(self.toggle_play)
        controls_layout.addWidget(self.play_btn)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.sliderMoved.connect(self.set_position)
        controls_layout.addWidget(self.slider)
        layout.addLayout(controls_layout)

        self.player = QMediaPlayer()
        self.audio = QAudioOutput()
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video_widget)
        self.player.setSource(QUrl.fromLocalFile(video_path))
        self.audio.setVolume(0.7)

        self.player.positionChanged.connect(self.position_changed)
        self.player.durationChanged.connect(self.duration_changed)
        self.player.play()

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.play_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        else:
            self.player.play()
            self.play_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))

    def position_changed(self, position): self.slider.setValue(position)
    def duration_changed(self, duration): self.slider.setRange(0, duration)
    def set_position(self, position): self.player.setPosition(position)


class CreateGroupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(400, 250)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setStyleSheet(VCPStyles.AUTH_STYLE + VCPStyles.MODAL_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.addWidget(QLabel("Create or Join Group", objectName="Title"))

        self.name_in = QLineEdit()
        self.name_in.setPlaceholderText("Enter new name OR paste link...")
        layout.addWidget(self.name_in)

        btn = QPushButton("Submit")
        btn.setObjectName("PrimaryBtn")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn)

        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        layout.addWidget(cancel)


class FilterSelectionDialog(QDialog):
    filter_selected = pyqtSignal(str)

    def __init__(self, current_filter: str, parent=None):
        super().__init__(parent)
        self.setFixedSize(400, 450)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setStyleSheet(VCPStyles.MODAL_STYLE)

        layout = QVBoxLayout(self)
        title = QLabel("Select Video Filter")
        title.setStyleSheet("color: #63B3ED; font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title)

        grid_container = QWidget()
        grid = QGridLayout(grid_container)
        filters = [("None", "original"), ("Grayscale", "gray"), ("Blur", "blur"), ("Sepia", "sepia")]

        for i, (name, fid) in enumerate(filters):
            btn = QPushButton(name)
            btn.setObjectName("FilterCard")
            btn.clicked.connect(lambda _, f=fid: self._select(f))
            grid.addWidget(btn, i // 2, i % 2)

        layout.addWidget(grid_container)
        close_btn = QPushButton("Cancel")
        close_btn.clicked.connect(self.reject)
        layout.addWidget(close_btn)

    def _select(self, fid: str):
        self.filter_selected.emit(fid)
        self.accept()


class GroupManagementDialog(QDialog):
    group_renamed = pyqtSignal(str)
    group_left = pyqtSignal()

    def __init__(self, current_name: str, invite_link: str, parent=None):
        super().__init__(parent)
        self.setFixedSize(450, 450)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setStyleSheet(VCPStyles.AUTH_STYLE + VCPStyles.MODAL_STYLE)
        self.invite_link_str = invite_link

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        header = QLabel("Group Settings")
        header.setObjectName("Title")
        layout.addWidget(header)

        layout.addWidget(QLabel("<b style='color:#A0AEC0;'>RENAME GROUP</b>"))
        self.rename_in = QLineEdit()
        self.rename_in.setText(current_name)
        rename_btn = QPushButton("Save New Name")
        rename_btn.setObjectName("PrimaryBtn")
        rename_btn.clicked.connect(self._handle_rename)
        layout.addWidget(self.rename_in)
        layout.addWidget(rename_btn)
        layout.addSpacing(20)

        layout.addWidget(QLabel("<b style='color:#A0AEC0;'>INVITE LINK</b>"))
        self.link_display = QLineEdit()
        self.link_display.setText(self.invite_link_str)
        self.link_display.setReadOnly(True)
        self.link_display.setStyleSheet("background-color: #090B10; color: #63B3ED;")
        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.setObjectName("PrimaryBtn")
        copy_btn.clicked.connect(self._copy_link)
        layout.addWidget(self.link_display)
        layout.addWidget(copy_btn)

        layout.addStretch()
        leave_btn = QPushButton("Leave Current Group")
        leave_btn.setObjectName("DangerBtn")
        leave_btn.clicked.connect(self._handle_leave)
        layout.addWidget(leave_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

    def _handle_rename(self):
        new_name = self.rename_in.text()
        if new_name:
            self.group_renamed.emit(new_name)
            self.accept()

    def _copy_link(self):
        QApplication.clipboard().setText(self.invite_link_str)
        self.link_display.setText("Copied!")

    def _handle_leave(self):
        self.group_left.emit()
        self.accept()
