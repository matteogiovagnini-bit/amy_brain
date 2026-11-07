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
  const MODULES_POLL_MS = 30000;
  // Il calendario interroga Calendar.app via AppleScript: si rilegge ogni
  // due minuti, non a ogni poll dello stato, e sempre su richiesta esplicita.
  const CALENDAR_POLL_MS = 120000;
  const PROJECT_POLL_MS = 60000;

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
    calendarTimer: 0,
    calendarLastFetch: 0,
    calendarLoading: false,
    projectTimer: 0,
    projectLastFetch: 0,
    projectLoading: false,
    modulesTimer: 0,
    modulesLastFetch: 0,
    modulesLoading: false,
    permissionsLoading: false,
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
    lastTranscriptSignature: "",
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
    app.lastTranscriptSignature = transcriptSignature(messages);
    return messages;
  }

  // La trascrizione è limitata agli ultimi 100 messaggi: confrontare solo la
  // lunghezza non basta, perché una volta raggiunto il limite resta 100 anche
  // quando arrivano nuovi messaggi. La firma include l'ultimo messaggio.
  function transcriptSignature(messages) {
    if (!messages.length) return "0";
    const last = messages[messages.length - 1];
    return [
      messages.length,
      last.created_at || "",
      last.role || "",
      String(last.content || "").slice(0, 40),
    ].join("|");
  }

  // Durante l'ascolto continuo i turni vocali avvengono in background: il
  // pannello va aggiornato anche senza un invio dal campo di testo.
  async function syncTranscriptIfNeeded() {
    if (!app.sessionId || document.hidden) return;
    try {
      const data = await api("/api/transcript?session=" + encodeURIComponent(app.sessionId));
      const messages = (data.messages || []).filter(
        (item) => item && (item.role === "user" || item.role === "assistant") && typeof item.content === "string"
      );
      const signature = transcriptSignature(messages);
      if (signature !== app.lastTranscriptSignature) {
        renderTranscript(messages);
        app.lastTranscriptSignature = signature;
      }
    } catch (error) {
      // Silenzioso: il polling riproverà al ciclo successivo.
    }
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
    const voiceState = String((data && data.voice && data.voice.state) || "");
    if (voiceState === "processing") {
      return {
        state: "processing",
        label: "Elaborazione",
        activity: "Il motore IA sta elaborando la richiesta",
        hint: "La chat resta utilizzabile: attendo la risposta e mostro solo esiti reali.",
      };
    }
    if (voiceState === "conversation_active" || voiceState === "waiting_for_input") {
      return {
        state: "conversation",
        label: "Conversazione",
        activity: "Amy ti ascolta senza chiedere di nuovo «Amy»",
        hint: "Rispondi pure con poche parole. Di' «basta» per chiudere la conversazione.",
      };
    }
    if (voiceState === "interrupted") {
      return {
        state: "interrupted",
        label: "Interrotta",
        activity: "Hai richiamato Amy mentre parlava",
        hint: "Amy ha fermato la voce. Di' il nuovo comando senza ripetere il suo nome.",
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
        label: "In attesa di «Amy»",
        activity: "Di' «Amy» per iniziare una conversazione",
        hint: "Dopo la wake word non serve ripeterla. Di' «Amy» mentre parla per interromperla.",
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
      text("voiceNote", "Ascolto continuo attivo: di' «Amy» per iniziare, poi rispondi senza ripeterlo. Di' «Amy» mentre parla per interromperla. Fermalo con «Ferma ascolto»." + duplex);
    } else if (greeting.enabled && greetingText) {
      text("voiceNote", "All'avvio Amy dice: «" + greetingText + "». Usa «Ripeti saluto» per riascoltarlo.");
    } else if (voice.ready_for_voice_commands) {
      text("voiceNote", "Microfono e trascrizione locali disponibili. L'ascolto continuo è spento: avvialo con «Ascolta «Amy»».");
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

  function renderPersonal(data) {
    const tasks = Array.isArray(data && data.tasks) ? data.tasks : [];
    const notes = Array.isArray(data && data.notes) ? data.notes : [];
    tag("personalTag", tasks.length + " attività · " + notes.length + " note", "ok");

    const tasksContainer = $("tasksList");
    if (tasksContainer) {
      tasksContainer.replaceChildren();
      if (!tasks.length) {
        tasksContainer.appendChild(node("div", "empty", "Nessuna attività."));
      } else {
        tasks.slice(0, 6).forEach((task) => {
          const row = node("div", "fact");
          row.appendChild(node("b", "", String(task.title || "Senza titolo")));
          const due = task.due_at ? " · scadenza " + String(task.due_at).slice(0, 16) : "";
          row.appendChild(node("span", "", String(task.status || "aperta") + " · " + String(task.priority || "normale") + due));
          tasksContainer.appendChild(row);
        });
      }
    }

    const notesContainer = $("notesList");
    if (notesContainer) {
      notesContainer.replaceChildren();
      if (!notes.length) {
        notesContainer.appendChild(node("div", "empty", "Nessuna nota."));
      } else {
        notes.slice(0, 6).forEach((note) => {
          const row = node("div", "fact");
          row.appendChild(node("b", "", String(note.title || "Nota")));
          row.appendChild(node("span", "", String(note.body || "").slice(0, 120)));
          notesContainer.appendChild(row);
        });
      }
    }
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

  // -------------------------------------------------------------- calendario
  function calendarDay(value, today) {
    const day = String(value || "").slice(0, 10);
    if (day === today) return "Oggi";
    const parts = day.split("-");
    if (parts.length !== 3) return day || "data sconosciuta";
    const parsed = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
    if (Number.isNaN(parsed.getTime())) return parts[2] + "/" + parts[1];
    return parsed.toLocaleDateString("it-IT", { weekday: "short", day: "2-digit", month: "2-digit" });
  }

  function calendarUnavailable(message) {
    tag("calendarTag", "non disponibile", "bad");
    const container = $("calendarEvents");
    if (!container) return;
    container.replaceChildren();
    container.appendChild(node("div", "empty", message));
  }

  function renderCalendar(data) {
    const payload = isObject(data) ? data : {};
    const events = Array.isArray(payload.events) ? payload.events : [];
    const days = Number(payload.days || 7);
    const failed = Number(payload.failed_days || 0);

    if (!payload.available) {
      calendarUnavailable(payload.reason
        ? "Calendario non disponibile: " + String(payload.reason)
        : "Calendario non disponibile.");
      text("calendarNote", "Nessun dato inventato: la lettura di calendar.events non è riuscita.");
      return;
    }

    tag("calendarTag", payload.calendar || "calendario locale", failed > 0 ? "warn" : "ok");
    text("calendarNote", "Letti da Calendar.app con calendar.events sui prossimi " + days
      + " giorni. Nessun dato remoto."
      + (failed > 0 ? " Lettura parziale: " + failed + " giorni non disponibili." : ""));

    const container = $("calendarEvents");
    if (!container) return;
    container.replaceChildren();
    if (!events.length) {
      container.appendChild(node("div", "empty", "Nessun appuntamento nei prossimi " + days + " giorni."));
      return;
    }

    const today = String(payload.date || "");
    events.forEach((event) => {
      const start = String(event.start || "");
      const row = node("div", "calendar-event");
      row.appendChild(node("span", "cal-when",
        calendarDay(start, today) + " · " + (start.slice(11, 16) || "orario non disponibile")));
      row.appendChild(node("span", "cal-title", String(event.title || "Senza titolo")));
      if (event.calendar) row.title = String(event.calendar);
      container.appendChild(row);
    });
  }

  async function refreshCalendar(force) {
    if (app.calendarLoading) return;
    const now = Date.now();
    if (!force && app.calendarLastFetch && now - app.calendarLastFetch < CALENDAR_POLL_MS) return;
    app.calendarLoading = true;
    try {
      const data = await api("/api/calendar/upcoming");
      app.calendarLastFetch = Date.now();
      renderCalendar(data);
    } catch (error) {
      calendarUnavailable("Calendario non disponibile: " + error.message);
    } finally {
      app.calendarLoading = false;
    }
  }

  // --------------------------------------------------------------- progetto
  function renderProject(payload) {
    const statusResult = isObject(payload && payload.status) ? payload.status : {};
    const diffResult = isObject(payload && payload.diff) ? payload.diff : {};
    const status = isObject(statusResult.data) ? statusResult.data : {};
    const diff = isObject(diffResult.data) ? diffResult.data : {};
    const available = Boolean(payload && payload.available) && Boolean(statusResult.ok);
    if (!available) {
      tag("projectTag", "non disponibile", "muted");
      text("projectBranch", "Non disponibile");
      text("projectModified", "Non disponibile");
      text("projectCommit", "Non disponibile");
      const container = $("projectDiff");
      if (container) container.textContent = String(
        (statusResult.message || (payload && payload.error) || "Modulo Developer non disponibile.")
      );
      return;
    }
    const changes = Number(status.modified || 0) + Number(status.untracked || 0);
    tag("projectTag", status.clean ? "pulito" : changes + " modifiche", status.clean ? "ok" : "warn");
    text("projectBranch", status.branch || "non disponibile");
    text("projectModified",
      Number(status.modified || 0) + " modificati · " + Number(status.untracked || 0) + " non tracciati");
    const commit = isObject(status.last_commit) ? status.last_commit : {};
    text("projectCommit",
      (commit.hash ? String(commit.hash) + " · " : "") + String(commit.subject || "non disponibile"));
    const container = $("projectDiff");
    if (!container) return;
    const stat = String(diff.stat || "").trim();
    container.textContent = stat || "Nessuna modifica da mostrare.";
  }

  async function loadProject(force) {
    if (app.projectLoading) return;
    const now = Date.now();
    if (!force && app.projectLastFetch && now - app.projectLastFetch < PROJECT_POLL_MS) return;
    app.projectLoading = true;
    try {
      const data = await api("/api/dev/status");
      app.projectLastFetch = Date.now();
      renderProject(data);
    } catch (error) {
      renderProject({ available: false, status: { ok: false, message: error.message } });
    } finally {
      app.projectLoading = false;
    }
  }

  // ---------------------------------------------------------------- moduli
  function moduleLabel(state) {
    const labels = {
      disabled: "disabilitato",
      initializing: "avvio",
      ready: "pronto",
      busy: "occupato",
      degraded: "parziale",
      offline: "offline",
      error: "errore",
    };
    return labels[state] || "sconosciuto";
  }

  function moduleTone(state) {
    if (state === "ready" || state === "busy") return "ok";
    if (state === "disabled") return "muted";
    if (state === "error") return "bad";
    return "warn";
  }

  function renderModules(data) {
    const modules = data && Array.isArray(data.modules) ? data.modules : [];
    tag("modulesTag", modules.length ? modules.length + " moduli" : "non disponibile", modules.length ? "ok" : "bad");
    const container = $("modulesList");
    if (!container) return;
    container.replaceChildren();
    if (!modules.length) {
      container.appendChild(node("div", "empty", "Nessun modulo registrato."));
      return;
    }
    modules.forEach((item) => {
      const manifest = isObject(item.manifest) ? item.manifest : {};
      const status = isObject(item.status) ? item.status : {};
      const state = String(status.state || "error");
      const name = String(manifest.name || "");
      const row = node("div", "module-row");
      const head = node("div", "module-head");
      head.appendChild(node("strong", "", String(manifest.title || name || "Modulo")));
      head.appendChild(node("span", "tag " + moduleTone(state), moduleLabel(state)));
      row.appendChild(head);
      if (manifest.description) row.appendChild(node("p", "module-detail", String(manifest.description)));
      if (status.detail) row.appendChild(node("p", "module-detail", String(status.detail)));
      const actions = node("div", "module-actions");
      const toolCount = Array.isArray(manifest.tools) ? manifest.tools.length : 0;
      actions.appendChild(node("span", "module-tools", toolCount + (toolCount === 1 ? " strumento" : " strumenti")));
      const toggle = node("button", "ghost small", item.enabled ? "Disabilita" : "Abilita");
      toggle.type = "button";
      toggle.disabled = !manifest.optional || !name;
      toggle.title = manifest.optional
        ? (item.enabled ? "Disabilita il modulo e i suoi strumenti" : "Abilita il modulo e i suoi strumenti")
        : "Modulo essenziale: non può essere disabilitato";
      toggle.addEventListener("click", () => toggleModule(name, !item.enabled));
      actions.appendChild(toggle);
      row.appendChild(actions);
      container.appendChild(row);
    });
  }

  async function loadModules() {
    if (app.modulesLoading) return;
    app.modulesLoading = true;
    try {
      const data = await api("/api/modules");
      app.modulesLastFetch = Date.now();
      renderModules(data);
    } catch (error) {
      tag("modulesTag", "non disponibile", "bad");
      const container = $("modulesList");
      if (container) {
        container.replaceChildren();
        container.appendChild(node("div", "empty", "Moduli non disponibili: " + error.message));
      }
    } finally {
      app.modulesLoading = false;
    }
  }

  async function loadPermissions() {
    if (app.permissionsLoading) return;
    app.permissionsLoading = true;
    try {
      const data = await api("/api/permissions");
      renderPermissions(data);
    } catch (error) {
      tag("permissionsTag", "non disponibile", "bad");
      const container = $("permissionsList");
      if (container) {
        container.replaceChildren();
        container.appendChild(node("div", "empty", "Permessi non disponibili: " + error.message));
      }
    } finally {
      app.permissionsLoading = false;
    }
  }

  function renderPermissions(data) {
    const capabilities = data && Array.isArray(data.capabilities) ? data.capabilities : [];
    tag("permissionsTag", capabilities.length ? capabilities.length + " capacità" : "non disponibile", capabilities.length ? "ok" : "bad");
    const container = $("permissionsList");
    if (!container) return;
    container.replaceChildren();
    if (!capabilities.length) {
      container.appendChild(node("div", "empty", "Nessuna capacità dichiarata."));
      return;
    }
    capabilities.forEach((item) => {
      const capability = String(item.capability || "");
      if (!capability) return;
      const row = node("div", "module-row");
      const head = node("div", "module-head");
      head.appendChild(node("strong", "", capability));
      head.appendChild(node("span", "tag " + (item.revoked ? "bad" : "ok"), item.revoked ? "revocata" : "attiva"));
      row.appendChild(head);
      row.appendChild(node("p", "module-detail", "Modulo " + String(item.module || "?") + " · " + String(item.title || "")));
      const actions = node("div", "module-actions");
      actions.appendChild(node("span", "module-tools", "capacità"));
      const toggle = node("button", "ghost small", item.revoked ? "Ripristina" : "Revoca");
      toggle.type = "button";
      toggle.title = item.revoked ? "Ripristina la capacità" : "Blocca gli strumenti di questa capacità";
      toggle.addEventListener("click", () => togglePermission(capability, !item.revoked));
      actions.appendChild(toggle);
      row.appendChild(actions);
      container.appendChild(row);
    });
  }

  async function togglePermission(capability, revoke) {
    if (!capability) return;
    clearError();
    try {
      const path = revoke ? "/api/permissions/revoke" : "/api/permissions/restore";
      const data = await post(path, { capability: capability });
      toast(revoke ? "Capacità revocata: " + capability : "Capacità ripristinata: " + capability);
      if (data && isObject(data.permissions)) renderPermissions(data.permissions);
      await refreshState();
    } catch (error) {
      toast("Permesso non modificato: " + error.message, true);
      markError("Permesso non modificato: " + error.message);
    }
  }

  async function toggleModule(name, enabled) {
    if (!name) return;
    clearError();
    try {
      const data = await post("/api/modules/" + encodeURIComponent(name) + "/enabled", { enabled: Boolean(enabled) });
      const result = data && isObject(data.result) ? data.result : {};
      toast("Modulo " + name + (result.enabled ? " abilitato." : " disabilitato."));
      await refreshState();
      await loadModules();
    } catch (error) {
      toast("Modulo non modificato: " + error.message, true);
      markError("Modulo non modificato: " + error.message);
    }
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
    renderPersonal(data);
    renderActivities(data);
    renderTools(data.tools || []);
    renderSettings(data);
    updateFooter();
    updateControls();
    renderCore();
    ensureFastPoll();

    const pendingCount = Number(data.pending_confirmations || 0);
    if (app.pending && pendingCount === 0) {
      // La conferma è stata risolta altrove (per esempio a voce).
      closeConfirm();
    } else if (!app.pending && !app.busy && !app.resolving && pendingCount > 0) {
      loadPending();
    }
  }

  async function refreshState() {
    if (app.refreshing || document.hidden) return;
    app.refreshing = true;
    try {
      const data = await api("/api/state");
      applyState(data);
      if (app.wakeRunning) await syncTranscriptIfNeeded();
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

    const permissionsRefreshButton = $("permissionsRefreshBtn");
    if (permissionsRefreshButton) {
      permissionsRefreshButton.addEventListener("click", () => loadPermissions());
    }

    const modulesRefreshButton = $("modulesRefreshBtn");
    if (modulesRefreshButton) {
      modulesRefreshButton.addEventListener("click", () => loadModules());
    }

    const calendarRefreshButton = $("calendarRefreshBtn");
    if (calendarRefreshButton) {
      calendarRefreshButton.addEventListener("click", () => refreshCalendar(true));
    }

    const projectRefreshButton = $("projectRefreshBtn");
    if (projectRefreshButton) {
      projectRefreshButton.addEventListener("click", () => loadProject(true));
    }

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
        refreshCalendar();
        loadProject();
        ensureFastPoll();
      }
    });
  }

  async function start() {
    bind();
    initMotion();
    renderCore();
    // Il self-test dell'app nativa apre la dashboard con `?selftest=1`: la
    // cronologia non viene caricata, così la prima risposta in chat è quella
    // del test e non una risposta vecchia della sessione.
    const selfTest = new URLSearchParams(window.location.search).get("selftest") === "1";
    showEmptyState(selfTest ? "Verifica automatica in corso…" : "Caricamento della sessione locale…");
    text("footerStatus", "caricamento…");

    try {
      const data = await api("/api/state");
      applyState(data);
      if (!app.sessionId && data.assistant && data.assistant.session_id) {
        setSession(data.assistant.session_id);
      }
      if (app.sessionId && !selfTest) await loadTranscript(app.sessionId);
      if (Number(data.pending_confirmations || 0) > 0) await loadPending();
      clearError();
    } catch (error) {
      showEmptyState("Dashboard non raggiungibile. Controlla che il server Amy sia in esecuzione.");
      appendError(error.message);
      markError("Dashboard non raggiungibile: " + error.message);
    }

    // Il calendario non blocca l'avvio: parte in background e ha un suo poll
    // lento, così la chat resta immediatamente utilizzabile.
    refreshCalendar(true);
    loadProject(true);
    loadModules();
    loadPermissions();
    app.pollTimer = window.setInterval(refreshState, BASE_POLL_MS);
    app.modulesTimer = window.setInterval(loadModules, MODULES_POLL_MS);
    app.calendarTimer = window.setInterval(() => refreshCalendar(true), CALENDAR_POLL_MS);
    app.projectTimer = window.setInterval(() => loadProject(true), PROJECT_POLL_MS);
    ensureFastPoll();
  }

  start();
})();
