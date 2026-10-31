#!/usr/bin/env bash
#
# Costruisce Amy Core.app: applicazione macOS nativa in Swift.
#
# - usa solo tool di sistema (swiftc, iconutil, codesign): nessuna dipendenza
#   da installare, nessun account, nessun costo;
# - il backend Python viene avviato dall'app, non è incorporato nel bundle;
# - l'icona è generata localmente da Tools/make_icon.swift.
#
# Uso:
#   ./apps/AmyCore/build.sh                 # usa il repository corrente
#   AMY_REPO_PATH=/percorso ./apps/AmyCore/build.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_DIR="$ROOT/apps/AmyCore"
DIST="$APP_DIR/dist"
BUILD="$DIST/.build"
APP="$DIST/Amy Core.app"

REPO_PATH="${AMY_REPO_PATH:-$ROOT}"
VERSION="$(awk -F'"' '/version = / {print $2; exit}' "$ROOT/pyproject.toml" 2>/dev/null || echo "0.1.0")"

if ! command -v swiftc >/dev/null 2>&1; then
    echo "ERRORE: swiftc non trovato. Serve Xcode Command Line Tools (gratuite)." >&2
    exit 1
fi

if [ ! -d "$REPO_PATH/amy" ]; then
    echo "ERRORE: $REPO_PATH non sembra il repository di Amy Brain." >&2
    exit 1
fi

echo "==> Compilazione (Swift, -swift-version 5)"
rm -rf "$BUILD"
mkdir -p "$BUILD"

cat > "$BUILD/BuiltConfig.swift" <<EOF
// Generato da apps/AmyCore/build.sh — non modificare a mano.
enum BuiltConfig {
    static let defaultRepoPath = "$(printf '%s' "$REPO_PATH" | sed 's/"/\\"/g')"
    static let appVersion = "$VERSION"
}
EOF

swiftc -O -swift-version 5 \
    -o "$BUILD/AmyCore" \
    "$APP_DIR/Sources/AmyCoreApp.swift" "$BUILD/BuiltConfig.swift"

echo "==> Icona"
swiftc -O -swift-version 5 -o "$BUILD/make_icon" "$APP_DIR/Tools/make_icon.swift"
"$BUILD/make_icon" "$BUILD/AmyCore.iconset"
iconutil -c icns "$BUILD/AmyCore.iconset" -o "$BUILD/AmyCore.icns"

echo "==> Bundle"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BUILD/AmyCore" "$APP/Contents/MacOS/AmyCore"
cp "$BUILD/AmyCore.icns" "$APP/Contents/Resources/AmyCore.icns"
cp "$APP_DIR/Resources/Info.plist" "$APP/Contents/Info.plist"
printf 'APPL????' > "$APP/Contents/PkgInfo"

echo "==> Firma ad-hoc (nessun certificato, nessun costo)"
codesign --force --sign - --timestamp=none "$APP" >/dev/null 2>&1 || \
    echo "ATTENZIONE: firma ad-hoc non riuscita; l'app funziona comunque in locale."

echo
echo "Applicazione pronta: $APP"
echo "Prova:  open \"$APP\""
echo "Installa in ~/Applications:  cp -R \"$APP\" ~/Applications/"
