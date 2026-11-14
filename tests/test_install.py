"""Per-user installation into the application menu."""
import os
import stat

import pytest

from megapencil import desktop_install as di
from megapencil.app import main


@pytest.fixture
def fake(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    src = tmp_path / "Downloads" / "MegaPencil-0.1.0-x86_64(2).AppImage"
    src.parent.mkdir()
    src.write_bytes(b"\x7fELF fake appimage")  # not executable, like a fresh download
    monkeypatch.setenv("APPIMAGE", str(src))
    monkeypatch.delenv("APPDIR", raising=False)
    return src


def test_install_and_uninstall(fake, tmp_path):
    assert di.appimage_path() == str(fake) and not di.is_installed()
    entry = di.install()
    binary = di.installed_binary()
    assert di.is_installed() and entry == str(tmp_path / "data" / "applications" / "megapencil.desktop")
    assert open(binary, "rb").read() == fake.read_bytes()
    assert os.stat(binary).st_mode & stat.S_IXUSR  # executable even though the download was not
    text = open(entry).read()
    assert f'Exec="{binary}" %F' in text and "Name=MegaPencil" in text and f"Icon={di.icon_file()}" in text
    assert os.path.isfile(di.icon_file())
    di.install()  # idempotent; also works when started from the installed copy
    os.environ["APPIMAGE"] = binary
    di.install()
    assert open(binary, "rb").read() == fake.read_bytes()
    assert len(di.uninstall()) == 3 and not di.is_installed() and di.uninstall() == []


def test_extract_and_run_mode_is_remembered(fake, monkeypatch):
    monkeypatch.setenv("APPDIR", "/tmp/appimage_extracted_abc")
    assert "--appimage-extract-and-run %F" in open(di.install()).read()


def test_command_line(fake, monkeypatch, capsys):
    assert main(["megapencil", "--install"]) == 0 and di.is_installed()
    assert "application menu" in capsys.readouterr().out
    assert main(["megapencil", "--uninstall"]) == 0 and not di.is_installed()
    monkeypatch.delenv("APPIMAGE")
    assert main(["megapencil", "--install"]) == 1
    assert "not running from an AppImage" in capsys.readouterr().err


def test_help_menu_action(window, fake):
    assert window.install_to_menu() and di.is_installed()
    window.offer_install()  # non-interactive windows never prompt
