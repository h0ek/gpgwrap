from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path


def output_path(value: str) -> Path:
    path = Path(value).expanduser().absolute()
    return path.parent.resolve(strict=True) / path.name


def validate_output(value: str, source: str | None = None) -> Path:
    path = output_path(value)
    if source:
        original = Path(source).expanduser().resolve(strict=True)
        if not original.is_file():
            raise ValueError("Input must be a regular file.")
        if path == original or (path.exists() and path.samefile(original)):
            raise ValueError(
                "Input and output must be different files, including links."
            )
    if path.is_symlink():
        raise ValueError("Output must not be a symbolic link.")
    if path.exists() and not path.is_file():
        raise ValueError("Output must be a regular file.")
    return path


def file_identity(path: Path) -> tuple[int, ...] | None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("Output must be a regular file, not a symbolic link.")
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


class AtomicOutput:
    def __init__(self, value: str, source: str | None = None, overwrite: bool = False):
        self.path = validate_output(value, source)
        self.source = source
        self.original = file_identity(self.path)
        if self.original is not None and not overwrite:
            raise FileExistsError("Output already exists. Confirm replacement first.")
        self.directory = tempfile.TemporaryDirectory(
            prefix=".gpgwrap-", dir=self.path.parent
        )
        self.temporary = Path(self.directory.name) / "output"

    def __enter__(self):
        return self

    def commit(self) -> None:
        validate_output(str(self.path), self.source)
        if file_identity(self.path) != self.original:
            raise FileExistsError(
                "Output changed during the operation. Nothing was replaced."
            )
        self.temporary.chmod(0o600)
        with self.temporary.open("rb") as stream:
            os.fsync(stream.fileno())
        if self.original is None:
            os.link(self.temporary, self.path)
        else:
            os.replace(self.temporary, self.path)

    def __exit__(self, exc_type, exc_value, traceback):
        self.directory.cleanup()
