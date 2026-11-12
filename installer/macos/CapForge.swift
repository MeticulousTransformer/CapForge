import AppKit
import Foundation

// The app owns the window; the shared installer owns deployment and rollback.
struct SetupOptions {
    var headless = false
    var dryRun = false
    var target: String?
    var extensionRoot: String?
    var enableUnsigned = false
    var skipDependencies = false

    init(_ arguments: [String]) throws {
        var index = 0
        while index < arguments.count {
            let argument = arguments[index]
            switch argument {
            case "--headless": headless = true
            case "--dry-run": dryRun = true
            case "--enable-unsigned": enableUnsigned = true
            case "--skip-dependencies": skipDependencies = true
            case "--target", "--extension-root":
                index += 1
                guard index < arguments.count, arguments[index].hasPrefix("/") else {
                    throw SetupError.message("\(argument) needs an absolute folder path.")
                }
                if argument == "--target" { target = arguments[index] }
                else { extensionRoot = arguments[index] }
            default: throw SetupError.message("Unknown option: \(argument)")
            }
            index += 1
        }
    }

    var runtime: URL {
        if let target = target { return URL(fileURLWithPath: target, isDirectory: true) }
        let support = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support", isDirectory: true)
        let legacy = support.appendingPathComponent("Kartuli Caption Forge", isDirectory: true)
        if ownsRuntime(legacy) { return legacy }
        return support.appendingPathComponent("CapForge", isDirectory: true)
    }

    var extensions: URL {
        if let extensionRoot = extensionRoot { return URL(fileURLWithPath: extensionRoot, isDirectory: true) }
        return FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/Adobe/CEP/extensions", isDirectory: true)
    }

    var installerArguments: [String] {
        var arguments = ["--headless", "--target", runtime.path, "--extension-root", extensions.path]
        if enableUnsigned { arguments.append("--enable-unsigned") }
        if skipDependencies { arguments.append("--skip-dependencies") }
        return arguments
    }
}

enum SetupError: Error, LocalizedError {
    case message(String)
    var errorDescription: String? { if case .message(let text) = self { return text }; return nil }
}

func ownsRuntime(_ location: URL) -> Bool {
    guard let data = try? Data(contentsOf: location.appendingPathComponent(".kcf-install.json")),
          let marker = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
          let tool = marker["tool"] as? String else { return false }
    return ["CapForge", "Kartuli Caption Forge"].contains(tool)
}

func releaseInfo(_ location: URL) -> [String: Any] {
    guard let data = try? Data(contentsOf: location.appendingPathComponent("release.json")),
          let value = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else { return [:] }
    return value
}

func bootstrapURL(_ options: SetupOptions) throws -> URL {
    guard let resources = Bundle.main.resourceURL else { throw SetupError.message("The app resources are missing. Download CapForge again.") }
    let payload = resources.appendingPathComponent("payload")
    let bundled = releaseInfo(payload)
    let installed = releaseInfo(options.runtime)
    let bundledVersion = (bundled["version"] as? String ?? "0.0.0").split(separator: ".").compactMap { Int($0) }
    let installedVersion = (installed["version"] as? String ?? "0.0.0").split(separator: ".").compactMap { Int($0) }
    let installedIsNewer = bundledVersion.lexicographicallyPrecedes(installedVersion) ||
        (bundledVersion == installedVersion && (installed["builtAt"] as? Int ?? 0) > (bundled["builtAt"] as? Int ?? 0))
    // An older copy in Applications must repair the current installed release,
    // not silently replace it with the app's older embedded payload.
    let source = ownsRuntime(options.runtime) && installedIsNewer ? options.runtime : payload
    let script = source.appendingPathComponent("installer/bootstrap_macos.sh")
    guard FileManager.default.fileExists(atPath: script.path) else {
        throw SetupError.message("The installation files are missing. Download CapForge again.")
    }
    return script
}

func setupProcess(_ options: SetupOptions) throws -> Process {
    let script = try bootstrapURL(options)
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/bin/bash")
    process.arguments = [script.path] + options.installerArguments
    process.currentDirectoryURL = script.deletingLastPathComponent().deletingLastPathComponent()
    var environment = ProcessInfo.processInfo.environment
    environment["PYTHONUNBUFFERED"] = "1"
    process.environment = environment
    return process
}

final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    var options: SetupOptions
    private var window: NSWindow!
    private var status: NSTextField!
    private var installedStatus: NSTextField!
    private var action: NSButton!
    private var unsigned: NSButton!
    private var progress: NSProgressIndicator!
    private var logView: NSTextView!
    private var running = false
    private var log = ""
    private let ink = NSColor(calibratedRed: 0.12, green: 0.14, blue: 0.15, alpha: 1)
    private let muted = NSColor(calibratedRed: 0.40, green: 0.42, blue: 0.43, alpha: 1)
    private let accent = NSColor(calibratedRed: 0.35, green: 0.25, blue: 0.63, alpha: 1)
    private var logURL: URL {
        FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Logs/CapForge/setup.log")
    }

    init(options: SetupOptions) { self.options = options; super.init() }

    func applicationDidFinishLaunching(_ notification: Notification) {
        let menu = NSMenu()
        let appItem = NSMenuItem()
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "About CapForge", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Quit CapForge", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu
        menu.addItem(appItem)
        NSApp.mainMenu = menu

        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 720, height: 690), styleMask: [.titled, .closable, .miniaturizable], backing: .buffered, defer: false)
        window.title = "CapForge"
        window.titlebarAppearsTransparent = true
        window.backgroundColor = NSColor(calibratedRed: 0.97, green: 0.96, blue: 0.94, alpha: 1)
        window.delegate = self
        window.isReleasedWhenClosed = false
        window.appearance = NSAppearance(named: .aqua)
        guard let content = window.contentView else { return }

        label("CAPFORGE  /  FOR AFTER EFFECTS", x: 36, y: 637, width: 648, height: 20, size: 11, weight: .semibold, color: accent)
        label("Your words. In motion.", x: 34, y: 579, width: 650, height: 48, size: 34, weight: .bold)
        label("Word-timed Georgian and English captions.\nInstall the studio, then make it yours inside After Effects.", x: 36, y: 518, width: 648, height: 48, size: 15, color: muted)

        let card = NSView(frame: NSRect(x: 36, y: 365, width: 648, height: 129))
        card.wantsLayer = true
        card.layer?.backgroundColor = NSColor.white.cgColor
        card.layer?.cornerRadius = 12
        content.addSubview(card)
        installedStatus = label(ownsRuntime(options.runtime) ? "Ready to update or repair" : "Ready for your first install", x: 54, y: 452, width: 600, height: 24, size: 17, weight: .semibold)
        label("INSTALLED FOR YOUR MAC ACCOUNT", x: 54, y: 419, width: 600, height: 17, size: 10, weight: .semibold, color: muted)
        let location = label(options.runtime.path, x: 54, y: 390, width: 600, height: 22, size: 11, color: muted)
        location.isSelectable = true
        location.lineBreakMode = .byTruncatingMiddle
        location.toolTip = options.runtime.path

        unsigned = NSButton(checkboxWithTitle: "Allow unsigned Adobe extensions for this account", target: nil, action: nil)
        unsigned.frame = NSRect(x: 36, y: 326, width: 648, height: 24)
        unsigned.font = .systemFont(ofSize: 12)
        unsigned.state = options.enableUnsigned ? .on : .off
        content.addSubview(unsigned)
        label("Required for this preview. Applies to all unsigned Adobe panels for this account.", x: 57, y: 302, width: 627, height: 19, size: 11, color: muted)
        label("Internet is needed for setup. Close After Effects before an update.", x: 36, y: 271, width: 648, height: 21, size: 12, color: muted)
        status = label("Install when you’re ready. Your existing projects stay intact.", x: 36, y: 229, width: 648, height: 35, size: 12)
        progress = NSProgressIndicator(frame: NSRect(x: 36, y: 214, width: 648, height: 6))
        progress.style = .bar
        progress.isIndeterminate = true
        progress.isDisplayedWhenStopped = false
        content.addSubview(progress)

        let scroll = NSScrollView(frame: NSRect(x: 36, y: 100, width: 648, height: 101))
        scroll.hasVerticalScroller = true
        scroll.borderType = .noBorder
        scroll.drawsBackground = false
        logView = NSTextView(frame: scroll.bounds)
        logView.isEditable = false
        logView.isSelectable = true
        logView.drawsBackground = false
        logView.font = .monospacedSystemFont(ofSize: 10, weight: .regular)
        logView.textColor = muted
        logView.textContainerInset = NSSize(width: 3, height: 5)
        logView.autoresizingMask = [.width]
        logView.textContainer?.widthTracksTextView = true
        scroll.documentView = logView
        content.addSubview(scroll)

        button("Help", x: 31, width: 64, selector: #selector(openHelp))
        button("Logs", x: 99, width: 64, selector: #selector(openLogs))
        button("Open After Effects", x: 171, width: 153, selector: #selector(openAfterEffects))
        action = button(ownsRuntime(options.runtime) ? "Update / Repair" : "Install CapForge", x: 512, width: 172, selector: #selector(install))
        action.bezelColor = accent
        action.keyEquivalent = "\r"
        let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? ""
        label("VERSION \(version)  ·  PREVIEW", x: 36, y: 14, width: 648, height: 17, size: 9, color: muted)
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    @discardableResult private func label(_ text: String, x: CGFloat, y: CGFloat, width: CGFloat, height: CGFloat, size: CGFloat, weight: NSFont.Weight = .regular, color: NSColor? = nil) -> NSTextField {
        let field = NSTextField(wrappingLabelWithString: text)
        field.frame = NSRect(x: x, y: y, width: width, height: height)
        field.font = .systemFont(ofSize: size, weight: weight)
        field.textColor = color ?? ink
        window.contentView?.addSubview(field)
        return field
    }

    @discardableResult private func button(_ title: String, x: CGFloat, width: CGFloat, selector: Selector) -> NSButton {
        let control = NSButton(title: title, target: self, action: selector)
        control.frame = NSRect(x: x, y: 44, width: width, height: 34)
        control.bezelStyle = .rounded
        control.font = .systemFont(ofSize: 12, weight: .medium)
        window.contentView?.addSubview(control)
        return control
    }

    @objc private func install() {
        guard !running else { return }
        if NSWorkspace.shared.runningApplications.contains(where: { ($0.bundleIdentifier ?? "").hasPrefix("com.adobe.AfterEffects") || ($0.localizedName ?? "").hasPrefix("Adobe After Effects") }) {
            let alert = NSAlert()
            alert.messageText = "After Effects is open"
            alert.informativeText = "Save your project and close After Effects before installing. If you continue now, restart After Effects after setup so it loads the updated panel."
            alert.addButton(withTitle: "Back")
            alert.addButton(withTitle: "Continue")
            if alert.runModal() != .alertSecondButtonReturn { return }
        }
        options.enableUnsigned = unsigned.state == .on
        if !options.enableUnsigned {
            let alert = NSAlert()
            alert.messageText = "Install without enabling the preview panel?"
            alert.informativeText = "This build’s Adobe panel is unsigned. It may remain hidden in After Effects unless unsigned extensions are already enabled for your account. You can enable them with the checkbox and run Repair later."
            alert.addButton(withTitle: "Install anyway")
            alert.addButton(withTitle: "Back")
            if alert.runModal() != .alertFirstButtonReturn { return }
        }
        running = true
        action.isEnabled = false
        action.title = "Installing…"
        unsigned.isEnabled = false
        progress.startAnimation(nil)
        log = "CapForge setup — \(Date())\n"
        logView.string = log
        status.stringValue = "Preparing CapForge…"
        let selected = options
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            do {
                let process = try setupProcess(selected)
                let pipe = Pipe()
                process.standardOutput = pipe
                process.standardError = pipe
                try process.run()
                while true {
                    let data = pipe.fileHandleForReading.availableData
                    if data.isEmpty { break }
                    let text = String(decoding: data, as: UTF8.self)
                    DispatchQueue.main.async { self?.appendLog(text) }
                }
                process.waitUntilExit()
                DispatchQueue.main.async { self?.finished(process.terminationStatus == 0) }
            } catch {
                DispatchQueue.main.async {
                    self?.appendLog(error.localizedDescription + "\n")
                    self?.finished(false)
                }
            }
        }
    }

    private func appendLog(_ text: String) {
        log += text
        logView.string = String(log.suffix(100_000))
        logView.scrollToEndOfDocument(nil)
        let lines = text.components(separatedBy: .newlines).filter { !$0.trimmingCharacters(in: .whitespaces).isEmpty }
        if let line = lines.last { status.stringValue = String(line.prefix(220)) }
    }

    private func finished(_ success: Bool) {
        running = false
        action.isEnabled = true
        unsigned.isEnabled = true
        action.title = success ? "Update / Repair" : "Try Again"
        progress.stopAnimation(nil)
        do {
            try FileManager.default.createDirectory(at: logURL.deletingLastPathComponent(), withIntermediateDirectories: true)
            try log.write(to: logURL, atomically: true, encoding: .utf8)
        } catch { appendLog("The setup log could not be saved: \(error.localizedDescription)\n") }
        if success {
            installedStatus.stringValue = "CapForge is installed"
            status.stringValue = "Restart After Effects → Window → Extensions → CapForge."
            startService()
        } else {
            status.stringValue = "Setup needs attention. Review the log, then try again."
            let alert = NSAlert()
            alert.alertStyle = .warning
            alert.messageText = "CapForge could not finish setup"
            alert.informativeText = "Your saved keys and exports are preserved.\n\n" + String(log.suffix(900))
            alert.addButton(withTitle: "OK")
            alert.runModal()
        }
    }

    private func startService() {
        do {
            let process = Process()
            process.executableURL = options.runtime.appendingPathComponent(".venv/bin/python")
            process.arguments = [options.runtime.appendingPathComponent("backend/start_service.py").path]
            process.currentDirectoryURL = options.runtime
            var environment = ProcessInfo.processInfo.environment
            environment["PYTHONUNBUFFERED"] = "1"
            process.environment = environment
            process.standardInput = FileHandle.nullDevice
            let serviceLog = logURL.deletingLastPathComponent().appendingPathComponent("service.log")
            FileManager.default.createFile(atPath: serviceLog.path, contents: nil)
            let handle = try FileHandle(forWritingTo: serviceLog)
            process.standardOutput = handle
            process.standardError = handle
            process.terminationHandler = { [weak self] child in
                try? handle.close()
                if child.terminationStatus != 0 {
                    DispatchQueue.main.async {
                        self?.appendLog("The panel is installed. The local service could not start; see service.log beside the setup log.\n")
                    }
                }
            }
            try process.run()
            appendLog("Started the local service in the background.\n")
        } catch {
            appendLog("The panel is installed. Start its local service from the panel’s Setup section: \(error.localizedDescription)\n")
        }
    }

    @objc private func openHelp() {
        if let resources = Bundle.main.resourceURL {
            NSWorkspace.shared.open(resources.appendingPathComponent("Help.html"))
        }
    }

    @objc private func openLogs() {
        if FileManager.default.fileExists(atPath: logURL.path) {
            NSWorkspace.shared.activateFileViewerSelecting([logURL])
        } else {
            let alert = NSAlert()
            alert.messageText = "No setup log yet"
            alert.informativeText = "The log is saved here after installation: \(logURL.path)"
            alert.runModal()
        }
    }

    @objc private func openAfterEffects() {
        let manager = FileManager.default
        let roots = [URL(fileURLWithPath: "/Applications"), manager.homeDirectoryForCurrentUser.appendingPathComponent("Applications")]
        var applications: [URL] = []
        for root in roots {
            for candidate in (try? manager.contentsOfDirectory(at: root, includingPropertiesForKeys: nil)) ?? [] where candidate.lastPathComponent.hasPrefix("Adobe After Effects") {
                if candidate.pathExtension == "app" { applications.append(candidate) }
                else {
                    applications += ((try? manager.contentsOfDirectory(at: candidate, includingPropertiesForKeys: nil)) ?? []).filter { $0.pathExtension == "app" && $0.lastPathComponent.hasPrefix("Adobe After Effects") }
                }
            }
        }
        if let application = applications.sorted(by: { $0.path.localizedStandardCompare($1.path) == .orderedDescending }).first {
            NSWorkspace.shared.openApplication(at: application, configuration: NSWorkspace.OpenConfiguration(), completionHandler: nil)
        } else {
            let alert = NSAlert()
            alert.messageText = "Open After Effects from Creative Cloud"
            alert.informativeText = "After installing CapForge, restart After Effects and choose Window → Extensions → CapForge."
            alert.runModal()
        }
    }

    func windowShouldClose(_ sender: NSWindow) -> Bool { return !running }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply { return running ? .terminateCancel : .terminateNow }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { return true }
}

do {
    let arguments = Array(CommandLine.arguments.dropFirst())
    if arguments == ["--help"] {
        print("CapForge [--headless] [--dry-run] [--target /absolute/path] [--extension-root /absolute/path] [--enable-unsigned] [--skip-dependencies]")
        exit(0)
    }
    let options = try SetupOptions(arguments)
    if options.dryRun {
        let details: [String: Any] = ["runtime": options.runtime.path, "extensions": options.extensions.path, "bootstrap": try bootstrapURL(options).path, "enableUnsigned": options.enableUnsigned, "version": Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") ?? ""]
        let data = try JSONSerialization.data(withJSONObject: details, options: [.prettyPrinted, .sortedKeys])
        FileHandle.standardOutput.write(data)
        FileHandle.standardOutput.write(Data("\n".utf8))
    } else if options.headless {
        let process = try setupProcess(options)
        process.standardOutput = FileHandle.standardOutput
        process.standardError = FileHandle.standardError
        try process.run()
        process.waitUntilExit()
        exit(process.terminationStatus)
    } else {
        let application = NSApplication.shared
        let delegate = AppDelegate(options: options)
        application.setActivationPolicy(.regular)
        application.delegate = delegate
        withExtendedLifetime(delegate) { application.run() }
    }
} catch {
    FileHandle.standardError.write(Data("CapForge: \(error.localizedDescription)\n".utf8))
    exit(1)
}
