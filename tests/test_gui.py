import subprocess
import sys
import time

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from gpgwrap.dialogs import RecipientPickerDialog
from gpgwrap.gpg_service import GPGService
from gpgwrap.gui import MainWindow
from gpgwrap.models import GPGKey, GPGResult
from gpgwrap.operations import OperationDialog, run_process_dialog
from gpgwrap.output_dialog import confirm_output
from gpgwrap.window_style import apply_window_style, uses_tiling_desktop
from conftest import FIXTURES


@pytest.fixture
def window(app, monkeypatch):
    monkeypatch.setattr(MainWindow, "refresh_keys", lambda self: None)
    monkeypatch.setattr(GPGService, "check_gpg_available", lambda self: True)
    instance = MainWindow()
    yield instance
    instance.close()
    instance.deleteLater()
    app.processEvents()


def key(name):
    return GPGKey("pub", name, name, [name], "u", "e", False, False, False)


def test_recipient_filter_keeps_hidden_selections_and_deselections(app):
    picker = RecipientPickerDialog([key("Alice"), key("Bob")], ["Alice"])
    picker.filter_edit.setText("Bob")
    picker.key_list.item(0).setSelected(True)
    assert picker.selected_key_ids() == ["Alice", "Bob"]
    picker.filter_edit.clear()
    assert len(picker.key_list.selectedItems()) == 2
    picker.key_list.clearSelection()
    picker.filter_edit.setText("no match")
    picker.filter_edit.clear()
    assert picker.selected_key_ids() == []
    picker.deleteLater()


@pytest.mark.parametrize("action", ["encrypt", "decrypt", "sign"])
def test_text_actions_preserve_boundary_whitespace(window, action):
    original = "  test\n\n"
    captured = []

    def runner(command, data):
        captured.append(data)
        return subprocess.CompletedProcess(
            command,
            0,
            original.encode(),
            b"[GNUPG:] DECRYPTION_OKAY\n" if action == "decrypt" else b"",
        )

    window.gpg = GPGService(runner=runner)
    window.text_recipient_ids = ["recipient"]
    window.text_signer_combo.addItem("Signer", "signer")
    getattr(window, f"text_{action}_btn").setChecked(True)
    window.text_editor.setPlainText(original)
    window.run_text_action()
    assert captured == [original.encode()]
    assert window.text_editor.toPlainText() == original
    assert original.strip() not in window.log_output.toPlainText()


def test_gui_detached_verification_uses_exact_text(window, public_gpg, monkeypatch):
    window.gpg = public_gpg[0]
    window.text_verify_btn.setChecked(True)
    window.verify_mode_combo.setCurrentIndex(1)
    original = (FIXTURES / "message.txt").read_text()
    window.text_editor.setPlainText(original)
    window.text_signature_input.setPlainText((FIXTURES / "signature.asc").read_text())
    messages = []
    monkeypatch.setattr(window, "_show_info", lambda title, text: messages.append(text))
    monkeypatch.setattr(window, "_show_error", lambda *args: pytest.fail(str(args)))
    window.run_text_action()
    assert "Signature is valid" in messages[0]
    assert window.text_editor.toPlainText() == original


def test_log_excludes_plaintext_and_clear_removes_log(window):
    window._append_log(
        "Decrypt text",
        GPGResult(True, "PRIVATE CONTENT", "<b>literal diagnostics</b>", 0),
    )
    log = window.log_output.toPlainText()
    assert "PRIVATE CONTENT" not in log
    assert "<b>literal diagnostics</b>" in log
    window.text_editor.setPlainText("PRIVATE CONTENT")
    window.clear_all_fields()
    assert not window.log_output.toPlainText()
    assert not window.text_editor.toPlainText()
    assert not window.text_editor.document().isUndoAvailable()


def test_signed_decryption_is_visible_with_explicit_warning(
    window, symmetric_gpg, monkeypatch
):
    window.gpg = symmetric_gpg
    window.text_decrypt_btn.setChecked(True)
    window.text_editor.setPlainText((FIXTURES / "signed-symmetric.asc").read_text())
    warnings = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda parent, title, text: warnings.append(text)
    )
    window.run_text_action()
    assert window.text_editor.toPlainText() == (FIXTURES / "message.txt").read_text()
    assert "Missing public key" in warnings[0]


def test_manual_output_requires_confirmation_every_time(app, tmp_path, monkeypatch):
    path = tmp_path / "existing"
    path.write_bytes(b"valuable")
    questions = []

    def ask(*args):
        questions.append(args)
        return QMessageBox.No

    monkeypatch.setattr(QMessageBox, "question", ask)
    assert confirm_output(None, str(path)) is None
    assert confirm_output(None, str(path)) is None
    assert len(questions) == 2
    assert path.read_bytes() == b"valuable"


def test_cancelled_replacement_never_starts_gpg(window, tmp_path, monkeypatch):
    source, target = tmp_path / "source", tmp_path / "existing"
    source.write_bytes(b"source")
    target.write_bytes(b"keep")
    window.file_input_edit.setText(str(source))
    window.file_output_edit.setText(str(target))
    window.file_recipient_ids = ["recipient"]
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.No)
    window.gpg = GPGService(runner=lambda *args: pytest.fail("GPG must not run"))
    window.run_file_action()
    assert target.read_bytes() == b"keep"


def test_background_process_keeps_qt_responsive(app):
    ticks = []
    timer = QTimer()
    timer.setInterval(10)
    timer.timeout.connect(lambda: ticks.append(time.monotonic()))
    timer.start()
    try:
        result = run_process_dialog(
            None,
            [sys.executable, "-c", "import time; time.sleep(0.25); print('done')"],
            None,
        )
    finally:
        timer.stop()
    assert result.returncode == 0 and result.stdout == b"done\n"
    assert len(ticks) >= 5


@pytest.mark.parametrize("action", ["cancel", "close", "escape"])
def test_progress_cancellation_waits_for_process_exit(app, action):
    def cancel():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, OperationDialog)
        if action == "cancel":
            dialog.cancel_button.click()
        elif action == "close":
            dialog.close()
        else:
            from PySide6.QtTest import QTest

            QTest.keyClick(dialog, Qt.Key_Escape)

    QTimer.singleShot(100, cancel)
    start = time.monotonic()
    result = run_process_dialog(
        None, [sys.executable, "-c", "import time; time.sleep(30)"], None
    )
    assert result.returncode == 130
    assert time.monotonic() - start < 5


@pytest.mark.parametrize(
    "environment,expected",
    [
        ({"XDG_CURRENT_DESKTOP": "GNOME"}, False),
        ({"XDG_CURRENT_DESKTOP": "KDE"}, False),
        ({"XDG_CURRENT_DESKTOP": "sway"}, True),
        ({"XDG_CURRENT_DESKTOP": "Hyprland"}, True),
        ({"XDG_CURRENT_DESKTOP": "Hyprland:wlroots"}, True),
        ({"DESKTOP_SESSION": "sway"}, True),
        ({"SWAYSOCK": "/run/sway.sock"}, True),
        ({"XDG_CURRENT_DESKTOP": "GNOME", "SWAYSOCK": "stale"}, False),
        ({}, False),
    ],
)
def test_desktop_detection(environment, expected):
    assert uses_tiling_desktop(environment) is expected


@pytest.mark.parametrize(
    "desktop,preference,frameless",
    [
        ("GNOME", "auto", False),
        ("KDE", "auto", False),
        ("sway", "auto", True),
        ("Hyprland", "auto", True),
        ("sway", "on", False),
        ("GNOME", "off", True),
    ],
)
def test_actual_window_flags(window, monkeypatch, desktop, preference, frameless):
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", desktop)
    monkeypatch.setenv("GPGWRAP_DECORATIONS", preference)
    apply_window_style(window)
    assert bool(window.windowFlags() & Qt.FramelessWindowHint) is frameless
