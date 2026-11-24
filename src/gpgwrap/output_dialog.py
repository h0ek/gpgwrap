from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from .file_io import validate_output


def confirm_output(parent, value: str, source: str | None = None) -> bool | None:
    try:
        path = validate_output(value, source)
    except (OSError, ValueError, RuntimeError) as error:
        QMessageBox.critical(parent, "Invalid output file", str(error))
        return None
    if not path.exists():
        return False
    answer = QMessageBox.question(
        parent,
        "Replace output file?",
        f"The following file already exists:\n{path}\n\nReplace it after this operation succeeds?",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No,
    )
    return True if answer == QMessageBox.Yes else None
