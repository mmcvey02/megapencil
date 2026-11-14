#!/usr/bin/env bash
# Build a self-contained .deb for MegaPencil.
#
#   packaging/build_deb.sh            -> dist/megapencil_<version>_<arch>.deb
#
# The package bundles MegaPencil and its Python dependencies (PySide6-Essentials,
# pyclipper) under /opt/megapencil, so the installed app needs no network access
# and no pip.  It depends on the same Python minor version it was built with
# (pyclipper is a compiled extension), so build it on the Ubuntu release you
# target, with Python 3.11 or newer.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-python3}"
PYVER="$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else "MegaPencil needs Python 3.11+")'
VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' "$ROOT/pyproject.toml")"
ARCH="$(dpkg --print-architecture)"
STAGE="$ROOT/build/deb/megapencil_${VERSION}_${ARCH}"
OUT="$ROOT/dist"

rm -rf "$STAGE"
mkdir -p "$STAGE/DEBIAN" "$STAGE/opt/megapencil/lib" "$STAGE/usr/bin" \
         "$STAGE/usr/share/applications" "$STAGE/usr/share/icons/hicolor/scalable/apps" "$OUT"

# Application + dependencies (Essentials has QtCore/QtGui/QtWidgets/QtSvg, all MegaPencil uses).
"$PY" -m pip install --quiet --no-compile --target "$STAGE/opt/megapencil/lib" \
    "PySide6-Essentials>=6.5" "pyclipper>=1.3"
"$PY" -m pip install --quiet --no-compile --no-deps --target "$STAGE/opt/megapencil/lib" "$ROOT"
rm -rf "$STAGE/opt/megapencil/lib/bin"
# Trim Qt pieces a 2-D widgets application never loads.
QT="$STAGE/opt/megapencil/lib/PySide6"
rm -rf "$QT/Qt/qml" "$QT/Qt/translations" "$QT/Qt/resources" "$QT/Qt/libexec" "$QT/examples" \
       "$QT/Qt/lib/"libQt6{Quick,Qml,WebEngine,Designer,3D,Multimedia,Pdf,Charts,DataVis,Bluetooth,Nfc,Sql,Test,Help}*.so* \
       "$QT/"Qt{Quick,Qml,WebEngine,Designer,3D,Multimedia,Pdf,Charts,DataVis,Bluetooth,Nfc,Sql,Help,UiTools}*.abi3.so \
       "$QT/"{assistant,designer,linguist,lrelease,lupdate,qmlformat,qmllint,qmlls,balsam,balsamui,qsb} 2>/dev/null || true

cat > "$STAGE/usr/bin/megapencil" <<LAUNCHER
#!/bin/sh
export PYTHONPATH="/opt/megapencil/lib\${PYTHONPATH:+:\$PYTHONPATH}"
exec python${PYVER} -m megapencil "\$@"
LAUNCHER
chmod 755 "$STAGE/usr/bin/megapencil"

install -m 644 "$ROOT/packaging/megapencil.desktop" "$STAGE/usr/share/applications/megapencil.desktop"
install -m 644 "$ROOT/src/megapencil/resources/megapencil.svg" \
    "$STAGE/usr/share/icons/hicolor/scalable/apps/megapencil.svg"

SIZE_KB="$(du -sk "$STAGE" | cut -f1)"
cat > "$STAGE/DEBIAN/control" <<CONTROL
Package: megapencil
Version: ${VERSION}
Section: graphics
Priority: optional
Architecture: ${ARCH}
Installed-Size: ${SIZE_KB}
Depends: python${PYVER}, libegl1, libgl1, libxkbcommon0, libxkbcommon-x11-0, libfontconfig1, libdbus-1-3, libxcb-cursor0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-render-util0, libxcb-shape0, libxcb-xinerama0
Maintainer: MegaPencil contributors <noreply@example.invalid>
Description: Vector graphics editor
 MegaPencil is a desktop vector graphics editor with pen, shape and text
 tools, layers, boolean path operations and gradients.  SVG is its native
 file format; it exports PNG and PDF and works entirely offline.
CONTROL

cat > "$STAGE/DEBIAN/postinst" <<'POSTINST'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then update-desktop-database -q || true; fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then gtk-update-icon-cache -q /usr/share/icons/hicolor || true; fi
POSTINST
chmod 755 "$STAGE/DEBIAN/postinst"

DEB="$OUT/megapencil_${VERSION}_${ARCH}.deb"
dpkg-deb --build --root-owner-group "$STAGE" "$DEB" >/dev/null
echo "Built $DEB ($(du -h "$DEB" | cut -f1))"
