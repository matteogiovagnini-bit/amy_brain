// Amy Core — applicazione macOS nativa.
//
// Finestra propria (AppKit) con WKWebView che mostra la dashboard locale di
// Amy Brain. Il backend Python viene avviato come processo figlio, legato
// solo a 127.0.0.1, e terminato alla chiusura dell'app.
//
// Nessuna dipendenza di terze parti: solo framework di sistema macOS
// (AppKit, WebKit, Foundation). Nessun servizio a pagamento, nessun account.

import AppKit
import Darwin
import WebKit

// MARK: - Configurazione locale

/// Percorsi e interprete usati dall'app, salvati in `~/.amy/app.json`.
struct LocalConfig: Codable {
    var repoPath: String
    var python: String
}

enum Settings {
    static var fileURL: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".amy", isDirectory: true)
            .appendingPathComponent("app.json")
    }

    static func load() -> LocalConfig? {
        guard let data = try? Data(contentsOf: fileURL) else { return nil }
        return try? JSONDecoder().decode(LocalConfig.self, from: data)
    }

    static func save(_ config: LocalConfig) {
        let directory = fileURL.deletingLastPathComponent()
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        guard let data = try? encoder.encode(config) else { return }
        try? data.write(to: fileURL)
    }
}

/// Verifica che una cartella contenga davvero il repository di Amy Brain.
func isValidRepository(path: String) -> Bool {
    let manager = FileManager.default
    var isDirectory: ObjCBool = false
    guard manager.fileExists(atPath: path, isDirectory: &isDirectory), isDirectory.boolValue else {
        return false
    }
    let required = ["amy/ui/server.py", "amy/__init__.py", "amy/cli.py"]
    for item in required where !manager.fileExists(atPath: path + "/" + item) {
        return false
    }
    return true
}

// MARK: - Log

enum AppLog {
    /// Log dell'app stessa.
    static let url: URL = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent(".amy", isDirectory: true)
        .appendingPathComponent("app.log")

    /// Log del backend Python: file separato, così le due scritture non si
    /// sovrappongono.
    static let backendURL: URL = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent(".amy", isDirectory: true)
        .appendingPathComponent("backend.log")

    static func write(_ message: String) {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd HH:mm:ss"
        let line = "[" + formatter.string(from: Date()) + "] " + message + "\n"
        append(line, to: url)
    }

    static func append(_ line: String, to target: URL) {
        let directory = target.deletingLastPathComponent()
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        if !FileManager.default.fileExists(atPath: target.path) {
            FileManager.default.createFile(atPath: target.path, contents: nil)
        }
        if let handle = try? FileHandle(forWritingTo: target) {
            handle.seekToEndOfFile()
            handle.write(Data(line.utf8))
            try? handle.close()
        } else {
            try? Data(line.utf8).write(to: target)
        }
    }
}

// MARK: - Controllo del backend

/// Verifica HTTP senza passare da ATS: connessione TCP a 127.0.0.1 e richiesta
/// grezza. `URLSession` rifiuta infatti il loopback su IP literal.
func localServerResponds(port: Int, timeout: TimeInterval = 1.0) -> Bool {
    let handle = socket(AF_INET, SOCK_STREAM, 0)
    guard handle >= 0 else { return false }
    defer { close(handle) }

    var timeoutValue = timeval(
        tv_sec: Int(timeout),
        tv_usec: Int32((timeout - floor(timeout)) * 1_000_000)
    )
    setsockopt(handle, SOL_SOCKET, SO_RCVTIMEO, &timeoutValue, socklen_t(MemoryLayout<timeval>.size))
    setsockopt(handle, SOL_SOCKET, SO_SNDTIMEO, &timeoutValue, socklen_t(MemoryLayout<timeval>.size))

    var address = sockaddr_in()
    address.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
    address.sin_family = sa_family_t(AF_INET)
    address.sin_port = in_port_t(UInt16(port)).bigEndian
    address.sin_addr.s_addr = inet_addr("127.0.0.1")

    let connected = withUnsafePointer(to: &address) { pointer -> Int32 in
        pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) {
            connect(handle, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
        }
    }
    guard connected == 0 else { return false }

    let request = "GET /api/state HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n"
    _ = request.withCString { pointer in
        send(handle, pointer, strlen(pointer), 0)
    }

    var buffer = [UInt8](repeating: 0, count: 1024)
    let received = recv(handle, &buffer, buffer.count, 0)
    guard received > 0 else { return false }
    let head = String(decoding: buffer[0..<min(received, buffer.count)], as: UTF8.self)
    return head.contains("200")
}

// MARK: - Backend Python

/// Errore di avvio del backend, con messaggio mostrabile all'utente.
struct BackendError: Error, LocalizedError {
    let message: String
    var errorDescription: String? { message }
}

final class Backend {
    private var process: Process?
    private(set) var port: Int = 0
    private let repoPath: String
    private let pythonPath: String
    private let heartbeatPath: String
    private var logHandle: FileHandle?

    init(repoPath: String, pythonPath: String, heartbeatPath: String) {
        self.repoPath = repoPath
        self.pythonPath = pythonPath
        self.heartbeatPath = heartbeatPath
    }

    var baseURL: URL {
        URL(string: "http://127.0.0.1:\(port)")!
    }

    /// Verifica se una porta TCP locale è libera (bind di prova).
    private func portAvailable(_ candidate: Int) -> Bool {
        let handle = socket(AF_INET, SOCK_STREAM, 0)
        guard handle >= 0 else { return false }
        defer { close(handle) }
        // Come il server: una porta in TIME_WAIT non è un ostacolo.
        var reuse: Int32 = 1
        setsockopt(handle, SOL_SOCKET, SO_REUSEADDR, &reuse, socklen_t(MemoryLayout<Int32>.size))
        var address = sockaddr_in()
        address.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        address.sin_family = sa_family_t(AF_INET)
        address.sin_port = in_port_t(UInt16(candidate)).bigEndian
        address.sin_addr.s_addr = inet_addr("127.0.0.1")
        let result = withUnsafePointer(to: &address) { pointer -> Int32 in
            pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                bind(handle, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
            }
        }
        return result == 0
    }

    /// Verifica che il backend risponda davvero.
    private func isHealthy(timeout: TimeInterval = 5.0) -> Bool {
        localServerResponds(port: port, timeout: timeout)
    }

    /// Avvia il backend sulla prima porta libera della serie 8765+.
    func start() throws {
        var chosen: Int?
        for candidate in 8765..<8795 where portAvailable(candidate) {
            chosen = candidate
            break
        }
        guard let selected = chosen else {
            throw BackendError(message: "Nessuna porta locale libera fra 8765 e 8794.")
        }
        port = selected

        let process = Process()
        process.executableURL = URL(fileURLWithPath: pythonPath)
        process.arguments = [
            "-m", "amy", "serve",
            "--host", "127.0.0.1",
            "--port", String(selected),
        ]
        process.currentDirectoryURL = URL(fileURLWithPath: repoPath)

        var environment = ProcessInfo.processInfo.environment
        environment["PYTHONUNBUFFERED"] = "1"
        // Il backend deve chiudersi se questa app termina in modo improvviso.
        environment["AMY_PARENT_PID"] = String(getpid())
        environment["AMY_HEARTBEAT_FILE"] = heartbeatPath
        let existingPath = environment["PYTHONPATH"] ?? ""
        environment["PYTHONPATH"] = existingPath.isEmpty ? repoPath : repoPath + ":" + existingPath
        process.environment = environment

        // Flussi separati: stdout e stderr non devono condividere la Pipe,
        // altrimenti Foundation duplica lo stesso descrittore e il watchdog
        // su stdin non riceve correttamente la chiusura.
        let outPipe = Pipe()
        let errPipe = Pipe()
        process.standardOutput = outPipe
        process.standardError = errPipe

        let directory = AppLog.backendURL.deletingLastPathComponent()
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        if !FileManager.default.fileExists(atPath: AppLog.backendURL.path) {
            FileManager.default.createFile(atPath: AppLog.backendURL.path, contents: nil)
        }
        let handle = try? FileHandle(forWritingTo: AppLog.backendURL)
        handle?.seekToEndOfFile()
        logHandle = handle
        for stream in [outPipe, errPipe] {
            stream.fileHandleForReading.readabilityHandler = { readable in
                let data = readable.availableData
                guard !data.isEmpty else { return }
                handle?.write(data)
            }
        }

        do {
            try process.run()
        } catch {
            throw BackendError(message: "Impossibile avviare \(pythonPath): \(error.localizedDescription)")
        }
        self.process = process
        AppLog.write("Backend avviato: \(pythonPath) -m amy serve --port \(selected) (repo: \(repoPath))")

        let deadline = Date().addingTimeInterval(40)
        while Date() < deadline {
            if isHealthy() {
                AppLog.write("Backend pronto su porta \(selected)")
                return
            }
            if !process.isRunning {
                throw BackendError(message: "Il backend si è chiuso subito. Vedi \(AppLog.backendURL.path).")
            }
            Thread.sleep(forTimeInterval: 0.4)
        }
        throw BackendError(message: "Il backend non ha risposto entro 40 secondi. Vedi \(AppLog.backendURL.path).")
    }

    func stop() {
        guard let process = process, process.isRunning else { return }
        process.terminate()
        let deadline = Date().addingTimeInterval(4)
        while process.isRunning && Date() < deadline {
            Thread.sleep(forTimeInterval: 0.1)
        }
        if process.isRunning {
            kill(process.processIdentifier, SIGKILL)
        }
        AppLog.write("Backend terminato (pid \(process.processIdentifier))")
    }
}

// MARK: - Delegate applicazione

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, NSWindowDelegate {
    private var window: NSWindow?
    private var webView: WKWebView!
    private var backend: Backend?
    private var monitorTimer: Timer?
    private var heartbeatTimer: Timer?
    private var signalSources: [DispatchSourceSignal] = []
    private var failedHealthChecks = 0
    private var didReportCrash = false
    private let selfTestMode = CommandLine.arguments.contains("--selftest")
    private var selfTestStarted = false
    private var selfTestDeadline = Date()

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        buildMainMenu()
        installSignalHandlers()
        terminateStaleInstance()
        writePidFile()
        // L'heartbeat deve esistere prima del backend: se manca, il backend
        // deduce che il genitore è morto e si chiude subito.
        writeHeartbeat()

        let repoPath = resolveRepositoryPath()
        guard let repoPath = repoPath else {
            presentFatal(message: "Non riesco a trovare il repository di Amy Brain.")
            return
        }

        let backend = Backend(
            repoPath: repoPath,
            pythonPath: resolvePythonPath(),
            heartbeatPath: heartbeatURL.path
        )
        do {
            try backend.start()
        } catch {
            presentFatal(message: error.localizedDescription)
            return
        }
        self.backend = backend

        let controller = buildWindow()
        window = controller.window
        webView = controller.webView
        webView.navigationDelegate = self
        window?.delegate = self
        if selfTestMode {
            // In modalità test la finestra resta fuori schermo: l'app deve
            // però avere una finestra visibile al WindowServer, altrimenti
            // viene considerata priva di finestre e termina.
            window?.setFrameOrigin(NSPoint(x: -4000, y: -4000))
            window?.makeKeyAndOrderFront(nil)
        } else {
            window?.makeKeyAndOrderFront(nil)
        }
        webView.load(URLRequest(url: backend.baseURL))
        NSApp.activate(ignoringOtherApps: true)

        monitorTimer = Timer.scheduledTimer(withTimeInterval: 8.0, repeats: true) { [weak self] _ in
            self?.checkBackend()
        }
        startHeartbeat()
        AppLog.write("App avviata: \(backend.baseURL.absoluteString)")
    }

    func applicationWillTerminate(_ notification: Notification) {
        stopHeartbeat()
        monitorTimer?.invalidate()
        backend?.stop()
        removePidFile()
        AppLog.write("App terminata")
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }

    func windowWillClose(_ notification: Notification) {
        NSApp.terminate(nil)
    }

    // MARK: Segnali

    /// SIGTERM e SIGINT chiudono l'app in modo ordinato, così il backend
    /// viene fermato subito invece di aspettare il watchdog.
    private func installSignalHandlers() {
        for signalNumber in [SIGTERM, SIGINT] {
            let source = DispatchSource.makeSignalSource(signal: signalNumber, queue: .main)
            source.setEventHandler {
                AppLog.write("Segnale \(signalNumber): chiusura ordinata")
                NSApp.terminate(nil)
            }
            signal(signalNumber, SIG_IGN)
            source.resume()
            signalSources.append(source)
        }
    }

    // MARK: Percorsi

    /// File con il pid dell'istanza attiva: evita due app in parallelo.
    private var pidFileURL: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".amy", isDirectory: true)
            .appendingPathComponent("app.pid")
    }

    /// File di heartbeat letto dal backend per sapere se l'app è viva.
    private var heartbeatURL: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".amy", isDirectory: true)
            .appendingPathComponent("app.heartbeat")
    }

    /// Aggiorna il heartbeat: il backend esce se il file non viene più toccato.
    private func writeHeartbeat() {
        let directory = heartbeatURL.deletingLastPathComponent()
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let stamp = String(Date().timeIntervalSince1970)
        try? Data(stamp.utf8).write(to: heartbeatURL)
    }

    private func startHeartbeat() {
        writeHeartbeat()
        heartbeatTimer = Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { [weak self] _ in
            self?.writeHeartbeat()
        }
    }

    private func stopHeartbeat() {
        heartbeatTimer?.invalidate()
        heartbeatTimer = nil
        try? FileManager.default.removeItem(at: heartbeatURL)
    }

    private func writePidFile() {
        let directory = pidFileURL.deletingLastPathComponent()
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try? Data(String(getpid()).utf8).write(to: pidFileURL)
    }

    private func removePidFile() {
        try? FileManager.default.removeItem(at: pidFileURL)
    }

    /// Chiude un'istanza precedente rimasta attiva (per esempio dopo un crash).
    private func terminateStaleInstance() {
        guard let data = try? Data(contentsOf: pidFileURL),
              let text = String(data: data, encoding: .utf8),
              let pid = Int(text.trimmingCharacters(in: .whitespacesAndNewlines)),
              pid > 0,
              pid != getpid(),
              kill(pid_t(pid), 0) == 0 else { return }
        var path = [CChar](repeating: 0, count: 1024)
        let length = proc_pidpath(pid_t(pid), &path, UInt32(path.count))
        guard length > 0 else { return }
        let processPath = String(cString: path)
        guard processPath.contains("AmyCore") else { return }
        kill(pid_t(pid), SIGTERM)
        AppLog.write("Istanza precedente terminata (pid \(pid))")
        removePidFile()
    }

    private func resolveRepositoryPath() -> String? {
        if let saved = Settings.load(), isValidRepository(path: saved.repoPath) {
            return saved.repoPath
        }
        let built = BuiltConfig.defaultRepoPath
        if isValidRepository(path: built) {
            return built
        }
        return askUserForRepository()
    }

    private func askUserForRepository() -> String? {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        panel.directoryURL = FileManager.default.homeDirectoryForCurrentUser
        panel.prompt = "Scegli la cartella di Amy Brain"
        panel.message = "Seleziona la cartella che contiene il pacchetto `amy` (per esempio /Progetti/amy_brain)."
        guard panel.runModal() == .OK, let url = panel.url else { return nil }
        let path = url.path
        guard isValidRepository(path: path) else {
            presentFatal(message: "La cartella scelta non contiene il pacchetto `amy`.")
            return nil
        }
        Settings.save(LocalConfig(repoPath: path, python: resolvePythonPath()))
        AppLog.write("Repository impostato dall'utente: \(path)")
        return path
    }

    private func resolvePythonPath() -> String {
        if let saved = Settings.load(), !saved.python.isEmpty {
            return saved.python
        }
        if let override = ProcessInfo.processInfo.environment["AMY_PYTHON"], !override.isEmpty {
            return override
        }
        return "/usr/bin/python3"
    }

    // MARK: Finestra

    private func buildWindow() -> (window: NSWindow, webView: WKWebView) {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()
        if #available(macOS 12.3, *) {
            configuration.preferences.isElementFullscreenEnabled = true
        }
        let web = WKWebView(frame: NSRect(x: 0, y: 0, width: 1280, height: 840), configuration: configuration)
        web.allowsBackForwardNavigationGestures = false
        if #available(macOS 12.0, *) {
            web.underPageBackgroundColor = NSColor(calibratedRed: 0.012, green: 0.024, blue: 0.051, alpha: 1)
        }

        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1280, height: 840),
            styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        window.title = "Amy Core"
        window.titlebarAppearsTransparent = false
        window.isReleasedWhenClosed = false
        window.minSize = NSSize(width: 960, height: 600)
        window.contentView = web
        window.center()
        return (window, web)
    }

    // MARK: Controllo backend

    private func checkBackend() {
        guard let backend = backend else { return }
        let port = backend.port
        DispatchQueue.global(qos: .utility).async { [weak self] in
            let ok = localServerResponds(port: port, timeout: 2.0)
            DispatchQueue.main.async {
                guard let self = self else { return }
                if ok {
                    self.failedHealthChecks = 0
                    return
                }
                self.failedHealthChecks += 1
                if self.failedHealthChecks >= 2 && !self.didReportCrash {
                    self.didReportCrash = true
                    self.presentBackendLost()
                }
            }
        }
    }

    private func presentBackendLost() {
        let alert = NSAlert()
        alert.messageText = "Il backend di Amy non risponde."
        alert.informativeText = "Il server locale si è fermato. Riavvio in corso, altrimenti rilancia Amy Core."
        alert.addButton(withTitle: "Riavvia backend")
        alert.addButton(withTitle: "Esci")
        if alert.runModal() == .alertFirstButtonReturn {
            backend?.stop()
            didReportCrash = false
            failedHealthChecks = 0
            let repoPath = resolveRepositoryPath()
            guard let repoPath = repoPath else { return }
            let restarted = Backend(
                repoPath: repoPath,
                pythonPath: resolvePythonPath(),
                heartbeatPath: heartbeatURL.path
            )
            do {
                try restarted.start()
                backend = restarted
                webView.load(URLRequest(url: restarted.baseURL))
            } catch {
                presentFatal(message: error.localizedDescription)
            }
        } else {
            NSApp.terminate(nil)
        }
    }

    private func presentFatal(message: String) {
        AppLog.write("Errore: \(message)")
        stopHeartbeat()
        let alert = NSAlert()
        alert.alertStyle = .critical
        alert.messageText = "Amy Core non può partire"
        alert.informativeText = message
        alert.addButton(withTitle: "Esci")
        alert.runModal()
        NSApp.terminate(nil)
    }

    // MARK: Navigazione

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        AppLog.write("Dashboard caricata")
        // Verifica programmatica: conferma che la pagina sia montata davvero.
        let script = """
        (function () {
          var state = document.getElementById('coreState');
          var title = document.title || '';
          return JSON.stringify({title: title, state: state ? state.textContent : null});
        })();
        """
        webView.evaluateJavaScript(script) { result, error in
            if let error = error {
                AppLog.write("Verifica pagina fallita: \(error.localizedDescription)")
            } else if let result = result as? String {
                AppLog.write("Verifica pagina: \(result)")
            }
        }
        if selfTestMode {
            startSelfTest()
        }
    }

    // MARK: Test automatico dell'app

    /// Verifica end-to-end dentro l'app nativa: invia un messaggio reale dal
    /// DOM e attende la risposta mostrata in chat.
    private func startSelfTest() {
        guard !selfTestStarted else { return }
        selfTestStarted = true
        let script = """
        (function () {
          var input = document.getElementById('composerInput');
          var form = document.getElementById('chatForm');
          if (!input || !form) return 'ERRORE:elementi mancanti';
          input.value = 'che ore sono?';
          input.dispatchEvent(new Event('input', {bubbles: true}));
          form.requestSubmit();
          return 'OK:inviato';
        })();
        """
        webView.evaluateJavaScript(script) { [weak self] result, error in
            guard let self = self else { return }
            if let error = error {
                self.finishSelfTest(ok: false, detail: "invio fallito: \(error.localizedDescription)")
                return
            }
            guard let text = result as? String, text.hasPrefix("OK") else {
                self.finishSelfTest(ok: false, detail: "invio non riuscito: \(result ?? "nil")")
                return
            }
            print("SELFTEST: messaggio inviato dalla UI")
            self.selfTestDeadline = Date().addingTimeInterval(45)
            self.pollSelfTest()
        }
    }

    private func pollSelfTest() {
        let script = """
        (function () {
          var container = document.getElementById('messages');
          if (!container) return 'ERRORE:contenitore mancante';
          var state = document.getElementById('coreState');
          var replies = container.querySelectorAll('.message.amy .bubble');
          var last = replies.length ? (replies[replies.length - 1].textContent || '') : '';
          return JSON.stringify({
            replies: replies.length,
            last: last,
            state: state ? state.textContent : null
          });
        })();
        """
        webView.evaluateJavaScript(script) { [weak self] result, error in
            guard let self = self else { return }
            if let error = error {
                self.finishSelfTest(ok: false, detail: "lettura DOM fallita: \(error.localizedDescription)")
                return
            }
            guard let text = result as? String,
                  let data = text.data(using: .utf8),
                  let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let last = payload["last"] as? String else {
                self.finishSelfTest(ok: false, detail: "risposta non interpretabile")
                return
            }
            if last.contains("Sono le") {
                let state = payload["state"] as? String ?? "?"
                self.finishSelfTest(ok: true, detail: "risposta in chat: \"\(last.prefix(80))\" · stato \(state)")
                return
            }
            if Date() < self.selfTestDeadline {
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.7) { self.pollSelfTest() }
            } else {
                self.finishSelfTest(ok: false, detail: "nessuna risposta in chat entro 45 secondi")
            }
        }
    }

    private func finishSelfTest(ok: Bool, detail: String) {
        print("SELFTEST \(ok ? "OK" : "FALLITO"): \(detail)")
        AppLog.write("SELFTEST \(ok ? "OK" : "FALLITO"): \(detail)")
        backend?.stop()
        removePidFile()
        exit(ok ? 0 : 1)
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        AppLog.write("Navigazione fallita: \(error.localizedDescription)")
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        AppLog.write("Navigazione provvisoria fallita: \(error.localizedDescription)")
    }

    // MARK: Menu

    private func buildMainMenu() {
        let mainMenu = NSMenu()

        let appMenuItem = NSMenuItem()
        let appMenu = NSMenu()
        appMenu.addItem(
            withTitle: "Informazioni su Amy Core",
            action: #selector(showAbout),
            keyEquivalent: ""
        ).target = self
        appMenu.addItem(NSMenuItem.separator())
        appMenu.addItem(
            withTitle: "Apri cartella configurazione",
            action: #selector(openConfigFolder),
            keyEquivalent: ""
        ).target = self
        appMenu.addItem(
            withTitle: "Apri log",
            action: #selector(openLog),
            keyEquivalent: ""
        ).target = self
        appMenu.addItem(NSMenuItem.separator())
        appMenu.addItem(
            withTitle: "Ricarica dashboard",
            action: #selector(reload),
            keyEquivalent: "r"
        ).target = self
        appMenu.addItem(NSMenuItem.separator())
        appMenu.addItem(
            withTitle: "Nascondi Amy Core",
            action: #selector(NSApplication.hide(_:)),
            keyEquivalent: "h"
        )
        appMenu.addItem(
            withTitle: "Esci",
            action: #selector(NSApplication.terminate(_:)),
            keyEquivalent: "q"
        )
        appMenuItem.submenu = appMenu
        mainMenu.addItem(appMenuItem)

        let editMenuItem = NSMenuItem()
        let editMenu = NSMenu(title: "Modifica")
        editMenu.addItem(withTitle: "Taglia", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        editMenu.addItem(withTitle: "Copia", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        editMenu.addItem(withTitle: "Incolla", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        editMenu.addItem(withTitle: "Seleziona tutto", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        editMenuItem.submenu = editMenu
        mainMenu.addItem(editMenuItem)

        let viewMenuItem = NSMenuItem()
        let viewMenu = NSMenu(title: "Visualizza")
        viewMenu.addItem(
            withTitle: "Schermo intero",
            action: #selector(toggleFullScreen),
            keyEquivalent: "f"
        ).target = self
        viewMenu.addItem(
            withTitle: "Ricarica",
            action: #selector(reload),
            keyEquivalent: "r"
        ).target = self
        viewMenuItem.submenu = viewMenu
        mainMenu.addItem(viewMenuItem)

        let windowMenuItem = NSMenuItem()
        let windowMenu = NSMenu(title: "Finestra")
        windowMenu.addItem(withTitle: "Riduci", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        windowMenu.addItem(withTitle: "Zoom", action: #selector(NSWindow.performZoom(_:)), keyEquivalent: "")
        windowMenu.addItem(withTitle: "Porta tutto in primo piano", action: #selector(NSApplication.activate(ignoringOtherApps:)), keyEquivalent: "")
        windowMenuItem.submenu = windowMenu
        mainMenu.addItem(windowMenuItem)

        NSApp.mainMenu = mainMenu
        NSApp.windowsMenu = windowMenu
    }

    @objc private func showAbout() {
        let alert = NSAlert()
        alert.messageText = "Amy Core"
        alert.informativeText = """
        Interfaccia nativa di Amy Brain.
        Versione \(BuiltConfig.appVersion).
        Il backend locale resta legato a 127.0.0.1: nessun dato esce dal computer.
        """
        alert.runModal()
    }

    @objc private func openConfigFolder() {
        let folder = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".amy", isDirectory: true)
        try? FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        NSWorkspace.shared.open(folder)
    }

    @objc private func openLog() {
        NSWorkspace.shared.open(AppLog.url)
    }

    @objc private func reload() {
        webView?.reload()
    }

    @objc private func toggleFullScreen(_ sender: Any?) {
        window?.toggleFullScreen(sender)
    }
}

// MARK: - Avvio

@main
enum AmyCoreMain {
    static func main() {
        let application = NSApplication.shared
        let delegate = AppDelegate()
        application.delegate = delegate
        application.setActivationPolicy(.regular)
        application.run()
    }
}
