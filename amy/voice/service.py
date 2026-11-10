"""Servizio vocale: TTS, STT, registrazione e ciclo wake word."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from ..core.errors import VoiceError
from ..core.logging_setup import get_logger
from .recorder import build_recorder
from .stt import FasterWhisperSTT, STT, build_stt
from .tts import MacSayTTS, NullTTS, TTS
from .state import VoiceState, VoiceStateMachine
from .wakeword import WakeWordDetector, normalize

_log = get_logger("voice")

DEFAULT_GREETING = "Amy è attiva e operativa."


class VoiceService:
    # Attesa massima per la fine della sintesi prima di registrare: se `say`
    # resta appeso, il ciclo non deve bloccarsi per sempre.
    ECHO_MAX_WAIT_S = 20.0

    def __init__(self, config) -> None:
        self.config = config
        self.enabled = bool(config.get("voice.enabled", False))
        engine = str(config.get("voice.tts.engine", "say")).lower()
        if engine == "say":
            self.tts: TTS = MacSayTTS(
                str(config.get("voice.tts.voice", "Alice")),
                int(config.get("voice.tts.rate", 185)),
            )
        else:
            self.tts = NullTTS()
        self.stt: STT = build_stt(config)
        # Modello leggero per il barge-in: deve trascrivere frammenti brevi
        # mentre Amy parla, quindi la latenza conta più della precisione.
        barge_model = str(config.get("voice.conversation.barge_in_model", "") or "").strip()
        if isinstance(self.stt, FasterWhisperSTT) and barge_model and barge_model != self.stt.model_name:
            self.barge_stt: STT = FasterWhisperSTT(
                barge_model,
                self.stt.language,
                self.stt.download_root,
                initial_prompt="Amy",
            )
        else:
            self.barge_stt = self.stt
        self.recorder = build_recorder(config)

        self.wake = WakeWordDetector(
            str(config.get("voice.wake_word.phrase", "amy")),
            float(config.get("voice.wake_word.sensitivity", 0.5)),
        )
        self._stop_event = threading.Event()
        self._loop_thread: Optional[threading.Thread] = None
        self._wake_deadline: Optional[float] = None
        self._wake_stop_reason = ""
        # Conferma vocale: mentre è attiva, il frammento successivo viene
        # interpretato come risposta (sì/no) anche senza la wake word.
        self._confirmation_callback: Optional[Callable[[str], bool]] = None
        self._confirmation_deadline = 0.0
        # Conversazione continua e macchina a stati.
        self.state = VoiceStateMachine()
        self._conversation_active = False
        self._conversation_deadline = 0.0
        self._presence_prompted = False

    def warm(self) -> None:
        """Precarica voci e modello STT in background.

        Non registra nulla: serve solo a evitare che il primo comando vocale
        aspetti il caricamento del modello.
        """
        if getattr(self, "_warmed", False):
            return
        self._warmed = True
        threading.Thread(target=self._warm_tts_cache, daemon=True).start()
        threading.Thread(target=self._warm_stt, daemon=True).start()

    def _warm_stt(self) -> None:
        warm = getattr(self.stt, "warm", None)
        if not callable(warm):
            return
        try:
            warm()
            _log.info("Modello STT locale pronto")
        except Exception as exc:  # pragma: no cover - dipende dall'ambiente
            _log.warning("Precaricamento STT non riuscito: %s", exc)

    # ------------------------------------------------------------------ sintesi
    def speak(self, text: str, *, block: bool = False) -> Dict[str, Any]:
        return self.tts.speak(text, block=block)

    def stop_speaking(self) -> None:
        self.tts.stop()

    def greeting_text(self) -> str:
        """Testo del messaggio di avvio, dalla configurazione."""
        value = str(self.config.get("voice.startup_greeting_text", "") or "").strip()
        return value or DEFAULT_GREETING

    def greet(self, text: Optional[str] = None) -> Dict[str, Any]:
        """Pronuncia il messaggio di avvio di Amy.

        Usa solo la sintesi locale: non registra e non avvia alcun ascolto.
        Se la voce è disabilitata o la sintesi non è disponibile, non dice
        nulla e restituisce il motivo.
        """
        if not self.enabled:
            return {"spoken": False, "reason": "voce disabilitata"}
        if not bool(self.config.get("voice.startup_greeting", True)):
            return {"spoken": False, "reason": "messaggio di avvio disattivato"}
        if not bool(self.tts.status().get("available")):
            return {"spoken": False, "reason": "sintesi vocale non disponibile"}
        message = (text or self.greeting_text()).strip()
        if not message:
            return {"spoken": False, "reason": "messaggio di avvio vuoto"}
        result = self.tts.speak(message, block=True)
        if result.get("spoken"):
            _log.info("Messaggio di avvio pronunciato: %s", message)
        else:
            _log.warning(
                "Messaggio di avvio non pronunciato: %s",
                result.get("reason") or "sintesi non riuscita",
            )
        return dict(result, text=message)

    # ------------------------------------------------------------------ ascolto
    def listen_once(self, seconds: Optional[float] = None) -> str:
        if not self.recorder.status().get("available"):
            raise VoiceError("Nessun registratore audio disponibile (serve ffmpeg o sox).")
        if not self.stt.available:
            raise VoiceError("Nessun motore di riconoscimento vocale configurato.")
        duration = seconds if seconds is not None else float(self.config.get("voice.recorder.seconds", 5))
        # Half-duplex: non registrare mentre Amy parla, altrimenti si cattura
        # la sua voce invece di quella dell'utente.
        if self._echo_guard_enabled() and self.tts.is_speaking():
            self._wait_quiet(self._stop_event, force_cooldown=True)
        if self._vad_enabled() and hasattr(self.recorder, "record_until_silence"):
            audio = self.recorder.record_until_silence(
                max_seconds=max(duration, self._vad_max_seconds()),
                silence_s=self._vad_silence(),
                start_timeout_s=self._vad_start_timeout(),
            )
        else:
            audio = self.recorder.record(duration)
        try:
            return self.stt.transcribe(audio)
        finally:
            try:
                audio.unlink(missing_ok=True)
            except OSError:
                pass

    # --------------------------------------------------------- protezione eco
    def _echo_guard_enabled(self) -> bool:
        return bool(self.config.get("voice.wake_word.echo_guard", True))

    def _echo_cooldown(self) -> float:
        try:
            value = float(self.config.get("voice.wake_word.echo_guard_cooldown_s", 0.8))
        except (TypeError, ValueError):
            value = 0.8
        return max(0.0, min(value, 5.0))

    def _wait_quiet(self, stop: threading.Event, *, force_cooldown: bool = False) -> bool:
        """Half-duplex: non registra mentre Amy sta parlando.

        Restituisce ``False`` se il ciclo è stato fermato durante l'attesa.
        """
        if not self._echo_guard_enabled():
            return not stop.is_set()
        deadline = time.monotonic() + self.ECHO_MAX_WAIT_S
        waited = False
        while not stop.is_set() and self.tts.is_speaking():
            if time.monotonic() >= deadline:
                _log.warning(
                    "Echo guard: la sintesi non è finita entro %.0f secondi, proseguo.",
                    self.ECHO_MAX_WAIT_S,
                )
                break
            if self._wake_deadline is not None and time.monotonic() >= self._wake_deadline:
                return False
            waited = True
            time.sleep(0.1)
        if stop.is_set():
            return False
        if waited or force_cooldown:
            cooldown = self._echo_cooldown()
            if cooldown > 0:
                _log.debug("Echo guard: attesa di %.1f s dopo la sintesi", cooldown)
                time.sleep(cooldown)
        return True

    def _echo_overlapped(self, started: float, ended: float) -> bool:
        """Vero se nella finestra registrata Amy stava parlando."""
        if not self._echo_guard_enabled():
            return False
        try:
            return bool(self.tts.speech_overlaps(started, ended))
        except Exception:  # noqa: BLE001 - la protezione non deve bloccare il ciclo
            return False

    # ------------------------------------------------------ conversazione
    def _conversation_enabled(self) -> bool:
        return bool(self.config.get("voice.conversation.enabled", True))

    def _conversation_timeout(self) -> float:
        try:
            value = float(self.config.get("voice.conversation.timeout_s", 30))
        except (TypeError, ValueError):
            value = 30.0
        return max(5.0, min(value, 300.0))

    def _barge_in_enabled(self) -> bool:
        return bool(self.config.get("voice.conversation.barge_in", True))

    def _vad_enabled(self) -> bool:
        return bool(self.config.get("voice.conversation.vad", True))

    def _vad_silence(self) -> float:
        try:
            value = float(self.config.get("voice.conversation.vad_silence_s", 1.0))
        except (TypeError, ValueError):
            value = 1.0
        return max(0.4, min(value, 3.0))

    def _vad_start_timeout(self) -> float:
        try:
            value = float(self.config.get("voice.conversation.vad_start_timeout_s", 6.0))
        except (TypeError, ValueError):
            value = 6.0
        return max(1.0, min(value, 15.0))

    def _vad_max_seconds(self) -> float:
        try:
            value = float(self.config.get("voice.conversation.vad_max_seconds", 15.0))
        except (TypeError, ValueError):
            value = 15.0
        return max(3.0, min(value, 30.0))

    def _barge_chunk(self) -> float:
        try:
            value = float(self.config.get("voice.conversation.barge_in_chunk_s", 1.0))
        except (TypeError, ValueError):
            value = 1.0
        return max(0.5, min(value, 3.0))

    def _reset_conversation_deadline(self) -> None:
        self._conversation_deadline = time.monotonic() + self._conversation_timeout()
        self._presence_prompted = False

    def begin_processing(self) -> None:
        self.state.set(VoiceState.PROCESSING, "elaborazione della richiesta")

    def begin_speaking(self) -> None:
        self.state.set(VoiceState.SPEAKING, "sintesi vocale")

    def begin_conversation(self, reason: str = "conversazione attiva") -> None:
        """Attiva la conversazione continua senza richiedere la wake word."""
        self._conversation_active = bool(self._conversation_enabled())
        self._reset_conversation_deadline()
        if self._conversation_active:
            self.state.set(VoiceState.CONVERSATION_ACTIVE, reason)
        else:
            self.state.set(VoiceState.IDLE, "conversazione disattivata")

    def end_conversation(self, reason: str = "conversazione terminata") -> None:
        self._conversation_active = False
        self._conversation_deadline = 0.0
        self._presence_prompted = False
        self.state.set(VoiceState.IDLE, reason)

    @staticmethod
    def _is_stop_phrase(text: str) -> bool:
        value = normalize(text)
        return value in {
            "basta", "stop", "fine", "fine conversazione", "chiudi",
            "chiudi la conversazione", "fermati", "silenzio",
            "non ho altro", "per ora basta",
        } or value.startswith("basta ")

    def _tts_echoes(self, text: str) -> bool:
        """Vero se il frammento sembra l'eco della sintesi in corso.

        Non è cancellazione acustica: confronta il testo trascritto con quello
        che Amy sta pronunciando. Se la wake word non compare nel testo di Amy,
        una sua presenza nel frammento è quasi certamente dell'utente.
        """
        spoken = normalize(getattr(self.tts, "current_text", "") or "")
        heard = normalize(text)
        if not spoken or not heard:
            return False
        if heard in spoken:
            return True
        heard_tokens = set(heard.split())
        spoken_tokens = set(spoken.split())
        if not heard_tokens:
            return False
        overlap = len(heard_tokens & spoken_tokens) / float(len(heard_tokens))
        return overlap >= 0.6

    def _listen_raw(self, seconds: float) -> str:
        """Registra e trascrive senza attendere la fine della sintesi."""
        if not self.recorder.status().get("available"):
            raise VoiceError("Nessun registratore audio disponibile.")
        if not self.barge_stt.available:
            raise VoiceError("Nessun motore di riconoscimento vocale configurato.")
        audio = self.recorder.record(seconds)
        try:
            return self.barge_stt.transcribe(audio)
        finally:
            try:
                audio.unlink(missing_ok=True)
            except OSError:
                pass

    def _forward(self, text: str, on_command: Callable[[str], None]) -> None:
        """Passa il comando al gestore senza bloccare il ciclo di ascolto."""
        self.state.set(VoiceState.PROCESSING, "comando vocale")
        worker = threading.Thread(
            target=self._run_command,
            args=(text, on_command),
            name="amy-voice-command",
            daemon=True,
        )
        worker.start()

    def _run_command(self, text: str, on_command: Callable[[str], None]) -> None:
        try:
            on_command(text)
        except Exception:  # noqa: BLE001 - un turno rotto non deve fermare l'ascolto
            _log.exception("Comando vocale non riuscito")
            self.state.set(VoiceState.ERROR, "comando vocale non riuscito")
            return
        # Un gestore che non aggiorna lo stato (per esempio un test o la sola
        # trascrizione) non deve lasciare il ciclo bloccato in PROCESSING.
        if self.state.state == VoiceState.PROCESSING and not self.tts.is_speaking():
            self.begin_conversation("comando concluso")

    def _barge_in_step(
        self,
        stop: threading.Event,
        on_command: Callable[[str], None],
        chunk: float,
    ) -> None:
        """Ascolta un frammento mentre Amy parla e reagisce alla wake word."""
        if stop.is_set():
            return
        try:
            text = self._listen_raw(chunk)
        except VoiceError as exc:
            _log.debug("Barge-in non disponibile: %s", exc.message)
            time.sleep(0.2)
            return
        if not text.strip():
            return
        if self._tts_echoes(text):
            return
        if not self.wake.matches(text):
            return
        _log.info("Wake word durante la sintesi: interruzione richiesta")
        try:
            self.tts.stop()
        except Exception:  # noqa: BLE001
            pass
        self.state.set(VoiceState.INTERRUPTED, "wake word durante la sintesi")
        self.begin_conversation("interruzione vocale")
        command = self.wake.extract_command(text)
        if command:
            self._forward(command, on_command)

    def _handle_conversation_timeout(self) -> None:
        if not self._presence_prompted:
            self._presence_prompted = True
            self._conversation_deadline = time.monotonic() + self._conversation_timeout()
            self.state.set(VoiceState.WAITING_FOR_INPUT, "verifica presenza")
            self.speak("Sei ancora lì?", block=False)
        else:
            self.speak("Torno in standby.", block=False)
            self.end_conversation("timeout della conversazione")

    def run_wake_loop(
        self,
        on_command: Callable[[str], None],
        *,
        stop_event: Optional[threading.Event] = None,
    ) -> None:
        """Ciclo vocale: wake word, conversazione continua e barge-in.

        - In attesa ascolta «Amy»; dopo la wake word non la richiede più.
        - Durante la sintesi continua a registrare: se sente «Amy» interrompe.
        - Dopo ``voice.conversation.timeout_s`` secondi di silenzio torna in
          standby, chiedendo prima «Sei ancora lì?».
        """
        stop = stop_event or self._stop_event
        if not self.recorder.status().get("available"):
            raise VoiceError("Serve un registratore audio per l'ascolto continuo.")
        if self.recorder.status().get("stuck"):
            raise VoiceError(
                "Il microfono non risponde: riavvia il servizio audio di macOS o il Mac, poi riprova."
            )
        if not self.stt.available:
            raise VoiceError("Serve un motore STT locale per l'ascolto continuo.")
        _log.info("Ascolto wake word «%s» attivo", self.wake.phrase)
        seconds = float(self.config.get("voice.recorder.seconds", 5))
        try:
            follow_seconds = float(self.config.get("voice.conversation.listen_seconds", 3.5))
        except (TypeError, ValueError):
            follow_seconds = 3.5
        follow_seconds = max(1.5, min(follow_seconds, seconds))
        barge_chunk = self._barge_chunk()
        empty_runs = 0
        self.state.set(VoiceState.IDLE, "in attesa della wake word")

        while not stop.is_set():
            if self._wake_deadline is not None and time.monotonic() >= self._wake_deadline:
                self._wake_stop_reason = "limite di durata raggiunto"
                _log.info("Ascolto wake word terminato: %s", self._wake_stop_reason)
                self.state.set(VoiceState.IDLE, "limite di durata")
                stop.set()
                break

            # Elaborazione in corso: non registrare comandi nuovi.
            if self.state.state == VoiceState.PROCESSING:
                time.sleep(0.1)
                continue

            # Amy sta parlando: barge-in o attesa half-duplex.
            if self.tts.is_speaking():
                if self.state.state in (VoiceState.IDLE, VoiceState.CONVERSATION_ACTIVE):
                    self.state.set(VoiceState.SPEAKING, "sintesi in corso")
                if self._barge_in_enabled():
                    self._barge_in_step(stop, on_command, barge_chunk)
                else:
                    if not self._wait_quiet(stop):
                        break
                continue

            # La sintesi è finita: la conversazione può continuare.
            if self.state.state == VoiceState.SPEAKING:
                self.begin_conversation("risposta conclusa")
                continue

            # Timeout della conversazione: sospeso mentre attende una conferma.
            if (
                self._conversation_active
                and self._confirmation_callback is None
                and time.monotonic() >= self._conversation_deadline
            ):
                self._handle_conversation_timeout()
                continue

            chunk_seconds = (
                follow_seconds
                if (self._conversation_active or self._confirmation_callback is not None)
                else seconds
            )
            started = time.monotonic()
            try:
                text = self.listen_once(chunk_seconds)
                empty_runs = 0
            except VoiceError as exc:
                _log.warning("Errore di ascolto: %s", exc.message)
                if "vuota" in exc.message.lower():
                    empty_runs += 1
                    if empty_runs >= 12:
                        _log.warning(
                            "Microfono silenzioso per %d cicli: riavvio il registratore.",
                            empty_runs,
                        )
                        self._recover_recorder()
                        empty_runs = 0
                else:
                    empty_runs = 0
                if self.recorder.status().get("stuck"):
                    self._wake_stop_reason = "microfono non rispondente"
                    _log.warning("Ascolto wake word terminato: %s", self._wake_stop_reason)
                    self.state.set(VoiceState.OFFLINE, "microfono non rispondente")
                    stop.set()
                    break
                time.sleep(1.0)
                continue
            ended = time.monotonic()
            if self._echo_overlapped(started, ended):
                _log.info("Frammento scartato: Amy stava parlando (protezione dall'eco).")
                continue

            # Conferma vocale in attesa.
            if self._confirmation_callback is not None:
                if time.monotonic() >= self._confirmation_deadline:
                    self.cancel_confirmation()
                    _log.info("Conferma vocale scaduta: operazione annullata")
                    self.state.set(VoiceState.CONVERSATION_ACTIVE, "conferma scaduta")
                    self.speak("Conferma scaduta: operazione annullata.")
                    continue
                try:
                    handled = bool(self._confirmation_callback(text))
                except Exception:  # noqa: BLE001
                    _log.warning("Conferma vocale non riuscita", exc_info=True)
                    handled = True
                if handled:
                    self.cancel_confirmation()
                continue

            # Conversazione attiva: nessuna wake word necessaria.
            if self._conversation_active:
                if not text.strip():
                    continue
                self._reset_conversation_deadline()
                if self._is_stop_phrase(text):
                    _log.info("Conversazione terminata su richiesta dell'utente")
                    self.speak("Va bene.", block=False)
                    self.end_conversation("richiesta dell'utente")
                    continue
                if self.wake.matches(text):
                    command = self.wake.extract_command(text)
                    if command:
                        self._forward(command, on_command)
                    else:
                        self.state.set(VoiceState.LISTENING, "solo wake word")
                        self.speak("Dimmi.", block=False)
                    continue
                self._forward(text.strip(), on_command)
                continue

            # Standby: serve la wake word.
            command = self.wake.extract_command(text)
            if command:
                self.state.set(VoiceState.WAKE_WORD_DETECTED, "wake word rilevata")
                self.tts.stop()
                self.begin_conversation("wake word con comando")
                self._forward(command, on_command)
            elif self.wake.matches(text):
                self.state.set(VoiceState.WAKE_WORD_DETECTED, "solo wake word")
                self.tts.stop()
                self.begin_conversation("wake word senza comando")
                self.state.set(VoiceState.LISTENING, "attesa del comando")
                self.speak("Dimmi.", block=False)

    def await_confirmation(
        self,
        callback: Callable[[str], bool],
        *,
        timeout_s: float = 30.0,
    ) -> None:
        """Attende una risposta vocale a una conferma già pronunciata.

        ``callback`` riceve il testo trascritto e restituisce True se ha
        risolto la conferma, False se la risposta non è chiara e va atteso un
        altro frammento. Scaduto il tempo, la conferma viene annullata.
        """
        self._confirmation_callback = callback
        self._confirmation_deadline = time.monotonic() + max(5.0, float(timeout_s))
        _log.info("In attesa di una conferma vocale")

    def cancel_confirmation(self) -> None:
        self._confirmation_callback = None
        self._confirmation_deadline = 0.0

    @property
    def awaiting_confirmation(self) -> bool:
        return self._confirmation_callback is not None

    def start_wake_loop(
        self,
        on_command: Callable[[str], None],
        *,
        max_minutes: Optional[float] = None,
    ) -> threading.Thread:
        """Avvia il ciclo di ascolto solo su richiesta esplicita.

        Con ``voice.wake_word.max_minutes`` maggiore di zero il ciclo si ferma
        dopo quel numero di minuti; con 0 (default) resta attivo finché l'app è
        aperta.
        """
        if self._loop_thread and self._loop_thread.is_alive():
            if not self._stop_event.is_set():
                return self._loop_thread
            # Il vecchio ciclo sta ancora chiudendo l'ultima registrazione:
            # diamogli un attimo, poi avviane uno nuovo. Senza questo, dopo
            # «Ferma ascolto» il pulsante «Ascolta Amy» sembra non ripartire.
            self._loop_thread.join(timeout=1.0)
        recorder_status = self.recorder.status()
        if not recorder_status.get("available"):
            raise VoiceError("Serve ffmpeg o sox per l'ascolto continuo.")
        if recorder_status.get("stuck"):
            raise VoiceError(
                "Il microfono non risponde: riavvia il servizio audio di macOS o il Mac, poi riprova.",
                detail=str(recorder_status.get("problem") or ""),
            )
        minutes = max_minutes
        if minutes is None:
            try:
                minutes = float(self.config.get("voice.wake_word.max_minutes", 0))
            except (TypeError, ValueError):
                minutes = 0.0
        minutes = float(minutes)
        if minutes > 0:
            minutes = max(1.0, min(minutes, 120.0))
            self._wake_deadline = time.monotonic() + minutes * 60.0
        else:
            # 0 = nessun limite: l'ascolto resta attivo finché l'app è aperta.
            self._wake_deadline = None
        self._wake_stop_reason = ""
        self._stop_event.clear()
        self._loop_thread = threading.Thread(
            target=self._wake_loop_entry,
            args=(on_command,),
            name="amy-wake-loop",
            daemon=True,
        )
        self._loop_thread.start()
        return self._loop_thread

    def _wake_loop_entry(self, on_command: Callable[[str], None]) -> None:
        """Esegue il ciclo e dichiara un errore imprevisto invece di tacere."""
        try:
            self.run_wake_loop(on_command)
        except BaseException as exc:  # noqa: BLE001 - il thread non deve morire in silenzio
            _log.exception("Ciclo wake word terminato inaspettatamente")
            self._wake_stop_reason = "errore del ciclo vocale"
            self.state.set(VoiceState.OFFLINE, "errore del ciclo vocale")
            if not isinstance(exc, VoiceError):
                _log.warning("Dettaglio: %s", exc)

    def _recover_recorder(self) -> None:
        """Ricrea il registratore dopo una lunga serie di registrazioni vuote.

        Il HAL di CoreAudio può smettere di consegnare frame dopo un lungo
        silenzio. Ricreare l'oggetto riapre lo stream; se il problema è più
        profondo, il ciclo continua a riprovare e la UI resta onesta.
        """
        try:
            self.recorder = build_recorder(self.config)
            _log.info("Registratore ricreato dopo silenzio prolungato")
        except Exception:  # noqa: BLE001
            _log.exception("Riavvio del registratore non riuscito")

    def request_stop_wake_loop(self) -> None:
        """Segnala lo stop senza attendere sintesi o lock audio."""
        self._stop_event.set()
        self._wake_deadline = None
        self.cancel_confirmation()
        self.end_conversation("ciclo fermato")
        threading.Thread(target=self.stop_speaking, daemon=True).start()

    def stop_wake_loop(self) -> None:
        self.request_stop_wake_loop()

    @property
    def wake_running(self) -> bool:
        """Vero finché il ciclo ascolta davvero.

        Dopo ``stop_wake_loop()`` il thread può essere ancora dentro l'ultima
        registrazione: per la UI l'ascolto è già fermo, così il pulsante non
        resta bloccato per qualche secondo.
        """
        if not (self._loop_thread and self._loop_thread.is_alive()):
            return False
        return not self._stop_event.is_set()

    def _warm_tts_cache(self) -> None:
        """Precarica in background l'elenco delle voci (se il motore lo supporta)."""
        warm = getattr(self.tts, "italian_voices", None)
        if not callable(warm):
            return
        try:
            warm()
        except Exception as exc:  # pragma: no cover - difensivo
            _log.debug("Precaricamento voci non riuscito: %s", exc)

    def status(self) -> Dict[str, Any]:
        tts_status = self.tts.status()
        stt_status = self.stt.status()
        recorder_status = self.recorder.status()
        return {
            "enabled": self.enabled,
            "speaking": bool(self.tts.is_speaking()),
            "tts": tts_status,
            "stt": stt_status,
            "recorder": recorder_status,
            "startup_greeting": {
                "enabled": bool(self.config.get("voice.startup_greeting", True)),
                "text": self.greeting_text(),
            },
            "wake_word": {
                "phrase": self.wake.phrase,
                "enabled": bool(self.config.get("voice.wake_word.enabled", False)),
                "running": self.wake_running,
                "available": bool(
                    stt_status.get("available")
                    and recorder_status.get("available")
                    and not recorder_status.get("stuck")
                ),
                "max_minutes": float(self.config.get("voice.wake_word.max_minutes", 0) or 0),
                "echo_guard": self._echo_guard_enabled(),
                "echo_guard_cooldown_s": self._echo_cooldown(),
                "stop_reason": self._wake_stop_reason,
            },
            "state": self.state.state.value,
            "state_reason": self.state.reason,
            "conversation": {
                "enabled": self._conversation_enabled(),
                "active": self._conversation_active,
                "timeout_s": self._conversation_timeout(),
                "barge_in": self._barge_in_enabled(),
            },
            "ready_for_voice_commands": bool(
                tts_status.get("available")
                and stt_status.get("available")
                and recorder_status.get("available")
                and not recorder_status.get("stuck")
            ),
        }
