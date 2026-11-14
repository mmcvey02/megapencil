#!/usr/bin/env bash
# Build a self-contained .deb for MegaPencil.
#
#   packaging/build_deb.sh            -> dist/megapencil_<version>_amd64.deb
#
# The package contains the same bundle as the AppImage (its own Python, Qt,
# pyclipper and MegaPencil) under /opt/megapencil, plus a `megapencil` command,
# the application-menu entry and the icon.  It needs no Python on the target
# machine: download it, double-click it, press Install.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' "$ROOT/pyproject.toml")"
ARCH="amd64"
APPDIR="$ROOT/build/appimage/MegaPencil.AppDir"
STAGE="$ROOT/build/deb/megapencil_${VERSION}_${ARCH}"
OUT="$ROOT/dist"

# The AppImage script assembles the bundle; reuse it.
if [ "${REUSE_APPDIR:-0}" != "1" ] || [ ! -x "$APPDIR/AppRun" ]; then
    "$ROOT/packaging/build_appimage.sh"
fi

rm -rf "$STAGE"
mkdir -p "$STAGE/DEBIAN" "$STAGE/opt" "$STAGE/usr/bin" "$STAGE/usr/share/applications" \
         "$STAGE/usr/share/icons/hicolor/scalable/apps" "$OUT"
cp -a "$APPDIR" "$STAGE/opt/megapencil"
rm -rf "$STAGE/opt/megapencil/usr/share" "$STAGE/opt/megapencil/.DirIcon" "$STAGE/opt/megapencil/megapencil.desktop"

cat > "$STAGE/usr/bin/megapencil" <<'LAUNCHER'
#!/bin/sh
exec /opt/megapencil/AppRun "$@"
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
Depends: libc6 (>= 2.34), libegl1, libgl1, libxkbcommon0, libfontconfig1, libdbus-1-3
Maintainer: MegaPencil contributors <noreply@example.invalid>
Description: Vector graphics editor
 MegaPencil is a desktop vector graphics editor with pen, shape and text
 tools, layers, boolean path operations and gradients.  SVG is its native
 file format; it exports PNG and PDF and works entirely offline.
 .
 The package bundles its own Python interpreter and Qt libraries.
CONTROL

cat > "$STAGE/DEBIAN/postinst" <<'POSTINST'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then update-desktop-database -q || true; fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then gtk-update-icon-cache -q /usr/share/icons/hicolor || true; fi
POSTINST
chmod 755 "$STAGE/DEBIAN/postinst"

DEB="$OUT/megapencil_${VERSION}_${ARCH}.deb"
rm -f "$DEB"
dpkg-deb --build --root-owner-group "$STAGE" "$DEB" >/dev/null
echo "Built $DEB ($(du -h "$DEB" | cut -f1))"
