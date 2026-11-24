from __future__ import annotations

import os
import re
from collections.abc import Mapping

from PySide6.QtCore import Qt


def uses_tiling_desktop(environment: Mapping[str, str] | None = None) -> bool:
    env = os.environ if environment is None else environment
    desktop = " ".join(
        env.get(key, "")
        for key in ("XDG_CURRENT_DESKTOP", "XDG_SESSION_DESKTOP", "DESKTOP_SESSION")
    )
    names = set(re.split(r"[^a-z0-9]+", desktop.lower()))
    if names & {"sway", "hyprland"}:
        return True
    if names & {"gnome", "kde", "plasma"}:
        return False
    return bool(env.get("SWAYSOCK") or env.get("HYPRLAND_INSTANCE_SIGNATURE"))


def apply_window_style(window) -> None:
    preference = os.environ.get("GPGWRAP_DECORATIONS", "auto").lower()
    frameless = preference == "off" or (preference == "auto" and uses_tiling_desktop())
    window.setWindowFlag(Qt.FramelessWindowHint, frameless)
