"""Test statici dell'app nativa macOS «Amy Core».

L'app è scritta in Swift e usa solo framework di sistema. Qui si controlla
che non introduca dipendenze a pagamento, risorse remote o servizi esterni, e
che la struttura del bundle sia completa.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_DIR = ROOT / "apps" / "AmyCore"
SOURCES = APP_DIR / "Sources" / "AmyCoreApp.swift"
TOOLS = APP_DIR / "Tools" / "make_icon.swift"
BUILD = APP_DIR / "build.sh"
SELFTEST = APP_DIR / "selftest.py"
INFO = APP_DIR / "Resources" / "Info.plist"


class NativeAppTests(unittest.TestCase):
    def test_files_exist(self) -> None:
        for path in (SOURCES, TOOLS, BUILD, SELFTEST, INFO):
            self.assertTrue(path.is_file(), str(path))

    def test_no_external_resources(self) -> None:
        """Nessuna CDN, nessun endpoint commerciale, nessun account."""
        for path in (SOURCES, TOOLS, BUILD, SELFTEST, INFO):
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"https?://(?!127\.0\.0\.1|localhost)", str(path))
            self.assertNotIn("api.openai.com", text, str(path))
            self.assertNotIn("api.anthropic.com", text, str(path))

    def test_only_system_frameworks(self) -> None:
        text = SOURCES.read_text(encoding="utf-8")
        imports = set(re.findall(r"^import\s+([A-Za-z]+)", text, re.MULTILINE))
        allowed = {"AppKit", "WebKit", "Foundation", "Darwin"}
        self.assertTrue(imports)
        self.assertEqual(imports - allowed, set(), "import non di sistema: %s" % (imports - allowed))

    def test_build_script_uses_system_tools_only(self) -> None:
        text = BUILD.read_text(encoding="utf-8")
        for tool in ("swiftc", "iconutil", "codesign"):
            self.assertIn(tool, text, tool)
        for forbidden in ("brew", "pip install", "npm ", "curl ", "wget "):
            self.assertNotIn(forbidden, text, forbidden)

    def test_info_plist_is_complete(self) -> None:
        text = INFO.read_text(encoding="utf-8")
        for key in (
            "CFBundleName",
            "CFBundleIdentifier",
            "CFBundleExecutable",
            "CFBundlePackageType",
            "CFBundleShortVersionString",
            "LSMinimumSystemVersion",
            "NSAppTransportSecurity",
        ):
            self.assertIn(key, text, key)
        self.assertIn("AmyCore", text)

    def test_backend_is_local_only(self) -> None:
        """Il backend deve restare legato al loopback."""
        text = SOURCES.read_text(encoding="utf-8")
        self.assertIn("127.0.0.1", text)
        self.assertNotIn("0.0.0.0", text)

    def test_heartbeat_protects_from_orphans(self) -> None:
        text = SOURCES.read_text(encoding="utf-8")
        self.assertIn("AMY_HEARTBEAT_FILE", text)
        self.assertIn("app.heartbeat", text)

    def test_heartbeat_does_not_depend_on_the_main_run_loop(self) -> None:
        """L'heartbeat deve sopravvivere a un alert modale.

        Un ``Timer`` sul main run loop smette di scattare mentre l'app mostra
        un ``NSAlert`` modale: il backend interpretava il file fermo come
        «genitore morto» e chiudeva la dashboard da solo. Serve un sorgente
        su una coda dedicata.
        """
        text = SOURCES.read_text(encoding="utf-8")
        self.assertIn("DispatchSource.makeTimerSource", text)
        self.assertIn("heartbeatTimer: DispatchSourceTimer?", text)
        self.assertNotIn("heartbeatTimer: Timer?", text)
        self.assertNotIn("Timer.scheduledTimer(withTimeInterval: 2.0", text)

    def test_backend_lost_alert_does_not_freeze_the_app(self) -> None:
        """L'avviso «backend non risponde» non deve bloccare il thread principale.

        Con `runModal` l'app restava congelata finché l'utente non rispondeva:
        la finestra non si aggiornava e il caso è stato osservato per ore.
        Serve una sheet, che lascia l'app viva.
        """
        text = SOURCES.read_text(encoding="utf-8")
        start = text.index("private func presentBackendLost()")
        end = text.index("private func restartBackend()", start)
        body = text[start:end]
        self.assertIn("beginSheetModal", body)
        # L'unico `alert.runModal()` ammesso è il ripiego senza finestra.
        self.assertLessEqual(body.count("alert.runModal()"), 1)

    def test_selftest_is_standard_library_only(self) -> None:
        text = SELFTEST.read_text(encoding="utf-8")
        imports = set(re.findall(r"^(?:import|from)\s+([A-Za-z_][\w.]*)", text, re.MULTILINE))
        allowed = {"__future__", "os", "subprocess", "sys", "pathlib"}
        self.assertEqual(imports - allowed, set(), "import non previsti: %s" % (imports - allowed))


if __name__ == "__main__":
    unittest.main()
