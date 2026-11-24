from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QHBoxLayout, QLabel, QStyle, QToolButton, QWidget


class TitleBar(QWidget):
    def __init__(self, window) -> None:
        super().__init__(window)
        self.setObjectName("gpgwrapTitleBar")
        self.setAutoFillBackground(True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 4, 4)
        layout.setSpacing(8)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(24, 24)
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(self.icon_label)

        self.title_label = QLabel(window.windowTitle())
        self.title_label.setTextFormat(Qt.PlainText)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(self.title_label, 1)

        self.close_button = QToolButton()
        self.close_button.setIcon(
            self.style().standardIcon(QStyle.SP_TitleBarCloseButton)
        )
        self.close_button.setToolTip("Close")
        self.close_button.setAccessibleName("Close window")
        self.close_button.setAutoRaise(True)
        self.close_button.setFixedSize(28, 24)
        self.close_button.clicked.connect(window.close)
        layout.addWidget(self.close_button)

        self._set_icon(window.windowIcon())
        window.windowTitleChanged.connect(self.title_label.setText)
        window.windowIconChanged.connect(self._set_icon)

    def _set_icon(self, icon: QIcon) -> None:
        self.icon_label.setPixmap(icon.pixmap(20, 20))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            handle = self.window().windowHandle()
            if handle is not None and handle.startSystemMove():
                event.accept()
                return
        super().mousePressEvent(event)
