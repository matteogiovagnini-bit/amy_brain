"""Collegamento Telegram per Amy.

Solo Bot API ufficiale, in long polling: nessuna porta aperta, nessun webhook.
Il servizio è opzionale e spento per default. Accetta solo chat private di
utenti in allowlist, non gruppi o canali.

La voce è supportata come **nota vocale**: il file viene scaricato, trascritto
in locale con il motore STT di Amy e passato all'assistente come testo. Le
risposte vocali sono opzionali e usano ``say`` + ``afconvert`` in locale.
"""

from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Set
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from ..core.config import get_secret
from ..core.errors import AmyError
from ..core.logging_setup import get_logger

_log = get_logger("telegram")

MAX_TELEGRAM_MESSAGE = 4096
DEFAULT_MAX_VOICE_BYTES = 20 * 1024 * 1024


class TelegramError(AmyError):
    code = "telegram_error"


class TelegramAPI:
    """Client minimale della Bot API, basato sulla libreria standard."""

    def __init__(self, token: str, *, timeout: float = 30.0) -> None:
        self._token = str(token)
        self._base = "https://api.telegram.org/bot%s" % self._token
        self.timeout = timeout

    def _redact(self, value: Any) -> str:
        text = str(value or "")
        return text.replace(self._token, "[REDATTO]")[:500]

    def _call(self, method: str, payload: Dict[str, Any], *, timeout: Optional[float] = None) -> Any:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            "%s/%s" % (self._base, method),
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout or self.timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                detail = ""
            raise TelegramError(
                "Telegram ha rifiutato la richiesta.",
                detail=self._redact(detail),
            ) from exc
        except (URLError, OSError, TimeoutError) as exc:
            raise TelegramError(
                "Telegram non è raggiungibile.",
                detail=self._redact(exc),
            ) from exc
        try:
            result = json.loads(body)
        except ValueError as exc:
            raise TelegramError("Risposta Telegram non valida.", detail=self._redact(body)) from exc
        if not isinstance(result, dict) or not result.get("ok"):
            description = result.get("description") if isinstance(result, dict) else body
            raise TelegramError(
                "Telegram ha rifiutato la richiesta.",
                detail=self._redact(description),
            )
        return result.get("result")

    def get_me(self) -> Dict[str, Any]:
        return self._call("getMe", {})

    def get_updates(self, offset: int, *, timeout: int = 25) -> List[Dict[str, Any]]:
        result = self._call(
            "getUpdates",
            {
                "offset": int(offset),
                "timeout": int(timeout),
                "allowed_updates": ["message", "callback_query"],
            },
            timeout=float(timeout) + 15.0,
        )
        return result if isinstance(result, list) else []

    def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> Any:
        payload: Dict[str, Any] = {
            "chat_id": int(chat_id),
            "text": str(text)[:MAX_TELEGRAM_MESSAGE],
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        return self._call("sendMessage", payload)

    def answer_callback_query(self, callback_id: str, text: str = "") -> Any:
        return self._call(
            "answerCallbackQuery",
            {"callback_query_id": str(callback_id), "text": str(text)[:200]},
        )

    def get_file(self, file_id: str) -> Dict[str, Any]:
        return self._call("getFile", {"file_id": str(file_id)})

    def download_file(self, file_path: str, destination: Path, *, max_bytes: int) -> Path:
        url = "https://api.telegram.org/file/bot%s/%s" % (self._token, quote(str(file_path)))
        destination.parent.mkdir(parents=True, exist_ok=True)
        total = 0
        try:
            with urlopen(url, timeout=self.timeout) as response, destination.open("wb") as handle:
                while True:
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise TelegramError(
                            "Il file Telegram supera il limite configurato.",
                            detail="%d byte > %d byte" % (total, max_bytes),
                        )
                    handle.write(chunk)
        except HTTPError as exc:
            raise TelegramError("Download del file Telegram non riuscito.", detail=self._redact(exc)) from exc
        except (URLError, OSError, TimeoutError) as exc:
            raise TelegramError("Download del file Telegram non riuscito.", detail=self._redact(exc)) from exc
        return destination

    def _post_file(
        self,
        method: str,
        chat_id: int,
        file_field: str,
        file_path: Path,
        mime: str,
        *,
        caption: str = "",
        label: str = "file",
    ) -> Any:
        boundary = "amy" + uuid.uuid4().hex
        fields = {
            "chat_id": str(int(chat_id)),
            "caption": str(caption)[:1024],
        }
        body = bytearray()
        for name, value in fields.items():
            body.extend(("--%s\r\n" % boundary).encode())
            body.extend(('Content-Disposition: form-data; name="%s"\r\n\r\n' % name).encode())
            body.extend(str(value).encode("utf-8"))
            body.extend(b"\r\n")
        body.extend(("--%s\r\n" % boundary).encode())
        body.extend(
            (
                'Content-Disposition: form-data; name="%s"; filename="%s"\r\n'
                "Content-Type: %s\r\n\r\n" % (file_field, file_path.name, mime)
            ).encode()
        )
        body.extend(file_path.read_bytes())
        body.extend(b"\r\n")
        body.extend(("--%s--\r\n" % boundary).encode())
        request = Request(
            "%s/%s" % (self._base, method),
            data=bytes(body),
            headers={"Content-Type": "multipart/form-data; boundary=%s" % boundary},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8", errors="replace"))
        except (HTTPError, URLError, OSError, ValueError) as exc:
            raise TelegramError(
                "Invio del %s non riuscito." % label,
                detail=self._redact(exc),
            ) from exc
        if not isinstance(result, dict) or not result.get("ok"):
            raise TelegramError("Telegram ha rifiutato il %s." % label)
        return result.get("result")

    def send_audio(self, chat_id: int, audio_path: Path, caption: str = "") -> Any:
        return self._post_file(
            "sendAudio",
            chat_id,
            "audio",
            audio_path,
            "audio/mp4",
            caption=caption,
            label="nota vocale",
        )

    def send_photo(self, chat_id: int, photo_path: Path, caption: str = "") -> Any:
        return self._post_file(
            "sendPhoto",
            chat_id,
            "photo",
            photo_path,
            "image/jpeg",
            caption=caption,
            label="foto",
        )


class TelegramService:
    """Servizio long polling con allowlist, sessioni e conferme."""

    def __init__(
        self,
        config: Any,
        *,
        handler: Callable[..., Any],
        resolver: Callable[[str, bool], Any],
        voice: Any = None,
        new_session: Optional[Callable[[str], str]] = None,
        memory: Any = None,
        sessions_path: Optional[Path] = None,
        api: Optional[TelegramAPI] = None,
    ) -> None:
        self.config = config
        self.handler = handler
        self.resolver = resolver
        self.voice = voice
        self._new_session = new_session
        self.memory = memory
        self.api = api
        self._sessions_path = (
            Path(sessions_path).expanduser()
            if sessions_path
            else self._default_sessions_path()
        )
        self._sessions = self._load_sessions()
        self._allowed_ids: Set[int] = set()
        self._voice_chats: Set[int] = set()
        self._pending_chat: Dict[str, int] = {}
        self._chat_pending: Dict[int, str] = {}
        self._queue: "queue.Queue[Optional[Dict[str, Any]]]" = queue.Queue()
        self._stop = threading.Event()
        self._poll_thread: Optional[threading.Thread] = None
        self._worker_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._state = "disabled"
        self._error = ""
        self._username = ""
        self._last_update = 0.0
        self._started_at = 0.0

    def _default_sessions_path(self) -> Path:
        db = Path(str(self.config.get("memory.db_path", "~/.amy/amy.db"))).expanduser()
        return db.parent / "telegram_sessions.json"

    # --------------------------------------------------------------- stato
    def enabled(self) -> bool:
        return bool(self.config.get("telegram.enabled", False))

    def status(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled(),
            "state": self._state,
            "running": bool(self._poll_thread and self._poll_thread.is_alive()),
            "connected": bool(self._username),
            "username": self._username,
            "allowed_users": len(self._allowed_ids),
            "voice_replies": bool(self.config.get("telegram.voice_replies", False)),
            "error": self._error,
            "last_update": self._last_update,
        }

    def _set_state(self, state: str, error: str = "") -> None:
        self._state = state
        self._error = error

    # -------------------------------------------------------- ciclo di vita
    def start(self) -> Dict[str, Any]:
        if not self.enabled():
            self._set_state("disabled", "Telegram disattivato nella configurazione.")
            return self.status()
        if self._poll_thread and self._poll_thread.is_alive():
            return self.status()
        token_name = str(self.config.get("telegram.token_env", "AMY_TELEGRAM_TOKEN"))
        try:
            token = get_secret(token_name)
        except Exception as exc:  # noqa: BLE001 - configurazione da dichiarare, non crash
            self._set_state("error", "Impossibile leggere il token Telegram: %s" % getattr(exc, "message", str(exc))[:200])
            return self.status()
        if not token:
            self._set_state("error", "Token Telegram non configurato (%s)." % token_name)
            return self.status()
        ids = self.config.get("telegram.allowed_user_ids", []) or []
        allowed: Set[int] = set()
        for value in ids if isinstance(ids, list) else []:
            try:
                allowed.add(int(value))
            except (TypeError, ValueError):
                continue
        if not allowed:
            self._set_state("error", "Allowlist Telegram vuota: configura telegram.allowed_user_ids.")
            return self.status()
        self._allowed_ids = allowed
        if self.api is None:
            self.api = TelegramAPI(token)
        self._stop.clear()
        self._started_at = time.time()
        self._set_state("starting")
        self._worker_thread = threading.Thread(
            target=self._worker_loop, name="amy-telegram-worker", daemon=True
        )
        self._poll_thread = threading.Thread(
            target=self._poll_loop, name="amy-telegram-poll", daemon=True
        )
        self._worker_thread.start()
        self._poll_thread.start()
        _log.info("Telegram in avvio: %d utenti autorizzati", len(allowed))
        return self.status()

    def stop(self) -> None:
        self._stop.set()
        self._queue.put(None)
        for thread in (self._poll_thread, self._worker_thread):
            if thread and thread.is_alive():
                thread.join(timeout=2.0)
        self._poll_thread = None
        self._worker_thread = None
        if self._state != "disabled":
            self._set_state("stopped", "")

    # ------------------------------------------------------------- polling
    def _poll_loop(self) -> None:
        offset = 0
        backoff = 1.0
        while not self._stop.is_set():
            try:
                if not self._username:
                    me = self.api.get_me() if self.api else {}
                    self._username = str((me or {}).get("username", ""))
                    if self._username:
                        _log.info("Telegram collegato come @%s", self._username)
                updates = self.api.get_updates(offset) if self.api else []
                backoff = 1.0
                self._set_state("running")
                for update in updates:
                    update_id = int(update.get("update_id", 0) or 0)
                    if update_id:
                        offset = max(offset, update_id + 1)
                    self._last_update = time.time()
                    self._queue.put(update)
            except TelegramError as exc:
                self._set_state("error", exc.message)
                _log.warning("Telegram: %s", exc.message)
                self._stop.wait(backoff)
                backoff = min(backoff * 2, 30.0)
            except Exception as exc:  # noqa: BLE001 - il loop non deve morire
                self._set_state("error", "Errore interno del collegamento Telegram.")
                _log.exception("Errore imprevisto nel polling Telegram")
                self._stop.wait(backoff)
                backoff = min(backoff * 2, 30.0)

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            update = self._queue.get()
            if update is None:
                break
            try:
                self._handle_update(update)
            except Exception:  # noqa: BLE001
                _log.exception("Errore nella gestione di un aggiornamento Telegram")

    # ------------------------------------------------------------- update
    def _handle_update(self, update: Dict[str, Any]) -> None:
        if "message" in update:
            self._handle_message(update["message"])
        elif "callback_query" in update:
            self._handle_callback(update["callback_query"])

    def _user_allowed(self, user_id: Any) -> bool:
        try:
            return int(user_id) in self._allowed_ids
        except (TypeError, ValueError):
            return False

    def _handle_message(self, message: Dict[str, Any]) -> None:
        chat = message.get("chat") or {}
        if chat.get("type") != "private":
            return
        sender = message.get("from") or {}
        user_id = sender.get("id")
        chat_id = chat.get("id")
        if chat_id is None:
            return
        try:
            chat_id = int(chat_id)
        except (TypeError, ValueError):
            return
        if not self._user_allowed(user_id):
            _log.warning("Telegram: messaggio ignorato da utente non autorizzato %s", user_id)
            return
        self._last_update = time.time()
        text = message.get("text") or message.get("caption") or ""
        if text:
            self._handle_text(chat_id, str(text))
            return
        voice = message.get("voice") or message.get("audio")
        if isinstance(voice, dict):
            self._handle_voice(chat_id, voice)
            return
        self._send(chat_id, "Posso leggere messaggi di testo e note vocali.")

    def _handle_text(self, chat_id: int, text: str) -> None:
        raw = text.strip()
        if raw.startswith("/"):
            command = raw.split()[0].split("@")[0].lower()
            if command == "/start":
                self._send(
                    chat_id,
                    "Ciao, sono Amy. Scrivimi un messaggio oppure invia una nota vocale. "
                    "Comandi: /help, /new, /status, /stop, /voce on|off.",
                )
                return
            if command == "/help":
                self._send(
                    chat_id,
                    "Posso chattare e ascoltare note vocali. Comandi:\\n"
                    "/new — nuova sessione\\n"
                    "/status — stato del collegamento\\n"
                    "/stop — interrompi la voce\\n"
                    "/voce on|off — risposte vocali in questa chat",
                )
                return
            if command == "/new":
                session = self._create_session(chat_id)
                self._send(chat_id, "Nuova sessione avviata: %s" % session[:8])
                return
            if command == "/status":
                data = self.status()
                self._send(
                    chat_id,
                    "Amy è collegata come @%s. Utenti autorizzati: %d. Voce: %s."
                    % (
                        data.get("username") or "—",
                        data.get("allowed_users", 0),
                        "attiva" if self._voice_replies(chat_id) else "solo testo",
                    ),
                )
                return
            if command == "/stop":
                try:
                    if self.voice is not None:
                        self.voice.stop_speaking()
                except Exception:  # noqa: BLE001
                    pass
                self._send(chat_id, "Voce interrotta.")
                return
            if command in {"/voce", "/voice"}:
                parts = raw.split()
                if len(parts) > 1 and parts[1].lower() in {"on", "si", "sì", "attiva"}:
                    self._voice_chats.add(chat_id)
                    self._send(chat_id, "Risposte vocali attive in questa chat.")
                elif len(parts) > 1 and parts[1].lower() in {"off", "no", "disattiva"}:
                    self._voice_chats.discard(chat_id)
                    self._send(chat_id, "Risposte vocali disattivate in questa chat.")
                else:
                    self._send(chat_id, "Uso: /voce on oppure /voce off.")
                return
            self._send(chat_id, "Comando non riconosciuto. Usa /help.")
            return
        if self._maybe_answer_pending(chat_id, raw):
            return
        self._ask(chat_id, raw)

    def _handle_voice(self, chat_id: int, voice: Dict[str, Any]) -> None:
        try:
            duration = int(voice.get("duration", 0) or 0)
        except (TypeError, ValueError):
            duration = 0
        maximum = int(self.config.get("telegram.max_voice_seconds", 120))
        if duration and duration > maximum:
            self._send(chat_id, "La nota vocale supera il limite di %d secondi." % maximum)
            return
        size = voice.get("file_size")
        max_bytes = int(self.config.get("telegram.max_voice_bytes", DEFAULT_MAX_VOICE_BYTES))
        if size and int(size) > max_bytes:
            self._send(chat_id, "La nota vocale supera il limite di %d MB." % (max_bytes // 1024 // 1024))
            return
        stt = getattr(self.voice, "stt", None) if self.voice is not None else None
        if stt is None or not getattr(stt, "available", False):
            self._send(chat_id, "Il riconoscimento vocale locale non è disponibile.")
            return
        file_id = str(voice.get("file_id", "") or "")
        if not file_id:
            self._send(chat_id, "Nota vocale non valida.")
            return
        self._send(chat_id, "Ricevuta. Sto trascrivendo la nota vocale…")
        path: Optional[Path] = None
        try:
            if self.api is None:
                raise TelegramError("Client Telegram non disponibile.")
            info = self.api.get_file(file_id) or {}
            remote = str(info.get("file_path", "") or "")
            if not remote:
                raise TelegramError("Telegram non ha restituito il file della nota vocale.")
            suffix = Path(remote).suffix or ".ogg"
            inbox = Path(str(self.config.get("memory.db_path", "~/.amy/amy.db"))).expanduser().parent / "telegram" / "inbox"
            inbox.mkdir(parents=True, exist_ok=True)
            path = inbox / (uuid.uuid4().hex + suffix)
            self.api.download_file(remote, path, max_bytes=max_bytes)
            text = self._transcribe(path)
        except TelegramError as exc:
            self._send(chat_id, exc.message)
            return
        except Exception as exc:  # noqa: BLE001
            _log.exception("Trascrizione Telegram non riuscita")
            self._send(chat_id, "Non sono riuscita a trascrivere la nota vocale.")
            return
        finally:
            if path is not None:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
        if not text:
            self._send(chat_id, "Non ho capito la nota vocale.")
            return
        if self._maybe_answer_pending(chat_id, text):
            return
        self._ask(chat_id, text)

    def _transcribe(self, path: Path) -> str:
        stt = getattr(self.voice, "stt", None) if self.voice is not None else None
        if stt is None:
            raise TelegramError("Motore STT non configurato.")
        try:
            return str(stt.transcribe(path)).strip()
        except Exception as first:  # noqa: BLE001 - tentiamo la conversione
            ffmpeg = shutil.which("ffmpeg")
            if not ffmpeg:
                raise TelegramError(
                    "Non riesco a decodificare la nota vocale. Installa ffmpeg per i file OGG/Opus.",
                    detail=str(first)[:300],
                ) from first
            wav = path.with_suffix(".wav")
            try:
                process = subprocess.run(
                    [ffmpeg, "-y", "-i", str(path), "-ar", "16000", "-ac", "1", str(wav)],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if process.returncode != 0:
                    raise TelegramError("Conversione della nota vocale non riuscita.")
                return str(stt.transcribe(wav)).strip()
            finally:
                try:
                    wav.unlink(missing_ok=True)
                except OSError:
                    pass

    def _ask(self, chat_id: int, text: str) -> None:
        maximum = int(self.config.get("telegram.max_message_chars", 3000))
        if len(text) > maximum:
            self._send(chat_id, "Il messaggio è troppo lungo (massimo %d caratteri)." % maximum)
            return
        session = self._session_for(chat_id)
        try:
            result = self.handler(text, session_id=session)
        except Exception:  # noqa: BLE001
            _log.exception("Richiesta Telegram non riuscita")
            self._send(chat_id, "Errore interno durante l'elaborazione della richiesta.")
            return
        reply = str(getattr(result, "reply", "") or "").strip()
        pending = getattr(result, "pending", None)
        if pending is not None:
            pending_id = str(getattr(pending, "pending_id", "") or "")
            if pending_id:
                self._remember_pending(chat_id, pending_id)
                self._send_confirmation(chat_id, pending, reply)
                return
        if reply:
            self._send(chat_id, reply)
            if self._voice_replies(chat_id):
                self._send_voice_reply(chat_id, reply)
        self._send_capture_photo(chat_id, result)

    def _send(self, chat_id: int, text: str) -> None:
        if self.api is None:
            return
        clean = str(text or "").strip()
        if not clean:
            return
        for chunk in self._chunks(clean):
            try:
                self.api.send_message(chat_id, chunk)
            except TelegramError as exc:
                self._set_state("error", exc.message)
                _log.warning("Invio Telegram non riuscito: %s", exc.message)
                return
            except Exception:  # noqa: BLE001
                _log.exception("Invio Telegram non riuscito")
                return

    @staticmethod
    def _chunks(text: str, limit: int = MAX_TELEGRAM_MESSAGE - 100) -> Iterable[str]:
        remaining = text
        while len(remaining) > limit:
            cut = remaining.rfind("\n", 0, limit)
            if cut < limit // 2:
                cut = limit
            yield remaining[:cut]
            remaining = remaining[cut:].lstrip()
        if remaining:
            yield remaining

    def _send_confirmation(self, chat_id: int, pending: Any, reply: str) -> None:
        pending_id = str(getattr(pending, "pending_id", "") or "")
        question = reply or "Confermi l'operazione?"
        tool = str(getattr(pending, "tool", "") or "")
        risk = getattr(getattr(pending, "risk", None), "value", "")
        text = question
        if tool:
            text += "\n\nStrumento: %s" % tool
        if risk:
            text += " · rischio %s" % risk
        text += "\n\nRispondi con i pulsanti oppure scrivi sì/no."
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "Autorizza", "callback_data": "yes:" + pending_id},
                    {"text": "Annulla", "callback_data": "no:" + pending_id},
                ]
            ]
        }
        if self.api is not None:
            try:
                self.api.send_message(chat_id, text[:MAX_TELEGRAM_MESSAGE], reply_markup=keyboard)
                return
            except TelegramError as exc:
                self._set_state("error", exc.message)
        self._send(chat_id, text)

    def _handle_callback(self, callback: Dict[str, Any]) -> None:
        sender = callback.get("from") or {}
        message = callback.get("message") or {}
        chat = message.get("chat") or {}
        if not self._user_allowed(sender.get("id")):
            return
        if chat.get("type") != "private":
            return
        try:
            chat_id = int(chat.get("id"))
        except (TypeError, ValueError):
            return
        data = str(callback.get("data", "") or "")
        action, _, pending_id = data.partition(":")
        if action not in {"yes", "no"} or not pending_id:
            return
        if self._pending_chat.get(pending_id) != chat_id:
            try:
                if self.api is not None:
                    self.api.answer_callback_query(str(callback.get("id", "")), "Richiesta non valida o scaduta.")
            except Exception:  # noqa: BLE001
                pass
            return
        self._resolve_pending(chat_id, pending_id, action == "yes")
        try:
            if self.api is not None:
                self.api.answer_callback_query(str(callback.get("id", "")), "Fatto.")
        except Exception:  # noqa: BLE001
            pass

    def _remember_pending(self, chat_id: int, pending_id: str) -> None:
        previous = self._chat_pending.get(chat_id)
        if previous:
            self._pending_chat.pop(previous, None)
        self._pending_chat[pending_id] = chat_id
        self._chat_pending[chat_id] = pending_id

    def _maybe_answer_pending(self, chat_id: int, text: str) -> bool:
        pending_id = self._chat_pending.get(chat_id)
        if not pending_id:
            return False
        words = re.findall(r"[\wàèéìòù]+", str(text).lower())
        if not words:
            return False
        yes = {"si", "sì", "s", "certo", "confermo", "ok", "okay", "procedi", "autorizza", "approva"}
        no = {"no", "n", "annulla", "cancella", "rifiuta", "stop"}
        if words[0] in yes:
            self._resolve_pending(chat_id, pending_id, True)
            return True
        if words[0] in no:
            self._resolve_pending(chat_id, pending_id, False)
            return True
        return False

    def _resolve_pending(self, chat_id: int, pending_id: str, approved: bool) -> None:
        try:
            result = self.resolver(pending_id, approved)
        except Exception:  # noqa: BLE001
            _log.exception("Conferma Telegram non riuscita")
            self._send(chat_id, "Non sono riuscita a risolvere la conferma.")
            return
        self._pending_chat.pop(pending_id, None)
        if self._chat_pending.get(chat_id) == pending_id:
            self._chat_pending.pop(chat_id, None)
        reply = str(getattr(result, "reply", "") or "").strip()
        if reply:
            self._send(chat_id, reply)
        self._send_capture_photo(chat_id, result)

    # ------------------------------------------------------------ sessione
    def _session_for(self, chat_id: int) -> str:
        key = str(chat_id)
        session = str(self._sessions.get(key, "") or "")
        if session and self.memory is not None:
            try:
                if not self.memory.get_session(session):
                    session = ""
            except Exception:  # noqa: BLE001
                pass
        if not session:
            session = self._create_session(chat_id)
        return session

    def _create_session(self, chat_id: int) -> str:
        session = ""
        if self._new_session is not None:
            session = str(self._new_session("Telegram") or "")
        if not session:
            session = "telegram-%s" % chat_id
        self._sessions[str(chat_id)] = session
        self._save_sessions()
        return session

    def _load_sessions(self) -> Dict[str, str]:
        try:
            data = json.loads(self._sessions_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {str(key): str(value) for key, value in data.items()}
        except (OSError, ValueError):
            pass
        return {}

    def _save_sessions(self) -> None:
        try:
            self._sessions_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._sessions_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._sessions, ensure_ascii=False, indent=2), encoding="utf-8")
            os.chmod(tmp, 0o600)
            tmp.replace(self._sessions_path)
        except OSError:
            _log.warning("Impossibile salvare le sessioni Telegram", exc_info=True)

    # --------------------------------------------------------------- voce
    def _voice_replies(self, chat_id: int) -> bool:
        if chat_id in self._voice_chats:
            return True
        return bool(self.config.get("telegram.voice_replies", False))

    def _send_capture_photo(self, chat_id: int, result: Any) -> None:
        """Se il turno ha scattato una foto, inviala come immagine Telegram."""
        tools = getattr(result, "tools_used", []) or []
        if "vision.capture" not in tools or self.api is None or self.memory is None:
            return
        session = str(getattr(result, "session_id", "") or "")
        try:
            activities = self.memory.list_activities(200)
        except Exception:  # noqa: BLE001 - la foto non deve rompere la risposta
            return
        root = (Path.home() / "Downloads" / "Amy" / "camera").resolve()
        for item in activities:
            if str(item.get("session_id", "")) != session:
                continue
            if item.get("tool") != "vision.capture" or item.get("status") != "ok":
                continue
            payload = item.get("result")
            data = payload.get("data") if isinstance(payload, dict) else {}
            image = str((data or {}).get("image", "") or "")
            if not image:
                continue
            path = Path(image).expanduser()
            try:
                resolved = path.resolve()
            except OSError:
                continue
            if root != resolved.parent and root not in resolved.parents:
                continue
            if not path.is_file():
                continue
            try:
                self.api.send_photo(chat_id, path, caption="Foto scattata da Amy.")
            except TelegramError as exc:
                _log.warning("Invio della foto Telegram non riuscito: %s", exc.message)
            return

    def _send_voice_reply(self, chat_id: int, text: str) -> None:
        say = shutil.which("say")
        afconvert = shutil.which("afconvert")
        if not say or not afconvert or self.api is None:
            return
        clean = " ".join(str(text).split())[:4000]
        if not clean:
            return
        voice = str(self.config.get("voice.tts.voice", "Alice"))
        rate = int(self.config.get("voice.tts.rate", 185))
        with tempfile.TemporaryDirectory(prefix="amy-telegram-voice-") as tmp:
            aiff = Path(tmp) / "reply.aiff"
            m4a = Path(tmp) / "reply.m4a"
            try:
                subprocess.run(
                    [say, "-v", voice, "-r", str(rate), "-o", str(aiff), clean],
                    capture_output=True,
                    timeout=90,
                )
                subprocess.run(
                    [afconvert, "-f", "m4af", "-d", "aac", "-b", "64000", str(aiff), str(m4a)],
                    capture_output=True,
                    timeout=90,
                )
                if m4a.is_file() and m4a.stat().st_size > 1000:
                    self.api.send_audio(chat_id, m4a, caption="Risposta vocale di Amy")
            except Exception:  # noqa: BLE001 - la risposta testuale è già stata inviata
                _log.warning("Invio della risposta vocale Telegram non riuscito", exc_info=True)
