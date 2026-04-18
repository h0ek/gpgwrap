import sys
from importlib.resources import files

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .gui import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("gpgwrap")
    app.setApplicationDisplayName("GPGWrap")
    app.setDesktopFileName("gpgwrap")

    try:
        icon_path = files("gpgwrap").joinpath("assets/gpgwrap.png")
        app.setWindowIcon(QIcon(str(icon_path)))
    except Exception:
        pass

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
