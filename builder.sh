#!/bin/bash
set -e

PKG_NAME="kvmsoft"
VERSION="3.0"
ARCH="amd64"
PKG_DIR="${PKG_NAME}_${VERSION}_${ARCH}"

echo "╔══════════════════════════════════════════╗"
echo "║       Build KVMSoft .deb v${VERSION}          ║"
echo "╚══════════════════════════════════════════╝"
echo ""

echo "[1/5] Création de la structure de répertoires..."
rm -rf "$PKG_DIR"
mkdir -p "$PKG_DIR/DEBIAN"
mkdir -p "$PKG_DIR/usr/bin"
mkdir -p "$PKG_DIR/usr/lib/$PKG_NAME"
mkdir -p "$PKG_DIR/usr/share/applications"

echo "[2/5] Copie des fichiers source..."
cp kvmsoft.py "$PKG_DIR/usr/lib/$PKG_NAME/"

echo "[3/5] Création des fichiers de packaging..."

cat > "$PKG_DIR/DEBIAN/control" << EOF
Package: kvmsoft
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: all
Depends: python3 (>= 3.6), python3-pip
Recommends: python3-pyqt5, python3-evdev, python3-xlib
Maintainer: Votre Nom <votre@email.com>
Description: Partage de clavier reseau entre deux machines Linux
 KVMSoft permet de partager un clavier physique entre deux ordinateurs
 Linux via TCP/IP (LAN ou VPN ZeroTier). Interface PyQt5.
EOF

cat > "$PKG_DIR/DEBIAN/postinst" << 'EOF'
#!/bin/bash
set -e
case "$1" in
    configure)
        for pkg in PyQt5 evdev python-xlib; do
            pip3 install --quiet --break-system-packages "$pkg" 2>/dev/null \
            || pip3 install --quiet "$pkg" 2>/dev/null || true
        done
        chmod +x /usr/lib/kvmsoft/kvmsoft.py /usr/bin/kvmsoft
        ;;
esac
exit 0
EOF

cat > "$PKG_DIR/DEBIAN/prerm" << 'EOF'
#!/bin/bash
set -e
case "$1" in remove|upgrade|deconfigure) : ;; esac
exit 0
EOF

cat > "$PKG_DIR/usr/bin/kvmsoft" << 'EOF'
#!/bin/bash
[ -z "$DISPLAY" ] && export DISPLAY=":0"
exec python3 /usr/lib/kvmsoft/kvmsoft.py "$@"
EOF

cat > "$PKG_DIR/usr/share/applications/kvmsoft.desktop" << 'EOF'
[Desktop Entry]
Version=1.0
Type=Application
Name=KVMSoft
Comment=Partagez votre clavier entre deux machines Linux
Exec=kvmsoft
Icon=kvmsoft
Terminal=false
Categories=Utility;Network;
EOF

echo "[4/5] Application des permissions..."
chmod 755 "$PKG_DIR/DEBIAN/postinst"
chmod 755 "$PKG_DIR/DEBIAN/prerm"
chmod 755 "$PKG_DIR/usr/bin/kvmsoft"
chmod 644 "$PKG_DIR/DEBIAN/control"
chmod 644 "$PKG_DIR/usr/lib/$PKG_NAME/kvmsoft.py"
chmod 644 "$PKG_DIR/usr/share/applications/kvmsoft.desktop"

echo "[5/5] Construction du paquet .deb..."
dpkg-deb --build "$PKG_DIR"

DEB_FILE="${PKG_DIR}.deb"

if [ -f "$DEB_FILE" ]; then
    echo ""
    echo "✅ Paquet créé : $DEB_FILE"
    echo ""
    ls -lh "$DEB_FILE"
    echo ""
    echo "── Contenu du paquet ──"
    dpkg-deb --contents "$DEB_FILE"
    echo ""
    echo "── Pour installer ──"
    echo "   sudo dpkg -i $DEB_FILE"
    echo "   sudo apt-get install -f"
else
    echo "❌ Échec : le fichier .deb n'a pas été créé."
    exit 1
fi