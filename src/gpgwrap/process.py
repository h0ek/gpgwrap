from __future__ import annotations

import subprocess
from threading import Event
from typing import Optional


def execute_process(
    command: list[str], data: Optional[bytes] = None, cancelled: Optional[Event] = None
) -> subprocess.CompletedProcess:
    if cancelled is not None and cancelled.is_set():
        return subprocess.CompletedProcess(command, 130, b"", b"Operation cancelled.")
    with subprocess.Popen(
        command,
        stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ) as process:
        while True:
            try:
                stdout, stderr = process.communicate(data, timeout=0.1)
                return subprocess.CompletedProcess(
                    command, process.returncode, stdout, stderr
                )
            except subprocess.TimeoutExpired:
                data = None
                if cancelled is None or not cancelled.is_set():
                    continue
                process.terminate()
                try:
                    process.communicate(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()
                return subprocess.CompletedProcess(
                    command, 130, b"", b"Operation cancelled."
                )
