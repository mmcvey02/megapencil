"""Add MegaPencil to the desktop's application menu (per user, no root).

Used when MegaPencil runs from an AppImage: the file is copied to a fixed
place in the user's data directory and a menu entry with the icon is
written, so the application starts from the menu with one click.
"""
from __future__ import annotations

import os
import shutil
import subprocess

DESKTOP_NAME = "megapencil.desktop"


def data_home() -> str:
    return os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")


def appimage_path() -> str | None:
    """Path of the AppImage this process was started from, if any."""
    p = os.environ.get("APPIMAGE")
    return p if p and os.path.isfile(p) else None


def installed_binary() -> str:
    return os.path.join(data_home(), "megapencil", "MegaPencil.AppImage")


def desktop_file() -> str:
    return os.path.join(data_home(), "applications", DESKTOP_NAME)


def icon_file() -> str:
    return os.path.join(data_home(), "icons", "hicolor", "scalable", "apps", "megapencil.svg")


def is_installed() -> bool:
    return os.path.isfile(desktop_file()) and os.path.isfile(installed_binary())


def _needs_extract_flag() -> bool:
    """True when this AppImage could not be mounted (no FUSE) and was run extracted."""
    return "appimage_extracted" in os.environ.get("APPDIR", "")


def install(source: str | None = None) -> str:
    """Install the AppImage for the current user; returns the menu entry path."""
    source = source or appimage_path()
    if not source or not os.path.isfile(source):
        raise RuntimeError("MegaPencil is not running from an AppImage, so there is nothing to install.")
    dest = installed_binary()
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.realpath(source) != os.path.realpath(dest):
        tmp = dest + ".new"
        shutil.copyfile(source, tmp)
        os.chmod(tmp, 0o755)
        os.replace(tmp, dest)
    else:
        os.chmod(dest, 0o755)

    icon = icon_file()
    os.makedirs(os.path.dirname(icon), exist_ok=True)
    shutil.copyfile(os.path.join(os.path.dirname(__file__), "resources", "megapencil.svg"), icon)

    flag = " --appimage-extract-and-run" if _needs_extract_flag() else ""
    entry = desktop_file()
    os.makedirs(os.path.dirname(entry), exist_ok=True)
    with open(entry, "w", encoding="utf-8") as f:
        f.write(
            "[Desktop Entry]\nType=Application\nVersion=1.0\nName=MegaPencil\n"
            "GenericName=Vector Graphics Editor\nComment=Draw and edit vector graphics (SVG)\n"
            f'Exec="{dest}"{flag} %F\nTryExec={dest}\nIcon={icon}\nTerminal=false\n'
            "Categories=Graphics;VectorGraphics;2DGraphics;Qt;\nMimeType=image/svg+xml;\n"
            "Keywords=vector;svg;drawing;illustration;pen;bezier;\nStartupNotify=true\n"
            "StartupWMClass=megapencil\n")
    os.chmod(entry, 0o755)
    _refresh()
    return entry


def uninstall() -> list[str]:
    """Remove the menu entry, icon and installed copy; returns what was removed."""
    removed = []
    for path in (desktop_file(), icon_file(), installed_binary()):
        try:
            os.remove(path)
            removed.append(path)
        except OSError:
            pass
    _refresh()
    return removed


def _refresh() -> None:
    try:
        subprocess.run(["update-desktop-database", "-q", os.path.join(data_home(), "applications")],
                       check=False, timeout=10, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        pass
