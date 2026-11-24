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


def apply_window_style(window) -> bool:
    preference = os.environ.get("GPGWRAP_DECORATIONS", "auto").strip().lower()
    if preference not in {"auto", "on", "off"}:
        preference = "auto"
    custom_title_bar = preference == "auto" and uses_tiling_desktop()
    frameless = preference == "off" or custom_title_bar
    flags = window.windowFlags()
    flags &= ~(
        Qt.FramelessWindowHint
        | Qt.CustomizeWindowHint
        | Qt.WindowTitleHint
        | Qt.WindowSystemMenuHint
        | Qt.WindowMinMaxButtonsHint
        | Qt.WindowCloseButtonHint
        | Qt.WindowContextHelpButtonHint
        | Qt.WindowFullscreenButtonHint
    )
    if frameless:
        flags |= Qt.FramelessWindowHint
    else:
        flags |= (
            Qt.CustomizeWindowHint
            | Qt.WindowTitleHint
            | Qt.WindowSystemMenuHint
            | Qt.WindowMinMaxButtonsHint
            | Qt.WindowCloseButtonHint
        )
    window.setWindowFlags(flags)
    return custom_title_bar
