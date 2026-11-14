#!/usr/bin/env bash
# Build MegaPencil as a single-file AppImage: one file you can double-click.
#
#   packaging/build_appimage.sh      -> dist/MegaPencil-<version>-x86_64.AppImage
#
# The AppImage contains its own Python interpreter, Qt (PySide6-Essentials),
# pyclipper and MegaPencil, so the target machine needs no Python and no pip.
# Building downloads a relocatable CPython (python-build-standalone) and
# appimagetool from GitHub; the finished application never uses the network.
set -euo pipefail

PY_VERSION="${PY_VERSION:-3.12.7}"
PBS_RELEASE="${PBS_RELEASE:-20241016}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' "$ROOT/pyproject.toml")"
ARCH="x86_64"
CACHE="$ROOT/build/appimage/cache"
APPDIR="$ROOT/build/appimage/MegaPencil.AppDir"
OUT="$ROOT/dist"
mkdir -p "$CACHE" "$OUT"

fetch() {  # fetch <url> <file>
    if [ ! -s "$2" ]; then
        echo "Downloading $(basename "$2")"
        curl -fsSL --retry 3 -o "$2.part" "$1"
        mv "$2.part" "$2"
    fi
}
PBS="https://github.com/astral-sh/python-build-standalone/releases/download/$PBS_RELEASE"
PY_TGZ="$CACHE/cpython-$PY_VERSION-$PBS_RELEASE.tar.gz"
fetch "$PBS/cpython-$PY_VERSION+$PBS_RELEASE-$ARCH-unknown-linux-gnu-install_only_stripped.tar.gz" "$PY_TGZ"
TOOL="$CACHE/appimagetool-$ARCH.AppImage"
fetch "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-$ARCH.AppImage" "$TOOL"
chmod +x "$TOOL"

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/scalable/apps"
tar -xzf "$PY_TGZ" -C "$APPDIR"            # -> $APPDIR/python
PYTHON="$APPDIR/python/bin/python3"

PIP=("$PYTHON" -m pip install --quiet --no-compile --no-warn-script-location --disable-pip-version-check)
"${PIP[@]}" "PySide6-Essentials>=6.5" "pyclipper>=1.3"
"${PIP[@]}" --no-deps "$ROOT"

# Trim what a 2-D widgets application never loads.
SITE="$("$PYTHON" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
QT="$SITE/PySide6"
rm -rf "$QT/Qt/qml" "$QT/Qt/translations" "$QT/Qt/resources" "$QT/Qt/libexec" "$QT/examples" \
       "$QT/Qt/lib/"libQt6{Quick,Qml,WebEngine,Designer,3D,Multimedia,Pdf,Charts,DataVis,Bluetooth,Nfc,Sql,Test,Help}*.so* \
       "$QT/"Qt{Quick,Qml,WebEngine,Designer,3D,Multimedia,Pdf,Charts,DataVis,Bluetooth,Nfc,Sql,Help,UiTools}*.abi3.so \
       "$QT/Qt/plugins/imageformats/libqpdf.so" \
       "$QT/"{assistant,designer,linguist,lrelease,lupdate,qmlformat,qmllint,qmlls,balsam,balsamui,qsb} 2>/dev/null || true
PYLIB="$APPDIR/python/lib/python${PY_VERSION%.*}"
rm -rf "$PYLIB/test" "$PYLIB/idlelib" "$PYLIB/tkinter" "$PYLIB/turtledemo" "$PYLIB/ensurepip" "$PYLIB/lib2to3" \
       "$PYLIB/site-packages/pip" "$PYLIB/site-packages/pip-"* "$PYLIB/lib-dynload/"_tkinter* \
       "$APPDIR/python/lib/"{libtcl,libtk,tcl,tk,itcl,thread}* "$APPDIR/python/include" "$APPDIR/python/share"
find "$APPDIR" -name __pycache__ -type d -prune -exec rm -rf {} +

# Qt's X11 plugin needs a few small xcb helper libraries.  libxcb-cursor0 in particular is not
# part of a default Ubuntu desktop, so copies are bundled and used only where the system has none.
XCB_PKGS="libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0 libxcb-util1 libxcb-xkb1 libxkbcommon-x11-0"
mkdir -p "$CACHE/debs" "$APPDIR/usr/fallback"
if (cd "$CACHE/debs" && for p in $XCB_PKGS; do ls "${p}"_*.deb >/dev/null 2>&1 || apt-get download -q "$p" >/dev/null; done); then
    for deb in "$CACHE/debs/"*.deb; do
        rm -rf "$CACHE/x" && dpkg-deb -x "$deb" "$CACHE/x"
        for lib in $(find "$CACHE/x" -name 'lib*.so.[0-9]' ); do
            real="$(readlink -f "$lib")"
            mkdir -p "$APPDIR/usr/fallback/$(basename "$lib")"
            cp "$real" "$APPDIR/usr/fallback/$(basename "$lib")/$(basename "$lib")"
        done
    done
    rm -rf "$CACHE/x"
else
    echo "warning: could not download the xcb helper libraries; on X11 the AppImage will need" >&2
    echo "         'sudo apt install libxcb-cursor0' on the target machine." >&2
fi

cat > "$APPDIR/AppRun" <<'APPRUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
unset PYTHONHOME PYTHONPATH
# Use a bundled xcb helper library only when the system does not provide it.
KNOWN="$(/sbin/ldconfig -p 2>/dev/null)"
for dir in "$HERE"/usr/fallback/*; do
    [ -d "$dir" ] || continue
    case "$KNOWN" in
        *"$(basename "$dir")"*) ;;
        *) LD_LIBRARY_PATH="$dir${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" ;;
    esac
done
export LD_LIBRARY_PATH
export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
exec "$HERE/python/bin/python3" -m megapencil "$@"
APPRUN
chmod 755 "$APPDIR/AppRun"

cp "$ROOT/packaging/megapencil.desktop" "$APPDIR/megapencil.desktop"
cp "$ROOT/packaging/megapencil.desktop" "$APPDIR/usr/share/applications/"
cp "$ROOT/src/megapencil/resources/megapencil.svg" "$APPDIR/megapencil.svg"
cp "$ROOT/src/megapencil/resources/megapencil.svg" "$APPDIR/usr/share/icons/hicolor/scalable/apps/"
ln -sf megapencil.svg "$APPDIR/.DirIcon"

APPIMAGE="$OUT/MegaPencil-$VERSION-$ARCH.AppImage"
LOG="$ROOT/build/appimage/appimagetool.log"
rm -f "$APPIMAGE"
# --appimage-extract-and-run lets the tool itself run where FUSE is missing (containers, CI).
if ! ARCH="$ARCH" "$TOOL" --appimage-extract-and-run --no-appstream "$APPDIR" "$APPIMAGE" >"$LOG" 2>&1; then
    tail -20 "$LOG"
    exit 1
fi
chmod +x "$APPIMAGE"
echo "Built $APPIMAGE ($(du -h "$APPIMAGE" | cut -f1))"
