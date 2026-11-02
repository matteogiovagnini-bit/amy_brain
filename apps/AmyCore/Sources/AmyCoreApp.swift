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

/// Trasforma una stringa in un literal JavaScript sicuro.
/// Serve per costruire gli script di verifica senza iniettare codice.
func jsonString(_ value: String) -> String {
    let data = (try? JSONSerialization.data(withJSONObject: [value], options: [])) ?? Data("[\"\"]".utf8)
    guard let array = try? JSONSerialization.jsonObject(with: data) as? [String] else { return "\"\"" }
    return array.first.map { jsonQuote($0) } ?? "\"\""
}

/// Escape di una stringa per un literal JavaScript.
func jsonQuote(_ value: String) -> String {
    var out = "\""
    for character in value.unicodeScalars {
        switch character {
        case "\"": out += "\\\""
        case "\\": out += "\\\\"
        case "\n": out += "\\n"
        case "\r": out += "\\r"
        case "\t": out += "\\t"
        default:
            if character.value < 0x20 {
                out += String(format: "\\u%04x", character.value)
            } else {
                out.unicodeScalars.append(character)
            }
        }
    }
    out += "\""
    return out
}

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
    /// Se falso il backend non pronuncia il messaggio di avvio (usato nei test).
    private let startupGreeting: Bool

    init(repoPath: String, pythonPath: String, heartbeatPath: String, startupGreeting: Bool = true) {
        self.repoPath = repoPath
        self.pythonPath = pythonPath
        self.heartbeatPath = heartbeatPath
        self.startupGreeting = startupGreeting
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
        if !startupGreeting {
            environment["AMY_STARTUP_GREETING"] = "0"
        }
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
    private var heartbeatTimer: DispatchSourceTimer?
    private var signalSources: [DispatchSourceSignal] = []
    private var failedHealthChecks = 0
    private var didReportCrash = false
    private let selfTestMode = CommandLine.arguments.contains("--selftest")
    private var selfTestStarted = false
    private var selfTestDeadline = Date()
    /// Modalità di verifica visiva: `--snapshot /percorso.png` salva un'immagine
    /// della dashboard dopo il caricamento e termina. Serve a controllare layout e
    /// leggibilità senza dipendere dal permesso di cattura schermo del terminale.
    private let snapshotPath: String? = {
        let args = CommandLine.arguments
        guard let index = args.firstIndex(of: "--snapshot"), index + 1 < args.count else { return nil }
        return args[index + 1]
    }()

    /// Dimensione della finestra per la verifica visiva: `--snapshot-size 960x600`.
    private let snapshotSize: NSSize? = {
        let args = CommandLine.arguments
        guard let index = args.firstIndex(of: "--snapshot-size"), index + 1 < args.count else { return nil }
        let parts = args[index + 1].lowercased().split(separator: "x")
        guard parts.count == 2, let width = Double(parts[0]), let height = Double(parts[1]) else { return nil }
        return NSSize(width: width, height: height)
    }()

    /// Selettore CSS da portare in vista prima dello snapshot:
    /// `--snapshot-scroll "[aria-labelledby='voiceTitle']"`. Serve a verificare
    /// le schede che stanno dentro il pannello scorrevole.
    private let snapshotScroll: String? = {
        let args = CommandLine.arguments
        guard let index = args.firstIndex(of: "--snapshot-scroll"), index + 1 < args.count else { return nil }
        return args[index + 1]
    }()

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        buildMainMenu()
        installSignalHandlers()
        terminateStaleInstance()
        writePidFile()
        // L'heartbeat deve esistere prima del backend: se manca, il backend
        // deduce che il genitore è morto e si chiude subito. Il timer parte
        // qui, non dopo l'avvio del backend: durante l'attesa il file deve
        // restare aggiornato, altrimenti il watchdog lo considera scaduto.
        startHeartbeat()

        let repoPath = resolveRepositoryPath()
        guard let repoPath = repoPath else {
            presentFatal(message: "Non riesco a trovare il repository di Amy Brain.")
            return
        }

        let backend = Backend(
            repoPath: repoPath,
            pythonPath: resolvePythonPath(),
            heartbeatPath: heartbeatURL.path,
            // Nel self-test il saluto viene omesso: il test verifica la UI, non l'audio.
            startupGreeting: !selfTestMode
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
        if let size = snapshotSize {
            window?.setContentSize(size)
        }
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
        if selfTestMode, var parts = URLComponents(url: backend.baseURL, resolvingAgainstBaseURL: false) {
            // Il self-test non eredita la cronologia della sessione.
            parts.queryItems = [URLQueryItem(name: "selftest", value: "1")]
            if let url = parts.url {
                webView.load(URLRequest(url: url))
            } else {
                webView.load(URLRequest(url: backend.baseURL))
            }
        } else {
            webView.load(URLRequest(url: backend.baseURL))
        }
        NSApp.activate(ignoringOtherApps: true)

        monitorTimer = Timer.scheduledTimer(withTimeInterval: 8.0, repeats: true) { [weak self] _ in
            self?.checkBackend()
        }
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
    /// Scrive sempre su disco: il backend legge il file, non lo tiene in memoria.
    private func writeHeartbeat() {
        let directory = heartbeatURL.deletingLastPathComponent()
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let stamp = String(Date().timeIntervalSince1970)
        try? Data(stamp.utf8).write(to: heartbeatURL)
    }

    private func startHeartbeat() {
        writeHeartbeat()
        // Thread dedicato invece di un `Timer` sul main run loop: se l'app
        // mostra un alert modale (per esempio «backend non risponde»), il main
        // thread è bloccato e i timer non scattano. Senza questo, l'heartbeat
        // si fermava e il backend chiudeva la dashboard da solo.
        let queue = DispatchQueue(label: "local.amy.brain.heartbeat")
        heartbeatTimer = DispatchSource.makeTimerSource(queue: queue)
        heartbeatTimer?.schedule(deadline: .now() + 2.0, repeating: 2.0)
        heartbeatTimer?.setEventHandler { [weak self] in
            self?.writeHeartbeat()
        }
        heartbeatTimer?.resume()
    }

    private func stopHeartbeat() {
        heartbeatTimer?.cancel()
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
            // Timeout generoso: durante una trascrizione vocale il backend è
            // occupato e può rispondere in più secondi. Un controllo troppo
            // severo dichiarerebbe «backend morto» mentre è solo occupato.
            let ok = localServerResponds(port: port, timeout: 6.0)
            DispatchQueue.main.async {
                guard let self = self else { return }
                if ok {
                    self.failedHealthChecks = 0
                    return
                }
                self.failedHealthChecks += 1
                // Tre controlli consecutivi falliti: con intervalli da 8 s
                // servono circa 24 s di backend irraggiungibile.
                if self.failedHealthChecks >= 3 && !self.didReportCrash {
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
        // Avviso non modale: `runModal` blocca il thread principale finché
        // l'utente non risponde, e con esso la finestra e i controlli
        // periodici. Una sheet lascia l'app viva e non la congela per ore.
        let handle: (NSApplication.ModalResponse) -> Void = { [weak self] response in
            guard let self = self else { return }
            if response == .alertFirstButtonReturn {
                self.restartBackend()
            } else {
                NSApp.terminate(nil)
            }
        }
        if let window = window {
            alert.beginSheetModal(for: window, completionHandler: handle)
        } else {
            handle(alert.runModal())
        }
    }

    private func restartBackend() {
        backend?.stop()
        didReportCrash = false
        failedHealthChecks = 0
        guard let repoPath = resolveRepositoryPath() else { return }
        let restarted = Backend(
            repoPath: repoPath,
            pythonPath: resolvePythonPath(),
            heartbeatPath: heartbeatURL.path,
            startupGreeting: !selfTestMode
        )
        do {
            try restarted.start()
            backend = restarted
            webView.load(URLRequest(url: restarted.baseURL))
        } catch {
            presentFatal(message: error.localizedDescription)
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
        } else if let path = snapshotPath {
            captureSnapshot(to: path)
        }
    }

    // MARK: Verifica visiva

    private func captureSnapshot(to path: String) {
        // Attende che il primo giro di stato popoli i pannelli.
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.5) { [weak self] in
            guard let self = self else { return }
            if let selector = self.snapshotScroll {
                self.scrollTo(selector: selector) {
                    self.takeSnapshot(to: path)
                }
                return
            }
            self.takeSnapshot(to: path)
        }
    }

    /// Porta in vista un elemento prima dello snapshot.
    private func scrollTo(selector: String, completion: @escaping () -> Void) {
        let script = """
        (function () {
          var target = document.querySelector(\(jsonString(selector)));
          if (!target) return 'ERRORE:selettore non trovato';
          target.scrollIntoView({block: 'start'});
          return 'OK:scrollato';
        })();
        """
        webView.evaluateJavaScript(script) { [weak self] result, error in
            if let error = error {
                AppLog.write("Scroll non riuscito: \(error.localizedDescription)")
            } else if let result = result as? String {
                AppLog.write("Scroll: \(result)")
            }
            // Breve attesa: il layout deve assestarsi prima della cattura.
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) {
                completion()
            }
            _ = self
        }
    }

    /// Cattura la WebView e scrive il PNG.
    private func takeSnapshot(to path: String) {
        let configuration = WKSnapshotConfiguration()
        configuration.rect = webView.bounds
        webView.takeSnapshot(with: configuration) { [weak self] image, error in
            guard let self = self else { return }
            guard let image = image,
                  let tiff = image.tiffRepresentation,
                  let bitmap = NSBitmapImageRep(data: tiff),
                  let png = bitmap.representation(using: .png, properties: [:]) else {
                print("SNAPSHOT FALLITO: \(error?.localizedDescription ?? "immagine non disponibile")")
                self.backend?.stop()
                exit(1)
            }
            do {
                try png.write(to: URL(fileURLWithPath: path))
                print("SNAPSHOT: \(path)")
            } catch {
                print("SNAPSHOT FALLITO: \(error.localizedDescription)")
                self.backend?.stop()
                exit(1)
            }
            self.backend?.stop()
            self.removePidFile()
            exit(0)
        }
    }

    // MARK: Test automatico dell'app

    /// Verifica end-to-end dentro l'app nativa: invia un messaggio reale dal
    /// DOM e attende la risposta mostrata in chat.
    private func startSelfTest() {
        guard !selfTestStarted else { return }
        selfTestStarted = true
        // Con `?selftest=1` la dashboard non carica la cronologia: la prima
        // risposta che compare è davvero quella del test, non una vecchia
        // risposta della sessione (osservato il 2 novembre 2026: «07:47»
        // alle 08:04).
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
            let replies = payload["replies"] as? Int ?? 0
            if replies > 0 && !last.isEmpty {
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
