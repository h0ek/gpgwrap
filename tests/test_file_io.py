import os
import subprocess
from pathlib import Path

import pytest

from gpgwrap.file_io import AtomicOutput
from gpgwrap.gpg_service import GPGService


@pytest.mark.parametrize("operation", ["encrypt", "decrypt", "sign"])
@pytest.mark.parametrize("link", ["same", "symlink", "hardlink"])
def test_source_cannot_be_used_as_output(tmp_path, operation, link):
    source = tmp_path / "original"
    source.write_bytes(b"irreplaceable data")
    target = source
    if link == "symlink":
        target = tmp_path / "symlink"
        target.symlink_to(source)
    elif link == "hardlink":
        target = tmp_path / "hardlink"
        os.link(source, target)
    service = GPGService(runner=lambda *args: pytest.fail("GPG must not run"))
    args = [str(source), str(target)]
    if operation == "encrypt":
        args.append(["recipient"])
    elif operation == "sign":
        args.append("signer")
    result = getattr(service, operation + "_file")(*args, overwrite=True)
    assert not result.ok
    assert "different files" in result.error
    assert source.read_bytes() == b"irreplaceable data"


@pytest.mark.parametrize("exists", [False, True])
@pytest.mark.parametrize(
    "returncode,status", [(2, "FAILURE encrypt 1"), (130, ""), (2, "BADMDC")]
)
def test_failed_or_cancelled_operation_preserves_output(
    tmp_path, exists, returncode, status
):
    source, target = tmp_path / "source", tmp_path / "target"
    source.write_bytes(b"source")
    if exists:
        target.write_bytes(b"old data")

    def runner(command, data):
        Path(command[command.index("--output") + 1]).write_bytes(b"partial output")
        return subprocess.CompletedProcess(
            command, returncode, b"", f"[GNUPG:] {status}\n".encode()
        )

    result = GPGService(runner=runner).decrypt_file(
        str(source), str(target), overwrite=True
    )
    assert not result.ok and not result.decryption_ok
    assert target.read_bytes() == b"old data" if exists else not target.exists()
    assert source.read_bytes() == b"source"
    assert not list(tmp_path.glob(".gpgwrap-*"))


def test_unconfirmed_output_is_never_overwritten(tmp_path):
    target = tmp_path / "existing"
    target.write_bytes(b"old data")
    service = GPGService(runner=lambda *args: pytest.fail("GPG must not run"))
    result = service.export_public_key_to_file("fingerprint", str(target))
    assert not result.ok
    assert target.read_bytes() == b"old data"


@pytest.mark.parametrize("existing", [False, True])
def test_output_changed_during_operation_is_preserved(tmp_path, existing):
    target = tmp_path / "target"
    if existing:
        target.write_bytes(b"old data")
    with AtomicOutput(str(target), overwrite=True) as output:
        output.temporary.write_bytes(b"new data")
        target.write_bytes(b"another application changed this")
        with pytest.raises(FileExistsError):
            output.commit()
    assert target.read_bytes() == b"another application changed this"


@pytest.mark.parametrize("existing", [False, True])
def test_atomic_output_commits_complete_private_file(tmp_path, existing):
    target = tmp_path / "target"
    if existing:
        target.write_bytes(b"old data")
    with AtomicOutput(str(target), overwrite=True) as output:
        output.temporary.write_bytes(b"complete output")
        if existing:
            assert target.read_bytes() == b"old data"
        else:
            assert not target.exists()
        output.commit()
    assert target.read_bytes() == b"complete output"
    assert target.stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob(".gpgwrap-*"))


def test_atomic_replace_does_not_modify_other_hardlinks(tmp_path):
    target, alias = tmp_path / "target", tmp_path / "alias"
    target.write_bytes(b"old data")
    os.link(target, alias)
    with AtomicOutput(str(target), overwrite=True) as output:
        output.temporary.write_bytes(b"new data")
        output.commit()
    assert target.read_bytes() == b"new data"
    assert alias.read_bytes() == b"old data"


def test_unrelated_and_broken_output_symlinks_are_rejected(tmp_path):
    target, link = tmp_path / "target", tmp_path / "link"
    link.symlink_to(target)
    for present in (False, True):
        if present:
            target.write_bytes(b"old data")
        with pytest.raises(ValueError, match="symbolic link"):
            AtomicOutput(str(link), overwrite=True)
    assert target.read_bytes() == b"old data"
