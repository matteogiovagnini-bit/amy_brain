"""Dashboard web locale di Amy.

Server HTTP sulla sola interfaccia locale (predefinita 127.0.0.1), senza
dipendenze esterne. Non espone il controllo remoto: per usarlo da un altro
dispositivo serve una configurazione di rete esplicita e consapevole.
"""

from __future__ import annotations

import ipaddress
import json
import mimetypes
import os
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from .. import __version__
from ..core.assistant import Assistant
from ..core.config import Config
from ..core.errors import AmyError, ConfigError
from ..core.logging_setup import get_logger, setup_logging
from ..macos import list_accounts
from ..voice.state import VoiceState
from ..voice.wakeword import normalize

_log = get_logger("ui.server")
STATIC = Path(__file__).parent / "static"
MAX_BODY = 2 * 1024 * 1024


class AmyHandler(BaseHTTPRequestHandler):
    server_version = "Amy/0.1"

    @property
    def assistant(self) -> Assistant:
        return self.server.assistant  # type: ignore[attr-defined]

    # ------------------------------------------------------------------ utils
    def _send_json(self, data: Any, status: int = 200) -> None:
        payload = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(payload)

    def _send_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self._send_json({"error": "file non trovato"}, 404)
            return
        data = path.read_bytes()
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
            content_type += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        )
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self) -> Dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length > MAX_BODY:
            raise ValueError("Richiesta troppo grande.")
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Il corpo deve essere un oggetto JSON.")
        return data

    def log_message(self, fmt: str, *args: Any) -> None:
        _log.debug("%s - %s", self.address_string(), fmt % args)

    # ---------------------------------------------------------- ascolto wake
    def _start_wake_loop(self) -> None:
        """Avvia l'ascolto continuo su richiesta della UI (o automaticamente all'avvio)."""
        voice = self.assistant.voice
        status = voice.status()
        if not bool(voice.config.get("voice.wake_word.enabled", False)):
            self._send_json(
                {
                    "error": "Ascolto continuo disattivato nella configurazione.",
                    "detail": "Imposta voice.wake_word.enabled = true in ~/.amy/config.json.",
                },
                400,
            )
            return
        if not status["wake_word"]["available"]:
            recorder = status.get("recorder") or {}
            if recorder.get("stuck"):
                self._send_json(
                    {
                        "error": "Il microfono non risponde: ascolto non avviato.",
                        "detail": recorder.get("problem")
                        or "Riavvia il servizio audio di macOS o il Mac, poi riprova.",
                    },
                    503,
                )
                return
            self._send_json(
                {"error": "Servono microfono e trascrizione locale per l'ascolto continuo."},
                400,
            )
            return
        voice.start_wake_loop(self._on_voice_command)
        self._send_json({"ok": True, "voice": voice.status()})

    def _on_voice_command(self, text: str) -> None:
        """Esegue un comando dettato e pronuncia la risposta, in un thread separato."""
        self.server.handle_voice_command(text)

    # -------------------------------------------------------------------- GET
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path in {"/", "/index.html"}:
                self._send_file(STATIC / "index.html")
            elif path.startswith("/static/"):
                name = path[len("/static/"):]
                if ".." in name or name.startswith("/"):
                    self._send_json({"error": "percorso non valido"}, 400)
                    return
                self._send_file(STATIC / name)
            elif path == "/api/permissions":
                self._send_json(self.assistant.authorization.snapshot())
            elif path == "/api/modules":
                self._send_json({"modules": self.assistant.modules.statuses()})
            elif path.startswith("/api/modules/"):
                name = path[len("/api/modules/"):].strip("/")
                modules = {
                    item["manifest"]["name"]: item
                    for item in self.assistant.modules.statuses()
                }
                if name not in modules:
                    self._send_json({"error": "Modulo non trovato"}, 404)
                    return
                self._send_json(modules[name])
            elif path == "/api/state":
                self._send_json(self.assistant.status())
            elif path == "/api/health":
                self._send_json({"ok": True, "version": __version__})
            elif path == "/api/tools":
                self._send_json({"tools": self.assistant.registry.catalog()})
            elif path == "/api/transcript":
                query = parse_qs(parsed.query)
                session = (query.get("session") or [""])[0] or self.assistant.resume_session()
                self._send_json({"session_id": session, "messages": self.assistant.transcript(session, 100)})
            elif path == "/api/pending":
                self._send_json({"pending": self.assistant.pending_confirmations()})
            elif path == "/api/activities":
                self._send_json({"activities": self.assistant.memory.list_activities(50)})
            elif path == "/api/robot/events":
                self._send_json({"events": self.assistant.memory.list_robot_events(50)})
            elif path == "/api/calendar/upcoming":
                query = parse_qs(parsed.query)
                raw_days = (query.get("days") or [""])[0]
                try:
                    days = int(raw_days) if raw_days else 7
                except ValueError:
                    days = 7
                # Il limite superiore è applicato anche da collect_upcoming:
                # nessun parametro della UI può ampliare la finestra oltre 14 giorni.
                self._send_json(self.assistant.upcoming_events(days=max(1, min(days, 14))))
            else:
                self._send_json({"error": "endpoint non trovato"}, 404)
        except AmyError as exc:
            self._send_json({"error": exc.message, "code": exc.code}, 500)
        except Exception as exc:  # noqa: BLE001
            _log.exception("Errore GET %s", path)
            self._send_json({"error": "errore interno", "detail": str(exc)[:300]}, 500)

    # ------------------------------------------------------------------- POST
    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            body = self._read_body()
            if path == "/api/chat":
                message = str(body.get("message", "")).strip()
                if not message:
                    self._send_json({"error": "Messaggio vuoto."}, 400)
                    return
                session_id = body.get("session_id") or self.assistant.resume_session()
                with self.server.chat_lock:  # type: ignore[attr-defined]
                    result = self.assistant.handle(message, session_id=session_id)
                self._send_json(result.to_dict())
            elif path == "/api/new_session":
                title = str(body.get("title", "Dashboard")).strip() or "Dashboard"
                session_id = self.assistant.new_session(title[:200])
                self._send_json({"session_id": session_id})
            elif path == "/api/confirm":
                pending_id = str(body.get("pending_id", ""))
                approved = bool(body.get("approved", False))
                if not pending_id:
                    self._send_json({"error": "pending_id mancante."}, 400)
                    return
                with self.server.chat_lock:  # type: ignore[attr-defined]
                    result = self.assistant.resolve_confirmation(pending_id, approved)
                self._send_json(result.to_dict())
            elif path == "/api/speak":
                text = str(body.get("text", "")).strip()
                if not text:
                    self._send_json({"error": "Testo mancante."}, 400)
                    return
                self._send_json(self.assistant.speak(text[:4000]))
            elif path == "/api/voice/stop":
                self.assistant.voice.stop_speaking()
                self._send_json({"stopped": True})
            elif path == "/api/voice/greet":
                self._send_json(self.assistant.voice.greet())
            elif path == "/api/voice/listen":
                seconds = float(body.get("seconds", 5.0))
                with self.server.chat_lock:  # type: ignore[attr-defined]
                    text = self.assistant.voice.listen_once(seconds)
                self._send_json({"text": text})
            elif path == "/api/voice/wake/start":
                self._start_wake_loop()
            elif path == "/api/voice/wake/stop":
                self.assistant.voice.stop_wake_loop()
                self._send_json({"ok": True, "voice": self.assistant.voice.status()})
            elif path == "/api/robot/estop":
                reason = str(body.get("reason", "dashboard"))
                data = self.assistant.robot_link.estop(reason)
                self.assistant.memory.record_robot_event("estop", data)
                self.assistant.audit.record("estop_from_ui", reason=reason)
                self._send_json({"ok": True, "result": data})
            elif path == "/api/robot/stop":
                data = self.assistant.robot_link.stop(str(body.get("reason", "dashboard")))
                self.assistant.memory.record_robot_event("stop", data)
                self._send_json({"ok": True, "result": data})
            elif path in {"/api/permissions/revoke", "/api/permissions/restore"}:
                capability = str(body.get("capability", "")).strip()
                if not capability:
                    self._send_json({"error": "Capacità mancante."}, 400)
                    return
                if path.endswith("/revoke"):
                    snapshot = self.assistant.authorization.revoke(capability)
                else:
                    snapshot = self.assistant.authorization.restore(capability)
                self._send_json({"ok": True, "permissions": snapshot})
            elif path.startswith("/api/modules/") and path.endswith("/enabled"):
                name = path[len("/api/modules/"):-len("/enabled")].strip("/")
                if "enabled" not in body:
                    self._send_json({"error": "Campo enabled mancante."}, 400)
                    return
                enabled = body.get("enabled")
                if not isinstance(enabled, bool):
                    self._send_json({"error": "enabled deve essere true o false."}, 400)
                    return
                result = self.assistant.set_module_enabled(name, enabled)
                self._send_json({"ok": True, "result": result})
            else:
                self._send_json({"error": "endpoint non trovato"}, 404)
        except json.JSONDecodeError:
            self._send_json({"error": "JSON non valido."}, 400)
        except AmyError as exc:
            self._send_json({"error": exc.message, "code": exc.code, "detail": exc.detail}, 400)
        except Exception as exc:  # noqa: BLE001
            _log.exception("Errore POST %s", path)
            self._send_json({"error": "errore interno", "detail": str(exc)[:300]}, 500)


class AmyHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, assistant: Assistant) -> None:
        self.assistant = assistant
        self.chat_lock = threading.Lock()
        super().__init__(address, AmyHandler)

    def handle_voice_command(self, text: str) -> None:
        """Esegue un comando dettato e pronuncia la risposta.

        Il servizio vocale lo chiama in un thread dedicato: qui si può restare
        sincroni senza bloccare l'ascolto del barge-in.
        """
        voice = self.assistant.voice
        voice.begin_processing()
        try:
            with self.chat_lock:
                result = self.assistant.handle(text, session_id=self.assistant.resume_session())
        except Exception:  # noqa: BLE001
            _log.exception("Comando vocale non riuscito")
            voice.state.set(VoiceState.ERROR, "comando vocale non riuscito")
            return
        reply = str(getattr(result, "reply", "") or "").strip()
        pending = getattr(result, "pending", None)
        if pending is not None:
            question = reply or "Confermi l'operazione?"
            voice.state.set(VoiceState.WAITING_FOR_CONFIRMATION, "conferma richiesta")
            try:
                voice.speak(question, block=False)
                voice.await_confirmation(
                    lambda answer: self._resolve_voice_confirmation(answer, pending.pending_id),
                    timeout_s=30.0,
                )
            except Exception:  # noqa: BLE001
                _log.warning("Conferma vocale non avviata", exc_info=True)
            return
        if reply:
            try:
                voice.speak(reply, block=False)
                voice.begin_speaking()
            except Exception:  # noqa: BLE001
                _log.warning("Sintesi della risposta vocale non riuscita")
                voice.begin_conversation("risposta senza sintesi")
        else:
            voice.begin_conversation("risposta vuota")

    @staticmethod
    def _voice_answer(text: str) -> Optional[bool]:
        """Interpreta un sì/no italiano; None se la risposta non è chiara."""
        words = normalize(text).split()
        if not words:
            return None
        yes = {
            "si", "s", "certo", "confermo", "conferma", "ok", "okay",
            "procedi", "vai", "fallo", "autorizzo", "approvo", "accetto",
        }
        no = {
            "no", "n", "annulla", "annullare", "lascia", "stare", "stop",
            "rifiuto", "nega", "cancel", "cancella",
        }
        if words[0] in yes:
            return True
        if words[0] in no:
            return False
        return None

    def _resolve_voice_confirmation(self, text: str, pending_id: str) -> bool:
        """Risolve una conferma con la risposta vocale; True se ha risposto."""
        answer = self._voice_answer(text)
        if answer is None:
            try:
                self.assistant.voice.speak("Rispondi sì oppure no.", block=False)
            except Exception:  # noqa: BLE001
                pass
            return False
        voice = self.assistant.voice
        voice.begin_processing()
        try:
            resolved = self.assistant.resolve_confirmation(pending_id, answer)
            message = str(getattr(resolved, "reply", "") or "").strip()
        except Exception:  # noqa: BLE001
            message = "La conferma non è più valida."
        if not message:
            message = "Fatto." if answer else "Operazione annullata."
        try:
            voice.speak(message, block=False)
            voice.begin_speaking()
        except Exception:  # noqa: BLE001
            _log.warning("Sintesi della conferma non riuscita")
            voice.begin_conversation("conferma senza sintesi")
        return True

    def start_wake_loop_on_launch(self) -> bool:
        """Avvia l'ascolto continuo se la configurazione lo richiede."""
        voice = self.assistant.voice
        if not bool(voice.config.get("voice.wake_word.enabled", False)):
            return False
        if not bool(voice.config.get("voice.wake_word.start_on_launch", False)):
            return False
        status = voice.status()
        if not bool(status.get("wake_word", {}).get("available", False)):
            _log.info("Ascolto continuo non avviato: microfono o STT non disponibili.")
            return False
        try:
            voice.start_wake_loop(self.handle_voice_command)
            _log.info("Ascolto continuo avviato automaticamente all'avvio.")
            return True
        except Exception:  # noqa: BLE001
            _log.warning("Avvio automatico dell'ascolto continuo non riuscito", exc_info=True)
            return False


def _is_loopback(host: str) -> bool:
    """True solo per indirizzi di loopback o per il nome ``localhost``."""
    if host in {"localhost", "::1"}:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _parent_alive(parent_pid: int) -> bool:
    """True se il processo padre esiste ancora."""
    try:
        os.kill(parent_pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


def _stop_dashboard(server: AmyHTTPServer, message: str) -> None:
    """Chiude il server e lascia una traccia, senza fallire se stdout è rotto.

    Quando l'app nativa termina, la pipe su stdout del backend si chiude: una
    ``print`` su quel canale solleverebbe BrokenPipeError. Per questo la
    chiusura parte prima del messaggio e il messaggio è protetto.
    """
    threading.Thread(target=server.shutdown, daemon=True).start()
    try:
        print(message)
    except Exception:  # pragma: no cover - stdout già chiuso
        pass


def _watch_heartbeat(
    server: AmyHTTPServer,
    path: str,
    max_age_s: float = 20.0,
    interval_s: float = 3.0,
) -> None:
    """Chiude il server se il heartbeat del genitore non viene più aggiornato.

    Il file viene scritto periodicamente dall'app nativa. Se sparisce o
    invecchia, il backend deduce che il genitore è morto e si chiude: evita
    processi orfano dopo un crash o un SIGKILL.

    La tolleranza è ampia (20 s) perché il file viene aggiornato ogni 2 s ma
    l'app può essere momentaneamente bloccata (per esempio un alert modale o
    un carico CPU alto durante una trascrizione vocale). Un backend lento non
    deve essere scambiato per un backend morto.
    """
    parent_pid = os.environ.get("AMY_PARENT_PID", "").strip()
    while True:
        time.sleep(interval_s)
        try:
            age = time.time() - os.path.getmtime(path)
        except OSError:
            if parent_pid.isdigit() and _parent_alive(int(parent_pid)):
                _log.warning("Heartbeat assente ma il genitore è vivo: continuo.")
                continue
            _stop_dashboard(server, "Heartbeat del genitore assente: chiudo la dashboard.")
            return
        if age > max_age_s:
            # App Nap può sospendere il timer dell'app quando è in secondo
            # piano: il file resta fermo ma il processo è vivo. In quel caso
            # chiudere il backend è un falso positivo (osservato il 3 novembre
            # 2026, con riavvii ogni minuto). Il PID del genitore è la prova
            # decisiva; il file serve solo quando il PID non è disponibile.
            if parent_pid.isdigit() and _parent_alive(int(parent_pid)):
                _log.debug(
                    "Heartbeat in ritardo (%.1f s) ma il genitore %s è vivo: continuo.",
                    age,
                    parent_pid,
                )
                continue
            _stop_dashboard(
                server,
                "Heartbeat del genitore scaduto: chiudo la dashboard. "
                "(file %s, età %.1f s, tolleranza %.0f s)" % (path, age, max_age_s),
            )
            return


def _watch_parent(server: AmyHTTPServer, parent_pid: int) -> None:
    """Chiude il server se il processo padre scompare.

    Serve all'app nativa Amy Core: chiudendo la finestra, il backend non deve
    restare vivo come processo orfano. È attivo solo quando il genitore
    imposta ``AMY_WATCH_STDIN=1`` (pipe su stdin: EOF = genitore morto) o
    ``AMY_PARENT_PID`` (controllo periodico del pid). La CLI normale non
    imposta nessuna delle due e resta invariata.
    """
    watch_stdin = os.environ.get("AMY_WATCH_STDIN", "") == "1"
    while True:
        if watch_stdin:
            # La pipe su stdin resta aperta finché il genitore vive: EOF
            # significa che il genitore è morto (anche se il pid è zombia).
            try:
                data = os.read(0, 1)
            except OSError:
                data = b""
            if not data:
                _stop_dashboard(server, "Genitore terminato: chiudo la dashboard.")
                return
            continue
        time.sleep(3.0)
        if not _parent_alive(parent_pid):
            _stop_dashboard(server, "Processo padre terminato: chiudo la dashboard.")
            return


def _warm_mail(config: Any) -> None:
    """Apre Mail in background per non far attendere il primo comando.

    Il primo AppleScript su Mail può richiedere decine di secondi (avvio e
    indicizzazione). Gli account vengono messi in cache; nessun messaggio
    viene letto.
    """
    if not bool(config.get("mail.warm_on_start", True)):
        return
    # Il primo AppleScript può andare in timeout mentre Mail si avvia: un
    # secondo tentativo dopo 30 secondi evita che il primo comando dell'utente
    # paghi l'attesa.
    for attempt in (1, 2):
        try:
            accounts = list_accounts(force=attempt > 1)
            _log.info("Mail pronta: %d account disponibili", len(accounts))
            return
        except Exception as exc:  # noqa: BLE001 - il riscaldamento è best-effort
            if attempt == 1:
                _log.info("Mail non ancora pronta: %s. Riprovo tra 30 s.", exc)
                time.sleep(30)
            else:
                _log.info("Mail non riscaldata: %s", exc)


def _schedule_greeting(assistant: Assistant, delay: float = 1.2) -> None:
    """Pronuncia il messaggio di avvio dopo che la dashboard è pronta.

    Usa solo la sintesi locale: nessuna registrazione, nessun ascolto in
    background. Se la voce è disabilitata o non disponibile, non succede
    nulla e Amy non finge di aver parlato.

    ``AMY_STARTUP_GREETING=0`` disattiva il saluto (usato dai test
    automatici per non emettere audio).
    """
    flag = os.environ.get("AMY_STARTUP_GREETING", "").strip().lower()
    if flag in {"0", "false", "no", "off"}:
        _log.info("Messaggio di avvio disattivato da AMY_STARTUP_GREETING")
        return

    def _run() -> None:
        time.sleep(max(0.0, delay))
        try:
            result = assistant.voice.greet()
        except Exception:  # noqa: BLE001 - difensivo: l'avvio non deve fallire
            _log.warning("Messaggio di avvio non riuscito", exc_info=True)
            return
        if result.get("spoken"):
            _log.info("Amy: %s", result.get("text", ""))
        else:
            _log.info("Messaggio di avvio non pronunciato: %s", result.get("reason", ""))

    threading.Thread(target=_run, name="amy-greeting", daemon=True).start()


def run_server(config: Config, *, host: Optional[str] = None, port: Optional[int] = None, open_browser: bool = False) -> None:
    setup_logging(
        level=str(config.get("logging.level", "INFO")),
        log_file=str(config.get("logging.file")),
    )
    listen_host = host or str(config.get("ui.host", "127.0.0.1"))
    listen_port = int(port if port is not None else config.get("ui.port", 8765))
    if not _is_loopback(listen_host) and not bool(config.get("ui.allow_remote", False)):
        raise ConfigError(
            "La dashboard può ascoltare solo su localhost.",
            detail=(
                "%s non è un indirizzo di loopback. La dashboard non ha autenticazione: "
                "imposta ui.allow_remote=true solo se sai cosa stai esponendo." % listen_host
            ),
        )
    if not _is_loopback(listen_host):
        print("ATTENZIONE: dashboard esposta su %s senza autenticazione." % listen_host)
    assistant = Assistant(config)
    assistant.voice.warm()  # modello STT e voci pronti, nessuna registrazione
    threading.Thread(target=_warm_mail, args=(config,), name="amy-mail-warm", daemon=True).start()
    server = AmyHTTPServer((listen_host, listen_port), assistant)
    url = "http://%s:%d" % (listen_host, listen_port)
    print("Dashboard Amy: %s" % url)
    print("Premi Ctrl-C per terminare.")
    if open_browser or config.get("ui.open_browser", False):
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    _schedule_greeting(assistant)
    server.start_wake_loop_on_launch()
    parent_pid = os.environ.get("AMY_PARENT_PID", "").strip()
    watch_stdin = os.environ.get("AMY_WATCH_STDIN", "") == "1"
    heartbeat = os.environ.get("AMY_HEARTBEAT_FILE", "").strip()
    if heartbeat:
        _log.info("Watchdog del genitore attivo sul file %s", heartbeat)
        threading.Thread(
            target=_watch_heartbeat,
            args=(server, heartbeat),
            daemon=True,
        ).start()
    elif watch_stdin or parent_pid.isdigit():
        pid = int(parent_pid) if parent_pid.isdigit() else os.getpid()
        threading.Thread(
            target=_watch_parent,
            args=(server, pid),
            daemon=True,
        ).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard terminata.")
    finally:
        server.server_close()
        assistant.close()
