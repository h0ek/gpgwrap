import subprocess
from threading import Event, Timer
import sys

import pytest

from gpgwrap.gpg_service import GPGService
from gpgwrap.process import execute_process
from conftest import FIXTURES


def result_service(statuses, code=0, output=b""):
    def runner(command, data):
        stderr = "".join(f"[GNUPG:] {status}\n" for status in statuses).encode()
        return subprocess.CompletedProcess(command, code, output, stderr)

    return GPGService(runner=runner)


@pytest.mark.parametrize(
    "bad,state",
    [
        ("BADSIG B Bob", "invalid"),
        ("ERRSIG B 1 8 00 0 9", "error"),
        ("EXPSIG B Bob", "expired"),
        ("EXPKEYSIG B Bob", "expired"),
        ("REVKEYSIG B Bob", "revoked"),
    ],
)
def test_each_signature_is_assessed(bad, state):
    service = result_service(["NEWSIG", "GOODSIG A Alice", "VALIDSIG A", "NEWSIG", bad])
    result = service.verify_clearsigned_text("signed")
    assert not result.ok
    assert [item.state for item in result.signatures] == ["valid", state]
    summary = service.describe_verify_result(result)
    assert "A:" in summary and "B:" in summary


def test_partial_signature_records_cannot_form_one_good_signature():
    service = result_service(["NEWSIG", "GOODSIG A Alice", "NEWSIG", "VALIDSIG B"])
    result = service.verify_clearsigned_text("signed")
    assert not result.ok
    assert [item.state for item in result.signatures] == ["unverified", "unverified"]


def test_no_signature_is_not_a_success():
    assert not result_service([]).verify_clearsigned_text("anything").ok


def test_missing_key_is_reported_before_generic_verification_error():
    service = result_service(["NEWSIG", "ERRSIG B 1 8 00 0 9", "NO_PUBKEY B"], 2)
    result = service.verify_clearsigned_text("signed")
    assert result.signatures[0].state == "missing_key"
    assert "Missing public key" in service.describe_verify_result(result)


@pytest.mark.parametrize(
    "fatal",
    [
        "BADMDC",
        "ERRMDC",
        "DECRYPTION_FAILED",
        "ERROR decrypt 1",
        "FAILURE decrypt 1",
        "NODATA 1",
    ],
)
def test_decryption_okay_cannot_override_integrity_or_io_errors(fatal):
    service = result_service(["DECRYPTION_OKAY", fatal], 2, b"untrusted plaintext")
    result = service.decrypt_text("encrypted")
    assert not result.ok and not result.decryption_ok
    assert not result.stdout


def test_valid_signature_does_not_override_process_failure():
    service = result_service(
        ["NEWSIG", "GOODSIG A Alice", "VALIDSIG A", "DECRYPTION_OKAY"], 2
    )
    result = service.decrypt_text("encrypted")
    assert not result.ok and not result.decryption_ok
    assert "additional error" in service.describe_verify_result(result)


def test_binary_text_output_is_rejected_without_crashing():
    service = result_service(["DECRYPTION_OKAY"], 0, b"\xff\x00")
    result = service.decrypt_text("encrypted")
    assert not result.ok and not result.decryption_ok
    assert result.stdout == ""
    assert "File mode" in result.error


def test_bytes_do_not_normalize_newlines():
    original = " \r\ntext\r\n "
    service = result_service(["DECRYPTION_OKAY"], 0, original.encode())
    assert service.decrypt_text("encrypted").stdout == original


@pytest.mark.parametrize(
    "fingerprint,level",
    [
        ("ABC", "full"),
        ("A" * 40 + "\nB:6:", "full"),
        ("G" * 40, "full"),
        ("A" * 40, "invalid"),
    ],
)
def test_ownertrust_input_validation(fingerprint, level):
    service = GPGService(runner=lambda *args: pytest.fail("GPG must not run"))
    assert not service.set_ownertrust(fingerprint, level).ok


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", "name\n%no-protection"),
        ("comment", "comment\r%commit"),
        ("passphrase", "password\n%no-protection"),
        ("email", "a\0b"),
        ("expiry", "bad"),
        ("passphrase", " password "),
    ],
)
def test_key_generation_rejects_unsafe_batch_values(field, value):
    fields = dict(
        name="Test",
        email="test@example.invalid",
        comment="",
        preset="Modern ECC",
        expiry="1y",
        passphrase="test-passphrase",
    )
    fields[field] = value
    service = GPGService(runner=lambda *args: pytest.fail("GPG must not run"))
    assert not service.generate_key(**fields).ok


def test_gpg_can_verify_fixture_and_detect_trimmed_message(public_gpg):
    service, _ = public_gpg
    message = (FIXTURES / "message.txt").read_text()
    signature = (FIXTURES / "signature.asc").read_text()
    assert service.verify_detached_signature(message, signature).ok
    assert not service.verify_detached_signature(message.strip(), signature).ok


def test_gpg_mixed_signatures(public_gpg):
    service, _ = public_gpg
    result = service.verify_file_signature(
        str(FIXTURES / "message.txt"), str(FIXTURES / "mixed.sig")
    )
    assert not result.ok
    assert [item.state for item in result.signatures] == ["valid", "invalid"]


@pytest.mark.parametrize(
    "level,value",
    [
        ("undefined", "2"),
        ("never", "3"),
        ("marginal", "4"),
        ("full", "5"),
        ("ultimate", "6"),
    ],
)
def test_gpg_ownertrust_roundtrip(public_gpg, level, value):
    service, fingerprint = public_gpg
    assert service.set_ownertrust(fingerprint, level).ok
    exported = service._run_text(["--export-ownertrust"])
    assert exported.ok
    assert f"{fingerprint}:{value}:" in exported.stdout


def test_gpg_encrypts_without_modifying_source(public_gpg, tmp_path):
    service, fingerprint = public_gpg
    assert service.set_ownertrust(fingerprint, "ultimate").ok
    source = tmp_path / "original"
    output = tmp_path / "encrypted"
    source.write_bytes(b"original data")
    result = service.encrypt_file(str(source), str(output), [fingerprint])
    assert result.ok, result.error or result.stderr
    assert source.read_bytes() == b"original data"
    assert output.stat().st_size > 0
    assert output.stat().st_mode & 0o777 == 0o600


def test_gpg_decrypts_missing_signer_with_warning(symmetric_gpg, tmp_path):
    encrypted = (FIXTURES / "signed-symmetric.asc").read_text()
    result = symmetric_gpg.decrypt_text(encrypted)
    assert not result.ok and result.decryption_ok, result.stderr
    assert result.stdout == (FIXTURES / "message.txt").read_text()
    assert result.signatures[0].state == "missing_key"
    output = tmp_path / "decrypted"
    result = symmetric_gpg.decrypt_file(
        str(FIXTURES / "signed-symmetric.asc"), str(output)
    )
    assert not result.ok and result.decryption_ok
    assert output.read_bytes() == (FIXTURES / "message.txt").read_bytes()


def test_gpg_decrypts_all_signatures(symmetric_gpg):
    symmetric_gpg.import_key_file(str(FIXTURES / "public.asc"))
    result = symmetric_gpg.decrypt_text((FIXTURES / "mixed-symmetric.asc").read_text())
    assert not result.ok
    assert any(item.state == "invalid" for item in result.signatures)
    if not result.decryption_ok:
        assert not result.stdout
    assert "invalid" in symmetric_gpg.describe_decrypt_result(result)


def test_gpg_binary_plaintext_requires_file_mode(symmetric_gpg, tmp_path):
    encrypted = FIXTURES / "binary-symmetric.asc"
    result = symmetric_gpg.decrypt_text(encrypted.read_text())
    assert not result.ok and not result.decryption_ok
    assert "UTF-8" in result.error
    output = tmp_path / "binary"
    result = symmetric_gpg.decrypt_file(str(encrypted), str(output))
    assert result.ok and result.decryption_ok, result.stderr
    assert output.read_bytes() == b"\xff\xfe\x00binary\n"


def test_gpg_corrupt_ciphertext_does_not_replace_output(symmetric_gpg, tmp_path):
    import base64

    armor = (FIXTURES / "signed-symmetric.asc").read_text()
    body = armor.split("\n\n", 1)[1].split("\n=")[0]
    data = bytearray(base64.b64decode(body))
    data[-1] ^= 1
    source, output = tmp_path / "corrupt.gpg", tmp_path / "output"
    source.write_bytes(data)
    output.write_bytes(b"keep me")
    result = symmetric_gpg.decrypt_file(str(source), str(output), overwrite=True)
    assert not result.ok and not result.decryption_ok
    assert output.read_bytes() == b"keep me"
    assert not list(tmp_path.glob(".gpgwrap-*"))


def test_process_cancellation_terminates_and_reaps_child():
    cancelled = Event()
    timer = Timer(0.2, cancelled.set)
    timer.start()
    try:
        result = execute_process(
            [sys.executable, "-c", "import time; time.sleep(30)"], cancelled=cancelled
        )
    finally:
        timer.cancel()
    assert result.returncode == 130
    assert result.stdout == b""


@pytest.mark.parametrize("preset", ["Modern ECC", "RSA 3072", "RSA 4096"])
def test_gpg_private_key_operations(private_gpg, tmp_path, preset):
    service = private_gpg
    result = service.generate_key(
        "GPGWrap CI", "ci@example.invalid", "", preset, "1d", "test-passphrase"
    )
    assert result.ok, result.error or result.stderr
    keys = service.list_secret_keys()
    assert len(keys) == 1
    fingerprint = keys[0].fingerprint
    message = "  secret\n\n"
    encrypted = service.encrypt_text(message, [fingerprint], fingerprint)
    assert encrypted.ok, encrypted.stderr
    decrypted = service.decrypt_text(encrypted.stdout)
    assert decrypted.ok and decrypted.decryption_ok, decrypted.stderr
    assert decrypted.stdout == message
    assert [item.state for item in decrypted.signatures] == ["valid"]
    signature = service.detach_sign_text(message, fingerprint)
    assert signature.ok
    assert service.verify_detached_signature(message, signature.stdout).ok
    signed = service.clearsign_text(message, fingerprint)
    assert signed.ok and service.verify_clearsigned_text(signed.stdout).ok
    source, ciphertext, output, signature_file = [
        tmp_path / name for name in ("data", "ciphertext", "output", "data.sig")
    ]
    source.write_bytes(b"\xff\x00data\n")
    assert service.encrypt_file(
        str(source), str(ciphertext), [fingerprint], sign_with=fingerprint
    ).ok
    assert service.decrypt_file(str(ciphertext), str(output)).ok
    assert output.read_bytes() == source.read_bytes()
    assert service.sign_file(str(source), str(signature_file), fingerprint).ok
    assert service.verify_file_signature(str(source), str(signature_file)).ok
