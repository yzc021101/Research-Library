import SwiftUI
import AppKit
struct ComponentSettings: View {
    @ObservedObject var m: LibraryModel
    var items: [[String: Any]] { m.componentInfo["items"] as? [[String: Any]] ?? [] }
    var job: [String: Any] { m.componentInfo["job"] as? [String: Any] ?? [:] }
    var working: Bool { ["installing", "downloading"].contains(job["phase"] as? String ?? "") }
    var body: some View {
        Section {
            HStack {
                VStack(alignment: .leading, spacing: 6) {
                    Text("基础运行环境").font(.headline)
                    Text(FileManager.default.isExecutableFile(atPath: AppRuntime.executable(root: m.root).path) ? "已就绪 · 独立发行版包含 Python 和基础解析依赖" : "运行环境缺失 · 请下载完整发行版并保留整个应用包")
                        .font(.callout).foregroundStyle(.secondary)
                }
                Spacer()
                if let url = AppRuntime.releaseURL { Link("下载完整安装包", destination: url) }
            }
            if AppRuntime.releaseURL == nil { Text("此构建尚未连接公开发布仓库；发布时会提供完整安装包下载入口。").font(.callout).foregroundStyle(.secondary) }
            HStack { Text("组件官方来源"); Spacer(); Link("Python", destination: URL(string: "https://www.python.org/downloads/")!); Link("OCR", destination: URL(string: "https://tesseract-ocr.github.io/tessdoc/Installation.html")!); Link("LibreOffice", destination: URL(string: "https://www.libreoffice.org/download/download-libreoffice/")!) }
            ForEach(items.indices, id: \.self) { i in
                let item = items[i]
                let installed = item["installed"] as? Bool ?? false
                let external = item["external"] as? Bool ?? false
                VStack(alignment: .leading, spacing: 8) {
                    Text(item["name"] as? String ?? "").font(.headline)
                    Text(item["description"] as? String ?? "").font(.callout).foregroundStyle(.secondary)
                    Text(installed ? "已安装 · " + size(item["installed_bytes"]) : (external ? "已复用本机组件；无需重复安装" : "按需安装 · 下载 " + size(item["download_bytes"]) + " · 安装后 " + size(item["expanded_bytes"])))
                        .font(.callout).foregroundStyle(.secondary)
                    if !installed && !external && item["url"] == nil { Text("发布者尚未提供此组件的下载地址。").font(.callout).foregroundStyle(.secondary) }
                    HStack {
                        if let source = item["url"] as? String, let url = URL(string: source) { Link("下载来源", destination: url) }
                        Spacer()
                        if installed { Button("移除…") { act(item, remove: true) } }
                        else {
                            Button("导入组件包…") { act(item, remove: false) }
                            Button("下载并安装") { act(item, remove: false, online: true) }
                                .disabled(item["url"] == nil || external)
                        }
                    }.disabled(working || m.busy || m.modelBusy || !m.running)
                }.padding(.vertical, 4)
            }
            if working {
                if job["phase"] as? String == "downloading" {
                    ProgressView("正在下载 \(size(job["done"])) / \(size(job["total"]))", value: (job["done"] as? NSNumber)?.doubleValue ?? 0, total: max(1,(job["total"] as? NSNumber)?.doubleValue ?? 1))
                } else { HStack { ProgressView().controlSize(.small); Text("正在校验和安装组件…") } }
                HStack { Spacer(); Button("取消") { Task { _ = try? await m.post("/components/cancel") } } }
            }
            if let text = job["message"] as? String { Text(text).font(.callout).foregroundStyle(.secondary) }
            if let text = job["error"] as? String { Text(text).font(.callout).foregroundStyle(.secondary) }
            HStack { Text("AGPL-3.0 开源软件"); Spacer(); Link("许可证与对应源码", destination: URL(string: "https://github.com/yzc021101/Research-Library/tree/v0.6.4")!) }
        } header: { Text("运行环境与可选组件") } footer: { Text("基础运行环境随完整 App 提供，无需单独安装 Python。OCR 与旧版 Office 转换器按需联网下载，校验后安装到本应用的资料库目录。安装或移除后重启服务；系统已有软件保持不变。") }
    }
    func size(_ value: Any?) -> String { ByteCountFormatter.string(fromByteCount: (value as? NSNumber)?.int64Value ?? 0, countStyle: .file) }
    func act(_ item: [String: Any], remove: Bool, online: Bool = false) {
        guard let id = item["id"] as? String else { return }
        var payload: [String: Any] = ["id": id]
        if remove {
            let alert = NSAlert(); alert.messageText = "移除此可选组件？"; alert.informativeText = "保留已录入的文字与原始资料，需要时可重新安装。"; alert.addButton(withTitle: "移除"); alert.addButton(withTitle: "取消")
            guard alert.runModal() == .alertFirstButtonReturn else { return }
        } else if !online {
            let panel = NSOpenPanel(); panel.title = "选择与此版本配套的组件 ZIP"; panel.allowsMultipleSelection = false; panel.canChooseDirectories = false
            guard panel.runModal() == .OK, let url = panel.url else { return }
            payload["path"] = url.path
        }
        Task { do { _ = try await m.post(remove ? "/components/remove" : "/components/install", payload); await m.refresh() } catch { m.message = error.localizedDescription } }
    }
}
