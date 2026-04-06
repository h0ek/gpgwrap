from __future__ import annotations

from pathlib import Path
from typing import List
from importlib.resources import files

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QAbstractItemView,
)

from . import __app_name__, __author__, __github_url__, __version__
from .gpg_service import GPGService
from .models import GPGKey


class AboutDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"About {__app_name__}")
        self.setMinimumWidth(420)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignCenter)

        try:
            icon_path = files("gpgwrap").joinpath("assets/gpgwrap.png")
            pixmap = QPixmap(str(icon_path))
            if not pixmap.isNull():
                icon_label.setPixmap(
                    pixmap.scaled(
                        96,
                        96,
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    )
                )
        except Exception:
            pass

        title_label = QLabel(f"<h2>{__app_name__}</h2>")
        title_label.setAlignment(Qt.AlignCenter)

        version_label = QLabel(f"Version {__version__}")
        version_label.setAlignment(Qt.AlignCenter)
        version_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        github_label = QLabel(f'<a href="{__github_url__}">{__github_url__}</a>')
        github_label.setAlignment(Qt.AlignCenter)
        github_label.setOpenExternalLinks(True)
        github_label.setTextInteractionFlags(Qt.TextBrowserInteraction)

        author_label = QLabel(f"Author: {__author__}")
        author_label.setAlignment(Qt.AlignCenter)
        author_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        credits_label = QLabel('Icons by <a href="https://icons8.com/">icons8.com</a>')
        credits_label.setAlignment(Qt.AlignCenter)
        credits_label.setOpenExternalLinks(True)
        credits_label.setTextInteractionFlags(Qt.TextBrowserInteraction)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)

        layout.addWidget(icon_label)
        layout.addWidget(title_label)
        layout.addWidget(version_label)
        layout.addWidget(github_label)
        layout.addSpacing(8)
        layout.addWidget(author_label)
        layout.addSpacing(8)
        layout.addWidget(credits_label)
        layout.addSpacing(12)
        layout.addWidget(close_btn, alignment=Qt.AlignCenter)

class GenerateKeyDialog(QDialog):
    def __init__(self, gpg: GPGService, parent=None) -> None:
        super().__init__(parent)
        self.gpg = gpg
        self.setWindowTitle("Generate key")
        self.resize(520, 360)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.email_edit = QLineEdit()
        self.comment_edit = QLineEdit()
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(["Modern ECC", "RSA 3072", "RSA 4096"])
        self.no_expiry = QCheckBox("No expiry")
        self.no_expiry.setChecked(True)
        self.expiry_edit = QLineEdit("1y")
        self.passphrase_edit = QLineEdit()
        self.passphrase_edit.setEchoMode(QLineEdit.Password)
        self.passphrase_confirm_edit = QLineEdit()
        self.passphrase_confirm_edit.setEchoMode(QLineEdit.Password)

        form.addRow("Name:", self.name_edit)
        form.addRow("Email:", self.email_edit)
        form.addRow("Comment:", self.comment_edit)
        form.addRow("Preset:", self.preset_combo)
        form.addRow("No expiry:", self.no_expiry)
        form.addRow("Expiry:", self.expiry_edit)
        form.addRow("Passphrase:", self.passphrase_edit)
        form.addRow("Confirm passphrase:", self.passphrase_confirm_edit)
        layout.addLayout(form)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output)

        btn_row = QHBoxLayout()
        self.generate_btn = QPushButton("Generate")
        self.generate_btn.clicked.connect(self.generate_key)
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        btn_row.addWidget(self.generate_btn)
        btn_row.addWidget(self.close_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.no_expiry.stateChanged.connect(self._toggle_expiry)
        self._toggle_expiry()

    def _toggle_expiry(self) -> None:
        self.expiry_edit.setEnabled(not self.no_expiry.isChecked())

    def generate_key(self) -> None:
        name = self.name_edit.text().strip()
        email = self.email_edit.text().strip()
        comment = self.comment_edit.text().strip()
        preset = self.preset_combo.currentText()
        expiry = "0" if self.no_expiry.isChecked() else self.expiry_edit.text().strip()
        passphrase = self.passphrase_edit.text()
        confirm = self.passphrase_confirm_edit.text()

        if not name:
            QMessageBox.warning(self, "Missing name", "Name is required.")
            return
        if not email:
            QMessageBox.warning(self, "Missing email", "Email is required.")
            return
        if not expiry:
            QMessageBox.warning(self, "Missing expiry", "Provide expiry or enable no expiry.")
            return
        if not passphrase:
            QMessageBox.warning(self, "Missing passphrase", "Passphrase is required.")
            return
        if passphrase != confirm:
            QMessageBox.warning(self, "Passphrase mismatch", "Passphrases do not match.")
            return

        result = self.gpg.generate_key(
            name=name,
            email=email,
            comment=comment,
            preset=preset,
            expiry=expiry,
            passphrase=passphrase,
        )

        if result.ok:
            self.output.setPlainText("Key was created successfully.")
            QMessageBox.information(self, "Success", "Key was created.")
        else:
            msg = result.stderr.strip() or self.gpg.describe_generic_failure(result)
            self.output.setPlainText(msg)
            QMessageBox.critical(self, "Key generation failed", msg)


class ManageKeysDialog(QDialog):
    def __init__(self, gpg: GPGService, parent=None) -> None:
        super().__init__(parent)
        self.gpg = gpg
        self.public_keys: List[GPGKey] = []
        self.secret_fingerprints: set[str] = set()
        self.setWindowTitle("Manage keys")
        self.resize(780, 560)
        self._build_ui()
        self.refresh_keys()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        top_row = QHBoxLayout()
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter keys...")
        self.filter_edit.textChanged.connect(self.populate_list)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_keys)

        top_row.addWidget(QLabel("Filter:"))
        top_row.addWidget(self.filter_edit)
        top_row.addWidget(refresh_btn)
        layout.addLayout(top_row)

        self.key_list = QListWidget()
        self.key_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.key_list.itemClicked.connect(self._remember_clicked_item)
        layout.addWidget(self.key_list)

        btn_row = QGridLayout()

        self.copy_btn = QPushButton("Copy public key")
        self.copy_btn.clicked.connect(self.copy_public_key)

        self.export_btn = QPushButton("Export public key")
        self.export_btn.clicked.connect(self.export_public_key)

        self.import_btn = QPushButton("Import key")
        self.import_btn.clicked.connect(self.import_key)

        self.delete_btn = QPushButton("Delete key")
        self.delete_btn.clicked.connect(self.delete_key)

        self.generate_btn = QPushButton("Generate key")
        self.generate_btn.clicked.connect(self.generate_key)

        btn_row.addWidget(self.copy_btn, 0, 0)
        btn_row.addWidget(self.export_btn, 0, 1)
        btn_row.addWidget(self.import_btn, 1, 0)
        btn_row.addWidget(self.delete_btn, 1, 1)
        btn_row.addWidget(self.generate_btn, 2, 0, 1, 2)

        layout.addLayout(btn_row)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output)
    
    def _remember_clicked_item(self, item: QListWidgetItem) -> None:
        self.key_list.setCurrentItem(item)

    def _match_key(self, key: GPGKey, term: str) -> bool:
        if not term:
            return True

        haystack = " ".join([key.key_id, key.fingerprint, *key.user_ids]).lower()
        return term.lower() in haystack

    def populate_list(self) -> None:
        self.key_list.clear()
        term = self.filter_edit.text().strip()

        for key in self.public_keys:
            if not self._match_key(key, term):
                continue

            suffix = " [secret key present]" if key.fingerprint in self.secret_fingerprints else ""

            item = QListWidgetItem(f"{key.primary_uid} | {key.key_id}{suffix}")
            item.setData(Qt.UserRole, key.fingerprint or key.key_id)
            item.setData(Qt.UserRole + 1, key.key_id)
            self.key_list.addItem(item)

            if self.key_list.count() == 1:
                self.key_list.setCurrentItem(item)

    def current_fingerprint(self) -> str | None:
        item = self.key_list.currentItem()
        if item is None:
            selected = self.key_list.selectedItems()
            if selected:
                item = selected[0]

        if item is None:
            return None

        value = item.data(Qt.UserRole)
        if not value:
            return None

        return str(value)

    def refresh_keys(self) -> None:
        self.public_keys = self.gpg.list_public_keys()
        self.secret_fingerprints = {key.fingerprint for key in self.gpg.list_secret_keys()}
        self.populate_list()
        self.output.setPlainText(f"Loaded {len(self.public_keys)} public keys.")

    def copy_public_key(self) -> None:
        fingerprint = self.current_fingerprint()
        if not fingerprint:
            QMessageBox.warning(self, "No key selected", "Select a key first.")
            return

        result = self.gpg.export_public_key_ascii(fingerprint)
        if result.ok:
            QApplication.clipboard().setText(result.stdout)
            QMessageBox.information(self, "Copied", "Public key copied to clipboard.")
            self.output.setPlainText("Public key copied to clipboard.")
        else:
            msg = result.stderr.strip() or self.gpg.describe_generic_failure(result)
            self.output.setPlainText(msg)
            QMessageBox.critical(self, "Export failed", msg)

    def export_public_key(self) -> None:
        fingerprint = self.current_fingerprint()
        if not fingerprint:
            QMessageBox.warning(self, "No key selected", "Select a key first.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export public key",
            f"{fingerprint}.asc",
            "ASCII armored key (*.asc);;All files (*)",
        )
        if not path:
            return

        result = self.gpg.export_public_key_to_file(fingerprint, path)
        if result.ok:
            self.output.setPlainText(f"Public key exported to:\n{path}")
            QMessageBox.information(self, "Exported", f"Public key exported to:\n{path}")
        else:
            msg = result.stderr.strip() or self.gpg.describe_generic_failure(result)
            self.output.setPlainText(msg)
            QMessageBox.critical(self, "Export failed", msg)

    def import_key(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import key",
            str(Path.home()),
            "Key files (*.asc *.gpg *.pgp *.key);;All files (*)",
        )
        if not path:
            return

        result = self.gpg.import_key_file(path)
        if result.ok:
            self.output.setPlainText(f"Key imported successfully:\n{path}")
            QMessageBox.information(self, "Imported", "Key imported successfully.")
            self.refresh_keys()
        else:
            msg = result.stderr.strip() or self.gpg.describe_generic_failure(result)
            self.output.setPlainText(msg)
            QMessageBox.critical(self, "Import failed", msg)

    def delete_key(self) -> None:
        fingerprint = self.current_fingerprint()
        if not fingerprint:
            QMessageBox.warning(self, "No key selected", "Select a key first.")
            return

        secret_too = fingerprint in self.secret_fingerprints

        extra = "\nA secret key also exists and will be deleted first." if secret_too else ""
        choice = QMessageBox.question(
            self,
            "Delete key",
            f"Fingerprint:\n{fingerprint}\n\nDelete this key?{extra}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if choice != QMessageBox.Yes:
            return

        result = self.gpg.delete_key(fingerprint, secret_too=secret_too)
        if result.ok:
            self.output.setPlainText(f"Key deleted:\n{fingerprint}")
            QMessageBox.information(self, "Deleted", "Key deleted successfully.")
            self.refresh_keys()
        else:
            msg = result.stderr.strip() or self.gpg.describe_generic_failure(result)
            self.output.setPlainText(msg)
            QMessageBox.critical(self, "Delete failed", msg)

    def generate_key(self) -> None:
        dialog = GenerateKeyDialog(self.gpg, self)
        dialog.exec()
        self.refresh_keys()

class RecipientPickerDialog(QDialog):
    def __init__(self, keys: List[GPGKey], selected_ids: List[str] | None = None, parent=None) -> None:
        super().__init__(parent)
        self.keys = keys
        self.selected_ids = set(selected_ids or [])
        self.setWindowTitle("Choose recipients")
        self.resize(720, 520)
        self._build_ui()
        self.populate_list()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        top_row = QHBoxLayout()
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter recipients...")
        self.filter_edit.textChanged.connect(self.populate_list)
        top_row.addWidget(QLabel("Filter:"))
        top_row.addWidget(self.filter_edit)
        layout.addLayout(top_row)

        self.key_list = QListWidget()
        self.key_list.setSelectionMode(QAbstractItemView.MultiSelection)
        layout.addWidget(self.key_list)

        btn_row = QHBoxLayout()
        ok_btn = QPushButton("Use selected")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

    def _match_key(self, key: GPGKey, term: str) -> bool:
        if not term:
            return True
        haystack = " ".join([key.key_id, key.fingerprint, *key.user_ids]).lower()
        return term.lower() in haystack

    def populate_list(self) -> None:
        selected_before = set(self.selected_key_ids())
        if not selected_before:
            selected_before = set(self.selected_ids)

        self.key_list.clear()
        term = self.filter_edit.text().strip()

        for key in self.keys:
            if not self._match_key(key, term):
                continue

            item = QListWidgetItem(f"{key.primary_uid} | {key.key_id}")
            item.setData(Qt.UserRole, key.key_id)
            self.key_list.addItem(item)

            if key.key_id in selected_before:
                item.setSelected(True)

    def selected_key_ids(self) -> List[str]:
        values: List[str] = []
        for item in self.key_list.selectedItems():
            value = item.data(Qt.UserRole)
            if value:
                values.append(str(value))
        return values