import math

from PyQt6.QtCore import QObject, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget


WINDOW_MIN_WIDTH = 900
WINDOW_MIN_HEIGHT = 650
MAIN_LAYOUT_MARGIN = 0
MAIN_LAYOUT_SPACING = 0
VIDEO_AREA_MARGIN = 10
GRID_MARGIN = 0
GRID_SPACING = 12
TOOLBAR_BORDER_WIDTH = 2
TOOLBAR_PADDING = 15
TOOLBAR_SPACING = 20
TOGGLE_PADDING_VERTICAL = 12
TOGGLE_PADDING_HORIZONTAL = 24
TOGGLE_RADIUS = 8
TOGGLE_FONT_SIZE = 14
VIDEO_TILE_BORDER_WIDTH = 2
VIDEO_TILE_RADIUS = 10
VIDEO_TILE_SPACING = 8
NAME_FONT_SIZE = 14

WINDOW_BACKGROUND_COLOR = "#1A202C"
TOOLBAR_BACKGROUND_COLOR = "#2D3748"
TOOLBAR_BORDER_COLOR = "#4A5568"
BUTTON_ON_COLOR = "#4A5568"
BUTTON_ON_HOVER_COLOR = "#718096"
BUTTON_OFF_COLOR = "#E53E3E"
BUTTON_OFF_HOVER_COLOR = "#FC8181"
VIDEO_TILE_BACKGROUND_COLOR = "#000000"
VIDEO_TILE_BORDER_COLOR = "#4A5568"
TEXT_COLOR = "white"


def build_toggle_button_style(background_color: str, hover_color: str) -> str:
    return f"""
        QPushButton {{
            background-color: {background_color};
            color: {TEXT_COLOR};
            padding: {TOGGLE_PADDING_VERTICAL}px {TOGGLE_PADDING_HORIZONTAL}px;
            border-radius: {TOGGLE_RADIUS}px;
            font-weight: bold;
            font-size: {TOGGLE_FONT_SIZE}px;
            border: none;
        }}
        QPushButton:hover {{ background-color: {hover_color}; }}
    """


class VideoSignals(QObject):
    new_frame = pyqtSignal(str, QImage)
    mic_toggled = pyqtSignal(bool)
    cam_toggled = pyqtSignal(bool)
    peer_disconnected = pyqtSignal(str)


class VideoWindow(QWidget):
    closed_signal = pyqtSignal()

    def __init__(self, room_name):
        super().__init__()
        self.setWindowTitle(room_name)
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self.setStyleSheet(f"background-color: {WINDOW_BACKGROUND_COLOR};")

        self.signals = VideoSignals()
        self.signals.new_frame.connect(self.update_video_feed)
        self.signals.peer_disconnected.connect(self.remove_video_feed)

        self.video_labels = {}
        self.video_containers = {}
        self.video_order = []
        self.btn_style_on = build_toggle_button_style(BUTTON_ON_COLOR, BUTTON_ON_HOVER_COLOR)
        self.btn_style_off = build_toggle_button_style(BUTTON_OFF_COLOR, BUTTON_OFF_HOVER_COLOR)
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(MAIN_LAYOUT_MARGIN, MAIN_LAYOUT_MARGIN, MAIN_LAYOUT_MARGIN, MAIN_LAYOUT_MARGIN)
        main_layout.setSpacing(MAIN_LAYOUT_SPACING)

        video_container = QWidget()
        video_layout = QVBoxLayout(video_container)
        video_layout.setContentsMargins(VIDEO_AREA_MARGIN, VIDEO_AREA_MARGIN, VIDEO_AREA_MARGIN, VIDEO_AREA_MARGIN)

        self.grid_layout = QGridLayout()
        self.grid_layout.setContentsMargins(GRID_MARGIN, GRID_MARGIN, GRID_MARGIN, GRID_MARGIN)
        self.grid_layout.setSpacing(GRID_SPACING)
        video_layout.addLayout(self.grid_layout, 1)
        main_layout.addWidget(video_container, stretch=1)

        toolbar_container = QWidget()
        toolbar_container.setStyleSheet(
            f"background-color: {TOOLBAR_BACKGROUND_COLOR}; border-top: {TOOLBAR_BORDER_WIDTH}px solid {TOOLBAR_BORDER_COLOR};"
        )
        toolbar_layout = QHBoxLayout(toolbar_container)
        toolbar_layout.setContentsMargins(TOOLBAR_PADDING, TOOLBAR_PADDING, TOOLBAR_PADDING, TOOLBAR_PADDING)
        toolbar_layout.setSpacing(TOOLBAR_SPACING)

        self.btn_mic = QPushButton("Mic: On")
        self.btn_cam = QPushButton("Cam: On")
        self.btn_hangup = QPushButton("Hang Up")

        self.btn_mic.setStyleSheet(self.btn_style_on)
        self.btn_cam.setStyleSheet(self.btn_style_on)
        self.btn_hangup.setStyleSheet(self.btn_style_off)

        self.btn_mic.setCheckable(True)
        self.btn_cam.setCheckable(True)
        self.btn_mic.clicked.connect(self._toggle_mic)
        self.btn_cam.clicked.connect(self._toggle_cam)
        self.btn_hangup.clicked.connect(self.close)

        toolbar_layout.addStretch()
        toolbar_layout.addWidget(self.btn_mic)
        toolbar_layout.addWidget(self.btn_cam)
        toolbar_layout.addWidget(self.btn_hangup)
        toolbar_layout.addStretch()
        main_layout.addWidget(toolbar_container)

    def _toggle_mic(self, checked):
        self.signals.mic_toggled.emit(checked)
        if checked:
            self.btn_mic.setText("Mic: Off")
            self.btn_mic.setStyleSheet(self.btn_style_off)
            return

        self.btn_mic.setText("Mic: On")
        self.btn_mic.setStyleSheet(self.btn_style_on)

    def _toggle_cam(self, checked):
        self.signals.cam_toggled.emit(checked)
        if checked:
            self.btn_cam.setText("Cam: Off")
            self.btn_cam.setStyleSheet(self.btn_style_off)
            return

        self.btn_cam.setText("Cam: On")
        self.btn_cam.setStyleSheet(self.btn_style_on)

    def add_video_feed(self, username):
        if username in self.video_containers:
            return

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(MAIN_LAYOUT_MARGIN, MAIN_LAYOUT_MARGIN, MAIN_LAYOUT_MARGIN, MAIN_LAYOUT_MARGIN)
        container_layout.setSpacing(VIDEO_TILE_SPACING)
        container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        container.setMinimumSize(MAIN_LAYOUT_MARGIN, MAIN_LAYOUT_MARGIN)

        label = QLabel()
        label.setStyleSheet(
            f"background-color: {VIDEO_TILE_BACKGROUND_COLOR}; "
            f"border: {VIDEO_TILE_BORDER_WIDTH}px solid {VIDEO_TILE_BORDER_COLOR}; "
            f"border-radius: {VIDEO_TILE_RADIUS}px;"
        )
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setMinimumSize(MAIN_LAYOUT_MARGIN, MAIN_LAYOUT_MARGIN)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        name_label = QLabel(username)
        name_label.setStyleSheet(f"color: {TEXT_COLOR}; font-weight: bold; font-size: {NAME_FONT_SIZE}px;")
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
            Qt.TransformationMode.SmoothTransformation,
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

        participant_count = len(self.video_order)
        if participant_count == 0:
            return

        column_count = math.ceil(math.sqrt(participant_count))
        row_count = math.ceil(participant_count / column_count)

        for row_index in range(row_count):
            self.grid_layout.setRowStretch(row_index, 1)
        for column_index in range(column_count):
            self.grid_layout.setColumnStretch(column_index, 1)

        for index, username in enumerate(self.video_order):
            container = self.video_containers.get(username)
            if container is None:
                continue
            row_index = index // column_count
            column_index = index % column_count
            self.grid_layout.addWidget(container, row_index, column_index)

    def closeEvent(self, event):
        self.closed_signal.emit()
        super().closeEvent(event)
