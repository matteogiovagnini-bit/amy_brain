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
            "/api/calendar/upcoming",
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

    def test_wake_listening_starts_only_from_the_button(self) -> None:
        """L'ascolto continuo deve partire solo da un comando esplicito."""
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="wakeBtn"', html)
        self.assertIn('aria-pressed="false"', html)
        self.assertIn("/api/voice/wake/start", js)
        self.assertIn("/api/voice/wake/stop", js)
        # Un solo punto di avvio, dentro il gestore del click.
        self.assertEqual(js.count("/api/voice/wake/start"), 1)
        self.assertIn('wake.addEventListener("click", toggleWake)', js)

    def test_startup_greeting_is_visible_and_repeatable(self) -> None:
        """Il saluto di avvio è dichiarato nella UI e ripetibile a comando."""
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="voiceGreeting"', html)
        self.assertIn('id="greetBtn"', html)
        self.assertIn("/api/voice/greet", js)
        self.assertIn('greetButton.addEventListener("click", greet)', js)
        # Il testo del saluto arriva dai dati reali dello stato.
        self.assertIn("startup_greeting", js)

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

    def test_calendar_panel_shows_upcoming_appointments(self) -> None:
        """Il riquadro «Prossimi appuntamenti» usa calendar.events, senza inventare dati."""
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        css = (STATIC / "style.css").read_text(encoding="utf-8")

        for marker in ("calendarTitle", "calendarTag", "calendarEvents",
                       "calendarRefreshBtn", "calendarNote", "Prossimi appuntamenti"):
            self.assertIn(marker, html, marker)
        self.assertIn('aria-live="polite"', html)
        self.assertIn('aria-labelledby="calendarTitle"', html)
        # Il riquadro è l'ottava card: deve avere il proprio z-index.
        self.assertIn(".side-panel .card:nth-child(8)", css)
        self.assertIn(".calendar-event", css)

        self.assertIn("/api/calendar/upcoming", js)
        self.assertIn("renderCalendar(", js)
        self.assertIn("refreshCalendar(", js)
        self.assertIn('calendarRefreshButton.addEventListener("click"', js)
        self.assertIn("calendarTimer", js)

    def test_calendar_panel_declares_missing_data_and_never_injects_markup(self) -> None:
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        self.assertIn("Nessun appuntamento", js)
        self.assertIn("Calendario non disponibile", js)
        self.assertIn("Nessun dato inventato", js)
        self.assertIn("Lettura parziale", js)
        self.assertNotIn(".innerHTML", js)
        self.assertNotIn("document.write", js)

    def test_calendar_is_polled_more_slowly_than_the_state(self) -> None:
        """Leggere Calendar.app a ogni poll dello stato sarebbe troppo costoso."""
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        self.assertIn("CALENDAR_POLL_MS = 120000", js)
        self.assertIn("window.setInterval(() => refreshCalendar(true), CALENDAR_POLL_MS)", js)
        self.assertIn("window.setInterval(refreshState, BASE_POLL_MS)", js)

    def test_personal_tasks_and_notes_panel(self) -> None:
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        for marker in ("tasksList", "notesList", "personalTag", "Attività e note"):
            self.assertIn(marker, html)
        self.assertIn("renderPersonal", js)
        self.assertNotIn("innerHTML", js)

    def test_project_panel_is_read_only(self) -> None:
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        module = (STATIC / "project.js").read_text(encoding="utf-8")
        for marker in (
            "projectTitle",
            "projectTag",
            "projectBranch",
            "projectModified",
            "projectCommit",
            "projectDiff",
            "projectRefreshBtn",
        ):
            self.assertIn(marker, html)
        self.assertIn("renderProject", js)
        self.assertIn("/api/dev/status", module)
        self.assertIn("window.AmyProject", module)
        self.assertLess(html.index("/static/project.js"), html.index("/static/app.js"))
        self.assertNotIn("innerHTML", js)
        self.assertNotIn("innerHTML", module)

    def test_neuron_field_is_local_and_respects_reduced_motion(self) -> None:
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        js = (STATIC / "neurons.js").read_text(encoding="utf-8")
        self.assertIn('id="neuronField"', html)
        self.assertIn("/static/neurons.js", html)
        self.assertLess(html.index("/static/neurons.js"), html.index("/static/app.js"))
        self.assertIn("window.AmyNeurons", js)
        self.assertIn("prefers-reduced-motion", js)
        self.assertIn("requestAnimationFrame", js)
        self.assertIn("visibilitychange", js)
        self.assertIn("ACTIVE_STATES", js)
        self.assertIn("FRAME_INTERVAL", js)
        self.assertIn("1 / 24", js)
        self.assertIn("1 / 12", js)
        self.assertIn("onBlur", js)
        self.assertNotIn("innerHTML", js)
        self.assertNotIn("http://", js)
        self.assertNotIn("https://", js)

    def test_core_hud_uses_real_data_without_remote_assets(self) -> None:
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        css = (STATIC / "style.css").read_text(encoding="utf-8")
        for marker in (
            "core-hud",
            "hudProvider",
            "hudMemory",
            "hudVoice",
            "hudRobot",
            "hud-arc",
            "hud-tick",
        ):
            self.assertIn(marker, html)
        self.assertIn("renderHud", js)
        self.assertIn(".core-hud", css)
        self.assertIn("hud-arc-a", css)
        self.assertIn("animation-play-state: paused", css)
        self.assertIn('data-state="listening"', css)
        self.assertIn('data-app-focus="off"', css)
        self.assertNotIn("innerHTML", js)
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)

    def test_log_panel_reads_only_the_local_file(self) -> None:
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        for marker in ("logTitle", "logTag", "logView", "logRefreshBtn"):
            self.assertIn(marker, html)
        self.assertIn("/api/logs?limit=", js)
        self.assertIn("renderLogs", js)
        self.assertNotIn("innerHTML", js)

    def test_permissions_panel_can_revoke_and_restore(self) -> None:
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        for marker in ("permissionsList", "permissionsRefreshBtn", "Permessi"):
            self.assertIn(marker, html)
        for marker in ("loadPermissions", "togglePermission", "/api/permissions/revoke", "/api/permissions/restore"):
            self.assertIn(marker, js)
        self.assertNotIn("innerHTML", js)

    def test_modules_panel_shows_real_state_and_toggle(self) -> None:
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        css = (STATIC / "style.css").read_text(encoding="utf-8")
        for marker in ("modulesList", "modulesRefreshBtn", "modulesTag", "Moduli"):
            self.assertIn(marker, html)
        for marker in ("loadModules", "toggleModule", "MODULES_POLL_MS", "/api/modules/"):
            self.assertIn(marker, js)
        self.assertIn(".module-row", css)
        self.assertNotIn("innerHTML", js)

    def test_estop_is_labelled_as_software_only(self) -> None:
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertIn("E-STOP SOFTWARE", html)
        self.assertIn("non sostituisce", html.lower())


if __name__ == "__main__":
    unittest.main()
