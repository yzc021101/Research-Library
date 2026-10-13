import AppKit
import SwiftUI

@MainActor final class AppUpdater: ObservableObject {
    let root: URL
    @Published var state: [String: Any] = [:]
    @Published var working = false
    @Published var error: String?
    private var pollTimer: Timer?
    private var autoTimer: Timer?
    var current: String { Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "0.6.5" }
    var phase: String { state["phase"] as? String ?? "idle" }
    var release: [String: Any] { state["release"] as? [String: Any] ?? [:] }
    init(root: URL) {
        self.root = root
        poll()
        pollTimer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in Task { @MainActor in self?.poll() } }
        autoTimer = Timer.scheduledTimer(withTimeInterval: 1800, repeats: true) { [weak self] _ in Task { @MainActor in await self?.automatic() } }
        Task { _ = await run("finish"); await automatic() }
    }
    func poll() {
        if let data = try? Data(contentsOf: root.appendingPathComponent("updates/state.json")), let s = try? JSONSerialization.jsonObject(with: data) as? [String: Any] { state = s }
    }
    func automatic() async {
        guard let data = try? Data(contentsOf: root.appendingPathComponent("data/settings.json")), let s = try? JSONSerialization.jsonObject(with: data) as? [String: Any], s["automatic_updates"] as? Bool == true else { return }
        _ = await run("check", automatic: true)
    }
    @discardableResult func run(_ action: String, automatic: Bool = false) async -> Bool {
        guard !working else { return false }
        working = true; error = nil
        defer { working = false; poll() }
        let process = Process()
        process.executableURL = AppRuntime.executable(root: root)
        process.arguments = AppRuntime.arguments("updater", root: root) + [action, "--current", current, "--target", Bundle.main.bundleURL.path, "--pid", String(ProcessInfo.processInfo.processIdentifier)] + (automatic ? ["--automatic"] : [])
        process.currentDirectoryURL = root
        var env = ProcessInfo.processInfo.environment; env["RESEARCH_LIBRARY_ROOT"] = root.path
        process.environment = env
        let log = root.appendingPathComponent("logs/updater.log")
        if !FileManager.default.fileExists(atPath: log.path) { FileManager.default.createFile(atPath: log.path, contents: nil) }
        let handle = try? FileHandle(forWritingTo: log); _ = try? handle?.seekToEnd()
        process.standardOutput = handle; process.standardError = handle
        return await withCheckedContinuation { continuation in
            process.terminationHandler = { p in continuation.resume(returning: p.terminationStatus == 0) }
            do { try process.run() } catch { self.error = error.localizedDescription; process.terminationHandler = nil; continuation.resume(returning: false) }
        }
    }
    func cancel() { try? Data().write(to: root.appendingPathComponent("updates/cancel")) }
}

struct UpdateSettings: View {
    @ObservedObject var m: LibraryModel
    @ObservedObject var updater: AppUpdater
    var body: some View {
        Section {
            HStack { Text("当前版本"); Spacer(); Text(updater.current).foregroundStyle(.secondary); Button("检查更新") { Task { await updater.run("check") } }.disabled(updater.working) }
            Toggle("自动更新", isOn: $m.preferences.automaticUpdates)
                .onChange(of: m.preferences.automaticUpdates) { _, enabled in if enabled { m.save(); Task { try? await Task.sleep(for: .milliseconds(400)); await updater.automatic() } } }
            if let v = updater.release["version"] as? String, ["available","ready","downloading","preparing"].contains(updater.phase) {
                HStack { Text("新版本 \(v)"); Spacer(); if let text = updater.release["release_url"] as? String, let url = URL(string: text) { Link("更新说明", destination: url) } }
            }
            if updater.phase == "available" {
                HStack { Text(ByteCountFormatter.string(fromByteCount: (updater.release["size"] as? NSNumber)?.int64Value ?? 0, countStyle: .file)).foregroundStyle(.secondary); Spacer(); Button("下载更新") { Task { await updater.run("download") } }.disabled(updater.working) }
            }
            if updater.phase == "ready" {
                HStack { Text("已下载并校验").foregroundStyle(.secondary); Spacer(); Button("安装并重启…") { install() }.disabled(updater.working || m.busy || m.modelBusy) }
            }
            if updater.working {
                if updater.phase == "downloading" {
                    ProgressView("正在下载更新", value: (updater.state["done"] as? NSNumber)?.doubleValue ?? 0, total: max(1,(updater.state["total"] as? NSNumber)?.doubleValue ?? 1))
                    HStack { Spacer(); Button("取消下载") { updater.cancel() } }
                } else { HStack { ProgressView().controlSize(.small); Text("正在检查或准备更新…").font(.callout) } }
            }
            if let text = updater.error ?? (updater.state["error"] as? String), !text.isEmpty { Text(text).font(.callout).foregroundStyle(.secondary).textSelection(.enabled) }
            else if let text = updater.state["message"] as? String { Text(text).font(.callout).foregroundStyle(.secondary) }
        } header: { Text("软件更新") } footer: { Text("自动更新开启后，每天从 GitHub 检查并下载正式版本，安装前由你选择重启。仅替换 App，保留资料库、模型和 MCP 配置。") }
    }
    func install() {
        let alert = NSAlert(); alert.messageText = "安装更新并重启投研纵览？"
        alert.informativeText = "会短暂停止本地服务，替换 App 后重新打开。来源文件、索引和设置保留。"; alert.addButton(withTitle: "安装并重启"); alert.addButton(withTitle: "取消")
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        Task {
            // Stop the service before handing off, and restore it if preparation fails.
            let wasRunning = m.running
            if wasRunning { await m.stop() }
            if await updater.run("install") { NSApp.terminate(nil) }
            else if wasRunning { await m.start() }
        }
    }
}
