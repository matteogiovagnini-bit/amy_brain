/* ==========================================================================
   Amy Core — comportamento dell'interfaccia locale
   --------------------------------------------------------------------------
   Nessuna dipendenza esterna e nessuna chiamata fuori dal server che ha
   servito la pagina. Il testo del modello entra sempre con textContent: una
   risposta non può iniettare markup o script.

   Gli stati del nucleo derivano solo da segnali reali del backend:
   - richiesta chat effettivamente in corso;
   - attività registrata con status "in_corso";
   - conferma realmente pendente;
   - sintesi vocale realmente attiva;
   - provider primario non raggiungibile;
   - errore effettivamente restituito.
   ========================================================================== */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const SPEAK_KEY = "amy.dashboard.speak";
  const MOTION_KEY = "amy.dashboard.motion";
  const LISTEN_SECONDS = 5;
  const BASE_POLL_MS = 5000;
  const FAST_POLL_MS = 1000;
  const ERROR_VISIBLE_MS = 8000;

  const app = {
    sessionId: "",
    state: null,
    pending: null,
    pendingSince: 0,
    busy: false,
    listening: false,
    speaking: false,
    speakingDeadline: 0,
    lastError: "",
    lastErrorAt: 0,
    errorTimer: 0,
    pollTimer: 0,
    fastTimer: 0,
    refreshing: false,
    loadingPending: false,
    resolving: false,
    modal: null,
    modalReturnFocus: null,
    motion: true,
    speak: false,
    voiceReady: false,
    wakeRunning: false,
    wakeAvailable: false,
  };

  // ------------------------------------------------------------------ utilità
  function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined && text !== null) element.textContent = String(text);
    return element;
  }

  function text(id, value) {
    const element = $(id);
    if (element) element.textContent = String(value);
  }

  function value(id, content, tone) {
    const element = $(id);
    if (!element) return;
    element.textContent = content === null || content === undefined || content === ""
      ? "Non disponibile"
      : String(content);
    element.className = tone ? "value-" + tone : "";
  }

  function tag(id, content, tone) {
    const element = $(id);
    if (!element) return;
    element.textContent = String(content);
    element.className = "tag" + (tone ? " " + tone : "");
  }

  function pill(id, content, tone, description) {
    const element = $(id);
    if (!element) return;
    element.className = "pill" + (tone ? " " + tone : "");
    const label = element.querySelector("span");
    if (label) label.textContent = String(content);
    element.title = description || String(content);
  }

  function setPaused(disabled) {
    const element = $("composerInput");
    if (element) element.setAttribute("aria-busy", disabled ? "true" : "false");
    const messages = $("messages");
    if (messages) messages.setAttribute("aria-busy", disabled ? "true" : "false");
  }

  function formatTime(input) {
    if (!input) return "";
    const date = new Date(input);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
  }

  function pretty(input) {
    try {
      return JSON.stringify(input, null, 2);
    } catch (error) {
      return String(input);
    }
  }

  function isObject(input) {
    return Boolean(input && typeof input === "object" && !Array.isArray(input));
  }

  function asNumber(input) {
    return typeof input === "number" && Number.isFinite(input) ? input : null;
  }

  let toastTimer = 0;
  function toast(message, bad) {
    const element = $("toast");
    if (!element) return;
    element.textContent = String(message);
    element.className = bad ? "toast bad" : "toast";
    element.hidden = false;
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => {
      element.hidden = true;
    }, 5400);
  }

  function readSetting(key) {
    try {
      return window.localStorage.getItem(key);
    } catch (error) {
      return null;
    }
  }

  function writeSetting(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch (error) {
      /* la preferenza resta valida solo per questa pagina */
    }
  }

  // --------------------------------------------------------------------- API
  async function api(path, options) {
    const response = await fetch(path, Object.assign({
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      cache: "no-store",
    }, options || {}));

    let data = null;
    try {
      data = await response.json();
    } catch (error) {
      data = null;
    }

    if (!response.ok) {
      const message = data && (data.error || data.detail || data.message);
      throw new Error(message || "Errore HTTP " + response.status);
    }
    if (data && data.error && !Object.prototype.hasOwnProperty.call(data, "status")) {
      throw new Error(data.error);
    }
    return data || {};
  }

  function post(path, body) {
    return api(path, { method: "POST", body: JSON.stringify(body || {}) });
  }

  // --------------------------------------------------------------- trascrizione
  function renderRich(parent, source) {
    const value = String(source || "");
    const pattern = /(\*\*[^*]+\*\*|`[^`]+`)/g;
    let last = 0;
    let match = pattern.exec(value);
    while (match) {
      if (match.index > last) {
        parent.appendChild(document.createTextNode(value.slice(last, match.index)));
      }
      const token = match[0];
      if (token.startsWith("**")) {
        parent.appendChild(node("strong", "", token.slice(2, -2)));
      } else {
        parent.appendChild(node("code", "", token.slice(1, -1)));
      }
      last = pattern.lastIndex;
      match = pattern.exec(value);
    }
    if (last < value.length) {
      parent.appendChild(document.createTextNode(value.slice(last)));
    }
  }

  function messageNode(role, content, createdAt, note) {
    const isUser = role === "user";
    const wrapper = node("div", "message " + (isUser ? "user" : "amy"));
    const meta = node("div", "meta");
    meta.appendChild(node("span", "", isUser ? "Tu" : "Amy"));
    const stamp = formatTime(createdAt);
    if (stamp) meta.appendChild(node("span", "", "· " + stamp));
    wrapper.appendChild(meta);

    const bubble = node("div", "bubble");
    renderRich(bubble, content);
    if (!isUser) {
      const speak = node("button", "speak", "Ascolta");
      speak.type = "button";
      speak.title = "Pronuncia questo messaggio con la voce di sistema";
      speak.setAttribute("aria-label", "Pronuncia questo messaggio");
      speak.addEventListener("click", () => speakText(String(content || "")));
      bubble.appendChild(speak);
    }
    wrapper.appendChild(bubble);

    if (note) wrapper.appendChild(node("div", "note", note));
    return wrapper;
  }

  function showEmptyState(message) {
    const container = $("messages");
    if (!container) return;
    container.replaceChildren(node("div", "empty-state", message));
  }

  function renderTranscript(messages) {
    const container = $("messages");
    if (!container) return;
    container.replaceChildren();
    if (!messages.length) {
      container.appendChild(node("div", "empty-state", "Nessun messaggio in questa sessione. Scrivi una richiesta per iniziare."));
      return;
    }
    messages.forEach((message) => {
      container.appendChild(messageNode(message.role, message.content, message.created_at));
    });
    scrollMessages();
  }

  function appendMessage(role, content, createdAt, note) {
    const container = $("messages");
    if (!container) return null;
    const empty = container.querySelector(".empty-state");
    if (empty) empty.remove();
    const element = messageNode(role, content, createdAt, note);
    container.appendChild(element);
    scrollMessages();
    return element;
  }

  function appendError(message) {
    const wrapper = appendMessage("assistant", message, new Date().toISOString());
    if (wrapper) wrapper.classList.add("error");
    const meta = wrapper && wrapper.querySelector(".meta span");
    if (meta) meta.textContent = "Amy · errore";
    return wrapper;
  }

  function scrollMessages() {
    const container = $("messages");
    if (container) container.scrollTop = container.scrollHeight;
  }

  function setTyping(visible) {
    const element = $("typing");
    if (element) element.hidden = !visible;
    if (visible) scrollMessages();
  }

  function setSession(sessionId) {
    if (!sessionId) return;
    app.sessionId = sessionId;
    text("sessionLabel", "sessione · " + sessionId);
  }

  async function loadTranscript(sessionId) {
    const query = sessionId ? "?session=" + encodeURIComponent(sessionId) : "";
    const data = await api("/api/transcript" + query);
    if (data.session_id) setSession(data.session_id);
    const messages = (data.messages || []).filter(
      (item) => item && (item.role === "user" || item.role === "assistant") && typeof item.content === "string"
    );
    renderTranscript(messages);
    return messages;
  }

  // ---------------------------------------------------------------- provider
  function providerView(data) {
    const raw = data && isObject(data.provider) ? data.provider : null;
    if (!raw) {
      return {
        name: "", model: "", endpoint: "", note: "",
        available: false, modelInstalled: null, fallback: null, fallbackAvailable: false,
        anyAvailable: false, primary: null,
      };
    }

    const primary = isObject(raw.primary) ? raw.primary : raw;
    const fallback = isObject(raw.fallback) ? raw.fallback : null;
    const available = typeof raw.available === "boolean"
      ? raw.available
      : Boolean(primary && primary.available);
    const fallbackAvailable = Boolean(fallback && fallback.available);
    const installedRaw = typeof raw.model_installed === "boolean"
      ? raw.model_installed
      : (primary && typeof primary.model_installed === "boolean" ? primary.model_installed : null);

    return {
      name: String((primary && primary.provider) || raw.provider || ""),
      model: String((primary && primary.model) || raw.model || ""),
      endpoint: String((primary && primary.base_url) || raw.base_url || ""),
      note: String(raw.last_fallback_reason || raw.note || ""),
      primaryNote: String((primary && primary.note) || ""),
      apiKeyEnv: String((primary && primary.api_key_env) || ""),
      apiKeyConfigured: primary ? primary.api_key_configured !== false : true,
      remote: Boolean(primary && primary.local_endpoint === false),
      available,
      modelInstalled: installedRaw,
      fallback,
      fallbackAvailable,
      anyAvailable: available || fallbackAvailable,
      primary,
    };
  }

  function fallbackLabel(provider) {
    if (!provider.fallback) return "Non configurato";
    const name = String(provider.fallback.provider || "fallback");
    const model = provider.fallback.model ? " · " + provider.fallback.model : "";
    const state = provider.fallbackAvailable ? "disponibile" : "non disponibile";
    return name + model + " (" + state + ")";
  }

  // ------------------------------------------------------------------- stato
  function recentError() {
    return Boolean(app.lastError) && (Date.now() - app.lastErrorAt) < ERROR_VISIBLE_MS;
  }

  function markError(message) {
    app.lastError = String(message || "Errore non specificato.");
    app.lastErrorAt = Date.now();
    text("footerStatus", "errore · " + app.lastError);
    const footer = $("footerStatus");
    if (footer) footer.className = "bad";
    window.clearTimeout(app.errorTimer);
    app.errorTimer = window.setTimeout(() => {
      if (Date.now() - app.lastErrorAt >= ERROR_VISIBLE_MS) {
        app.lastError = "";
        renderCore();
      }
    }, ERROR_VISIBLE_MS + 150);
    renderCore();
  }

  function clearError() {
    app.lastError = "";
    app.lastErrorAt = 0;
    window.clearTimeout(app.errorTimer);
    const footer = $("footerStatus");
    if (footer) footer.className = "";
    updateFooter();
  }

  function runningActivity() {
    const activities = (app.state && app.state.activities) || [];
    return activities.find((item) => item && item.status === "in_corso") || null;
  }

  // Il simulatore espone lo stato in piano; il collegamento MQTT lo
  // annida nell'invilto (response.payload). Si accettano entrambe le forme.
  function robotPayload(raw) {
    if (!isObject(raw)) return null;
    const response = isObject(raw.response) ? raw.response : null;
    const payload = response && isObject(response.payload) ? response.payload : null;
    if (payload && isObject(payload.status)) return payload.status;
    if (payload) return payload;
    return raw;
  }

  function robotEstopActive() {
    const source = robotPayload(app.state && app.state.robot);
    return Boolean(source && source.estop_latched);
  }

  function coreView() {
    const data = app.state;
    const provider = providerView(data);
    const running = runningActivity();
    const voiceSpeaking = Boolean(data && data.voice && data.voice.speaking) || app.speaking;

    if (app.pending) {
      return {
        state: "waiting_confirmation",
        label: "Conferma richiesta",
        activity: (app.pending.tool || "Operazione") + " · attende la tua autorizzazione",
        hint: app.pending.reason || "Controlla i dettagli prima di autorizzare o annullare.",
      };
    }
    if (recentError()) {
      return {
        state: "error",
        label: "Errore",
        activity: app.lastError,
        hint: "L'operazione non è stata dichiarata completata. Controlla il messaggio in chat o riprova.",
      };
    }
    if (robotEstopActive()) {
      return {
        state: "error",
        label: "E-stop attivo",
        activity: "Il robot è bloccato dal latch dell'E-stop software",
        hint: "L'E-stop software non sostituisce quello fisico. Il latch va azzerato con la procedura prevista.",
      };
    }
    if (running) {
      return {
        state: "executing",
        label: "Esecuzione",
        activity: String(running.tool || "Strumento") + " in corso",
        hint: "Amy sta eseguendo un'operazione autorizzata. L'esito sarà mostrato al termine.",
      };
    }
    if (app.listening) {
      return {
        state: "listening",
        label: "In ascolto",
        activity: "Registrazione dal microfono del Mac",
        hint: "La registrazione dura " + LISTEN_SECONDS + " secondi e parte solo su tua richiesta.",
      };
    }
    if (app.busy) {
      return {
        state: "processing",
        label: "Elaborazione",
        activity: "Il motore IA sta elaborando la richiesta",
        hint: "La chat resta utilizzabile: attendo la risposta e mostro solo esiti reali.",
      };
    }
    if (voiceSpeaking) {
      return {
        state: "speaking",
        label: "Risposta vocale",
        activity: "Sintesi vocale in corso",
        hint: "Puoi interrompere la voce con il pulsante «Stop voce».",
      };
    }
    if (app.wakeRunning) {
      return {
        state: "listening",
        label: "In ascolto",
        activity: "Di' «Amy» seguito dal comando",
        hint: "L'ascolto continuo parte solo da qui, si ferma con lo stesso pulsante e ha un limite di durata.",
      };
    }
    if (data && !provider.anyAvailable) {
      return {
        state: "offline",
        label: "Offline",
        activity: provider.name ? provider.name + " non raggiungibile" : "Nessun motore IA configurato",
        hint: provider.fallbackAvailable
          ? "Rispondo con il fallback locale " + fallbackLabel(provider) + "."
          : "La chat resterà limitata finché il provider non torna disponibile.",
      };
    }
    return {
      state: "idle",
      label: "Pronta",
      activity: "In attesa di una richiesta",
      hint: "Scrivi un messaggio, usa il microfono se disponibile o avvia una nuova interazione.",
    };
  }

  function renderCore() {
    const stage = $("amyCore");
    if (!stage) return;
    const view = coreView();
    stage.dataset.state = view.state;
    stage.setAttribute("aria-label", "Amy Core: " + view.label + ". " + view.activity);
    text("coreState", view.label);
    text("coreActivity", view.activity);
    text("coreHint", view.hint);

    const stateNode = $("coreState");
    if (stateNode) stateNode.className = "core-state state-" + view.state;

    const data = app.state;
    const provider = providerView(data);
    const line = $("coreProvider");
    let message = "Motore IA in verifica…";
    let tone = "";

    if (data) {
      if (!provider.name) {
        message = "Nessun motore IA configurato";
        tone = "bad";
      } else if (provider.available) {
        message = provider.name + (provider.model ? " · " + provider.model : "") + " · disponibile";
        tone = "ok";
      } else if (provider.remote && provider.apiKeyConfigured === false) {
        message = provider.name + " · chiave API non configurata";
        tone = "warn";
      } else if (provider.fallbackAvailable) {
        message = provider.name + " non raggiungibile · fallback " + String(
          (provider.fallback && provider.fallback.provider) || "locale"
        );
        tone = "warn";
      } else {
        message = provider.name + (provider.model ? " · " + provider.model : "") + " · non raggiungibile";
        tone = "bad";
      }
    }

    if (line) line.className = "core-provider" + (tone ? " " + tone : "");
    text("coreProviderText", message);
  }

  // ------------------------------------------------------------ pannello dati
  function renderProvider(data) {
    const provider = providerView(data);
    const missingModel = provider.available && provider.modelInstalled === false;
    text("engineProvider", provider.name || "Non configurato");
    text("engineModel", provider.model || "Non configurato");
    value("engineEndpoint", provider.endpoint || "Non disponibile", provider.endpoint ? "" : "muted");
    value("engineFallback", fallbackLabel(provider), provider.fallback ? (provider.fallbackAvailable ? "" : "warn") : "muted");

    if (!data || !data.provider) {
      tag("engineTag", "non disponibile", "bad");
    } else if (missingModel) {
      tag("engineTag", "modello mancante", "warn");
    } else if (provider.available) {
      tag("engineTag", "disponibile", "ok");
    } else if (provider.fallbackAvailable) {
      tag("engineTag", "fallback locale", "warn");
    } else {
      tag("engineTag", "non disponibile", "bad");
    }

    const primaryPill = provider.name
      ? "motore · " + provider.name
      : "motore · non configurato";
    let tone = provider.available ? "ok" : (provider.fallbackAvailable ? "warn" : "bad");
    if (missingModel) tone = "warn";
    if (!data) tone = "";
    pill("providerPill", primaryPill, tone, provider.note || primaryPill);

    let note = "Il motore IA resta locale per impostazione predefinita.";
    if (provider.remote && provider.apiKeyConfigured === false) {
      note = "Servizio gratuito scelto, ma manca la chiave API: imposta " +
        (provider.apiKeyEnv || "la variabile indicata") +
        " in ~/.amy/secrets.json (permessi 600) e riavvia Amy.";
    } else if (provider.remote) {
      note = provider.primaryNote ||
        "Servizio online gratuito autorizzato: la conversazione lascia questo computer.";
    } else if (missingModel) {
      note = "Ollama è raggiungibile ma il modello configurato (" + (provider.model || "non specificato") +
        ") non risulta installato. Scarica il modello o Amy userà il fallback se disponibile.";
    } else if (provider.note) {
      note = provider.note;
    }
    text("engineNote", note);
  }

  function renderSystem(data) {
    const system = data && isObject(data.system) ? data.system : null;
    if (!system) {
      value("systemOs", "Non disponibile", "muted");
      value("systemArch", "Non disponibile", "muted");
      value("systemPython", "Non disponibile", "muted");
      value("systemCpu", "Non disponibile", "muted");
      value("systemLoad", "Non disponibile", "muted");
      value("systemDisk", "Non disponibile", "muted");
      tag("systemTag", "non disponibile", "bad");
      return;
    }

    const osName = String(system.os_name || "");
    const osVersion = system.os ? String(system.os) : "";
    let osLabel = "Non disponibile";
    if (osVersion && osVersion !== osName) {
      osLabel = osName === "Darwin" ? "macOS " + osVersion : (osName ? osName + " " + osVersion : osVersion);
    } else if (osVersion) {
      osLabel = osVersion;
    } else if (osName) {
      osLabel = osName;
    }
    value("systemOs", osLabel, osLabel === "Non disponibile" ? "muted" : "");
    value("systemArch", system.arch || "Non disponibile", system.arch ? "" : "muted");
    value("systemPython", system.python || "Non disponibile", system.python ? "" : "muted");
    value(
      "systemCpu",
      typeof system.cpu_count === "number" ? system.cpu_count + " core" : "Non disponibile",
      typeof system.cpu_count === "number" ? "" : "muted"
    );

    let load = "Non disponibile";
    if (Array.isArray(system.load_average) && system.load_average.length) {
      load = system.load_average.slice(0, 3).join(" / ") + " (1 / 5 / 15 min)";
    }
    value("systemLoad", load, load === "Non disponibile" ? "muted" : "");

    let disk = "Non disponibile";
    let diskTone = "muted";
    if (isObject(system.disk)) {
      const free = asNumber(system.disk.free_gb);
      const total = asNumber(system.disk.total_gb);
      const used = asNumber(system.disk.used_pct);
      if (free !== null && total !== null) {
        disk = free + " GB liberi su " + total + " GB";
        if (used !== null) disk += " (" + used + "% usato)";
        diskTone = used !== null && used > 90 ? "warn" : "";
      }
    }
    value("systemDisk", disk, diskTone);

    tag("systemTag", "dati locali", "ok");
  }

  function renderVoice(data) {
    const voice = data && isObject(data.voice) ? data.voice : null;
    if (!voice) {
      value("voiceTts", "Non disponibile", "muted");
      value("voiceStt", "Non disponibile", "muted");
      value("voiceRecorder", "Non disponibile", "muted");
      value("voiceWake", "Non configurata", "muted");
      value("voiceGreeting", "Non configurato", "muted");
      tag("voiceTag", "non disponibile", "bad");
      text("voiceNote", "La chat testuale funziona anche senza voce.");
      app.voiceReady = false;
      return;
    }

    const tts = isObject(voice.tts) ? voice.tts : {};
    const stt = isObject(voice.stt) ? voice.stt : {};
    const recorder = isObject(voice.recorder) ? voice.recorder : {};
    const wake = isObject(voice.wake_word) ? voice.wake_word : {};
    const greeting = isObject(voice.startup_greeting) ? voice.startup_greeting : {};
    app.voiceReady = Boolean(voice.ready_for_voice_commands);

    value(
      "voiceTts",
      tts.available
        ? "Disponibile · " + (tts.engine || "sistema") + (tts.voice ? " · " + tts.voice : "")
        : "Non disponibile",
      tts.available ? "ok" : "bad"
    );
    value(
      "voiceStt",
      stt.available
        ? "Disponibile · " + (stt.engine || "configurato")
        : (stt.engine && stt.engine !== "none" ? "Non disponibile" : "Non configurato"),
      stt.available ? "ok" : (stt.engine && stt.engine !== "none" ? "bad" : "muted")
    );
    value(
      "voiceRecorder",
      recorder.available
        ? (recorder.stuck
          ? "Non risponde · " + (recorder.engine || "microfono")
          : "Disponibile · " + (recorder.engine || "configurato"))
        : "Non disponibile",
      recorder.available && !recorder.stuck ? "ok" : "bad"
    );

    let wakeText = "Non configurata";
    let wakeTone = "muted";
    if (wake.enabled) {
      wakeText = wake.running ? "Attiva · in ascolto" : "Configurata · non attiva";
      wakeTone = wake.running ? "ok" : "warn";
    }
    value("voiceWake", wakeText, wakeTone);

    const greetingText = String(greeting.text || "").trim();
    if (greeting.enabled && greetingText) {
      value("voiceGreeting", "Attivo · " + greetingText, "ok");
    } else if (greetingText) {
      value("voiceGreeting", "Disattivato · " + greetingText, "muted");
    } else {
      value("voiceGreeting", "Non configurato", "muted");
    }

    if (voice.ready_for_voice_commands) {
      tag("voiceTag", "pronta", "ok");
    } else if (tts.available) {
      tag("voiceTag", "solo testo", "warn");
    } else {
      tag("voiceTag", "non disponibile", "bad");
    }

    if (voice.speaking) {
      const duplex = wake.running && wake.echo_guard ? " Il microfono resta chiuso finché parla." : "";
      text("voiceNote", "Sintesi vocale in corso. Puoi interromperla con «Stop voce»." + duplex);
    } else if (recorder.stuck) {
      text("voiceNote", "Il microfono non ha risposto e Amy ha sospeso le registrazioni. Riavvia il servizio audio di macOS o il Mac, poi riprova.");
    } else if (wake.running) {
      const duplex = wake.echo_guard ? " Mentre Amy parla il microfono è chiuso." : "";
      text("voiceNote", "Ascolto continuo attivo: di' «Amy» seguito dal comando. Fermalo con «Ferma ascolto»." + duplex);
    } else if (greeting.enabled && greetingText) {
      text("voiceNote", "All'avvio Amy dice: «" + greetingText + "». Usa «Ripeti saluto» per riascoltarlo.");
    } else if (voice.ready_for_voice_commands) {
      text("voiceNote", "Microfono e trascrizione locali disponibili. Usa il microfono o «Ascolta «Amy»»; nulla parte da solo.");
    } else {
      text("voiceNote", "La chat testuale funziona. Per i comandi vocali servono microfono e trascrizione locale (sounddevice e faster-whisper).");
    }

    pill(
      "voicePill",
      voice.ready_for_voice_commands ? "voce · pronta" : "voce · solo testo",
      voice.ready_for_voice_commands ? "ok" : "warn",
      voice.ready_for_voice_commands ? "Sintesi e comandi vocali disponibili" : "La sintesi può essere disponibile anche senza microfono"
    );
  }

  function renderRobot(data) {
    const raw = data && isObject(data.robot) ? data.robot : null;
    const config = data && isObject(data.config) ? data.config : {};
    const transport = String((raw && raw.transport) || config.robot_transport || "simulated");

    if (!raw) {
      value("robotReachable", "Non disponibile", "muted");
      value("robotMode", "Non disponibile", "muted");
      value("robotPhase", "Non disponibile", "muted");
      value("robotEstop", "Non disponibile", "muted");
      value("robotHeartbeat", "Non disponibile", "muted");
      value("robotBattery", "Non disponibile", "muted");
      value("robotPi", "Non disponibile", "muted");
      tag("robotTransport", transport, "warn");
      text("robotNote", "Nessun collegamento robot disponibile. Nessun comando viene inviato.");
      const estop = $("estopBtn");
      if (estop) estop.disabled = false;
      pill("robotPill", "robot · non disponibile", "bad", "Nessun collegamento robot");
      return;
    }

    const source = robotPayload(raw) || {};
    const reachable = raw.reachable !== false && source.connected !== false;
    const simulated = Boolean(source.simulated || raw.simulated || transport === "simulated");
    const estopLatched = Boolean(source.estop_latched);
    const fault = Boolean(source.fault_latched);

    tag("robotTransport", simulated ? "simulato" : transport, simulated ? "warn" : "ok");

    if (!reachable) {
      value("robotReachable", "Non collegato", "bad");
      value("robotMode", "Non disponibile", "muted");
      value("robotPhase", "Non disponibile", "muted");
      value("robotEstop", "Non disponibile", "muted");
      value("robotHeartbeat", "Non disponibile", "muted");
      value("robotBattery", "Non disponibile", "muted");
      value("robotPi", "Non collegato", "bad");
      text("robotNote", "Robot non collegato" + (raw.error ? ": " + raw.error : "") + ". Nessun comando viene inviato.");
      pill("robotPill", "robot · offline", "bad", "Robot non collegato");
    } else {
      value("robotReachable", simulated ? "Simulatore locale" : "Collegato", simulated ? "warn" : "ok");
      value("robotMode", source.mode || "Non disponibile", source.mode ? "" : "muted");
      value("robotPhase", source.motion_phase || "Non disponibile", source.motion_phase ? "" : "muted");

      if (estopLatched) {
        value("robotEstop", "ATTIVO", "bad");
      } else if (fault) {
        value("robotEstop", "Fault" + (source.fault_code ? ": " + source.fault_code : ""), "bad");
      } else {
        value("robotEstop", "Non attivo", "ok");
      }

      const heartbeat = asNumber(source.last_heartbeat_age_ms);
      const watchdog = asNumber(source.watchdog_timeout_s);
      if (heartbeat === null) {
        value("robotHeartbeat", "Non disponibile", "muted");
      } else {
        const seconds = Math.round(heartbeat / 100) / 10;
        value(
          "robotHeartbeat",
          seconds + " s" + (watchdog !== null && heartbeat > watchdog * 1000 ? " · oltre watchdog" : ""),
          watchdog !== null && heartbeat > watchdog * 1000 ? "warn" : ""
        );
      }

      const battery = asNumber(source.battery_pct);
      if (battery === null) {
        value("robotBattery", "Non disponibile", "muted");
      } else {
        value(
          "robotBattery",
          battery.toFixed(0) + "%" + (source.battery_estimated || simulated ? " (stimata)" : ""),
          battery < 20 ? "bad" : (battery < 40 ? "warn" : "")
        );
      }

      const pi = source.pi || source.raspberry_pi || source.pi_status;
      if (typeof pi === "string" && pi) {
        value("robotPi", pi, "");
      } else if (isObject(pi)) {
        value("robotPi", pi.status || pi.state || "Segnalato", "");
      } else {
        value("robotPi", "Non disponibile", "muted");
      }

      if (simulated) {
        text("robotNote", "Il simulatore non muove attuatori fisici. Batteria, heartbeat e movimento sono valori simulati.");
      } else if (transport === "mqtt") {
        text("robotNote", "Collegamento MQTT sperimentale. Amy non può verificare il movimento fisico.");
      } else {
        text("robotNote", "Stato ricevuto dal collegamento. Il movimento fisico non è verificato da Amy.");
      }

      if (estopLatched) {
        pill("robotPill", "robot · E-stop", "bad", "E-stop software attivo");
      } else {
        pill(
          "robotPill",
          "robot · " + (simulated ? "simulato" : transport),
          simulated ? "warn" : "ok",
          simulated ? "Nessun hardware fisico collegato" : "Trasporto " + transport
        );
      }
    }

    const estop = $("estopBtn");
    if (estop) {
      estop.textContent = estopLatched ? "E-STOP ATTIVO" : "E-STOP SOFTWARE";
      estop.disabled = estopLatched;
      estop.title = estopLatched
        ? "Il latch dell'E-stop software è attivo"
        : "Invia un E-stop software. Non sostituisce l'E-stop fisico.";
    }
    const stop = $("robotStopBtn");
    if (stop) stop.disabled = !reachable;
  }

  function renderMemory(data) {
    const memory = data && isObject(data.memory) ? data.memory : {};
    text("statMessages", Number(memory.messages || 0));
    text("statFacts", Number(memory.facts || 0));
    text("statActivities", Number(memory.activities || 0));
    tag("memoryTag", "SQLite locale", "ok");

    const container = $("facts");
    if (!container) return;
    container.replaceChildren();
    const facts = (data && data.facts) || [];
    if (!facts.length) {
      container.appendChild(node("div", "empty", "Nessun fatto memorizzato."));
      return;
    }
    facts.slice(0, 8).forEach((fact) => {
      const row = node("div", "fact");
      row.appendChild(node("b", "", fact.key));
      row.appendChild(node("span", "", String(fact.value)));
      row.title = String(fact.key) + ": " + String(fact.value);
      container.appendChild(row);
    });
  }

  function activityTone(status) {
    if (status === "errore") return "bad";
    if (status === "rifiutato") return "warn";
    if (status === "in_corso") return "running";
    return "ok";
  }

  function activityLabel(status) {
    if (status === "in_corso") return "in corso";
    if (status === "errore") return "errore";
    if (status === "rifiutato") return "rifiutato";
    return "ok";
  }

  function renderActivities(data) {
    const container = $("activities");
    if (!container) return;
    container.replaceChildren();
    const activities = (data && data.activities) || [];
    if (!activities.length) {
      container.appendChild(node("div", "empty", "Nessuna attività registrata."));
      return;
    }
    activities.slice(0, 10).forEach((activity) => {
      const row = node("div", "activity");
      row.appendChild(node("span", "dot " + activityTone(activity.status)));
      const body = node("div", "");
      body.appendChild(node("div", "name", String(activity.tool || "strumento") + " · " + activityLabel(activity.status)));
      const result = isObject(activity.result) ? activity.result : {};
      if (result.message) body.appendChild(node("div", "detail", String(result.message)));
      row.appendChild(body);
      row.appendChild(node("span", "time", formatTime(activity.started_at)));
      row.title = pretty({ risk: activity.risk, args: activity.args, result: activity.result });
      container.appendChild(row);
    });
  }

  function renderTools(tools) {
    text("toolCount", String((tools || []).length));
    const container = $("tools");
    if (!container) return;
    container.replaceChildren();
    if (!tools || !tools.length) {
      container.appendChild(node("div", "empty", "Nessuno strumento disponibile."));
      return;
    }
    tools.forEach((tool) => {
      const row = node("div", "tool");
      row.appendChild(node("span", "risk " + (tool.risk || "A"), tool.risk || "A"));
      row.appendChild(node("span", "", tool.name));
      row.title = tool.description || tool.name;
      container.appendChild(row);
    });
  }

  function renderSettings(data) {
    const config = data && isObject(data.config) ? data.config : {};
    const provider = providerView(data);
    const voice = data && isObject(data.voice) ? data.voice : {};
    const tools = (data && data.tools) || [];
    const rows = [
      ["Assistente", (data && data.assistant && data.assistant.name) || "Amy"],
      ["Versione", (data && data.assistant && data.assistant.version) || "0.1.0"],
      ["Motore primario", provider.name ? provider.name + (provider.model ? " · " + provider.model : "") : "Non configurato"],
      ["Stato motore", provider.available && provider.modelInstalled === false
        ? "modello mancante"
        : (provider.available ? "disponibile" : (provider.fallbackAvailable ? "fallback locale" : "non disponibile"))],
      ["Fallback", fallbackLabel(provider)],
      ["Trasporto robot", config.robot_transport || "non configurato"],
      ["Voce attiva", config.voice_enabled ? "sì" : "no"],
      ["Comandi vocali", voice.ready_for_voice_commands ? "pronti" : "STT o registratore non disponibili"],
      ["Lingua", config.language || "non configurata"],
      ["Cartelle autorizzate", (Array.isArray(config.allowed_roots) ? config.allowed_roots.join(", ") : "") || "non configurate"],
      ["Memoria", (data && data.memory && data.memory.db_path) || "non disponibile"],
      ["Strumenti", String(tools.length)],
      ["Configurazione", config.config_path || "non disponibile"],
    ];

    const grid = $("settingsGrid");
    if (!grid) return;
    grid.replaceChildren();
    rows.forEach((pair) => {
      grid.appendChild(node("dt", "", pair[0]));
      grid.appendChild(node("dd", "", pair[1]));
    });
    text("settingsPath", config.config_path || "~/.amy/config.json");
  }

  function updateFooter() {
    const data = app.state;
    const config = data && isObject(data.config) ? data.config : {};
    text("configPath", config.config_path || "~/.amy/config.json");
    if (recentError()) {
      text("footerStatus", "errore · " + app.lastError);
      const footer = $("footerStatus");
      if (footer) footer.className = "bad";
      return;
    }
    const provider = providerView(data);
    const transport = config.robot_transport || "robot non configurato";
    const engine = provider.name || "motore non configurato";
    text("footerStatus", "locale · IA " + engine + " · robot " + transport);
  }

  function applyState(data) {
    app.state = data;

    if (data.assistant && data.assistant.session_id && !app.sessionId) {
      setSession(data.assistant.session_id);
    }

    const wake = data.voice && isObject(data.voice.wake_word) ? data.voice.wake_word : {};
    app.wakeRunning = Boolean(wake.running);
    app.wakeAvailable = Boolean(wake.available);

    const voiceSpeaking = Boolean(data.voice && data.voice.speaking);
    if (voiceSpeaking) {
      app.speaking = true;
      app.speakingDeadline = 0;
    } else if (app.speaking && (app.speakingDeadline === 0 || Date.now() >= app.speakingDeadline)) {
      app.speaking = false;
      app.speakingDeadline = 0;
    }

    renderProvider(data);
    renderSystem(data);
    renderVoice(data);
    renderRobot(data);
    renderMemory(data);
    renderActivities(data);
    renderTools(data.tools || []);
    renderSettings(data);
    updateFooter();
    updateControls();
    renderCore();
    ensureFastPoll();

    const pendingCount = Number(data.pending_confirmations || 0);
    if (!app.pending && !app.busy && !app.resolving && pendingCount > 0) {
      loadPending();
    }
  }

  async function refreshState() {
    if (app.refreshing || document.hidden) return;
    app.refreshing = true;
    try {
      const data = await api("/api/state");
      applyState(data);
    } catch (error) {
      markError("Stato non raggiungibile: " + error.message);
    } finally {
      app.refreshing = false;
    }
  }

  function ensureFastPoll() {
    const need = app.busy || app.listening || app.speaking || app.wakeRunning || Boolean(runningActivity());
    if (need && !app.fastTimer) {
      app.fastTimer = window.setInterval(refreshState, FAST_POLL_MS);
    } else if (!need && app.fastTimer) {
      window.clearInterval(app.fastTimer);
      app.fastTimer = 0;
    }
  }

  async function loadPending() {
    if (app.loadingPending || app.pending) return;
    app.loadingPending = true;
    try {
      const data = await api("/api/pending");
      const pending = (data.pending || [])[0];
      if (pending) showConfirm(pending);
    } catch (error) {
      toast("Impossibile leggere la richiesta di conferma: " + error.message, true);
    } finally {
      app.loadingPending = false;
    }
  }

  // ---------------------------------------------------------------- conferme
  function showConfirm(pending) {
    if (!pending || !pending.pending_id) return;
    app.pending = pending;
    app.pendingSince = Date.now();

    const riskLevel = pending.risk || "B";
    text("confirmRisk", riskLevel);
    const risk = $("confirmRisk");
    if (risk) risk.className = "risk " + riskLevel;
    text("confirmTool", pending.tool || "Strumento");
    text("confirmReason", pending.reason || "Operazione con impatto da confermare.");
    text("confirmArgs", pretty(pending.args || {}));
    text("confirmConsequences", pending.consequences || "Nessuna conseguenza specificata.");
    text("confirmUndo", pending.undo || "Nessuna procedura di annullamento automatica.");

    const approve = $("confirmApprove");
    const cancel = $("confirmCancel");
    if (approve) approve.disabled = false;
    if (cancel) cancel.disabled = false;

    openModal($("confirmModal"), cancel);
    renderCore();
  }

  function closeConfirm() {
    const modal = $("confirmModal");
    if (modal) closeModal(modal);
    app.pending = null;
    app.pendingSince = 0;
    renderCore();
  }

  async function resolveConfirmation(approved) {
    if (!app.pending || app.resolving) return;
    const pendingId = app.pending.pending_id;
    app.resolving = true;
    app.busy = true;
    updateControls();
    ensureFastPoll();

    const approve = $("confirmApprove");
    const cancel = $("confirmCancel");
    if (approve) approve.disabled = true;
    if (cancel) cancel.disabled = true;

    try {
      const result = await post("/api/confirm", { pending_id: pendingId, approved: approved });
      closeConfirm();
      await afterTurn(result);
    } catch (error) {
      toast("Conferma non inviata: " + error.message, true);
      markError("Conferma non inviata: " + error.message);
      if (approve) approve.disabled = false;
      if (cancel) cancel.disabled = false;
    } finally {
      app.resolving = false;
      app.busy = false;
      setPaused(false);
      updateControls();
      renderCore();
      await refreshState();
      ensureFastPoll();
    }
  }

  // ------------------------------------------------------------------ turni
  async function afterTurn(result) {
    if (!isObject(result)) return;
    if (result.session_id) setSession(result.session_id);

    let messages = [];
    try {
      messages = await loadTranscript(app.sessionId);
    } catch (error) {
      toast("Cronologia non disponibile: " + error.message, true);
    }

    const last = messages.length ? messages[messages.length - 1] : null;
    const storedReply = Boolean(last && last.role === "assistant" && last.content === result.reply);

    if (result.status === "error" && result.reply && !storedReply) {
      appendError(result.reply);
      markError(result.reply);
    } else if (result.status === "error" && result.reply) {
      markError(result.reply);
    } else if (result.reply && !storedReply) {
      // Anche il preambolo di una conferma va mostrato: il backend lo include
      // nella risposta ma non lo salva nella trascrizione.
      appendMessage("assistant", result.reply, new Date().toISOString());
    }

    if (result.fallback_reason && last && last.role === "assistant") {
      const lastNode = $("messages") && $("messages").lastElementChild;
      if (lastNode) {
        lastNode.appendChild(
          node("div", "note", "Motore primario non disponibile: " + result.fallback_reason)
        );
        scrollMessages();
      }
    }

    if (result.pending) {
      showConfirm(result.pending);
    } else if (!result.status || result.status !== "error") {
      if (app.speak && result.reply) speakText(result.reply);
    }
  }

  async function sendMessage(rawText) {
    const content = String(rawText || "").trim();
    if (!content || app.busy) return;

    clearError();
    app.busy = true;
    app.listening = false;
    setPaused(true);
    updateControls();
    appendMessage("user", content, new Date().toISOString());
    setTyping(true);
    renderCore();
    ensureFastPoll();

    try {
      const result = await post("/api/chat", {
        message: content,
        session_id: app.sessionId || undefined,
      });
      await afterTurn(result);
    } catch (error) {
      appendError("Non riesco a contattare il cervello di Amy: " + error.message);
      toast(error.message, true);
      markError("Chat non disponibile: " + error.message);
    } finally {
      app.busy = false;
      setTyping(false);
      setPaused(false);
      updateControls();
      renderCore();
      await refreshState();
      ensureFastPoll();
    }
  }

  async function newSession() {
    if (app.busy) return;
    clearError();
    try {
      const data = await post("/api/new_session", { title: "Dashboard" });
      setSession(data.session_id);
      showEmptyState("Nuova sessione pronta. Scrivi la prima richiesta ad Amy.");
      toast("Nuova sessione avviata.");
      await refreshState();
    } catch (error) {
      toast("Impossibile creare una nuova sessione: " + error.message, true);
      markError("Nuova sessione non creata: " + error.message);
    }
  }

  // ------------------------------------------------------------------- voce
  async function speakText(value) {
    const content = String(value || "").trim();
    if (!content) return;
    clearError();
    try {
      const result = await post("/api/speak", { text: content });
      if (result.spoken === false) {
        toast("Voce non disponibile: " + String(result.reason || "sintesi disattivata"), true);
        return;
      }
      app.speaking = true;
      app.speakingDeadline = Date.now() + 3500;
      renderCore();
      ensureFastPoll();
      await refreshState();
    } catch (error) {
      toast("Voce non disponibile: " + error.message, true);
    }
  }

  async function stopVoice() {
    app.speaking = false;
    app.speakingDeadline = 0;
    renderCore();
    try {
      await post("/api/voice/stop", {});
      toast("Sintesi vocale interrotta.");
      await refreshState();
    } catch (error) {
      toast("Impossibile interrompere la voce: " + error.message, true);
    }
  }

  async function greet() {
    if (app.busy) return;
    clearError();
    try {
      const data = await post("/api/voice/greet", {});
      if (data && data.spoken) {
        toast("Amy: " + (data.text || ""));
      } else {
        toast("Saluto non pronunciato: " + ((data && data.reason) || "sintesi non disponibile"), true);
      }
      await refreshState();
    } catch (error) {
      toast("Saluto non riuscito: " + error.message, true);
    }
  }

  async function listen() {
    if (app.busy) return;
    if (!app.voiceReady) {
      toast("Microfono o riconoscimento vocale non disponibili. La chat testuale funziona comunque.", true);
      return;
    }

    clearError();
    app.listening = true;
    app.busy = true;
    setPaused(true);
    updateControls();
    const mic = $("micBtn");
    if (mic) mic.classList.add("listening");
    renderCore();
    ensureFastPoll();

    try {
      const data = await post("/api/voice/listen", { seconds: LISTEN_SECONDS });
      const transcript = String(data.text || "").trim();
      const input = $("composerInput");
      if (!transcript) {
        toast("Nessun parlato rilevato. Riprova avvicinandoti al microfono.", true);
      } else if (input) {
        input.value = transcript;
        input.focus();
        toast("Trascrizione pronta: controlla il testo e premi Invia.");
      }
    } catch (error) {
      toast("Ascolto non disponibile: " + error.message, true);
      markError("Ascolto non disponibile: " + error.message);
    } finally {
      app.listening = false;
      app.busy = false;
      if (mic) mic.classList.remove("listening");
      setPaused(false);
      updateControls();
      renderCore();
      await refreshState();
      ensureFastPoll();
    }
  }

  async function toggleWake() {
    if (app.busy) return;
    const running = app.wakeRunning;
    clearError();
    try {
      const data = await post(running ? "/api/voice/wake/stop" : "/api/voice/wake/start", {});
      const wake = data && isObject(data.voice) && isObject(data.voice.wake_word) ? data.voice.wake_word : {};
      app.wakeRunning = Boolean(wake.running);
      toast(
        app.wakeRunning
          ? "Ascolto attivo: di' «Amy» seguito dal comando. Si ferma con lo stesso pulsante."
          : "Ascolto continuo fermato."
      );
      await refreshState();
    } catch (error) {
      toast("Ascolto continuo non disponibile: " + error.message, true);
      markError("Ascolto continuo non disponibile: " + error.message);
      await refreshState();
    }
  }

  // ------------------------------------------------------------------ robot
  async function robotCommand(path, reason) {
    clearError();
    try {
      await post(path, { reason: reason });
      toast(path.endsWith("estop") ? "E-stop software attivato." : "Arresto controllato inviato.");
      await refreshState();
    } catch (error) {
      toast("Comando robot non riuscito: " + error.message, true);
      markError("Comando robot non riuscito: " + error.message);
    }
  }

  // ------------------------------------------------------------- accessibilità
  function focusable(modal) {
    return Array.from(modal.querySelectorAll(
      'button:not([disabled]), [href], input:not([disabled]), textarea:not([disabled]), select:not([disabled]), summary, [tabindex]:not([tabindex="-1"])'
    )).filter((element) => element.offsetParent !== null || element === document.activeElement);
  }

  function openModal(modal, initialFocus) {
    if (!modal) return;
    app.modalReturnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    app.modal = modal;
    modal.hidden = false;
    window.setTimeout(() => {
      if (modal.hidden) return;
      const target = initialFocus || focusable(modal)[0] || modal;
      if (target && typeof target.focus === "function") target.focus();
    }, 0);
  }

  function closeModal(modal) {
    if (!modal) return;
    modal.hidden = true;
    if (app.modal === modal) app.modal = null;
    const previous = app.modalReturnFocus;
    app.modalReturnFocus = null;
    if (previous && document.contains(previous) && typeof previous.focus === "function") {
      previous.focus();
    }
  }

  function trapFocus(event) {
    if (!app.modal || app.modal.hidden || event.key !== "Tab") return;
    const items = focusable(app.modal);
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function handleEscape(event) {
    if (event.key !== "Escape") return;
    const confirm = $("confirmModal");
    const settings = $("settingsModal");
    if (confirm && !confirm.hidden) {
      event.preventDefault();
      resolveConfirmation(false);
    } else if (settings && !settings.hidden) {
      event.preventDefault();
      closeModal(settings);
    }
  }

  // ------------------------------------------------------------------- moto
  function applyMotion(enabled, persist) {
    app.motion = Boolean(enabled);
    document.documentElement.dataset.motion = app.motion ? "full" : "off";
    const button = $("motionBtn");
    if (button) {
      button.textContent = app.motion ? "Movimento: attivo" : "Movimento: ridotto";
      button.setAttribute("aria-pressed", app.motion ? "true" : "false");
      button.title = app.motion
        ? "Riduci le animazioni decorative"
        : "Riattiva le animazioni decorative";
    }
    if (persist) writeSetting(MOTION_KEY, app.motion ? "full" : "off");
  }

  function initMotion() {
    const stored = readSetting(MOTION_KEY);
    const media = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;
    if (stored === "off" || stored === "full") {
      applyMotion(stored === "full", false);
    } else {
      applyMotion(!(media && media.matches), false);
    }
    if (media && typeof media.addEventListener === "function") {
      media.addEventListener("change", (event) => {
        if (!readSetting(MOTION_KEY)) applyMotion(!event.matches, false);
      });
    }
  }

  // ------------------------------------------------------------ schermo pieno
  function fullscreenElement() {
    return document.fullscreenElement || document.webkitFullscreenElement || null;
  }

  async function toggleFullscreen() {
    const root = document.documentElement;
    try {
      if (fullscreenElement()) {
        const exit = document.exitFullscreen || document.webkitExitFullscreen;
        if (exit) await exit.call(document);
      } else {
        const enter = root.requestFullscreen || root.webkitRequestFullscreen;
        if (!enter) {
          toast("Questo browser non espone lo schermo intero. Usa il controllo nativo di macOS.", true);
          return;
        }
        await enter.call(root);
      }
    } catch (error) {
      toast("Schermo intero non disponibile: " + error.message, true);
    }
  }

  function onFullscreenChange() {
    const active = Boolean(fullscreenElement());
    document.documentElement.classList.toggle("is-fullscreen", active);
    const button = $("fullscreenBtn");
    if (button) {
      button.textContent = active ? "Esci da schermo intero" : "Schermo intero";
      button.setAttribute("aria-pressed", active ? "true" : "false");
    }
  }

  // ---------------------------------------------------------------- controlli
  function updateControls() {
    const send = $("sendBtn");
    const mic = $("micBtn");
    const newSessionButton = $("newSessionBtn");
    const wake = $("wakeBtn");
    if (wake) {
      wake.textContent = app.wakeRunning ? "Ferma ascolto" : "Ascolta «Amy»";
      wake.setAttribute("aria-pressed", app.wakeRunning ? "true" : "false");
      wake.disabled = app.busy || (!app.wakeAvailable && !app.wakeRunning);
      wake.title = app.wakeRunning
        ? "Interrompi l'ascolto della parola «Amy»"
        : app.wakeAvailable
          ? "Ascolta la parola «Amy» dal microfono del Mac, poi il comando"
          : "Servono microfono e trascrizione locale per l'ascolto continuo";
    }
    if (send) send.disabled = app.busy;
    if (mic) {
      mic.disabled = app.busy || !app.voiceReady;
      mic.title = app.voiceReady
        ? "Ascolta dal microfono del Mac per " + LISTEN_SECONDS + " secondi"
        : "Microfono o riconoscimento vocale non configurati";
    }
    if (newSessionButton) newSessionButton.disabled = app.busy;
  }

  function updateSpeakToggle() {
    const toggle = $("speakToggle");
    if (toggle) toggle.checked = app.speak;
  }

  function bind() {
    const form = $("chatForm");
    const input = $("composerInput");

    if (form) {
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        if (app.busy) {
          toast("Attendi la fine dell'operazione in corso.", true);
          return;
        }
        const content = input ? input.value : "";
        if (!String(content).trim()) return;
        if (input) input.value = "";
        sendMessage(content);
      });
    }

    if (input) {
      input.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
          event.preventDefault();
          if (form) form.requestSubmit();
        }
      });
    }

    const mic = $("micBtn");
    if (mic) mic.addEventListener("click", listen);

    const wake = $("wakeBtn");
    if (wake) wake.addEventListener("click", toggleWake);

    const stop = $("stopBtn");
    if (stop) stop.addEventListener("click", stopVoice);

    const greetButton = $("greetBtn");
    if (greetButton) greetButton.addEventListener("click", greet);

    const newSessionButton = $("newSessionBtn");
    if (newSessionButton) newSessionButton.addEventListener("click", newSession);

    const newInteraction = $("newInteractionBtn");
    if (newInteraction) {
      newInteraction.addEventListener("click", () => {
        clearError();
        if (input) input.focus();
        toast("Scrivi la tua richiesta ad Amy.");
      });
    }

    const estop = $("estopBtn");
    if (estop) estop.addEventListener("click", () => robotCommand("/api/robot/estop", "dashboard"));

    const robotStop = $("robotStopBtn");
    if (robotStop) robotStop.addEventListener("click", () => robotCommand("/api/robot/stop", "dashboard"));

    const approve = $("confirmApprove");
    if (approve) approve.addEventListener("click", () => resolveConfirmation(true));

    const cancel = $("confirmCancel");
    if (cancel) cancel.addEventListener("click", () => resolveConfirmation(false));

    const settingsButton = $("settingsBtn");
    const settingsModal = $("settingsModal");
    const settingsClose = $("settingsClose");
    if (settingsButton) {
      settingsButton.addEventListener("click", () => openModal(settingsModal, settingsClose));
    }
    if (settingsClose) {
      settingsClose.addEventListener("click", () => closeModal(settingsModal));
    }
    if (settingsModal) {
      settingsModal.addEventListener("click", (event) => {
        if (event.target === settingsModal) closeModal(settingsModal);
      });
    }

    const confirmModal = $("confirmModal");
    if (confirmModal) {
      confirmModal.addEventListener("click", (event) => {
        if (event.target === confirmModal) {
          toast("Usa «Annulla» o «Autorizza» per rispondere alla richiesta.", true);
        }
      });
    }

    const motionButton = $("motionBtn");
    if (motionButton) {
      motionButton.addEventListener("click", () => {
        applyMotion(!app.motion, true);
        toast(app.motion ? "Animazioni decorative attive." : "Animazioni decorative ridotte.");
      });
    }

    const fullscreenButton = $("fullscreenBtn");
    if (fullscreenButton) fullscreenButton.addEventListener("click", toggleFullscreen);

    const speakToggle = $("speakToggle");
    if (speakToggle) {
      app.speak = readSetting(SPEAK_KEY) === "1";
      updateSpeakToggle();
      speakToggle.addEventListener("change", (event) => {
        app.speak = Boolean(event.target.checked);
        writeSetting(SPEAK_KEY, app.speak ? "1" : "0");
        toast(app.speak ? "Amy pronuncerà le risposte." : "Risposte solo testuali.");
      });
    }

    document.addEventListener("keydown", trapFocus);
    document.addEventListener("keydown", handleEscape);
    document.addEventListener("fullscreenchange", onFullscreenChange);
    document.addEventListener("webkitfullscreenchange", onFullscreenChange);

    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) {
        refreshState();
        ensureFastPoll();
      }
    });
  }

  async function start() {
    bind();
    initMotion();
    renderCore();
    showEmptyState("Caricamento della sessione locale…");
    text("footerStatus", "caricamento…");

    try {
      const data = await api("/api/state");
      applyState(data);
      if (!app.sessionId && data.assistant && data.assistant.session_id) {
        setSession(data.assistant.session_id);
      }
      if (app.sessionId) await loadTranscript(app.sessionId);
      if (Number(data.pending_confirmations || 0) > 0) await loadPending();
      clearError();
    } catch (error) {
      showEmptyState("Dashboard non raggiungibile. Controlla che il server Amy sia in esecuzione.");
      appendError(error.message);
      markError("Dashboard non raggiungibile: " + error.message);
    }

    app.pollTimer = window.setInterval(refreshState, BASE_POLL_MS);
    ensureFastPoll();
  }

  start();
})();
