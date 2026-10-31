"""Test statici della dashboard: nessuna risorsa esterna, niente innerHTML.

I test verificano anche i requisiti dell'interfaccia «Amy Core»: otto stati
del nucleo, accessibilità, movimento ridotto e assenza di stili inline
(vietati dalla CSP ``style-src 'self'`` del server).
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "amy" / "ui" / "static"

CORE_STATES = (
    "idle",
    "listening",
    "processing",
    "speaking",
    "executing",
    "waiting_confirmation",
    "error",
    "offline",
)


class StaticUiTests(unittest.TestCase):
    def test_files_exist(self) -> None:
        for name in ("index.html", "style.css", "app.js"):
            self.assertTrue((STATIC / name).is_file(), name)

    def test_no_external_resources(self) -> None:
        for name in ("index.html", "style.css", "app.js"):
            text = (STATIC / name).read_text(encoding="utf-8")
            self.assertNotRegex(text, r"https?://", name)
            self.assertNotIn("//cdn", text, name)

    def test_no_inner_html(self) -> None:
        text = (STATIC / "app.js").read_text(encoding="utf-8")
        self.assertNotIn(".innerHTML", text)
        self.assertNotIn("document.write", text)
        self.assertNotIn("eval(", text)

    def test_index_references_local_assets(self) -> None:
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="/static/style.css"', html)
        self.assertIn('src="/static/app.js"', html)
        self.assertIn('lang="it"', html)

    def test_app_uses_expected_endpoints(self) -> None:
        text = (STATIC / "app.js").read_text(encoding="utf-8")
        for endpoint in (
            "/api/state",
            "/api/chat",
            "/api/confirm",
            "/api/new_session",
            "/api/transcript",
            "/api/robot/estop",
            "/api/robot/stop",
            "/api/voice/listen",
            "/api/voice/stop",
            "/api/speak",
        ):
            self.assertIn(endpoint, text, endpoint)
        self.assertNotRegex(text, re.compile(r"fetch\(\s*['\"]https?://"))

    def test_no_inline_styles(self) -> None:
        """La CSP del server consente solo fogli esterni: niente style inline."""
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertNotRegex(html, re.compile(r"\sstyle\s*="), "stile inline in index.html")
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        self.assertNotRegex(js, re.compile(r"\.style\s*[\.\[]"), "scrittura di stili dal JS")
        self.assertNotIn('setAttribute("style"', js)
        self.assertNotIn("setAttribute('style'", js)

    def test_core_contains_the_eight_states(self) -> None:
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        css = (STATIC / "style.css").read_text(encoding="utf-8")
        for state in CORE_STATES:
            self.assertIn('"' + state + '"', js, "stato mancante nel JS: " + state)
            self.assertIn('data-state="' + state + '"', css, "stato mancante nel CSS: " + state)

    def test_core_states_are_derived_from_real_signals(self) -> None:
        """Gli stati devono dipendere da segnali reali, non da valori casuali."""
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        self.assertIn("in_corso", js)  # attività realmente in corso
        self.assertIn("pending_confirmations", js)  # conferma realmente pendente
        self.assertIn("voice.speaking", js)  # sintesi realmente attiva
        self.assertIn("estop_latched", js)  # latch E-stop reale
        self.assertNotIn("setTimeout(() => Math.random", js)

    def test_layout_has_the_three_areas(self) -> None:
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        for marker in ("chat-panel", "core-panel", "side-panel"):
            self.assertIn(marker, html, marker)
        self.assertIn('id="amyCore"', html)
        self.assertIn('id="messages"', html)
        self.assertIn('id="systemOs"', html)

    def test_layout_is_stage_with_satellite_chat_and_overlapping_panels(self) -> None:
        """Il nucleo occupa il palco, la chat è un satellite, i pannelli si sovrappongono."""
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        css = (STATIC / "style.css").read_text(encoding="utf-8")
        self.assertIn('class="stage"', html)
        self.assertIn("orbit-link", html)
        self.assertIn('class="side-scroll"', html)
        # Il nucleo è a piena area, senza card contenitiva.
        self.assertIn(".core-panel {", css)
        self.assertIn("inset: 0;", css)
        # La chat è posizionata rispetto al palco, non in una griglia.
        self.assertIn(".chat-panel {", css)
        self.assertIn("position: absolute;", css)
        # Le schede di sinistra si accavallano e si sollevano al focus.
        self.assertIn("margin-top: -12px;", css)
        self.assertIn(".side-panel .card:focus-within", css)
        # Sotto la soglia del palco si passa al flusso verticale.
        self.assertIn("@media (max-width: 1040px)", css)
        self.assertIn("order: -3;", css)  # chat subito dopo la topbar
        self.assertIn("order: -2;", css)  # poi la barra comandi

    def test_command_bar_is_separate_and_starfield_is_static(self) -> None:
        """La barra comandi vive fuori dalla chat; lo sfondo stellato è locale."""
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        css = (STATIC / "style.css").read_text(encoding="utf-8")

        self.assertIn('class="command-bar"', html)
        bar_start = html.index('class="command-bar"')
        core_start = html.index('class="panel core-panel"')
        self.assertLess(bar_start, core_start)

        # Gli stessi controlli di prima, ma dentro la barra: un solo invio.
        for control in ("chatForm", "composerInput", "micBtn", "sendBtn", "speakToggle"):
            position = html.index('id="' + control + '"')
            self.assertTrue(
                bar_start < position < core_start,
                "controllo fuori dalla barra comandi: " + control,
            )

        # Il nucleo non deve finire sotto la barra: riserva spazio in fondo.
        self.assertIn("padding-bottom: clamp(116px", css)
        self.assertIn(".command-bar {", css)

        # Campo stellato: SVG inline generato localmente, nessuna risorsa esterna.
        self.assertIn('class="bg-stars"', html)
        self.assertIn('<svg viewBox="0 0 1600 1000"', html)
        self.assertIn(".bg-stars", css)
        self.assertNotIn("<img", html)
        self.assertNotIn("<video", html)

    def test_accessibility_basics(self) -> None:
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        css = (STATIC / "style.css").read_text(encoding="utf-8")
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        self.assertIn("skip-link", html)
        self.assertIn(":focus-visible", css)
        self.assertIn("aria-label", html)
        self.assertIn("aria-live", html)
        self.assertIn("role=\"dialog\"", html)
        self.assertIn("trapFocus", js)
        self.assertIn('"Escape"', js)
        self.assertIn("prefers-reduced-motion", css)

    def test_status_is_not_color_only(self) -> None:
        """Lo stato deve essere leggibile anche senza colore."""
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="coreState"', html)
        self.assertIn('id="coreActivity"', html)
        self.assertIn("text(\"coreState\", view.label)", js)

    def test_reduced_motion_toggle(self) -> None:
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        css = (STATIC / "style.css").read_text(encoding="utf-8")
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        self.assertIn('data-motion="full"', html)
        self.assertIn('id="motionBtn"', html)
        self.assertIn('html[data-motion="off"]', css)
        self.assertIn("prefers-reduced-motion", js)

    def test_fullscreen_and_responsive(self) -> None:
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        css = (STATIC / "style.css").read_text(encoding="utf-8")
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="fullscreenBtn"', html)
        self.assertIn("requestFullscreen", js)
        self.assertIn("is-fullscreen", css)
        self.assertIn("@media (max-width", css)

    def test_unavailable_data_is_explicit(self) -> None:
        """I valori assenti si dichiarano: niente dati inventati."""
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        self.assertIn("Non disponibile", js)
        self.assertIn("Non configurato", js)
        self.assertIn("modello mancante", js)
        self.assertIn("model_installed", js)
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertIn("Non disponibile", html)

    def test_estop_is_labelled_as_software_only(self) -> None:
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertIn("E-STOP SOFTWARE", html)
        self.assertIn("non sostituisce", html.lower())


if __name__ == "__main__":
    unittest.main()
