import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from gpgwrap.gpg_service import GPGService
from gpgwrap.process import execute_process

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def app():
    from PySide6.QtWidgets import QApplication

    instance = QApplication.instance() or QApplication([])
    yield instance


@pytest.fixture
def gpg_home():
    if not shutil.which("gpg"):
        pytest.fail("GnuPG is required for integration tests.")
    with tempfile.TemporaryDirectory(prefix="gw-test-") as directory:
        os.chmod(directory, 0o700)
        yield Path(directory)
        if shutil.which("gpgconf"):
            subprocess.run(
                ["gpgconf", "--homedir", directory, "--kill", "gpg-agent"],
                capture_output=True,
                timeout=10,
            )


def service_for(home, extra=()):
    def runner(command, data):
        return execute_process(
            [command[0], "--homedir", str(home), *extra, *command[1:]], data
        )

    return GPGService(runner=runner)


@pytest.fixture
def public_gpg(gpg_home):
    service = service_for(gpg_home, ("--no-autostart",))
    service.import_key_file(str(FIXTURES / "public.asc"))
    keys = service.list_public_keys()
    assert len(keys) == 1
    return service, keys[0].fingerprint


@pytest.fixture
def symmetric_gpg(gpg_home):
    return service_for(
        gpg_home,
        (
            "--no-autostart",
            "--pinentry-mode",
            "loopback",
            "--no-symkey-cache",
            "--passphrase",
            "gpgwrap-test-only",
        ),
    )


@pytest.fixture
def private_gpg(gpg_home):
    probe = subprocess.run(
        ["gpgconf", "--homedir", str(gpg_home), "--launch", "gpg-agent"],
        capture_output=True,
        timeout=10,
    )
    if probe.returncode:
        reason = "This environment cannot start gpg-agent."
        if os.environ.get("GPGWRAP_REQUIRE_AGENT") == "1":
            pytest.fail(reason + " " + probe.stderr.decode(errors="replace"))
        pytest.skip(reason)
    return service_for(
        gpg_home, ("--pinentry-mode", "loopback", "--passphrase", "test-passphrase")
    )
