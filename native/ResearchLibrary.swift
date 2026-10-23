import AppKit
import SwiftUI
import ServiceManagement

struct Preferences: Codable, Equatable {
    var sourceFolders: [String] = []
    var topK = 8
    var searchMode = "hybrid"
    var largeFileMode = false
    var autoScan = true
    var scanInterval = 30
    var startServiceOnLaunch = true
    var keepInMenuBar = true
    var appManaged = true
    var automaticUpdates = false
    var keepSnapshots = false
    var cacheRetentionDays = 30
    enum CodingKeys: String, CodingKey {
        case sourceFolders = "source_folders", topK = "top_k", searchMode = "search_mode"
        case largeFileMode = "large_file_mode"
        case autoScan = "auto_scan", scanInterval = "scan_interval"
        case automaticUpdates = "automatic_updates"
        case keepSnapshots = "keep_snapshots", cacheRetentionDays = "cache_retention_days"
        case startServiceOnLaunch = "start_service_on_launch", keepInMenuBar = "keep_in_menu_bar", appManaged = "app_managed"
    }
    init() {}
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        sourceFolders = try c.decodeIfPresent([String].self, forKey: .sourceFolders) ?? []
        topK = try c.decodeIfPresent(Int.self, forKey: .topK) ?? 8
        searchMode = try c.decodeIfPresent(String.self, forKey: .searchMode) ?? "hybrid"
        largeFileMode = try c.decodeIfPresent(Bool.self, forKey: .largeFileMode) ?? false
        autoScan = try c.decodeIfPresent(Bool.self, forKey: .autoScan) ?? true
        scanInterval = try c.decodeIfPresent(Int.self, forKey: .scanInterval) ?? 30
        startServiceOnLaunch = try c.decodeIfPresent(Bool.self, forKey: .startServiceOnLaunch) ?? true
        keepInMenuBar = try c.decodeIfPresent(Bool.self, forKey: .keepInMenuBar) ?? true
        appManaged = try c.decodeIfPresent(Bool.self, forKey: .appManaged) ?? true
        automaticUpdates = try c.decodeIfPresent(Bool.self, forKey: .automaticUpdates) ?? false
        keepSnapshots = try c.decodeIfPresent(Bool.self, forKey: .keepSnapshots) ?? false
        cacheRetentionDays = try c.decodeIfPresent(Int.self, forKey: .cacheRetentionDays) ?? 30
    }
}

struct Passage: Identifiable {
    let id: String, docID: String, title: String, text: String, source: String, date: String, path: String
    let page: Int
    let fileFormat: String, location: String
    let review: Bool
    let tables: [SourceTable]
    init(_ d: [String: Any]) {
        id = d["chunk_id"] as? String ?? UUID().uuidString
        docID = d["doc_id"] as? String ?? ""
        title = d["title"] as? String ?? "未命名文档"
        let warning = d["citation_warning"] as? String
        tables = SourceTable.parse(d["tables"])
        text = (warning.map { "⚠ " + $0 + "\n\n" } ?? "") + (d["display_text"] as? String ?? d["text"] as? String ?? "")
        source = d["institution"] as? String ?? "本地资料"
        date = d["publication_date_display"] as? String ?? d["published_date"] as? String ?? "日期未标注"
        path = d["original_path"] as? String ?? ""
        page = d["unit_index"] as? Int ?? d["pdf_page"] as? Int ?? 1
        fileFormat = d["file_format"] as? String ?? "pdf"
        location = (d["location"] as? [String: Any])?["label"] as? String ?? "PDF 第 \(page) 页"
        review = d["needs_review"] as? Bool ?? false
    }
}

struct ModelOption: Identifiable, Decodable {
    let id: String
    let name: String
    let dimensions: Int
    let downloadGB: Double
    let description: String
    let source: String
    let active: Bool
    let downloaded: Bool
    enum CodingKeys: String, CodingKey {
        case id, name, dimensions, description, source, active, downloaded
        case downloadGB = "download_gb"
    }
}

@MainActor final class LibraryModel: ObservableObject {
    let root: URL
    let updater: AppUpdater
    @Published var preferences = Preferences()
    @Published var selected = "overview"
    @Published var settingsPane = "general"
    var openSources: (() -> Void)?
    var openOnboarding: (() -> Void)?
    @Published var running = false
    @Published var starting = false
    @Published var busy = false
    @Published var syncProgress = ""
    @Published var docCount = 0
    @Published var chunkCount = 0
    @Published var modelLoaded = false
    @Published var models: [ModelOption] = []
    @Published var modelJob: [String: Any] = [:]
    @Published var componentInfo: [String: Any] = [:]
    @Published var requestingModel = false
    var modelBusy: Bool { requestingModel || ["starting", "downloading", "indexing", "ready"].contains(modelJob["phase"] as? String ?? "") }
    var activeModelName: String { models.first { $0.active }?.name ?? "Multilingual MiniLM L12" }
    @Published var lastSync = "尚未同步"
    @Published var files: [[String: Any]] = []
    @Published var message: String?
    @Published var query = ""
    @Published var searchSuggestions: [String] = []
    @Published var hits: [Passage] = []
    @Published var searching = false
    @Published var hasSearched = false
    @Published var searchSeconds = 0.0
    @Published var preview: NSImage?
    @Published var previewText: String?
    @Published var previewTables: [SourceTable] = []
    @Published var previewTitle = ""
    @Published var loginEnabled = false
    @Published var loginApproval = false
    private var worker: Process?
    private var timer: Timer?
    private var saving: Task<Void, Never>?
    var didChangeStatus: (() -> Void)?

    init(root: URL) {
        self.root = root
        self.updater = AppUpdater(root: root)
        preferences.sourceFolders = [root.appendingPathComponent("inbox").path]
        if let data = try? Data(contentsOf: settingsURL), let p = try? JSONDecoder().decode(Preferences.self, from: data) { preferences = p }
        preferences.appManaged = true
        persist()
        updateLoginStatus()
        timer = Timer.scheduledTimer(withTimeInterval: 3, repeats: true) { [weak self] _ in
            Task { @MainActor in await self?.refresh() }
        }
        if preferences.startServiceOnLaunch { Task { await start() } }
    }
    var settingsURL: URL { root.appendingPathComponent("data/settings.json") }
    var stateLabel: String { starting ? "正在启动" : (running ? (busy ? "正在整理资料" : "服务运行中") : "服务已停止") }
    var modeLabel: String { ["hybrid":"混合检索", "keyword":"关键词检索", "semantic":"语义检索"][preferences.searchMode] ?? "混合检索" }
    var visibleFiles: [[String: Any]] { files.filter { $0["state"] as? String != "missing" } }
    var failedCount: Int { files.filter { $0["state"] as? String == "failed" }.count }

    func persist() {
        do {
            let encoder = JSONEncoder(); encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            try encoder.encode(preferences).write(to: settingsURL, options: .atomic)
        } catch { message = "保存设置失败：\(error.localizedDescription)" }
    }
    func save() {
        persist()
        saving?.cancel()
        saving = Task {
            try? await Task.sleep(for: .milliseconds(250))
            guard !Task.isCancelled, running else { return }
            do {
                let data = try JSONEncoder().encode(preferences)
                _ = try await request("/settings", body: data)
                await refresh()
            } catch { if !Task.isCancelled { message = error.localizedDescription } }
        }
    }

    func request(_ path: String, body: Data? = nil) async throws -> [String: Any] {
        let configData = try Data(contentsOf: root.appendingPathComponent("data/service.json"))
        guard let info = try JSONSerialization.jsonObject(with: configData) as? [String: Any],
              let port = info["port"] as? Int, let token = info["token"] as? String,
              let url = URL(string: "http://127.0.0.1:\(port)\(path)") else { throw Failure("服务连接信息不可用") }
        var request = URLRequest(url: url)
        request.timeoutInterval = path == "/status" ? 3 : 180
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        if let body {
            request.httpMethod = "POST"; request.httpBody = body
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        let (data, response) = try await URLSession.shared.data(for: request)
        let result = (try JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
        if (response as? HTTPURLResponse)?.statusCode != 200 { throw Failure(result["error"] as? String ?? "请求失败") }
        return result
    }
    func post(_ path: String, _ payload: [String: Any] = [:]) async throws -> [String: Any] {
        try await request(path, body: JSONSerialization.data(withJSONObject: payload))
    }
    func retryImports(path: String? = nil) async {
        guard !busy && !modelBusy else { return }
        busy = true
        do {
            let result = try await post("/imports/retry", path.map { ["path": $0] } ?? [:])
            message = result["accepted"] as? Bool == true ? "已开始重试未完整入库文件" : "请等待当前任务完成后重试"
        } catch { message = error.localizedDescription }
        await refresh()
    }
    func refresh() async {
        do {
            let s = try await request("/status")
            running = true; busy = s["busy"] as? Bool ?? false
            let progress = s["sync_progress"] as? [String: Any] ?? [:]
            let stage = progress["stage"] as? String ?? ""
            let file = progress["file"] as? String ?? ""
            let index = progress["file_index"] as? Int ?? 0
            let total = progress["file_total"] as? Int ?? 0
            let detail = stage == "ocr" ? "识别图片 \(progress["image"] as? Int ?? 0)" : (stage == "embedding" ? "建立检索索引" : (stage == "converting" ? "转换旧版 Office" : "读取资料"))
            syncProgress = busy ? "\(index)/\(total) · \(file) · \(detail)" : ""
            docCount = s["active_documents"] as? Int ?? 0
            chunkCount = s["chunk_count"] as? Int ?? 0
            modelLoaded = s["model_loaded"] as? Bool ?? false
            files = s["sources"] as? [[String: Any]] ?? []
            let suggestions = s["search_suggestions"] as? [String] ?? []
            if searchSuggestions != suggestions { searchSuggestions = suggestions }
            if let list = s["models"], let data = try? JSONSerialization.data(withJSONObject: list), let values = try? JSONDecoder().decode([ModelOption].self, from: data) { models = values }
            modelJob = s["model_job"] as? [String: Any] ?? [:]
            componentInfo = s["components"] as? [String: Any] ?? [:]
            lastSync = s["last_sync"] as? String ?? "等待首次同步"
            if let error = s["last_error"] as? String { message = error }
        } catch { running = false; busy = false; modelLoaded = false; modelJob = [:]; searchSuggestions = [] }
        updateLoginStatus(); didChangeStatus?()
    }
    func start() async {
        guard !starting else { return }
        await refresh()
        if running { return }
        starting = true; message = nil; didChangeStatus?()
        defer { starting = false; didChangeStatus?() }
        let executable = AppRuntime.executable(root: root)
        guard FileManager.default.isExecutableFile(atPath: executable.path) else {
            message = "运行环境缺失。请在设置 → 模型 → 运行环境与可选组件中下载完整安装包。"; return
        }
        let process = Process()
        process.executableURL = executable
        process.arguments = AppRuntime.arguments("backend", root: root)
        process.currentDirectoryURL = root
        var env = ProcessInfo.processInfo.environment
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["RESEARCH_LIBRARY_ROOT"] = root.path
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
        env["TMPDIR"] = root.appendingPathComponent("tmp").path
        env["XDG_CACHE_HOME"] = root.appendingPathComponent("cache").path
        process.environment = env
        let log = root.appendingPathComponent("logs/native-backend.log")
        if !FileManager.default.fileExists(atPath: log.path) { FileManager.default.createFile(atPath: log.path, contents: nil) }
        let handle = try? FileHandle(forWritingTo: log); _ = try? handle?.seekToEnd()
        process.standardOutput = handle; process.standardError = handle
        do { try process.run(); worker = process }
        catch { message = "启动失败：\(error.localizedDescription)"; return }
        for _ in 0..<40 {
            try? await Task.sleep(for: .milliseconds(250))
            await refresh()
            if running { return }
            if !process.isRunning { break }
        }
        message = "服务未能启动，请查看运行日志。"
    }
    func stop() async {
        do { _ = try await post("/shutdown") } catch { }
        // All work is owned by this helper; stopping drops the model and frees its process.
        if let worker, worker.isRunning { worker.terminate() }
        for _ in 0..<16 {
            try? await Task.sleep(for: .milliseconds(150))
            await refresh()
            if !running { break }
        }
        if let worker, worker.isRunning { kill(worker.processIdentifier, SIGKILL) }
        worker = nil
        running = false; busy = false; starting = false; modelLoaded = false; didChangeStatus?()
    }
    func sync() async {
        if !running { await start() }
        guard running else { return }
        do { _ = try await post("/sync"); message = nil; await refresh() }
        catch { message = error.localizedDescription }
    }
    func search() async {
        guard !query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        guard running else { message = "先启动本地服务，再检索资料。"; return }
        searching = true; message = nil; hasSearched = true
        let begun = Date()
        defer { searching = false; searchSeconds = Date().timeIntervalSince(begun) }
        do {
            let response = try await post("/tool", ["name":"search_passages", "arguments":["query":query]])
            hits = (response["results"] as? [[String: Any]] ?? []).map(Passage.init)
            await refresh()
        } catch { hits = []; message = error.localizedDescription }
    }
    func cancelSync() async {
        do { _ = try await post("/sync/cancel"); message = "正在取消同步，已完成的文档会保留。" }
        catch { message = error.localizedDescription }
    }
    func showPage(_ hit: Passage) async {
        do {
            preview = nil; previewText = nil; previewTables = []
            previewTitle = "\(hit.location) · \(hit.title)"
            if hit.fileFormat != "pdf" {
                let d = try await post("/tool", ["name":"read_unit", "arguments":["doc_id":hit.docID,"unit_index":hit.page]])
                let unit = d["unit"] as? [String: Any] ?? [:]
                let document = d["document"] as? [String: Any] ?? [:]
                let warnings = document["extraction_warnings"] as? [String] ?? []
                if let path = d["image_path"] as? String { preview = NSImage(contentsOfFile: path) }
                previewTables = SourceTable.parse(unit["tables"])
                previewText = (unit["display_text"] as? String ?? unit["text"] as? String ?? "") + (warnings.isEmpty ? "" : "\n\n—— 读取说明 ——\n" + warnings.joined(separator: "\n"))
                return
            }
            let d = try await post("/tool", ["name":"read_page", "arguments":["doc_id":hit.docID,"pdf_page":hit.page,"render":true]])
            if let path = d["image_path"] as? String {
                preview = NSImage(contentsOfFile: path); previewTitle = "第 \(hit.page) 页 · \(hit.title)"
            }
        } catch { message = error.localizedDescription }
    }
    func addFolder() {
        let panel = NSOpenPanel()
        panel.title = "选择资料文件夹"; panel.message = "支持 PDF、Word（DOC/DOCX）、PPT（PPT/PPTX）、Excel（XLS/XLSX）、TXT、MD、RTF、CSV、TSV。原文件只读，索引和缓存保存在资料库目录。"
        panel.canChooseDirectories = true; panel.canChooseFiles = false; panel.allowsMultipleSelection = true
        if panel.runModal() == .OK {
            for url in panel.urls where !preferences.sourceFolders.contains(url.path) { preferences.sourceFolders.append(url.path) }
            save()
        }
    }
    func removeFolder(_ path: String) { preferences.sourceFolders.removeAll { $0 == path }; save() }
    func reveal(_ path: String) { guard !path.isEmpty else { message = "原文件已变化或不可用，请先同步资料。"; return }; NSWorkspace.shared.open(URL(fileURLWithPath: path)) }
    func switchModel(_ id: String) async {
        guard running else { message = "请先启动服务。"; return }
        requestingModel = true
        defer { requestingModel = false }
        do { _ = try await post("/models/switch", ["model": id]); await refresh() }
        catch { message = error.localizedDescription }
    }
    func cancelModel() async {
        do { _ = try await post("/models/cancel"); await refresh() }
        catch { message = error.localizedDescription }
    }
    func updateLoginStatus() {
        let state = SMAppService.mainApp.status
        loginEnabled = state == .enabled || state == .requiresApproval
        loginApproval = state == .requiresApproval
    }
    func setLogin(_ enabled: Bool) {
        do {
            if enabled { try SMAppService.mainApp.register() }
            else { try SMAppService.mainApp.unregister() }
            updateLoginStatus()
        } catch { updateLoginStatus(); message = "登录项设置未完成：\(error.localizedDescription)" }
    }
    struct Failure: LocalizedError { let text: String; init(_ text: String) { self.text = text }; var errorDescription: String? { text } }
}

struct MainView: View {
    @ObservedObject var m: LibraryModel
    @State private var columns: NavigationSplitViewVisibility = .all
    @State private var failedRecordsExpanded = true
    @State private var partialRecordsExpanded = true
    @State private var readyRecordsExpanded = false
    var title: String { ["overview":"概览", "sources":"资料来源", "search":"检索资料", "mcp":"MCP 接入"][m.selected] ?? "资料库" }

    var body: some View {
        NavigationSplitView(columnVisibility: $columns) {
            List(selection: Binding<String?>(get: { m.selected }, set: { if let value = $0 { m.selected = value } })) {
                Section("资料库") {
                    Label("概览", systemImage: "books.vertical").tag("overview")
                    Label("资料来源", systemImage: "folder").tag("sources")
                    Label("检索资料", systemImage: "magnifyingglass").tag("search")
                    Label("MCP 接入", systemImage: "point.3.connected.trianglepath.dotted").tag("mcp")
                }
            }
            .listStyle(.sidebar)
            .navigationSplitViewColumnWidth(min: 170, ideal: 200, max: 260)
            .safeAreaInset(edge: .bottom) {
                VStack(alignment: .leading, spacing: 5) {
                    Label(m.stateLabel, systemImage: m.running ? "checkmark.circle" : "pause.circle")
                    Text("\(m.docCount) 份文档").foregroundStyle(.secondary)
                }.font(.caption).frame(maxWidth: .infinity, alignment: .leading).padding()
            }
        } detail: {
            VStack(spacing: 0) {
                if let error = m.message {
                    HStack {
                        Label(error, systemImage: "exclamationmark.triangle").textSelection(.enabled)
                        Spacer()
                        Button("关闭提示", systemImage: "xmark") { m.message = nil }.labelStyle(.iconOnly).buttonStyle(.borderless)
                    }.font(.callout).padding().background(.quaternary)
                    Divider()
                }
                switch m.selected {
                case "sources": sources
                case "search": search
                case "mcp": Form { MCPConnectionView(m: m) }.formStyle(.grouped)
                default: overview
                }
            }
            .navigationTitle(title)
            .toolbar {
                ToolbarItemGroup {
                    if m.busy {
                        ProgressView().controlSize(.small)
                            .frame(width: 32, height: 28).padding(.horizontal, 4)
                            .accessibilityLabel("正在同步资料").help(m.syncProgress)
                        Button("取消同步", systemImage: "xmark.circle") { Task { await m.cancelSync() } }
                    }
                    Button("添加文件夹", systemImage: "folder.badge.plus") { m.addFolder() }
                    Button("立即同步", systemImage: "arrow.clockwise") { Task { await m.sync() } }.disabled(m.busy || m.starting)
                    Button(m.running ? "停止服务" : "启动服务", systemImage: m.running ? "stop.circle" : "play.circle") {
                        Task { if m.running { await m.stop() } else { await m.start() } }
                    }.disabled(m.starting)
                }
            }
        }
        .navigationSplitViewStyle(.balanced)
        .toolbarBackground(Color(nsColor: .windowBackgroundColor).opacity(0.96), for: .windowToolbar)
        .toolbarBackground(.visible, for: .windowToolbar)
        .frame(minWidth: 800, minHeight: 540)
        .onChange(of: m.preferences) { m.save() }
        .sheet(isPresented: Binding(get: { m.preview != nil || m.previewText != nil }, set: { if !$0 { m.preview = nil; m.previewText = nil } })) {
            VStack(spacing: 0) {
                HStack {
                    Text(m.previewTitle).font(.headline).lineLimit(1)
                    Spacer()
                    Button("完成") { m.preview = nil; m.previewText = nil }.keyboardShortcut(.cancelAction)
                }.padding()
                Divider()
                if let text = m.previewText {
                    ScrollView(.vertical) {
                        VStack(alignment: .leading, spacing: 20) {
                            if let image = m.preview {
                                Text("内嵌图片 · 请核对下方 OCR 文字").font(.headline)
                                Image(nsImage: image).resizable().scaledToFit().frame(maxWidth: .infinity)
                                Text("图片预览已应用裁剪和旋转，不代表整页排版。").font(.callout).foregroundStyle(.secondary)
                                Divider()
                            }
                            ForEach(m.previewTables) { table in TableContentView(table: table, preview: true) }
                            if !text.isEmpty {
                                Text(text).font(.system(.body, design: .monospaced)).textSelection(.enabled)
                                    .frame(maxWidth: .infinity, alignment: .leading).fixedSize(horizontal: false, vertical: true)
                            }
                        }.padding(24)
                    }.background(Color(nsColor: .textBackgroundColor))
                } else {
                    ScrollView([.horizontal, .vertical]) {
                        if let image = m.preview { Image(nsImage: image).resizable().scaledToFit().frame(width: 720).padding() }
                    }.background(Color(nsColor: .underPageBackgroundColor))
                }
            }.frame(width: 790, height: 720)
        }
    }

    func card<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 16, content: content)
            .padding(20).frame(maxWidth: .infinity, alignment: .leading)
            .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(Color(nsColor: .separatorColor), lineWidth: 1.25))
    }
    func page<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        ScrollView {
            // Result count is capped at 20. Stable eager layout avoids recycling
            // selectable AppKit text views while the scroll extent is changing.
            VStack(alignment: .leading, spacing: 18, content: content)
                .padding(24).frame(maxWidth: .infinity, alignment: .topLeading)
        }.frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            .background(Color(nsColor: .windowBackgroundColor))
    }
    func stat(_ value: Int, _ title: String, _ icon: String) -> some View {
        card {
            Label(title, systemImage: icon).font(.callout).foregroundStyle(.secondary)
            Text(value, format: .number).font(.system(.largeTitle, design: .rounded).weight(.semibold))
        }
    }
    var overview: some View {
        page {
            HStack(spacing: 16) {
                stat(m.docCount, "已收录文档", "doc.text")
                stat(m.preferences.sourceFolders.count, "资料文件夹", "folder")
                stat(m.preferences.topK, "返回片段 · Top K", "text.alignleft")
            }
            card {
                HStack(alignment: .top, spacing: 16) {
                    Image(systemName: m.running ? "checkmark.circle" : "power")
                        .font(.largeTitle).foregroundStyle(Color.accentColor)
                    VStack(alignment: .leading, spacing: 8) {
                        Text(m.stateLabel).font(.title3.weight(.semibold))
                        Text(m.running ? "App 与 MCP 共用本地资料库，可从菜单栏随时停止服务。" : "启动服务后可以同步资料和检索原文。")
                            .foregroundStyle(.secondary)
                        if m.busy { Text(m.syncProgress).font(.callout).foregroundStyle(.secondary).textSelection(.enabled) }
                        HStack {
                            Spacer()
                            if m.busy { Button("取消同步") { Task { await m.cancelSync() } } }
                            Button(m.running ? "停止服务" : "启动服务") { Task { if m.running { await m.stop() } else { await m.start() } } }
                                .disabled(m.starting)
                            Button("立即同步") { Task { await m.sync() } }.disabled(m.busy || m.starting)
                            if m.busy { ProgressView().controlSize(.small) }
                        }
                    }
                    Spacer(minLength: 0)
                }
                Divider()
                HStack {
                    Label(m.modelLoaded ? "模型已载入" : "模型按需载入", systemImage: "cpu")
                    Spacer()
                    Text("上次同步：\(m.lastSync)")
                }.font(.callout).foregroundStyle(.secondary)
            }
            card {
                Text("检索资料").font(.headline)
                Text("输入公司、产品或参数，查找相关原文与出处。").foregroundStyle(.secondary)
                HStack {
                    Text(m.modeLabel).font(.callout).foregroundStyle(.secondary)
                    Spacer()
                    Button("开始检索", systemImage: "magnifyingglass") { m.selected = "search" }.buttonStyle(.borderedProminent)
                    Button("添加资料文件夹", systemImage: "folder.badge.plus") { m.addFolder() }
                }
            }
            card {
                Label("MCP 接入", systemImage: "point.3.connected.trianglepath.dotted").font(.headline)
                Text("把资料库连接到 Codex、WorkBuddy、Claude Code 等 AI 工具。").foregroundStyle(.secondary)
                HStack {
                    Spacer()
                    Button("查看配置与指南") { m.selected = "mcp" }.buttonStyle(.borderedProminent)
                    Button("打开接入引导") { m.openOnboarding?() }
                }
            }
            if m.failedCount > 0 {
                Label("\(m.failedCount) 份文件入库失败，可在资料来源中查看。", systemImage: "exclamationmark.triangle")
            }
        }
    }

    var sources: some View {
        page {
            HStack {
                Text("\(m.preferences.sourceFolders.count) 个来源文件夹").font(.headline)
                Spacer()
                Button("添加文件夹…", systemImage: "plus") { m.addFolder() }.buttonStyle(.borderedProminent)
            }
            if m.preferences.sourceFolders.isEmpty {
                card {
                    Label("添加资料来源", systemImage: "folder").font(.headline)
                    Text("支持 PDF、DOC/DOCX、PPT/PPTX、XLS/XLSX、TXT、MD、RTF、CSV、TSV，子文件夹也会一并收录。").foregroundStyle(.secondary)
                    Text("旧版 Office 自动在后台转换，原文件保持不变；转换后的排版、数字和图片请对照原文件。").font(.callout).foregroundStyle(.secondary)
                    HStack { Spacer(); Button("选择文件夹…") { m.addFolder() } }
                }
            }
            ForEach(m.preferences.sourceFolders, id: \.self) { path in
                card {
                    HStack(alignment: .top, spacing: 12) {
                        Image(systemName: "folder.fill").font(.title2).foregroundStyle(Color.accentColor)
                        VStack(alignment: .leading, spacing: 6) {
                            Text(URL(fileURLWithPath: path).lastPathComponent).font(.headline)
                            Text(path).font(.callout).foregroundStyle(.secondary).textSelection(.enabled)
                            if !FileManager.default.fileExists(atPath: path) {
                                Label("文件夹不可访问", systemImage: "exclamationmark.triangle").font(.callout)
                            }
                        }
                        Spacer()
                        Button("在 Finder 中打开", systemImage: "arrow.up.forward.square") { m.reveal(path) }.labelStyle(.iconOnly)
                        Button("移除来源", systemImage: "minus.circle") { m.removeFolder(path) }.labelStyle(.iconOnly).help("保留原文件，停止收录")
                    }
                }
            }
            Text("移除来源只停止收录，保留原文件。").font(.callout).foregroundStyle(.secondary)
            if !m.visibleFiles.isEmpty {
                card {
                    Text("入库记录").font(.headline)
                    importGroup("导入失败", files: m.visibleFiles.filter { $0["state"] as? String == "failed" }, expanded: $failedRecordsExpanded, failed: true)
                    Divider()
                    importGroup("部分入库", files: m.visibleFiles.filter { $0["state"] as? String == "partial" }, expanded: $partialRecordsExpanded, failed: true, partial: true)
                    Divider()
                    importGroup("已入库", files: m.visibleFiles.filter { $0["state"] as? String == "ready" }, expanded: $readyRecordsExpanded, failed: false)
                }
            }
        }
    }

    func importGroup(_ title: String, files: [[String: Any]], expanded: Binding<Bool>, failed: Bool, partial: Bool = false) -> some View {
        DisclosureGroup(isExpanded: expanded) {
            if expanded.wrappedValue {
                if files.isEmpty {
                    Text(failed ? "没有失败的导入记录" : "暂无已入库文档").font(.callout).foregroundStyle(.secondary).padding(.top, 8)
                } else {
                    if failed {
                        HStack { Spacer(); Button("重试所有未完整入库文件") { Task { await m.retryImports() } }
                            .disabled(m.busy || m.modelBusy).accessibilityIdentifier("RetryAllImports") }
                    }
                    LazyVStack(alignment: .leading, spacing: 12) {
                        ForEach(files, id: \.pathIdentity) { file in
                            VStack(alignment: .leading, spacing: 6) {
                                HStack(alignment: .top) {
                                    Image(systemName: failed ? "exclamationmark.circle.fill" : "doc.text")
                                        .foregroundStyle(failed ? (partial ? Color.orange : Color.red) : Color.secondary)
                                    Text(URL(fileURLWithPath: file["path"] as? String ?? "").lastPathComponent)
                                        .lineLimit(2).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
                                        .help(file["path"] as? String ?? "")
                                    if failed {
                                        Button("重试") { Task { await m.retryImports(path: file["path"] as? String) } }
                                            .disabled(m.busy || m.modelBusy).accessibilityIdentifier("RetryImport")
                                    }
                                }
                                if let error = file["error"] as? String, !error.isEmpty {
                                    Text(error).font(.callout).foregroundStyle(.secondary).textSelection(.enabled)
                                }
                            }
                            Divider()
                        }
                    }.padding(.top, 10)
                }
            }
        } label: {
            HStack {
                Label(title, systemImage: failed ? "exclamationmark.circle.fill" : "checkmark.circle")
                    .foregroundStyle(failed && !files.isEmpty ? (partial ? Color.orange : Color.red) : Color.primary)
                Spacer()
                Text("\(files.count) 份").foregroundStyle(.secondary)
            }.font(.headline).padding(.vertical, 4)
        }.accessibilityIdentifier(partial ? "PartialImports" : failed ? "FailedImports" : "ReadyImports")
    }

    var search: some View {
        page {
            card {
                HStack(spacing: 12) {
                    LibrarySearchField(text: $m.query) { Task { await m.search() } }
                        .frame(minWidth: 200, maxWidth: .infinity).frame(height: 26)
                    Button("检索") { Task { await m.search() } }.buttonStyle(.borderedProminent)
                        .disabled(m.searching || m.query.trimmingCharacters(in: .whitespaces).isEmpty)
                }
                HStack {
                    Text(m.modeLabel)
                    Spacer()
                    Text("最多返回 \(m.preferences.topK) 个片段")
                }.font(.callout).foregroundStyle(.secondary)
            }
            if m.searching {
                card { HStack { ProgressView().controlSize(.small); Text("正在检索…").foregroundStyle(.secondary) } }
            } else if !m.hasSearched || m.query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                card {
                    Label(m.docCount == 0 ? "先添加研究资料" : "查找原文和参数", systemImage: "doc.text.magnifyingglass").font(.headline)
                    Text(m.docCount == 0 ? "选择资料文件夹，同步完成后即可检索。" : "输入问题或关键词，结果会保留文件名称、来源和原文位置。")
                        .foregroundStyle(.secondary)
                    HStack {
                        Spacer()
                        if m.docCount == 0 {
                            Button("添加资料文件夹…") { m.addFolder() }
                            Button("管理来源") { m.selected = "sources" }
                        } else if !m.searchSuggestions.isEmpty {
                            VStack(alignment: .trailing, spacing: 8) {
                                ForEach(m.searchSuggestions, id: \.self) { suggestion in
                                    Button {
                                        m.query = suggestion; Task { await m.search() }
                                    } label: {
                                        Text("试试：\(suggestion)").lineLimit(1).truncationMode(.tail)
                                    }.help(suggestion)
                                }
                            }
                        }
                    }
                }
            } else {
                HStack {
                    Text("\(m.hits.count) 个相关片段").font(.headline)
                    Spacer()
                    Text(String(format: "%.2f 秒", m.searchSeconds)).font(.callout).foregroundStyle(.secondary)
                }
                if m.hits.isEmpty {
                    card {
                        Label("没有找到匹配内容", systemImage: "magnifyingglass").font(.headline)
                        Text(m.docCount == 0 ? "资料库暂无已收录文档，请先添加来源文件夹。" : "试试其他关键词，或检查资料范围与检索方式。")
                            .foregroundStyle(.secondary)
                    }
                }
                ForEach(m.hits) { hit in
                    card {
                        HStack {
                            Text(hit.source).font(.subheadline.weight(.medium))
                            Text(hit.date).font(.callout).foregroundStyle(.secondary)
                            Spacer()
                            Text(hit.fileFormat == "pdf" ? hit.location : "\(hit.fileFormat.uppercased()) · \(hit.location)").font(.callout).foregroundStyle(.secondary)
                        }
                        Text(hit.title).font(.headline).textSelection(.enabled)
                        if !hit.text.isEmpty {
                            Text(hit.text).lineSpacing(4).fixedSize(horizontal: false, vertical: true).textSelection(.enabled)
                        }
                        ForEach(hit.tables) { table in TableContentView(table: table) }
                        Divider()
                        HStack {
                            if hit.review { Label("OCR 内容，请核对原图", systemImage: "eye").font(.callout).foregroundStyle(.secondary) }
                            Spacer()
                            Button(hit.fileFormat == "pdf" ? "查看原页" : "查看原文", systemImage: "doc.richtext") { Task { await m.showPage(hit) } }
                            Button("打开原文件", systemImage: "arrow.up.forward.square") { m.reveal(hit.path) }.disabled(hit.path.isEmpty)
                        }
                    }
                }
            }
        }
    }

}

// Keep search input in SwiftUI. An embedded NSSearchField can invalidate hosting
// constraints while AppKit updates cursor tracking during a scroll (macOS 26).
struct LibrarySearchField: View {
    @Binding var text: String
    var submit: () -> Void
    @FocusState private var focused: Bool
    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
            TextField("搜索资料", text: $text)
                .textFieldStyle(.plain)
                .accessibilityLabel("搜索资料")
                .focused($focused)
                .onSubmit(submit)
            if !text.isEmpty {
                Button {
                    text = ""; focused = true
                } label: {
                    Image(systemName: "xmark.circle.fill").foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("清除搜索")
            }
        }
        .padding(.horizontal, 7).padding(.vertical, 4)
        .background(Color(nsColor: .textBackgroundColor), in: RoundedRectangle(cornerRadius: 6))
        .overlay(RoundedRectangle(cornerRadius: 6).strokeBorder(Color(nsColor: .separatorColor), lineWidth: 0.75))
    }
}

struct TopKField: View {
    @Binding var value: Int
    @State private var text = ""
    @FocusState private var focused: Bool
    var body: some View {
        TextField("1–20", text: $text)
            .labelsHidden()
            .textFieldStyle(.roundedBorder)
            .multilineTextAlignment(.trailing)
            .frame(width: 72)
            .focused($focused)
            .accessibilityLabel("返回片段数 Top K")
            .help("输入 1 至 20 的整数")
            .onAppear { text = String(value) }
            .onChange(of: text) { if let n = Int(text), (1...20).contains(n) { value = n } }
            .onChange(of: value) { if !focused { text = String(value) } }
            .onChange(of: focused) { if !focused { text = String(value) } }
            .onSubmit { text = String(value); focused = false }
    }
}

struct SettingsView: View {
    @ObservedObject var m: LibraryModel
    @State private var pendingModel: ModelOption?
    var body: some View {
        Form {
            switch m.settingsPane {
            case "retrieval":
                Section {
                    LabeledContent("返回片段数（Top K）") { TopKField(value: $m.preferences.topK) }
                    Picker("检索方式", selection: $m.preferences.searchMode) {
                        Text("混合检索").tag("hybrid")
                        Text("关键词").tag("keyword")
                        Text("语义检索").tag("semantic")
                    }
                } header: { Text("检索") } footer: { Text("App 与 MCP 共用默认值，单次 MCP 请求可另行指定。") }
                Section("模型") { LabeledContent("当前模型", value: m.activeModelName) }
            case "mcp":
                MCPConnectionView(m: m)
            case "models":
                modelControls
            case "data":
                Section {
                    Toggle("大文件模式", isOn: $m.preferences.largeFileMode)
                    Toggle("自动检测文件变化", isOn: $m.preferences.autoScan)
                    Picker("检查间隔", selection: $m.preferences.scanInterval) {
                        Text("15 秒").tag(15); Text("30 秒").tag(30); Text("1 分钟").tag(60)
                        Text("5 分钟").tag(300); Text("10 分钟").tag(600)
                    }.disabled(!m.preferences.autoScan)
                } header: { Text("资料同步") } footer: { Text("服务运行时检查来源文件夹。默认读取最多 200 万个有效单元格；大文件模式提高到 500 万格，处理时间和索引空间也会增加。部分入库的文件将在切换模式后重新读取。") }
                Section {
                    LabeledContent("来源文件夹") { Text(m.preferences.sourceFolders.count, format: .number) }
                    HStack {
                        Spacer()
                        Button("管理来源文件夹…") { m.openSources?() }
                        Button("打开资料库文件夹…") { m.reveal(m.root.path) }
                    }
                } header: { Text("储存") } footer: { Text("索引、模型和日志保存在资料库目录。外部来源文件夹只读。") }
                StorageSettings(m: m)
            default:
                Section {
                    Toggle("登录 Mac 时启动", isOn: Binding(get: { m.loginEnabled }, set: { m.setLogin($0) }))
                    if m.loginApproval { HStack { Spacer(); Button("在系统设置中允许登录项…") { SMAppService.openSystemSettingsLoginItems() } } }
                    Toggle("打开 App 时启动服务", isOn: $m.preferences.startServiceOnLaunch)
                } header: { Text("启动") }
                Section {
                    Toggle("关闭窗口后保留在菜单栏", isOn: $m.preferences.keepInMenuBar)
                } header: { Text("后台运行") } footer: { Text("在菜单栏中选择“停止服务”可释放模型内存；选择“退出并停止服务”可完全退出。") }
                UpdateSettings(m: m, updater: m.updater)
            }
            if let error = m.message { Section { Label(error, systemImage: "exclamationmark.triangle").font(.callout).textSelection(.enabled) } }
        }
        .formStyle(.grouped)
        .frame(width: 560, height: m.settingsPane == "mcp" ? 650 : (["models", "data"].contains(m.settingsPane) ? 650 : 620))
        .alert("切换向量模型？", isPresented: Binding(get: { pendingModel != nil }, set: { if !$0 { pendingModel = nil } })) {
            if let option = pendingModel {
                Button(option.downloaded ? "重建索引并切换" : "下载并切换") { pendingModel = nil; Task { await m.switchModel(option.id) } }
                Button("取消", role: .cancel) { pendingModel = nil }
            }
        } message: {
            if let option = pendingModel {
                Text(option.downloaded ? "将为 \(option.name) 重建向量索引，成功后启用。" : String(format: "将下载 %@（约 %.2f GB）并重建向量索引。成功后才启用新模型，失败或取消会继续使用当前模型。", option.name, option.downloadGB))
            }
        }
        .onChange(of: m.preferences) { m.save() }
    }
    @ViewBuilder var modelControls: some View {
        if !m.running {
            Section { Text("启动服务后可管理向量模型。").foregroundStyle(.secondary); HStack { Spacer(); Button("启动服务") { Task { await m.start() } }.disabled(m.starting) } }
        }
        Section {
            ForEach(m.models) { option in
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Text(option.name).font(.headline)
                        Spacer()
                        if option.active && option.downloaded { Button("重建索引…") { pendingModel = option }.disabled(!m.running || m.modelBusy || m.busy) }
                        else {
                            Button(option.downloaded ? "切换…" : "下载并切换…") { pendingModel = option }
                                .disabled(!m.running || m.modelBusy || m.busy)
                        }
                    }
                    Text(option.description).font(.callout).foregroundStyle(.secondary)
                    HStack {
                        Text("\(option.dimensions) 维 · " + (option.downloaded ? "已下载" : String(format: "约 %.2f GB", option.downloadGB)))
                        Spacer()
                        if let url = URL(string: option.source) { Link("模型说明", destination: url) }
                    }.font(.caption).foregroundStyle(.secondary)
                    if option.downloaded {
                        HStack { Spacer(); Button("移除模型…") {
                            let alert = NSAlert(); alert.messageText = "移除本机模型文件？"; alert.informativeText = "保留文档与文本索引。当前模型移除后仍可使用关键词检索。"; alert.addButton(withTitle: "移除"); alert.addButton(withTitle: "取消")
                            if alert.runModal() == .alertFirstButtonReturn { Task { do { _ = try await m.post("/models/remove", ["model": option.id]); await m.refresh() } catch { m.message = error.localizedDescription } } }
                        }.disabled(m.busy || m.modelBusy) }
                    }
                }.padding(.vertical, 4)
            }
        } header: { Text("本地向量模型") } footer: {
            Text("只在选择下载后联网获取模型，文件统一保存在资料库目录。下载量为估计值，不代表内存占用；切换时需要额外的模型与索引空间。")
        }
        ComponentSettings(m: m)
        if m.modelBusy {
            Section {
                if m.modelJob["phase"] as? String == "indexing" {
                    let done = m.modelJob["completed"] as? Int ?? 0
                    let total = m.modelJob["total"] as? Int ?? 0
                    ProgressView("重建索引：\(done) / \(total) 个片段", value: Double(done), total: Double(max(total, 1)))
                } else { HStack { ProgressView().controlSize(.small); Text("正在下载或准备模型…") } }
                HStack { Spacer(); Button("取消任务", role: .cancel) { Task { await m.cancelModel() } } }
            }
        } else if let error = m.modelJob["error"] as? String {
            Section { Label(error, systemImage: "exclamationmark.circle").font(.callout).textSelection(.enabled) }
        } else if m.modelJob["phase"] as? String == "complete" {
            Section { Label("模型与索引已切换", systemImage: "checkmark.circle") }
        }
    }

}

@MainActor final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, NSToolbarDelegate {
    var model: LibraryModel!
    var window: NSWindow!
    var settingsWindow: NSWindow?
    var onboardingWindow: NSWindow?
    private var closeObserver: NSObjectProtocol?
    var statusItem: NSStatusItem!
    let panes = [("general", "通用", "gearshape"), ("retrieval", "检索", "magnifyingglass"), ("data", "资料", "folder"), ("models", "模型", "cpu"), ("mcp", "MCP 接入", "point.3.connected.trianglepath.dotted")]

    func applicationDidFinishLaunching(_ notification: Notification) {
        // A second copy must reopen the running library instead of competing for its Dock tile.
        if ProcessInfo.processInfo.environment["RESEARCH_LIBRARY_ROOT"] == nil, let identifier = Bundle.main.bundleIdentifier,
           let existing = NSRunningApplication.runningApplications(withBundleIdentifier: identifier)
            .first(where: { $0.processIdentifier != ProcessInfo.processInfo.processIdentifier && !$0.isTerminated }),
           let url = existing.bundleURL {
            let configuration = NSWorkspace.OpenConfiguration()
            configuration.activates = true
            NSWorkspace.shared.openApplication(at: url, configuration: configuration) { _, _ in
                DispatchQueue.main.async { NSApp.terminate(nil) }
            }
            return
        }
        let sibling = Bundle.main.bundleURL.deletingLastPathComponent()
        let configured = (Bundle.main.object(forInfoDictionaryKey: "ResearchLibraryDataRoot") as? String).map { URL(fileURLWithPath: $0, isDirectory: true) }
        // Development builds follow their adjacent library; installed builds use the
        // signed, build-time location without writing user data into /Applications.
        let dataHome = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/research_library")
        let override = ProcessInfo.processInfo.environment["RESEARCH_LIBRARY_ROOT"].map { URL(fileURLWithPath: $0, isDirectory: true) }
        let root = override ?? (AppRuntime.packaged ? AppRuntime.libraryRoot(defaultRoot: dataHome) : (FileManager.default.fileExists(atPath: sibling.appendingPathComponent("src/backend.py").path) ? sibling : (configured ?? sibling)))
        do { try AppRuntime.prepare(root: root) } catch { NSApp.terminate(nil); return }
        guard FileManager.default.isWritableFile(atPath: root.appendingPathComponent("data").path) else {
            let alert = NSAlert()
            alert.messageText = "找不到本机资料库"
            alert.informativeText = "资料库目录不可写，或应用运行环境不完整。请检查目录权限或重新安装 App。\n\n\(root.path)"
            alert.addButton(withTitle: "退出")
            NSApp.activate(ignoringOtherApps: true)
            alert.runModal()
            NSApp.terminate(nil)
            return
        }
        model = LibraryModel(root: root)
        model.openOnboarding = { [weak self] in self?.showOnboarding() }
        model.openSources = { [weak self] in self?.model.selected = "sources"; self?.showWindow() }
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1080, height: 740), styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView], backing: .buffered, defer: false)
        window.title = "投研纵览"
        window.titlebarAppearsTransparent = false
        window.titlebarSeparatorStyle = .line
        window.toolbarStyle = .unified
        window.isReleasedWhenClosed = false
        window.minSize = NSSize(width: 820, height: 580)
        window.delegate = self
        window.contentViewController = NSHostingController(rootView: MainView(m: model))
        window.center()
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        if let url = Bundle.main.url(forResource: "MenuBarTemplate", withExtension: "png"),
           let image = NSImage(contentsOf: url) {
            image.size = NSSize(width: 22, height: 22)
            image.isTemplate = true
            image.accessibilityDescription = "投研纵览"
            statusItem.button?.image = image
        } else {
            statusItem.button?.image = NSImage(systemSymbolName: "books.vertical", accessibilityDescription: "投研纵览")
        }
        statusItem.button?.toolTip = "投研纵览"
        model.didChangeStatus = { [weak self] in self?.refreshMenu() }
        refreshMenu()
        makeMainMenu()
        closeObserver = NotificationCenter.default.addObserver(forName: NSWindow.willCloseNotification, object: nil, queue: .main) { [weak self] note in
            let closing = note.object as? NSWindow
            Task { @MainActor in self?.updateActivationPolicy(excluding: closing) }
        }
        let event = NSAppleEventManager.shared().currentAppleEvent
        let loginLaunch = event?.paramDescriptor(forKeyword: keyAEPropData)?.enumCodeValue == keyAELaunchedAsLogInItem
        if loginLaunch { NSApp.setActivationPolicy(.accessory) } else { showWindow() }
    }
    func presentAsApplication() {
        // Let macOS render the bundle icon, including its system rounded mask.
        // Assigning applicationIconImage uses the raw bitmap as a custom Dock tile.
        NSApp.setActivationPolicy(.regular)
    }
    var onboardingURL: URL { model.root.appendingPathComponent("data/onboarding.json") }
    var needsOnboarding: Bool {
        guard let data = try? Data(contentsOf: onboardingURL),
              let state = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return true }
        return state["status"] as? String != "completed" && state["status"] as? String != "deferred"
    }
    @discardableResult func saveOnboarding(completed: Bool) -> Bool {
        do {
            let data = try JSONSerialization.data(withJSONObject: ["version": 1, "status": completed ? "completed" : "deferred"], options: [.prettyPrinted, .sortedKeys])
            try data.write(to: onboardingURL, options: .atomic)
            return true
        } catch { model.message = "保存引导状态失败：\(error.localizedDescription)"; return false }
    }
    @objc func showOnboarding() {
        presentAsApplication()
        if onboardingWindow == nil {
            let w = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 720, height: 680), styleMask: [.titled, .closable], backing: .buffered, defer: false)
            w.title = "MCP 接入引导"; w.isReleasedWhenClosed = false; w.delegate = self
            w.contentViewController = NSHostingController(rootView: OnboardingView(m: model) { [weak self] completed in
                guard let self, self.saveOnboarding(completed: completed) else { return }
                self.onboardingWindow?.close()
            })
            w.center(); onboardingWindow = w
        }
        onboardingWindow?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }
    @objc func showMCP() { model.selected = "mcp"; showWindow() }
    func updateActivationPolicy(excluding closed: NSWindow? = nil) {
        let hasWindow = NSApp.windows.contains { candidate in
            candidate !== closed && candidate !== statusItem?.button?.window && (candidate.isVisible || candidate.isMiniaturized) && candidate.level == .normal && (candidate.canBecomeMain || candidate.canBecomeKey)
        }
        if hasWindow { presentAsApplication() } else { NSApp.setActivationPolicy(.accessory) }
    }
    func windowWillClose(_ notification: Notification) {
        let closing = notification.object as? NSWindow
        if closing === onboardingWindow { onboardingWindow = nil }
        DispatchQueue.main.async { [weak self] in self?.updateActivationPolicy(excluding: closing) }

    }
    func makeMainMenu() {
        let main = NSMenu()
        let appItem = NSMenuItem(); let appMenu = NSMenu(title: "投研纵览")
        add(appMenu, "关于 投研纵览", #selector(about), "")
        appMenu.addItem(.separator())
        add(appMenu, "设置…", #selector(settings), ",")
        add(appMenu, "MCP 接入", #selector(showMCP), "")
        add(appMenu, "接入引导…", #selector(showOnboarding), "")
        appMenu.addItem(.separator())
        add(appMenu, "退出并停止服务", #selector(quit), "q")
        appItem.submenu = appMenu; main.addItem(appItem)
        let editItem = NSMenuItem(); let editMenu = NSMenu(title: "编辑")
        for (title, action, key) in [("撤销", "undo:", "z"), ("剪切", "cut:", "x"), ("复制", "copy:", "c"), ("粘贴", "paste:", "v"), ("全选", "selectAll:", "a")] {
            editMenu.addItem(NSMenuItem(title: title, action: Selector(action), keyEquivalent: key))
        }
        editItem.submenu = editMenu; main.addItem(editItem)
        let winItem = NSMenuItem(); let winMenu = NSMenu(title: "窗口")
        add(winMenu, "打开资料库", #selector(showWindow), "0")
        let closeItem = NSMenuItem(title: "关闭窗口", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
        winMenu.addItem(closeItem); winItem.submenu = winMenu; main.addItem(winItem)
        NSApp.mainMenu = main
        NSApp.windowsMenu = winMenu
    }
    func refreshMenu() {
        let menu = NSMenu()
        let state = NSMenuItem(title: model.stateLabel, action: nil, keyEquivalent: ""); state.isEnabled = false; menu.addItem(state)
        menu.addItem(.separator())
        add(menu, "打开资料库", #selector(showWindow), "0")
        add(menu, model.running ? "停止服务" : "启动服务", #selector(toggleService), "")
        add(menu, "立即同步", #selector(sync), "")
        add(menu, "设置…", #selector(settings), ",")
        add(menu, "MCP 接入", #selector(showMCP), "")
        menu.addItem(.separator())
        add(menu, "退出并停止服务", #selector(quit), "q")
        statusItem.menu = menu
    }
    func add(_ menu: NSMenu, _ title: String, _ selector: Selector, _ key: String) {
        let item = NSMenuItem(title: title, action: selector, keyEquivalent: key); item.target = self; menu.addItem(item)
    }
    @objc func showWindow() {
        presentAsApplication()
        window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
        if needsOnboarding { showOnboarding() }
    }
    @objc func settings() {
        presentAsApplication()
        if settingsWindow == nil {
            let w = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 560, height: 420), styleMask: [.titled, .closable], backing: .buffered, defer: false)
            w.isReleasedWhenClosed = false; w.delegate = self
            w.contentViewController = NSHostingController(rootView: SettingsView(m: model))
            w.toolbarStyle = .preference
            let toolbar = NSToolbar(identifier: "ResearchLibrary.Settings")
            toolbar.delegate = self; toolbar.allowsUserCustomization = false; toolbar.autosavesConfiguration = false
            toolbar.displayMode = .iconAndLabel
            w.toolbar = toolbar
            w.center(); settingsWindow = w
        }
        settingsWindow?.title = panes.first { $0.0 == model.settingsPane }?.1 ?? "通用"
        settingsWindow?.toolbar?.selectedItemIdentifier = NSToolbarItem.Identifier(model.settingsPane)
        settingsWindow?.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
    }
    func toolbarDefaultItemIdentifiers(_ toolbar: NSToolbar) -> [NSToolbarItem.Identifier] { panes.map { NSToolbarItem.Identifier($0.0) } }
    func toolbarAllowedItemIdentifiers(_ toolbar: NSToolbar) -> [NSToolbarItem.Identifier] { toolbarDefaultItemIdentifiers(toolbar) }
    func toolbarSelectableItemIdentifiers(_ toolbar: NSToolbar) -> [NSToolbarItem.Identifier] { toolbarDefaultItemIdentifiers(toolbar) }
    func toolbar(_ toolbar: NSToolbar, itemForItemIdentifier id: NSToolbarItem.Identifier, willBeInsertedIntoToolbar flag: Bool) -> NSToolbarItem? {
        guard let pane = panes.first(where: { $0.0 == id.rawValue }) else { return nil }
        let item = NSToolbarItem(itemIdentifier: id)
        item.label = pane.1; item.image = NSImage(systemSymbolName: pane.2, accessibilityDescription: pane.1)
        item.target = self; item.action = #selector(selectPane(_:)); return item
    }
    @objc func selectPane(_ sender: NSToolbarItem) {
        model.settingsPane = sender.itemIdentifier.rawValue
        settingsWindow?.title = sender.label
        settingsWindow?.toolbar?.selectedItemIdentifier = sender.itemIdentifier
    }
    @objc func about() { presentAsApplication(); NSApp.orderFrontStandardAboutPanel(options: [.applicationName: "投研纵览", .applicationVersion: Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "", .version: "独立试用版"]) }
    @objc func toggleService() { Task { if model.running { await model.stop() } else { await model.start() } } }
    @objc func sync() { Task { await model.sync() } }
    @objc func quit() { Task { await model.stop(); NSApp.terminate(nil) } }
    func windowShouldClose(_ sender: NSWindow) -> Bool {
        if sender === onboardingWindow {
            if needsOnboarding && !saveOnboarding(completed: false) { return false }
            return true
        }
        if sender === settingsWindow { return true }
        if model.preferences.keepInMenuBar {
            sender.orderOut(nil)
            updateActivationPolicy(excluding: sender)
            return false
        }
        quit(); return false
    }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool { showWindow(); return true }
}

@main struct ResearchLibraryMain {
    @MainActor static func main() {
        let app = NSApplication.shared
        app.setActivationPolicy(.regular)
        let delegate = AppDelegate()
        app.delegate = delegate
        app.run()
        _ = delegate
    }
}

private extension Dictionary where Key == String, Value == Any {
    var pathIdentity: String { self["path"] as? String ?? "" }
}
