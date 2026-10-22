import SwiftUI
import AppKit

struct MCPConnectionView: View {
    @ObservedObject var m: LibraryModel
    var body: some View {
        MCPStatusSection(m: m)
        MCPClientSections(root: m.root, openOnboarding: m.openOnboarding)
    }
}

struct MCPClientSections: View {
    let root: URL
    var openOnboarding: (() -> Void)? = nil
    @State private var client: MCPClient = .codex
    @State private var copied: String?
    var body: some View {
        Section {
            Picker("使用的客户端", selection: $client) {
                ForEach(MCPClient.allCases) { Text($0.name).tag($0) }
            }
            LabeledContent("服务名称", value: "投研纵览（research_library）")
            LabeledContent("配置位置", value: client.destination)
        } header: { Text("选择客户端") } footer: {
            FormNote(client.steps)
        }
        Section {
            ScrollView([.horizontal, .vertical]) {
                Text(client.configuration(root: root)).font(.system(.callout, design: .monospaced))
                    .textSelection(.enabled).fixedSize(horizontal: true, vertical: true)
                    .padding(.vertical, 8).frame(maxWidth: .infinity, alignment: .leading)
            }.frame(height: client == .claudeCode ? 72 : 158)
            HStack {
                if let copied { Text(copied).font(.callout).foregroundStyle(.secondary) }
                Spacer()
                Button(client == .claudeCode ? "复制添加命令" : "复制完整配置", systemImage: "doc.on.doc") {
                    copy(client.configuration(root: root), label: "已复制")
                }.buttonStyle(.borderedProminent)
                Button("复制启动路径") { copy(MCPConfiguration.command(root: root), label: "启动路径已复制") }
            }
        } header: { Text(client.formatLabel) }
        Section {
            HStack {
                Text("在客户端验证连接")
                Spacer()
                Button("复制验证提示词") { copy(MCPClient.verificationPrompt, label: "验证提示词已复制") }
            }
            if let openOnboarding {
                HStack {
                    Text("重新查看接入步骤")
                    Spacer()
                    Button("打开接入引导", action: openOnboarding)
                }
            }
        } header: { Text("验证与帮助") } footer: {
            VStack(alignment: .leading, spacing: 6) {
                FormNote("完成客户端配置后，把验证提示词发给该客户端；需自行检查目标客户端是否正常调用。")
                if openOnboarding != nil {
                    FormNote("独立版运行环境包含在 App 内；资料、模型与可选组件保存在资料库目录，更新 App 不会覆盖资料。")
                }
            }
        }
        .onChange(of: client) { copied = nil }
    }
    func copy(_ value: String, label: String) {
        NSPasteboard.general.clearContents()
        let ok = NSPasteboard.general.setString(value, forType: .string)
        copied = ok && NSPasteboard.general.string(forType: .string) == value ? label : "复制失败，请重试"
    }
}

struct MCPStatusSection: View {
    @ObservedObject var m: LibraryModel
    var showClientReminder = false
    @State private var checking = false
    @State private var checkResult: String?
    @State private var checkOK = false
    var body: some View {
        Section {
            LabeledContent("本地服务", value: m.stateLabel)
            HStack {
                Spacer()
                Button(checking ? "检查中…" : "检查 MCP 连接") { Task { await check() } }.disabled(checking)
                if !m.running { Button("启动服务") { Task { await m.start() } }.disabled(m.starting) }
                if checking { ProgressView().controlSize(.small) }
            }
            if let result = checkResult {
                Label(result, systemImage: checkOK ? "checkmark.circle" : "exclamationmark.circle")
                    .font(.callout).textSelection(.enabled)
            }
        } header: { Text("连接信息") } footer: {
            VStack(alignment: .leading, spacing: 6) {
                FormNote("本地连接无需填写 URL 或 MCP Key。使用 MCP 时保持 App 的服务运行。")
                if showClientReminder { FormNote("需自行检查目标客户端是否正常调用。") }
            }
        }
    }
    func check() async {
        guard !checking else { return }
        checking = true; checkResult = nil
        defer { checking = false }
        let root = m.root
        let result = await Task.detached(priority: .userInitiated) { () -> (Bool, String) in
            guard FileManager.default.isExecutableFile(atPath: MCPConfiguration.command(root: root)) else { return (false, "启动程序不存在或不可执行，请检查 App 所在目录。") }
            let process = Process()
            process.executableURL = AppRuntime.executable(root: root)
            process.arguments = AppRuntime.arguments("check_mcp", root: root)
            process.currentDirectoryURL = root
            var env = ProcessInfo.processInfo.environment
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            env["RESEARCH_LIBRARY_ROOT"] = root.path
            env["TMPDIR"] = root.appendingPathComponent("tmp").path
            env["XDG_CACHE_HOME"] = root.appendingPathComponent("cache").path
            process.environment = env
            let pipe = Pipe(); process.standardOutput = pipe
            let log = root.appendingPathComponent("logs/mcp-check.stderr.log")
            FileManager.default.createFile(atPath: log.path, contents: nil)
            let errors = try? FileHandle(forWritingTo: log); process.standardError = errors
            defer { try? errors?.close() }
            do {
                try process.run()
                let data = pipe.fileHandleForReading.readDataToEndOfFile()
                process.waitUntilExit()
                guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] else { return (false, "检查结果无法读取，请查看运行日志。") }
                if process.terminationStatus == 0 && json["ok"] as? Bool == true {
                    return (true, "连接成功 · 发现 \(json["tool_count"] as? Int ?? 0) 个工具，资料库状态可读取")
                }
                return (false, json["error"] as? String ?? "连接失败，请启动服务后重试。")
            } catch { return (false, "检查失败：\(error.localizedDescription)") }
        }.value
        checkOK = result.0; checkResult = result.1
    }
}

/// Supporting copy belongs outside grouped controls, using the same quiet style.
struct FormNote: View {
    let text: String
    init(_ text: String) { self.text = text }
    var body: some View {
        Text(text).font(.system(size: 12)).foregroundStyle(.secondary)
            .textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
    }
}
