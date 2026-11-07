"""Orchestrazione del turno conversazionale di Amy.

Il modello propone azioni strutturate; questo modulo:
- valida gli argomenti;
- applica la policy di rischio;
- sospende il turno quando serve una conferma;
- esegue lo strumento, registra l'attività e restituisce l'esito al modello;
- salva in memoria solo la conversazione utile, non i JSON interni.
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .. import __version__
from ..ai.base import AIProvider
from ..ai.factory import build_provider
from ..core.config import Config
from ..core.errors import AIError, AmyError, ToolError, ToolValidationError
from ..core.modules import ModuleError
from ..core.logging_setup import get_logger, redact
from ..core.prompts import build_system_prompt, format_tool_result
from ..core.system_info import collect_system_info
from ..memory.store import MemoryStore
from ..modules import build_module_registry
from ..modules.registry import DEFAULT_MODULES
from ..robot.links import RobotLink, build_robot_link
from ..security.audit import AuditLog
from ..security.authorization import AuthorizationBroker
from ..security.policy import ConfirmationRequest, PathGuard, PolicyEngine
from ..security.risk import RiskLevel
from ..shared.events import EventBus
from ..shared.module import ModuleContext
from ..tools.base import ToolContext, ToolResult
from ..tools.builtin import build_default_registry
from ..tools.calendar_tools import collect_upcoming
from ..tools.registry import ToolNotFoundError, ToolRegistry
from ..tools.schema import validate_arguments
from ..voice.service import VoiceService

_log = get_logger("core.assistant")


@dataclass
class TurnResult:
    reply: str
    status: str = "ok"
    session_id: str = ""
    pending: Optional[ConfirmationRequest] = None
    tools_used: List[str] = field(default_factory=list)
    fallback_reason: str = ""
    error_code: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reply": self.reply,
            "status": self.status,
            "session_id": self.session_id,
            "pending": self.pending.to_dict() if self.pending else None,
            "tools_used": self.tools_used,
            "fallback_reason": self.fallback_reason,
            "error_code": self.error_code,
        }


@dataclass
class ParsedResponse:
    text: str = ""
    action: Optional[Dict[str, Any]] = None
    malformed_action: bool = False


@dataclass
class _Turn:
    session_id: str
    messages: List[Dict[str, str]]
    tools_used: List[str] = field(default_factory=list)
    steps: int = 0
    created_at: float = field(default_factory=time.time)


@dataclass
class _Pending:
    turn: _Turn
    request: ConfirmationRequest
    action: Dict[str, Any]
    risk: RiskLevel
    created_at: float = field(default_factory=time.time)


def _extract_json_objects(text: str) -> List[Any]:
    results: List[Any] = []
    for match in re.finditer(r"```(?:json)?\s*(.*?)```", text, re.S | re.I):
        try:
            results.append(json.loads(match.group(1).strip()))
        except json.JSONDecodeError:
            continue
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            results.append(json.loads(stripped))
        except json.JSONDecodeError:
            pass
    # Primo oggetto bilanciato, per risposte con testo introduttivo.
    start = text.find("{")
    if start >= 0 and not results:
        depth = 0
        in_string = False
        escape = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
            else:
                if char == '"':
                    in_string = True
                elif char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            results.append(json.loads(text[start:index + 1]))
                        except json.JSONDecodeError:
                            pass
                        break
    return results


def parse_response(text: str) -> ParsedResponse:
    cleaned = (text or "").strip()
    if not cleaned:
        return ParsedResponse(text="")
    for candidate in _extract_json_objects(cleaned):
        if not isinstance(candidate, dict):
            continue
        action = candidate.get("action")
        if isinstance(action, dict):
            tool = action.get("tool") or action.get("name")
            args = action.get("args", {})
            if not isinstance(tool, str) or not tool:
                return ParsedResponse(malformed_action=True)
            if not isinstance(args, dict):
                return ParsedResponse(malformed_action=True)
            return ParsedResponse(text=str(candidate.get("say", "")), action={"tool": tool, "args": args})
        if isinstance(candidate.get("tool"), str):
            args = candidate.get("args", {})
            if not isinstance(args, dict):
                return ParsedResponse(malformed_action=True)
            return ParsedResponse(text=str(candidate.get("say", "")), action={"tool": candidate["tool"], "args": args})
        for key in ("say", "reply", "message", "text"):
            if isinstance(candidate.get(key), str):
                return ParsedResponse(text=candidate[key])
    if cleaned.startswith("{") and ("action" in cleaned or '"tool"' in cleaned):
        return ParsedResponse(malformed_action=True)
    return ParsedResponse(text=cleaned)


def _preview_args(args: Dict[str, Any], limit: int = 600) -> Dict[str, Any]:
    safe = redact(args)
    output: Dict[str, Any] = {}
    for key, value in safe.items():
        if isinstance(value, str) and len(value) > limit:
            output[key] = value[:limit] + "… [%d caratteri]" % len(value)
        elif isinstance(value, list):
            output[key] = value[:20]
        else:
            output[key] = value
    return output


def _dynamic_reason(tool: str, args: Dict[str, Any], fallback: str) -> str:
    if tool == "robot.move":
        joints = args.get("joints") or []
        desc = ", ".join(
            "%s=%.1f°" % (item.get("joint"), float(item.get("position_deg", 0)))
            for item in joints
            if isinstance(item, dict)
        )
        return "Muovere %d giunti: %s." % (len(joints), desc)
    if tool == "files.write":
        content = str(args.get("content", ""))
        return "Scrivere %s (%d caratteri)." % (args.get("path", "?"), len(content))
    if tool == "files.trash":
        return "Spostare nel cestino di Amy: %s." % args.get("path", "?")
    if tool == "files.move":
        return "Spostare %s in %s." % (args.get("source", "?"), args.get("destination", "?"))
    if tool == "apps.quit":
        return "Chiedere la chiusura di %s." % args.get("name", "?")
    if tool == "robot.reset_estop":
        return "Azzerare il latch dell'E-stop software."
    if tool == "robot.mode":
        return "Impostare la modalità robot su %s." % str(args.get("mode", "?")).upper()
    return fallback


class Assistant:
    def __init__(
        self,
        config: Config,
        *,
        provider: Optional[AIProvider] = None,
        memory: Optional[MemoryStore] = None,
        registry: Optional[ToolRegistry] = None,
        robot_link: Optional[RobotLink] = None,
        voice: Optional[VoiceService] = None,
        audit: Optional[AuditLog] = None,
        policy: Optional[PolicyEngine] = None,
        events: Optional[EventBus] = None,
    ) -> None:
        self.config = config
        self.memory = memory or MemoryStore(config.require_str("memory.db_path"))
        self.registry = registry or build_default_registry()
        self.audit = audit or AuditLog(config.require_str("security.audit_path"))
        self.policy = policy or PolicyEngine(
            auto_approve_levels=config.get("security.auto_approve_levels", ["A"]),
            auto_approve_tools=config.get("security.auto_approve_tools", []),
        )
        self.path_guard = PathGuard(
            config.allowed_roots(),
            max_file_bytes=int(config.get("security.max_file_bytes", 1048576)),
        )
        self.provider = provider or build_provider(config)
        self.robot_link = robot_link or build_robot_link(config)
        self.voice = voice or VoiceService(config)
        self.events = events or EventBus()
        self._module_context = ModuleContext(
            config=self.config,
            events=self.events,
            logger=_log,
            data_dir=None,
            path_guard=self.path_guard,
            audit=self.audit,
            memory=self.memory,
            providers=self.provider,
        )
        self.modules = build_module_registry(
            self.config,
            events=self.events,
            voice=self.voice,
            memory=self.memory,
            robot_link=self.robot_link,
            enabled={name: True for name in DEFAULT_MODULES},
        )
        self.modules.start_all(self._module_context)
        self.authorization = AuthorizationBroker(self.modules)
        self._pending: Dict[str, _Pending] = {}
        self._pending_lock = threading.RLock()
        self._provider_status_cache: Tuple[float, Dict[str, Any]] = (0.0, {})
        self._session_lock = threading.RLock()

    # ------------------------------------------------------------- sessioni
    def new_session(self, title: str = "") -> str:
        session_id = self.memory.create_session(title)
        self.audit.record("session_created", session_id=session_id)
        return session_id

    def resume_session(self) -> str:
        latest = self.memory.latest_session()
        return latest["id"] if latest else self.new_session()

    def transcript(self, session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        return self.memory.history(session_id, limit)

    # ------------------------------------------------------------- contesto
    def _facts(self) -> List[Dict[str, Any]]:
        limit = int(self.config.get("memory.max_facts_in_prompt", 40))
        facts = self.memory.list_facts(limit)
        # La memoria di progetto è utile quanto i fatti personali, ma resta
        # entro il budget: il prompt non deve crescere senza limite.
        try:
            for item in self.memory.list_memories(category="project", limit=limit):
                facts.append({"key": item["key"], "value": item["value"]})
        except Exception:  # noqa: BLE001 - la memoria non deve rompere il turno
            pass
        return facts[:limit]

    def _robot_context(self) -> str:
        transport = str(self.config.get("robot.transport", "simulated"))
        if transport == "simulated":
            return (
                "Trasporto: simulatore locale. Nessun attuatore fisico è collegato. "
                "I movimenti sono simulati e il campo simulated è true. "
                "La calibrazione meccanica reale non è disponibile."
            )
        return (
            "Trasporto: MQTT verso il robot. Lo stato non viene interrogato automaticamente "
            "in questo turno: usa robot.status per verificarlo."
        )

    def _build_messages(self, session_id: str, user_text: str) -> List[Dict[str, str]]:
        limit = int(self.config.get("memory.max_history_messages", 24))
        history = self.memory.history(session_id, limit)
        system = build_system_prompt(
            assistant_name=str(self.config.get("assistant.name", "Amy")),
            user_name=str(self.config.get("assistant.user_name", "")),
            tools_catalog=self.registry.catalog(),
            facts=self._facts(),
            robot_context=self._robot_context(),
        )
        messages = [{"role": "system", "content": system}]
        selected = []
        for item in reversed(history):
            if item["role"] not in {"user", "assistant"}:
                continue
            selected.append(item)
        selected.reverse()

        # Budget in caratteri: una singola risposta molto lunga (per esempio
        # l'elenco degli strumenti) non deve far superare il limite gratuito
        # di token al minuto. Si tengono i messaggi più recenti.
        budget = int(self.config.get("memory.max_history_chars", 4000))
        trimmed = []
        used = 0
        for item in reversed(selected):
            content = str(item["content"])
            remaining = budget - used
            if remaining <= 0:
                break
            if len(content) > remaining:
                content = content[:remaining] + "…"
            trimmed.append({"role": item["role"], "content": content})
            used += len(content)
        trimmed.reverse()
        messages.extend(trimmed)
        messages.append({"role": "user", "content": user_text})
        return messages

    # --------------------------------------------------------------- turno
    def handle(self, text: str, session_id: Optional[str] = None) -> TurnResult:
        user_text = (text or "").strip()
        if not user_text:
            return TurnResult(reply="Scrivi una richiesta.", status="error", error_code="empty_input")
        with self._session_lock:
            sid = session_id or self.resume_session()
            if not self.memory.get_session(sid):
                sid = self.new_session()
            self._cleanup_pending()
            messages = self._build_messages(sid, user_text)
            self.memory.add_message(sid, "user", user_text)
        turn = _Turn(session_id=sid, messages=messages)
        return self._run_turn(turn)

    def _run_turn(self, turn: _Turn) -> TurnResult:
        max_steps = int(self.config.get("ai.max_tool_steps", 4))
        while turn.steps < max_steps:
            turn.steps += 1
            try:
                raw = self.provider.chat(turn.messages)
            except AIError as exc:
                reply = "Non riesco a raggiungere il motore IA: %s" % exc.message
                self.memory.add_message(turn.session_id, "assistant", reply)
                self.audit.record("ai_error", session_id=turn.session_id, code=exc.code, detail=exc.detail)
                return TurnResult(
                    reply=reply,
                    status="error",
                    session_id=turn.session_id,
                    fallback_reason=getattr(self.provider, "last_fallback_reason", ""),
                    error_code=exc.code,
                )
            parsed = parse_response(raw)
            if parsed.malformed_action:
                reply = (
                    "Ho formulato un'azione non valida e non l'ho eseguita. "
                    "Riprova a riformulare la richiesta."
                )
                self.memory.add_message(turn.session_id, "assistant", reply)
                self.audit.record("invalid_action_format", session_id=turn.session_id)
                return TurnResult(reply=reply, status="error", session_id=turn.session_id, error_code="invalid_action")
            if not parsed.action:
                reply = parsed.text.strip() or "Fatto."
                self.memory.add_message(turn.session_id, "assistant", reply)
                return TurnResult(
                    reply=reply,
                    status="ok",
                    session_id=turn.session_id,
                    tools_used=turn.tools_used,
                    fallback_reason=getattr(self.provider, "last_fallback_reason", ""),
                )

            action = parsed.action
            tool_name = action["tool"]
            args = action["args"]
            preface = parsed.text.strip()

            # Validazione prima della conferma: non si chiede consenso per un comando malformato.
            try:
                tool = self.registry.get(tool_name)
                validate_arguments(tool.spec.parameters, args)
            except ToolNotFoundError:
                result = ToolResult.failure(
                    "Strumento non disponibile: %s" % tool_name,
                    error_code="tool_not_found",
                )
                self._record_rejected(turn, tool_name, args, "?", result)
                self._append_action(turn, raw, tool_name, result)
                continue
            except ToolValidationError as exc:
                result = ToolResult.failure(exc.message, error_code="tool_validation", data={"detail": exc.detail})
                self._record_rejected(turn, tool_name, args, tool.spec.risk.value, result)
                self._append_action(turn, raw, tool_name, result)
                continue

            risk = tool.risk_for(args)
            authorization = self.authorization.check(tool_name, risk)
            if not authorization.allowed:
                result = ToolResult.failure(
                    authorization.reason,
                    error_code="authorization_denied",
                )
                self._record_rejected(
                    turn,
                    tool_name,
                    args,
                    risk.value,
                    result,
                    module=authorization.module,
                    capability=authorization.capability,
                )
                self._append_action(turn, raw, tool_name, result)
                continue
            reason = _dynamic_reason(tool_name, args, tool.spec.reason)
            decision = self.policy.evaluate(
                tool_name,
                risk,
                reason=reason,
                consequences=tool.spec.consequences,
                undo=tool.spec.undo,
            )
            if decision.requires_confirmation:
                pending_id = "cfm_" + uuid.uuid4().hex[:16]
                request = ConfirmationRequest(
                    pending_id=pending_id,
                    tool=tool_name,
                    args=_preview_args(args),
                    risk=risk,
                    reason=reason,
                    consequences=decision.consequences,
                    undo=decision.undo,
                    session_id=turn.session_id,
                    created_at=time.time(),
                    extra={"preface": preface},
                )
                with self._pending_lock:
                    self._pending[pending_id] = _Pending(
                        turn=turn,
                        request=request,
                        action={"tool": tool_name, "args": args},
                        risk=risk,
                    )
                self.audit.record(
                    "confirmation_requested",
                    session_id=turn.session_id,
                    pending_id=pending_id,
                    tool=tool_name,
                    risk=risk.value,
                    module=authorization.module,
                    capability=authorization.capability,
                    args=_preview_args(args, 200),
                )
                return TurnResult(
                    reply=preface or "Serve una conferma per questa operazione.",
                    status="confirmation_required",
                    session_id=turn.session_id,
                    pending=request,
                    tools_used=turn.tools_used,
                )

            result = self._execute(turn, tool_name, args, risk, approved_by="policy")
            self._append_action(turn, raw, tool_name, result)

        reply = (
            "Ho raggiunto il limite di passaggi per questa richiesta e mi fermo qui. "
            "Dimmi come preferisci procedere."
        )
        self.memory.add_message(turn.session_id, "assistant", reply)
        return TurnResult(reply=reply, status="error", session_id=turn.session_id, error_code="tool_step_limit")

    def _record_rejected(
        self,
        turn: _Turn,
        tool_name: str,
        args: Dict[str, Any],
        risk: str,
        result: ToolResult,
        *,
        module: str = "",
        capability: str = "",
    ) -> None:
        """Registra un'azione scartata prima dell'esecuzione.

        Strumenti inesistenti e argomenti non validi non arrivano a
        ``_execute``: senza questo passaggio il tentativo non comparirebbe né
        nel registro attività né nell'audit. Il rischio ignoto è indicato con
        ``?``, mentre per gli errori di schema si usa il rischio dichiarato
        dallo strumento.
        """
        activity_id = self.memory.start_activity(
            session_id=turn.session_id,
            tool=tool_name,
            args=args,
            risk=risk,
        )
        self.memory.finish_activity(activity_id, status="errore", result=result.to_dict())
        self.audit.record(
            "tool_rejected",
            session_id=turn.session_id,
            tool=tool_name,
            risk=risk,
            module=module,
            capability=capability,
            error_code=result.error_code,
            args=_preview_args(args, 200),
        )

    def _append_action(self, turn: _Turn, raw: str, tool_name: str, result: ToolResult) -> None:
        turn.tools_used.append(tool_name)
        turn.messages.append({"role": "assistant", "content": raw})
        turn.messages.append(
            {
                "role": "user",
                "content": format_tool_result(tool_name, result.to_dict()),
            }
        )

    def _execute(
        self,
        turn: _Turn,
        tool_name: str,
        args: Dict[str, Any],
        risk: RiskLevel,
        *,
        approved_by: str,
    ) -> ToolResult:
        activity_id = self.memory.start_activity(
            session_id=turn.session_id,
            tool=tool_name,
            args=args,
            risk=risk.value,
        )
        authorization = self.authorization.describe(tool_name)
        self.audit.record(
            "tool_execution_started",
            session_id=turn.session_id,
            tool=tool_name,
            risk=risk.value,
            module=authorization.get("module", ""),
            capability=authorization.get("capability", ""),
            approved_by=approved_by,
            args=_preview_args(args, 200),
        )
        context = self.tool_context(session_id=turn.session_id)
        try:
            result = self.registry.execute(tool_name, args, context)
        except ToolError as exc:
            result = ToolResult.failure(exc.message, error_code=exc.code, data={"detail": exc.detail})
        except AmyError as exc:
            result = ToolResult.failure(exc.message, error_code=exc.code)
        except Exception as exc:  # noqa: BLE001
            _log.exception("Errore imprevisto nello strumento %s", tool_name)
            result = ToolResult.failure(
                "Errore imprevisto durante l'esecuzione.",
                error_code="internal_error",
                data={"detail": str(exc)[:300]},
            )
        self.memory.finish_activity(
            activity_id,
            status="ok" if result.ok else "errore",
            result=result.to_dict(),
        )
        self.audit.record(
            "tool_execution_finished",
            session_id=turn.session_id,
            tool=tool_name,
            ok=result.ok,
            error_code=result.error_code,
            duration_ms=result.duration_ms,
        )
        return result

    # ----------------------------------------------------------- conferme
    def resolve_confirmation(self, pending_id: str, approved: bool) -> TurnResult:
        with self._pending_lock:
            pending = self._pending.pop(pending_id, None)
        if not pending:
            return TurnResult(
                reply="La richiesta di conferma non esiste più o è scaduta.",
                status="error",
                error_code="pending_not_found",
            )
        ttl = float(self.config.get("security.confirmation_ttl_s", 300))
        if time.time() - pending.created_at > ttl:
            self.audit.record("confirmation_expired", pending_id=pending_id, tool=pending.request.tool)
            return TurnResult(
                reply="La richiesta di conferma è scaduta. Ripeti il comando.",
                status="error",
                session_id=pending.turn.session_id,
                error_code="pending_expired",
            )
        tool_name = pending.action["tool"]
        args = pending.action["args"]
        if approved:
            authorization = self.authorization.check(tool_name, pending.risk)
            if not authorization.allowed:
                result = ToolResult.failure(
                    authorization.reason,
                    error_code="authorization_denied",
                )
                self._record_rejected(
                    pending.turn,
                    tool_name,
                    args,
                    pending.risk.value,
                    result,
                    module=authorization.module,
                    capability=authorization.capability,
                )
                return TurnResult(
                    reply=authorization.reason,
                    status="error",
                    session_id=pending.turn.session_id,
                    error_code="authorization_denied",
                )
            self.audit.record(
                "confirmation_approved",
                session_id=pending.turn.session_id,
                pending_id=pending_id,
                tool=tool_name,
                risk=pending.risk.value,
            )
            result = self._execute(pending.turn, tool_name, args, pending.risk, approved_by="utente")
            raw_action = json.dumps({"tool": tool_name, "args": args}, ensure_ascii=False)
        else:
            result = ToolResult.failure(
                "L'utente ha annullato l'operazione.",
                error_code="user_denied",
            )
            raw_action = json.dumps({"tool": tool_name, "args": args}, ensure_ascii=False)
            self.audit.record(
                "confirmation_denied",
                session_id=pending.turn.session_id,
                pending_id=pending_id,
                tool=tool_name,
                risk=pending.risk.value,
            )
            activity_id = self.memory.start_activity(
                session_id=pending.turn.session_id,
                tool=tool_name,
                args=args,
                risk=pending.risk.value,
            )
            self.memory.finish_activity(activity_id, status="rifiutato", result=result.to_dict())
        self._append_action(pending.turn, raw_action, tool_name, result)
        return self._run_turn(pending.turn)

    def pending_confirmations(self) -> List[Dict[str, Any]]:
        self._cleanup_pending()
        with self._pending_lock:
            return [item.request.to_dict() for item in self._pending.values()]

    def _cleanup_pending(self) -> None:
        ttl = float(self.config.get("security.confirmation_ttl_s", 300))
        now = time.time()
        with self._pending_lock:
            expired = [key for key, item in self._pending.items() if now - item.created_at > ttl]
            for key in expired:
                self._pending.pop(key, None)

    # ------------------------------------------------------------- servizio
    def tool_context(self, *, session_id: str = "") -> ToolContext:
        """Dipendenze condivise passate a ogni strumento eseguito da Amy."""
        return ToolContext(
            config=self.config,
            memory=self.memory,
            path_guard=self.path_guard,
            audit=self.audit,
            session_id=session_id,
            robot_link=self.robot_link,
            voice=self.voice,
        )

    def upcoming_events(self, *, days: int = 7, limit: int = 8) -> Dict[str, Any]:
        """Prossimi appuntamenti per la dashboard, letti con ``calendar.events``.

        È una lettura di livello A richiesta dalla UI locale, non un'azione
        proposta dal modello: non modifica nulla e non richiede conferma.
        """
        return collect_upcoming(self.registry, self.tool_context(), days=days, limit=limit)

    def provider_status(self, *, cache_s: float = 30.0) -> Dict[str, Any]:
        now = time.monotonic()
        cached_at, cached = self._provider_status_cache
        if cached and now - cached_at < cache_s:
            return cached
        try:
            status = self.provider.status()
        except Exception as exc:  # noqa: BLE001
            status = {"provider": getattr(self.provider, "name", "?"), "available": False, "error": str(exc)}
        self._provider_status_cache = (now, status)
        return status

    def robot_status(self) -> Dict[str, Any]:
        try:
            return self.robot_link.status()
        except Exception as exc:  # noqa: BLE001
            return {"reachable": False, "error": str(exc), "transport": self.config.get("robot.transport")}

    def set_module_enabled(self, name: str, enabled: bool) -> Dict[str, Any]:
        """Abilita o disabilita un modulo e i suoi strumenti.

        Il modulo Memory è essenziale: non può essere disabilitato. Gli altri
        moduli possono essere spenti senza fermare il Core.
        """
        module = self.modules.get(name)
        if not enabled and not module.manifest.optional:
            raise ModuleError(
                "Il modulo %s è essenziale e non può essere disabilitato." % name
            )
        if enabled:
            status = self.modules.enable(name, self._module_context)
            for tool in module.tools():
                tool_name = getattr(getattr(tool, "spec", None), "name", "")
                if tool_name and not self.registry.has(tool_name):
                    self.registry.register(tool)
        else:
            tool_names = {
                getattr(getattr(tool, "spec", None), "name", "")
                for tool in module.tools()
            }
            with self._pending_lock:
                cancelled = [
                    pending_id
                    for pending_id, pending in self._pending.items()
                    if pending.request.tool in tool_names
                ]
                for pending_id in cancelled:
                    self._pending.pop(pending_id, None)
            if cancelled:
                self.audit.record(
                    "confirmations_cancelled",
                    detail="modulo %s disabilitato: %d conferme annullate"
                    % (name, len(cancelled)),
                )
            for tool_name in tool_names:
                if tool_name:
                    self.registry.unregister(tool_name)
            status = self.modules.disable(name)
        self.audit.record(
            "module_toggled",
            detail="%s=%s" % (name, "enabled" if enabled else "disabled"),
        )
        return {
            "name": name,
            "enabled": bool(enabled),
            "status": status.to_dict(),
            "tools": len(self.registry.names()),
        }

    def status(self) -> Dict[str, Any]:
        return {
            "assistant": {
                "name": self.config.get("assistant.name", "Amy"),
                "version": __version__,
                "session_id": self.resume_session(),
            },
            "provider": self.provider_status(),
            "system": collect_system_info(),
            "memory": self.memory.stats(),
            "voice": self.voice.status(),
            "robot": self.robot_status(),
            "tools": [
                {"name": item["name"], "risk": item["risk"], "description": item["description"]}
                for item in self.registry.catalog()
            ],
            "modules": self.modules.statuses(),
            "permissions": self.authorization.snapshot(),
            "pending_confirmations": len(self.pending_confirmations()),
            "facts": self.memory.list_facts(12),
            "activities": self.memory.list_activities(12),
            "robot_events": self.memory.list_robot_events(12),
            "config": {
                "ai_provider": self.config.get("ai.provider"),
                "ai_model": self.config.get("ai.model"),
                "robot_transport": self.config.get("robot.transport"),
                "voice_enabled": self.config.get("voice.enabled"),
                "allowed_roots": [str(root) for root in self.path_guard.roots],
                "config_path": str(self.config.path),
                "language": self.config.get("assistant.language"),
            },
        }

    def speak(self, text: str) -> Dict[str, Any]:
        if not str(text).strip():
            return {"spoken": False, "reason": "testo vuoto"}
        return self.voice.speak(text, block=False)

    def close(self) -> None:
        try:
            self.voice.stop_speaking()
        except Exception:
            pass
        try:
            self.robot_link.close()
        except Exception:
            pass
        try:
            self.events.close()
        except Exception:
            pass
        self.memory.close()
