"""Interfaccia a riga di comando di Amy."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import platform
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import __version__
from .ai.factory import build_primary
from .ai.offline import OfflineProvider
from .ai.presets import PRESETS, get_preset
from .core.assistant import Assistant, TurnResult
from .core.config import Config, amy_home, default_config_path, init_config, is_local_endpoint, load_secrets
from .core.errors import AmyError, ConfigError
from .core.logging_setup import setup_logging
from .robot.links import build_robot_link
from .robot.protocol import JOINT_NAMES, LEG_JOINTS
from .security.policy import ConfirmationRequest
from .security.risk import RiskLevel
from .voice.service import VoiceService


# --------------------------------------------------------------------- utilità
def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _print_json(value: Any) -> None:
    print(_json(value))


def _load_config() -> Config:
    path = default_config_path()
    if not path.exists():
        init_config(path=path)
        print("Configurazione iniziale creata in %s" % path)
    config = Config.load(path)
    config.ensure_dirs()
    setup_logging(
        level=str(config.get("logging.level", "INFO")),
        log_file=str(config.get("logging.file")),
        max_bytes=int(config.get("logging.max_bytes", 2000000)),
        backup_count=int(config.get("logging.backup_count", 3)),
    )
    return config


def _build_assistant(config: Config, *, offline: bool = False) -> Assistant:
    provider = OfflineProvider() if offline else None
    return Assistant(config, provider=provider)


def _risk_badge(risk: str) -> str:
    return {"A": "A · ordinaria", "B": "B · impatto significativo", "C": "C · sensibile/irreversibile"}.get(risk, risk)


def _ask_confirmation(request: ConfirmationRequest) -> bool:
    print()
    print("=" * 72)
    print("CONFERMA RICHIESTA — rischio %s" % _risk_badge(request.risk.value))
    print("Operazione: %s" % request.tool)
    print("Motivo: %s" % request.reason)
    print("Parametri:")
    print(_json(request.args))
    if request.consequences:
        print("Conseguenze: %s" % request.consequences)
    if request.undo:
        print("Annullamento: %s" % request.undo)
    print("=" * 72)
    if not sys.stdin.isatty():
        print("Nessun terminale interattivo: operazione NON autorizzata.")
        return False
    if request.risk == RiskLevel.C:
        answer = input("Scrivi CONFERMO per autorizzare, qualunque altra risposta annulla: ").strip()
        return answer.upper() == "CONFERMO"
    answer = input("Autorizzi l'operazione? [s/N] ").strip().lower()
    return answer in {"s", "si", "sì", "y", "yes"}


def _handle_pending(assistant: Assistant, result: TurnResult, *, speak: bool = False) -> TurnResult:
    if not result.pending:
        return result
    approved = _ask_confirmation(result.pending)
    resolved = assistant.resolve_confirmation(result.pending.pending_id, approved)
    if resolved.reply:
        print("Amy › %s" % resolved.reply)
        if speak:
            assistant.speak(resolved.reply)
    return resolved


def _print_turn(result: TurnResult, *, speak: bool, assistant: Assistant) -> None:
    if result.reply:
        print("Amy › %s" % result.reply)
        if speak:
            try:
                assistant.speak(result.reply)
            except AmyError as exc:
                print("(voce non disponibile: %s)" % exc.message)
    if result.fallback_reason:
        print("(nota: provider primario non disponibile — %s)" % result.fallback_reason)


# --------------------------------------------------------------------- comandi
def cmd_init(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser() if args.path else default_config_path()
    created = init_config(force=args.force, path=path)
    print("Configurazione: %s" % created)
    print("Cartella dati: %s" % amy_home())
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    config = _load_config()
    checks: List[Dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str = "", level: str = "ATTENZIONE") -> None:
        checks.append({"name": name, "ok": ok, "detail": detail, "level": level})

    add("Python", sys.version_info >= (3, 9), platform.python_version())
    add("macOS", platform.system() == "Darwin", platform.mac_ver()[0])
    add("Architettura", True, platform.machine())
    add("Configurazione", config.path.exists(), str(config.path))
    try:
        config.ensure_dirs()
        add("Cartelle dati", True, str(amy_home()))
    except OSError as exc:
        add("Cartelle dati", False, str(exc), "ERRORE")

    roots = config.allowed_roots()
    missing = [str(root) for root in roots if not root.exists()]
    add("Radici autorizzate", not missing, ", ".join(str(r) for r in roots) + (" — mancanti: " + ", ".join(missing) if missing else ""))

    try:
        secrets = load_secrets()
        add("File segreti", True, "presente, permessi corretti" if secrets else "non presente (facoltativo)")
    except ConfigError as exc:
        add("File segreti", False, exc.message + " " + exc.detail, "ATTENZIONE")

    # Provider.
    assistant_for_provider = _build_assistant(config)
    try:
        provider_status = assistant_for_provider.provider_status(cache_s=0)
    finally:
        assistant_for_provider.close()
    provider_available = bool(provider_status.get("available"))
    model_installed = provider_status.get("model_installed")
    provider_ok = provider_available and model_installed is not False
    provider_detail = "%s · %s" % (provider_status.get("provider"), provider_status.get("model"))
    if provider_available and model_installed is False:
        provider_detail += " (modello non installato)"
    add(
        "Motore IA",
        provider_ok,
        provider_detail,
        "OK" if provider_ok else "ATTENZIONE",
    )

    provider_name = str(config.get("ai.provider", "ollama")).lower()
    preset = get_preset(provider_name)
    if preset is not None:
        add(
            "Servizio IA",
            True,
            "%s · piano gratuito verificato il %s" % (preset.label, preset.verified_on),
            "OK",
        )
        try:
            probe = build_primary(config).check_remote()  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001
            probe = {"key_valid": False, "detail": str(exc)}
        key_env = str(config.get("ai.online.api_key_env", "") or preset.api_key_env)
        if probe.get("key_valid"):
            add("Chiave API", True, "%s valida" % key_env, "OK")
            if probe.get("model_available") is False:
                add(
                    "Modello online",
                    False,
                    "%s non è nell'elenco del servizio" % provider_status.get("model"),
                    "ATTENZIONE",
                )
            else:
                add("Modello online", True, str(provider_status.get("model")), "OK")
        else:
            add(
                "Chiave API",
                False,
                "%s assente o non valida: %s" % (key_env, probe.get("detail", "")),
                "ATTENZIONE",
            )
        add(
            "Costi IA",
            True,
            "%s · %s" % (preset.free_terms, preset.limits),
            "OK",
        )
    elif provider_name in {"ollama", "offline"}:
        add("Costi IA", True, "provider locale o offline, nessun costo previsto", "OK")
    else:
        base_url = str(config.get("ai.openai.base_url", ""))
        if is_local_endpoint(base_url):
            add("Costi IA", True, "endpoint locale: %s" % base_url, "OK")
        else:
            add(
                "Costi IA",
                False,
                "endpoint remoto autorizzato: verifica che sia gratuito (%s)" % base_url,
                "ATTENZIONE",
            )

    # Voce.
    voice = VoiceService(config)
    voice_status = voice.status()
    add("TTS macOS", bool(voice_status["tts"].get("available")), "voci italiane: %s" % ", ".join(voice_status["tts"].get("italian_voices", [])[:5]))
    if voice_status["tts"].get("available"):
        try:
            with tempfile.TemporaryDirectory(prefix="amy-doctor-") as tmp:
                target = voice.tts.to_file("Verifica voce di Amy.", Path(tmp) / "test.aiff")
                add("TTS test su file", target.exists(), "%d byte" % target.stat().st_size)
        except Exception as exc:  # noqa: BLE001
            add("TTS test su file", False, str(exc), "ATTENZIONE")
    add("STT", bool(voice_status["stt"].get("available")), "%s · %s" % (voice_status["stt"].get("engine"), voice_status["stt"].get("model", "")))
    add("Registratore audio", bool(voice_status["recorder"].get("available")), "%s" % voice_status["recorder"].get("engine"))

    # AppleScript di sola lettura.
    try:
        from .macos import application_is_running

        running = application_is_running("Finder")
        add("AppleScript", True, "Finder in esecuzione: %s" % running)
    except Exception as exc:  # noqa: BLE001
        add("AppleScript", False, str(exc), "ATTENZIONE")

    # Robot.
    try:
        link = build_robot_link(config)
        status = link.status()
        reachable = status.get("reachable", True) and status.get("connected", True)
        add("Robot", bool(reachable), "trasporto %s" % config.get("robot.transport"), "OK" if reachable else "ATTENZIONE")
        link.close()
    except Exception as exc:  # noqa: BLE001
        add("Robot", False, str(exc), "ATTENZIONE")

    try:
        import paho.mqtt  # noqa: F401

        add("paho-mqtt", True, "disponibile per il trasporto MQTT")
    except ImportError:
        add("paho-mqtt", False, "non installato (serve solo per MQTT)", "ATTENZIONE")

    print("Amy — verifica dell'ambiente\n")
    for check in checks:
        mark = "OK " if check["ok"] else check.get("level", "ATTENZIONE")
        print("[%-10s] %-24s %s" % (mark, check["name"], check["detail"]))
    critical = [c for c in checks if not c["ok"] and c.get("level") == "ERRORE"]
    print()
    if critical:
        print("Problemi critici: %d. Correggili prima di usare Amy." % len(critical))
        return 1
    print("Amy può funzionare. Le voci mancanti sono opzionali o richiedono configurazione.")
    return 0


def cmd_tools(args: argparse.Namespace) -> int:
    config = _load_config()
    assistant = _build_assistant(config, offline=True)
    rows = assistant.registry.catalog()
    for item in rows:
        print("%-22s [%s] %s" % (item["name"], item["risk"], item["description"]))
    print("\nTotale: %d strumenti." % len(rows))
    assistant.close()
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    config = _load_config()
    if args.action == "path":
        print(config.path)
    else:
        _print_json(config.redacted())
    return 0


def cmd_providers(args: argparse.Namespace) -> int:
    """Elenca i provider online gratuiti verificati, senza segreti."""
    print("Provider IA online gratuiti verificati\n")
    for preset in PRESETS.values():
        print("%s — %s" % (preset.id, preset.label))
        print("  endpoint : %s" % preset.base_url)
        print("  modello  : %s" % preset.model)
        print("  chiave   : %s (da %s)" % (preset.api_key_env, preset.signup_url))
        print("  licenza  : %s" % preset.model_license)
        print("  limiti   : %s" % preset.limits)
        print("  privacy  : %s" % preset.privacy)
        print("  verificato il %s" % preset.verified_on)
        print()
    print("Per attivarlo, nella configurazione personale:")
    print('  ai.provider = "groq"')
    print("  ai.online.consent = true")
    print("  ai.fallback_provider = \"offline\"")
    print("Poi salva la chiave con: python3 -m amy secret set GROQ_API_KEY")
    return 0


def cmd_secret(args: argparse.Namespace) -> int:
    """Legge o scrive i segreti locali, senza mai stamparli."""
    path = amy_home() / "secrets.json"
    if args.action == "list":
        if not path.exists():
            print("Nessun segreto configurato (%s non esiste)." % path)
            return 0
        names = sorted(load_secrets(path))
        if not names:
            print("Nessun segreto configurato.")
            return 0
        for name in names:
            print(name)
        return 0

    name = str(args.name or "").strip()
    if not re.match(r"^[A-Z][A-Z0-9_]*$", name):
        print("Nome non valido: usa lettere maiuscole, numeri e underscore (es. GROQ_API_KEY).")
        return 2
    try:
        value = getpass.getpass("Valore per %s (non verrà mostrato): " % name).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return 1
    if not value:
        print("Valore vuoto: nessuna modifica.")
        return 1

    data: Dict[str, str] = {}
    if path.exists():
        # Un file esistente con permessi aperti bloccherebbe la lettura: li
        # correggiamo prima di leggerlo.
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        data = load_secrets(path)
    data[name] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    print("Segreto %s salvato in %s (permessi 600)." % (name, path))
    return 0


def cmd_chat(args: argparse.Namespace) -> int:
    config = _load_config()
    assistant = _build_assistant(config, offline=args.offline)
    speak = bool(args.voice or config.get("voice.enabled"))
    session_id = None
    if getattr(args, "new", False):
        session_id = assistant.new_session("Conversazione")
    else:
        session_id = assistant.resume_session()
    provider = assistant.provider_status(cache_s=0)
    print("Amy — assistente personale · sessione %s" % session_id)
    print(
        "Motore: %s (%s)%s"
        % (
            provider.get("provider"),
            provider.get("model"),
            " — OFFLINE" if args.offline else "",
        )
    )
    print("Scrivi /aiuto per i comandi, /esci per terminare.")
    print()
    try:
        while True:
            try:
                line = input("Tu › ").strip()
            except EOFError:
                print()
                break
            if not line:
                continue
            if line.startswith("/"):
                should_exit, session_id, speak = _slash_command(line, assistant, session_id, speak)
                if should_exit:
                    break
                continue
            try:
                result = assistant.handle(line, session_id=session_id)
            except KeyboardInterrupt:
                print("\n(richiesta interrotta)")
                continue
            _print_turn(result, speak=speak, assistant=assistant)
            if result.pending:
                _handle_pending(assistant, result, speak=speak)
    except KeyboardInterrupt:
        print("\nArrivederci.")
    finally:
        assistant.close()
    return 0


def _slash_command(line: str, assistant: Assistant, session_id: str, speak: bool) -> tuple:
    """Gestisce un comando ``/`` e restituisce (esci, sessione, voce)."""
    command = line.split()[0].lower()
    if command in {"/esci", "/quit", "/exit"}:
        print("Arrivederci.")
        return True, session_id, speak
    if command in {"/aiuto", "/help"}:
        print(
            "Comandi: /strumenti /stato /memoria /robot /nuova /voce on|off /conferme /esci\n"
            "Puoi anche scrivere richieste in linguaggio naturale."
        )
        return False, session_id, speak
    if command == "/strumenti":
        for item in assistant.registry.catalog():
            print("%-22s [%s] %s" % (item["name"], item["risk"], item["description"]))
        return False, session_id, speak
    if command == "/stato":
        status = assistant.status()
        print(
            "Sessione: %s\nMotore: %s (%s)\nMemoria: %s messaggi, %s fatti\nRobot: %s\nVoce: %s\nConferme in attesa: %s"
            % (
                session_id,
                status["provider"].get("provider"),
                status["provider"].get("model"),
                status["memory"].get("messages"),
                status["memory"].get("facts"),
                status["robot"].get("transport", status["robot"].get("mode", "?")),
                "pronta" if status["voice"].get("ready_for_voice_commands") else "parziale",
                status["pending_confirmations"],
            )
        )
        return False, session_id, speak
    if command == "/memoria":
        facts = assistant.memory.list_facts(50)
        if not facts:
            print("La memoria è vuota.")
        for fact in facts:
            print("- %s = %s" % (fact["key"], fact["value"]))
        return False, session_id, speak
    if command == "/robot":
        _print_json(assistant.robot_status())
        return False, session_id, speak
    if command == "/nuova":
        session_id = assistant.new_session("Conversazione")
        print("Nuova sessione: %s" % session_id)
        return False, session_id, speak
    if command == "/conferme":
        pending = assistant.pending_confirmations()
        if not pending:
            print("Nessuna conferma in attesa.")
        for item in pending:
            print("- %s: %s (%s)" % (item["pending_id"], item["tool"], item["reason"]))
        return False, session_id, speak
    if command == "/voce":
        parts = line.split()
        if len(parts) > 1 and parts[1].lower() in {"on", "off"}:
            enabled = parts[1].lower() == "on"
            assistant.config.data["voice"]["enabled"] = enabled
            speak = enabled
            print("Voce %s." % ("attiva" if enabled else "disattivata"))
        else:
            print("Uso: /voce on|off")
        return False, session_id, speak
    print("Comando sconosciuto. Scrivi /aiuto.")
    return False, session_id, speak


def cmd_ask(args: argparse.Namespace) -> int:
    config = _load_config()
    assistant = _build_assistant(config, offline=args.offline)
    speak = bool(args.voice or config.get("voice.enabled"))
    try:
        result = assistant.handle(args.text, session_id=args.session)
        _print_turn(result, speak=speak, assistant=assistant)
        if result.pending:
            if not sys.stdin.isatty():
                print(
                    "\nConferma necessaria ma nessun terminale interattivo. "
                    "Usa 'amy chat' oppure la dashboard per autorizzare.",
                    file=sys.stderr,
                )
                return 2
            _handle_pending(assistant, result, speak=speak)
        return 0 if result.status != "error" else 1
    finally:
        assistant.close()


def cmd_memory(args: argparse.Namespace) -> int:
    config = _load_config()
    assistant = _build_assistant(config, offline=True)
    try:
        if args.action == "list":
            facts = assistant.memory.list_facts(args.limit)
            if not facts:
                print("La memoria è vuota.")
            for fact in facts:
                print("%s = %s  (aggiornato: %s)" % (fact["key"], fact["value"], fact["updated_at"]))
        elif args.action == "set":
            assistant.memory.set_fact(args.key, args.value)
            print("Memorizzato: %s" % args.key)
        elif args.action == "forget":
            removed = assistant.memory.delete_fact(args.key)
            print("Rimosso." if removed else "Chiave non trovata.")
        elif args.action == "export":
            data = assistant.memory.export_all()
            if args.file:
                path = Path(args.file).expanduser()
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(_json(data) + "\n", encoding="utf-8")
                os.chmod(path, 0o600)
                print("Esportato in %s" % path)
            else:
                _print_json(data)
        elif args.action == "sessions":
            for session in assistant.memory.list_sessions(args.limit):
                print(
                    "%s  %s  (%d messaggi)  %s"
                    % (
                        session["id"],
                        session["updated_at"],
                        assistant.memory.message_count(session["id"]),
                        session.get("title") or "senza titolo",
                    )
                )
        else:
            print("Azione non riconosciuta.", file=sys.stderr)
            return 2
        return 0
    finally:
        assistant.close()


def cmd_robot(args: argparse.Namespace) -> int:
    config = _load_config()
    link = build_robot_link(config)
    try:
        if args.action == "status":
            _print_json(link.status())
        elif args.action == "ping":
            _print_json(link.ping())
        elif args.action == "estop":
            _print_json(link.estop(args.reason or "operatore"))
        elif args.action == "stop":
            _print_json(link.stop(args.reason or "operatore"))
        elif args.action == "reset":
            if not args.confirm:
                print("Il reset dell'E-stop è di livello C. Usa --confirm dopo aver verificato l'area.")
                return 2
            _print_json(link.reset_estop(operator_ack=True))
        elif args.action == "mode":
            mode = args.mode
            if mode not in {"test", "idle", "ready"}:
                print("Modalità ammessa: test, idle, ready.", file=sys.stderr)
                return 2
            if not args.confirm:
                print("Cambio modalità (livello B): usa --confirm per procedere.")
                return 2
            _print_json(link.set_mode(mode))
        elif args.action == "move":
            status = link.status()
            limits = {item["joint"]: item for item in status.get("limits", [])}
            joints = []
            for raw in args.joints:
                if "=" not in raw:
                    print("Formato giunto non valido: %s (atteso nome=gradi)." % raw, file=sys.stderr)
                    return 2
                name, value = raw.split("=", 1)
                name = name.strip()
                if name not in JOINT_NAMES:
                    print("Giunto sconosciuto: %s" % name, file=sys.stderr)
                    return 2
                try:
                    angle = float(value)
                except ValueError:
                    print("Angolo non valido per %s: %s" % (name, value), file=sys.stderr)
                    return 2
                limit = limits.get(name)
                if limit and (angle < limit["min_deg"] or angle > limit["max_deg"]):
                    print(
                        "Fuori limite: %s=%.1f (ammesso %.1f..%.1f)."
                        % (name, angle, limit["min_deg"], limit["max_deg"]),
                        file=sys.stderr,
                    )
                    return 2
                joints.append({"joint": name, "position_deg": angle})
            if not joints:
                print("Nessun giunto specificato.", file=sys.stderr)
                return 2
            head_only = all(item["joint"] in {"head_pan", "head_tilt"} for item in joints)
            leg_only = all(item["joint"] in LEG_JOINTS for item in joints)
            if not head_only and not leg_only:
                print("Non mescolare giunti della testa e delle gambe nello stesso comando.", file=sys.stderr)
                return 2
            print("Stato attuale:")
            _print_json(status)
            print("\nRichiesta di movimento %s:" % ("testa" if head_only else "gambe"))
            print(_json({"joints": joints, "speed_limit_dps": args.speed, "deadline_ms": args.deadline}))
            if not args.confirm:
                answer = input("Scrivi CONFERMO per autorizzare il movimento: ").strip().upper()
                if answer != "CONFERMO":
                    print("Movimento annullato.")
                    return 2
            _print_json(
                link.move(
                    joints,
                    speed_limit_dps=args.speed,
                    deadline_ms=args.deadline,
                    head=head_only,
                )
            )
        else:
            print("Azione robot non riconosciuta.", file=sys.stderr)
            return 2
        return 0
    except AmyError as exc:
        print("Errore: %s" % exc.message)
        if exc.detail:
            print(exc.detail)
        return 1
    finally:
        link.close()


def cmd_voice(args: argparse.Namespace) -> int:
    config = _load_config()
    voice = VoiceService(config)
    try:
        if args.action == "status":
            _print_json(voice.status())
        elif args.action == "speak":
            if not args.text:
                print("Testo mancante.", file=sys.stderr)
                return 2
            print(_json(voice.speak(" ".join(args.text), block=True)))
        elif args.action == "listen":
            text = voice.listen_once(args.seconds)
            print(text or "(nessun parlato rilevato)")
        elif args.action == "ask":
            text = voice.listen_once(args.seconds)
            print("Tu (voce) › %s" % text)
            assistant = _build_assistant(config, offline=args.offline)
            try:
                result = assistant.handle(text)
                _print_turn(result, speak=True, assistant=assistant)
                if result.pending:
                    print("Serve una conferma: usa 'amy chat' per autorizzare l'operazione.")
            finally:
                assistant.close()
        elif args.action == "loop":
            print("Ascolto continuo della wake word. Ctrl-C per terminare.")

            def on_command(text: str) -> None:
                print("Tu (voce) › %s" % text)
                if not args.execute:
                    print("(comando trascritto; usa --execute per eseguirlo)")
                    return
                assistant = _build_assistant(config, offline=args.offline)
                try:
                    result = assistant.handle(text)
                    print("Amy › %s" % result.reply)
                    if result.pending:
                        print("Conferma necessaria: usa 'amy chat' per autorizzare.")
                    else:
                        assistant.speak(result.reply)
                finally:
                    assistant.close()

            try:
                voice.run_wake_loop(on_command)
            except KeyboardInterrupt:
                print("\nAscolto terminato.")
        else:
            print("Azione voce non riconosciuta.", file=sys.stderr)
            return 2
        return 0
    except AmyError as exc:
        print("Errore voce: %s" % exc.message)
        if exc.detail:
            print(exc.detail)
        return 1
    finally:
        voice.stop_speaking()


def cmd_serve(args: argparse.Namespace) -> int:
    config = _load_config()
    from .ui.server import run_server

    run_server(config, host=args.host, port=args.port, open_browser=args.open_browser)
    return 0


# ----------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="amy", description="Amy — assistente personale per macOS e robotica")
    parser.add_argument("--version", action="version", version="Amy %s" % __version__)
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="crea la configurazione iniziale")
    p_init.add_argument("--force", action="store_true", help="sovrascrive la configurazione esistente")
    p_init.add_argument("--path", help="percorso alternativo della configurazione")
    p_init.set_defaults(func=cmd_init)

    p_doctor = sub.add_parser("doctor", help="verifica ambiente, voce, IA e robot")
    p_doctor.set_defaults(func=cmd_doctor)

    p_tools = sub.add_parser("tools", help="elenca gli strumenti disponibili")
    p_tools.set_defaults(func=cmd_tools)

    p_config = sub.add_parser("config", help="mostra la configurazione")
    p_config.add_argument("action", choices=["show", "path"], nargs="?", default="show")
    p_config.set_defaults(func=cmd_config)

    p_providers = sub.add_parser("providers", help="elenca i provider IA online gratuiti verificati")
    p_providers.set_defaults(func=cmd_providers)

    p_secret = sub.add_parser("secret", help="gestisci i segreti locali (mai stampati)")
    secret_sub = p_secret.add_subparsers(dest="action")
    secret_set = secret_sub.add_parser("set")
    secret_set.add_argument("name")
    secret_sub.add_parser("list")
    p_secret.set_defaults(func=cmd_secret, action="list")

    p_chat = sub.add_parser("chat", help="avvia la conversazione interattiva")
    p_chat.add_argument("--offline", action="store_true", help="usa solo l'interprete locale")
    p_chat.add_argument("--voice", action="store_true", help="pronuncia le risposte")
    p_chat.add_argument("--new", action="store_true", help="inizia una nuova sessione")
    p_chat.set_defaults(func=cmd_chat)

    p_ask = sub.add_parser("ask", help="invia una singola richiesta")
    p_ask.add_argument("text", help="richiesta in linguaggio naturale")
    p_ask.add_argument("--offline", action="store_true")
    p_ask.add_argument("--voice", action="store_true")
    p_ask.add_argument("--session", help="identificatore sessione esistente")
    p_ask.set_defaults(func=cmd_ask)

    p_mem = sub.add_parser("memory", help="gestisci la memoria locale")
    mem_sub = p_mem.add_subparsers(dest="action")
    mem_list = mem_sub.add_parser("list")
    mem_list.add_argument("--limit", type=int, default=100)
    mem_set = mem_sub.add_parser("set")
    mem_set.add_argument("key")
    mem_set.add_argument("value")
    mem_forget = mem_sub.add_parser("forget")
    mem_forget.add_argument("key")
    mem_export = mem_sub.add_parser("export")
    mem_export.add_argument("--file")
    mem_sessions = mem_sub.add_parser("sessions")
    mem_sessions.add_argument("--limit", type=int, default=20)
    p_mem.set_defaults(func=cmd_memory, action="list")

    p_robot = sub.add_parser("robot", help="stato e comandi del robot")
    robot_sub = p_robot.add_subparsers(dest="action")
    rs = robot_sub.add_parser("status")
    rp = robot_sub.add_parser("ping")
    re = robot_sub.add_parser("estop")
    re.add_argument("--reason")
    rst = robot_sub.add_parser("stop")
    rst.add_argument("--reason")
    rr = robot_sub.add_parser("reset")
    rr.add_argument("--confirm", action="store_true")
    rm = robot_sub.add_parser("mode")
    rm.add_argument("mode", choices=["test", "idle", "ready"])
    rm.add_argument("--confirm", action="store_true")
    rmv = robot_sub.add_parser("move")
    rmv.add_argument("joints", nargs="+", help="nome=gradi, per esempio head_pan=10")
    rmv.add_argument("--speed", type=float, default=15.0)
    rmv.add_argument("--deadline", type=int, default=3000)
    rmv.add_argument("--confirm", action="store_true", help="salta il prompt (la conferma resta esplicita)")
    p_robot.set_defaults(func=cmd_robot, action="status")

    p_voice = sub.add_parser("voice", help="strumenti vocali")
    voice_sub = p_voice.add_subparsers(dest="action")
    voice_sub.add_parser("status")
    vs = voice_sub.add_parser("speak")
    vs.add_argument("text", nargs="+")
    vl = voice_sub.add_parser("listen")
    vl.add_argument("--seconds", type=float, default=5.0)
    va = voice_sub.add_parser("ask")
    va.add_argument("--seconds", type=float, default=5.0)
    va.add_argument("--offline", action="store_true")
    vloop = voice_sub.add_parser("loop")
    vloop.add_argument("--execute", action="store_true", help="esegue i comandi riconosciuti")
    vloop.add_argument("--offline", action="store_true")
    p_voice.set_defaults(func=cmd_voice, action="status")

    p_serve = sub.add_parser("serve", help="avvia la dashboard web locale")
    p_serve.add_argument("--host", default=None)
    p_serve.add_argument("--port", type=int, default=None)
    p_serve.add_argument("--open-browser", action="store_true")
    p_serve.set_defaults(func=cmd_serve)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    # Sotto-comandi senza azione esplicita: default sicuri.
    if getattr(args, "action", None) is None and args.command in {"memory", "robot", "voice"}:
        setattr(args, "action", "list" if args.command == "memory" else "status")
    try:
        return int(args.func(args))
    except ConfigError as exc:
        print("Configurazione non valida: %s" % exc.message, file=sys.stderr)
        if exc.detail:
            print(exc.detail, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrotto.", file=sys.stderr)
        return 130
    except AmyError as exc:
        print("Errore: %s" % exc.message, file=sys.stderr)
        if exc.detail:
            print(exc.detail, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
