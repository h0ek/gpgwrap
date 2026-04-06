from __future__ import annotations

from pathlib import Path
from typing import List, Optional
from importlib.resources import files

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QStackedWidget
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QRadioButton,
    QSizePolicy,
    QStatusBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QToolButton,
)

from .dialogs import AboutDialog, ManageKeysDialog, RecipientPickerDialog
from .gpg_service import GPGService
from .models import GPGKey, GPGResult


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.gpg = GPGService()
        self.public_keys: List[GPGKey] = []
        self.secret_keys: List[GPGKey] = []
        self.text_recipient_ids: List[str] = []
        self.file_recipient_ids: List[str] = []

        self.current_mode = "text"
        self.current_text_action = "encrypt"
        self.current_file_action = "encrypt"

        self.setWindowTitle("GPGWrap")
        self.resize(900, 780)

        self.status = QStatusBar()
        self.setStatusBar(self.status)

        self._load_icon()
        self._build_ui()
        self._build_menu()
        self.refresh_keys()

        if not self.gpg.check_gpg_available():
            self._show_error(
                "GPG not found",
                "Could not find 'gpg' in PATH. Install GnuPG first.",
            )

    def _load_icon(self) -> None:
        try:
            icon_path = files("gpgwrap").joinpath("assets/gpgwrap.png")
            self.setWindowIcon(QIcon(str(icon_path)))
        except Exception:
            pass

    def _build_menu(self) -> None:
        menubar = self.menuBar()
        app_menu = menubar.addMenu("App")

        refresh_action = QAction("Refresh keys", self)
        refresh_action.triggered.connect(self.refresh_keys)

        keys_action = QAction("Manage keys", self)
        keys_action.triggered.connect(self.open_manage_keys)

        clear_action = QAction("Clear fields", self)
        clear_action.triggered.connect(self.clear_all_fields)

        about_action = QAction("About", self)
        about_action.triggered.connect(self.open_about)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.close)

        app_menu.addAction(refresh_action)
        app_menu.addAction(keys_action)
        app_menu.addAction(clear_action)
        app_menu.addSeparator()
        app_menu.addAction(about_action)
        app_menu.addAction(quit_action)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        root.addLayout(self._build_mode_row())

        self.mode_stack = QStackedWidget()
        self.text_mode_widget = self._build_text_section()
        self.file_mode_widget = self._build_file_section()

        self.mode_stack.addWidget(self.text_mode_widget)
        self.mode_stack.addWidget(self.file_mode_widget)

        root.addWidget(self.mode_stack, 1)
        root.addWidget(self._build_log_section())

        self._apply_mode_visibility()
        self._apply_text_action_ui()
        self._apply_file_action_ui()
        self._update_text_recipient_label()
        self._update_file_recipient_label()

    def _build_mode_row(self) -> QHBoxLayout:
        layout = QHBoxLayout()

        layout.addWidget(QLabel("Mode:"))

        self.mode_group = QButtonGroup(self)

        self.text_mode_btn = QRadioButton("Text")
        self.file_mode_btn = QRadioButton("File")
        self.text_mode_btn.setChecked(True)

        self.mode_group.addButton(self.text_mode_btn)
        self.mode_group.addButton(self.file_mode_btn)

        self.text_mode_btn.toggled.connect(self._toggle_mode)

        layout.addWidget(self.text_mode_btn)
        layout.addWidget(self.file_mode_btn)
        layout.addStretch(1)

        return layout

    def _build_text_section(self) -> QGroupBox:
        box = QGroupBox("Text mode")
        layout = QVBoxLayout(box)

        actions_row = QHBoxLayout()
        actions_row.addWidget(QLabel("Action:"))

        self.text_action_group = QButtonGroup(self)
        self.text_encrypt_btn = QRadioButton("Encrypt")
        self.text_decrypt_btn = QRadioButton("Decrypt")
        self.text_sign_btn = QRadioButton("Sign")
        self.text_verify_btn = QRadioButton("Verify")
        self.text_encrypt_btn.setChecked(True)

        for btn in [
            self.text_encrypt_btn,
            self.text_decrypt_btn,
            self.text_sign_btn,
            self.text_verify_btn,
        ]:
            self.text_action_group.addButton(btn)
            btn.toggled.connect(self._on_text_action_changed)
            actions_row.addWidget(btn)

        actions_row.addStretch(1)
        layout.addLayout(actions_row)

        self.text_encrypt_options_box = QGroupBox("Encryption options")
        enc_layout = QVBoxLayout(self.text_encrypt_options_box)

        recipient_row = QHBoxLayout()
        self.text_choose_recipients_btn = QPushButton("Choose recipients...")
        self.text_choose_recipients_btn.clicked.connect(self._choose_text_recipients)
        self.text_recipients_label = QLabel("No recipients selected.")
        self.text_recipients_label.setWordWrap(True)
        recipient_row.addWidget(self.text_choose_recipients_btn)
        recipient_row.addWidget(self.text_recipients_label, 1)
        enc_layout.addLayout(recipient_row)

        enc_sign_row = QHBoxLayout()
        self.sign_and_encrypt_check = QCheckBox("Sign before encrypt")
        self.sign_and_encrypt_check.toggled.connect(self._apply_text_action_ui)
        self.encrypt_signer_label = QLabel("Signing key:")
        self.encrypt_signer_combo = QComboBox()
        self.encrypt_signer_combo.setMinimumWidth(420)
        enc_sign_row.addWidget(self.sign_and_encrypt_check)
        enc_sign_row.addWidget(self.encrypt_signer_label)
        enc_sign_row.addWidget(self.encrypt_signer_combo)
        enc_sign_row.addStretch(1)
        enc_layout.addLayout(enc_sign_row)

        layout.addWidget(self.text_encrypt_options_box)

        self.text_sign_options_box = QGroupBox("Signing options")
        sign_layout = QHBoxLayout(self.text_sign_options_box)

        self.text_sign_mode_label = QLabel("Sign mode:")
        self.text_sign_mode_combo = QComboBox()
        self.text_sign_mode_combo.addItems(["Clear-signed message", "Detached signature"])
        self.text_sign_mode_combo.currentIndexChanged.connect(self._apply_text_action_ui)

        self.text_signer_label = QLabel("Signing key:")
        self.text_signer_combo = QComboBox()
        self.text_signer_combo.setMinimumWidth(420)

        sign_layout.addWidget(self.text_sign_mode_label)
        sign_layout.addWidget(self.text_sign_mode_combo)
        sign_layout.addWidget(self.text_signer_label)
        sign_layout.addWidget(self.text_signer_combo)
        sign_layout.addStretch(1)

        layout.addWidget(self.text_sign_options_box)

        self.text_verify_options_box = QGroupBox("Verification options")
        verify_layout = QVBoxLayout(self.text_verify_options_box)

        verify_mode_row = QHBoxLayout()
        self.verify_mode_label = QLabel("Verify mode:")
        self.verify_mode_combo = QComboBox()
        self.verify_mode_combo.addItems(["Clear-signed message", "Detached signature"])
        self.verify_mode_combo.currentIndexChanged.connect(self._apply_text_action_ui)
        verify_mode_row.addWidget(self.verify_mode_label)
        verify_mode_row.addWidget(self.verify_mode_combo)
        verify_mode_row.addStretch(1)
        verify_layout.addLayout(verify_mode_row)

        self.text_signature_label = QLabel("Detached signature:")
        verify_layout.addWidget(self.text_signature_label)

        self.text_signature_input = self._make_plain(
            "Paste detached signature here..."
        )
        verify_layout.addWidget(self.text_signature_input)

        layout.addWidget(self.text_verify_options_box)

        editor_box = QGroupBox("Text")
        editor_layout = QVBoxLayout(editor_box)

        editor_info = QLabel(
            "Use the same field for input and output. Paste data, run the action, and the result replaces the current content."
        )
        editor_info.setWordWrap(True)
        editor_layout.addWidget(editor_info)

        self.text_editor = self._make_plain(
            "Paste plaintext, encrypted text, signed message, or detached-signature source text here..."
        )
        editor_layout.addWidget(self.text_editor)

        editor_buttons = QHBoxLayout()
        self.text_execute_btn = QPushButton("Run action")
        self.text_execute_btn.clicked.connect(self.run_text_action)
        self.text_copy_btn = QPushButton("Copy text")
        self.text_copy_btn.clicked.connect(lambda: self._copy_text(self.text_editor.toPlainText()))
        self.text_clear_btn = QPushButton("Clear")
        self.text_clear_btn.clicked.connect(self._clear_text_mode)
        self.text_wrap_check = QCheckBox("Wrap text")
        self.text_wrap_check.setChecked(True)
        self.text_wrap_check.toggled.connect(self._apply_text_wrap)
        editor_buttons.addWidget(self.text_execute_btn)
        editor_buttons.addWidget(self.text_copy_btn)
        editor_buttons.addWidget(self.text_clear_btn)
        editor_buttons.addWidget(self.text_wrap_check)
        editor_buttons.addStretch(1)
        editor_layout.addLayout(editor_buttons)

        self.text_status_label = QLabel("Status: waiting")
        self.text_status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        editor_layout.addWidget(self.text_status_label)

        layout.addWidget(editor_box)
        return box

    def _build_file_section(self) -> QGroupBox:
        box = QGroupBox("File mode")
        layout = QVBoxLayout(box)

        actions_row = QHBoxLayout()
        actions_row.addWidget(QLabel("Action:"))

        self.file_action_group = QButtonGroup(self)
        self.file_encrypt_btn = QRadioButton("Encrypt")
        self.file_decrypt_btn = QRadioButton("Decrypt")
        self.file_sign_btn = QRadioButton("Sign")
        self.file_verify_btn = QRadioButton("Verify")
        self.file_encrypt_btn.setChecked(True)

        for btn in [
            self.file_encrypt_btn,
            self.file_decrypt_btn,
            self.file_sign_btn,
            self.file_verify_btn,
        ]:
            self.file_action_group.addButton(btn)
            btn.toggled.connect(self._on_file_action_changed)
            actions_row.addWidget(btn)

        actions_row.addStretch(1)
        layout.addLayout(actions_row)

        self.file_encrypt_options_box = QGroupBox("Encryption options")
        fenc_layout = QVBoxLayout(self.file_encrypt_options_box)

        file_recipient_row = QHBoxLayout()
        self.file_choose_recipients_btn = QPushButton("Choose recipients...")
        self.file_choose_recipients_btn.clicked.connect(self._choose_file_recipients)
        self.file_recipients_label = QLabel("No recipients selected.")
        self.file_recipients_label.setWordWrap(True)
        file_recipient_row.addWidget(self.file_choose_recipients_btn)
        file_recipient_row.addWidget(self.file_recipients_label, 1)
        fenc_layout.addLayout(file_recipient_row)

        file_enc_opts_row = QHBoxLayout()
        self.file_ascii_armor_check = QCheckBox("ASCII armor")
        self.file_sign_and_encrypt_check = QCheckBox("Sign before encrypt")
        self.file_sign_and_encrypt_check.toggled.connect(self._apply_file_action_ui)
        self.file_encrypt_signer_label = QLabel("Signing key:")
        self.file_encrypt_signer_combo = QComboBox()
        self.file_encrypt_signer_combo.setMinimumWidth(420)
        file_enc_opts_row.addWidget(self.file_ascii_armor_check)
        file_enc_opts_row.addWidget(self.file_sign_and_encrypt_check)
        file_enc_opts_row.addWidget(self.file_encrypt_signer_label)
        file_enc_opts_row.addWidget(self.file_encrypt_signer_combo)
        file_enc_opts_row.addStretch(1)
        fenc_layout.addLayout(file_enc_opts_row)

        layout.addWidget(self.file_encrypt_options_box)

        self.file_sign_options_box = QGroupBox("Signing options")
        fsign_layout = QHBoxLayout(self.file_sign_options_box)

        self.file_detached_check = QCheckBox("Detached signature")
        self.file_detached_check.setChecked(True)
        self.file_signer_label = QLabel("Signing key:")
        self.file_signer_combo = QComboBox()
        self.file_signer_combo.setMinimumWidth(420)

        fsign_layout.addWidget(self.file_detached_check)
        fsign_layout.addWidget(self.file_signer_label)
        fsign_layout.addWidget(self.file_signer_combo)
        fsign_layout.addStretch(1)

        layout.addWidget(self.file_sign_options_box)

        paths_box = QGroupBox("Paths")
        paths_layout = QVBoxLayout(paths_box)

        input_row = QHBoxLayout()
        self.file_input_edit = QLineEdit()
        self.file_input_edit.setPlaceholderText("Select input file...")
        self.file_input_browse_btn = QPushButton("Browse")
        self.file_input_browse_btn.clicked.connect(self.pick_input_file)
        input_row.addWidget(QLabel("Input file:"))
        input_row.addWidget(self.file_input_edit)
        input_row.addWidget(self.file_input_browse_btn)
        paths_layout.addLayout(input_row)

        output_row = QHBoxLayout()
        self.file_output_edit = QLineEdit()
        self.file_output_edit.setPlaceholderText("Select output file...")
        self.file_output_browse_btn = QPushButton("Browse")
        self.file_output_browse_btn.clicked.connect(self.pick_output_file)
        output_row.addWidget(QLabel("Output file:"))
        output_row.addWidget(self.file_output_edit)
        output_row.addWidget(self.file_output_browse_btn)
        paths_layout.addLayout(output_row)

        self.file_signature_row = QHBoxLayout()
        self.file_signature_edit = QLineEdit()
        self.file_signature_edit.setPlaceholderText("Select detached signature file...")
        self.file_signature_browse_btn = QPushButton("Browse")
        self.file_signature_browse_btn.clicked.connect(self.pick_signature_file)
        self.file_signature_row.addWidget(QLabel("Signature file:"))
        self.file_signature_row.addWidget(self.file_signature_edit)
        self.file_signature_row.addWidget(self.file_signature_browse_btn)
        paths_layout.addLayout(self.file_signature_row)

        layout.addWidget(paths_box)

        file_buttons = QHBoxLayout()
        self.file_execute_btn = QPushButton("Run action")
        self.file_execute_btn.clicked.connect(self.run_file_action)
        self.file_clear_btn = QPushButton("Clear")
        self.file_clear_btn.clicked.connect(self._clear_file_mode)
        file_buttons.addWidget(self.file_execute_btn)
        file_buttons.addWidget(self.file_clear_btn)
        file_buttons.addStretch(1)
        layout.addLayout(file_buttons)

        self.file_status_label = QLabel("Status: waiting")
        self.file_status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.file_status_label)

        return box

    def _build_log_section(self) -> QGroupBox:
        box = QGroupBox("GPG Log")
        layout = QVBoxLayout(box)

        self.log_toggle_btn = QToolButton()
        self.log_toggle_btn.setText("Show log")
        self.log_toggle_btn.setCheckable(True)
        self.log_toggle_btn.setChecked(False)
        self.log_toggle_btn.toggled.connect(self._toggle_log_visibility)
        layout.addWidget(self.log_toggle_btn)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setVisible(False)
        layout.addWidget(self.log_output)

        btn_row = QHBoxLayout()
        clear_btn = QPushButton("Clear log")
        clear_btn.clicked.connect(self.log_output.clear)
        clear_btn.setVisible(False)
        self.log_clear_btn = clear_btn
        btn_row.addWidget(clear_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        return box

    def _make_plain(self, placeholder: str = "", readonly: bool = False) -> QPlainTextEdit:
        widget = QPlainTextEdit()
        widget.setPlaceholderText(placeholder)
        widget.setReadOnly(readonly)
        widget.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        return widget

    def _toggle_mode(self) -> None:
        self.current_mode = "file" if self.file_mode_btn.isChecked() else "text"
        self._apply_mode_visibility()

    def _apply_mode_visibility(self) -> None:
        if self.current_mode == "text":
            self.mode_stack.setCurrentWidget(self.text_mode_widget)
        else:
            self.mode_stack.setCurrentWidget(self.file_mode_widget)

    def _on_text_action_changed(self) -> None:
        if self.text_encrypt_btn.isChecked():
            self.current_text_action = "encrypt"
        elif self.text_decrypt_btn.isChecked():
            self.current_text_action = "decrypt"
        elif self.text_sign_btn.isChecked():
            self.current_text_action = "sign"
        elif self.text_verify_btn.isChecked():
            self.current_text_action = "verify"
        self._apply_text_action_ui()

    def _on_file_action_changed(self) -> None:
        if self.file_encrypt_btn.isChecked():
            self.current_file_action = "encrypt"
        elif self.file_decrypt_btn.isChecked():
            self.current_file_action = "decrypt"
        elif self.file_sign_btn.isChecked():
            self.current_file_action = "sign"
        elif self.file_verify_btn.isChecked():
            self.current_file_action = "verify"
        self._apply_file_action_ui()

    def _apply_text_action_ui(self) -> None:
        action = self.current_text_action

        self.text_encrypt_options_box.setVisible(action == "encrypt")
        self.text_sign_options_box.setVisible(action == "sign")
        self.text_verify_options_box.setVisible(action == "verify")

        encrypt_sign_visible = action == "encrypt" and self.sign_and_encrypt_check.isChecked()
        self.encrypt_signer_label.setVisible(encrypt_sign_visible)
        self.encrypt_signer_combo.setVisible(encrypt_sign_visible)

        verify_detached = (
            action == "verify" and self.verify_mode_combo.currentIndex() == 1
        )
        self.text_signature_label.setVisible(verify_detached)
        self.text_signature_input.setVisible(verify_detached)

        if action == "encrypt":
            self.text_execute_btn.setText("Encrypt")
            self.text_editor.setPlaceholderText("Paste plaintext here...")
        elif action == "decrypt":
            self.text_execute_btn.setText("Decrypt")
            self.text_editor.setPlaceholderText("Paste encrypted armored text here...")
        elif action == "sign":
            self.text_execute_btn.setText("Sign")
            if self.text_sign_mode_combo.currentIndex() == 0:
                self.text_editor.setPlaceholderText("Paste plaintext to clear-sign here...")
            else:
                self.text_editor.setPlaceholderText("Paste plaintext to create detached signature for...")
        else:
            self.text_execute_btn.setText("Verify")
            if self.verify_mode_combo.currentIndex() == 0:
                self.text_editor.setPlaceholderText("Paste clear-signed message here...")
            else:
                self.text_editor.setPlaceholderText("Paste plaintext/message here...")

    def _apply_file_action_ui(self) -> None:
        action = self.current_file_action

        self.file_encrypt_options_box.setVisible(action == "encrypt")
        self.file_sign_options_box.setVisible(action == "sign")

        enc_sign_visible = action == "encrypt" and self.file_sign_and_encrypt_check.isChecked()
        self.file_encrypt_signer_label.setVisible(enc_sign_visible)
        self.file_encrypt_signer_combo.setVisible(enc_sign_visible)

        verify_mode = action == "verify"
        self.file_signature_edit.setVisible(verify_mode)
        self.file_signature_browse_btn.setVisible(verify_mode)

        # label is first widget in signature row
        sig_label = self.file_signature_row.itemAt(0).widget()
        if sig_label is not None:
            sig_label.setVisible(verify_mode)

        if action == "encrypt":
            self.file_execute_btn.setText("Encrypt")
            self.file_output_edit.setPlaceholderText("Output encrypted file...")
        elif action == "decrypt":
            self.file_execute_btn.setText("Decrypt")
            self.file_output_edit.setPlaceholderText("Output decrypted file...")
        elif action == "sign":
            self.file_execute_btn.setText("Sign")
            self.file_output_edit.setPlaceholderText("Output signature file or signed file...")
        else:
            self.file_execute_btn.setText("Verify")
            self.file_output_edit.setPlaceholderText("Not used for verify")

    def _apply_text_wrap(self) -> None:
        mode = QPlainTextEdit.WidgetWidth if self.text_wrap_check.isChecked() else QPlainTextEdit.NoWrap
        self.text_editor.setLineWrapMode(mode)
        self.text_signature_input.setLineWrapMode(mode)
    
    def _toggle_log_visibility(self, checked: bool) -> None:
        self.log_output.setVisible(checked)
        self.log_clear_btn.setVisible(checked)
        self.log_toggle_btn.setText("Hide log" if checked else "Show log")

    def _show_error(self, title: str, message: str) -> None:
        QMessageBox.critical(self, title, message)

    def _show_info(self, title: str, message: str) -> None:
        QMessageBox.information(self, title, message)

    def _copy_text(self, text: str) -> None:
        QApplication.clipboard().setText(text)
        self.status.showMessage("Copied to clipboard.", 3000)

    def _append_log(self, title: str, result: GPGResult) -> None:
        blocks = [f"=== {title} ==="]
        if result.stdout.strip():
            blocks.append("[stdout]")
            blocks.append(result.stdout.strip())
        if result.stderr.strip():
            blocks.append("[stderr]")
            blocks.append(result.stderr.strip())
        statuses = result.status_lines()
        if statuses:
            blocks.append("[parsed statuses]")
            blocks.extend(statuses)
        blocks.append("")
        self.log_output.append("\n".join(blocks))

    def _friendly_error(self, result: GPGResult, default_message: str) -> str:
        tags = {item.tag for item in result.statuses}

        if "NO_PUBKEY" in tags:
            return "Required public key is missing."
        if "NO_SECKEY" in tags:
            return "Required secret key is missing."
        if "INV_RECP" in tags:
            return "Recipient key is unusable or not trusted enough."
        if "NODATA" in tags:
            return "No valid OpenPGP data was detected for this operation."
        if "BADSIG" in tags:
            return "Signature is invalid."
        if "ERRSIG" in tags:
            return "Signature verification failed."
        if "DECRYPTION_FAILED" in tags:
            return "Decryption failed."
        if "FAILURE" in tags:
            return "GPG operation failed."

        return default_message

    def _format_key_label(self, key: GPGKey) -> str:
        flags = []
        if key.revoked:
            flags.append("revoked")
        if key.expired:
            flags.append("expired")
        if key.disabled:
            flags.append("disabled")
        suffix = f" [{' '.join(flags)}]" if flags else ""
        return f"{key.primary_uid} | {key.key_id}{suffix}"
    
    def _recipient_summary(self, ids: List[str]) -> str:
        if not ids:
            return "No recipients selected."

        labels: List[str] = []
        for key in self.public_keys:
            if key.key_id in ids:
                labels.append(f"{key.primary_uid} ({key.key_id})")

        return ", ".join(labels) if labels else "No recipients selected."

    def _update_text_recipient_label(self) -> None:
        self.text_recipients_label.setText(self._recipient_summary(self.text_recipient_ids))

    def _update_file_recipient_label(self) -> None:
        self.file_recipients_label.setText(self._recipient_summary(self.file_recipient_ids))

    def _choose_text_recipients(self) -> None:
        dialog = RecipientPickerDialog(self.public_keys, self.text_recipient_ids, self)
        if dialog.exec():
            self.text_recipient_ids = dialog.selected_key_ids()
            self._update_text_recipient_label()

    def _choose_file_recipients(self) -> None:
        dialog = RecipientPickerDialog(self.public_keys, self.file_recipient_ids, self)
        if dialog.exec():
            self.file_recipient_ids = dialog.selected_key_ids()
            self._update_file_recipient_label()

    def _match_key(self, key: GPGKey, text: str) -> bool:
        if not text:
            return True
        haystack = " ".join(
            [key.key_id, key.fingerprint, key.trust, key.capabilities, *key.user_ids]
        ).lower()
        return text.lower() in haystack

    def _current_encrypt_signer(self) -> Optional[str]:
        value = self.encrypt_signer_combo.currentData()
        return str(value) if value else None

    def _current_text_signer(self) -> Optional[str]:
        value = self.text_signer_combo.currentData()
        return str(value) if value else None

    def _current_file_encrypt_signer(self) -> Optional[str]:
        value = self.file_encrypt_signer_combo.currentData()
        return str(value) if value else None

    def _current_file_signer(self) -> Optional[str]:
        value = self.file_signer_combo.currentData()
        return str(value) if value else None

    def _populate_secret_key_combos(self) -> None:
        current_encrypt = self.encrypt_signer_combo.currentData()
        current_text_sign = self.text_signer_combo.currentData()
        current_file_encrypt = self.file_encrypt_signer_combo.currentData()
        current_file_sign = self.file_signer_combo.currentData()

        self.encrypt_signer_combo.clear()
        self.text_signer_combo.clear()
        self.file_encrypt_signer_combo.clear()
        self.file_signer_combo.clear()

        for key in self.secret_keys:
            label = self._format_key_label(key)
            self.encrypt_signer_combo.addItem(label, key.key_id)
            self.text_signer_combo.addItem(label, key.key_id)
            self.file_encrypt_signer_combo.addItem(label, key.key_id)
            self.file_signer_combo.addItem(label, key.key_id)

        for combo, current_value in [
            (self.encrypt_signer_combo, current_encrypt),
            (self.text_signer_combo, current_text_sign),
            (self.file_encrypt_signer_combo, current_file_encrypt),
            (self.file_signer_combo, current_file_sign),
        ]:
            if current_value is not None:
                idx = combo.findData(current_value)
                if idx >= 0:
                    combo.setCurrentIndex(idx)

    def refresh_keys(self) -> None:
        self.public_keys = self.gpg.list_public_keys()
        self.secret_keys = self.gpg.list_secret_keys()

        self._populate_secret_key_combos()
        self._update_text_recipient_label()
        self._update_file_recipient_label()

        self.status.showMessage(
            f"Loaded {len(self.public_keys)} public keys and {len(self.secret_keys)} secret keys.",
            5000,
        )

    def open_manage_keys(self) -> None:
        dialog = ManageKeysDialog(self.gpg, self)
        dialog.exec()
        self.refresh_keys()

    def open_about(self) -> None:
        dialog = AboutDialog(self)
        dialog.exec()

    def _clear_text_mode(self) -> None:
        self.text_editor.clear()
        self.text_signature_input.clear()
        self.text_status_label.setText("Status: waiting")

    def _clear_file_mode(self) -> None:
        self.file_input_edit.clear()
        self.file_output_edit.clear()
        self.file_signature_edit.clear()
        self.file_status_label.setText("Status: waiting")

    def clear_all_fields(self) -> None:
        self._clear_text_mode()
        self._clear_file_mode()

    def pick_input_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select input file", str(Path.home())
        )
        if path:
            self.file_input_edit.setText(path)

    def pick_output_file(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Select output file", str(Path.home())
        )
        if path:
            self.file_output_edit.setText(path)

    def pick_signature_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select signature file", str(Path.home())
        )
        if path:
            self.file_signature_edit.setText(path)

    def run_text_action(self) -> None:
        action = self.current_text_action

        if action == "encrypt":
            recipients = self.text_recipient_ids
            if not recipients:
                self._show_error("Missing recipient", "Select at least one recipient public key.")
                return

            text = self.text_editor.toPlainText().strip()
            if not text:
                self._show_error("Missing text", "Paste plaintext first.")
                return

            signer = None
            if self.sign_and_encrypt_check.isChecked():
                signer = self._current_encrypt_signer()
                if not signer:
                    self._show_error("Missing signing key", "Select a secret key for sign+encrypt.")
                    return

            result = self.gpg.encrypt_text(text, recipients, sign_with=signer)
            self._append_log("Encrypt text", result)

            if result.ok:
                self.text_editor.setPlainText(result.stdout.strip())
                self.text_status_label.setText(f"Status: {self.gpg.describe_encrypt_result(result)}")
            else:
                msg = self._friendly_error(result, "Encryption failed.")
                self.text_status_label.setText(f"Status: {msg}")
                self._show_error("Encryption failed", msg)

        elif action == "decrypt":
            text = self.text_editor.toPlainText().strip()
            if not text:
                self._show_error("Missing text", "Paste encrypted armored text first.")
                return

            result = self.gpg.decrypt_text(text)
            self._append_log("Decrypt text", result)

            if result.ok:
                self.text_editor.setPlainText(result.stdout.strip())
                self.text_status_label.setText(
                    f"Status: {self.gpg.describe_decrypt_result(result)}"
                )
            else:
                msg = self._friendly_error(
                    result, self.gpg.describe_decrypt_result(result)
                )
                self.text_status_label.setText(f"Status: {msg}")
                self._show_error("Decrypt failed", msg)

        elif action == "sign":
            text = self.text_editor.toPlainText()
            if not text.strip():
                self._show_error("Missing text", "Paste plaintext first.")
                return

            signer = self._current_text_signer()
            if not signer:
                self._show_error("Missing signing key", "Select a secret key for signing.")
                return

            detached = self.text_sign_mode_combo.currentIndex() == 1
            result = (
                self.gpg.detach_sign_text(text, signer)
                if detached
                else self.gpg.clearsign_text(text, signer)
            )
            self._append_log("Sign text", result)

            if result.ok:
                self.text_editor.setPlainText(result.stdout.strip())
                self.text_status_label.setText(f"Status: {self.gpg.describe_sign_result(result)}")
            else:
                msg = self._friendly_error(result, "Signing failed.")
                self.text_status_label.setText(f"Status: {msg}")
                self._show_error("Signing failed", msg)

        elif action == "verify":
            if self.verify_mode_combo.currentIndex() == 0:
                signed_text = self.text_editor.toPlainText().strip()
                if not signed_text:
                    self._show_error("Missing text", "Paste clear-signed message first.")
                    return
                result = self.gpg.verify_clearsigned_text(signed_text)
            else:
                text = self.text_editor.toPlainText().strip()
                signature = self.text_signature_input.toPlainText().strip()
                if not text:
                    self._show_error("Missing text", "Paste message/plaintext first.")
                    return
                if not signature:
                    self._show_error("Missing detached signature", "Paste detached signature first.")
                    return
                result = self.gpg.verify_detached_signature(text, signature)

            self._append_log("Verify text", result)

            summary = self.gpg.describe_verify_result(result)
            if result.ok:
                self.text_status_label.setText(f"Status: {summary}")
                self._show_info("Verification result", summary)
            else:
                msg = self._friendly_error(result, summary)
                self.text_status_label.setText(f"Status: {msg}")
                self._show_error("Verification failed", msg)

    def run_file_action(self) -> None:
        action = self.current_file_action

        input_file = self.file_input_edit.text().strip()

        if not input_file:
            self._show_error("Missing input file", "Select input file first.")
            return

        if action == "encrypt":
            output_file = self.file_output_edit.text().strip()
            if not output_file:
                self._show_error("Missing output file", "Select output file first.")
                return

            recipients = self.file_recipient_ids
            if not recipients:
                self._show_error("Missing recipient", "Select at least one recipient public key.")
                return

            signer = None
            if self.file_sign_and_encrypt_check.isChecked():
                signer = self._current_file_encrypt_signer()
                if not signer:
                    self._show_error("Missing signing key", "Select a secret key for sign+encrypt.")
                    return

            result = self.gpg.encrypt_file(
                input_file,
                output_file,
                recipients,
                armor=self.file_ascii_armor_check.isChecked(),
                sign_with=signer,
            )
            self._append_log("Encrypt file", result)

            if result.ok:
                self.file_status_label.setText(f"Status: {self.gpg.describe_encrypt_result(result)}")
            else:
                msg = self._friendly_error(result, "File encryption failed.")
                self.file_status_label.setText(f"Status: {msg}")
                self._show_error("File encryption failed", msg)

        elif action == "decrypt":
            output_file = self.file_output_edit.text().strip()
            if not output_file:
                self._show_error("Missing output file", "Select output file first.")
                return

            result = self.gpg.decrypt_file(input_file, output_file)
            self._append_log("Decrypt file", result)

            if result.ok:
                self.file_status_label.setText(
                    f"Status: {self.gpg.describe_decrypt_result(result)}"
                )
            else:
                msg = self._friendly_error(
                    result, self.gpg.describe_decrypt_result(result)
                )
                self.file_status_label.setText(f"Status: {msg}")
                self._show_error("File decrypt failed", msg)

        elif action == "sign":
            output_file = self.file_output_edit.text().strip()
            if not output_file:
                self._show_error("Missing output file", "Select output file first.")
                return

            signer = self._current_file_signer()
            if not signer:
                self._show_error("Missing signing key", "Select a secret key for signing.")
                return

            result = self.gpg.sign_file(
                input_file,
                output_file,
                signer,
                detached=self.file_detached_check.isChecked(),
                armor=self.file_ascii_armor_check.isChecked(),
            )
            self._append_log("Sign file", result)

            if result.ok:
                self.file_status_label.setText(f"Status: {self.gpg.describe_sign_result(result)}")
            else:
                msg = self._friendly_error(result, "File signing failed.")
                self.file_status_label.setText(f"Status: {msg}")
                self._show_error("File signing failed", msg)

        elif action == "verify":
            signature_file = self.file_signature_edit.text().strip()
            if not signature_file:
                self._show_error("Missing signature file", "Select detached signature file first.")
                return

            result = self.gpg.verify_file_signature(input_file, signature_file)
            self._append_log("Verify file", result)

            summary = self.gpg.describe_verify_result(result)
            if result.ok:
                self.file_status_label.setText(f"Status: {summary}")
                self._show_info("Verification result", summary)
            else:
                msg = self._friendly_error(result, summary)
                self.file_status_label.setText(f"Status: {msg}")
                self._show_error("File verification failed", msg)