from __future__ import annotations

import shutil
import subprocess
from importlib.resources import files
from pathlib import Path


def main() -> int:
    app_name = "gpgwrap"
    executable = shutil.which(app_name)

    if executable is None:
        print("gpgwrap command not found in PATH")
        return 1

    icon_src = files("gpgwrap").joinpath("assets/gpgwrap.png")

    app_dir = Path.home() / ".local/share/applications"
    icon_dir = Path.home() / ".local/share/icons/hicolor/256x256/apps"

    app_dir.mkdir(parents=True, exist_ok=True)
    icon_dir.mkdir(parents=True, exist_ok=True)

    desktop_dst = app_dir / f"{app_name}.desktop"
    icon_dst = icon_dir / f"{app_name}.png"

    desktop_content = f"""[Desktop Entry]
Version=1.0
Type=Application
Name=GPGWrap
Comment=GPG text and file encryption/signing GUI
Exec={executable}
TryExec={executable}
Icon=gpgwrap
Terminal=false
Categories=Utility;Security;
Keywords=GPG;PGP;Encrypt;Decrypt;Sign;Verify;Crypto;
StartupNotify=true
"""

    desktop_dst.write_text(desktop_content, encoding="utf-8")
    icon_dst.write_bytes(Path(icon_src).read_bytes())

    desktop_dst.chmod(0o644)
    icon_dst.chmod(0o644)

    update_desktop_database = shutil.which("update-desktop-database")
    if update_desktop_database:
        subprocess.run(
            [update_desktop_database, str(app_dir)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )

    gtk_update_icon_cache = shutil.which("gtk-update-icon-cache")
    if gtk_update_icon_cache:
        subprocess.run(
            [
                gtk_update_icon_cache,
                "-f",
                "-t",
                str(Path.home() / ".local/share/icons/hicolor"),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )

    print("Installed desktop launcher and icon.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
