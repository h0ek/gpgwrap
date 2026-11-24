from __future__ import annotations

import subprocess
from threading import Event

from PySide6.QtCore import QThread, QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from .process import execute_process


class ProcessWorker(QThread):
    def __init__(self, command: list[str], data: bytes | None, parent=None):
        super().__init__(parent)
        self.command = command
        self.data = data
        self.cancelled = Event()
        self.result = None
        self.error = None

    def run(self) -> None:
        try:
            self.result = execute_process(self.command, self.data, self.cancelled)
        except Exception as error:
            self.error = error
        finally:
            self.data = None


class OperationDialog(QDialog):
    def __init__(self, command: list[str], data: bytes | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("GPG operation")
        self.setWindowModality(Qt.ApplicationModal)
        self.setMinimumWidth(340)
        layout = QVBoxLayout(self)
        self.label = QLabel("GPG is working. Complete any pinentry prompt to continue.")
        self.label.setWordWrap(True)
        layout.addWidget(self.label)
        progress = QProgressBar()
        progress.setRange(0, 0)
        layout.addWidget(progress)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        layout.addWidget(self.cancel_button)
        self.worker = ProcessWorker(command, data, self)
        self.worker.finished.connect(self.accept)

    def reject(self) -> None:
        self.worker.cancelled.set()
        self.label.setText("Cancelling the GPG operation...")
        self.cancel_button.setEnabled(False)

    def closeEvent(self, event) -> None:
        self.reject()
        event.ignore()


def run_process_dialog(
    parent, command: list[str], data: bytes | None
) -> subprocess.CompletedProcess:
    owner = QApplication.activeModalWidget() or parent
    dialog = OperationDialog(command, data, owner)
    QTimer.singleShot(0, dialog.worker.start)
    dialog.exec()
    dialog.worker.wait()
    result, error = dialog.worker.result, dialog.worker.error
    dialog.deleteLater()
    if error is not None:
        raise error
    return result
